#!/usr/bin/env python3
"""index_media.py - Index files into a SQLite database by logical volume.

Recursively scans a registered volume mount, extracts metadata by file type,
generates thumbnails, and stores portable relative paths in the database.

Supported types: images, videos, audio, documents (PDF/txt/Office), and .eml email.
"""

import argparse
import email
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import textwrap
from datetime import datetime
from email import policy
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from media_utils import (
    METADATA_TABLES,
    calculate_file_hash,
    catalog_mime_type,
    classify_file_type,
    create_database_schema,
    get_indexable_file_type,
    get_mime_type,
    get_volume,
    has_rich_metadata,
    insert_thumbnail,
    normalize_volume_name,
    prepare_image_for_thumbnail,
    thumbnail_jpeg_dimensions,
    to_storage_relpath,
)

# Try to import PIL for image processing
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: PIL/Pillow not available. Thumbnail generation will be limited.", file=sys.stderr)


# ==================== EXIF Processing ====================

def get_exif_data(filepath: str) -> Optional[Dict]:
    """Extract EXIF data from an image file using exiftool."""
    try:
        cmd = ["exiftool", "-json", "-G", filepath]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]
        return None
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error extracting EXIF from {filepath}: {e}", file=sys.stderr)
        return None


def normalize_exif_data(exif: Dict) -> Dict:
    """Extract and normalize relevant fields from raw EXIF data."""
    normalized = {}
    
    # Dimensions
    normalized['width'] = (exif.get('EXIF:ImageWidth') or 
                          exif.get('File:ImageWidth') or 
                          exif.get('Composite:ImageSize', '').split('x')[0] if 'x' in str(exif.get('Composite:ImageSize', '')) else None)
    normalized['height'] = (exif.get('EXIF:ImageHeight') or 
                           exif.get('File:ImageHeight') or 
                           exif.get('Composite:ImageSize', '').split('x')[1] if 'x' in str(exif.get('Composite:ImageSize', '')) else None)
    
    # Date taken - try multiple fields
    normalized['date_taken'] = (exif.get('EXIF:DateTimeOriginal') or 
                               exif.get('EXIF:CreateDate') or 
                               exif.get('XMP:DateCreated') or 
                               exif.get('IPTC:DateCreated'))
    
    # Camera settings
    normalized['exposure_time'] = exif.get('EXIF:ExposureTime')
    normalized['focal_length'] = exif.get('EXIF:FocalLength')
    normalized['focal_length_35mm'] = exif.get('EXIF:FocalLengthIn35mmFormat')
    normalized['f_number'] = exif.get('EXIF:FNumber')
    normalized['iso'] = exif.get('EXIF:ISO')
    
    # Camera and lens
    normalized['camera_make'] = exif.get('EXIF:Make')
    normalized['camera_model'] = exif.get('EXIF:Model')
    normalized['lens_model'] = (exif.get('EXIF:LensModel') or 
                               exif.get('XMP:LensModel') or 
                               exif.get('EXIF:LensInfo'))
    
    # GPS data
    gps_lat = exif.get('EXIF:GPSLatitude') or exif.get('Composite:GPSLatitude')
    gps_lon = exif.get('EXIF:GPSLongitude') or exif.get('Composite:GPSLongitude')
    gps_alt = exif.get('EXIF:GPSAltitude') or exif.get('Composite:GPSAltitude')
    
    if gps_lat:
        normalized['latitude'] = _parse_gps_coordinate(gps_lat)
    if gps_lon:
        normalized['longitude'] = _parse_gps_coordinate(gps_lon)
    if gps_alt:
        normalized['altitude'] = _parse_altitude(gps_alt)
    
    # Location information
    normalized['city'] = (exif.get('XMP-photoshop:City') or 
                         exif.get('IPTC:City') or 
                         exif.get('XMP:City'))
    normalized['state'] = (exif.get('XMP-photoshop:State') or 
                          exif.get('IPTC:Province-State') or 
                          exif.get('XMP:State'))
    normalized['country'] = (exif.get('XMP-photoshop:Country') or 
                            exif.get('IPTC:Country-PrimaryLocationName') or 
                            exif.get('XMP:Country'))
    normalized['country_code'] = (exif.get('XMP-iptcExt:LocationShownCountryCode') or 
                                 exif.get('IPTC:Country-PrimaryLocationCode'))
    normalized['coverage'] = (exif.get('XMP-dc:Coverage') or 
                             exif.get('XMP:Coverage') or 
                             exif.get('Coverage'))
    
    # Caption and keywords
    normalized['caption'] = (exif.get('IPTC:Caption-Abstract') or 
                            exif.get('XMP:Description') or 
                            exif.get('EXIF:ImageDescription'))
    
    keywords = (exif.get('XMP-dc:Subject') or 
               exif.get('IPTC:Keywords') or 
               exif.get('XMP:Subject'))
    if keywords:
        if isinstance(keywords, list):
            # Convert all items to strings before joining
            normalized['keywords'] = ', '.join(str(k) for k in keywords)
        else:
            normalized['keywords'] = str(keywords)
    
    return normalized


