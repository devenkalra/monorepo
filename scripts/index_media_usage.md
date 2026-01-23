# index_media.py - Usage Guide

## Overview

`index_media.py` is a comprehensive media indexing tool that recursively scans directories for image and video files, extracts metadata, generates thumbnails, and stores everything in a SQLite database for easy querying and management.

## Features

- **Recursive directory scanning** with pattern-based filtering
- **Image metadata extraction** from EXIF data (dimensions, camera settings, GPS, location, keywords, etc.)
- **RAW image format support** (CR2, CR3, NEF, ARW, RW2, DNG, ORF, and many more)
- **Video metadata extraction** using ffprobe (dimensions, codecs, duration, frame rate, etc.)
- **Thumbnail generation** for images, RAW files, and videos
- **File hashing** (SHA256) for duplicate detection
- **SQLite database** with normalized schema and indexes
- **Comprehensive metadata normalization** from various EXIF fields

## Requirements

### System Dependencies

```bash
# Install exiftool (required)
sudo apt-get install exiftool

# Install ffmpeg/ffprobe (required for video processing)
sudo apt-get install ffmpeg

# Optional: ImageMagick (alternative for image processing)
sudo apt-get install imagemagick
```

### Python Dependencies

```bash
pip install Pillow
```

## Database Schema

The script creates a SQLite database with the following tables:

### `files` - Main file records
- Basic file information (path, name, dates, size, mime type, hash)
- Indexed by volume, extension, and hash

### `image_metadata` - Image-specific data
- Raw EXIF data (JSON)
- Normalized fields: dimensions, camera settings, GPS coordinates, location, caption, keywords

### `video_metadata` - Video-specific data
- Dimensions, frame rate, codecs
- Audio information
- Duration

### `thumbnails` - Generated thumbnails
- JPEG thumbnail data (200x200 max)
- Linked to file records

### `skipped_files` - Tracking skipped files
- Records all files that were skipped during indexing
- Tracks run timestamp, filepath, skip reason, volume
- Useful for debugging and understanding what was excluded

## Command-Line Options

| Option | Required | Description |
|--------|----------|-------------|
| `--path` | Yes | Base path to scan |
| `--start-dir` | No | Starting directory relative to path (can be repeated; default: scan from path root) |
| `--volume` | Yes | Volume tag to identify this collection |
| `--include-pattern` | No | Pattern to include in paths (regex by default, literal with `--literal-patterns`; can be repeated) |
| `--skip-pattern` | No | Pattern to skip in paths (regex by default, literal with `--literal-patterns`; can be repeated) |
| `--literal-patterns` | No | Treat include/skip patterns as literal strings instead of regex (auto-escapes special chars) |
| `--max-depth` | No | Maximum directory depth to recurse (0 = current directory only, default: unlimited) |
| `--check-existing` | No | Criteria for checking if file already indexed (choices: `fullpath`, `volume`, `size`, `modified_date`, `hash`; can be repeated; default: `fullpath+volume`) |
| `--verbose`, `-v` | No | Verbosity level: 0=quiet, 1=file+outcome, 2=more details, 3=full metadata (default: 0) |
| `--dry-run` | No | Show what would be done without actually processing files or modifying the database |
| `--db-path` | No | Path to SQLite database file (default: `media_index.db`) |

## Usage Examples

### Basic Usage

Index all media files in a directory:

```bash
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos" \
  --db-path media.db
```

### With Start Directory

Start scanning from a subdirectory:

```bash
python3 index_media.py \
  --path /media \
  --start-dir photos/2024 \
  --volume "Photos2024" \
  --db-path media.db
```

### Multiple Start Directories

Scan multiple subdirectories in one run:

```bash
python3 index_media.py \
  --path /media/photos \
  --start-dir 2023 \
  --start-dir 2024 \
  --start-dir 2025 \
  --volume "RecentPhotos" \
  --db-path media.db
```

