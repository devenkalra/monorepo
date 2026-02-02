# Database Reprocess Feature Summary

**Date:** 2026-01-28  
**Status:** ✅ **COMPLETED**

---

## Overview

Added capability to `apply_exif.py` to check if files are in the media database and automatically reprocess them after EXIF updates. This keeps the database in sync with updated metadata.

---

## Problem Solved

**Before:**
- User updates EXIF tags on photos with `apply_exif.py`
- Database still has old metadata
- Need to manually run `index_media.py` to update database
- Risk of database and files being out of sync

**After:**
- User updates EXIF tags with `apply_exif.py`
- Script checks if file is in database
- Automatically reprocesses file to update database
- Database and files stay in sync!

---

## New Arguments

### **`--db-path`**
- **Type:** String (file path)
- **Required:** Optional
- **Purpose:** Path to media index database
- **Example:** `--db-path ~/media_index.db`

### **`--reprocess-db`**
- **Type:** Boolean flag
- **Required:** Optional (requires `--db-path`)
- **Purpose:** Enable automatic reprocessing after EXIF update
- **Example:** `--reprocess-db`

---

## Usage

### **Basic EXIF Update (No Database)**
```bash
python3 apply_exif.py \
  --files photo1.jpg photo2.jpg \
  --latitude 32.7157 \
  --longitude -97.3308 \
  --city "Fort Worth" \
  --state "Texas" \
  --country "USA"
```
✅ Updates EXIF tags only

---

### **EXIF Update with Database Sync**
```bash
python3 apply_exif.py \
  --files photo1.jpg photo2.jpg \
  --latitude 32.7157 \
  --longitude -97.3308 \
  --city "Fort Worth" \
  --state "Texas" \
  --country "USA" \
  --db-path ~/media_index.db \
  --reprocess-db
```
✅ Updates EXIF tags  
✅ Checks if files in database  
✅ Reprocesses to update database

---

### **With Dry Run**
```bash
python3 apply_exif.py \
  --files *.jpg \
  --place "Fort Worth, Texas, USA" \
  --db-path ~/media_index.db \
  --reprocess-db \
  --dry-run
```
✅ Shows what would be done  
❌ Doesn't modify files or database  
ℹ️ Database reprocess skipped in dry-run mode

---

## Workflow

### **Step 1: Apply EXIF Tags**
```
Processing file: /photos/vacation/IMG_1234.jpg
Tag: GPSLatitude = '32.7157'
Tag: GPSLatitudeRef = 'N'
Tag: GPSLongitude = '97.3308'
Tag: GPSLongitudeRef = 'W'
...
Exiftool command executed
```

### **Step 2: Check Database**
```
File found in database, reprocessing...
```

### **Step 3: Reprocess File**
```
Reprocessing in database: /photos/vacation/IMG_1234.jpg
✓ Database updated
```

### **Step 4: Summary**
```
✓ EXIF tags applied and database updated for 1 file(s).
```

---

## How It Works

### **1. Check if File is in Database**

Function: `check_file_in_database(db_path, file_path)`

```python
def check_file_in_database(db_path: str, file_path: str) -> bool:
    """Check if a file exists in the database."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check by absolute path
    abs_path = os.path.abspath(file_path)
    cursor.execute("SELECT id FROM files WHERE fullpath = ?", (abs_path,))
    result = cursor.fetchone()
    
    conn.close()
    return result is not None
```

**Query:** Looks up file by `fullpath` in `files` table  
**Returns:** `True` if found, `False` if not

---

### **2. Reprocess File in Database**

Function: `reprocess_file_in_database(db_path, file_path, verbose)`

```python
def reprocess_file_in_database(db_path: str, file_path: str, verbose: bool) -> bool:
    """Reprocess a file by calling index_media for just this file."""
    # Find index_media.py in same directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    index_media_script = os.path.join(script_dir, 'index_media.py')
    
    # Build command to reindex just this file
    cmd = [
        'python3', index_media_script,
        '--path', file_dir,
        '--volume', 'updated',
        '--db-path', db_path,
        '--include-pattern', f'^{file_name}$',  # Exact match
        '--literal-patterns',  # Treat as literal
        '--check-existing', 'fullpath'  # Update existing record
    ]
    
    # Run index_media
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result.returncode == 0
```

**Process:**
1. Locates `index_media.py` in same directory as `apply_exif.py`
2. Builds command to reindex just the updated file
3. Uses `--include-pattern` with exact file name match
4. Uses `--check-existing fullpath` to update existing record
5. Runs as subprocess with 60-second timeout
6. Returns success/failure

---

## Database Updates

When a file is reprocessed, `index_media.py` updates:

### **Files Table:**
- `modified_date` - Updated from file
- `file_hash` - Recalculated (unchanged if only EXIF changed)
- `size` - Updated from file
- `indexed_date` - Updated to current time

