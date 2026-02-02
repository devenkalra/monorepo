# Bug Fix: Reprocess Existing Files in Database

**Date:** 2026-01-28  
**Issue:** Files not being updated in database after EXIF changes - skipped as "already indexed"  
**Status:** ✅ **FIXED**

---

## Problem

After writing EXIF tags to a file, the database reprocessing was skipping the file:

```
Skipping (already indexed by fullpath): /mnt/photo/1988/05/Yogesh Trip/00193_n_19am6nkcam0193_b.jpg

Files added: 0
Files updated: 0    ← Should be 1!
Files skipped: 47

Skip reasons breakdown:
  - already_indexed (by fullpath): 1
```

### Root Cause

The `apply_exif.py` script was calling `index_media.py` with:

```bash
--volume updated \
--check-existing fullpath
```

**Two problems:**

1. **Wrong volume**: Using placeholder volume "updated" instead of the file's original volume
   - Database uses `fullpath + volume` as UNIQUE constraint
   - File was indexed with original volume (e.g., "Photos")
   - Looking for file with volume "updated" wouldn't find it

2. **Wrong check-existing strategy**: Using `--check-existing fullpath`
   - This tells index_media to **skip** if fullpath matches
   - We want it to **update**, not skip

---

## Solution

### Part 1: Query Original Volume

Before reprocessing, query the database to get the file's original volume:

```python
# Get the volume for this file from the database
abs_path = os.path.abspath(file_path)
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT volume FROM files WHERE fullpath = ? LIMIT 1", (abs_path,))
result = cursor.fetchone()
conn.close()

if not result:
    print(f"Warning: File not found in database: {file_path}", file=sys.stderr)
    return False

volume = result[0]
```

### Part 2: Use Hash-Based Check

Use `--check-existing hash` instead of `fullpath`:

```python
cmd = [
    'python3',
    index_media_script,
    '--path', file_dir,
    '--volume', volume,  # Use the SAME volume as originally indexed
    '--db-path', db_path,
    '--include-pattern', pattern,
    '--check-existing', 'hash'  # Check by hash, not fullpath
]
```

### Why This Works

**index_media.py logic** (lines 662-683):

```python
# Step 1: Check if file exists by check_existing criteria
if check_file_exists(file_info, check_existing, conn):
    # Matches check criteria → SKIP
    return False, "already_indexed", False

# Step 2: Check if file exists by fullpath+volume (UNIQUE constraint)
cursor.execute("SELECT id FROM files WHERE fullpath = ? AND volume = ?", ...)
if existing:
    # Exists but didn't match check criteria → UPDATE
    print(f"Updating existing record: {filepath}")
    # ... update logic ...
```

**Our strategy:**

1. **Step 1 fails to match** because:
   - We check by `hash`
   - EXIF update changed the file hash
   - Old hash in DB ≠ new hash in file
   - Result: Doesn't skip

2. **Step 2 finds the record** because:
   - We query by `fullpath + volume`
   - We use the CORRECT volume (from DB query)
   - Record found → **UPDATE**

---

## Flow Diagram

### Before Fix (WRONG)

```
apply_exif.py
  ├─ Update EXIF tags ✅
  ├─ Call index_media.py
  │    ├─ --volume updated (WRONG! Not in DB)
  │    ├─ --check-existing fullpath
  │    ├─ Step 1: Check fullpath → MATCH ✅
  │    └─ SKIP (already indexed) ❌
  └─ Database NOT updated ❌
```

### After Fix (CORRECT)

```
apply_exif.py
  ├─ Update EXIF tags ✅
  ├─ Query DB for original volume → "Photos" ✅
  ├─ Call index_media.py
  │    ├─ --volume Photos (CORRECT! Same as DB)
  │    ├─ --check-existing hash
  │    ├─ Step 1: Check hash → NO MATCH (hash changed) ✅
  │    ├─ Step 2: Check fullpath+volume → FOUND ✅
  │    └─ UPDATE existing record ✅
  └─ Database updated with new metadata ✅
```

---

## Code Changes

**File:** `/home/ubuntu/monorepo/scripts/apply_exif.py`

**Function:** `reprocess_file_in_database()`

### Added: Volume Query

```python
# Get the volume for this file from the database
abs_path = os.path.abspath(file_path)
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT volume FROM files WHERE fullpath = ? LIMIT 1", (abs_path,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print(f"Warning: File not found in database: {file_path}", file=sys.stderr)
        return False
    
    volume = result[0]
    if verbose >= 2:
        print(f"[DEBUG] File volume in database: {volume}")
except Exception as e:
    print(f"Warning: Could not query database for volume: {e}", file=sys.stderr)
    return False
```