def _parse_gps_coordinate(coord_str) -> Optional[float]:
    """Parse GPS coordinate from various formats to decimal degrees."""
    if coord_str is None:
        return None
    
    # If already a number
    if isinstance(coord_str, (int, float)):
        return float(coord_str)
    
    coord_str = str(coord_str)
    
    # Handle formats like "28 deg 36' 50.04\" N" or "-97.3308"
    try:
        # Try direct float conversion first
        return float(coord_str)
    except ValueError:
        pass
    
    # Parse DMS format
    try:
        # Remove direction letter
        direction = 1
        if 'S' in coord_str or 'W' in coord_str:
            direction = -1
        
        # Extract numbers
        parts = coord_str.replace('deg', '').replace("'", '').replace('"', '').replace('N', '').replace('S', '').replace('E', '').replace('W', '').strip().split()
        if len(parts) >= 3:
            degrees = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])
            return direction * (degrees + minutes/60 + seconds/3600)
    except Exception:
        pass
    
    return None


def _parse_altitude(alt_str) -> Optional[float]:
    """Parse altitude from string like '216 m' to float."""
    if alt_str is None:
        return None
    
    if isinstance(alt_str, (int, float)):
        return float(alt_str)
    
    try:
        # Remove units and convert
        alt_str = str(alt_str).replace('m', '').replace('meters', '').strip()
        return float(alt_str)
    except ValueError:
        return None


# ==================== Video Processing ====================

def get_video_metadata(filepath: str) -> Optional[Dict]:
    """Extract metadata from a video file using ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        metadata = {}
        
        # Find video and audio streams
        video_stream = None
        audio_stream = None
        
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video' and video_stream is None:
                video_stream = stream
            elif stream.get('codec_type') == 'audio' and audio_stream is None:
                audio_stream = stream
        
        # Extract video metadata
        if video_stream:
            metadata['width'] = video_stream.get('width')
            metadata['height'] = video_stream.get('height')
            metadata['video_codec'] = video_stream.get('codec_name')
            
            # Parse frame rate
            fps_str = video_stream.get('r_frame_rate', '0/1')
            try:
                num, den = map(int, fps_str.split('/'))
                if den != 0:
                    metadata['frame_rate'] = num / den
            except Exception:
                pass
        
        # Extract audio metadata
        if audio_stream:
            metadata['audio_channels'] = audio_stream.get('channels')
            bit_rate = audio_stream.get('bit_rate')
            if bit_rate:
                try:
                    metadata['audio_bit_rate_kbps'] = float(bit_rate) / 1000
                except ValueError:
                    pass
        
        # Extract duration
        format_data = data.get('format', {})
        duration = format_data.get('duration')
        if duration:
            try:
                metadata['duration_seconds'] = float(duration)
            except ValueError:
                pass
        
        return metadata
        
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error extracting video metadata from {filepath}: {e}", file=sys.stderr)
        return None


def get_audio_metadata(filepath: str) -> Optional[Dict]:
    """Extract metadata from an audio file using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-show_format", filepath,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)

        metadata = {}
        audio_stream = None
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'audio' and audio_stream is None:
                audio_stream = stream
                break

        if audio_stream:
            metadata['audio_codec'] = audio_stream.get('codec_name')
            metadata['channels'] = audio_stream.get('channels')
            sample_rate = audio_stream.get('sample_rate')
            if sample_rate:
                try:
                    metadata['sample_rate'] = int(sample_rate)
                except ValueError:
                    pass
            bit_rate = audio_stream.get('bit_rate')
            if bit_rate:
                try:
                    metadata['bit_rate_kbps'] = float(bit_rate) / 1000
                except ValueError:
                    pass

        format_data = data.get('format', {})
        duration = format_data.get('duration')
        if duration:
            try:
                metadata['duration_seconds'] = float(duration)
            except ValueError:
                pass

        tags = format_data.get('tags') or {}
        metadata['title'] = tags.get('title') or tags.get('TITLE')
        metadata['artist'] = tags.get('artist') or tags.get('ARTIST')
        metadata['album'] = tags.get('album') or tags.get('ALBUM')

        return metadata if metadata else None
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error extracting audio metadata from {filepath}: {e}", file=sys.stderr)
        return None


def get_document_metadata(filepath: str, extension: str) -> Optional[Dict]:
    """Extract metadata from PDF, text, and Office documents."""
    metadata = {}
    ext = extension.lower()

    if ext == '.pdf':
        try:
            cmd = ["pdfinfo", filepath]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
            for line in result.stdout.splitlines():
                if ':' not in line:
                    continue
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                if key == 'pages':
                    try:
                        metadata['page_count'] = int(value)
                    except ValueError:
                        pass
                elif key == 'title':
                    metadata['title'] = value
                elif key == 'author':
                    metadata['author'] = value
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass

    if ext in {'.txt', '.md'} or (get_mime_type(filepath).startswith('text/') and ext in {'.txt', '.md'}):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                metadata['text_preview'] = f.read(8000)
        except OSError as e:
            print(f"Error reading text file {filepath}: {e}", file=sys.stderr)

    if ext in {'.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp', '.rtf'}:
        try:
            cmd = ["exiftool", "-json", "-PageCount", "-Title", "-Author", filepath]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)
            if data:
                item = data[0]
                page_count = item.get('PageCount')
                if page_count is not None:
                    try:
                        metadata['page_count'] = int(page_count)
                    except (TypeError, ValueError):
                        pass
                if item.get('Title'):
                    metadata['title'] = str(item['Title'])
                if item.get('Author'):
                    metadata['author'] = str(item['Author'])
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError,
                subprocess.TimeoutExpired):
            pass

    return metadata if metadata else {}


