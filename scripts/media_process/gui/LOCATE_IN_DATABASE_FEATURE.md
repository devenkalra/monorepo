# Locate in Database Feature

## Overview
The "Locate in Database" feature allows you to find files in your media database by computing their hash and searching for matches. This is useful for:
- Finding duplicates
- Verifying if files are already indexed
- Locating files across different volumes
- Checking file existence and metadata

## How to Use

1. **Select Files**: Select one or more files in the file list
2. **Click "Locate in Database"**: Opens the Locate in Database dialog
3. **Configure Options**:
   - **Show metadata**: Display detailed information about matches (dimensions, date, location, etc.)
   - **Show file hash**: Display the SHA256 hash of each file
4. **Click "Start"**: Begins the search operation

## What It Does

For each selected file, the feature:
1. Calculates the SHA256 hash of the file
2. Searches the database for files with matching hashes
3. Categorizes results into three groups:
   - **Not Found**: Files not in the database
   - **Unique**: Files found exactly once in the database
   - **Duplicates**: Files found multiple times in the database

## Output Format

### Not Found Section
Lists files that are not in the database:
```
NOT FOUND IN DATABASE
--------------------------------------------------------------------------------
  /path/to/file.jpg
```

### Unique Files Section
Shows files found once with optional metadata:
```
UNIQUE FILES (Found once)
--------------------------------------------------------------------------------
  Candidate: /path/to/query_file.jpg
    Hash: abc123... (if show hash enabled)
    Match:
      /mnt/volume/indexed/path/file.jpg
        [Vol:MyVolume | Size:2.3 MB | ✓Exists | 4032x3024 | Date:2023-07-01 12:34:56 | Loc:San Francisco, CA]
```

### Duplicates Section
Shows files found multiple times:
```
DUPLICATES (Found multiple times)
--------------------------------------------------------------------------------
  Candidate: /path/to/query_file.jpg
    Hash: abc123... (if show hash enabled)
    Duplicates (3):
      /mnt/volume1/path/file.jpg
        [Vol:Volume1 | Size:2.3 MB | ✓Exists | 4032x3024 | Date:2023-07-01 12:34:56]
      /mnt/volume2/backup/file.jpg
        [Vol:Volume2 | Size:2.3 MB | ✗Missing | 4032x3024 | Date:2023-07-01 12:34:56]
      /mnt/volume3/archive/file.jpg
        [Vol:Volume3 | Size:2.3 MB | ✓Exists | 4032x3024 | Date:2023-07-01 12:34:56]
```

## Metadata Information

When "Show metadata" is enabled, the following information is displayed:

### For Images
- **Volume**: Database volume name
- **Size**: File size in human-readable format
- **Exists**: Whether the file currently exists at the indexed path (✓ or ✗)
- **Dimensions**: Width x Height in pixels
- **Date**: Date the photo was taken (from EXIF)
- **Location**: City and state (from EXIF GPS data)

### For Videos
- **Volume**: Database volume name
- **Size**: File size in human-readable format
- **Exists**: Whether the file currently exists at the indexed path (✓ or ✗)
- **Dimensions**: Width x Height in pixels
- **Duration**: Video length in minutes:seconds format

## Technical Details

### Hash Calculation
- Uses SHA256 algorithm for reliable file identification
- Reads files in 8KB chunks for memory efficiency
- Same hash calculation method used by the indexing system

### Database Queries
The feature queries these tables:
- `files`: Main file information (path, hash, size, dates, etc.)
- `image_metadata`: Image-specific metadata (dimensions, EXIF, GPS)
- `video_metadata`: Video-specific metadata (duration, codec, frame rate)

### Thread Safety
The search operation runs in a background thread to keep the UI responsive, especially when processing many files or large files.

## Use Cases

### Finding Duplicates
Select multiple files and locate them to see which ones have duplicates in the database.

### Verifying Backups
Check if files exist in the database and verify their physical existence on disk (✓Exists vs ✗Missing).

### Cross-Volume Search
Find where a file exists across multiple volumes or backup locations.

### Pre-Import Check
Before indexing new files, check if they're already in the database to avoid duplicate indexing.

## Implementation Notes

The feature is implemented directly in Python (not as a subprocess call to `locate_in_db.py`) for:
- Better integration with the GUI
- Real-time progress updates
- Thread-safe output display
- Consistent error handling

The code reuses the core logic from `locate_in_db.py` but adapts it for GUI display.