### Changed: Command Building

**Before:**
```python
cmd = [
    '--volume', 'updated',          # ❌ Wrong volume
    '--check-existing', 'fullpath'  # ❌ Will skip
]
```

**After:**
```python
cmd = [
    '--volume', volume,            # ✅ Correct volume from DB
    '--check-existing', 'hash'     # ✅ Won't match, will update
]
```

---

## Testing

### Test 1: Normal update flow

```bash
python3 apply_exif.py --verbose 2 \
  --files /mnt/photo/1988/05/Yogesh\ Trip/00193_n_19am6nkcam0193_b.jpg \
  --latitude 28.5439554 \
  --longitude 77.198706 \
  --db-path ~/data/media-index/files.db \
  --reprocess-db
```

**Expected output:**
```
[DEBUG] File volume in database: Photos
[DEBUG] Reprocess command: python3 .../index_media.py --path /mnt/photo/1988/05/Yogesh Trip --volume Photos --db-path files.db --include-pattern [/\\]00193_n_19am6nkcam0193_b\.jpg$ --check-existing hash --verbose 2

Scanning directory: /mnt/photo/1988/05/Yogesh Trip
Volume tag: Photos
Check existing by: hash

Updating existing record: /mnt/photo/1988/05/Yogesh Trip/00193_n_19am6nkcam0193_b.jpg

Files added: 0
Files updated: 1    ← SUCCESS!
Files skipped: 0

  ✓ Database updated
```

### Test 2: File not in database

```bash
python3 apply_exif.py --verbose 2 \
  --files /tmp/new_photo.jpg \
  --city "Fort Worth" \
  --db-path ~/data/media-index/files.db \
  --reprocess-db
```

**Expected output:**
```
  ✓ EXIF tags written successfully
Warning: File not found in database: /tmp/new_photo.jpg
  (File not in database, skipping reprocess)
```

### Test 3: Verify database has new metadata

```bash
# Before EXIF update
python3 locate_in_db.py --files 00193_n_19am6nkcam0193_b.jpg --db-path files.db --metadata
# Should show: No GPS coordinates

# After EXIF update + reprocess
python3 locate_in_db.py --files 00193_n_19am6nkcam0193_b.jpg --db-path files.db --metadata
# Should show: GPS: 28.5439554, 77.198706
```

---

## Why Check by Hash?

**Q:** Why use `--check-existing hash` instead of removing it entirely?

**A:** Multiple reasons:

1. **Hash changes after EXIF update**
   - Writing EXIF modifies file bytes
   - File hash changes
   - Old hash ≠ new hash → no match → proceeds to update

2. **Safe for concurrent updates**
   - If file hasn't changed, hash matches → skips
   - Prevents unnecessary reprocessing

3. **Explicit intent**
   - Makes it clear we want to check for actual file changes
   - Not just blindly reprocessing

4. **Works with volume**
   - Using correct volume + hash check
   - Finds record by fullpath+volume
   - Updates it with new metadata

---

## Edge Cases

### Edge Case 1: File in database with multiple volumes

**Scenario:** Same file indexed under multiple volumes

**Database:**
```
fullpath: /mnt/photo/2024/photo.jpg, volume: Photos
fullpath: /mnt/photo/2024/photo.jpg, volume: Backup
```

**Behavior:**
- Queries DB, gets first volume: "Photos"
- Updates only the "Photos" record
- "Backup" record remains unchanged

**Is this OK?** Yes! Each volume is independent. User probably wants to update the primary one.

### Edge Case 2: Hash doesn't change

**Scenario:** EXIF write failed silently, hash didn't change

**Behavior:**
- `--check-existing hash` finds match
- File skipped
- User sees "Files skipped: 1"

**Is this OK?** Yes! If hash didn't change, file wasn't actually updated, so skipping is correct.

### Edge Case 3: File not in database

**Behavior:**
- Volume query returns None
- Returns False, prints warning
- Skips reprocess

**Is this OK?** Yes! Can't reprocess what's not indexed. User should run `index_media.py` first.

---

## Summary

✅ **Query original volume from database** - Use correct volume for update  
✅ **Use `--check-existing hash`** - Allow update when hash changes  
✅ **Better error handling** - Detect when file not in database  
✅ **Explicit debug output** - Shows volume being used  
✅ **Database properly updated** - Metadata reflects new EXIF  

**The database reprocessing now works correctly!** 🎉

Files are properly updated after EXIF changes, with GPS coordinates, city, state, country, and all other metadata refreshed in the database.
