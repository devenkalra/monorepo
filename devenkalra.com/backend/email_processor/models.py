from django.db import models


class MailboxAccount(models.Model):
    """Single OAuth-connected Gmail mailbox (aliases share this inbox)."""
    email = models.EmailField(unique=True)
    refresh_token = models.TextField(blank=True, default='')
    history_id = models.CharField(max_length=64, blank=True, default='')
    watch_expiration = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Mailbox account'
        verbose_name_plural = 'Mailbox accounts'

    def __str__(self):
        return self.email


class EmailMessage(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'New'
        CLASSIFIED = 'classified', 'Classified'
        PROCESSING = 'processing', 'Processing'
        PROCESSED = 'processed', 'Processed'
        NEEDS_REVIEW = 'needs_review', 'Needs review'
        FAILED = 'failed', 'Failed'
        IGNORED = 'ignored', 'Ignored'

    mailbox = models.ForeignKey(
        MailboxAccount, on_delete=models.CASCADE, related_name='messages',
    )
    gmail_id = models.CharField(max_length=64, unique=True, db_index=True)
    thread_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    history_id = models.CharField(max_length=64, blank=True, default='')
    subject = models.CharField(max_length=500, blank=True, default='')
    from_address = models.CharField(max_length=320, blank=True, default='')
    to_addresses = models.TextField(blank=True, default='', help_text='Comma-separated')
    snippet = models.TextField(blank=True, default='')
    received_at = models.DateTimeField(null=True, blank=True, db_index=True)
    label_ids = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NEW, db_index=True,
    )
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-received_at', '-id']
        verbose_name = 'Email message'
        verbose_name_plural = 'Email messages'

    def __str__(self):
        return f'{self.subject or "(no subject)"} [{self.gmail_id}]'


class Classification(models.Model):
    message = models.OneToOneField(
        EmailMessage, on_delete=models.CASCADE, related_name='classification',
    )
    intent = models.CharField(max_length=40, db_index=True)
    confidence = models.FloatField(default=0.0)
    summary = models.TextField(blank=True, default='')
    reason = models.TextField(blank=True, default='')
    extracted = models.JSONField(default=dict, blank=True)
    suggested_actions = models.JSONField(default=list, blank=True)
    risk_flags = models.JSONField(default=list, blank=True)
    model = models.CharField(max_length=80, blank=True, default='')
    raw = models.JSONField(default=dict, blank=True)
    bypassed_llm = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.intent} ({self.confidence:.2f}) → {self.message_id}'


class WorkflowRun(models.Model):
    class Kind(models.TextChoices):
        WRITING_IDEA = 'writing_idea', 'Writing idea → ClickUp'
        IMAGE_INGEST = 'image_ingest', 'Image → Static files'
        IGNORE = 'ignore', 'Ignore / archive'
        NEWSLETTER = 'newsletter', 'Newsletter process'
        REVIEW = 'review', 'Human review'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    message = models.ForeignKey(
        EmailMessage, on_delete=models.CASCADE, related_name='runs',
    )
    kind = models.CharField(max_length=40, choices=Kind.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True,
    )
    external_ids = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.kind} {self.status} msg={self.message_id}'


class CommandSession(models.Model):
    """Prompt-to-Select session: display number → Gmail id mapping with TTL."""
    session_key = models.CharField(max_length=64, unique=True, db_index=True)
    user_id = models.IntegerField(db_index=True)
    mailbox = models.ForeignKey(
        MailboxAccount, null=True, blank=True, on_delete=models.CASCADE,
        related_name='command_sessions',
    )
    prompt = models.TextField(blank=True, default='')
    gmail_query = models.TextField(blank=True, default='')
    explanation = models.TextField(blank=True, default='')
    items = models.JSONField(default=list, blank=True)
    last_action = models.TextField(blank=True, default='')
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'CommandSession {self.session_key[:8]}… ({len(self.items or [])} items)'


class SavedSearch(models.Model):
    """Persisted Command Center prompts (cross-device / cross-session)."""
    user_id = models.IntegerField(db_index=True)
    label = models.CharField(max_length=120, blank=True, default='')
    prompt = models.TextField()
    gmail_query = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        indexes = [
            models.Index(fields=['user_id', '-updated_at']),
        ]

    def __str__(self):
        return (self.label or self.prompt or self.gmail_query or 'SavedSearch')[:80]


class EmailJob(models.Model):
    class JobType(models.TextChoices):
        RECONCILE = 'reconcile', 'Reconcile history'
        FETCH_MESSAGE = 'fetch_message', 'Fetch message'
        CLASSIFY = 'classify', 'Classify'
        RUN_WORKFLOW = 'run_workflow', 'Run workflow'
        RENEW_WATCH = 'renew_watch', 'Renew Gmail watch'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        DONE = 'done', 'Done'
        FAILED = 'failed', 'Failed'

    job_type = models.CharField(max_length=40, choices=JobType.choices, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True,
    )
    mailbox = models.ForeignKey(
        MailboxAccount, null=True, blank=True, on_delete=models.CASCADE, related_name='jobs',
    )
    message = models.ForeignKey(
        EmailMessage, null=True, blank=True, on_delete=models.CASCADE, related_name='jobs',
    )
    payload = models.JSONField(default=dict, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    run_after = models.DateTimeField(null=True, blank=True, db_index=True)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['status', 'run_after', 'id']),
        ]

    def __str__(self):
        return f'{self.job_type} {self.status} #{self.pk}'
