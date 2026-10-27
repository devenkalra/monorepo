"""Mailbox sync, classify, and workflow orchestration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import gmail as gmail_api
from .classifier import (
    bypass_intent_for_recipients,
    classify_with_openai,
    extract_recipient_addresses,
    should_auto_run,
    workflow_kind_for_intent,
)
from .models import Classification, EmailJob, EmailMessage, MailboxAccount
from .workflows import run_workflow

logger = logging.getLogger(__name__)


def enqueue_job(job_type, mailbox=None, message=None, payload=None, run_after=None):
    return EmailJob.objects.create(
        job_type=job_type,
        mailbox=mailbox,
        message=message,
        payload=payload or {},
        run_after=run_after,
    )


def get_active_mailbox():
    return MailboxAccount.objects.filter(is_active=True).exclude(refresh_token='').first()


def service_for(mailbox):
    return gmail_api.build_gmail_service(mailbox.refresh_token)


def renew_watch(mailbox=None):
    mailbox = mailbox or get_active_mailbox()
    if not mailbox:
        raise RuntimeError('No active mailbox connected')
    topic = getattr(settings, 'EMAIL_PUBSUB_TOPIC', '') or ''
    if not topic:
        raise RuntimeError('EMAIL_PUBSUB_TOPIC is not configured')
    service = service_for(mailbox)
    gmail_api.ensure_label(service, gmail_api.LABEL_PROCESSED)
    gmail_api.ensure_label(service, gmail_api.LABEL_NEEDS_REVIEW)
    result = gmail_api.start_watch(service, topic)
    mailbox.history_id = str(result.get('historyId') or mailbox.history_id)
    exp_ms = result.get('expiration')
    if exp_ms:
        mailbox.watch_expiration = datetime.fromtimestamp(
            int(exp_ms) / 1000.0, tz=dt_timezone.utc,
        )
    mailbox.last_error = ''
    mailbox.save(update_fields=['history_id', 'watch_expiration', 'last_error', 'updated_at'])
    return result


def reconcile_mailbox(mailbox=None):
    mailbox = mailbox or get_active_mailbox()
    if not mailbox:
        raise RuntimeError('No active mailbox connected')
    service = service_for(mailbox)
    message_ids = []
    if mailbox.history_id:
        try:
            for mid, latest in gmail_api.list_history(service, mailbox.history_id):
                message_ids.append(mid)
                mailbox.history_id = latest
        except Exception as exc:
            logger.warning('history.list failed (%s); falling back to inbox list', exc)
            message_ids = gmail_api.list_recent_inbox_ids(service, max_results=100)
            profile = service.users().getProfile(userId='me').execute()
            mailbox.history_id = str(profile.get('historyId') or mailbox.history_id)
    else:
        message_ids = gmail_api.list_recent_inbox_ids(service, max_results=100)
        profile = service.users().getProfile(userId='me').execute()
        mailbox.history_id = str(profile.get('historyId') or '')

    mailbox.last_sync_at = timezone.now()
    mailbox.last_error = ''
    mailbox.save(update_fields=['history_id', 'last_sync_at', 'last_error', 'updated_at'])

    unique_ids = list(dict.fromkeys(message_ids))
    for mid in unique_ids:
        if EmailMessage.objects.filter(gmail_id=mid).exists():
            continue
        enqueue_job(EmailJob.JobType.FETCH_MESSAGE, mailbox=mailbox, payload={'gmail_id': mid})
    return {'enqueued': len(unique_ids), 'history_id': mailbox.history_id}


def upsert_message_from_gmail(mailbox, raw):
    headers = gmail_api.header_map(raw.get('payload') or {})
    subject = headers.get('subject', '')
    from_address = headers.get('from', '')
    to_addresses = headers.get('to', '')
    received_at = gmail_api.parse_received_at(raw.get('internalDate'), headers.get('date', ''))
    msg, created = EmailMessage.objects.update_or_create(
        gmail_id=raw['id'],
        defaults={
            'mailbox': mailbox,
            'thread_id': raw.get('threadId') or '',
            'history_id': str(raw.get('historyId') or ''),
            'subject': subject[:500],
            'from_address': from_address[:320],
            'to_addresses': to_addresses,
            'snippet': raw.get('snippet') or '',
            'received_at': received_at,
            'label_ids': raw.get('labelIds') or [],
        },
    )
    if created or msg.status == EmailMessage.Status.NEW:
        enqueue_job(EmailJob.JobType.CLASSIFY, mailbox=mailbox, message=msg)
    return msg, created


def fetch_and_store_message(mailbox, gmail_id):
    service = service_for(mailbox)
    raw = gmail_api.fetch_message(service, gmail_id)
    return upsert_message_from_gmail(mailbox, raw)


def classify_message(message):
    mailbox = message.mailbox
    service = service_for(mailbox)
    raw = gmail_api.fetch_message(service, message.gmail_id)
    headers = gmail_api.header_map(raw.get('payload') or {})
    plain, html = gmail_api.get_text_bodies(raw.get('payload') or {})
    body_text = plain or html
    recipients = extract_recipient_addresses(message.to_addresses, headers)
    bypass = bypass_intent_for_recipients(recipients)

    if bypass:
        data = {
            'intent': bypass,
            'confidence': 1.0,
            'summary': message.snippet or message.subject,
            'reason': f'Direct alias route ({bypass})',
            'extracted': {
                'title': message.subject or 'Writing idea',
                'urls': [],
                'tags': [],
                'is_newsletter': False,
                'is_automated': False,
                'has_images': bypass == 'image_ingest',
                'sender_role': 'unknown',
            },
            'suggested_actions': [],
            'risk_flags': [],
            'model': 'bypass',
        }
        bypassed = True
    else:
        data = classify_with_openai(
            subject=message.subject,
            from_address=message.from_address,
            to_addresses=message.to_addresses,
            snippet=message.snippet,
            body_text=body_text,
        )
        bypassed = False

    Classification.objects.update_or_create(
        message=message,
        defaults={
            'intent': data['intent'],
            'confidence': data['confidence'],
            'summary': data.get('summary') or '',
            'reason': data.get('reason') or '',
            'extracted': data.get('extracted') or {},
            'suggested_actions': data.get('suggested_actions') or [],
            'risk_flags': data.get('risk_flags') or [],
            'model': data.get('model') or '',
            'raw': data,
            'bypassed_llm': bypassed,
        },
    )

    review_label = gmail_api.ensure_label(service, gmail_api.LABEL_NEEDS_REVIEW)
    processed_label = gmail_api.ensure_label(service, gmail_api.LABEL_PROCESSED)

    if should_auto_run(data):
        kind = workflow_kind_for_intent(data['intent'])
        message.status = EmailMessage.Status.CLASSIFIED
        message.save(update_fields=['status', 'updated_at'])
        enqueue_job(
            EmailJob.JobType.RUN_WORKFLOW,
            mailbox=mailbox,
            message=message,
            payload={'kind': kind},
        )
    else:
        message.status = EmailMessage.Status.NEEDS_REVIEW
        message.save(update_fields=['status', 'updated_at'])
        gmail_api.apply_needs_review(service, message.gmail_id, review_label)

    return data


def execute_workflow_for_message(message, kind=None):
    from .models import WorkflowRun

    mailbox = message.mailbox
    service = service_for(mailbox)
    classification = getattr(message, 'classification', None)
    if not classification:
        raise RuntimeError('Message has no classification')
    data = classification.raw or {
        'intent': classification.intent,
        'confidence': classification.confidence,
        'summary': classification.summary,
        'extracted': classification.extracted,
    }
    kind = kind or workflow_kind_for_intent(classification.intent)
    if not kind:
        raise RuntimeError(f'No workflow for intent {classification.intent}')

    message.status = EmailMessage.Status.PROCESSING
    message.save(update_fields=['status', 'updated_at'])

    raw = gmail_api.fetch_message(service, message.gmail_id)
    try:
        run = run_workflow(kind, service, message, data, gmail_payload=raw)
        processed_label = gmail_api.ensure_label(service, gmail_api.LABEL_PROCESSED)
        gmail_api.mark_processed_and_archive(service, message.gmail_id, processed_label)
        message.status = EmailMessage.Status.PROCESSED
        message.error = ''
        message.save(update_fields=['status', 'error', 'updated_at'])
        return run
    except Exception as exc:
        message.status = EmailMessage.Status.FAILED
        message.error = str(exc)[:2000]
        message.save(update_fields=['status', 'error', 'updated_at'])
        raise


def process_job(job: EmailJob):
    if job.status != EmailJob.Status.RUNNING:
        job.status = EmailJob.Status.RUNNING
    job.attempts += 1
    job.save(update_fields=['status', 'attempts', 'updated_at'])
    try:
        if job.job_type == EmailJob.JobType.RECONCILE:
            reconcile_mailbox(job.mailbox or get_active_mailbox())
        elif job.job_type == EmailJob.JobType.RENEW_WATCH:
            renew_watch(job.mailbox or get_active_mailbox())
        elif job.job_type == EmailJob.JobType.FETCH_MESSAGE:
            mailbox = job.mailbox or get_active_mailbox()
            gmail_id = (job.payload or {}).get('gmail_id')
            if not gmail_id:
                raise RuntimeError('fetch_message missing gmail_id')
            fetch_and_store_message(mailbox, gmail_id)
        elif job.job_type == EmailJob.JobType.CLASSIFY:
            if not job.message:
                raise RuntimeError('classify missing message')
            data = classify_message(job.message)
            job.message.refresh_from_db()
            payload = dict(job.payload or {})
            payload['result'] = {
                'intent': data.get('intent'),
                'confidence': data.get('confidence'),
                'summary': (data.get('summary') or '')[:500],
                'reason': (data.get('reason') or '')[:500],
                'message_status': job.message.status,
                'next': (
                    'run_workflow'
                    if job.message.status == EmailMessage.Status.CLASSIFIED
                    else job.message.status
                ),
            }
            job.payload = payload
        elif job.job_type == EmailJob.JobType.RUN_WORKFLOW:
            if not job.message:
                raise RuntimeError('run_workflow missing message')
            run = execute_workflow_for_message(
                job.message, kind=(job.payload or {}).get('kind'),
            )
            payload = dict(job.payload or {})
            payload['result'] = {
                'workflow_run_id': getattr(run, 'pk', None),
                'kind': getattr(run, 'kind', None),
                'status': getattr(run, 'status', None),
                'external_ids': getattr(run, 'external_ids', None) or {},
            }
            job.payload = payload
        else:
            raise RuntimeError(f'Unknown job type {job.job_type}')
        job.status = EmailJob.Status.DONE
        job.error = ''
        job.save(update_fields=['status', 'error', 'payload', 'updated_at'])
    except Exception as exc:
        logger.exception('Job %s failed', job.pk)
        job.error = str(exc)[:2000]
        if job.attempts >= job.max_attempts:
            job.status = EmailJob.Status.FAILED
        else:
            job.status = EmailJob.Status.PENDING
            job.run_after = timezone.now() + timedelta(minutes=min(30, 2 ** job.attempts))
        job.save(update_fields=['status', 'error', 'run_after', 'updated_at'])


def claim_next_job():
    now = timezone.now()
    with transaction.atomic():
        job = (
            EmailJob.objects
            .select_for_update()
            .filter(status=EmailJob.Status.PENDING)
            .filter(Q(run_after__isnull=True) | Q(run_after__lte=now))
            .order_by('id')
            .first()
        )
        if not job:
            return None
        job.status = EmailJob.Status.RUNNING
        job.save(update_fields=['status', 'updated_at'])
        return job


def schedule_maintenance():
    """Enqueue watch renew / reconcile if due."""
    mailbox = get_active_mailbox()
    if not mailbox:
        return
    now = timezone.now()
    if (
        not mailbox.watch_expiration
        or mailbox.watch_expiration <= now + timedelta(days=1)
    ):
        if not EmailJob.objects.filter(
            job_type=EmailJob.JobType.RENEW_WATCH,
            status=EmailJob.Status.PENDING,
            mailbox=mailbox,
        ).exists():
            enqueue_job(EmailJob.JobType.RENEW_WATCH, mailbox=mailbox)

    stale = (not mailbox.last_sync_at) or (mailbox.last_sync_at <= now - timedelta(minutes=60))
    if stale and not EmailJob.objects.filter(
        job_type=EmailJob.JobType.RECONCILE,
        status__in=[EmailJob.Status.PENDING, EmailJob.Status.RUNNING],
        mailbox=mailbox,
    ).exists():
        enqueue_job(EmailJob.JobType.RECONCILE, mailbox=mailbox)
