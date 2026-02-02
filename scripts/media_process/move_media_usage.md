# move_media.py - Move Media Files and Update Database

## Overview

`move_media.py` moves media files to a new destination directory and updates the database with their new locations and metadata. This script is part of the media management suite and works with the database created by `index_media.py`.

## Purpose

- Move files to reorganize your media library
- Update database records with new file locations
- Re-index metadata after moving files
- Maintain database integrity during reorganization
- Handle filename conflicts automatically

## Features

- ✅ Move files to destination directory
- ✅ Update existing database records
- ✅ Insert new records for files not in database
- ✅ Re-extract metadata (EXIF, video info)
- ✅ Regenerate thumbnails
- ✅ Handle filename conflicts
- ✅ Dry-run mode for testing
- ✅ Verbose output for monitoring
- ✅ Transaction-based updates

## Requirements

- Python 3.6+
- SQLite3
- `media_utils.py` (shared utilities)
- `index_media.py` (for metadata extraction)
- Database created by `index_media.py`

## Installation

No installation needed. Ensure the script is executable:

```bash
chmod +x move_media.py
```

## Usage

### Basic Syntax

```bash
python3 move_media.py --files FILE1 [FILE2 ...] \
  --destination DEST_DIR \
  --volume VOLUME_TAG \
  --db-path DATABASE
```

### Required Parameters

- `--files FILE [FILE ...]`: Files to move (can specify multiple)
- `--destination DEST_DIR` or `--dest`: Destination directory
- `--volume VOLUME_TAG`: Volume identifier for the files
- `--db-path DATABASE` or `--db`: Path to media database

### Optional Parameters

- `--verbose LEVEL` or `-v`: Verbosity level (0-3, default: 1)
  - `0`: Quiet (only summary)
  - `1`: Normal (file names and status)
  - `2`: Detailed (operations and metadata)
  - `3`: Debug (full details)
- `--dry-run`: Preview what would be done without making changes

## Examples

### Example 1: Move Photos with Dry-Run

```bash
python3 move_media.py \
  --files /photos/temp/img1.jpg /photos/temp/img2.jpg \
  --destination /photos/2024/vacation \
  --volume Vacation2024 \
  --db-path media.db \
  --dry-run
```

**Output:**
```
======================================================================
Move Media Files
======================================================================
Files to move: 2
Destination: /photos/2024/vacation
Volume: Vacation2024
Database: media.db
Mode: DRY RUN (no changes will be made)

Processing: /photos/temp/img1.jpg
  [DRY RUN] Would move to: /photos/2024/vacation/img1.jpg
  Would be updated

Processing: /photos/temp/img2.jpg
  [DRY RUN] Would move to: /photos/2024/vacation/img2.jpg
  Would be inserted

======================================================================
Move complete!
Files moved: 2
  Database updated: 1
  Database inserted: 1
Errors: 0
Duration: 0.15 seconds

[DRY RUN] No actual changes were made
======================================================================
```

### Example 2: Move All JPGs from Directory

```bash
python3 move_media.py \
  --files /downloads/*.jpg \
  --destination /photos/archive \
  --volume Archive \
  --db-path media.db \
  --verbose 2
```

### Example 3: Move Files from List

```bash
# Create file list
cat > files_to_move.txt << EOF
/photos/old/photo1.jpg
/photos/old/photo2.jpg
/photos/old/video1.mp4
EOF

# Move files
python3 move_media.py \
  --files $(cat files_to_move.txt) \
  --destination /photos/organized \
  --volume MainLibrary \
  --db-path media.db
```

### Example 4: Reorganize Library with Verbose Output

```bash
python3 move_media.py \
  --files /old_location/*.jpg /old_location/*.mp4 \
  --destination /new_location/organized \
  --volume MainLibrary \
  --db-path media.db \
  --verbose 3
```

## How It Works

### Processing Flow

1. **Validate Input**
   - Check source files exist
   - Verify database exists
   - Create destination if needed

2. **For Each File**
   - Move file to destination
   - Handle filename conflicts
   - Update or insert database record
   - Extract metadata
   - Generate thumbnail

3. **Database Update**
   - Update existing records (change path)
   - Insert new records (not in database)
   - Store metadata
   - Commit transaction

### Filename Conflicts

If a file with the same name exists in the destination:

```
Original:  photo.jpg
Conflict:  photo_1.jpg
Another:   photo_2.jpg
...
```

### Database Behavior

**File Already in Database:**
- Updates existing record
- Changes `fullpath` to new location
- Updates `volume` tag
- Updates `modified_date`
- Updates `indexed_date`
- Re-extracts metadata
- Regenerates thumbnail

**File Not in Database:**
- Inserts new record
- Calculates file hash
- Extracts metadata
- Generates thumbnail
- Links to volume

## Verbosity Levels

### Level 0: Quiet
```
======================================================================
Move Media Files
======================================================================
Files to move: 5
Destination: /photos/archive
Volume: Archive
Database: media.db

======================================================================
Move complete!
Files moved: 5
  Database updated: 3
  Database inserted: 2
Errors: 0
Duration: 2.34 seconds
======================================================================
```

### Level 1: Normal (Default)
```
Processing: /photos/img1.jpg
  ✓ Updated

Processing: /photos/img2.jpg
  ✓ Inserted
```

