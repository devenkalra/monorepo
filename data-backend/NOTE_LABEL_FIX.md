# Note Label Field Fix

## Issue
Error message appearing during tests: `Error indexing note: 'Note' object has no attribute 'label'`

## Root Cause
The codebase had legacy references to a `label` field that no longer exists on the `Note` model. Notes now use the `display` field inherited from the `Entity` base class.

## Files Fixed

### 1. `/people/vector_search_client.py`
**Lines 37, 42**: Changed `note.label` → `note.display`

```python
# Before
content = re.sub('<[^<]+?>', '', note.description) if note.description else note.label
data = {
    'label': note.label,
    ...
}

# After
content = re.sub('<[^<]+?>', '', note.description) if note.description else note.display
data = {
    'label': note.display,  # Note uses 'display' not 'label'
    ...
}
```

### 2. `/people/management/commands/update_conversation_descriptions.py`
**Lines 66, 72**: Changed `conversation.label` → `conversation.display`

```python
# Before
f'  ✓ Updated: {conversation.label}'
f'  ✗ Failed to update {conversation.label}: {e}'

# After
f'  ✓ Updated: {conversation.display}'
f'  ✗ Failed to update {conversation.display}: {e}'
```

### 3. `/people/management/commands/import_chats.py`
**Line 92**: Changed `label=` → `display=`

```python
# Before
note, created = Note.objects.update_or_create(
    user=user,
    label=conv_data['title'],
    defaults={...}
)

# After
note, created = Note.objects.update_or_create(
    user=user,
    display=conv_data['title'],  # Note uses 'display' not 'label'
    defaults={...}
)
```

### 4. `/people/vector_search.py`
**Line 64**: Changed `turn.conversation.label` → `turn.conversation.display`

```python
# Before
metadata = {
    'conversation_label': turn.conversation.label,
    ...
}

# After
metadata = {
    'conversation_label': turn.conversation.display,  # Note uses 'display' not 'label'
    ...
}
```

## Impact

### Before Fix
- ❌ Error message on every Note creation/update
- ❌ Notes may not be indexed properly in vector search
- ❌ Conversation import may fail
- ❌ Conversation description updates may fail

### After Fix
- ✅ No error messages
- ✅ Notes indexed correctly
- ✅ All 37 tests passing
- ✅ Clean test output

## Verification

### Test Results
```bash
./tests/run_tests.sh

# Output:
# Ran 37 tests in 95.861s
# OK
# ✓ No "Error indexing note" messages
```

### Affected Features
- ✅ Note creation/update
- ✅ Vector search indexing
- ✅ Conversation import (ChatGPT/Claude)
- ✅ Conversation description updates

## Related Issues

This fix resolves:
- Bug #5 from `BUGS_FOUND_BY_TESTS.md`
- Note indexing errors in test output
- Potential vector search failures for Notes

## Migration Note

The `label` field was likely removed in a previous migration (`0018_remove_entity_label.py` exists in `migrations.backup/`). This fix updates all remaining code references to use the current `display` field.

## Testing

All integration tests now pass cleanly:
- ✅ 21 core tests
- ✅ 1 cross-user import/export test
- ✅ 9 entity type CRUD tests
- ✅ 6 file upload tests
- ✅ 1 stress test

**Total**: 37 tests, all passing, no errors.
