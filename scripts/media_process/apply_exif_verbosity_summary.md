# Apply EXIF Verbosity Enhancement

**Date:** 2026-01-28  
**Issue:** EXIF not getting updated for files already in database  
**Solution:** Added comprehensive verbosity levels to trace execution  
**Status:** ✅ **COMPLETE**

---

## Overview

Added `-v/--verbose` parameter with **multiple verbosity levels** to `apply_exif.py` to help debug EXIF update issues. The verbosity flag can be specified multiple times for increasing detail.

---

## Verbosity Levels

### **Level 0: Normal/Quiet (default)**
```bash
python3 apply_exif.py --files photo.jpg --latitude 32.7157 --longitude -97.3308
# or explicitly:
python3 apply_exif.py --verbose 0 --files photo.jpg --latitude 32.7157 --longitude -97.3308
```

**Shows:**
- File being processed
- Tags being applied
- Basic success/failure messages
- Exiftool command executed

**Example output:**
```
Processing file: photo.jpg
Tag: GPSLatitude = '32.7157'
Tag: GPSLongitude = '-97.3308'
Exiftool command: exiftool -GPSLatitude=32.7157 -GPSLongitude=-97.3308 photo.jpg
  ✓ EXIF tags written successfully
  File found in database, reprocessing...
  ✓ Database updated
Done.
```

---

### **Level 1: Verbose**
```bash
python3 apply_exif.py --verbose 1 --files photo.jpg --latitude 32.7157 --longitude -97.3308 --db-path media.db --reprocess-db
# or shorthand:
python3 apply_exif.py -v 1 --files photo.jpg --latitude 32.7157 --longitude -97.3308 --db-path media.db --reprocess-db
```

**Adds:**
- More detailed status messages
- File found/not found in database
- Reprocessing progress
- index_media stdout/stderr if errors occur

**Example output:**
```
Processing file: photo.jpg
Tag: GPSLatitude = '32.7157'
Tag: GPSLongitude = '-97.3308'
[VERBOSE] Exiftool command: exiftool -GPSLatitude=32.7157 ...
  ✓ EXIF tags written successfully
  File found in database, reprocessing...
  Reprocessing in database: photo.jpg
  ✓ Database updated
✓ EXIF tags applied and database updated for 1 file(s).
```

---

### **Level 2: Debug**
```bash
python3 apply_exif.py --verbose 2 --files photo.jpg --latitude 32.7157 --longitude -97.3308 --db-path media.db --reprocess-db
# or shorthand:
python3 apply_exif.py -v 2 --files photo.jpg --latitude 32.7157 --longitude -97.3308 --db-path media.db --reprocess-db
```

**Adds:**
- Step-by-step execution trace
- Function entry/exit
- Configuration details
- File existence checks
- File permissions
- Command building details
- Subprocess execution status
- Return codes

**Example output:**
```
Processing 1 file(s)...
[DEBUG] Verbosity level: 2
[DEBUG] Dry run: False
[DEBUG] Database path: media.db
[DEBUG] Reprocess database: True
[DEBUG] Base tags to apply: {'GPSLatitude': '32.7157', ...}
[DEBUG] Files to process: ['photo.jpg']

Processing file: photo.jpg
[DEBUG] ========== Processing: photo.jpg ==========
[DEBUG] File exists: True
[DEBUG] File size: 2458624 bytes
[DEBUG] File permissions: 0o100644
[DEBUG] Tags to apply for photo.jpg:
Tag: GPSLatitude = '32.7157'
Tag: GPSLongitude = '-97.3308'
[DEBUG] Step 1: Writing EXIF tags to file...
[DEBUG] Building exiftool command for 1 file(s) with 2 tag(s)
[DEBUG] Executing exiftool subprocess...
[DEBUG] Exiftool completed with return code: 0
[DEBUG] Exiftool execution successful
[DEBUG] Step 2: Verifying EXIF write...
[DEBUG] Verifying EXIF write for: photo.jpg
[DEBUG] Will verify tag: GPSLatitude
[DEBUG] Verification succeeded
  ✓ EXIF tags written successfully
[DEBUG] Step 3: Checking if file is in database...
[DEBUG] Waiting 200ms for filesystem sync...
  File found in database, reprocessing...
[DEBUG] Step 4: Reprocessing file in database...
[DEBUG] Starting database reprocess for: photo.jpg
[DEBUG] Looking for index_media.py at: /home/ubuntu/monorepo/scripts/index_media.py
[DEBUG] File directory: /path/to
[DEBUG] File name: photo.jpg
[DEBUG] Reprocess command: python3 /home/ubuntu/.../index_media.py --path /path/to --volume updated --db-path media.db --include-pattern ^photo.jpg$ --literal-patterns --check-existing fullpath --verbose 2
[DEBUG] Executing index_media subprocess...
[DEBUG] index_media completed with return code: 0
  ✓ Database updated
✓ EXIF tags applied and database updated for 1 file(s).
```

