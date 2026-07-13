import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class IMAPService:
    """Service for connecting to IMAP servers and downloading emails"""
    
    def __init__(self, host, port, username, password, use_ssl=True):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.connection = None
    
    def connect(self):
        """Establish connection to IMAP server"""
        try:
            if self.use_ssl:
                self.connection = imaplib.IMAP4_SSL(self.host, self.port)
            else:
                self.connection = imaplib.IMAP4(self.host, self.port)
            
            self.connection.login(self.username, self.password)
            logger.info(f"Successfully connected to {self.host} as {self.username}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to IMAP server: {str(e)}")
            raise
    
    def disconnect(self):
        """Close IMAP connection"""
        if self.connection:
            try:
                self.connection.logout()
            except:
                pass
            self.connection = None
    
    def list_mailboxes(self):
        """List all available mailboxes"""
        if not self.connection:
            raise Exception("Not connected to IMAP server")
        
        status, mailboxes = self.connection.list()
        if status != 'OK':
            raise Exception(f"Failed to list mailboxes: {status}")
        
        return [mb.decode() for mb in mailboxes]
    
    def search_emails(self, mailbox='INBOX', search_criteria='ALL', max_count=100):
        """
        Search for emails in a mailbox
        
        Args:
            mailbox: Mailbox name (e.g., 'INBOX', '[Gmail]/All Mail')
            search_criteria: IMAP search criteria (e.g., 'FROM "user@example.com"')
            max_count: Maximum number of emails to return
        
        Returns:
            List of email UIDs
        """
        if not self.connection:
            raise Exception("Not connected to IMAP server")
        
        # Select mailbox
        status, messages = self.connection.select(mailbox, readonly=True)
        if status != 'OK':
            raise Exception(f"Failed to select mailbox {mailbox}: {status}")
        
        # Search for emails
        status, data = self.connection.search(None, search_criteria)
        if status != 'OK':
            raise Exception(f"Search failed: {status}")
        
        # Get email UIDs
        email_ids = data[0].split()
        
        # Limit results
        if max_count and len(email_ids) > max_count:
            email_ids = email_ids[-max_count:]  # Get most recent
        
        logger.info(f"Found {len(email_ids)} emails in {mailbox} matching criteria: {search_criteria}")
        return email_ids
    
    def fetch_email(self, email_id):
        """
        Fetch a single email by ID
        
        Returns:
            dict with email metadata and raw content
        """
        if not self.connection:
            raise Exception("Not connected to IMAP server")
        
        # Fetch email
        status, data = self.connection.fetch(email_id, '(RFC822)')
        if status != 'OK':
            raise Exception(f"Failed to fetch email {email_id}: {status}")
        
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        # Parse email metadata
        metadata = self._parse_email_metadata(msg)
        metadata['raw_content'] = raw_email
        metadata['uid'] = email_id.decode() if isinstance(email_id, bytes) else str(email_id)
        
        return metadata
    
    def _parse_email_metadata(self, msg):
        """Extract metadata from email message"""
        
        # Decode subject
        subject = self._decode_header(msg.get('Subject', ''))
        
        # Get addresses
        from_address = self._decode_header(msg.get('From', ''))
        to_addresses = self._parse_address_list(msg.get('To', ''))
        cc_addresses = self._parse_address_list(msg.get('Cc', ''))
        bcc_addresses = self._parse_address_list(msg.get('Bcc', ''))
        
        # Get dates
        date_str = msg.get('Date')
        try:
            date = parsedate_to_datetime(date_str) if date_str else None
        except:
            date = None
        
        # Get message ID
        message_id = msg.get('Message-ID', '')
        
        # Extract body
        body_text = ''
        body_html = ''
        attachments = []
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get('Content-Disposition', ''))
                
                if 'attachment' in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        attachments.append(self._decode_header(filename))
                elif content_type == 'text/plain' and not body_text:
                    try:
                        body_text = part.get_payload(decode=True).decode()
                    except:
                        pass
                elif content_type == 'text/html' and not body_html:
                    try:
                        body_html = part.get_payload(decode=True).decode()
                    except:
                        pass
        else:
            # Not multipart
            content_type = msg.get_content_type()
            try:
                payload = msg.get_payload(decode=True).decode()
                if content_type == 'text/plain':
                    body_text = payload
                elif content_type == 'text/html':
                    body_html = payload
            except:
                pass
        
        return {
            'message_id': message_id,
            'subject': subject,
            'from_address': from_address,
            'to_addresses': to_addresses,
            'cc_addresses': cc_addresses,
            'bcc_addresses': bcc_addresses,
            'date': date,
            'body_text': body_text,
            'body_html': body_html,
            'attachments': attachments,
            'has_attachments': len(attachments) > 0,
            'attachment_count': len(attachments),
        }
    
    def _decode_header(self, header_value):
        """Decode email header that might be encoded"""
        if not header_value:
            return ''
        
        decoded_parts = decode_header(header_value)
        result = []
        
        for content, encoding in decoded_parts:
            if isinstance(content, bytes):
                try:
                    result.append(content.decode(encoding or 'utf-8'))
                except:
                    result.append(content.decode('utf-8', errors='replace'))
            else:
                result.append(str(content))
        
        return ''.join(result)
    
    def _parse_address_list(self, address_str):
        """Parse comma-separated email addresses"""
        if not address_str:
            return []
        
        decoded = self._decode_header(address_str)
        addresses = [addr.strip() for addr in decoded.split(',')]
        return [addr for addr in addresses if addr]
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
