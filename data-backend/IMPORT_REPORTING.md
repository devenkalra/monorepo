# Import Detailed Reporting

## Overview

The import functionality now provides comprehensive reporting of what was imported, what was skipped, and why.

## Response Format

When you import a file, you'll receive a detailed JSON response with the following structure:

```json
{
  "success": true,
  "message": "Import completed: 150 created, 50 updated, 20 skipped",
  "stats": {
    "file_summary": { ... },
    "summary": { ... },
    "tags_created": 45,
    "tags_skipped": 10,
    "entities_created": 30,
    "entities_updated": 10,
    "entities_skipped": 5,
    "people_created": 25,
    "people_updated": 8,
    "people_skipped": 3,
    ...
    "errors": [],
    "warnings": []
  }
}
```

## Detailed Breakdown

### File Summary

Shows what was in the imported file:

```json
"file_summary": {
  "tags_in_file": 55,
  "entities_in_file": 45,
  "people_in_file": 25,
  "notes_in_file": 30,
  "locations_in_file": 15,
  "movies_in_file": 10,
  "books_in_file": 8,
  "containers_in_file": 5,
  "assets_in_file": 3,
  "orgs_in_file": 12,
  "relations_in_file": 40
}
```

### Summary Totals

High-level overview of what happened:

```json
"summary": {
  "total_entities_in_file": 153,
  "total_created": 120,
  "total_updated": 25,
  "total_skipped": 8,
  "total_errors": 0,
  "total_warnings": 2,
  "tags_created": 45,
  "tags_skipped": 10,
  "relations_created": 35,
  "relations_skipped": 5
}
```

### Per-Entity-Type Breakdown

For each entity type, you get three counters:

- **`created`**: New entities that were created
- **`updated`**: Existing entities that were modified (data changed)
- **`skipped`**: Existing entities that were identical (no changes needed)

```json
"people_created": 25,
"people_updated": 8,
"people_skipped": 3,

"notes_created": 30,
"notes_updated": 5,
"notes_skipped": 2,

"orgs_created": 12,
"orgs_updated": 3,
"orgs_skipped": 1,
...
```

### Errors and Warnings

#### Errors

Errors indicate that an entity or relation failed to import:

```json
"errors": [
  "Person 'John Doe' (abc-123): IntegrityError: duplicate key value",
  "Relation IS_FRIEND_OF (xyz-789): ValidationError: invalid relation type"
]
```

Each error includes:
- Entity type or "Relation"
- Entity name/display
- Entity ID
- Error message

#### Warnings

Warnings indicate non-critical issues:

```json
"warnings": [
  "Relation skipped: from_entity abc-123 not found",
  "Relation skipped: to_entity xyz-789 not found"
]
```

## Understanding the Counts

### Why Would Entities Be Skipped?

Entities are skipped when:
1. **Already exists with same data**: The entity with that ID already exists in the database and all fields match exactly
2. **No changes needed**: The entity exists and importing it wouldn't change anything

### Why Would Entities Be Updated?

Entities are updated when:
1. **Entity exists but data changed**: The entity ID exists but one or more fields have different values
2. **Tags changed**: The entity's tags were modified
3. **Any field changed**: Any field (display, description, etc.) has a different value

### Why Would Relations Be Skipped?

Relations are skipped when:
1. **Already exists**: A relation with the same from_entity, to_entity, and relation_type already exists
2. **Missing entities**: One or both entities in the relation don't exist (warning generated)

## Example Scenarios

### Scenario 1: Fresh Import (No Existing Data)

**File**: 100 people, 50 notes, 20 relations

**Result**:
```json
{
  "summary": {
    "total_created": 150,
    "total_updated": 0,
    "total_skipped": 0,
    "total_errors": 0
  },
  "people_created": 100,
  "notes_created": 50,
  "relations_created": 20
}
```

**Interpretation**: Everything was new, so everything was created.

---

### Scenario 2: Re-importing Same File

**File**: Same 100 people, 50 notes, 20 relations

**Result**:
```json
{
  "summary": {
    "total_created": 0,
    "total_updated": 0,
    "total_skipped": 150,
    "total_errors": 0
  },
  "people_skipped": 100,
  "notes_skipped": 50,
  "relations_skipped": 20
}
```

**Interpretation**: Everything already exists with identical data, so everything was skipped.

---

### Scenario 3: Partial Update

**File**: 100 people (50 new, 30 modified, 20 unchanged), 50 notes (all new)

**Result**:
```json
{
  "summary": {
    "total_created": 100,
    "total_updated": 30,
    "total_skipped": 20,
    "total_errors": 0
  },
  "people_created": 50,
  "people_updated": 30,
  "people_skipped": 20,
  "notes_created": 50
}
```