This is useful for:
- Indexing specific year/month folders
- Processing only certain project directories
- Skipping unwanted intermediate directories

### Index RAW Files

Index only RAW image files:

```bash
python3 index_media.py \
  --path /media/raw_photos \
  --volume "RawPhotos2024" \
  --include-pattern ".CR2" \
  --include-pattern ".NEF" \
  --include-pattern ".ARW" \
  --include-pattern ".RW2" \
  --db-path media.db
```

Index both RAW and JPEG files from the same shoot:

```bash
python3 index_media.py \
  --path /media/photo_shoot \
  --volume "PhotoShoot2024" \
  --include-pattern ".CR2" \
  --include-pattern ".jpg" \
  --include-pattern ".JPG" \
  --db-path media.db
```

### Depth Control

Only scan current directory (no subdirectories):

```bash
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos" \
  --max-depth 0 \
  --db-path media.db
```

Limit scanning to 2 levels deep:

```bash
python3 index_media.py \
  --path /media \
  --volume "MyPhotos" \
  --max-depth 2 \
  --db-path media.db
```

### Include Patterns

Only process JPG files:

```bash
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos" \
  --include-pattern ".jpg" \
  --include-pattern ".JPG" \
  --include-pattern ".jpeg" \
  --db-path media.db
```

Only process files in directories containing "2024":

```bash
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos" \
  --include-pattern "2024" \
  --db-path media.db
```

### Skip Patterns

Skip certain directories or files (applied after include patterns):

```bash
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos" \
  --skip-pattern ".git" \
  --skip-pattern "node_modules" \
  --skip-pattern ".tmp" \
  --skip-pattern "@eaDir" \
  --db-path media.db
```

### Combining Include and Skip

Process only JPG files, but skip thumbnail directories:

```bash
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos" \
  --include-pattern ".jpg" \
  --include-pattern ".JPG" \
  --skip-pattern "thumb" \
  --skip-pattern ".thumbnails" \
  --db-path media.db
```

### Multiple Volumes

Index different collections into the same database:

```bash
# Index vacation photos
python3 index_media.py \
  --path /media/vacation \
  --volume "Vacation2024" \
  --db-path ~/media.db

# Index family photos
python3 index_media.py \
  --path /media/family \
  --volume "Family2024" \
  --db-path ~/media.db

# Index work photos
python3 index_media.py \
  --path /media/work \
  --volume "Work2024" \
  --db-path ~/media.db
```

### Dry Run Mode

Preview what would be indexed without making any changes:

```bash
# See what files would be processed
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos" \
  --dry-run

# Combine with verbose to see details
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos" \
  --dry-run \
  --verbose 2
```

**Use Cases:**
- Test patterns before running full index
- Preview which files will be processed
- Verify skip/include patterns work correctly
- Check directory structure without modifying database

### Pattern Matching Modes

By default, patterns use **regex** (regular expressions). Use `--literal-patterns` for simple substring matching.

#### Regex Mode (default)

```bash
# Skip files ending with .tmp
python3 index_media.py --path /media --volume "Photos" \
  --skip-pattern "\.tmp$"

# Include only JPG or PNG files
python3 index_media.py --path /media --volume "Photos" \
  --include-pattern "\.(jpg|png)$"

# Skip hidden directories
python3 index_media.py --path /media --volume "Photos" \
  --skip-pattern "/\.[^/]+/"
```

#### Literal Mode (--literal-patterns)

```bash
# Skip .DS_Store files (no escaping needed!)
python3 index_media.py --path /media --volume "Photos" \
  --skip-pattern ".DS_Store" \
  --literal-patterns

# Skip multiple system files
python3 index_media.py --path /media --volume "Photos" \
  --skip-pattern ".DS_Store" \
  --skip-pattern "@eaDir" \
  --skip-pattern "Thumbs.db" \
  --literal-patterns

# Include only .JPG files
python3 index_media.py --path /media --volume "Photos" \
  --include-pattern ".JPG" \
  --literal-patterns
```