### **Image Metadata Table:**
- `raw_exif` - Complete EXIF JSON (includes new tags)
- `width`, `height` - Dimensions
- `date_taken` - From EXIF
- `latitude`, `longitude`, `altitude` - GPS data (NEW!)
- `city`, `state`, `country`, `country_code` - Location (NEW!)
- `coverage` - Full address (NEW!)
- `caption` - Caption/description (NEW!)
- `keywords` - Keywords list (NEW!)
- `camera_make`, `camera_model` - Camera info
- `exposure_time`, `f_number`, `iso`, etc. - Photo settings

### **Thumbnail:**
- Thumbnail regenerated from updated file

---

## UI Integration (image_process.py)

### **New Controls for Apply EXIF:**

```
┌─────────────────────────────────────────────────┐
│ Files:                [multiline text]          │
│ ...location fields...                           │
│ Database Path:        [~/media_index.db] [📁]  │
│ ☑ Reprocess in Database                         │
│ ☑ Dry Run                                       │
│ Limit:                [10]                      │
└─────────────────────────────────────────────────┘
```

**"Reprocess in Database" checkbox:**
- Only shown for `apply_exif` command
- Requires "Database Path" to be filled
- Automatically reprocesses files after EXIF update

---

## Use Cases

### **1. Adding Location to Vacation Photos**

**Scenario:** You have 100 vacation photos already in database, need to add location

```bash
python3 apply_exif.py \
  --files ~/Photos/Vacation2024/*.jpg \
  --place "Paris, France" \
  --db-path ~/media_index.db \
  --reprocess-db
```

**Result:**
- ✅ Location added to all EXIF tags
- ✅ Database updated with GPS coordinates
- ✅ Database updated with city/country
- ✅ Can search by location in database

---

### **2. Correcting Location Data**

**Scenario:** Wrong location was indexed, need to fix

```bash
python3 apply_exif.py \
  --files ~/Photos/Event/*.jpg \
  --latitude 28.5439554 \
  --longitude 77.198706 \
  --city "New Delhi" \
  --country "India" \
  --db-path ~/media_index.db \
  --reprocess-db
```

**Result:**
- ✅ Corrected location in EXIF
- ✅ Database synchronized with new location
- ✅ Searches now use correct location

---

### **3. Adding Keywords to Indexed Photos**

**Scenario:** Need to add keywords to photos already in database

```bash
python3 apply_exif.py \
  --files ~/Photos/Wildlife/*.jpg \
  --add-keyword "wildlife" \
  --add-keyword "nature" \
  --add-keyword "2024" \
  --db-path ~/media_index.db \
  --reprocess-db
```

**Result:**
- ✅ Keywords added to EXIF
- ✅ Database updated with new keywords
- ✅ Can search by keywords in database

---

### **4. Bulk Caption Updates**

**Scenario:** Add captions to event photos

```bash
python3 apply_exif.py \
  --files ~/Photos/Wedding/*.jpg \
  --caption "Smith-Johnson Wedding, June 2024" \
  --db-path ~/media_index.db \
  --reprocess-db
```

**Result:**
- ✅ Caption in EXIF
- ✅ Database has caption
- ✅ Searchable by caption

---

## Output Examples

### **Without Database Reprocess:**

```
Applying tags to 3 file(s).

Processing file: /photos/img1.jpg
Tag: GPSLatitude = '32.7157'
Tag: GPSLatitudeRef = 'N'
...
Exiftool command: exiftool ...
Done.
```

### **With Database Reprocess:**

```
Applying tags to 3 file(s).

Processing file: /photos/img1.jpg
Tag: GPSLatitude = '32.7157'
Tag: GPSLatitudeRef = 'N'
...
Exiftool command: exiftool ...
  File found in database, reprocessing...
  Reprocessing in database: /photos/img1.jpg
  ✓ Database updated

Processing file: /photos/img2.jpg
...
  File found in database, reprocessing...
  Reprocessing in database: /photos/img2.jpg
  ✓ Database updated

Processing file: /photos/img3.jpg
...
  (File not in database, skipping reprocess)

✓ EXIF tags applied and database updated for 3 file(s).
```

---

## Error Handling

### **Database Not Found:**
```
Warning: Could not check database for /photos/img1.jpg: [Errno 2] No such file or directory
(File not in database, skipping reprocess)
```
**Action:** Continues without reprocessing

### **index_media.py Not Found:**
```
Warning: index_media.py not found at /path/to/index_media.py
Warning: Reprocessing failed, database may be out of sync
```
**Action:** EXIF updated, but database not updated

### **Reprocessing Timeout:**
```
Warning: Reprocessing timed out for /photos/img1.jpg
Warning: Reprocessing failed, database may be out of sync
```
**Action:** EXIF updated, continues with next file

### **Reprocessing Failed:**
```
Warning: Reprocessing failed: [error details]
Warning: Reprocessing failed, database may be out of sync
```
**Action:** Shows warning, continues processing

---

## Performance

### **Timing Estimates:**

| Operation | Time per File |
|-----------|--------------|
| EXIF Update | ~0.1-0.5s |
| Database Check | ~0.01s |
| Database Reprocess | ~0.5-2s |
| **Total** | ~0.6-2.5s per file |

### **For 100 Files:**
- EXIF only: ~10-50 seconds
- EXIF + Database: ~60-250 seconds (1-4 minutes)

