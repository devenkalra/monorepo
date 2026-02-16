# Delete Files and Audit Logging Feature

## Overview
Added file deletion capability with database cleanup and comprehensive audit logging for all operations.

## Features Implemented

### 1. Delete Files Operation

#### UI Components
- **Delete Files Button**: Added to Bulk Operations section
- **DeleteFilesDialog**: New dialog for file deletion with safety features

#### Dialog Features
- Warning message about permanent deletion
- File count display
- Options:
  - Delete from database (if file exists in DB)
  - Dry run mode (enabled by default for safety)
- Confirmation dialog before actual deletion (when not in dry run)
- Real-time output showing progress

#### Deletion Process
1. Checks if file exists
2. Calculates file hash for audit trail
3. Looks up file in database
4. Captures metadata before deletion (for audit)
5. Deletes file from filesystem
6. Deletes database record (cascades to metadata and thumbnails)
7. Logs operation to audit table
8. Refreshes file list in main app after completion

#### Safety Features
- Dry run enabled by default
- Explicit confirmation dialog for non-dry-run deletions
- Detailed logging of each operation
- Error handling with detailed messages
- Skips already-deleted files gracefully

### 2. Audit Logging System

#### Database Schema
New `audit_log` table with the following fields:
- `id`: Primary key
- `timestamp`: When operation occurred (ISO format)
- `operation`: Type of operation (delete, move, update_exif, index, etc.)
- `file_path`: Path to the file being operated on
- `file_hash`: SHA256 hash for tracking
- `old_path`: Original path (for move operations)
- `new_path`: New path (for move operations)
- `old_volume`: Original volume (for move operations)
- `new_volume`: New volume (for move operations)
- `metadata_before`: JSON string of metadata before operation
- `metadata_after`: JSON string of metadata after operation
- `success`: Boolean (1 for success, 0 for failure)
- `error_message`: Error details if operation failed
- `additional_info`: Any additional information

#### Indexes
- `idx_audit_timestamp`: For time-based queries
- `idx_audit_operation`: For filtering by operation type
- `idx_audit_file_path`: For finding operations on specific files

#### Audit Function
New `log_audit()` function in `media_utils.py`:
```python
log_audit(
    conn, 
    operation, 
    file_path,
    success=True,
    error_message=None,
    file_hash=None,
    old_path=None,
    new_path=None,
    old_volume=None,
    new_volume=None,
    metadata_before=None,
    metadata_after=None,
    additional_info=None
)
```

### 3. Operations with Audit Logging

#### Delete Operation
Logs:
- File path
- File hash
- Complete metadata before deletion (files, image_metadata, video_metadata)
- File size
- Success/failure status
- Error messages if any

**Note**: Delete operations cannot be reversed, but audit log contains all information about what was deleted.

#### Move Operation
Logs:
- Old path and new path
- Old volume and new volume
- File hash
- Database action taken (updated/inserted)
- Success/failure status

**Reversibility**: Move operations can be reversed by:
1. Finding the audit record
2. Moving file from `new_path` back to `old_path`
3. Updating database record to restore original volume and path

#### Apply EXIF Operation
**Status**: Not yet implemented in audit log
**Reason**: Apply EXIF uses external `apply_exif.py` script
**Future Work**: Would need to modify `apply_exif.py` to log to audit table

#### Index Media Operation
**Status**: Not yet implemented in audit log
**Reason**: Index Media uses external `index_media.py` script
**Future Work**: Would need to modify `index_media.py` to log to audit table

## Usage Examples

### Delete Files
1. Select files in the file list
2. Click "Delete Files" button
3. Review options in dialog
4. For safety, leave "Dry run" checked first
5. Click "Start" to preview what would be deleted
6. Review output
7. Uncheck "Dry run" and click "Start" again
8. Confirm deletion in the warning dialog
9. Files are deleted and records removed from database

### Query Audit Log
```sql
-- Find all delete operations
SELECT * FROM audit_log WHERE operation = 'delete' ORDER BY timestamp DESC;

-- Find all operations on a specific file
SELECT * FROM audit_log WHERE file_path LIKE '%filename%' ORDER BY timestamp;

-- Find all failed operations
SELECT * FROM audit_log WHERE success = 0 ORDER BY timestamp DESC;

-- Find all move operations in the last day
SELECT * FROM audit_log 
WHERE operation = 'move' 
AND timestamp > datetime('now', '-1 day')
ORDER BY timestamp DESC;

-- Get details of what was deleted
SELECT 
    timestamp,
    file_path,
    file_hash,
    metadata_before,
    additional_info
FROM audit_log 
WHERE operation = 'delete'
ORDER BY timestamp DESC;
```

### Reverse a Move Operation
```sql
-- Find the move operation
SELECT id, old_path, new_path, old_volume, new_volume, file_hash
FROM audit_log 
WHERE operation = 'move' 
AND file_path = '/new/path/to/file.jpg'
ORDER BY timestamp DESC 
LIMIT 1;

-- Then use the information to:
-- 1. Move the file back: mv /new/path/to/file.jpg /old/path/to/file.jpg
-- 2. Update database: UPDATE files SET fullpath = '/old/path/to/file.jpg', volume = 'old_volume' WHERE file_hash = 'hash_value'
```

## Files Modified

### `/home/ubuntu/monorepo/scripts/media_process/gui/media_utils.py`
- Added `audit_log` table to schema
- Added indexes for audit table
- Added `log_audit()` function

### `/home/ubuntu/monorepo/scripts/media_process/gui/media_processor_app.py`
- Added "Delete Files" button to Bulk Operations
- Added `delete_files()` method to MediaProcessorApp
- Added `DeleteFilesDialog` class with complete implementation
- Added audit logging to `MoveMediaDialog._process_file()`
- Updated imports to include `json` for metadata serialization

## Future Enhancements

### Short Term
1. Add audit logging to `apply_exif.py` script
2. Add audit logging to `index_media.py` script
3. Add audit logging to duplicate management operations

### Long Term
1. Create an "Audit Viewer" dialog in the GUI to browse audit history
2. Add "Undo" functionality for reversible operations (move, update EXIF)
3. Add audit log export (CSV, JSON)
4. Add audit log cleanup/archival for old records
5. Add audit statistics dashboard
6. Add ability to filter/search audit log from GUI

## Security Considerations

1. **Audit Log Integrity**: The audit log is stored in the same database as the media records. For production use, consider:
   - Write-protecting the audit log (triggers to prevent updates/deletes)
   - Storing audit log in a separate database
   - Regular backups of audit log

2. **Sensitive Information**: The audit log may contain file paths and metadata. Ensure:
   - Database file has appropriate permissions
   - Audit log is included in backup/restore procedures
   - Consider data retention policies

3. **Performance**: With many operations, the audit log can grow large:
   - Indexes are in place for common queries
   - Consider periodic archival of old audit records
   - Monitor database size

## Testing Recommendations

1. **Delete Operation**:
   - Test dry run mode
   - Test actual deletion
   - Verify database records are removed
   - Verify audit log is created
   - Test with files not in database
   - Test with files already deleted

2. **Audit Logging**:
   - Verify all move operations are logged
   - Verify all delete operations are logged
   - Verify failed operations are logged with error messages
   - Test audit log queries
   - Verify metadata_before contains complete information

3. **Integration**:
   - Test file list refresh after deletion
   - Test multiple file deletion
   - Test deletion with database connection issues
   - Test with read-only files
