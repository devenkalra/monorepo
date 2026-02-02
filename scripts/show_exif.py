#!/usr/bin/env python3
"""show_exif.py - Display EXIF/metadata information from image and video files.

This script uses exiftool to extract and display metadata in various formats.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional


def run_exiftool(files: List[str], options: List[str]) -> str:
    """Run exiftool with specified options.
    
    Args:
        files: List of file paths
        options: List of exiftool options
    
    Returns:
        Output from exiftool
    """
    cmd = ['exiftool'] + options + files
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running exiftool: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: exiftool not found. Please install it:", file=sys.stderr)
        print("  Ubuntu/Debian: sudo apt-get install libimage-exiftool-perl", file=sys.stderr)
        print("  macOS: brew install exiftool", file=sys.stderr)
        sys.exit(1)


def show_common_tags(files: List[str], grouped: bool = False, show_filenames: bool = True):
    """Show common EXIF tags.
    
    Args:
        files: List of file paths
        grouped: Whether to group tags by category
        show_filenames: Whether to show filenames
    """
    tags = [
        'FileName', 'FileSize', 'FileType', 'MIMEType',
        'ImageWidth', 'ImageHeight', 'Make', 'Model',
        'DateTimeOriginal', 'CreateDate', 'ModifyDate',
        'ISO', 'FNumber', 'ExposureTime', 'FocalLength',
        'LensModel', 'Orientation'
    ]
    
    options = []
    for tag in tags:
        options.extend(['-' + tag])
    
    if grouped:
        options.append('-G')
    
    if not show_filenames:
        options.append('-s3')  # Short format, values only
    
    output = run_exiftool(files, options)
    print(output)


def show_gps_tags(files: List[str], grouped: bool = False, show_filenames: bool = True):
    """Show GPS-related tags.
    
    Args:
        files: List of file paths
        grouped: Whether to group tags by category
        show_filenames: Whether to show filenames
    """
    options = ['-a', '-GPS:all', '-XMP-photoshop:City', '-XMP-photoshop:State', 
               '-XMP-photoshop:Country', '-XMP-iptcExt:LocationShown*',
               '-XMP-dc:Coverage']
    
    if grouped:
        options.append('-G')
    
    if not show_filenames:
        options.append('-s3')
    
    output = run_exiftool(files, options)
    if output.strip():
        print(output)
    else:
        print("No GPS/location data found in the specified file(s).")


def show_all_tags(files: List[str], grouped: bool = False, show_filenames: bool = True):
    """Show all EXIF tags.
    
    Args:
        files: List of file paths
        grouped: Whether to group tags by category
        show_filenames: Whether to show filenames
    """
    options = ['-a']  # Allow duplicate tags
    
    if grouped:
        options.append('-G')  # Group by category
    
    if not show_filenames:
        options.append('-s3')
    
    output = run_exiftool(files, options)
    print(output)


def show_specific_tags(files: List[str], tags: List[str], show_filenames: bool = True):
    """Show specific EXIF tags.
    
    Args:
        files: List of file paths
        tags: List of tag names
        show_filenames: Whether to show filenames
    """
    options = []
    for tag in tags:
        if not tag.startswith('-'):
            tag = '-' + tag
        options.append(tag)
    
    if not show_filenames:
        options.append('-s3')
    
    output = run_exiftool(files, options)
    print(output)


def show_json(files: List[str], grouped: bool = False):
    """Show EXIF data in JSON format.
    
    Args:
        files: List of file paths
        grouped: Whether to group tags by category
    """
    options = ['-json', '-a']
    
    if grouped:
        options.append('-G')
    
    output = run_exiftool(files, options)
    
    # Pretty print JSON
    try:
        data = json.loads(output)
        print(json.dumps(data, indent=2))
    except json.JSONDecodeError:
        print(output)


def show_keywords(files: List[str], grouped: bool = False, show_filenames: bool = True):
    """Show keywords and caption information.
    
    Args:
        files: List of file paths
        grouped: Whether to group tags by category
        show_filenames: Whether to show filenames
    """
    options = ['-a', '-Keywords', '-Subject', '-XMP-dc:Subject', 
               '-IPTC:Keywords', '-Caption-Abstract', '-ImageDescription',
               '-XMP-dc:Description', '-XMP-dc:Title']
    
    if grouped:
        options.append('-G')
    
    if not show_filenames:
        options.append('-s3')
    
    output = run_exiftool(files, options)
    if output.strip():
        print(output)
    else:
        print("No keywords/captions found in the specified file(s).")


def show_camera_settings(files: List[str], grouped: bool = False, show_filenames: bool = True):
    """Show camera settings.
    
    Args:
        files: List of file paths
        grouped: Whether to group tags by category
        show_filenames: Whether to show filenames
    """
    options = ['-Make', '-Model', '-LensModel', '-LensInfo',
               '-ISO', '-FNumber', '-ExposureTime', '-FocalLength',
               '-FocalLengthIn35mmFormat', '-WhiteBalance', '-Flash',
               '-ExposureProgram', '-MeteringMode', '-ExposureCompensation']
    
    if grouped:
        options.append('-G')
    
    if not show_filenames:
        options.append('-s3')
    
    output = run_exiftool(files, options)
    print(output)


def show_video_metadata(files: List[str], grouped: bool = False, show_filenames: bool = True):
    """Show video metadata.
    
    Args:
        files: List of file paths
        grouped: Whether to group tags by category
        show_filenames: Whether to show filenames
    """
    options = ['-ImageWidth', '-ImageHeight', '-Duration', '-VideoFrameRate',
               '-VideoCodec', '-AudioChannels', '-AudioBitrate', '-AudioCodec',
               '-CompressorName', '-BitDepth', '-ColorSpace']
    
    if grouped:
        options.append('-G')
    
    if not show_filenames:
        options.append('-s3')
    
    output = run_exiftool(files, options)
    print(output)


def extract_thumbnails(files: List[str], output_dir: str = None):
    """Extract and save thumbnails from files.
    
    Args:
        files: List of file paths
        output_dir: Directory to save thumbnails (default: temp directory)
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix='exif_thumbnails_')
    else:
        os.makedirs(output_dir, exist_ok=True)
    
    print(f"Extracting thumbnails to: {output_dir}\n")
    
    extracted_count = 0
    for file_path in files:
        filename = Path(file_path).name
        output_file = os.path.join(output_dir, f"thumb_{filename}")
        
        # Try to extract thumbnail using exiftool
        cmd = ['exiftool', '-b', '-ThumbnailImage', file_path]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=False
            )
            
            if result.returncode == 0 and result.stdout and len(result.stdout) > 0:
                # Save thumbnail
                with open(output_file, 'wb') as f:
                    f.write(result.stdout)
                
                # Get thumbnail info
                info_cmd = ['exiftool', '-s', '-ImageWidth', '-ImageHeight', output_file]
                info_result = subprocess.run(info_cmd, capture_output=True, text=True, check=False)
                
                print(f"✓ {filename}")
                print(f"  Saved to: {output_file}")
                if info_result.stdout:
                    print(f"  {info_result.stdout.strip()}")
                print()
                
                extracted_count += 1
            else:
                print(f"✗ {filename}")
                print(f"  No thumbnail found")
                print()
        
        except Exception as e:
            print(f"✗ {filename}")
            print(f"  Error: {str(e)}")
            print()
    
    if extracted_count > 0:
        print(f"\nExtracted {extracted_count} thumbnail(s)")
        print(f"Location: {output_dir}")
        
        # Try to open the directory in file manager
        try:
            if sys.platform == 'darwin':
                subprocess.run(['open', output_dir], check=False)
            elif sys.platform == 'linux':
                subprocess.run(['xdg-open', output_dir], check=False)
            elif sys.platform == 'win32':
                subprocess.run(['explorer', output_dir], check=False)
        except:
            pass
    else:
        print("\nNo thumbnails found in any files")
    
    return output_dir