def get_email_metadata(filepath: str) -> Optional[Dict]:
    """Extract metadata from an .eml file (headers only, no body)."""
    try:
        with open(filepath, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)

        attachment_count = 0
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_disposition() == 'attachment':
                    attachment_count += 1

        recipients = msg.get('To', '') or ''
        return {
            'message_id': msg.get('Message-ID', ''),
            'subject': msg.get('Subject', ''),
            'sender': msg.get('From', ''),
            'recipients': recipients,
            'cc': msg.get('Cc', ''),
            'email_date': msg.get('Date', ''),
            'has_attachments': attachment_count > 0,
            'attachment_count': attachment_count,
        }
    except Exception as e:
        print(f"Error parsing email {filepath}: {e}", file=sys.stderr)
        return None


# ==================== Thumbnail Generation ====================

def generate_thumbnail(filepath: str, mime_type: str, extension: str = '',
                       file_type: str = '', max_size: Tuple[int, int] = (200, 200)) -> Optional[bytes]:
    """Generate a thumbnail for a supported file."""
    ext = extension.lower()

    raw_extensions = [
        '.raw', '.cr2', '.cr3', '.nef', '.arw', '.dng', '.orf', '.rw2',
        '.pef', '.srw', '.raf', '.3fr', '.fff', '.iiq', '.rwl', '.nrw',
        '.mrw', '.erf', '.kdc', '.dcr', '.mos', '.ptx', '.r3d',
    ]

    if ext in raw_extensions:
        return _generate_raw_thumbnail(filepath, max_size)
    if file_type == 'image' or mime_type.startswith('image/'):
        return _generate_image_thumbnail(filepath, max_size)
    if file_type == 'video' or mime_type.startswith('video/'):
        return _generate_video_thumbnail(filepath, max_size)
    if file_type == 'document':
        return _generate_document_thumbnail(filepath, ext, max_size)
    if file_type == 'email':
        meta = get_email_metadata(filepath) or {}
        label = meta.get('subject') or os.path.basename(filepath)
        sender = meta.get('sender') or ''
        return _generate_text_thumbnail(f"{label}\n\n{sender}", max_size)
    if file_type == 'audio':
        return _generate_text_thumbnail(os.path.basename(filepath), max_size)

    return None


def _generate_text_thumbnail(text: str, max_size: Tuple[int, int]) -> Optional[bytes]:
    """Render text into a JPEG thumbnail."""
    if not PIL_AVAILABLE:
        return None

    try:
        from PIL import ImageDraw, ImageFont

        img = Image.new('RGB', max_size, color=(248, 248, 248))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        wrapped = textwrap.fill(text or 'Document', width=28)
        draw.multiline_text((10, 10), wrapped[:500], fill=(20, 20, 20), font=font, spacing=4)

        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()
    except Exception as e:
        print(f"Error generating text thumbnail: {e}", file=sys.stderr)
        return None


def _generate_document_thumbnail(filepath: str, extension: str,
                                 max_size: Tuple[int, int]) -> Optional[bytes]:
    """Generate a first-page thumbnail for documents."""
    ext = extension.lower()

    if ext == '.pdf':
        thumbnail = _generate_pdf_thumbnail(filepath, max_size)
        if thumbnail:
            return thumbnail

    if ext in {'.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp', '.rtf'}:
        thumbnail = _generate_office_thumbnail(filepath, max_size)
        if thumbnail:
            return thumbnail

    if ext in {'.txt', '.md'}:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                return _generate_text_thumbnail(f.read(1500), max_size)
        except OSError:
            pass

    return _generate_text_thumbnail(os.path.basename(filepath), max_size)


def _generate_pdf_thumbnail(filepath: str, max_size: Tuple[int, int]) -> Optional[bytes]:
    """Extract the first page of a PDF as a thumbnail."""
    if not PIL_AVAILABLE:
        return None

    import tempfile

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        for tool, cmd in [
            ('pdftoppm', ['pdftoppm', '-f', '1', '-l', '1', '-png', '-singlefile', filepath, tmp_path[:-4]]),
            ('mutool', ['mutool', 'draw', '-o', tmp_path, filepath, '1']),
        ]:
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                output_path = tmp_path if tool == 'mutool' else tmp_path[:-4] + '.png'
                if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    with Image.open(output_path) as img:
                        if img.mode not in ('RGB', 'RGBA'):
                            img = img.convert('RGB')
                        img.thumbnail(max_size, Image.Resampling.LANCZOS)
                        buffer = io.BytesIO()
                        img.save(buffer, format='JPEG', quality=85)
                        return buffer.getvalue()
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
    finally:
        for path in (tmp_path, tmp_path[:-4] + '.png'):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    return None


