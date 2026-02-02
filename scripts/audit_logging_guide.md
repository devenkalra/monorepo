# Audit Logging Guide

## Overview

All media management scripts now include comprehensive audit logging. Audit logs provide a permanent, append-only record of all operations, enabling database reconstruction and disaster recovery.

## Purpose

Audit logs serve as:
- **Disaster Recovery**: Reconstruct database from old backup + audit logs
- **Compliance**: Track all file operations with timestamps
- **Debugging**: Understand what happened and when
- **Accountability**: Complete history of all changes
- **Analysis**: Query operations over time

## Audit Log Format

### Log Entry Structure

```
timestamp | script_name | level | message
```

Example:
```
2026-01-26 22:30:15 | audit.move_media | INFO | FILE_MOVED | action=inserted | file_id=123 | source=/old/path.jpg | dest=/new/path.jpg | volume=Photos | hash=abc123...
```

### Components

- **Timestamp**: `YYYY-MM-DD HH:MM:SS` format
- **Script Name**: `audit.{script_name}` (e.g., `audit.move_media`)
- **Level**: INFO, ERROR, WARNING
- **Message**: Structured log message with key=value pairs

## Log Entry Types

### SESSION_START
Logged when script begins execution.

```
SESSION_START | script=move_media | args={'files': [...], 'destination': '/dest', ...}
```

### SESSION_END
Logged when script completes execution.

```
SESSION_END | script=move_media | stats={'moved': 10, 'skipped': 2, 'errors': 0, ...}
```

### FILE_MOVED
Logged when a file is moved.

```
FILE_MOVED | action=inserted | file_id=123 | source=/old/path.jpg | dest=/new/path.jpg | volume=Photos | hash=abc123...
```

Actions: `moved`, `updated`, `inserted`, `skipped`

### FILE_INDEXED
Logged when a file is indexed.

```
FILE_INDEXED | action=indexed | file_id=456 | path=/photos/img.jpg | volume=Photos | hash=def456...
```

Actions: `indexed`, `updated`, `skipped`

### FILE_DUPLICATE
Logged when a duplicate file is handled.

```
FILE_DUPLICATE | action=moved | path=/source/dup.jpg | hash=abc123... | reason=duplicate_found | dest=/dupes/dup.jpg
```

### FILE_REMOVED
Logged when a file record is removed from database.

```
FILE_REMOVED | file_id=789 | path=/photos/old.jpg | hash=ghi789... | reason=duplicate | dest=/dupes/old.jpg
```

### FILE_SKIPPED
Logged when a file is skipped.

```
FILE_SKIPPED | path=/photos/skip.jpg | reason=destination_exists_same_hash | details=dest=/dest/skip.jpg, hash=abc123...
```

### ERROR
Logged when an error occurs.

```
ERROR | type=file_not_found | message=Source file not found: /missing.jpg | context=processing
```

### DB_OPERATION
Logged for significant database operations.

```
DB_OPERATION | op=INSERT | table=files | id=123 | details=new file indexed
```

## Usage

### Command Line

All scripts support the `--audit-log` parameter:

```bash
# Use default audit log (script_name_audit.log)
python3 move_media.py --files *.jpg --destination /dest --volume Photos --db-path media.db

# Specify custom audit log
python3 move_media.py --files *.jpg --destination /dest --volume Photos --db-path media.db \
  --audit-log /logs/custom_audit.log
```

### Default Locations

If `--audit-log` is not specified, logs are written to:
- `move_media_audit.log` (for move_media.py)
- `index_media_audit.log` (for index_media.py)
- `manage_dupes_audit.log` (for manage_dupes.py)
- `remove_dupes_audit.log` (for remove_dupes.py)

Located in the same directory as the script.

## Disaster Recovery

### Scenario: Database Lost

You have:
- Old database backup from January 1
- Audit logs from January 1 to January 26

### Recovery Steps

1. **Restore old backup**
   ```bash
   cp media_backup_2026-01-01.db media.db
   ```

2. **Extract operations from audit logs**
   ```bash
   # Get all FILE_MOVED operations since backup
   grep "FILE_MOVED" move_media_audit.log | \
     awk -F'|' '$1 >= "2026-01-01"' > operations.txt
   ```

3. **Reconstruct database**
   Parse audit log entries and replay operations:
   ```python
   # Example reconstruction script
   import sqlite3
   import re
   
   conn = sqlite3.connect('media.db')
   
   with open('operations.txt') as f:
       for line in f:
           # Parse: file_id=123 | source=/old | dest=/new | volume=Photos | hash=abc
           match = re.search(r'file_id=(\d+).*dest=([^ |]+).*volume=([^ |]+).*hash=([^ |]+)', line)
           if match:
               file_id, dest, volume, hash_val = match.groups()
               # Update or insert record
               conn.execute("""
                   INSERT OR REPLACE INTO files (id, fullpath, volume, file_hash)
                   VALUES (?, ?, ?, ?)
               """, (file_id, dest, volume, hash_val))
   
   conn.commit()
   ```

4. **Verify reconstruction**
   ```bash
   # Compare file counts
   sqlite3 media.db "SELECT COUNT(*) FROM files"
   
   # Verify recent files
   sqlite3 media.db "SELECT * FROM files ORDER BY indexed_date DESC LIMIT 10"
   ```

## Querying Audit Logs

### Find all moves in date range

```bash
grep "FILE_MOVED" move_media_audit.log | \
  awk -F'|' '$1 >= "2026-01-20" && $1 <= "2026-01-26"'
```

