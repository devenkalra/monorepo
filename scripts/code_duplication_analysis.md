# Code Duplication Analysis - Media Management Scripts

## Executive Summary

Yes, there is **significant code duplication** across the media management scripts. While some refactoring has been done to extract common functionality into `media_utils.py`, `location_utils.py`, and `audit_utils.py`, **`index_media.py` still contains duplicated code** that exists in the utility modules.

## Detailed Analysis

### 1. **Hash Calculation - DUPLICATED**

**Status:** ❌ **Duplicated**

**Locations:**
- `index_media.py` (lines 148-158) - Custom implementation
- `media_utils.py` (lines 124-141) - Shared implementation
- `index_media2026-01-22-20-37.py` (lines 148-158) - Backup/old file

**Issue:** `index_media.py` has its own `calculate_file_hash()` function instead of importing from `media_utils.py`.

```python
# index_media.py - DUPLICATE
def calculate_file_hash(filepath: str, chunk_size: int = 8192) -> str:
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    # ... implementation ...

# media_utils.py - SHARED VERSION
def calculate_file_hash(filepath: str, algorithm: str = 'sha256') -> str:
    """Calculate hash of a file."""
    hash_obj = hashlib.new(algorithm)
    # ... implementation ...
```

**Scripts using shared version:**
- ✅ `move_media.py` - imports from `media_utils`
- ✅ `locate_in_db.py` - imports from `media_utils`
- ✅ `manage_dupes.py` - imports from `media_utils`
- ✅ `remove_dupes.py` - imports from `media_utils`

**Scripts NOT using shared version:**
- ❌ `index_media.py` - has its own copy

---

### 2. **Database Schema Creation - DUPLICATED**

**Status:** ❌ **Duplicated**

**Locations:**
- `index_media.py` (lines 40-143) - Full schema (~100 lines)
- `media_utils.py` (lines 17-119) - Shared schema (~100 lines)
- `index_media2026-01-22-20-37.py` (lines 40-143) - Backup/old file

**Issue:** `index_media.py` has its own complete `create_database_schema()` function with the same table definitions as `media_utils.py`.

**Scripts using shared version:**
- ✅ `move_media.py` - imports from `media_utils`
- ✅ `manage_dupes.py` - imports from `media_utils`
- ✅ `remove_dupes.py` - imports from `media_utils`

**Scripts NOT using shared version:**
- ❌ `index_media.py` - has its own copy (~100 lines of duplication)

---

### 3. **EXIF Data Extraction - DUPLICATED**

**Status:** ❌ **Duplicated**

**Locations:**
- `index_media.py` - `get_exif_data()`, `normalize_exif_data()` (lines 163-379)
- `move_media.py` - Has its own implementation of EXIF processing
- `apply_exif.py` - Has different exiftool execution logic
- `show_exif.py` - Has `run_exiftool()` function

**Issue:** Multiple scripts run `exiftool` with different wrappers and error handling:

```python
# index_media.py
def get_exif_data(filepath: str) -> Optional[Dict]:
    cmd = ["exiftool", "-json", "-G", filepath]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    # ...

# show_exif.py
def run_exiftool(files: List[str], options: List[str]) -> str:
    cmd = ['exiftool'] + options + files
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    # ...

# apply_exif.py
def run_exiftool(files: list, tags: dict, dry_run: bool):
    cmd = build_exiftool_cmd(files, tags, dry_run)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    # ...
```

**Recommendation:** Create a shared `exif_utils.py` module with:
- `run_exiftool()` - Generic exiftool execution
- `get_exif_data()` - Extract EXIF as JSON
- `normalize_exif_data()` - Normalize fields
- `build_exiftool_write_cmd()` - Build write commands

---

### 4. **File Type Detection - PARTIALLY SHARED**

**Status:** ⚠️ **Partially Shared**

**Shared in `media_utils.py`:**
- `get_mime_type()` - Returns MIME type
- `is_image_file()` - Check if file is image
- `is_video_file()` - Check if file is video
- Constants: `IMAGE_MIMES`, `VIDEO_MIMES`, `RAW_IMAGE_EXTENSIONS`

