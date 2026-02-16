# Task Cancellation Behavior

## Overview

All async tasks (import, export, reindex) support cancellation with proper cleanup and rollback.

## How Cancellation Works

### 1. User Clicks Cancel Button

Frontend calls: `POST /api/entities/tasks/{task_id}/cancel/`

### 2. Backend Marks Task for Cancellation

- Sets `task_cancel_{task_id}` flag in Redis cache
- Calls `result.revoke(terminate=True)` on Celery task
- Returns immediately to user

### 3. Task Checks for Cancellation

Tasks check `check_task_cancelled(task_id)` at these points:

**Import Task:**
- Every tag (every 10 tags)
- **Every entity** (every 1-3 entities depending on batch size)
- Every relation (every 10 relations)

**Export Task:**
- Before gathering data
- Before serialization

**Reindex Task:**
- Every entity (every 10 entities)

### 4. Task Handles Cancellation

When cancellation is detected:

1. **Updates progress**: Status set to 'cancelled'
2. **Raises exception**: `Exception('Import cancelled by user')`
3. **Transaction rollback**: Django's `transaction.atomic()` rolls back ALL database changes
4. **Returns result**: `{'success': False, 'cancelled': True, 'message': '...'}`

## Import Task Cancellation

### What Gets Rolled Back

✅ **Everything!** The entire import is wrapped in `transaction.atomic()`:

- All tags created/updated
- All entities created/updated (Person, Note, Location, etc.)
- All relations created
- All tag counts adjusted

### Database State After Cancellation

**Before Import**: 10 entities
**During Import**: 50 entities created, then cancelled
**After Cancellation**: 10 entities (rolled back to original state)

### Progress Updates During Cancellation

```
1. "Importing people: 45/100" (processing)
2. User clicks Cancel
3. "Import cancelled during people - rolling back" (cancelled)
4. Transaction rolls back
5. "Import cancelled - all changes rolled back" (cancelled, final)
```

### Frontend Behavior

```javascript
// ProgressModal detects cancelled status
if (progressData.status === 'cancelled') {
  // Shows yellow warning icon
  // Displays "Import was cancelled" message
  // User clicks Close button
}
```

## Export Task Cancellation

### What Happens

- Export data is NOT saved to cache
- No database changes (export is read-only)
- Task returns early

### No Rollback Needed

Export is read-only, so cancellation just stops the task.

## Reindex Task Cancellation

### What Happens

- Stops indexing entities
- Returns partial results: `{'indexed': 45, 'total': 100, 'cancelled': True}`

### MeiliSearch State

⚠️ **Partial indexing remains!**

- Entities indexed before cancellation stay in MeiliSearch
- Entities not yet indexed are missing from search
- User can run reindex again to complete

### No Rollback

MeiliSearch doesn't support transactions, so partial indexing is expected behavior.

## Cancellation Timing

### Fast Cancellation (< 1 second)

- User clicks Cancel
- Task checks cancellation on next checkpoint
- Rolls back immediately

### Slow Cancellation (1-5 seconds)

- User clicks Cancel
- Task is in middle of entity import
- Waits for current entity to complete
- Checks cancellation
- Rolls back

### Very Slow Cancellation (> 5 seconds)

- Celery's `revoke(terminate=True)` forcefully kills the worker process
- Transaction is automatically rolled back by database
- Progress shows "cancelled" status

## Error Handling

### Cancellation Exception

```python
try:
    with transaction.atomic():
        # ... import logic ...
        if check_task_cancelled(task_id):
            raise Exception('Import cancelled by user')
except Exception as e:
    if 'cancelled by user' in str(e).lower():
        # Clean cancellation - transaction already rolled back
        return {'success': False, 'cancelled': True}
    else:
        # Real error - re-raise
        raise
```

### Failed Cancellation

If cancellation check fails (Redis down):
- Task continues running
- User sees "cancelling..." in UI
- Task eventually completes or times out

## Testing Cancellation

### Manual Test

1. Start import of large file (1000+ entities)
2. Click Cancel button after 2-3 seconds
3. Verify:
   - Progress shows "cancelled"
   - Database has NO new entities
   - Page reload shows original data

### Automated Test

```python
def test_import_cancellation():
    # Start import
    task = import_entities_async.delay(user_id, large_data)
    
    # Wait for it to start
    time.sleep(1)
    
    # Cancel it
    cache.set(f'task_cancel_{task.id}', True)
    
    # Wait for cancellation
    time.sleep(2)
    
    # Verify no entities were created
    assert Entity.objects.filter(user=user).count() == original_count
```

## Best Practices

### For Users

1. **Cancel early** - The sooner you cancel, the less work is wasted
2. **Wait for confirmation** - Don't close browser until "cancelled" status shows
3. **Re-import if needed** - Cancellation is safe, you can retry immediately

### For Developers

1. **Check frequently** - Add cancellation checks every few items
2. **Use transactions** - Wrap all database operations in `transaction.atomic()`
3. **Update progress** - Show "rolling back" message during cancellation
4. **Handle gracefully** - Distinguish cancellation from real errors

## Limitations

### What Cancellation Cannot Do

❌ **Cannot undo external API calls** (if any were made)
❌ **Cannot undo MeiliSearch indexing** (no transaction support)
❌ **Cannot undo file uploads** (files remain on disk)
❌ **Cannot undo Neo4j changes** (if not in same transaction)

### Workarounds

For operations that can't be rolled back:
1. Do them AFTER the transaction commits
2. Implement manual cleanup on cancellation
3. Use idempotent operations that can be safely retried

## Summary

| Task | Rollback | Partial State | Safe to Retry |
|------|----------|---------------|---------------|
| Import | ✅ Full | ❌ None | ✅ Yes |
| Export | N/A | ❌ None | ✅ Yes |
| Reindex | ❌ None | ⚠️ Partial | ✅ Yes |

**Key Takeaway**: Import cancellation is **atomic** - either everything imports or nothing does. This prevents partial/corrupted data in your database.
