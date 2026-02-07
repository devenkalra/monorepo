import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
import hashlib
import os
from django.core.files.storage import default_storage


class TimeStampedModel(models.Model):
    """Abstract base class with created/modified timestamps."""
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Folder(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subfolders'
    )

    def __str__(self):
        return self.name
from django.utils import timezone
class FileCatalogManager(models.Manager):
    def ingest(self, doc, thumbnail_file=None):
        """
        Custom logic to Check, Skip, Update, or Create.
        Returns: (instance, action_string)
        """
        # 1. Lookup
        volume = doc["volume"]
        path = doc["path"]
        name = doc["name"]
        entry = self.filter(volume=volume, path=path, name=name).first()
        if "thumbnail" in doc:
            del doc["thumbnail"]

        incoming_hash = doc["hash"]
        if entry:
            # --- EXISTS ---
            if entry.hash == incoming_hash:
                # MATCH: Touch timestamp only
                entry.last_seen = timezone.now()
                entry.save(update_fields=['last_seen'])
                return entry, "verified"
            else:
                # MISMATCH: Update content
                entry.hash = incoming_hash
                entry.last_seen = timezone.now()
                if thumbnail_file:
                    entry.thumbnail = thumbnail_file
                entry.save()
                return entry, "updated"
        else:
            # --- NEW ---
            flat_doc = {}
            for key, value in doc.items():
                # If it's a list with exactly one item, take that item
                if isinstance(value, list) and len(value) == 1:
                    flat_doc[key] = value[0]
                else:
                    flat_doc[key] = value
            entry = self.model(**flat_doc,
                thumbnail=thumbnail_file,
                last_seen=timezone.now()
            )
            entry.save()
            return entry, "created"

class File(TimeStampedModel):

    objects = FileCatalogManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    folder = models.ForeignKey(
        Folder,
        on_delete=models.CASCADE,
        related_name='files',
        null=True,
        blank=True
    )

    # Common Attributes
    size = models.BigIntegerField(default=0, db_index=True)
    mime = models.CharField(max_length=100, null=True, db_index=True)
    volume = models.CharField(max_length=100, default="primary", db_index=True)
    path = models.CharField(max_length=2000, null=True, db_index=True)
    extension = models.CharField(max_length=100)
    created = models.DateTimeField(auto_now_add=True, null=True)
    modified = models.DateTimeField(auto_now=True, null=True)
    hash = models.CharField(max_length=64, null=True)
    thumbnail = models.ImageField(
        upload_to=settings.THUMBNAIL_UPLOAD_TO,
        null=True
    )
    # Flexible metadata (e.g., EXIF, ID3 tags)
    metadata = models.JSONField(default=dict, blank=True)
    last_seen = models.DateTimeField(default=timezone.now)
    meta = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            # 1. Standard single-column index with a custom name
            models.Index(fields=['hash'], name='hash_idx'),

            # 2. Composite Index (ordering matters!)
            # fast for queries filtering on 'folder_name' AND 'created_at'
            #models.Index(fields=['folder_name', 'created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['volume', 'path', 'name'],
                name='unique_file_location'
            )
        ]

    def entry_exists(self):
        pass
    def save(self, *args, **kwargs):
        # Check if there is a file and if it's a NEW upload
        # (self.thumbnail._committed is False for new uploads)
        if self.thumbnail and not self.thumbnail._committed:

            # 1. Compute the Hash (SHA-256)
            # We read in chunks to handle large files without eating RAM
            hasher = hashlib.sha256()
            for chunk in self.thumbnail.chunks():
                hasher.update(chunk)
            file_hash = hasher.hexdigest()

            # CRITICAL: Reset file pointer to the start!
            # If you don't do this, Django will save an empty file later
            # because the generator has been exhausted.
            self.thumbnail.seek(0)

            # 2. Create the Path Structure (Sharding)
            # Hash: abcdef12345...
            # Path: abc/def/abcdef12345... .jpg
            folder_1 = file_hash[:3]
            folder_2 = file_hash[3:6]

            # Preserve the original extension (e.g., .jpg, .png)
            extension = os.path.splitext(self.thumbnail.name)[1].lower()

            upload_dir = settings.THUMBNAIL_UPLOAD_TO  # e.g., 'thumbnails/'

            final_path = f"{upload_dir}{folder_1}/{folder_2}/{file_hash}{extension}"


            # 3. Deduplication Logic
            if self.thumbnail.storage.exists(final_path):
                # CASE A: Duplicate Found
                # Point the database field to the existing file path.
                self.thumbnail.name = final_path

                # MAGIC FLAG: Setting _committed = True tells Django:
                # "This file is already saved on disk, do not write it again."
                self.thumbnail._committed = True
            else:
                # CASE B: New Unique File
                # Rename the file to our hashed path.
                # Django's standard save process will write the data to this path.
                self.thumbnail.name = final_path

        # Call the real save method
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


def catalog_file_entry(volume, path, name, incoming_hash, thumbnail_file=None):
    # 1. Try to find the existing record by its "Natural Key"
    # We use .first() instead of .get() to avoid try/except blocks
    entry = File.objects.filter(
        volume=volume,
        path=path,
        name=name
    ).first()

    if entry:
        # --- PATH A: Record Exists ---

        # Check if the content is actually different
        if entry.file_hash == incoming_hash:
            # CASE 1: EXACT MATCH -> SKIP
            # We do nothing. No DB write. No 'updated_at' change.
            return entry, "skipped"

        else:
            # CASE 2: HASH MISMATCH -> UPDATE
            # The file exists but content changed (e.g., edited image)
            entry.file_hash = incoming_hash

            # If you have a new thumbnail, update it now
            if thumbnail_file:
                # Assuming your custom save() handles the deduplication
                entry.thumbnail = thumbnail_file

            entry.save()
            return entry, "updated"

    else:
        # --- PATH B: Record Missing ---

        # CASE 3: NEW ENTRY -> CREATE
        entry = File(
            volume=volume,
            path=path,
            name=name,
            file_hash=incoming_hash,
            thumbnail=thumbnail_file
        )
        entry.save()
        return entry, "created"

class Task(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        RUNNING = 'RUNNING', _('Running')
        SUCCESS = 'SUCCESS', _('Success')
        FAILURE = 'FAILURE', _('Failure')
        CANCEL = 'CANCEL', _('Cancelled')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    command = models.CharField(max_length=100)
    parameters = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    result = models.JSONField(default=dict, blank=True, help_text="Output of the task")
    error_message = models.TextField(blank=True, null=True)
    output = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.command} ({self.status})"