### Level 2: Detailed
```
Processing: /photos/img1.jpg
  ✓ Moved to: /photos/archive/img1.jpg
  Updated database record (ID: 123)
  ✓ Updated
```

### Level 3: Debug
```
Processing: /photos/img1.jpg
  ✓ Moved to: /photos/archive/img1.jpg
  Updated database record (ID: 123)
  Stored image metadata
  Generated thumbnail
  ✓ Updated
```

## Metadata Processing

### For Images
- Raw EXIF data
- Camera and lens information
- Exposure settings
- GPS coordinates
- Date taken
- Keywords and captions
- Dimensions
- Thumbnail (200x200)

### For Videos
- Resolution (width x height)
- Duration
- Frame rate
- Video codec
- Audio channels
- Audio bit rate
- Thumbnail (from first frame)

## Safety Features

### Dry-Run Mode
Test before making changes:
```bash
python3 move_media.py --files *.jpg --destination /archive \
  --volume Archive --db-path media.db --dry-run
```

### Transaction-Based
All database changes are committed together. If an error occurs, previous changes are preserved.

### Error Handling
- Continues processing on individual file errors
- Reports errors in summary
- Non-zero exit code if errors occurred

### Filename Conflict Resolution
Automatically renames files to avoid overwrites.

## Integration with Other Scripts

### Works With

**index_media.py**
- Creates the database
- Same schema and tables
- Compatible metadata format

**manage_dupes.py**
- Uses same database
- Can move files after deduplication

**remove_dupes.py**
- Uses same database
- Can reorganize after cleanup

### Database Schema

Uses the same tables as `index_media.py`:
- `files`: Main file records
- `image_metadata`: EXIF data for images
- `video_metadata`: Video information
- `thumbnails`: Thumbnail images

## Common Workflows

### Workflow 1: Reorganize Library

```bash
# 1. Backup database
cp media.db media.db.backup

# 2. Test with dry-run
python3 move_media.py --files /old/*.jpg \
  --destination /new/organized \
  --volume MainLibrary \
  --db-path media.db \
  --dry-run

# 3. Execute move
python3 move_media.py --files /old/*.jpg \
  --destination /new/organized \
  --volume MainLibrary \
  --db-path media.db

# 4. Verify
sqlite3 media.db "SELECT fullpath FROM files WHERE volume='MainLibrary' LIMIT 5"
```

### Workflow 2: Archive Old Media

```bash
# Move files from 2020 to archive
python3 move_media.py \
  --files /photos/2020/**/*.jpg \
  --destination /archive/2020 \
  --volume Archive2020 \
  --db-path media.db \
  --verbose 2
```

### Workflow 3: Consolidate Scattered Files

```bash
# Create list of files to consolidate
find /scattered -name "*.jpg" > files.txt

# Move all to one location
python3 move_media.py \
  --files $(cat files.txt) \
  --destination /consolidated \
  --volume Consolidated \
  --db-path media.db
```

## Troubleshooting

### Database file does not exist
**Problem:** Database not found at specified path.

**Solution:**
```bash
# Create database first with index_media.py
python3 index_media.py --path /photos --start-dir . \
  --volume MainLibrary --db-path media.db
```

### Source file not found
**Problem:** File doesn't exist at source path.

**Solution:**
- Check file paths (use absolute paths)
- Verify files exist: `ls -l /path/to/file.jpg`
- Check for typos

### Failed to move file
**Problem:** Cannot move file to destination.

**Solution:**
- Check permissions: `ls -ld /destination`
- Check disk space: `df -h /destination`
- Verify destination path exists or can be created

### Database update failed
**Problem:** Cannot update database.

**Solution:**
- Check database permissions: `ls -l media.db`
- Ensure database not locked (close other connections)
- Check disk space: `df -h .`

## Best Practices

1. **Always Backup**
   ```bash
   cp media.db media.db.backup
   ```

2. **Test First**
   ```bash
   # Use --dry-run before actual move
   python3 move_media.py --files *.jpg --dest /new \
     --volume Vol --db media.db --dry-run
   ```

3. **Use Absolute Paths**
   ```bash
   # More reliable
   --files /home/user/photos/img.jpg
   # Less reliable
   --files ../photos/img.jpg
   ```

4. **Monitor Progress**
   ```bash
   # Use verbose mode for large operations
   python3 move_media.py --files *.jpg --dest /new \
     --volume Vol --db media.db --verbose 2
   ```

5. **Verify After Move**
   ```bash
   # Check a few files
   ls -l /destination/
   sqlite3 media.db "SELECT * FROM files WHERE volume='Vol' LIMIT 5"
   ```

## Exit Codes

- `0`: Success (all files moved)
- `1`: Errors occurred (some files failed)

## Notes

- Files are **moved** (not copied) - original location is emptied
- Metadata is re-extracted from moved files
- Thumbnails are regenerated
- File hash is preserved (not recalculated)
- Database maintains file history through updates
- Compatible with all media management scripts

## See Also

- `index_media.py` - Index media files into database
- `manage_dupes.py` - Find and manage duplicate files
- `remove_dupes.py` - Remove duplicates from database
- `media_utils.py` - Shared utility functions
