import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.db import models

from .constants import (
    ACCESS_CHOICES,
    ACCESS_PUBLIC,
    MEDIA_TYPE_CHOICES,
    MEDIA_IMAGE,
    ROLE_CHOICES,
    ROLE_VIEW,
)


class Gallery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='galleries')
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=80)
    description = models.TextField(blank=True, default='')
    cover = models.JSONField(default=dict, blank=True)
    access_mode = models.CharField(max_length=20, choices=ACCESS_CHOICES, default=ACCESS_PUBLIC)
    allow_download = models.BooleanField(default=False)
    source_entity = models.ForeignKey(
        'people.Entity',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='source_galleries',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['owner', 'slug'], name='gallery_owner_slug_uniq'),
        ]
        indexes = [
            models.Index(fields=['owner']),
            models.Index(fields=['access_mode']),
        ]

    def __str__(self):
        return f'{self.title} ({self.slug})'


class GalleryItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gallery = models.ForeignKey(Gallery, on_delete=models.CASCADE, related_name='items')
    sort_order = models.PositiveIntegerField(default=0)
    media_type = models.CharField(max_length=20, choices=MEDIA_TYPE_CHOICES, default=MEDIA_IMAGE)
    # media path under /media/ (relative or absolute site path starting with /media/)
    url = models.CharField(max_length=1000, blank=True, default='')
    # external http(s) URL when source is web
    external_url = models.URLField(max_length=2000, blank=True, default='')
    thumbnail_url = models.CharField(max_length=1000, blank=True, default='')
    title = models.CharField(max_length=255, blank=True, default='')
    caption = models.TextField(blank=True, default='')
    filename = models.CharField(max_length=500, blank=True, default='')
    # Stable key into entity.photos for refresh dedupe (usually the photo url)
    source_photo_key = models.CharField(max_length=1000, blank=True, default='')
    thumbnail_status = models.CharField(
        max_length=20,
        default='ready',
        help_text='ready|pending|failed|n/a',
    )
    analysis = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'created_at']
        indexes = [
            models.Index(fields=['gallery', 'sort_order']),
        ]

    def __str__(self):
        return self.title or self.filename or str(self.id)

    @property
    def display_url(self):
        return self.external_url or self.url


class GalleryShare(models.Model):
    """Per-email share grant with its own password (deactivate by disabling or rotating password)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gallery = models.ForeignKey(Gallery, on_delete=models.CASCADE, related_name='shares')
    email = models.EmailField()
    password_hash = models.CharField(max_length=128)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_VIEW)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['gallery', 'email'], name='gallery_share_email_uniq'),
        ]

    def __str__(self):
        return f'{self.email} → {self.gallery.slug} ({self.role})'

    def set_password(self, raw_password: str):
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password(raw_password, self.password_hash)


class GalleryShow(models.Model):
    """Scripted slideshow config (FolderBrowser-compatible JSON in `config`)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gallery = models.ForeignKey(Gallery, on_delete=models.CASCADE, related_name='shows')
    slug = models.SlugField(max_length=80)
    title = models.CharField(max_length=255, blank=True, default='')
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title', 'slug']
        constraints = [
            models.UniqueConstraint(fields=['gallery', 'slug'], name='gallery_show_slug_uniq'),
        ]

    def __str__(self):
        return self.title or self.slug


class ShowBuildJob(models.Model):
    STATUS_QUEUED = 'queued'
    STATUS_ANALYZING = 'analyzing'
    STATUS_PLANNING = 'planning'
    STATUS_COMPILING = 'compiling'
    STATUS_READY = 'ready'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_QUEUED, 'Queued'),
        (STATUS_ANALYZING, 'Analyzing'),
        (STATUS_PLANNING, 'Planning'),
        (STATUS_COMPILING, 'Compiling'),
        (STATUS_READY, 'Ready'),
        (STATUS_FAILED, 'Failed'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gallery = models.ForeignKey(Gallery, on_delete=models.CASCADE, related_name='show_jobs')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gallery_show_jobs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    prompt = models.TextField(blank=True, default='')
    style = models.CharField(max_length=32, blank=True, default='')
    target_seconds = models.FloatField(null=True, blank=True)
    item_ids = models.JSONField(default=list, blank=True)
    title = models.CharField(max_length=255, blank=True, default='')
    plan = models.JSONField(default=dict, blank=True)
    log = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True, default='')
    show = models.ForeignKey(
        GalleryShow, null=True, blank=True, on_delete=models.SET_NULL, related_name='build_jobs'
    )
    celery_task_id = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.status}:{self.id}'


class UserMedia(models.Model):
    """Per-user media library entry (uploads and reused /media/ files)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gallery_media')
    url = models.CharField(max_length=1000)
    thumbnail_url = models.CharField(max_length=1000, blank=True, default='')
    filename = models.CharField(max_length=500, blank=True, default='')
    media_type = models.CharField(max_length=20, choices=MEDIA_TYPE_CHOICES, default=MEDIA_IMAGE)
    sha256 = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', '-created_at']),
            models.Index(fields=['owner', 'url']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['owner', 'url'], name='gallery_usermedia_owner_url_uniq'),
        ]

    def __str__(self):
        return self.filename or self.url