def _generate_office_thumbnail(filepath: str, max_size: Tuple[int, int]) -> Optional[bytes]:
    """Convert an Office document to PDF and render the first page."""
    import tempfile
    import shutil

    if not shutil.which('soffice'):
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            subprocess.run(
                ['soffice', '--headless', '--convert-to', 'pdf', '--outdir', tmpdir, filepath],
                capture_output=True, check=True, timeout=120,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return None

        pdf_name = os.path.splitext(os.path.basename(filepath))[0] + '.pdf'
        pdf_path = os.path.join(tmpdir, pdf_name)
        if os.path.exists(pdf_path):
            return _generate_pdf_thumbnail(pdf_path, max_size)

    return None


def _generate_raw_thumbnail(filepath: str, max_size: Tuple[int, int]) -> Optional[bytes]:
    """Generate thumbnail from a RAW file using exiftool to extract embedded preview."""
    if not PIL_AVAILABLE:
        return None
    
    try:
        import tempfile
        import io
        
        # Extract embedded preview/thumbnail using exiftool
        # Try PreviewImage first, then JpgFromRaw, then ThumbnailImage
        for tag in ['PreviewImage', 'JpgFromRaw', 'ThumbnailImage']:
            try:
                cmd = ["exiftool", "-b", f"-{tag}", filepath]
                result = subprocess.run(cmd, capture_output=True, check=True, timeout=30)
                
                if result.stdout and len(result.stdout) > 100:  # Valid image data
                    with Image.open(io.BytesIO(result.stdout)) as img:
                        img = prepare_image_for_thumbnail(img)
                        img.thumbnail(max_size, Image.Resampling.LANCZOS)
                        buffer = io.BytesIO()
                        img.save(buffer, format='JPEG', quality=85)
                        return buffer.getvalue()
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                continue  # Try next tag
        
        # If no embedded preview found, try to open with PIL (some RAW formats supported)
        return _generate_image_thumbnail(filepath, max_size)
        
    except Exception as e:
        print(f"Error generating RAW thumbnail for {filepath}: {e}", file=sys.stderr)
        return None


def _generate_image_thumbnail(filepath: str, max_size: Tuple[int, int]) -> Optional[bytes]:
    """Generate thumbnail from an image file."""
    if not PIL_AVAILABLE:
        return None
    
    try:
        with Image.open(filepath) as img:
            img = prepare_image_for_thumbnail(img)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            return buffer.getvalue()
    except Exception as e:
        print(f"Error generating image thumbnail for {filepath}: {e}", file=sys.stderr)
        return None


def _generate_video_thumbnail(filepath: str, max_size: Tuple[int, int]) -> Optional[bytes]:
    """Generate thumbnail from a video file using ffmpeg.
    
    Tries multiple strategies to extract a frame:
    1. Fast seek to 1 second (after input)
    2. If that fails, try first frame (0 seconds)
    3. If that fails, try without seeking
    """
    if not PIL_AVAILABLE:
        return None
    
    import tempfile
    import io
    
    # Try different seek strategies
    seek_strategies = [
        ("1", 10),    # 1 second, 10 second timeout
        ("0", 10),    # First frame, 10 second timeout
        (None, 15),   # No seeking, 15 second timeout
    ]
    
    for seek_time, timeout in seek_strategies:
        try:
            # Create temp file for extracted frame
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp_path = tmp.name
            
            # Build ffmpeg command
            # Put -ss AFTER -i for faster (but less accurate) seeking
            cmd = ["ffmpeg", "-v", "quiet", "-i", filepath]
            
            if seek_time:
                cmd.extend(["-ss", seek_time])
            
            cmd.extend([
                "-vframes", "1",      # Extract 1 frame
                "-q:v", "2",          # High quality
                "-f", "image2",       # Force image output
                "-y",                 # Overwrite output
                tmp_path
            ])
            
            # Try to extract frame with timeout
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
            
            # Check if output file was created and has content
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                # Load and resize the extracted frame
                with Image.open(tmp_path) as img:
                    # Convert to RGB if necessary
                    if img.mode not in ('RGB', 'RGBA'):
                        img = img.convert('RGB')
                    
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)
                    
                    buffer = io.BytesIO()
                    img.save(buffer, format='JPEG', quality=85)
                    thumbnail_data = buffer.getvalue()
                
                # Clean up temp file
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                
                return thumbnail_data
            else:
                # Clean up failed temp file
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                # Try next strategy
                continue
                
        except subprocess.TimeoutExpired:
            # Clean up temp file
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            # Try next strategy
            continue
        except Exception as e:
            # Clean up temp file
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            # Try next strategy
            continue
    
    # All strategies failed
    print(f"Warning: Could not generate video thumbnail for {filepath} (all strategies failed)", file=sys.stderr)
    return None


# ==================== File Processing ====================

def should_skip_path(path: str, skip_patterns: List[str], literal: bool = False) -> bool:
    """Check if a path should be skipped based on patterns.
    
    Args:
        path: Path to check
        skip_patterns: List of patterns to match against
        literal: If True, treat patterns as literal strings; if False, treat as regex
    
    Returns:
        True if path matches any skip pattern, False otherwise
    """
    path_str = str(path)
    for pattern in skip_patterns:
        try:
            if literal:
                # Escape special regex characters for literal matching
                escaped_pattern = re.escape(pattern)
                if re.search(escaped_pattern, path_str):
                    return True
            else:
                if re.search(pattern, path_str):
                    return True
        except re.error as e:
            print(f"Warning: Invalid regex pattern '{pattern}': {e}", file=sys.stderr)
            # Fall back to substring match for invalid regex
            if pattern in path_str:
                return True
    return False


def matches_include_pattern(path: str, include_patterns: List[str], literal: bool = False) -> bool:
    """Check if a path matches any of the include patterns.
    
    If no include patterns are specified, all paths match.
    
    Args:
        path: Path to check
        include_patterns: List of patterns to match against
        literal: If True, treat patterns as literal strings; if False, treat as regex
    
    Returns:
        True if path matches any include pattern (or no patterns specified), False otherwise
    """
    if not include_patterns:
        return True
    
    path_str = str(path)
    for pattern in include_patterns:
        try:
            if literal:
                # Escape special regex characters for literal matching
                escaped_pattern = re.escape(pattern)
                if re.search(escaped_pattern, path_str):
                    return True
            else:
                if re.search(pattern, path_str):
                    return True
        except re.error as e:
            print(f"Warning: Invalid regex pattern '{pattern}': {e}", file=sys.stderr)
            # Fall back to substring match for invalid regex
            if pattern in path_str:
                return True
    return False


