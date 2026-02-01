# Export Functionality Fix

## Issues Fixed

### Issue 1: Missing Entity Types
The export endpoint was not including the new entity types (Location, Movie, Book, Container, Asset, Org) that were added to the system. Only Person and Note entities were being exported.

### Issue 2: Wrong ViewSet Location
The export method was accidentally placed in the `OrgViewSet` class instead of the `EntityViewSet` class, causing it to be accessible at the wrong URL (`/api/orgs/export/` instead of `/api/entities/export/`).

## Root Cause
The `export()` action in `EntityViewSet` was only querying and serializing `Person` and `Note` entities, missing all the newer entity types added to the system.

## Solution
Updated the export endpoint to include all entity types:

### Before
```python
# Gather all user's data
entities = Entity.objects.filter(user=request.user)
people = Person.objects.filter(user=request.user)
notes = Note.objects.filter(user=request.user)
relations = EntityRelation.objects.filter(...)
tags = Tag.objects.all()

export_data = {
    'export_version': '1.0',
    'export_date': datetime.now().isoformat(),
    'user': {...},
    'entities': EntitySerializer(entities, many=True).data,
    'people': PersonSerializer(people, many=True).data,
    'notes': NoteSerializer(notes, many=True).data,
    'relations': EntityRelationSerializer(relations, many=True).data,
    'tags': TagSerializer(tags, many=True).data,
}
```

### After
```python
# Gather all user's data
entities = Entity.objects.filter(user=request.user)
people = Person.objects.filter(user=request.user)
notes = Note.objects.filter(user=request.user)
locations = Location.objects.filter(user=request.user)
movies = Movie.objects.filter(user=request.user)
books = Book.objects.filter(user=request.user)
containers = Container.objects.filter(user=request.user)
assets = Asset.objects.filter(user=request.user)
orgs = Org.objects.filter(user=request.user)
relations = EntityRelation.objects.filter(...)
tags = Tag.objects.all()

export_data = {
    'export_version': '1.0',
    'export_date': datetime.now().isoformat(),
    'user': {...},
    'entities': EntitySerializer(entities, many=True).data,
    'people': PersonSerializer(people, many=True).data,
    'notes': NoteSerializer(notes, many=True).data,
    'locations': LocationSerializer(locations, many=True).data,
    'movies': MovieSerializer(movies, many=True).data,
    'books': BookSerializer(books, many=True).data,
    'containers': ContainerSerializer(containers, many=True).data,
    'assets': AssetSerializer(assets, many=True).data,
    'orgs': OrgSerializer(orgs, many=True).data,
    'relations': EntityRelationSerializer(relations, many=True).data,
    'tags': TagSerializer(tags, many=True).data,
}
```

## Export Format
The export now includes all entity types in separate arrays:

```json
{
  "export_version": "1.0",
  "export_date": "2026-01-31T12:17:00.000000",
  "user": {
    "username": "bob",
    "email": "bob@example.com"
  },
  "entities": [...],
  "people": [...],
  "notes": [...],
  "locations": [...],
  "movies": [...],
  "books": [...],
  "containers": [...],
  "assets": [...],
  "orgs": [...],
  "relations": [...],
  "tags": [...]
}
```

## Testing
To test the export:

1. **Via API**:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:8000/api/entities/export/ \
     -o export.json
```

2. **Via Frontend**: 
   - Click the export button in the UI
   - File will download with all entity types included

## Files Modified
- `/home/ubuntu/monorepo/data-backend/people/views.py` 
  - Moved `export()` action from `OrgViewSet` to `EntityViewSet`
  - Added all missing entity types to the export
- `/home/ubuntu/monorepo/data-backend/frontend/src/components/UserMenu.jsx`
  - Fixed export endpoint from `/api/notes/export/` to `/api/entities/export/`

## Correct URL
The export is now accessible at:
- **Correct**: `/api/entities/export/` (EntityViewSet)
- ~~Incorrect~~: `/api/orgs/export/` (was wrongly placed here)

## Compatibility
- Export format version remains `1.0`
- Backward compatible - old imports will still work
- New entity types are optional in the export format
- Import endpoint already supports all these entity types

## Related
This fix ensures that the export/import cycle works correctly for all entity types, not just Person and Note.
