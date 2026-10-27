from django.db import models


class GoogleAccount(models.Model):
    """The single Google account whose contacts are synced."""
    email = models.EmailField(blank=True, default='')
    refresh_token = models.TextField(blank=True, default='')
    scopes = models.TextField(blank=True, default='')
    last_error = models.TextField(blank=True, default='')
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def can_write(self):
        return 'https://www.googleapis.com/auth/contacts' in self.scopes.split()

    def __str__(self):
        return self.email or f'Google account #{self.pk}'


class ContactsState(models.Model):
    """Small key/value store: Google sync token, ignore patterns, last list check, OAuth state."""
    key = models.CharField(max_length=64, unique=True)
    value = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get(cls, key, default=None):
        row = cls.objects.filter(key=key).first()
        return row.value if row else default

    @classmethod
    def put(cls, key, value):
        cls.objects.update_or_create(key=key, defaults={'value': value})

    def __str__(self):
        return self.key


class SourceFile(models.Model):
    class Kind(models.TextChoices):
        LINKEDIN_CONNECTIONS = 'linkedin_connections', 'LinkedIn connections'
        LINKEDIN_MESSAGES = 'linkedin_messages', 'LinkedIn messages'
        WHATSAPP = 'whatsapp', 'WhatsApp export'
        CONTACTS_EXPORT = 'contacts_export', 'Contacts export'

    kind = models.CharField(max_length=32, choices=Kind.choices)
    original_name = models.CharField(max_length=255)
    path = models.CharField(max_length=500, help_text='Relative to CONTACTS_DATA_DIR')
    size = models.PositiveIntegerField(default=0)
    rows = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, default='')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.get_kind_display()}: {self.original_name}'


class SyncRun(models.Model):
    class Source(models.TextChoices):
        GOOGLE = 'google', 'Google'
        LINKEDIN = 'linkedin', 'LinkedIn'
        WHATSAPP = 'whatsapp', 'WhatsApp'
        MERGE = 'merge', 'Merge'
        EXPORT = 'export', 'Export'
        IMPORT = 'import', 'Import'

    class Mode(models.TextChoices):
        DRY = 'dry', 'Dry run'
        LIVE = 'live', 'Live'

    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        RUNNING = 'running', 'Running'
        DONE = 'done', 'Done'
        FAILED = 'failed', 'Failed'
        STOPPED = 'stopped', 'Stopped by a safety check'
        CANCELLED = 'cancelled', 'Cancelled'
        INTERRUPTED = 'interrupted', 'Interrupted'

    source = models.CharField(max_length=16, choices=Source.choices)
    mode = models.CharField(max_length=8, choices=Mode.choices, default=Mode.DRY)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    options = models.JSONField(default=dict, blank=True)
    files = models.ManyToManyField(SourceFile, blank=True, related_name='runs')
    plan = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='applied_by',
                             help_text='The dry run this live run applies')
    max_ops = models.PositiveIntegerField(null=True, blank=True, help_text='Write budget for live runs')
    ops = models.PositiveIntegerField(default=0, help_text='Writes planned (dry) or made (live)')
    stats = models.JSONField(default=dict, blank=True)
    actions = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    unknown_groups = models.JSONField(default=dict, blank=True)
    unknown_sources = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True, default='')
    phase = models.CharField(max_length=80, blank=True, default='')
    progress_done = models.PositiveIntegerField(default=0)
    progress_total = models.PositiveIntegerField(default=0)
    cancel_requested = models.BooleanField(default=False)
    foreground = models.BooleanField(default=False, help_text='Run by the CLI, not the background worker')
    snapshot_path = models.CharField(max_length=500, blank=True, default='')
    output = models.ForeignKey(SourceFile, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
                               help_text='The file an export run wrote')
    created_by = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-id']

    @property
    def is_live(self):
        return self.mode == self.Mode.LIVE

    def __str__(self):
        return f'#{self.pk} {self.source} {self.mode} {self.status}'


class ChangeLog(models.Model):
    """One ClickUp (or Google) write made by a live run, recorded before it is sent."""
    run = models.ForeignKey(SyncRun, on_delete=models.CASCADE, related_name='changes')
    op = models.CharField(max_length=24)
    task_id = models.CharField(max_length=64, db_index=True)
    task_name = models.CharField(max_length=500, blank=True, default='')
    field = models.CharField(max_length=80, blank=True, default='')
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    ok = models.BooleanField(default=False)
    error = models.TextField(blank=True, default='')
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.op} {self.task_id} {self.field}'


class EntityCache(models.Model):
    """A row of the People & Orgs list view, copied from ClickUp so the list loads without reading 4,000 tasks."""
    task_id = models.CharField(max_length=64, unique=True)
    list_key = models.CharField(max_length=16, db_index=True)
    row = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.list_key}: {self.row.get("name", self.task_id)}'


class EntityEdit(models.Model):
    """One save from the People & Orgs editor, with every ClickUp write it made."""
    task_id = models.CharField(max_length=64, db_index=True)
    task_name = models.CharField(max_length=500, blank=True, default='')
    changes = models.JSONField(default=list, blank=True)
    ok = models.BooleanField(default=False)
    error = models.TextField(blank=True, default='')
    edited_by = models.CharField(max_length=255, blank=True, default='')
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f'{self.task_name or self.task_id} by {self.edited_by}'


class ImportedTask(models.Model):
    """A task created by an import, so an interrupted import resumes instead of creating it twice."""
    import_key = models.CharField(max_length=200, db_index=True,
                                  help_text='Export file hash + target list IDs')
    list_key = models.CharField(max_length=16)
    source_id = models.CharField(max_length=64)
    target_id = models.CharField(max_length=64)
    run = models.ForeignKey(SyncRun, null=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['import_key', 'source_id'], name='contacts_imported_once')]

    def __str__(self):
        return f'{self.source_id} -> {self.target_id}'


class ReviewItem(models.Model):
    """An uncertain name match that needs a person to say 'same' or 'new'."""

    class Decision(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SAME = 'same', 'Same person'
        NEW = 'new', 'Different person'

    source = models.CharField(max_length=16, choices=SyncRun.Source.choices)
    key = models.CharField(max_length=500)
    name = models.CharField(max_length=500, blank=True, default='')
    company = models.CharField(max_length=500, blank=True, default='')
    title = models.CharField(max_length=500, blank=True, default='')
    suggested_task_id = models.CharField(max_length=64, blank=True, default='')
    suggested_task_name = models.CharField(max_length=500, blank=True, default='')
    note = models.TextField(blank=True, default='')
    decision = models.CharField(max_length=16, choices=Decision.choices, default=Decision.PENDING, db_index=True)
    chosen_task_id = models.CharField(max_length=64, blank=True, default='')
    decided_by = models.CharField(max_length=255, blank=True, default='')
    decided_at = models.DateTimeField(null=True, blank=True)
    last_seen_run = models.ForeignKey(SyncRun, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['source', 'name']
        constraints = [models.UniqueConstraint(fields=['source', 'key'], name='contacts_review_source_key')]

    def __str__(self):
        return f'{self.source}: {self.name} ({self.decision})'