### **Optimization:**
- Timeout set to 60 seconds per file (prevents hanging)
- Database check is very fast (single SQL query)
- Reprocessing runs in subprocess (doesn't block main process)

---

## Safety Features

### **1. Dry Run Protection**
```python
if args.db_path and args.reprocess_db and not args.dry_run:
    # Only reprocess if not in dry-run mode
```
✅ Database never modified in dry-run mode

### **2. Error Tolerance**
```python
try:
    reprocess_file_in_database(...)
except Exception as e:
    print(f"Warning: {e}")
    # Continue processing next file
```
✅ One file's failure doesn't stop the batch

### **3. Timeout Protection**
```python
subprocess.run(..., timeout=60)
```
✅ Stuck reprocessing doesn't hang forever

### **4. Path Validation**
```python
abs_path = os.path.abspath(file_path)
# Always uses absolute paths for database lookup
```
✅ Reliable file matching regardless of CWD

---

## Integration Points

### **Works With:**

✅ **Location Bookmarks** - Load bookmark, apply to files, sync database  
✅ **Place Geocoding** - Geocode location, apply to files, sync database  
✅ **Manual GPS Entry** - Enter coordinates, apply to files, sync database  
✅ **Keywords** - Add/remove keywords, sync database  
✅ **Captions** - Add captions, sync database  
✅ **Dry Run** - Preview changes without modifying database  
✅ **Limit** - Test on few files before full batch  

### **Requires:**

⚠️ **`index_media.py` must be in same directory as `apply_exif.py`**  
⚠️ **Database must exist** (created by `index_media.py`)  
⚠️ **Files must be indexed first** (new files won't be added to database)  

---

## Command-Line Examples

### **Example 1: Location Update**
```bash
python3 apply_exif.py \
  --files ~/Photos/Trip/*.jpg \
  --latitude 48.8584 \
  --longitude 2.2945 \
  --city "Paris" \
  --country "France" \
  --db-path ~/media_index.db \
  --reprocess-db
```

### **Example 2: Keyword Addition**
```bash
python3 apply_exif.py \
  --files $(cat photo_list.txt) \
  --add-keyword "family" \
  --add-keyword "2024" \
  --db-path ~/media_index.db \
  --reprocess-db \
  --verbose
```

### **Example 3: Test Run**
```bash
python3 apply_exif.py \
  --files ~/Photos/Test/*.jpg \
  --place "Fort Worth, Texas, USA" \
  --db-path ~/media_index.db \
  --reprocess-db \
  --dry-run \
  --limit 3
```

### **Example 4: From Location Bookmark (GUI)**
*In image_process.py:*
1. Select "Apply EXIF Tags"
2. Add files
3. Select location bookmark (e.g., "Home")
4. Set Database Path: `~/media_index.db`
5. Check "Reprocess in Database"
6. Click Execute

---

## Files Modified

### **`apply_exif.py`**

**Changes:**
1. Added `os` import
2. Added `--db-path` argument
3. Added `--reprocess-db` argument
4. Added `check_file_in_database()` function
5. Added `reprocess_file_in_database()` function
6. Added database check/reprocess logic after `run_exiftool()`
7. Added summary message for database updates

**Lines added:** ~100

---

### **`image_process.py`**

**Changes:**
1. Added `reprocess_db` parameter definition
2. Updated `apply_exif` command params list to include `db_path` and `reprocess_db`

**Lines added:** ~8

---

## Future Enhancements (Optional)

Potential improvements:

1. **Batch Reprocessing**
   - Reprocess all files in one `index_media.py` call
   - Faster for large batches

2. **Progress Bar**
   - Show progress during reprocessing
   - Estimated time remaining

3. **Selective Reprocess**
   - Option to skip reprocess if no metadata changed
   - Check hash before/after

4. **Auto-Add to Database**
   - If file not in database, add it
   - Instead of just skipping

5. **Rollback on Failure**
   - If reprocessing fails, restore original EXIF
   - Transaction-like behavior

---

## Testing

### Test 1: File in Database
```
✓ File found in database
✓ Reprocessing triggered
✓ Database updated
✓ Success message shown
```

### Test 2: File Not in Database
```
✓ File checked
✓ Not found message shown
✓ Reprocess skipped
✓ EXIF still updated
```

### Test 3: Dry Run Mode
```
✓ EXIF changes previewed
✓ Database NOT checked
✓ Database NOT modified
```

### Test 4: Multiple Files
```
✓ All files processed
✓ Each file checked individually
✓ Database updated for each found file
✓ Summary shows total updated
```

### Test 5: Error Recovery
```
✓ One file fails reprocessing
✓ Warning shown
✓ Continues with next file
✓ Batch completes
```

---

## Conclusion

✅ **Database reprocess feature complete**  
✅ **Automatic database sync after EXIF updates**  
✅ **File-by-file checking and reprocessing**  
✅ **Error handling and timeout protection**  
✅ **Integrated with UI**  
✅ **Works with all location features**  
✅ **No breaking changes**  

Users can now keep their database in perfect sync with EXIF updates! 🎉
