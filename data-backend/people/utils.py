import hashlib
import os
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from pathlib import Path

def save_file_deduplicated(uploaded_file):
    """
    Saves a file to MEDIA_ROOT using a content-addressable scheme:
    abc/def/abcdef...xyz.ext
    
    Returns:
        dict: {
            'url': media_url,
            'sha256': sha_hash,
            'path': relative_path
        }
    """
    # 1. Calculate SHA256
    sha = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        sha.update(chunk)
    file_hash = sha.hexdigest()
    
    # 2. Determine Path
    # Structure: abc/def/FULL_HASH.ext
    prefix1 = file_hash[:3]
    prefix2 = file_hash[3:6]
    
    ext = Path(uploaded_file.name).suffix
    filename = f"{file_hash}{ext}"
    
    relative_path = os.path.join(prefix1, prefix2, filename)
    full_path = os.path.join(settings.MEDIA_ROOT, relative_path)
    
    # 3. Check Deduplication
    if not os.path.exists(full_path):
        # Ensure dirs exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        # Write file manually (or use default_storage if preferred, but manual gives us strict control over path)
        # We need to rewind the uploaded_file because we read it for hashing
        uploaded_file.seek(0)
        
        with open(full_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
    
    # 4. Construct URL
    url = f"{settings.MEDIA_URL}{relative_path}"
    
    result = {
        'url': url,
        'sha256': file_hash,
        'path': relative_path
    }

    # 5. Thumbnail Generation (if image)
    try:
        from PIL import Image
        
        # Check if it's an image by extension first (optimization)
        if ext.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
            thumb_filename = f"{file_hash}_thumb{ext}"
            thumb_relative_path = os.path.join(prefix1, prefix2, thumb_filename)
            thumb_full_path = os.path.join(settings.MEDIA_ROOT, thumb_relative_path)
            
            if not os.path.exists(thumb_full_path):
                uploaded_file.seek(0)
                image = Image.open(uploaded_file)
                image.thumbnail((256, 256)) # Max dimension 256px
                image.save(thumb_full_path)
            
            result['thumbnail_url'] = f"{settings.MEDIA_URL}{thumb_relative_path}"
    
        # Check if it's a PDF
        elif ext.lower() == '.pdf':
            thumb_filename = f"{file_hash}_thumb.jpg" # Force jpg for pdf preview
            thumb_relative_path = os.path.join(prefix1, prefix2, thumb_filename)
            thumb_full_path = os.path.join(settings.MEDIA_ROOT, thumb_relative_path)
            
            preview_filename = f"{file_hash}_preview.jpg"
            preview_relative_path = os.path.join(prefix1, prefix2, preview_filename)
            preview_full_path = os.path.join(settings.MEDIA_ROOT, preview_relative_path)
            
            if not os.path.exists(thumb_full_path) or not os.path.exists(preview_full_path):
                from pdf2image import convert_from_bytes
                
                # We need to read the file bytes
                uploaded_file.seek(0)
                file_bytes = uploaded_file.read()
                
                # Convert first page
                images = convert_from_bytes(file_bytes, first_page=1, last_page=1)
                if images:
                    original_image = images[0]
                    
                    if not os.path.exists(preview_full_path):
                        original_image.save(preview_full_path, format='JPEG')
                    
                    if not os.path.exists(thumb_full_path):
                        thumb_image = original_image.copy()
                        thumb_image.thumbnail((256, 256))
                        thumb_image.save(thumb_full_path, format='JPEG')
                    
            # Always set URLs if we assume they exist now or we skipped because they exist
            result['thumbnail_url'] = f"{settings.MEDIA_URL}{thumb_relative_path}"
            result['preview_url'] = f"{settings.MEDIA_URL}{preview_relative_path}"

    except ImportError:
        pass # Pillow or pdf2image not installed
    except Exception as e:
        print(f"Thumbnail generation failed: {e}") # Non-blocking error

    return result