**Scripts using shared version:**
- ✅ `move_media.py` - imports from `media_utils`
- ✅ `manage_dupes.py` - imports from `media_utils`

**Scripts with their own logic:**
- ❌ `index_media.py` - Has inline MIME detection
- ⚠️ `convert_non_photos.py` - Has its own file extension checks

---

### 5. **Argument Parsing - HIGHLY DUPLICATED**

**Status:** ❌ **Highly Duplicated**

**Common arguments across scripts:**
- `--dry-run` - In 6+ scripts
- `--verbose` / `-v` - In 6+ scripts with same choices `[0,1,2,3]`
- `--db-path` / `--db` - In 5+ scripts
- `--limit` - In 6+ scripts (recently added to all)

**Issue:** Every script defines these independently with slight variations:

```python
# index_media.py
parser.add_argument("--verbose", "-v", type=int, default=0, choices=[0, 1, 2, 3],
                   help="Verbosity level: 0=quiet, 1=file+outcome, 2=more details, 3=full metadata (default: 0)")

# move_media.py
parser.add_argument("--verbose", "-v", type=int, default=1, choices=[0, 1, 2, 3],
                   help="Verbosity level: 0=quiet, 1=summary, 2=detailed, 3=debug (default: 1)")

# remove_dupes.py
parser.add_argument("--verbose", "-v", type=int, default=1, choices=[0, 1, 2, 3],
                   help="Verbosity level: 0=quiet, 1=summary, 2=detailed, 3=debug (default: 1)")
```

**Recommendation:** Create an `argparse_utils.py` module with common argument factory functions:
- `add_verbose_arg(parser, default=0)`
- `add_dry_run_arg(parser)`
- `add_limit_arg(parser)`
- `add_db_path_arg(parser, required=True)`

---

### 6. **Thumbnail Generation - UNIQUE (Not Duplicated)**

**Status:** ✅ **Unique to `index_media.py`**

**Location:** Only in `index_media.py` (lines 380-580+)

Functions:
- `generate_thumbnail()` - Main dispatcher
- `_generate_raw_thumbnail()` - RAW image thumbnails
- `_generate_image_thumbnail()` - Standard image thumbnails
- `_generate_video_thumbnail()` - Video thumbnails with ffmpeg

**Note:** This is legitimately unique to `index_media.py` and doesn't need to be shared since other scripts don't generate thumbnails.

---

### 7. **Video Metadata Extraction - UNIQUE (Not Duplicated)**

**Status:** ✅ **Unique to `index_media.py`**

**Location:** Only in `index_media.py` (lines 580-700+)

Functions:
- `get_video_metadata()` - Extract with ffprobe
- `parse_video_duration()` - Parse duration strings

**Note:** Only `index_media.py` extracts video metadata, so this is appropriately unique.

---

### 8. **Location/Geocoding - PROPERLY REFACTORED**

**Status:** ✅ **Properly Shared**

**Shared in `location_utils.py`:**
- `geocode_place()` - Geocode with retry logic
- `get_elevation()` - Get elevation from coordinates
- `create_exif_metadata()` - Build location metadata dict

**Scripts using shared version:**
- ✅ `apply_exif.py` - imports from `location_utils`
- ✅ `find_location.py` - imports from `location_utils`

**This is the CORRECT pattern** - code was extracted and is now shared.

---

### 9. **Audit Logging - PROPERLY REFACTORED**

**Status:** ✅ **Properly Shared**

**Shared in `audit_utils.py`:**
- `get_audit_logger()` - Setup logger
- `log_session_start()`, `log_session_end()` - Session tracking
- `log_file_moved()`, `log_file_indexed()`, etc. - Action logging
- `log_error()`, `log_skip()` - Error/skip logging

**Scripts using shared version:**
- ✅ `move_media.py` - imports from `audit_utils`
- ✅ Other scripts can import as needed

**This is the CORRECT pattern** - shared utility properly used.

---

### 10. **Pattern Matching / File Filtering - UNIQUE**

**Status:** ⚠️ **Could be shared**

**Current state:**
- `index_media.py` - Has pattern matching logic for `--skip-pattern` and `--include-pattern`
- `manage_dupes.py` - Has similar pattern matching logic
- `convert_non_photos.py` - Has its own file filtering