**When to use literal mode:**
- Simple substring matching
- Patterns with special characters (dots, brackets, etc.)
- When you don't need regex power

**When to use regex mode:**
- Pattern matching at start/end of strings (`^`, `$`)
- Multiple alternatives (`(jpg|png)`)
- Character classes (`[0-9]`, `\d`, `\w`)
- Complex patterns

### Verbose Output

Control the amount of information displayed during indexing:

```bash
# Quiet mode (default) - only summary
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos"

# Level 1 - Show each file being processed and outcome
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos" \
  --verbose 1

# Level 2 - Show file details (type, size, hash)
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos" \
  --verbose 2

# Level 3 - Show full metadata extracted
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos" \
  --verbose 3
```

**Verbosity Levels:**
- **0 (quiet)**: Only shows summary at the end
- **1 (file+outcome)**: Shows each file being processed, skipped, or updated
- **2 (more details)**: Adds file type, size, and hash information
- **3 (full metadata)**: Shows all extracted metadata (EXIF, GPS, camera settings, etc.)

### Duplicate Detection Strategies

By default, files are checked for duplication by `fullpath+volume`. You can customize this behavior:

```bash
# Check only by hash (useful for finding renamed/moved files)
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos" \
  --check-existing hash \
  --db-path media.db

# Check by size and modified date (faster than hash)
python3 index_media.py \
  --path /media/photos \
  --volume "MyPhotos" \
  --check-existing size \
  --check-existing modified_date \
  --db-path media.db

# Check by hash AND volume (find duplicates across different drives)
python3 index_media.py \
  --path /media/backup \
  --volume "BackupDrive" \
  --check-existing hash \
  --check-existing volume \
  --db-path media.db

# Check only by fullpath (ignore volume differences)
python3 index_media.py \
  --path /media/photos \
  --volume "NewVolume" \
  --check-existing fullpath \
  --db-path media.db
```

**Note**: When using `--check-existing hash`, the script will calculate the hash for each file before checking if it exists, which adds processing time but is useful for finding duplicates that have been renamed or moved.

## Supported File Formats

### Image Formats
- **Standard formats**: JPEG, PNG, GIF, BMP, TIFF, WebP
- **RAW formats**: 
  - Canon: CR2, CR3
  - Nikon: NEF, NRW
  - Sony: ARW
  - Panasonic: RW2
  - Olympus: ORF
  - Pentax: PEF
  - Samsung: SRW
  - Fujifilm: RAF
  - Adobe: DNG (Digital Negative)
  - Phase One: IIQ
  - Hasselblad: 3FR, FFF
  - Leica: RWL, DNG
  - Minolta: MRW
  - Kodak: KDC, DCR
  - Leaf: MOS
  - And many more...

### Video Formats
- MP4, MOV, AVI, MKV, WebM, FLV, WMV, and all formats supported by ffprobe

## Image Metadata Extracted

The script extracts and normalizes the following image metadata (works for both standard and RAW formats):

### Dimensions
- Width, Height

### Camera Settings
- Date taken (from multiple possible EXIF fields)
- Exposure time (shutter speed)
- Focal length
- Focal length (35mm equivalent)
- F-number (aperture)
- ISO

### Camera & Lens
- Camera make (manufacturer)
- Camera model
- Lens model

### GPS & Location
- Latitude, Longitude, Altitude
- City, State, Country, Country Code
- Coverage (location description)

### Descriptive
- Caption (description)
- Keywords (comma-separated)

## Video Metadata Extracted

For video files, the script extracts:

- **Dimensions**: Width, Height
- **Video**: Frame rate, Video codec
- **Audio**: Audio channels, Audio bit rate (kbps)
- **Duration**: Duration in seconds (fractional)

## Querying the Database