### Find all errors

```bash
grep "ERROR" *_audit.log
```

### Count operations by type

```bash
grep -o "FILE_[A-Z]*" move_media_audit.log | sort | uniq -c
```

### Find operations on specific file

```bash
grep "/photos/vacation/beach.jpg" *_audit.log
```

### Get session statistics

```bash
grep "SESSION_END" move_media_audit.log | tail -5
```

### Find all skipped files

```bash
grep "FILE_SKIPPED" move_media_audit.log | \
  awk -F'|' '{print $4, $5}' | \
  sort | uniq -c
```

## Best Practices

### 1. Regular Backups

Backup both database and audit logs:
```bash
# Daily backup script
DATE=$(date +%Y-%m-%d)
cp media.db backups/media_${DATE}.db
cp *_audit.log backups/
```

### 2. Log Rotation

Audit logs are append-only and can grow large. Rotate periodically:
```bash
# Monthly rotation
DATE=$(date +%Y-%m)
mv move_media_audit.log archives/move_media_audit_${DATE}.log
# Script will create new log automatically
```

### 3. Centralized Logging

For multiple machines, aggregate logs:
```bash
# Send to central log server
rsync -av *_audit.log logserver:/logs/media/$(hostname)/
```

### 4. Monitoring

Set up alerts for errors:
```bash
# Check for errors in last hour
if grep "ERROR" move_media_audit.log | \
   awk -F'|' '$1 >= "'$(date -d '1 hour ago' '+%Y-%m-%d %H:%M:%S')'"' | \
   grep -q .; then
    echo "Errors detected in audit log!" | mail -s "Alert" admin@example.com
fi
```

### 5. Retention Policy

Define how long to keep logs:
- Active logs: Keep indefinitely
- Archived logs: Keep for 1 year
- Compressed archives: Keep for 7 years

## Integration with Scripts

### move_media.py

```bash
python3 move_media.py \
  --files *.jpg \
  --destination /photos/2024 \
  --volume Photos \
  --db-path media.db \
  --audit-log /logs/move_media.log
```

Logs:
- Session start/end
- Each file moved
- Skipped files
- Errors
- Database operations

### index_media.py

```bash
python3 index_media.py \
  --path /photos \
  --start-dir 2024 \
  --volume Photos \
  --db-path media.db \
  --audit-log /logs/index_media.log
```

Logs:
- Session start/end
- Each file indexed
- Metadata extracted
- Skipped files
- Errors

### manage_dupes.py

```bash
python3 manage_dupes.py \
  --source /downloads \
  --dest /dupes \
  --db-path media.db \
  --audit-log /logs/manage_dupes.log
```

Logs:
- Session start/end
- Duplicate files found
- Files moved/copied
- Database checks
- Errors

### remove_dupes.py

```bash
python3 remove_dupes.py \
  --db-path media.db \
  --dest /dupes \
  --base-dir /photos \
  --audit-log /logs/remove_dupes.log
```

Logs:
- Session start/end
- Duplicate groups found
- Files removed
- Database records deleted
- Errors

## Audit Log Analysis

### Python Script Example

```python
import re
from datetime import datetime
from collections import defaultdict

def analyze_audit_log(log_file):
    """Analyze audit log and generate statistics."""
    stats = defaultdict(int)
    errors = []
    
    with open(log_file) as f:
        for line in f:
            # Parse timestamp
            match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if not match:
                continue
            
            timestamp = match.group(1)
            
            # Count operation types
            if 'FILE_MOVED' in line:
                stats['files_moved'] += 1
            elif 'FILE_INDEXED' in line:
                stats['files_indexed'] += 1
            elif 'FILE_SKIPPED' in line:
                stats['files_skipped'] += 1
            elif 'ERROR' in line:
                stats['errors'] += 1
                errors.append((timestamp, line))
    
    return stats, errors

# Usage
stats, errors = analyze_audit_log('move_media_audit.log')
print(f"Files moved: {stats['files_moved']}")
print(f"Errors: {stats['errors']}")

for timestamp, error in errors:
    print(f"{timestamp}: {error}")
```

## Security Considerations

### File Permissions

Protect audit logs:
```bash
chmod 640 *_audit.log
chown user:admin *_audit.log
```

### Tamper Detection

Create checksums:
```bash
# Daily checksum
sha256sum *_audit.log > audit_checksums.txt
```

Verify integrity:
```bash
sha256sum -c audit_checksums.txt
```

### Encryption

Encrypt archived logs:
```bash
tar czf - move_media_audit_2026-01.log | \
  gpg --encrypt --recipient admin@example.com > \
  move_media_audit_2026-01.log.tar.gz.gpg
```

## Troubleshooting

### Log file not created

Check permissions:
```bash
ls -l /path/to/audit.log
```

Check disk space:
```bash
df -h /path/to
```

### Missing log entries

Verify script completed:
```bash
grep "SESSION_END" move_media_audit.log | tail -1
```

Check for crashes:
```bash
grep "ERROR" move_media_audit.log | tail -10
```

### Large log files

Compress old logs:
```bash
gzip move_media_audit_2025-*.log
```

Archive to external storage:
```bash
rsync -av *.log.gz backup-server:/archives/
```

## Summary

Audit logging provides:
- ✅ Complete operation history
- ✅ Disaster recovery capability
- ✅ Compliance and accountability
- ✅ Debugging and analysis
- ✅ Minimal performance impact
- ✅ Append-only security
- ✅ Structured, parseable format

All media management scripts now include audit logging by default!