**Recommendation:** Could extract to `file_utils.py`:
- `should_process_file()` - Apply skip/include patterns
- `matches_pattern()` - Pattern matching with regex/literal support

---

## Summary of Issues

### Critical Duplications (Should be fixed):

1. **`index_media.py` should use `media_utils.calculate_file_hash()`**
   - Currently has 10+ lines of duplicate code
   - Easy fix: Replace with import

2. **`index_media.py` should use `media_utils.create_database_schema()`**
   - Currently has ~100 lines of duplicate code
   - Easy fix: Replace with import

3. **EXIF extraction should be centralized**
   - Multiple different implementations across 3+ scripts
   - Medium effort: Create `exif_utils.py`

4. **Argument parsing should use shared functions**
   - High duplication across 6+ scripts
   - Medium effort: Create `argparse_utils.py`

---

## Recommended Refactoring Priority

### **Priority 1: Fix `index_media.py` imports (Easy, High Impact)**

```python
# At top of index_media.py, add:
from media_utils import (
    create_database_schema,
    calculate_file_hash,
    get_mime_type,
    is_image_file,
    is_video_file
)

# Then DELETE duplicate functions:
# - Lines 40-143 (create_database_schema)
# - Lines 148-158 (calculate_file_hash)
```

**Impact:** Reduces `index_media.py` by ~110 lines, ensures consistency

---

### **Priority 2: Create `exif_utils.py` (Medium Effort, High Value)**

Extract common EXIF operations:

```python
# exif_utils.py
def run_exiftool_read(filepath: str, grouped: bool = True) -> Optional[Dict]:
    """Read EXIF data from file."""
    
def run_exiftool_write(files: List[str], tags: Dict[str, str], 
                        dry_run: bool = False) -> bool:
    """Write EXIF tags to files."""

def normalize_exif_data(exif: Dict) -> Dict:
    """Normalize EXIF to common fields."""
```

**Impact:** Consolidates 3+ implementations, reduces errors

---

### **Priority 3: Create `argparse_utils.py` (Medium Effort, Maintainability)**

```python
# argparse_utils.py
def add_common_args(parser, include_dry_run=True, include_verbose=True, 
                   include_limit=True, include_db=False):
    """Add common arguments to parser."""
    if include_dry_run:
        parser.add_argument("--dry-run", action="store_true",
                          help="Show what would be done without making changes")
    if include_verbose:
        parser.add_argument("--verbose", "-v", type=int, default=1, 
                          choices=[0, 1, 2, 3],
                          help="Verbosity level: 0=quiet, 1=summary, 2=detailed, 3=debug")
    # ... etc
```

**Impact:** Reduces argparse duplication, ensures consistency

---

## Files Summary

### Well-Refactored (Good examples):
- ✅ `media_utils.py` - Shared utilities properly extracted
- ✅ `location_utils.py` - Location code properly shared
- ✅ `audit_utils.py` - Audit logging properly shared
- ✅ `move_media.py` - Properly uses all shared utilities
- ✅ `manage_dupes.py` - Properly uses shared utilities
- ✅ `remove_dupes.py` - Properly uses shared utilities

### Needs Refactoring:
- ❌ `index_media.py` - Should import from `media_utils` instead of duplicating
- ⚠️ `show_exif.py` - Could share EXIF utilities
- ⚠️ `apply_exif.py` - Could share EXIF utilities

### Old/Backup Files (Should be deleted):
- 🗑️ `index_media2026-01-22-20-37.py` - Old backup, should be removed

---

## Conclusion

**Yes, there is duplication**, primarily in `index_media.py` which has ~110 lines of code that already exists in `media_utils.py`. The refactoring effort that created `media_utils.py`, `location_utils.py`, and `audit_utils.py` was excellent, but `index_media.py` was never updated to use these shared utilities.

**Quick Win:** Refactor `index_media.py` to import from `media_utils.py` - this is a 10-minute fix that eliminates significant duplication.

**Long-term:** Consider creating `exif_utils.py` and `argparse_utils.py` for even better code organization.