---

### **Level 3: Trace**
```bash
python3 apply_exif.py --verbose 3 --files photo.jpg --latitude 32.7157 --longitude -97.3308 --db-path media.db --reprocess-db
# or shorthand:
python3 apply_exif.py -v 3 --files photo.jpg --latitude 32.7157 --longitude -97.3308 --db-path media.db --reprocess-db
```

**Adds:**
- Full stdout/stderr from exiftool
- Full stdout/stderr from index_media
- Verification command details
- Verification results (raw output)
- All subprocess output

**Example output:**
```
[... All Level 2 output plus ...]

[DEBUG] Exiftool stdout (156 chars):
    1 image files updated

[DEBUG] Verification command: exiftool -GPSLatitude -s3 photo.jpg
[DEBUG] Verification result stdout: '32.7157'
[DEBUG] Verification result stderr: ''

[DEBUG] index_media stdout:
Scanning directory: /path/to
Processing file: photo.jpg
  Hash: abc123...
  Updating existing record
  ✓ Updated 1 file
[DEBUG] index_media stderr:
```

---

## Key Debugging Steps Traced

### **Step 1: Writing EXIF Tags**
```
[DEBUG] Step 1: Writing EXIF tags to file...
[DEBUG] Building exiftool command for 1 file(s) with 2 tag(s)
[DEBUG] Executing exiftool subprocess...
[DEBUG] Exiftool completed with return code: 0
```

**What to check:**
- Does exiftool execute?
- What's the return code?
- Any warnings/errors?

---

### **Step 2: Verifying Write**
```
[DEBUG] Step 2: Verifying EXIF write...
[DEBUG] Verifying EXIF write for: photo.jpg
[DEBUG] Will verify tag: GPSLatitude
[DEBUG] Verification command: exiftool -GPSLatitude -s3 photo.jpg
[DEBUG] Verification result stdout: '32.7157'
[DEBUG] Verification succeeded
```

**What to check:**
- Can we read back the tag?
- Does it have the expected value?
- Is verification hanging?

---

### **Step 3: Checking Database**
```
[DEBUG] Step 3: Checking if file is in database...
[DEBUG] Waiting 200ms for filesystem sync...
  File found in database, reprocessing...
```

**What to check:**
- Is file in database?
- Is the path correct?
- Is database accessible?

---

### **Step 4: Reprocessing**
```
[DEBUG] Step 4: Reprocessing file in database...
[DEBUG] Starting database reprocess for: photo.jpg
[DEBUG] Looking for index_media.py at: /home/ubuntu/monorepo/scripts/index_media.py
[DEBUG] Reprocess command: python3 /home/ubuntu/.../index_media.py ...
[DEBUG] Executing index_media subprocess...
[DEBUG] index_media completed with return code: 0
```

**What to check:**
- Does index_media.py exist?
- Does the command execute?
- What's the return code?
- Any errors in stdout/stderr?

---

## Usage Examples

### **Quick Test (Level 1)**
```bash
python3 apply_exif.py --verbose 1 \
  --files /mnt/photo/test.jpg \
  --city "Fort Worth" \
  --db-path ~/media_index.db \
  --reprocess-db
```

