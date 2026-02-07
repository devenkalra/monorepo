# Move Media Files Feature

## Overview
The "Move Media Files" feature allows you to move selected files to a new destination directory while automatically updating the media database with the new file locations. This is useful for:
- Reorganizing your media library
- Moving files to different storage volumes
- Consolidating files from multiple locations
- Archiving files to new locations while maintaining database integrity

## How to Use

1. **Select Files**: Select one or more files in the file list
2. **Click "Move Media Files"**: Opens the Move Media Files dialog
3. **Configure Options**:
   - **Destination**: Browse to or enter the destination directory path
   - **Volume**: Specify the volume name (e.g., "MediaLibrary", "Backup2024")
   - **Dry run**: Enable to preview what would happen without making actual changes
4. **Click "Start"**: Begins the move operation

## What It Does

For each selected file, the feature:
1. Validates that the source file exists
2. Calculates the file hash (SHA256) for duplicate detection
3. Checks if the file already exists at the destination
4. Moves the file to the destination directory
5. Updates or inserts the database record with the new location
6. Handles filename conflicts by adding a counter (e.g., `photo_1.jpg`, `photo_2.jpg`)

## Database Operations

### Update vs Insert
The feature intelligently handles database records:

- **Update**: If the file's original path exists in the database, the record is updated with:
  - New file path
  - New volume name
  - Updated modified date
  - New indexed date

- **Insert**: If the file's original path is NOT in the database, a new record is created with:
  - File path, name, volume
  - File size, MIME type, extension
  - File hash (SHA256)
  - Created and modified dates
  - Indexed date

## Duplicate Detection

The feature includes several safety checks:

### Destination File Exists
If a file with the same name already exists at the destination:
- Calculates hash of destination file
- If hashes match: Skips the move (file already there)
- If hashes differ: Generates unique filename with counter

### Database Exists Check
If the destination path already exists in the database:
- Compares file hashes
- If hashes match: Skips the move (already indexed)
- Prevents duplicate database entries for the same file

## Output Format

### Per-File Output
```
Processing: /path/to/source/photo.jpg
  ✓ Moved to: /destination/path/photo.jpg
  Updated database record (ID: 12345)
  ✓ Updated
```

### Skipped Files
```
Processing: /path/to/photo.jpg
  Skipping: File already exists in destination with same content
```

### Errors
```
Processing: /path/to/photo.jpg
  ✗ Source file not found
```

### Summary
```
================================================================================
Move complete!
Files moved: 15
  Database updated: 12
  Database inserted: 3
Files skipped: 2
  Destination Exists Same Hash: 1
  Db Exact Match: 1
Errors: 0
[DRY RUN] No actual changes were made
================================================================================
```

## Dry Run Mode

When "Dry run" is enabled:
- Shows what would be moved without making changes
- Displays destination paths
- Shows database operations that would occur
- No files are actually moved
- No database changes are committed
- Useful for:
  - Testing move operations
  - Previewing results
  - Verifying destination paths
  - Planning reorganizations

## Volume Names

The volume parameter is a logical tag for organizing files:
- Can be any descriptive name (e.g., "MainLibrary", "Travel2024", "Backup")
- Used to filter and search files in the database
- Allows tracking which storage location/backup contains which files
- Helps identify file locations when managing multiple storage devices

## File Handling

### Filename Conflicts
If a file with the same name exists at the destination:
1. Checks if content is identical (by hash)
2. If identical: Skips move
3. If different: Appends counter to filename
   - `photo.jpg` → `photo_1.jpg` → `photo_2.jpg`, etc.

### Directory Creation
- Destination directory is created automatically if it doesn't exist
- Parent directories are created as needed
- In dry-run mode, directory is not created

### Error Handling
Common errors and how they're handled:
- **Source not found**: Skips file, logs error
- **Permission denied**: Reports error, continues with other files
- **Hash calculation failed**: Skips file, logs error
- **Database error**: Rolls back transaction, reports error

## Use Cases

### Reorganizing Library
Move files from temporary locations to organized permanent storage:
- Source: `/Downloads/vacation_photos/`
- Destination: `/media/photos/2024/vacation/`
- Volume: `MainLibrary`

### Creating Backups
Move or copy files to backup location:
- Source: Current working directory
- Destination: `/backup/photos/2024/`
- Volume: `Backup2024`

### Consolidating Collections
Merge files from multiple locations:
- Move files from various folders to unified location
- Database tracks all moves
- Duplicate detection prevents redundancy

### Volume Migration
Move files between storage devices:
- Source: Files on old drive
- Destination: New drive location
- Volume: Update to new volume name
- Database maintains continuity

## Technical Details

### Database Schema
The feature updates/inserts into the `files` table:
```sql
- id: Auto-incrementing primary key
- volume: Volume tag
- fullpath: Complete file path
- name: Filename
- created_date: File creation date (ISO format)
- modified_date: File modification date (ISO format)
- size: File size in bytes
- mime_type: MIME type (e.g., image/jpeg)
- extension: File extension (e.g., .jpg)
- file_hash: SHA256 hash
- indexed_date: When record was created/updated (ISO format)
```

### Thread Safety
- Move operations run in background thread
- UI remains responsive during moves
- Output updates are thread-safe using `after()`
- Database commits happen in worker thread

### Transaction Handling
- All database changes are part of single transaction
- Changes committed only after all files processed
- If error occurs, can be rolled back
- Dry-run mode prevents commits

## Implementation Notes

The feature is implemented directly in Python (not as a subprocess call to `move_media.py`) for:
- Better GUI integration
- Real-time progress updates
- Thread-safe operation
- Consistent error handling
- No dependency on external scripts

The implementation reuses core logic from `move_media.py` but adapts it for GUI display and interaction.

## Differences from Command-Line Script

Compared to `move_media.py`, the GUI version:
- ✅ Provides real-time visual feedback
- ✅ Runs in background thread (non-blocking)
- ✅ Allows interactive configuration
- ❌ Does NOT process EXIF metadata (simplified)
- ❌ Does NOT generate thumbnails (simplified)
- ❌ Does NOT create audit logs
- ✅ Simpler but sufficient for most use cases

For advanced features like metadata extraction and audit logging, use the command-line `move_media.py` script directly.
