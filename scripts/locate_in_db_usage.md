# locate_in_db.py - Find Files in Database by Hash

## Overview

`locate_in_db.py` searches the media database for files matching the hash of one or more query files. This is useful for:
- Finding if a file is already indexed
- Locating duplicates across different paths
- Verifying file locations
- Checking file existence

## Features

- ✅ Search by file hash (content-based)
- ✅ Support multiple query files
- ✅ Show file metadata (EXIF, video info)
- ✅ Check if files still exist at recorded paths
- ✅ JSON output for scripting
- ✅ Summary statistics
- ✅ Human-readable output

## Usage

### Basic Syntax

```bash
python3 locate_in_db.py --file QUERY_FILE --db-path DATABASE
```

### Required Parameters

- `--file FILE` or `--files FILE [FILE ...]`: File(s) to search for (can be repeated)
- `--db-path DATABASE` or `--db`: Path to media database

### Optional Parameters

- `--metadata` or `-m`: Show metadata for matching files
- `--json`: Output results as JSON
- `--show-hash`: Display file hash in output
- `--summary` or `-s`: Show only summary statistics

## Examples

### Example 1: Find Single File

```bash
python3 locate_in_db.py --file photo.jpg --db-path media.db
```

**Output:**
```
================================================================================
Query File: photo.jpg
Matches in database: 2
================================================================================

[1] File ID: 123
    Path: /photos/2024/vacation/photo.jpg
    Volume: Photos
    Size: 2.5 MB
    Modified: 2024-08-15T14:30:00
    Indexed: 2024-08-20T10:00:00
    Status: ✓ File exists

[2] File ID: 456
    Path: /backup/2024/photo.jpg
    Volume: Backup
    Size: 2.5 MB
    Modified: 2024-08-15T14:30:00
    Indexed: 2024-08-21T15:00:00
    Status: ✓ File exists
```

### Example 2: Multiple Files

```bash
python3 locate_in_db.py \
  --file photo1.jpg \
  --file photo2.jpg \
  --file video.mp4 \
  --db-path media.db
```

### Example 3: Show Metadata

```bash
python3 locate_in_db.py --file photo.jpg --db-path media.db --metadata
```

**Output:**
```
[1] File ID: 123
    Path: /photos/2024/vacation/photo.jpg
    Volume: Photos
    Size: 2.5 MB
    Modified: 2024-08-15T14:30:00
    Indexed: 2024-08-20T10:00:00
    Status: ✓ File exists
    Metadata:
      Dimensions: 4032x3024
      Date Taken: 2024-08-15 14:30:00
      Camera: Apple iPhone 15 Pro
      Location: 32.7767, -96.7970
      Place: Dallas, Texas, United States
      Keywords: vacation, beach, sunset
```

### Example 4: JSON Output

```bash
python3 locate_in_db.py --file photo.jpg --db-path media.db --json
```

**Output:**
```json
{
  "query_file": "photo.jpg",
  "hash": "abc123...",
  "match_count": 2,
  "matches": [
    {
      "id": 123,
      "volume": "Photos",
      "fullpath": "/photos/2024/vacation/photo.jpg",
      "name": "photo.jpg",
      "size": 2621440,
      "modified_date": "2024-08-15T14:30:00",
      "indexed_date": "2024-08-20T10:00:00",
      "exists": true
    },
    {
      "id": 456,
      "volume": "Backup",
      "fullpath": "/backup/2024/photo.jpg",
      "name": "photo.jpg",
      "size": 2621440,
      "modified_date": "2024-08-15T14:30:00",
      "indexed_date": "2024-08-21T15:00:00",
      "exists": true
    }
  ]
}
```

### Example 5: Summary Only

```bash
python3 locate_in_db.py \
  --file *.jpg \
  --db-path media.db \
  --summary
```

**Output:**
```
================================================================================
SUMMARY
================================================================================
Files queried: 10
Files with matches: 7
Files without matches: 3
Total matches found: 15
Average matches per file: 2.1
================================================================================
```

### Example 6: Show Hash Values

```bash
python3 locate_in_db.py --file photo.jpg --db-path media.db --show-hash
```

**Output:**
```
================================================================================
Query File: photo.jpg
Hash: a1b2c3d4e5f6...
Matches in database: 2
================================================================================
```

## Use Cases

### Use Case 1: Check if File is Already Indexed

Before adding a file to the database:

```bash
python3 locate_in_db.py --file new_photo.jpg --db-path media.db
```