### **Debug Issue (Level 2)**
```bash
python3 apply_exif.py --verbose 2 \
  --files /mnt/photo/test.jpg \
  --latitude 32.7157 \
  --longitude -97.3308 \
  --db-path ~/media_index.db \
  --reprocess-db
```

### **Full Trace (Level 3)**
```bash
python3 apply_exif.py --verbose 3 \
  --files /mnt/photo/test.jpg \
  --place "Fort Worth, Texas, USA" \
  --db-path ~/media_index.db \
  --reprocess-db
```

### **Dry Run with Debug**
```bash
python3 apply_exif.py --verbose 2 --dry-run \
  --files test.jpg \
  --latitude 32.7157 \
  --longitude -97.3308
```

---

## Common Issues and What to Look For

### **Issue: EXIF not written**

**Look for in `--verbose 2` output:**
```
[DEBUG] Exiftool completed with return code: 1    <-- NON-ZERO!
Exiftool stderr: Error: File not found
```

**Possible causes:**
- File doesn't exist
- File not writable
- Invalid tag values
- Exiftool not installed

---

### **Issue: Verification fails**

**Look for in `--verbose 2` output:**
```
[DEBUG] Verification result stdout: ''    <-- EMPTY!
[DEBUG] Verification FAILED
  ⚠ EXIF tags may not have been written
```

**Possible causes:**
- EXIF write failed silently
- Tag format incorrect
- File was overwritten
- Filesystem caching issue

---

### **Issue: Database not updated**

**Look for in `--verbose 2` output:**
```
[DEBUG] index_media completed with return code: 1    <-- NON-ZERO!
  ⚠ Database reprocess returned code 1
[VERBOSE] Stderr: Error: Cannot access database
```

**Possible causes:**
- index_media.py not found
- Database locked
- Database path incorrect
- File not in database
- Permission issues

---

### **Issue: File not in database**

**Look for in `--verbose 2` output:**
```
[DEBUG] Step 3: Checking if file is in database...
  (File not in database, skipping reprocess)
[DEBUG] File /path/to/photo.jpg not found in database
```

**This is expected if:**
- File was never indexed
- File path changed
- Database is different

**Solution:** Index the file first with `index_media.py`

---

## Modified Functions

All functions now accept a `verbose` parameter (integer):

### **`run_exiftool(files, tags, dry_run, verbose=0)`**
- Traces command building
- Shows subprocess execution
- Displays stdout/stderr
- Reports return code

### **`verify_exif_written(file_path, expected_tags, verbose=0)`**
- Shows which tag is being verified
- Displays verification command
- Shows verification results
- Reports success/failure

### **`reprocess_file_in_database(db_path, file_path, verbose=0)`**
- Traces file lookup
- Shows command building
- Displays subprocess execution
- Reports index_media output

---

## Integration with image_process.py

Update the `apply_exif` command in `image_process.py` to include verbose:

```python
'params': [
    'dry_run',
    'files',
    'place',
    'gps_coords',
    'city', 'state', 'country', 'country_code',
    'coverage',
    'date', 'offset',
    'add_keyword', 'remove_keyword',
    'caption',
    'db_path', 'reprocess_db',
    'verbose',    # <-- ADD THIS
    'limit'
]
```

And add the parameter definition:

```python
'verbose': {
    'label': 'Verbosity',
    'type': 'choice',
    'flag': '--verbose',
    'options': ['0 (Quiet)', '1 (Verbose)', '2 (Debug)', '3 (Trace)'],
    'values': ['0', '1', '2', '3'],
    'default': '0',
    'help': 'Verbosity level: 0=quiet, 1=verbose, 2=debug, 3=trace'
}
```

---

## Troubleshooting Workflow

### **Step 1: Run with --verbose 1**
```bash
python3 apply_exif.py --verbose 1 --files test.jpg ...
```
**Goal:** See if basic flow works

### **Step 2: If issue persists, run with --verbose 2**
```bash
python3 apply_exif.py --verbose 2 --files test.jpg ...
```
**Goal:** See which step is failing

### **Step 3: If still unclear, run with --verbose 3**
```bash
python3 apply_exif.py --verbose 3 --files test.jpg ...
```
**Goal:** See full command output

