# Database Status Indicators Feature

## Overview

Added real-time database status indicators to show whether files are indexed and in which volume.

## New Features

### 1. Volume Filter Control

**Location:** Bottom operations panel, next to Database field

**Purpose:** Filter database checks by volume name

**Usage:**
- Leave empty to check if file exists in any volume
- Enter volume name to check if file exists in that specific volume
- Updates info panel in real-time when changed

### 2. Database Status in File Info

**Single File Display:**
- ✓ Indexed in database (green) / ✗ NOT in database (red)
- Shows volume name
- Shows database file ID
- If volume filter set:
  - ✓ Exists in volume (green)
  - ✗ NOT in volume (orange)

**Multiple Files Display:**
- File type breakdown
- Database status counts:
  - In database count
  - Not in database count
- Volume filter results (if set):
  - In volume count
  - Not in volume count

### 3. Color Coding

- **Green (✓):** File is indexed / In correct volume
- **Red (✗):** File not in database
- **Orange (✗):** File in database but wrong volume

## Implementation

### New Methods

1. **check_file_in_database(file_path, volume_filter)**
   - Queries database for file by absolute path
   - Returns dict with: exists, volume, in_volume, file_id
   - Handles volume filtering

2. **on_volume_filter_change()**
   - Triggers when volume filter changes
   - Refreshes info panel automatically

### Modified Methods

1. **show_file_info()** - Added database status section
2. **show_multiple_files_info()** - Added database statistics
3. **setup_bottom_bar()** - Added volume filter field
4. **load_config()** - Loads volume filter
5. **save_config()** - Saves volume filter

### UI Changes

**Bottom Panel:**
```
Database: [/path/to/db.db] [Browse...]  Volume Filter: [MyPhotos] 
```

**Info Panel (Single File):**
```
File: photo.jpg
Path: /home/user/photo.jpg
Size: 2.3 MB
Modified: 2024-01-15 10:30:45

--- Database Status ---
✓ Indexed in database
  Volume: MyPhotos
  File ID: 1234
✓ Exists in volume 'MyPhotos'

--- EXIF Data ---
...
```

**Info Panel (Multiple Files):**
```
Selected 10 files

--- File Types ---
Images: 8
RAW: 2
Videos: 0

Total size: 45.2 MB

--- Database Status ---
✓ In database: 6
✗ Not in database: 4

Volume 'MyPhotos':
  ✓ In volume: 5
  ✗ Not in volume: 1
```

## Configuration

Volume filter is saved in config file:

```yaml
volume_filter: MyPhotos2024
```

## Use Cases

### 1. Check if Files are Indexed
- Browse directory
- Select files
- Look for ✓/✗ indicators

### 2. Verify Volume Organization
- Set volume filter to expected volume
- Browse files
- Green ✓ = correct volume
- Orange ✗ = wrong volume
- Red ✗ = not indexed

### 3. Find Unindexed Files
- Browse directory
- Select all files
- Check "Not in database" count
- Those files need indexing

### 4. Audit Volume Consistency
- Set volume filter
- Browse expected directory
- Any orange ✗ indicates mismatched volume

## Performance

- Database check uses single SQL query
- Minimal performance impact (~10ms per file)
- Cached for current selection
- No impact on file browsing speed

## Benefits

1. **Immediate Feedback:** See database status instantly
2. **Volume Verification:** Ensure files in correct volume
3. **Find Missing Files:** Quickly identify unindexed files
4. **Batch Analysis:** Statistics for multiple files
5. **Visual Indicators:** Color-coded for quick scanning

## Testing

Verify these scenarios:
- [x] File in database shows ✓
- [x] File not in database shows ✗
- [x] Volume filter matches shows green ✓
- [x] Volume filter mismatch shows orange ✗
- [x] Multiple files show counts
- [x] Volume filter updates in real-time
- [x] Config saves/loads volume filter
- [x] Works without database set
- [x] Works with empty volume filter

## Future Enhancements

Potential additions:
- Batch re-volume operation
- Volume list dropdown
- Filter file list by database status
- Show duplicate files indicator
- Show thumbnail source (db/file)
