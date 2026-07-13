"""WhatsApp Assistant models - messages and media from WhatsApp Cloud API."""

import uuid
from django.db import models


class WhatsAppMessage(models.Model):
    """A message received via WhatsApp webhook."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # WhatsApp identifiers
    wa_message_id = models.CharField(max_length=255, unique=True, db_index=True)
    wa_from = models.CharField(max_length=50, db_index=True)  # sender phone number (with country code)
    wa_to = models.CharField(max_length=50, db_index=True)  # our business phone
    wa_timestamp = models.DateTimeField(null=True, blank=True)  # WhatsApp timestamp
    # Message content
    msg_type = models.CharField(max_length=50)  # text, image, audio, video, document, etc.
    text_body = models.TextField(blank=True)  # for text messages
    raw_payload = models.JSONField(default=dict, blank=True)  # full webhook payload for debugging
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wa_from']),
            models.Index(fields=['wa_timestamp']),
        ]

    def __str__(self):
        preview = (self.text_body[:50] + '...') if self.text_body and len(self.text_body) > 50 else (self.text_body or self.msg_type)
        return f"{self.wa_from} @ {self.wa_timestamp}: {preview}"


class WhatsAppMedia(models.Model):
    """Media attached to a WhatsApp message, stored in hierarchical storage."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(WhatsAppMessage, on_delete=models.CASCADE, related_name='media')
    # WhatsApp identifiers
    wa_media_id = models.CharField(max_length=255, db_index=True)
    mime_type = models.CharField(max_length=128, blank=True)
    # Hierarchical storage (same scheme as people/utils: abc/def/abcdef...xyz.ext)
    sha256 = models.CharField(max_length=64, db_index=True, blank=True)
    path = models.CharField(max_length=512)  # relative path under MEDIA_ROOT
    url = models.CharField(max_length=1024)  # MEDIA_URL + path
    thumbnail_url = models.CharField(max_length=1024, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wa_media_id']),
        ]

    def __str__(self):
        return f"Media {self.wa_media_id} ({self.mime_type})"
