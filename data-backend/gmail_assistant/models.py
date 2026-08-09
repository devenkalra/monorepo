"""Gmail Assistant models — accounts, prefs, prompts, summaries, jobs.

Zero-knowledge mode (UserPreference.zero_knowledge): never store email content
fields (subject/from/snippet/body/summary text). Category + confidence OK.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


CATEGORIES = (
    'Marketing',
    'Newsletter',
    'Offer',
    'Receipt',
    'Important',
    'Personal',
    'Work',
    'Social',
    'Spam',
    'Other',
)


class GmailAccount(models.Model):
    """One connected Gmail mailbox for a bldrdojo user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gmail_accounts',
    )
    email = models.EmailField()
    label = models.CharField(max_length=120, blank=True, default='')
    refresh_token = models.TextField()
    scopes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=False)
    last_error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['email']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'email'],
                name='gmail_assistant_account_user_email_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f'{self.email} ({self.user_id})'


class UserPreference(models.Model):
    """Per-user preferences for Gmail Assistant."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gmail_assistant_prefs',
    )
    # Default OFF: persist summaries like aiserver when False.
    zero_knowledge = models.BooleanField(default=False)
    llm_context_size = models.PositiveIntegerField(default=8192)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'prefs:{self.user_id}'


class SavedPrompt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gmail_saved_prompts',
    )
    label = models.CharField(max_length=120)
    prompt = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['label']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'label'],
                name='gmail_assistant_prompt_user_label_uniq',
            ),
        ]

    def __str__(self):
        return self.label


class EmailSummary(models.Model):
    """Summary / metadata for a Gmail message.

    In zero-knowledge mode only gmail_id/thread_id + category/confidence
    (and empty content fields) may be stored — callers must enforce this.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gmail_summaries',
    )
    account = models.ForeignKey(
        GmailAccount,
        on_delete=models.CASCADE,
        related_name='summaries',
    )
    gmail_id = models.CharField(max_length=64)
    thread_id = models.CharField(max_length=64, blank=True, default='')
    subject = models.TextField(blank=True, default='')
    from_addr = models.TextField(blank=True, default='')
    snippet = models.TextField(blank=True, default='')
    date_iso = models.CharField(max_length=64, blank=True, default='')
    internal_date_ms = models.BigIntegerField(default=0)
    brief_summary = models.TextField(blank=True, default='')
    key_points = models.JSONField(default=list, blank=True)
    details = models.TextField(blank=True, default='')
    category = models.CharField(max_length=40, blank=True, default='')
    category_confidence = models.FloatField(default=0)
    labels = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, default='active')
    model = models.CharField(max_length=120, blank=True, default='')
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['account', 'gmail_id'],
                name='gmail_assistant_summary_account_mid_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'account']),
            models.Index(fields=['gmail_id']),
        ]

    def __str__(self):
        return self.gmail_id


class LlmJob(models.Model):
    KIND_SUMMARIZE = 'summarize'
    KIND_PROCESS = 'process'
    KIND_CHOICES = (
        (KIND_SUMMARIZE, 'Summarize'),
        (KIND_PROCESS, 'Process'),
    )

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gmail_llm_jobs',
    )
    account = models.ForeignKey(
        GmailAccount,
        on_delete=models.CASCADE,
        related_name='llm_jobs',
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    celery_task_id = models.CharField(max_length=64, blank=True, default='')
    gmail_ids = models.JSONField(default=list, blank=True)
    prompt = models.TextField(blank=True, default='')
    # Process result discarded in ZK; otherwise may hold final text.
    result = models.TextField(blank=True, default='')
    progress = models.JSONField(default=dict, blank=True)
    errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.kind}:{self.status}:{self.id}'
