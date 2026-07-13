from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
import os
import logging
from datetime import datetime, timezone as dt_timezone
from .models import EmailAccount, ImportConfig, Email
from .imap_service import IMAPService

logger = logging.getLogger(__name__)


def update_task_progress(task_id, current, total, message, status='processing'):
    """Update task progress in cache"""
    progress_data = {
        'task_id': task_id,
        'status': status,
        'current': current,
        'total': total,
        'percentage': int((current / total * 100)) if total > 0 else 0,
        'message': message,
    }
    cache.set(f'task_progress_{task_id}', progress_data, timeout=3600)
    logger.info(f"Task {task_id}: {message} ({current}/{total})")


def check_task_cancelled(task_id):
    """Check if task has been marked for cancellation"""
    return cache.get(f'task_cancel_{task_id}', False)


class TASK_CANCELLED_BY_USER(Exception):
    """Custom exception for user-initiated task cancellation"""
    pass


@shared_task(bind=True)
def import_emails_async(self, config_id, user_id):
    """
    Async task to import emails from an IMAP account
    
    Args:
        config_id: ImportConfig ID
        user_id: User ID
    """
    task_id = self.request.id
    logger.info(f"Starting email import task {task_id} for config {config_id}")
    
    try:
        # Initial progress
        update_task_progress(task_id, 0, 100, 'Starting email import...', 'processing')
        
        # Load config
        from django.contrib.auth.models import User
        config = ImportConfig.objects.select_related('account').get(id=config_id, user_id=user_id)
        account = config.account
        user = User.objects.get(id=user_id)
        
        update_task_progress(task_id, 5, 100, f'Connecting to {account.imap_host}...', 'processing')
        
        # Check cancellation
        if check_task_cancelled(task_id):
            raise TASK_CANCELLED_BY_USER()
        
        # Connect to IMAP
        with IMAPService(
            host=account.imap_host,
            port=account.imap_port,
            username=account.username,
            password=account.password,
            use_ssl=account.imap_use_ssl
        ) as imap:
            
            update_task_progress(task_id, 10, 100, f'Searching emails in {config.mailbox}...', 'processing')
            
            # Search for emails
            search_criteria = config.get_imap_search_criteria()
            email_ids = imap.search_emails(
                mailbox=config.mailbox,
                search_criteria=search_criteria,
                max_count=config.max_emails
            )
            
            total_emails = len(email_ids)
            if total_emails == 0:
                update_task_progress(task_id, 100, 100, 'No emails found matching criteria', 'completed')
                return {'success': True, 'imported': 0, 'skipped': 0, 'errors': 0}
            
            update_task_progress(task_id, 15, 100, f'Found {total_emails} emails to import...', 'processing')
            
            # Check cancellation
            if check_task_cancelled(task_id):
                raise TASK_CANCELLED_BY_USER()
            
            # Base storage directory for .eml files
            media_root = settings.MEDIA_ROOT
            base_storage_dir = os.path.join(media_root, 'emails', str(user_id), str(account.id))
            logger.info(f"Base storage directory: {base_storage_dir}")
            
            imported = 0
            skipped = 0
            errors = 0
            
            # Process each email
            for idx, email_id in enumerate(email_ids, 1):
                try:
                    # Check cancellation every 5 emails
                    if idx % 5 == 0 and check_task_cancelled(task_id):
                        raise TASK_CANCELLED_BY_USER()
                    
                    # Fetch email
                    email_data = imap.fetch_email(email_id)
                    
                    # Check if already imported
                    if Email.objects.filter(user=user, message_id=email_data['message_id']).exists():
                        skipped += 1
                        logger.debug(f"Skipping duplicate email: {email_data['message_id']}")
                        continue
                    
                    # Save .eml file with format: YYYYMMDDhhmmss_sender_uid.eml in yyyy/mm/ subfolder
                    email_date = email_data['date'] or timezone.now()
                    # Convert to GMT/UTC for consistent naming
                    email_date_utc = email_date.astimezone(dt_timezone.utc) if email_date.tzinfo else email_date.replace(tzinfo=dt_timezone.utc)
                    date_str = email_date_utc.strftime('%Y%m%d%H%M%S')
                    year_month = email_date_utc.strftime('%Y/%m')
                    
                    # Create year/month subdirectory
                    storage_dir = os.path.join(base_storage_dir, year_month)
                    os.makedirs(storage_dir, exist_ok=True)
                    
                    # Extract sender email or name from from_address
                    from_addr = email_data['from_address']
                    # Parse "Name <email@domain.com>" or just "email@domain.com"
                    if '<' in from_addr and '>' in from_addr:
                        # Extract email between < >
                        sender = from_addr.split('<')[1].split('>')[0].strip()
                    else:
                        sender = from_addr.strip()
                    
                    # Sanitize sender for filename (remove invalid chars)
                    sender_safe = ''.join(c if c.isalnum() or c in '.-_@' else '_' for c in sender)
                    uid_str = email_data['uid']
                    eml_filename = f"{date_str}_{sender_safe}_{uid_str}.eml"
                    eml_absolute_path = os.path.join(storage_dir, eml_filename)
                    eml_relative_path = os.path.join('emails', str(user_id), str(account.id), year_month, eml_filename)
                    
                    with open(eml_absolute_path, 'wb') as f:
                        f.write(email_data['raw_content'])
                    
                    file_size = os.path.getsize(eml_absolute_path)
                    logger.debug(f"Saved .eml file: {eml_absolute_path} ({file_size} bytes)")
                    
                    # Create Email record (store relative path for portability)
                    Email.objects.create(
                        user=user,
                        account=account,
                        message_id=email_data['message_id'],
                        subject=email_data['subject'][:500] if email_data['subject'] else '',
                        from_address=email_data['from_address'][:500],
                        to_addresses=email_data['to_addresses'],
                        cc_addresses=email_data['cc_addresses'],
                        bcc_addresses=email_data['bcc_addresses'],
                        date=email_data['date'] or timezone.now(),
                        body_text=email_data['body_text'],
                        body_html=email_data['body_html'],
                        has_attachments=email_data['has_attachments'],
                        attachment_count=email_data['attachment_count'],
                        eml_file_path=eml_relative_path,
                        file_size=file_size,
                    )
                    
                    imported += 1
                    
                    # Update progress
                    progress = 15 + int((idx / total_emails) * 80)
                    update_task_progress(
                        task_id, 
                        progress, 
                        100, 
                        f'Imported {imported} of {total_emails} emails...', 
                        'processing'
                    )
                    
                except Exception as e:
                    errors += 1
                    logger.error(f"Error importing email {email_id}: {str(e)}")
            
            # Update last sync time
            account.last_sync = timezone.now()
            account.save()
            
            # Final progress
            update_task_progress(
                task_id, 
                100, 
                100, 
                f'Import complete: {imported} imported, {skipped} skipped, {errors} errors', 
                'completed'
            )
            
            return {
                'success': True,
                'imported': imported,
                'skipped': skipped,
                'errors': errors,
                'total': total_emails
            }
    
    except TASK_CANCELLED_BY_USER:
        logger.info(f"Email import task {task_id} cancelled by user")
        update_task_progress(task_id, 0, 0, 'Task cancelled by user', 'cancelled')
        return {'success': False, 'cancelled': True}
    
    except Exception as e:
        logger.error(f"Email import task {task_id} failed: {str(e)}")
        update_task_progress(task_id, 0, 0, f'Error: {str(e)}', 'failed')
        return {'success': False, 'error': str(e)}