### Query Examples

```sql
-- Find all images taken with a specific camera
SELECT f.fullpath, i.camera_make, i.camera_model, i.date_taken
FROM files f
JOIN image_metadata i ON f.id = i.file_id
WHERE i.camera_make LIKE '%Canon%';

-- Find all images in a specific location
SELECT f.fullpath, i.city, i.state, i.country
FROM files f
JOIN image_metadata i ON f.id = i.file_id
WHERE i.city = 'New Delhi';

-- Find all videos longer than 1 minute
SELECT f.fullpath, v.duration_seconds, v.width, v.height
FROM files f
JOIN video_metadata v ON f.id = v.file_id
WHERE v.duration_seconds > 60;

-- Find duplicate files by hash
SELECT file_hash, COUNT(*) as count, GROUP_CONCAT(fullpath)
FROM files
WHERE file_hash != ''
GROUP BY file_hash
HAVING count > 1;

-- Find all images with GPS coordinates
SELECT f.fullpath, i.latitude, i.longitude, i.city, i.country
FROM files f
JOIN image_metadata i ON f.id = i.file_id
WHERE i.latitude IS NOT NULL AND i.longitude IS NOT NULL;

-- Get statistics by volume
SELECT volume, 
       COUNT(*) as total_files,
       SUM(size) / (1024*1024*1024.0) as total_gb,
       COUNT(DISTINCT extension) as file_types
FROM files
GROUP BY volume;

-- Find images with specific keywords
SELECT f.fullpath, i.keywords
FROM files f
JOIN image_metadata i ON f.id = i.file_id
WHERE i.keywords LIKE '%vacation%';

-- Get all images sorted by date taken
SELECT f.fullpath, i.date_taken, i.camera_model
FROM files f
JOIN image_metadata i ON f.id = i.file_id
WHERE i.date_taken IS NOT NULL
ORDER BY i.date_taken DESC;

-- View skipped files for a specific run
SELECT run_timestamp, fullpath, skip_reason, file_size
FROM skipped_files
WHERE run_timestamp = '2026-01-22T10:30:00.123456'
ORDER BY skip_reason, fullpath;

-- Get skip reasons summary for latest run
SELECT skip_reason, COUNT(*) as count
FROM skipped_files
WHERE run_timestamp = (SELECT MAX(run_timestamp) FROM skipped_files)
GROUP BY skip_reason
ORDER BY count DESC;

-- Find files that were skipped across multiple runs
SELECT fullpath, COUNT(DISTINCT run_timestamp) as times_skipped, 
       GROUP_CONCAT(DISTINCT skip_reason) as reasons
FROM skipped_files
GROUP BY fullpath
HAVING times_skipped > 1
ORDER BY times_skipped DESC;

-- Get all skipped files for a volume
SELECT s.run_timestamp, s.fullpath, s.skip_reason
FROM skipped_files s
WHERE s.volume = 'MyPhotos'
ORDER BY s.run_timestamp DESC, s.fullpath;
```

## Skip Reasons

The script tracks the following skip reasons:

| Reason | Description |
|--------|-------------|
| `not_matching_include_pattern` | File path doesn't match any include pattern |
| `matches_skip_pattern` | File path matches a skip pattern |
| `already_indexed (by ...)` | File already exists in the database (shows criteria used) |
| `not_media_file (mime: ...)` | File is not an image or video (shows MIME type) |
| `processing_error: ...` | An error occurred while processing (shows error message) |
```

## Pattern Matching Logic

The script applies patterns in the following order:

1. **Include Patterns** (if specified): File must match at least one include pattern
   - If no include patterns are specified, all files match
   - Patterns are substring matches (e.g., `".jpg"` matches any path containing ".jpg")

2. **Skip Patterns**: File must NOT match any skip pattern
   - Applied after include patterns
   - Also substring matches

### Examples

```bash
# Only process .jpg files, but skip thumbnails
--include-pattern ".jpg" --skip-pattern "thumb"
# Result: Processes "photo.jpg" but not "photo_thumb.jpg"

