# Neo4j Export to Django Import Conversion

## Summary

Successfully converted Neo4j export to Django import format.

### Conversion Results

- **Input File**: `~/data/bldrdojo/subgraph_500.json`
- **Output File**: `~/data/bldrdojo/import_data.json`
- **Entities Extracted**: 103 Person entities
- **Relationships Extracted**: 100 (all IS_CHILD_OF type)
- **Note Entities**: 0 (none found in source)

## Conversion Script

Location: `/home/ubuntu/monorepo/data-backend/convert_neo4j_export.py`

### Usage

```bash
python3 convert_neo4j_export.py <input_file> <output_file>

# Example:
python3 convert_neo4j_export.py ~/data/bldrdojo/subgraph_500.json ~/data/bldrdojo/import_data.json
```

### Features

- Extracts Person and Note nodes from Neo4j export
- Preserves all properties (firstName, lastName, gender, dob, description, photo, etc.)
- Converts relationships with proper entity mapping
- Handles multi-line JSON objects in NDJSON format
- Generates Django-compatible import format

## Output Format

The output file follows the Django import/export format:

```json
{
  "export_version": "1.0",
  "export_date": "2026-01-30T...",
  "user": { ... },
  "entities": [ ... ],
  "people": [ ... ],
  "notes": [ ... ],
  "relations": [ ... ],
  "tags": [ ... ]
}
```

### Entity Structure (Person)

```json
{
  "id": "Nidhi Kalra",
  "type": "Person",
  "label": "Person_NidhiKalra",
  "description": "<p>My wife.</p>...",
  "tags": [],
  "created_at": "1980-01-01T00:00Z",
  "updated_at": "2025-09-22T08:27:30.148600Z",
  "firstName": "Nidhi",
  "lastName": "Kalra",
  "gender": "Female",
  "dob": "9/25/1967",
  "photo": "[{...}]"
}
```

### Relationship Structure

```json
{
  "from_entity": "Nidhi Kalra",
  "to_entity": "Lalita Kumar",
  "relation_type": "IS_CHILD_OF"
}
```

## Importing to Django

### Via API

```bash
curl -X POST http://localhost:8001/api/import/ \
     -H 'Authorization: Bearer YOUR_TOKEN' \
     -H 'Content-Type: application/json' \
     -d @~/data/bldrdojo/import_data.json
```

### Via Frontend

1. Log in to the application
2. Click on your user menu (top right)
3. Select "Import"
4. Upload `import_data.json`

## Notes

- The conversion script maps Neo4j node IDs to entity IDs
- All Person-specific fields are preserved
- Relationships are only created if both entities exist in the export
- The script handles duplicate nodes by tracking seen node IDs
- User ID is extracted from Neo4j labels (u_xxx format) if present

## Relationship Types Found

- **IS_CHILD_OF**: 100 relationships

All relationships connect Person entities in a family tree structure.