def calculate_depth(base_path: str, current_path: str) -> int:
    """Calculate the depth of current_path relative to base_path."""
    try:
        rel_path = os.path.relpath(current_path, base_path)
        if rel_path == '.':
            return 0
        # Count the number of directory separators
        return rel_path.count(os.sep) + 1
    except ValueError:
        # Paths are on different drives (Windows)
        return 0


def record_skipped_file(filepath: str, skip_reason: str, volume: str,
                        mount_path: str, run_timestamp: str, conn: sqlite3.Connection):
    """Record a skipped file in the database."""
    try:
        cursor = conn.cursor()

        file_size = None
        if os.path.exists(filepath):
            try:
                file_size = os.path.getsize(filepath)
            except Exception:
                pass

        relpath = to_storage_relpath(filepath, mount_path)
        cursor.execute("""
            INSERT INTO skipped_files (run_timestamp, relpath, skip_reason, volume, file_size, recorded_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            run_timestamp,
            relpath,
            skip_reason,
            normalize_volume_name(volume),
            file_size,
            datetime.now().isoformat(),
        ))
    except Exception as e:
        print(f"Warning: Could not record skipped file {filepath}: {e}", file=sys.stderr)


def get_file_info(filepath: str, volume: str, mount_path: str) -> Dict:
    """Get basic file information with portable relative path."""
    stat = os.stat(filepath)

    info = {
        'volume': normalize_volume_name(volume),
        'relpath': to_storage_relpath(filepath, mount_path),
        'name': os.path.basename(filepath),
        'modified_date': datetime.fromtimestamp(stat.st_mtime).isoformat(),
        'size': stat.st_size,
        'extension': os.path.splitext(filepath)[1].lower(),
    }

    try:
        info['created_date'] = datetime.fromtimestamp(stat.st_ctime).isoformat()
    except Exception:
        info['created_date'] = info['modified_date']

    info['mime_type'] = get_mime_type(filepath)
    return info


def _criterion_column(criterion: str) -> Optional[str]:
    """Map CLI existence-check criteria to database columns."""
    if criterion in ('relpath', 'fullpath'):
        return 'relpath'
    if criterion in ('volume', 'size', 'modified_date', 'hash'):
        return 'file_hash' if criterion == 'hash' else criterion
    return None


def check_file_exists(file_info: Dict, check_criteria: List[str], conn: sqlite3.Connection) -> bool:
    """Check if a file already exists in database based on specified criteria."""
    cursor = conn.cursor()

    conditions = []
    params = []

    for criterion in check_criteria:
        column = _criterion_column(criterion)
        if not column:
            continue
        if column == 'file_hash':
            if file_info.get('file_hash'):
                conditions.append("file_hash = ?")
                params.append(file_info['file_hash'])
        else:
            value = file_info.get(column)
            if value is not None:
                conditions.append(f"{column} = ?")
                params.append(value)

    if not conditions:
        conditions = ["relpath = ?", "volume = ?"]
        params = [file_info.get('relpath'), file_info.get('volume')]

    where_clause = " AND ".join(conditions)
    query = f"SELECT id FROM files WHERE {where_clause}"
    cursor.execute(query, params)
    return cursor.fetchone() is not None


def _delete_metadata_for_file(cursor: sqlite3.Cursor, file_id: int):
    """Remove all type-specific metadata rows before re-indexing."""
    for table in METADATA_TABLES:
        cursor.execute(f"DELETE FROM {table} WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM thumbnails WHERE file_id = ?", (file_id,))


def _file_type_label(file_type: str) -> str:
    return {
        'image': 'Image',
        'video': 'Video',
        'audio': 'Audio',
        'document': 'Document',
        'email': 'Email',
        'unknown': 'Unknown',
    }.get(file_type, file_type.title())


def process_file(filepath: str, volume: str, mount_path: str, run_timestamp: str,
                 check_existing: List[str], verbose: int, dry_run: bool,
                 conn: sqlite3.Connection) -> Tuple[bool, Optional[str], bool]:
    """Process a single media file and store in database.
    
    Args:
        filepath: Path to file
        volume: Volume tag
        run_timestamp: Run timestamp
        check_existing: List of criteria for checking if file exists
        verbose: Verbosity level (0=quiet, 1=file+outcome, 2=more details, 3=full data)
        dry_run: If True, only show what would be done without actually doing it
        conn: Database connection
    
    Returns:
        Tuple of (success, skip_reason, was_update)
        - success: True if file was processed, False if skipped
        - skip_reason: Reason for skipping (None if processed)
        - was_update: True if existing record was updated, False if new record
    """
    cursor = conn.cursor()

    try:
        file_info = get_file_info(filepath, volume, mount_path)

        if 'hash' in check_existing:
            file_info['file_hash'] = calculate_file_hash(filepath)

        if check_file_exists(file_info, check_existing, conn):
            criteria_str = '+'.join(check_existing)
            if verbose >= 1 or dry_run:
                print(f"Skipping (already indexed by {criteria_str}): {filepath}")
            return False, f"already_indexed (by {criteria_str})", False

        cursor.execute(
            "SELECT id FROM files WHERE relpath = ? AND volume = ?",
            (file_info['relpath'], file_info['volume']),
        )
        existing = cursor.fetchone()
        existing_file_id = existing[0] if existing else None

        if existing_file_id:
            if dry_run or verbose >= 1:
                action = "[DRY RUN] Would update" if dry_run else "Updating"
                print(f"{action} existing record: {filepath}")
        elif dry_run or verbose >= 1:
            action = "[DRY RUN] Would process" if dry_run else "Processing"
            print(f"{action}: {filepath}")

        mime_type = file_info['mime_type']
        extension = file_info['extension']
        file_type = classify_file_type(mime_type, extension)
        stored_mime_type = catalog_mime_type(mime_type, extension, filepath)
        file_info['mime_type'] = stored_mime_type

        if dry_run:
            if verbose >= 2:
                print(f"  Type: {_file_type_label(file_type)} ({stored_mime_type})")
                print(f"  Relpath: {file_info['relpath']}")
                print(f"  Size: {file_info['size']} bytes")
            if verbose >= 3 and has_rich_metadata(file_type):
                print("  [DRY RUN] Would extract and store metadata")
            return True, None, existing_file_id is not None

        if 'file_hash' not in file_info:
            file_info['file_hash'] = calculate_file_hash(filepath)
        file_info['indexed_date'] = datetime.now().isoformat()

        if existing_file_id:
            cursor.execute("""
                UPDATE files
                SET name = ?, created_date = ?, modified_date = ?,
                    size = ?, mime_type = ?, extension = ?, file_hash = ?, indexed_date = ?
                WHERE id = ?
            """, (
                file_info['name'],
                file_info['created_date'],
                file_info['modified_date'],
                file_info['size'],
                file_info['mime_type'],
                file_info['extension'],
                file_info['file_hash'],
                file_info['indexed_date'],
                existing_file_id,
            ))
            file_id = existing_file_id
            _delete_metadata_for_file(cursor, file_id)
        else:
            cursor.execute("""
                INSERT INTO files (volume, relpath, name, created_date, modified_date,
                                   size, mime_type, extension, file_hash, indexed_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_info['volume'],
                file_info['relpath'],
                file_info['name'],
                file_info['created_date'],
                file_info['modified_date'],
                file_info['size'],
                file_info['mime_type'],
                file_info['extension'],
                file_info['file_hash'],
                file_info['indexed_date'],
            ))
            file_id = cursor.lastrowid

        metadata = None
        if file_type == 'image':
            metadata = process_image(filepath, file_id, conn)
        elif file_type == 'video':
            metadata = process_video(filepath, file_id, conn)
        elif file_type == 'audio':
            metadata = process_audio(filepath, file_id, conn)
        elif file_type == 'document':
            metadata = process_document(filepath, file_id, conn, extension)
        elif file_type == 'email':
            metadata = process_email(filepath, file_id, conn)

        if verbose >= 2:
            print(f"  Type: {_file_type_label(file_type)} ({stored_mime_type})")
            print(f"  Relpath: {file_info['relpath']}")
            print(f"  Size: {file_info['size']} bytes")
            print(f"  Hash: {file_info['file_hash'][:16]}...")
        if verbose >= 3 and metadata:
            print(f"  Metadata:")
            for key, value in metadata.items():
                if value is not None and value != '':
                    print(f"    {key}: {value}")

        if has_rich_metadata(file_type):
            thumbnail_data = generate_thumbnail(filepath, mime_type, extension, file_type)
            if thumbnail_data:
                thumb_w, thumb_h = thumbnail_jpeg_dimensions(thumbnail_data)
                if not thumb_w:
                    thumb_w, thumb_h = 200, 200
                insert_thumbnail(conn, file_id, thumbnail_data, thumb_w, thumb_h)

        conn.commit()
        return True, None, existing_file_id is not None

    except Exception as e:
        error_msg = f"Error processing file {filepath}: {e}"
        print(error_msg, file=sys.stderr)
        conn.rollback()
        return False, f"processing_error: {str(e)[:100]}", False


