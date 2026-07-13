from django.db import models
from django.contrib.auth.models import User
from django.core.validators import EmailValidator
import json


class EmailAccount(models.Model):
    """Stores IMAP email account credentials"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_accounts')
    name = models.CharField(max_length=255, help_text="Friendly name for this account")
    email_address = models.EmailField(validators=[EmailValidator()])
    
    # IMAP settings
    imap_host = models.CharField(max_length=255, help_text="IMAP server hostname (e.g., imap.gmail.com)")
    imap_port = models.IntegerField(default=993, help_text="IMAP port (usually 993 for SSL)")
    imap_use_ssl = models.BooleanField(default=True)
    
    # Credentials (consider encrypting in production)
    username = models.CharField(max_length=255, help_text="IMAP username (usually email address)")
    password = models.CharField(max_length=255, help_text="IMAP password or app-specific password")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_sync = models.DateTimeField(null=True, blank=True, help_text="Last successful sync timestamp")
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = [['user', 'email_address']]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.email_address})"


class ImportConfig(models.Model):
    """Stores import filter configurations for an email account"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='import_configs')
    account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE, related_name='import_configs')
    name = models.CharField(max_length=255, help_text="Name for this import configuration")
    
    # Filter criteria
    mailbox = models.CharField(max_length=255, default='INBOX', help_text="Mailbox/folder to import from")
    from_filter = models.CharField(max_length=255, blank=True, help_text="Filter by sender email")
    to_filter = models.CharField(max_length=255, blank=True, help_text="Filter by recipient email")
    subject_filter = models.CharField(max_length=255, blank=True, help_text="Filter by subject keywords")
    labels = models.JSONField(default=list, blank=True, help_text="Gmail labels to filter by")
    since_date = models.DateField(null=True, blank=True, help_text="Only import emails after this date")
    to_date = models.DateField(null=True, blank=True, help_text="Only import emails before this date")
    
    # Import settings
    max_emails = models.IntegerField(default=100, help_text="Maximum number of emails to import per run")
    is_active = models.BooleanField(default=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.account.email_address}"
    
    def get_imap_search_criteria(self):
        """Build IMAP search criteria from filters"""
        criteria = []
        
        if self.from_filter:
            criteria.append(f'FROM "{self.from_filter}"')
        if self.to_filter:
            criteria.append(f'TO "{self.to_filter}"')
        if self.subject_filter:
            criteria.append(f'SUBJECT "{self.subject_filter}"')
        if self.since_date:
            criteria.append(f'SINCE {self.since_date.strftime("%d-%b-%Y")}')
        if self.to_date:
            criteria.append(f'BEFORE {self.to_date.strftime("%d-%b-%Y")}')
        
        return ' '.join(criteria) if criteria else 'ALL'


class Email(models.Model):
    """Stores imported email metadata and references to .eml files"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='emails')
    account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE, related_name='emails')
    
    # Email metadata
    message_id = models.CharField(max_length=500, help_text="Unique message ID from email header")
    subject = models.TextField(blank=True)
    from_address = models.CharField(max_length=500)
    to_addresses = models.JSONField(default=list, help_text="List of recipient email addresses")
    cc_addresses = models.JSONField(default=list, blank=True, help_text="List of CC email addresses")
    bcc_addresses = models.JSONField(default=list, blank=True, help_text="List of BCC email addresses")
    
    # Email dates
    date = models.DateTimeField(help_text="Email sent date from headers")
    received_date = models.DateTimeField(null=True, blank=True, help_text="Date received by server")
    
    # Content
    body_text = models.TextField(blank=True, help_text="Plain text body")
    body_html = models.TextField(blank=True, help_text="HTML body")
    has_attachments = models.BooleanField(default=False)
    attachment_count = models.IntegerField(default=0)
    
    # Storage
    eml_file_path = models.CharField(max_length=1000, help_text="Path to stored .eml file")
    file_size = models.IntegerField(default=0, help_text="Size of .eml file in bytes")
    
    # Gmail-specific
    labels = models.JSONField(default=list, blank=True, help_text="Gmail labels")
    thread_id = models.CharField(max_length=255, blank=True, help_text="Email thread ID")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, help_text="When imported into system")
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [['user', 'message_id']]
        ordering = ['-date']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['user', 'from_address']),
            models.Index(fields=['user', 'subject']),
        ]
    
    def __str__(self):
        return f"{self.subject[:50]} - {self.from_address} ({self.date})"