If matches found → File already indexed
If no matches → Safe to add

### Use Case 2: Find All Copies of a File

```bash
python3 locate_in_db.py --file original.jpg --db-path media.db
```

Shows all locations where this file (or identical copies) exist.

### Use Case 3: Verify File Locations

```bash
python3 locate_in_db.py --file photo.jpg --db-path media.db
```

Check "Status" field:
- ✓ File exists → File still at recorded path
- ✗ File not found → File moved or deleted

### Use Case 4: Find Duplicates Before Moving

Before moving files:

```bash
for file in /downloads/*.jpg; do
    python3 locate_in_db.py --file "$file" --db-path media.db --summary
done
```

### Use Case 5: Batch Lookup with JSON

```bash
python3 locate_in_db.py \
  --file *.jpg \
  --db-path media.db \
  --json > results.json

# Process with jq
jq '.matches[] | select(.exists == false)' results.json
```

### Use Case 6: Find Missing Files

```bash
python3 locate_in_db.py --file photo.jpg --db-path media.db | \
  grep "File not found"
```

## Output Format

### Text Output

Each match shows:
- File ID (database record ID)
- Path (full file path)
- Volume (volume tag)
- Size (human-readable)
- Modified date
- Indexed date
- Status (file exists or not)
- Metadata (if --metadata flag used)

### JSON Output

Structured format with:
- `query_file`: Original query file
- `hash`: Computed hash
- `match_count`: Number of matches
- `matches`: Array of matching files
  - All database fields
  - `exists`: Boolean for file existence
  - `metadata`: Optional metadata object

## Exit Codes

- `0`: Success (matches found or not)
- `1`: Error (database not found, file not found, etc.)

## Performance

- Hash computation: ~1-2 seconds per GB
- Database query: Milliseconds
- Large databases: Indexed by hash, very fast

## Integration with Other Scripts

### With index_media.py

```bash
# Check before indexing
python3 locate_in_db.py --file new_photo.jpg --db-path media.db
if [ $? -eq 0 ]; then
    echo "File already indexed"
else
    python3 index_media.py --files new_photo.jpg --volume Photos --db-path media.db
fi
```

### With move_media.py

```bash
# Find where file exists before moving
python3 locate_in_db.py --file photo.jpg --db-path media.db --json | \
  jq -r '.matches[].fullpath'
```

### With manage_dupes.py

```bash
# Check if file is duplicate before moving
python3 locate_in_db.py --file suspect.jpg --db-path media.db --summary
```

## Scripting Examples

### Bash: Find All Duplicates

```bash
#!/bin/bash
for file in /downloads/*.jpg; do
    matches=$(python3 locate_in_db.py --file "$file" --db-path media.db --json | \
              jq '.match_count')
    if [ "$matches" -gt 0 ]; then
        echo "$file has $matches duplicates"
    fi
done
```

### Python: Process Results

```python
import subprocess
import json

result = subprocess.run([
    'python3', 'locate_in_db.py',
    '--file', 'photo.jpg',
    '--db-path', 'media.db',
    '--json'
], capture_output=True, text=True)

data = json.loads(result.stdout)
print(f"Found {data['match_count']} matches")

for match in data['matches']:
    if not match['exists']:
        print(f"Missing: {match['fullpath']}")
```

## Troubleshooting

### No matches found

Possible reasons:
- File not in database
- File modified since indexing (different hash)
- Database path incorrect

### Error computing hash

Check:
- File permissions
- Disk space
- File not corrupted

### Database locked

Close other connections:
```bash
# Check for locks
fuser media.db

# Kill processes
fuser -k media.db
```

## Tips

1. **Use JSON for Scripting**
   Always use `--json` flag for programmatic processing

2. **Check Multiple Files**
   Use `--file` multiple times for batch processing

3. **Summary for Overview**
   Use `--summary` to quickly see statistics

4. **Metadata for Details**
   Use `--metadata` to see complete file information

5. **Combine with Other Tools**
   Pipe output to `grep`, `jq`, `awk` for filtering

## Notes

- Hash is computed from file content (SHA-256)
- Same content = same hash, regardless of filename
- Modified files have different hashes
- Database records may be outdated if files moved externally
- Use with `--metadata` to see complete information

## See Also

- `index_media.py` - Index media files into database
- `move_media.py` - Move files and update database
- `manage_dupes.py` - Find and manage duplicate files
- `remove_dupes.py` - Remove duplicates from database