def process_image(filepath: str, file_id: int, conn: sqlite3.Connection) -> Optional[Dict]:
    """Process image file and extract metadata.
    
    Returns:
        Dictionary of normalized metadata, or None if no EXIF data
    """
    cursor = conn.cursor()
    
    # Get EXIF data
    exif_data = get_exif_data(filepath)
    
    if exif_data:
        # Store raw EXIF as JSON
        raw_exif_json = json.dumps(exif_data)
        
        # Normalize EXIF data
        normalized = normalize_exif_data(exif_data)
        
        # Insert image metadata
        cursor.execute("""
            INSERT INTO image_metadata (
                file_id, raw_exif, width, height, date_taken, exposure_time,
                focal_length, focal_length_35mm, f_number, camera_make, camera_model,
                lens_model, iso, latitude, longitude, altitude, city, state, country,
                country_code, coverage, caption, keywords
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id,
            raw_exif_json,
            normalized.get('width'),
            normalized.get('height'),
            normalized.get('date_taken'),
            normalized.get('exposure_time'),
            normalized.get('focal_length'),
            normalized.get('focal_length_35mm'),
            normalized.get('f_number'),
            normalized.get('camera_make'),
            normalized.get('camera_model'),
            normalized.get('lens_model'),
            normalized.get('iso'),
            normalized.get('latitude'),
            normalized.get('longitude'),
            normalized.get('altitude'),
            normalized.get('city'),
            normalized.get('state'),
            normalized.get('country'),
            normalized.get('country_code'),
            normalized.get('coverage'),
            normalized.get('caption'),
            normalized.get('keywords')
        ))
        
        return normalized
    
    return None


def process_video(filepath: str, file_id: int, conn: sqlite3.Connection) -> Optional[Dict]:
    """Process video file and extract metadata.
    
    Returns:
        Dictionary of video metadata, or None if extraction failed
    """
    cursor = conn.cursor()
    
    # Get video metadata
    video_data = get_video_metadata(filepath)
    
    if video_data:
        # Insert video metadata
        cursor.execute("""
            INSERT INTO video_metadata (
                file_id, width, height, frame_rate, video_codec,
                audio_channels, audio_bit_rate_kbps, duration_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id,
            video_data.get('width'),
            video_data.get('height'),
            video_data.get('frame_rate'),
            video_data.get('video_codec'),
            video_data.get('audio_channels'),
            video_data.get('audio_bit_rate_kbps'),
            video_data.get('duration_seconds')
        ))
        
        return video_data
    
    return None


