#!/usr/bin/env python3
"""index_media.py - Index media files (images and videos) into a SQLite database.

This script recursively scans a directory, extracts metadata from image and video files,
generates thumbnails, and stores everything in a SQLite database.

Features:
- Recursive directory scanning with pattern-based skipping
- Image metadata extraction from EXIF data
- Video metadata extraction using ffprobe
- Thumbnail generation for both images and videos
- File hashing for duplicate detection
- Normalized metadata fields for easy querying
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import shared utilities
from media_utils import (
    create_database_schema,
    calculate_file_hash,
    get_mime_type,
    is_image_file,
    is_video_file
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


# ==================== Thumbnail Generation ====================

def generate_thumbnail(filepath: str, mime_type: str, extension: str = '', 
                       max_size: Tuple[int, int] = (200, 200)) -> Optional[bytes]:
    """Generate a thumbnail for an image or video file."""
    
    # Check if it's a RAW file
    raw_extensions = [
        '.raw', '.cr2', '.cr3', '.nef', '.arw', '.dng', '.orf', '.rw2', 
        '.pef', '.srw', '.raf', '.3fr', '.fff', '.iiq', '.rwl', '.nrw',
        '.mrw', '.erf', '.kdc', '.dcr', '.mos', '.ptx', '.r3d'
    ]
    
    if extension.lower() in raw_extensions:
        return _generate_raw_thumbnail(filepath, max_size)
    elif mime_type.startswith('image/'):
        return _generate_image_thumbnail(filepath, max_size)
    elif mime_type.startswith('video/'):
        return _generate_video_thumbnail(filepath, max_size)
    
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
                    # Load the extracted image
                    img = Image.open(io.BytesIO(result.stdout))
                    
                    # Convert to RGB if necessary
                    if img.mode not in ('RGB', 'RGBA'):
                        img = img.convert('RGB')
                    
                    # Generate thumbnail
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)
                    
                    # Save to bytes
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
            # Convert to RGB if necessary
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')
            
            # Generate thumbnail
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save to bytes
            import io
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
                        run_timestamp: str, conn: sqlite3.Connection):
    """Record a skipped file in the database."""
    try:
        cursor = conn.cursor()
        
        # Get file size if file exists
        file_size = None
        if os.path.exists(filepath):
            try:
                file_size = os.path.getsize(filepath)
            except Exception:
                pass
        
        cursor.execute("""
            INSERT INTO skipped_files (run_timestamp, fullpath, skip_reason, volume, file_size, recorded_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            run_timestamp,
            os.path.abspath(filepath),
            skip_reason,
            volume,
            file_size,
            datetime.now().isoformat()
        ))
        # Don't commit here - let the caller handle commits
    except Exception as e:
        print(f"Warning: Could not record skipped file {filepath}: {e}", file=sys.stderr)


def get_file_info(filepath: str, volume: str) -> Dict:
    """Get basic file information."""
    stat = os.stat(filepath)
    
    info = {
        'volume': volume,
        'fullpath': os.path.abspath(filepath),
        'name': os.path.basename(filepath),
        'modified_date': datetime.fromtimestamp(stat.st_mtime).isoformat(),
        'size': stat.st_size,
        'extension': os.path.splitext(filepath)[1].lower(),
    }
    
    # Try to get creation date (platform dependent)
    try:
        info['created_date'] = datetime.fromtimestamp(stat.st_ctime).isoformat()
    except Exception:
        info['created_date'] = info['modified_date']
    
    # Get MIME type
    info['mime_type'] = get_mime_type(filepath)
    
    return info


