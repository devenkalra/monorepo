import os
import sys
import json
import hashlib
from pathlib import Path

# Bootstrap Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from django.conf import settings
from people.models import Entity
from PIL import Image

def verify_encrypted_file(file_path_str, original_filename):
    full_path = Path(settings.MEDIA_ROOT) / file_path_str
    
    print(f"\nChecking file: {original_filename}")
    print(f"  Storage path: {full_path}")
    
    if not full_path.exists():
        print(f"  ❌ ERROR: File does not exist on disk!")
        return False
        
    # Check 1: Check file extension
    if not full_path.suffix == '.enc':
        print(f"  ❌ ERROR: File extension on disk is '{full_path.suffix}', expected '.enc'")
        return False
    print(f"  ✓ File extension is .enc")
        
    # Read the first 256 bytes to inspect headers/magic bytes
    with open(full_path, 'rb') as f:
        header = f.read(256)
        
    # Check 2: Verify magic byte absence
    # Common headers:
    # JPEG: FF D8 FF
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    # PDF: 25 50 44 46 (%PDF)
    # GIF: 47 49 46 38 (GIF8)
    magic_headers = {
        b'\xff\xd8\xff': 'JPEG',
        b'\x89PNG\r\n\x1a\n': 'PNG',
        b'%PDF': 'PDF',
        b'GIF8': 'GIF',
        b'\x50\x4b\x03\x04': 'ZIP/OfficeDoc'
    }
    
    for magic, fmt in magic_headers.items():
        if header.startswith(magic):
            print(f"  ❌ ERROR: File contains plaintext magic bytes for {fmt}!")
            return False
            
    print(f"  ✓ No common plaintext magic headers found")
    
    # Check 3: Ensure it cannot be parsed as an image or PDF
    try:
        with Image.open(full_path) as img:
            img.verify()
        print(f"  ❌ ERROR: File was successfully parsed as an unencrypted image by PIL!")
        return False
    except Exception:
        print(f"  ✓ PIL correctly failed to parse the encrypted file as an image")
        
    # Check 4: Verify no thumbnails were generated
    # Thumbnail naming scheme: {hash}_thumb.ext
    # Encrypted files should not have a thumbnail
    file_hash = full_path.stem
    parent_dir = full_path.parent
    
    # Look for any thumbnail pattern in the parent directory
    thumbs = list(parent_dir.glob(f"{file_hash}_thumb*"))
    previews = list(parent_dir.glob(f"{file_hash}_preview*"))
    
    if thumbs:
        print(f"  ❌ ERROR: Found generated thumbnail(s): {[t.name for t in thumbs]}!")
        return False
    if previews:
        print(f"  ❌ ERROR: Found generated preview(s): {[p.name for p in previews]}!")
        return False
        
    print(f"  ✓ No plaintext thumbnails or previews exist for this file hash")
    print(f"  ✓ VERIFICATION SUCCESSFUL: File is securely stored encrypted.")
    return True

def main():
    print("==================================================")
    print("Starting Encryption Verification for Uploaded Files")
    print("==================================================")
    
    # Fetch all encrypted entities
    encrypted_entities = Entity.objects.filter(is_encrypted=True)
    print(f"Found {encrypted_entities.count()} encrypted entities in database.\n")
    
    total_files = 0
    verified_files = 0
    failed_files = 0
    
    for entity in encrypted_entities:
        print(f"\nEntity ID: {entity.id} ({entity.type})")
        
        # We need to decrypt the metadata or get photos/attachments
        # Since is_encrypted=True, the database columns photos and attachments
        # should be empty lists (finalPayload clears them and puts them in encrypted_data)
        # Let's verify that database columns photos and attachments are indeed empty!
        db_photos = entity.photos or []
        db_attachments = entity.attachments or []
        
        if db_photos or db_attachments:
            print(f"  ❌ ERROR: Database plaintext columns contain photos/attachments for encrypted entity!")
            print(f"    Plaintext Photos in DB: {db_photos}")
            print(f"    Plaintext Attachments in DB: {db_attachments}")
            failed_files += len(db_photos) + len(db_attachments)
            continue
        else:
            print(f"  ✓ Database columns 'photos' and 'attachments' are correctly empty (zero data leak)")

        # Now, since the actual file data is stored inside the 'encrypted_data' JSON block,
        # let's find any files that are currently stored on disk ending in '.enc' 
        # or verify existing uploaded files in the media folder.
        # Let's list all .enc files in the media directory and verify them.
        
    print("\nScanning media directory for all encrypted (.enc) files on disk...")
    media_root = Path(settings.MEDIA_ROOT)
    enc_files = list(media_root.glob("**/*.enc"))
    
    print(f"Found {len(enc_files)} '.enc' files stored in media root.")
    
    for enc_file in enc_files:
        relative_path = enc_file.relative_to(media_root)
        total_files += 1
        if verify_encrypted_file(str(relative_path), enc_file.name):
            verified_files += 1
        else:
            failed_files += 1
            
    print("\n==================================================")
    print("Verification Summary:")
    print(f"  Total encrypted files found: {total_files}")
    print(f"  Successfully verified:        {verified_files}")
    print(f"  Failures/Leaks detected:      {failed_files}")
    print("==================================================")
    
    if failed_files > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
