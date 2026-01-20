# Software Design Document: File Cataloger & Ingestion System

## 1. System Overview
The File Cataloger is a high-throughput system designed to index file metadata from external volumes and store visual thumbnails. The system is architected for **idempotency** and **deduplication**, allowing repeated scanning of source volumes without creating redundant database records or duplicating storage assets.

## 2. Architecture & Tech Stack
* **Framework:** Django 5.x + Django REST Framework (DRF)
* **Database:** PostgreSQL (Required for composite constraints and high-performance indexing)
* **Storage Backend:** Local Filesystem or AWS S3 (via `django-storages`)
* **Client Protocol:** HTTP `multipart/form-data` (JSON metadata string + Binary image stream)

## 3. Data Model

### Entity: `File`
Represents a unique file located on a specific volume.

| Field Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `AutoIncrement` | `PK` | Internal Django ID. |
| `volume` | `CharField(100)` | Unique Key (Composite) | The logical drive/source (e.g., "NAS_01"). |
| `path` | `CharField(500)` | Unique Key (Composite) | The directory path (e.g., "/photos/2024/"). |
| `name` | `CharField(255)` | Unique Key (Composite) | The filename (e.g., "img_01.jpg"). |
| `hash` | `CharField(64)` | `db_index=True` | SHA-256 hash of the *original* file content. |
| `size` | `BigIntegerField` | `null=True` | File size in bytes. |
| `last_seen` | `DateTimeField` | Default: `now` | Timestamp of the last successful scan/verification. |
| `thumbnail` | `ImageField` | Custom Upload Logic | The visual representation (deduplicated). |

### Database Constraints
1.  **Composite Unique Constraint:**
    * **Fields:** `['volume', 'path', 'name']`
    * **Purpose:** Ensures strict uniqueness for a file's location. Prevents race conditions during parallel ingestion.
2.  **Index:**
    * **Fields:** `['hash']`
    * **Purpose:** Enables rapid lookup of duplicate files across different folders/volumes (e.g., "Find all copies of this image").

## 4. Storage Strategy (Thumbnail Deduplication)

To minimize storage costs and disk usage, the system implements a **Content-Addressable Storage (CAS)** pattern for the `thumbnail` field.

* **Hashing:** Thumbnails are named based on the SHA-256 hash of the *thumbnail image data itself* (not the original file).
* **Sharding:** Files are distributed into subdirectories to prevent filesystem performance degradation.
    * *Structure:* `thumbnails/{hash_prefix_3}/{hash_sub_3}/{full_hash}.jpg`
    * *Example:* `thumbnails/a1b/2c3/a1b2c3d4... .jpg`
* **Write Logic (Idempotency):**
    1.  Compute hash of the incoming thumbnail stream.
    2.  Check the storage backend (Disk/S3) for existence of the generated path.
    3.  **If Exists:** The specific path is saved to the DB; the physical file write is **skipped**.
    4.  **If New:** The file is written to storage.

## 5. Ingestion Logic (The "Upsert" Pattern)

The ingestion logic is encapsulated in a custom Django Manager (`FileManager`) to maintain data integrity and keep API views clean.

### Workflow
1.  **Lookup:** Attempt to find a `File` record using the natural key `(volume, path, name)`.
2.  **Decision Tree:**
    * **Case A: File Found & Hash Matches**
        * *Status:* `verified`
        * *Action:* Update `last_seen` timestamp only. (Zero content DB writes).
    * **Case B: File Found & Hash Mismatches** (File content changed)
        * *Status:* `updated`
        * *Action:* Update `hash`, `size`, `thumbnail`, and `last_seen`.
    * **Case C: File Not Found**
        * *Status:* `created`
        * *Action:* Insert new record with all data.

## 6. Implementation Reference

### A. The Model (`models.py`)

```python
import hashlib
import os
from django.db import models
from django.conf import settings
from django.utils import timezone

# 1. The Manager (Business Logic)
class FileManager(models.Manager):
    def ingest(self, volume, path, name, incoming_hash, size, thumbnail_file=None):
        entry = self.filter(volume=volume, path=path, name=name).first()

        if entry:
            if entry.hash == incoming_hash:
                # MATCH: Fast verification
                entry.last_seen = timezone.now()
                entry.save(update_fields=['last_seen'])
                return entry, "verified"
            else:
                # MISMATCH: Content update
                entry.hash = incoming_hash
                entry.size = size
                entry.last_seen = timezone.now()
                if thumbnail_file:
                    entry.thumbnail = thumbnail_file
                entry.save()
                return entry, "updated"
        else:
            # NEW: Create
            entry = self.model(
                volume=volume, path=path, name=name,
                hash=incoming_hash, size=size,
                thumbnail=thumbnail_file,
                last_seen=timezone.now()
            )
            entry.save()
            return entry, "created"

# 2. The Model (Data Structure)
class File(models.Model):
    volume = models.CharField(max_length=100)
    path = models.CharField(max_length=500)
    name = models.CharField(max_length=255)
    hash = models.CharField(max_length=64, db_index=True)
    size = models.BigIntegerField(null=True, blank=True)
    last_seen = models.DateTimeField(default=timezone.now)
    
    # Custom upload location handled by save() logic
    thumbnail = models.ImageField(upload_to=settings.THUMBNAIL_UPLOAD_TO)

    objects = FileManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['volume', 'path', 'name'], 
                name='unique_file_location'
            )
        ]

    # 3. The Deduplication Logic (Storage)
    def save(self, *args, **kwargs):
        if self.thumbnail and not self.thumbnail._committed:
            # Calculate Hash of the Thumbnail Image
            hasher = hashlib.sha256()
            for chunk in self.thumbnail.chunks():
                hasher.update(chunk)
            file_hash = hasher.hexdigest()
            self.thumbnail.seek(0) # Rewind

            # Define Path Structure
            upload_dir = settings.THUMBNAIL_UPLOAD_TO.rstrip('/') + '/'
            folder_1 = file_hash[:3]
            folder_2 = file_hash[3:6]
            ext = os.path.splitext(self.thumbnail.name)[1].lower()
            
            final_path = f"{upload_dir}{folder_1}/{folder_2}/{file_hash}{ext}"

            # Check if image already exists on disk/S3
            if self.thumbnail.storage.exists(final_path):
                # Point to existing file, skip write
                self.thumbnail.name = final_path
                self.thumbnail._committed = True
            else:
                # Will write to this new path
                self.thumbnail.name = final_path

        super().save(*args, **kwargs)