def show_thumbnail_info(files: List[str]):
    """Show information about embedded thumbnails.
    
    Args:
        files: List of file paths
    """
    for file_path in files:
        print(f"======== {file_path}")
        
        # Check for thumbnail
        cmd = ['exiftool', '-a', '-G', '-ThumbnailImage', '-PreviewImage',
               '-JpgFromRaw', '-OtherImage', file_path]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        
        if result.stdout.strip():
            print(result.stdout)
            
            # Try to get thumbnail dimensions
            thumb_cmd = ['exiftool', '-b', '-ThumbnailImage', file_path]
            thumb_result = subprocess.run(thumb_cmd, capture_output=True, check=False)
            
            if thumb_result.returncode == 0 and thumb_result.stdout and len(thumb_result.stdout) > 0:
                # Save to temp file to get dimensions
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    tmp.write(thumb_result.stdout)
                    tmp_path = tmp.name
                
                try:
                    info_cmd = ['exiftool', '-s', '-ImageWidth', '-ImageHeight', '-FileSize', tmp_path]
                    info_result = subprocess.run(info_cmd, capture_output=True, text=True, check=False)
                    if info_result.stdout:
                        print("Thumbnail Details:")
                        print(info_result.stdout)
                finally:
                    os.unlink(tmp_path)
        else:
            print("No embedded thumbnail found")
        
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Display EXIF/metadata information from image and video files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show common EXIF tags
  python3 show_exif.py --files photo.jpg --mode common
  
  # Show GPS information
  python3 show_exif.py --files photo.jpg --mode gps
  
  # Show all tags, grouped by category
  python3 show_exif.py --files photo.jpg --mode all --grouped
  
  # Show specific tags
  python3 show_exif.py --files photo.jpg --mode specific --tags Make Model ISO
  
  # Output as JSON
  python3 show_exif.py --files photo.jpg video.mp4 --mode json
  
  # Show camera settings for multiple files
  python3 show_exif.py --files *.jpg --mode camera
  
  # Show keywords and captions
  python3 show_exif.py --files photo.jpg --mode keywords
  
  # Show thumbnail information
  python3 show_exif.py --files photo.jpg --mode thumbnail
  
  # Extract thumbnails to files
  python3 show_exif.py --files photo.jpg video.mp4 --extract-thumbnails
  
  # Extract thumbnails to specific directory
  python3 show_exif.py --files *.jpg --extract-thumbnails --thumbnail-dir ./thumbnails
        """
    )
    
    parser.add_argument("--file", "--files", dest="files", action="append", 
                       default=[], required=True,
                       help="File(s) to show EXIF data for (can be repeated)")
    
    parser.add_argument("--mode", "-m", action="append", choices=[
        'common', 'gps', 'all', 'specific', 'json', 
        'keywords', 'camera', 'video', 'thumbnail'
    ], default=[],
                       help="Display mode(s) - can be specified multiple times (default: common)")
    
    parser.add_argument("--grouped", "-g", action="store_true",
                       help="Group tags by category (adds -G option)")
    
    parser.add_argument("--tags", "-t", nargs="+",
                       help="Specific tags to display (for --mode specific)")
    
    parser.add_argument("--no-filenames", action="store_true",
                       help="Don't show filenames in output")
    
    parser.add_argument("--compact", "-c", action="store_true",
                       help="Compact output format")
    
    parser.add_argument("--extract-thumbnails", action="store_true",
                       help="Extract and save thumbnails to files")
    
    parser.add_argument("--thumbnail-dir", type=str,
                       help="Directory to save extracted thumbnails (default: temp directory)")
    
    parser.add_argument("--limit", type=int,
                       help="Limit number of files to process (useful for testing)")
    
    args = parser.parse_args()
    
    # Flatten files list
    files = []
    for item in args.files:
        if isinstance(item, list):
            files.extend(item)
        else:
            files.append(item)
    
    # Check files exist
    for file_path in files:
        if not Path(file_path).exists():
            print(f"Warning: File not found: {file_path}", file=sys.stderr)
    
    # Filter to existing files
    files = [f for f in files if Path(f).exists()]
    
    if not files:
        print("Error: No valid files specified", file=sys.stderr)
        sys.exit(1)
    
    # Apply limit if specified
    if args.limit and args.limit > 0:
        original_count = len(files)
        files = files[:args.limit]
        print(f"Limit applied: Processing {len(files)} of {original_count} file(s).\n")
    
    show_filenames = not args.no_filenames
    
    # Default to common if no modes specified
    modes = args.mode if args.mode else ['common']
    
    # Execute based on mode(s)
    for i, mode in enumerate(modes):
        # Add separator between modes if multiple
        if i > 0:
            print("\n" + "="*80 + "\n")
        
        if mode == 'common':
            show_common_tags(files, args.grouped, show_filenames)
        
        elif mode == 'gps':
            show_gps_tags(files, args.grouped, show_filenames)
        
        elif mode == 'all':
            show_all_tags(files, args.grouped, show_filenames)
        
        elif mode == 'specific':
            if not args.tags:
                print("Error: --tags required for --mode specific", file=sys.stderr)
                sys.exit(1)
            show_specific_tags(files, args.tags, show_filenames)
        
        elif mode == 'json':
            show_json(files, args.grouped)
        
        elif mode == 'keywords':
            show_keywords(files, args.grouped, show_filenames)
        
        elif mode == 'camera':
            show_camera_settings(files, args.grouped, show_filenames)
        
        elif mode == 'video':
            show_video_metadata(files, args.grouped, show_filenames)
        
        elif mode == 'thumbnail':
            show_thumbnail_info(files)
    
    # Extract thumbnails if requested
    if args.extract_thumbnails:
        print("\n" + "="*80 + "\n")
        extract_thumbnails(files, args.thumbnail_dir)


if __name__ == "__main__":
    main()