def process_audio(filepath: str, file_id: int, conn: sqlite3.Connection) -> Optional[Dict]:
    """Process audio file and extract metadata."""
    cursor = conn.cursor()
    audio_data = get_audio_metadata(filepath)

    if audio_data:
        cursor.execute("""
            INSERT INTO audio_metadata (
                file_id, duration_seconds, audio_codec, bit_rate_kbps,
                sample_rate, channels, title, artist, album
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id,
            audio_data.get('duration_seconds'),
            audio_data.get('audio_codec'),
            audio_data.get('bit_rate_kbps'),
            audio_data.get('sample_rate'),
            audio_data.get('channels'),
            audio_data.get('title'),
            audio_data.get('artist'),
            audio_data.get('album'),
        ))
        return audio_data

    return None


def process_document(filepath: str, file_id: int, conn: sqlite3.Connection,
                     extension: str) -> Optional[Dict]:
    """Process document file and extract metadata."""
    cursor = conn.cursor()
    document_data = get_document_metadata(filepath, extension)

    if document_data is not None:
        cursor.execute("""
            INSERT INTO document_metadata (
                file_id, page_count, title, author, text_preview
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            file_id,
            document_data.get('page_count'),
            document_data.get('title'),
            document_data.get('author'),
            document_data.get('text_preview'),
        ))
        return document_data

    return None