**Interpretation**: 
- 50 people were new (created)
- 30 people existed but had changes (updated)
- 20 people existed and were identical (skipped)
- All 50 notes were new (created)

---

### Scenario 4: Import with Errors

**File**: 100 people, 50 notes, 20 relations

**Result**:
```json
{
  "summary": {
    "total_created": 145,
    "total_updated": 0,
    "total_skipped": 0,
    "total_errors": 5,
    "total_warnings": 2
  },
  "people_created": 95,
  "notes_created": 50,
  "relations_created": 18,
  "relations_skipped": 2,
  "errors": [
    "Person 'John Doe' (abc-123): IntegrityError: duplicate key",
    "Person 'Jane Smith' (def-456): ValidationError: invalid email",
    "Person 'Bob Jones' (ghi-789): ValidationError: missing required field",
    "Relation IS_FRIEND_OF (xyz-1): ValidationError: invalid relation type",
    "Relation IS_COLLEAGUE_OF (xyz-2): ValidationError: invalid relation type"
  ],
  "warnings": [
    "Relation skipped: from_entity missing-123 not found",
    "Relation skipped: to_entity missing-456 not found"
  ]
}
```

**Interpretation**:
- 95 of 100 people created successfully (5 failed)
- All 50 notes created successfully
- 18 of 20 relations created (2 had missing entities)
- 5 errors occurred (3 people, 2 relations)
- 2 warnings about missing entities

---

## Using the Report

### In the UI

The frontend can display a summary like:

```
Import Complete!

✅ 145 entities created
✅ 30 entities updated
ℹ️  20 entities skipped (no changes)
❌ 5 errors
⚠️  2 warnings

Details:
- People: 95 created, 30 updated, 20 skipped
- Notes: 50 created
- Locations: 15 created
- Relations: 18 created, 2 skipped

Errors:
- Person 'John Doe': duplicate key
- Person 'Jane Smith': invalid email
- ...

Warnings:
- Relation skipped: from_entity not found
- ...
```

### For Debugging

If imports are not working as expected:

1. **Check `file_summary`**: Verify the file contains what you expect
2. **Check `summary.total_created`**: See how many were actually created
3. **Check `summary.total_skipped`**: See if entities are being skipped
4. **Check `errors`**: See specific failures with entity names and IDs
5. **Check `warnings`**: See non-critical issues

### Example: "Why weren't my entities imported?"

**Check the response**:

```json
{
  "file_summary": {
    "people_in_file": 100
  },
  "people_created": 0,
  "people_updated": 0,
  "people_skipped": 100
}
```

**Answer**: All 100 people were skipped because they already exist with identical data.

---

## API Endpoint

**POST** `/api/entities/import_data/`

**Request**:
```
Content-Type: multipart/form-data

file: <JSON file>
```

**Response** (Success):
```json
{
  "success": true,
  "message": "Import completed: 150 created, 50 updated, 20 skipped",
  "stats": { ... }
}
```

**Response** (Error):
```json
{
  "error": "Import failed: Invalid JSON file"
}
```

---

## Logging

The import process also logs detailed information to the server logs:

```
INFO: Starting import for user bob@example.com
INFO: Importing 100 people
INFO: Created people 'John Doe' (abc-123)
INFO: Updated people 'Jane Smith' (def-456)
INFO: Skipped people 'Bob Jones' (ghi-789) - already exists with same data
INFO: Importing 50 notes
INFO: Created notes 'Meeting Notes' (xyz-123)
...
INFO: Import completed: 150 created, 50 updated, 20 skipped, 0 errors
```

---

## Best Practices

### 1. Always Check the Response

Don't just check `success: true` - look at the stats to understand what happened.

### 2. Handle Errors Gracefully

If `total_errors > 0`, show the user which entities failed and why.

### 3. Inform About Skipped Entities

If `total_skipped > 0`, let the user know that some entities were already up-to-date.

### 4. Log for Debugging

Keep the full response for debugging if users report issues.

### 5. Validate Before Import

Check `file_summary` to ensure the file contains expected data before processing.

---

## Summary

The new import reporting provides:

✅ **Complete visibility**: Know exactly what was imported, updated, or skipped  
✅ **Detailed errors**: Specific entity names and IDs for failures  
✅ **Warnings**: Non-critical issues that didn't stop the import  
✅ **File summary**: What was in the file vs what was processed  
✅ **Per-type breakdown**: See results for each entity type separately  

This makes debugging import issues much easier and gives users confidence that their data was imported correctly.
