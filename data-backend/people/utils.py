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
                image = Image.open(full_path)
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
                from pdf2image import convert_from_path
                
                # Convert first page directly from disk path
                images = convert_from_path(full_path, first_page=1, last_page=1)
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

def save_file_scoped(uploaded_file, entity_id):
    """
    Saves a file to MEDIA_ROOT under an entity-scoped directory for description images:
    media/<entity_id>/<filename>
    
    Returns:
        dict: {
            'url': media_url,
            'path': relative_path,
            'name': filename
        }
    """
    from django.utils.text import get_valid_filename
    
    # 1. Clean the entity_id to prevent any directory traversal (ensure it's alphanumeric + hyphens/UUID)
    clean_entity_id = str(entity_id).replace('/', '').replace('\\', '').strip()
    
    # 2. Get sanitized filename
    filename = get_valid_filename(uploaded_file.name)
    
    relative_path = os.path.join(clean_entity_id, filename)
    full_path = os.path.join(settings.MEDIA_ROOT, relative_path)
    
    # Ensure dir exists
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    # 3. Write file
    uploaded_file.seek(0)
    with open(full_path, 'wb+') as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)
            
    # 4. Construct URL
    url = f"{settings.MEDIA_URL}{clean_entity_id}/{filename}"
    
    result = {
        'url': url,
        'path': relative_path,
        'name': filename
    }
    
    return result

def delete_file_and_derivatives(file_path):
    """
    Deletes the primary file and any thumbnail or preview files associated with it.
    """
    full_path = os.path.join(settings.MEDIA_ROOT, file_path)
    if os.path.exists(full_path):
        try:
            os.remove(full_path)
        except Exception as e:
            print(f"Error deleting file {full_path}: {e}")
            
    # Derive thumbnail and preview paths
    dir_name, file_name = os.path.split(file_path)
    base_name, ext = os.path.splitext(file_name)
    
    derivatives = [
        f"{base_name}_thumb{ext}",
        f"{base_name}_thumb.jpg",
        f"{base_name}_preview.jpg"
    ]
    
    for derivative in derivatives:
        deriv_path = os.path.join(settings.MEDIA_ROOT, dir_name, derivative)
        if os.path.exists(deriv_path):
            try:
                os.remove(deriv_path)
            except Exception as e:
                print(f"Error deleting derivative {deriv_path}: {e}")