def process_email(filepath: str, file_id: int, conn: sqlite3.Connection) -> Optional[Dict]:
    """Process email file and extract metadata."""
    cursor = conn.cursor()
    email_data = get_email_metadata(filepath)

    if email_data:
        cursor.execute("""
            INSERT INTO email_metadata (
                file_id, message_id, subject, sender, recipients, cc,
                email_date, has_attachments, attachment_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id,
            email_data.get('message_id'),
            email_data.get('subject'),
            email_data.get('sender'),
            email_data.get('recipients'),
            email_data.get('cc'),
            email_data.get('email_date'),
            1 if email_data.get('has_attachments') else 0,
            email_data.get('attachment_count', 0),
        ))
        return email_data

    return None


# ==================== Directory Scanning ====================

def scan_directory(mount_path: str, start_dir: str, volume: str, skip_patterns: List[str],
                   include_patterns: List[str], max_depth: Optional[int],
                   check_existing: List[str], verbose: int, dry_run: bool, literal_patterns: bool,
                   run_timestamp: str, conn: sqlite3.Connection, limit: Optional[int] = None) -> Tuple[int, int, int]:
    """Recursively scan a volume mount and process indexable files."""
    full_path = os.path.join(mount_path, start_dir) if start_dir else mount_path
    volume_name = normalize_volume_name(volume)

    if not os.path.exists(full_path):
        print(f"Error: Path does not exist: {full_path}", file=sys.stderr)
        return 0, 0, 0

    files_added = 0
    files_updated = 0
    files_skipped = 0
    files_processed = 0
    commit_counter = 0
    commit_interval = 100

    print(f"\nScanning directory: {full_path}")
    print(f"Volume: {volume_name}")
    print(f"Mount path: {mount_path}")
    print(f"Include patterns: {include_patterns if include_patterns else 'All files'}")
    print(f"Skip patterns: {skip_patterns if skip_patterns else 'None'}")
    print(f"Max depth: {max_depth if max_depth is not None else 'Unlimited'}")
    print(f"Check existing by: {', '.join(check_existing)}")
    if limit:
        print(f"Limit: {limit} files")
    if dry_run:
        print("Mode: DRY RUN (no changes will be made)")
    print()

    for root, dirs, files in os.walk(full_path):
        current_depth = calculate_depth(full_path, root)

        if max_depth is not None and current_depth > max_depth:
            dirs.clear()
            continue

        if should_skip_path(root, skip_patterns, literal_patterns):
            print(f"Skipping directory (matches skip pattern): {root}")
            dirs.clear()
            continue

        if max_depth is not None:
            if current_depth >= max_depth:
                dirs.clear()
            else:
                dirs[:] = [d for d in dirs if not should_skip_path(os.path.join(root, d), skip_patterns, literal_patterns)]
        else:
            dirs[:] = [d for d in dirs if not should_skip_path(os.path.join(root, d), skip_patterns, literal_patterns)]

        for filename in files:
            if limit and files_processed >= limit:
                print(f"\nReached limit of {limit} files. Stopping.")
                return files_added, files_updated, files_skipped

            filepath = os.path.join(root, filename)

            if not matches_include_pattern(filepath, include_patterns, literal_patterns):
                record_skipped_file(filepath, "not_matching_include_pattern", volume_name,
                                    mount_path, run_timestamp, conn)
                files_skipped += 1
                continue

            if should_skip_path(filepath, skip_patterns, literal_patterns):
                record_skipped_file(filepath, "matches_skip_pattern", volume_name,
                                    mount_path, run_timestamp, conn)
                files_skipped += 1
                continue

            success, skip_reason, was_update = process_file(
                filepath, volume_name, mount_path, run_timestamp,
                check_existing, verbose, dry_run, conn,
            )
            if success:
                if was_update:
                    files_updated += 1
                else:
                    files_added += 1
                files_processed += 1
            else:
                files_skipped += 1
                if skip_reason:
                    record_skipped_file(filepath, skip_reason, volume_name,
                                        mount_path, run_timestamp, conn)

            if not dry_run:
                commit_counter += 1
                if commit_counter >= commit_interval:
                    conn.commit()
                    commit_counter = 0

    if not dry_run:
        conn.commit()

    return files_added, files_updated, files_skipped


# ==================== Main ====================

def main():
    parser = argparse.ArgumentParser(
        description="Index files by logical volume into a SQLite database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Register a volume first
  python3 manage_volumes.py --db-path media.db set Photo \\
      --src-root /volume1/photo --mount /mnt/photo

  # Index all supported files in a volume
  python3 index_media.py --volume Photo --db-path media.db

  # Index one subdirectory
  python3 index_media.py --volume Photo --start-dir 2024 --db-path media.db

  # Incremental indexing
  python3 index_media.py --volume Photo --db-path media.db \\
      --check-existing relpath --check-existing size --check-existing modified_date
        """
    )

    parser.add_argument("--volume", required=True,
                        help="Logical volume name (case-insensitive; must be registered)")
    parser.add_argument("--start-dir", action="append", default=[],
                        help="Starting directory relative to volume mount (repeatable)")
    parser.add_argument("--include-pattern", action="append", default=[],
                        help="Pattern to include in paths (regex by default)")
    parser.add_argument("--skip-pattern", action="append", default=[],
                        help="Pattern to skip in paths (regex by default)")
    parser.add_argument("--literal-patterns", action="store_true",
                        help="Treat include/skip patterns as literal strings")
    parser.add_argument("--max-depth", type=int, default=None,
                        help="Maximum directory depth to recurse")
    parser.add_argument("--check-existing", action="append",
                        choices=['relpath', 'fullpath', 'volume', 'size', 'modified_date', 'hash'],
                        help="Criteria for checking if file already indexed")
    parser.add_argument("--verbose", "-v", type=int, default=0, choices=[0, 1, 2, 3],
                        help="Verbosity level")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show actions without modifying the database")
    parser.add_argument("--limit", type=int,
                        help="Limit number of files to process")
    parser.add_argument("--db-path", default="media_index.db",
                        help="Path to SQLite database file")

    args = parser.parse_args()

    if not PIL_AVAILABLE:
        print("Warning: PIL/Pillow not installed. Install with: pip install Pillow", file=sys.stderr)

    try:
        subprocess.run(["exiftool", "-ver"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: exiftool not found. Please install it.", file=sys.stderr)
        sys.exit(1)

    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Warning: ffprobe not found. Audio/video processing will be limited.", file=sys.stderr)

    print(f"Using database: {args.db_path}")
    conn = sqlite3.connect(args.db_path)
    create_database_schema(conn)

    volume = get_volume(conn, args.volume)
    if not volume:
        print(
            f"Error: volume '{args.volume}' is not registered. "
            f"Use manage_volumes.py set to register it.",
            file=sys.stderr,
        )
        conn.close()
        sys.exit(1)

    mount_path = volume['mount_path']
    if not os.path.isdir(mount_path):
        print(f"Error: volume mount path is not accessible: {mount_path}", file=sys.stderr)
        conn.close()
        sys.exit(1)

    start_time = datetime.now()
    run_timestamp = start_time.isoformat()
    check_existing = args.check_existing if args.check_existing else ['relpath', 'volume']

    print(f"Run timestamp: {run_timestamp}")
    print(f"Resolved volume '{volume['name']}' -> {mount_path}")
    print(f"Source root: {volume['src_root']}\n")

    start_dirs = args.start_dir if args.start_dir else [""]
    total_files_added = 0
    total_files_updated = 0
    total_files_skipped = 0
    remaining_limit = args.limit

    for start_dir in start_dirs:
        current_limit = remaining_limit if remaining_limit else None
        files_added, files_updated, files_skipped = scan_directory(
            mount_path,
            start_dir,
            volume['name'],
            args.skip_pattern,
            args.include_pattern,
            args.max_depth,
            check_existing,
            args.verbose,
            args.dry_run,
            args.literal_patterns,
            run_timestamp,
            conn,
            current_limit,
        )
        total_files_added += files_added
        total_files_updated += files_updated
        total_files_skipped += files_skipped

        if remaining_limit:
            remaining_limit -= (files_added + files_updated)
            if remaining_limit <= 0:
                print("\nLimit reached. Stopping further directory scans.")
                break

    end_time = datetime.now()

    skip_reasons = []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT skip_reason, COUNT(*)
            FROM skipped_files
            WHERE run_timestamp = ?
            GROUP BY skip_reason
            ORDER BY COUNT(*) DESC
        """, (run_timestamp,))
        skip_reasons = cursor.fetchall()
    except Exception as e:
        print(f"Warning: Could not retrieve skip reasons summary: {e}", file=sys.stderr)

    conn.close()

    duration = (end_time - start_time).total_seconds()
    print(f"\n{'='*60}")
    print("Indexing complete!")
    print(f"Run timestamp: {run_timestamp}")
    print(f"Files added: {total_files_added}")
    print(f"Files updated: {total_files_updated}")
    print(f"Files skipped: {total_files_skipped}")

    if skip_reasons:
        print("\nSkip reasons breakdown:")
        for reason, count in skip_reasons:
            print(f"  - {reason}: {count}")

    print(f"\nDuration: {duration:.2f} seconds")
    print(f"Database: {args.db_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