# Only process files in "vacation" folder, but skip raw files
--include-pattern "vacation" --skip-pattern ".raw"
# Result: Processes "/photos/vacation/img.jpg" but not "/photos/vacation/img.raw"

# Process all files except hidden directories
--skip-pattern "/."
# Result: Skips anything in paths like "/.git/" or "/.thumbnails/"
```

## Depth Levels

The `--max-depth` parameter controls how deep to recurse:

- `--max-depth 0`: Only scan files in the specified directory (no subdirectories)
- `--max-depth 1`: Scan specified directory and immediate subdirectories
- `--max-depth 2`: Scan two levels deep
- No `--max-depth`: Unlimited recursion (default)

### Depth Examples

Given structure:
```
/photos/
  ├── img1.jpg         (depth 0)
  ├── 2024/
  │   ├── img2.jpg     (depth 1)
  │   └── vacation/
  │       └── img3.jpg (depth 2)
```

```bash
# depth 0: Only img1.jpg
--path /photos --max-depth 0

# depth 1: img1.jpg, img2.jpg
--path /photos --max-depth 1

# depth 2: img1.jpg, img2.jpg, img3.jpg
--path /photos --max-depth 2
```

## Performance Tips

1. **Skip Patterns**: Use `--skip-pattern` to exclude system directories and reduce processing time:
   ```bash
   --skip-pattern ".git" --skip-pattern "@eaDir" --skip-pattern ".thumbnails"
   ```

2. **Incremental Indexing**: The script checks if files are already indexed (by fullpath) and skips them, making it safe to run multiple times.

3. **Database Indexes**: The schema includes indexes on commonly queried fields (volume, extension, hash, date_taken, location).

4. **Large Collections**: For very large collections, consider:
   - Running on a machine with SSD for better I/O performance
   - Splitting into multiple database files by volume or date range

## Troubleshooting

### "exiftool not found"
Install exiftool:
```bash
sudo apt-get install exiftool
```

### "PIL/Pillow not available"
Install Pillow:
```bash
pip install Pillow
```

### "ffprobe not found"
Install ffmpeg (includes ffprobe):
```bash
sudo apt-get install ffmpeg
```

### Thumbnails not generating
- Ensure PIL/Pillow is installed for images
- Ensure exiftool is installed for RAW files (extracts embedded previews)
- Ensure ffmpeg is installed for videos
- Check file permissions
- For RAW files, the script extracts embedded preview images using exiftool

### Database locked errors
- Ensure only one instance of the script is running
- Check that the database file is not open in another program

## Output

The script provides progress information and a detailed summary:

```
Using database: media.db
Run timestamp: 2026-01-22T10:30:45.123456

Scanning directory: /media/photos
Volume tag: MyPhotos
Include patterns: All files
Skip patterns: ['.git', '@eaDir']
Max depth: Unlimited
Check existing by: fullpath, volume

(With --verbose 1 or higher, you'll see:)
Processing: /media/photos/IMG_001.jpg
Processing: /media/photos/IMG_002.jpg
Skipping (already indexed by fullpath+volume): /media/photos/IMG_003.jpg
Processing: /media/photos/video.mp4
...

============================================================
Indexing complete!
Run timestamp: 2026-01-22T10:30:45.123456
Files processed: 150
Files skipped: 25

Skip reasons breakdown:
  - already_indexed (by fullpath+volume): 15
  - not_media_file (mime: text/plain): 5
  - matches_skip_pattern: 3
  - not_matching_include_pattern: 2

Duration: 45.23 seconds
Database: media.db
============================================================
```

The run timestamp allows you to query the `skipped_files` table to see exactly which files were skipped and why during this specific run.

## License

This script is provided under the same license as the rest of the repository.