def check_file_exists(file_info: Dict, check_criteria: List[str], conn: sqlite3.Connection) -> bool:
    """Check if a file already exists in database based on specified criteria.
    
    Args:
        file_info: Dictionary with file information
        check_criteria: List of criteria to check ('fullpath', 'volume', 'size', 'modified_date', 'hash')
        conn: Database connection
    
    Returns:
        True if file exists, False otherwise
    """
    cursor = conn.cursor()
    
    # Build WHERE clause based on criteria
    conditions = []
    params = []
    
    for criterion in check_criteria:
        if criterion == 'fullpath':
            conditions.append("fullpath = ?")
            params.append(file_info.get('fullpath'))
        elif criterion == 'volume':
            conditions.append("volume = ?")
            params.append(file_info.get('volume'))
        elif criterion == 'size':
            conditions.append("size = ?")
            params.append(file_info.get('size'))
        elif criterion == 'modified_date':
            conditions.append("modified_date = ?")
            params.append(file_info.get('modified_date'))
        elif criterion == 'hash':
            # Hash might not be calculated yet
            if 'file_hash' in file_info and file_info['file_hash']:
                conditions.append("file_hash = ?")
                params.append(file_info['file_hash'])
    
    if not conditions:
        # Default to fullpath and volume
        conditions = ["fullpath = ?", "volume = ?"]
        params = [file_info.get('fullpath'), file_info.get('volume')]
    
    where_clause = " AND ".join(conditions)
    query = f"SELECT id FROM files WHERE {where_clause}"
    
    cursor.execute(query, params)
    return cursor.fetchone() is not None