### **Step 4: Check specific components**

**Test exiftool directly:**
```bash
exiftool -GPSLatitude=32.7157 test.jpg
exiftool -GPSLatitude test.jpg
```

**Test file in database:**
```bash
python3 locate_in_db.py --files test.jpg --db-path media.db
```

**Test index_media directly:**
```bash
python3 index_media.py --path /path/to --volume test --db-path media.db --verbose 2
```

---

## Changes Made

### **`apply_exif.py`**

**Lines added:** ~150  
**Functions modified:** 3

1. **Added `--verbose/-v` argument** (line ~595)
   ```python
   parser.add_argument("--verbose", "-v", type=int, default=0, choices=[0, 1, 2, 3],
                       help="Verbosity level: 0=quiet, 1=verbose, 2=debug, 3=trace (default: 0)")
   ```

2. **Updated `run_exiftool()` to accept `verbose` parameter** (line ~117)
   - Added debug output for command building
   - Added trace output for subprocess execution
   - Added stdout/stderr display at level 3

3. **Updated `verify_exif_written()` to accept `verbose` parameter** (line ~378)
   - Added debug output for verification process
   - Added trace output for verification command and results

4. **Updated `reprocess_file_in_database()` to accept `verbose` parameter** (line ~469)
   - Changed from `verbose: bool` to `verbose: int`
   - Added debug output for all steps
   - Added trace output for subprocess output

5. **Added debug output in main processing loop** (line ~713+)
   - File existence and permissions check
   - Step-by-step execution trace
   - Configuration display
   - Exception tracebacks at level 2

---

## Testing

### **Test 1: Normal operation**
```bash
python3 apply_exif.py \
  --files test.jpg \
  --latitude 32.7157 \
  --longitude -97.3308
```
**Expected:** No debug output, clean success messages

### **Test 2: Verbose operation**
```bash
python3 apply_exif.py --verbose 1 \
  --files test.jpg \
  --latitude 32.7157 \
  --longitude -97.3308
```
**Expected:** Shows reprocessing messages

### **Test 3: Debug operation**
```bash
python3 apply_exif.py --verbose 2 \
  --files test.jpg \
  --latitude 32.7157 \
  --longitude -97.3308 \
  --db-path media.db \
  --reprocess-db
```
**Expected:** Shows [DEBUG] prefixed messages for each step

### **Test 4: Trace operation**
```bash
python3 apply_exif.py --verbose 3 \
  --files test.jpg \
  --city "Fort Worth" \
  --db-path media.db \
  --reprocess-db
```
**Expected:** Shows full subprocess output

---

## Benefits

✅ **Pinpoint failures** - See exactly which step fails  
✅ **Verify writes** - Confirm EXIF actually written  
✅ **Debug reprocessing** - See index_media output  
✅ **Check permissions** - See file access issues  
✅ **Trace commands** - See exact commands executed  
✅ **Non-intrusive** - Default behavior unchanged  
✅ **Progressive detail** - Choose verbosity level needed  

---

## Next Steps

1. **Test with problematic file:**
   ```bash
   python3 apply_exif.py --verbose 2 \
     --files /mnt/photo/problem.jpg \
     --latitude 32.7157 \
     --longitude -97.3308 \
     --db-path ~/media_index.db \
     --reprocess-db
   ```

2. **Look for specific failure:**
   - Step 1 failure → exiftool issue
   - Step 2 failure → verification issue
   - Step 3 failure → database connectivity
   - Step 4 failure → index_media issue

3. **Share output** for further diagnosis if needed

---

## Summary

✅ Added comprehensive verbosity levels (0, 1, 2, 3)  
✅ Traces all 4 key steps of EXIF update process  
✅ Shows exact commands and their output  
✅ Displays file permissions and existence  
✅ Reports return codes and errors  
✅ Non-intrusive (default behavior unchanged)  
✅ Progressive detail based on level  
✅ Consistent with other scripts (numeric levels)  

**Now you can run with `--verbose 2` to see exactly where the EXIF update is failing!** 🎉