def process_file(filepath: str, volume: str, run_timestamp: str, 
                check_existing: List[str], verbose: int, dry_run: bool, conn: sqlite3.Connection) -> Tuple[bool, Optional[str], bool]:
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
        # Get basic file info
        file_info = get_file_info(filepath, volume)
        
        # Calculate hash if it's part of check criteria
        if 'hash' in check_existing:
            file_info['file_hash'] = calculate_file_hash(filepath)
        
        # Check if file already exists based on user's specified criteria
        existing_file_id = None
        if check_file_exists(file_info, check_existing, conn):
            # File exists based on check criteria - we'll skip it
            criteria_str = '+'.join(check_existing)
            if verbose >= 1:
                print(f"Skipping (already indexed by {criteria_str}): {filepath}")
            return False, f"already_indexed (by {criteria_str})", False
        
        # Check if file exists by fullpath+volume (UNIQUE constraint)
        # If it exists but didn't match check criteria, we need to update it
        cursor.execute("SELECT id FROM files WHERE fullpath = ? AND volume = ?", 
                      (file_info['fullpath'], file_info['volume']))
        existing = cursor.fetchone()
        if existing:
            existing_file_id = existing[0]
            if dry_run or verbose >= 1:
                action = "[DRY RUN] Would update" if dry_run else "Updating"
                print(f"{action} existing record: {filepath}")
        else:
            if dry_run or verbose >= 1:
                action = "[DRY RUN] Would process" if dry_run else "Processing"
                print(f"{action}: {filepath}")
        
        mime_type = file_info['mime_type']
        extension = file_info['extension']
        
        # Only process image and video files
        if not (is_image_file(mime_type, extension) or is_video_file(mime_type)):
            return False, f"not_media_file (mime: {mime_type}, ext: {extension})", False
        
        # In dry-run mode, stop here and return success
        if dry_run:
            if verbose >= 2:
                print(f"  Type: {'Image' if is_image_file(mime_type, extension) else 'Video'} ({mime_type})")
                print(f"  Size: {file_info['size']} bytes")
            if verbose >= 3:
                print(f"  [DRY RUN] Would extract and store metadata")
            return True, None, (existing_file_id is not None)
        
        # Calculate hash if not already calculated
        if 'file_hash' not in file_info:
            file_info['file_hash'] = calculate_file_hash(filepath)
        file_info['indexed_date'] = datetime.now().isoformat()
        
        # Insert or update file record
        if existing_file_id:
            # Update existing record
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
                existing_file_id
            ))
            file_id = existing_file_id
            
            # Delete old metadata and thumbnails (will be regenerated)
            cursor.execute("DELETE FROM image_metadata WHERE file_id = ?", (file_id,))
            cursor.execute("DELETE FROM video_metadata WHERE file_id = ?", (file_id,))
            cursor.execute("DELETE FROM thumbnails WHERE file_id = ?", (file_id,))
        else:
            # Insert new record
            cursor.execute("""
                INSERT INTO files (volume, fullpath, name, created_date, modified_date, 
                                 size, mime_type, extension, file_hash, indexed_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_info['volume'],
                file_info['fullpath'],
                file_info['name'],
                file_info['created_date'],
                file_info['modified_date'],
                file_info['size'],
                file_info['mime_type'],
                file_info['extension'],
                file_info['file_hash'],
                file_info['indexed_date']
            ))
            file_id = cursor.lastrowid
        
        # Process based on file type
        if is_image_file(mime_type, extension):
            normalized_data = process_image(filepath, file_id, conn)
            if verbose >= 2:
                print(f"  Type: Image ({mime_type})")
                print(f"  Size: {file_info['size']} bytes")
                print(f"  Hash: {file_info['file_hash'][:16]}...")
            if verbose >= 3 and normalized_data:
                print(f"  Image metadata:")
                for key, value in normalized_data.items():
                    if value is not None and value != '':
                        print(f"    {key}: {value}")
        elif is_video_file(mime_type):
            video_data = process_video(filepath, file_id, conn)
            if verbose >= 2:
                print(f"  Type: Video ({mime_type})")
                print(f"  Size: {file_info['size']} bytes")
                print(f"  Hash: {file_info['file_hash'][:16]}...")
            if verbose >= 3 and video_data:
                print(f"  Video metadata:")
                for key, value in video_data.items():
                    if value is not None and value != '':
                        print(f"    {key}: {value}")
        
        # Generate and store thumbnail
        thumbnail_data = generate_thumbnail(filepath, mime_type, extension)
        if thumbnail_data:
            cursor.execute("""
                INSERT INTO thumbnails (file_id, thumbnail_data, thumbnail_width, thumbnail_height)
                VALUES (?, ?, ?, ?)
            """, (file_id, thumbnail_data, 200, 200))
        
        conn.commit()
        return True, None, (existing_file_id is not None)
        
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


# ==================== Directory Scanning ====================

def scan_directory(base_path: str, start_dir: str, volume: str, skip_patterns: List[str],
                   include_patterns: List[str], max_depth: Optional[int],
                   check_existing: List[str], verbose: int, dry_run: bool, literal_patterns: bool,
                   run_timestamp: str, conn: sqlite3.Connection, limit: Optional[int] = None) -> Tuple[int, int, int]:
    """Recursively scan directory and process media files.
    
    Args:
        base_path: Base directory path
        start_dir: Starting subdirectory
        volume: Volume tag for this collection
        skip_patterns: Patterns to skip (applied after include)
        include_patterns: Patterns to include (applied first)
        max_depth: Maximum depth to recurse (None = unlimited, 0 = current dir only)
        check_existing: Criteria for checking if file exists (fullpath, volume, size, modified_date, hash)
        verbose: Verbosity level (0=quiet, 1=file+outcome, 2=more details, 3=full data)
        dry_run: If True, only show what would be done without actually doing it
        literal_patterns: If True, treat patterns as literal strings; if False, treat as regex
        run_timestamp: Timestamp for this run (for tracking skipped files)
        conn: Database connection
    
    Returns:
        Tuple of (files_added, files_updated, files_skipped)
    """
    full_path = os.path.join(base_path, start_dir) if start_dir else base_path
    
    if not os.path.exists(full_path):
        print(f"Error: Path does not exist: {full_path}", file=sys.stderr)
        return 0, 0, 0
    
    files_added = 0
    files_updated = 0
    files_skipped = 0
    files_processed = 0
    commit_counter = 0
    commit_interval = 100  # Commit every 100 files
    
    print(f"\nScanning directory: {full_path}")
    print(f"Volume tag: {volume}")
    print(f"Include patterns: {include_patterns if include_patterns else 'All files'}")
    print(f"Skip patterns: {skip_patterns if skip_patterns else 'None'}")
    print(f"Max depth: {max_depth if max_depth is not None else 'Unlimited'}")
    print(f"Check existing by: {', '.join(check_existing)}")
    if limit:
        print(f"Limit: {limit} files")
    if dry_run:
        print(f"Mode: DRY RUN (no changes will be made)")
    print()
    
    for root, dirs, files in os.walk(full_path):
        # Calculate current depth
        current_depth = calculate_depth(full_path, root)
        
        # Check if we've exceeded max depth
        if max_depth is not None and current_depth > max_depth:
            dirs.clear()  # Don't recurse further
            continue
        
        # Check if current directory should be skipped
        if should_skip_path(root, skip_patterns, literal_patterns):
            print(f"Skipping directory (matches skip pattern): {root}")
            dirs.clear()  # Don't recurse into subdirectories
            continue
        
        # Filter out directories to skip, and respect max_depth
        if max_depth is not None:
            # Only keep directories if we haven't reached max depth
            if current_depth >= max_depth:
                dirs.clear()
            else:
                dirs[:] = [d for d in dirs if not should_skip_path(os.path.join(root, d), skip_patterns, literal_patterns)]
        else:
            dirs[:] = [d for d in dirs if not should_skip_path(os.path.join(root, d), skip_patterns, literal_patterns)]
        
        for filename in files:
            # Check if we've reached the limit
            if limit and files_processed >= limit:
                print(f"\nReached limit of {limit} files. Stopping.")
                return files_added, files_updated, files_skipped
            
            filepath = os.path.join(root, filename)
            
            # First check if file matches include pattern
            if not matches_include_pattern(filepath, include_patterns, literal_patterns):
                record_skipped_file(filepath, "not_matching_include_pattern", volume, run_timestamp, conn)
                files_skipped += 1
                continue
            
            # Then check if file should be skipped
            if should_skip_path(filepath, skip_patterns, literal_patterns):
                record_skipped_file(filepath, "matches_skip_pattern", volume, run_timestamp, conn)
                files_skipped += 1
                continue
            
            # Process the file
            success, skip_reason, was_update = process_file(filepath, volume, run_timestamp, check_existing, verbose, dry_run, conn)
            if success:
                if was_update:
                    files_updated += 1
                else:
                    files_added += 1
                files_processed += 1
            else:
                files_skipped += 1
                if skip_reason and not dry_run:
                    record_skipped_file(filepath, skip_reason, volume, run_timestamp, conn)
            
            # Periodic commit to avoid losing too much data and keep transaction size manageable
            # Skip commits in dry-run mode
            if not dry_run:
                commit_counter += 1
                if commit_counter >= commit_interval:
                    conn.commit()
                    commit_counter = 0
    
    # Final commit for any remaining data (skip in dry-run mode)
    if not dry_run:
        conn.commit()
    
    return files_added, files_updated, files_skipped


# ==================== Main ====================

def main():
    parser = argparse.ArgumentParser(
        description="Index media files (images and videos) into a SQLite database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Index all media in a directory
  python3 index_media.py --path /media --start-dir photos --volume "MyPhotos" --db-path media.db
  
  # Only process current directory (depth 0)
  python3 index_media.py --path /media/photos --volume "MyPhotos" --max-depth 0
  
  # Limit depth to 2 levels
  python3 index_media.py --path /media --volume "MyPhotos" --max-depth 2
  
  # Only include JPG files
  python3 index_media.py --path /media --volume "MyPhotos" --include-pattern ".jpg" --include-pattern ".JPG"
  
  # Include only images, skip thumbnails
  python3 index_media.py --path /media --volume "MyPhotos" --include-pattern "image/" --skip-pattern "thumb"
  
  # Skip certain directories
  python3 index_media.py --path /media --volume "MyPhotos" --skip-pattern ".git" --skip-pattern "node_modules"
  
  # Check for duplicates by hash (useful for finding moved/renamed files)
  python3 index_media.py --path /media --volume "MyPhotos" --check-existing hash
  
  # Check by multiple criteria (hash AND size)
  python3 index_media.py --path /media --volume "MyPhotos" --check-existing hash --check-existing size
        """
    )
    
    parser.add_argument("--path", required=True, 
                       help="Base path to scan")
    parser.add_argument("--start-dir", action="append", default=[],
                       help="Starting directory relative to path (can be repeated; default: scan from path root)")
    parser.add_argument("--volume", required=True,
                       help="Volume tag to identify this collection")
    parser.add_argument("--include-pattern", action="append", default=[],
                       help="Pattern to include in paths (regex by default, literal with --literal-patterns; can be repeated)")
    parser.add_argument("--skip-pattern", action="append", default=[],
                       help="Pattern to skip in paths (regex by default, literal with --literal-patterns; can be repeated)")
    parser.add_argument("--literal-patterns", action="store_true",
                       help="Treat include/skip patterns as literal strings instead of regex (auto-escapes special chars)")
    parser.add_argument("--max-depth", type=int, default=None,
                       help="Maximum directory depth to recurse (0 = current directory only, default: unlimited)")
    parser.add_argument("--check-existing", action="append", 
                       choices=['fullpath', 'volume', 'size', 'modified_date', 'hash'],
                       help="Criteria for checking if file already indexed (can be repeated; default: fullpath+volume)")
    parser.add_argument("--verbose", "-v", type=int, default=0, choices=[0, 1, 2, 3],
                       help="Verbosity level: 0=quiet, 1=file+outcome, 2=more details, 3=full metadata (default: 0)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without actually processing files or modifying the database")
    parser.add_argument("--limit", type=int,
                       help="Limit number of files to process (useful with --dry-run for testing)")
    parser.add_argument("--db-path", default="media_index.db",
                       help="Path to SQLite database file (default: media_index.db)")
    
    args = parser.parse_args()
    
    # Check dependencies
    if not PIL_AVAILABLE:
        print("Warning: PIL/Pillow not installed. Install with: pip install Pillow", file=sys.stderr)
    
    # Check for exiftool
    try:
        subprocess.run(["exiftool", "-ver"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: exiftool not found. Please install it.", file=sys.stderr)
        sys.exit(1)
    
    # Check for ffprobe
    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Warning: ffprobe not found. Video processing will be limited.", file=sys.stderr)
    
    # Connect to database
    print(f"Using database: {args.db_path}")
    conn = sqlite3.connect(args.db_path)
    
    # Create schema
    create_database_schema(conn)
    
    # Generate run timestamp
    start_time = datetime.now()
    run_timestamp = start_time.isoformat()
    
    # Set default check_existing criteria if none specified
    check_existing = args.check_existing if args.check_existing else ['fullpath', 'volume']
    
    print(f"Run timestamp: {run_timestamp}\n")
    
    # Determine which directories to scan
    start_dirs = args.start_dir if args.start_dir else [""]
    
    # Scan directories (accumulate totals across all start_dirs)
    total_files_added = 0
    total_files_updated = 0
    total_files_skipped = 0
    
    remaining_limit = args.limit  # Track remaining limit across directories
    for start_dir in start_dirs:
        # Calculate limit for this directory
        current_limit = remaining_limit if remaining_limit else None
        
        files_added, files_updated, files_skipped = scan_directory(
            args.path,
            start_dir,
            args.volume,
            args.skip_pattern,
            args.include_pattern,
            args.max_depth,
            check_existing,
            args.verbose,
            args.dry_run,
            args.literal_patterns,
            run_timestamp,
            conn,
            current_limit
        )
        total_files_added += files_added
        total_files_updated += files_updated
        total_files_skipped += files_skipped
        
        # Update remaining limit
        if remaining_limit:
            remaining_limit -= (files_added + files_updated)
            if remaining_limit <= 0:
                print(f"\nLimit reached. Stopping further directory scans.")
                break
    
    end_time = datetime.now()
    
    # Get skipped files count by reason (before closing database)
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
    
    # Close database
    conn.close()
    
    # Print summary
    duration = (end_time - start_time).total_seconds()
    print(f"\n{'='*60}")
    print(f"Indexing complete!")
    print(f"Run timestamp: {run_timestamp}")
    print(f"Files added: {total_files_added}")
    print(f"Files updated: {total_files_updated}")
    print(f"Files skipped: {total_files_skipped}")
    
    if skip_reasons:
        print(f"\nSkip reasons breakdown:")
        for reason, count in skip_reasons:
            print(f"  - {reason}: {count}")
    
    print(f"\nDuration: {duration:.2f} seconds")
    print(f"Database: {args.db_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
