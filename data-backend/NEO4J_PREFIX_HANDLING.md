# Neo4j Entity Type Prefix Handling

## Overview
The Neo4j conversion script (`convert_neo4j_test.py`) automatically handles the `pkg_` prefix used in Neo4j node labels and converts them to the appropriate Django entity types.

## Supported Entity Type Mappings

| Neo4j Label | Django Type | Notes |
|-------------|-------------|-------|
| `pkg_Person` | `Person` | Full person entity with name, DOB, emails, etc. |
| `pkg_Note` | `Note` | Note entity with date field |
| `pkg_Event` | `Note` | Events are converted to Notes |
| `pkg_Location` | `Location` | Location with address fields |
| `pkg_Movie` | `Movie` | Movie with year, language, country |
| `pkg_Book` | `Book` | Book with year, language, country, summary |
| `pkg_Container` | `Container` | Generic container entity |
| `pkg_Asset` | `Asset` | Asset with value and acquired_on date |
| `pkg_Org` | `Org` | Organization with name and kind |

## How It Works

### 1. Label Detection
The script identifies entity nodes by checking for the `pkg_` prefix:

```python
def is_entity_node(labels):
    """Check if node is an entity (not system node like __TAG, Feedback, etc.)"""
    return any(label.startswith('pkg_') for label in labels)
```

### 2. Type Extraction
The entity type is extracted by stripping the `pkg_` prefix:

```python
def get_entity_type(labels):
    """
    Extract entity type from labels.
    Handles both pkg_ prefixed labels and returns the base type.
    
    Examples:
        ['pkg_Person', 'u_123'] -> 'Person'
        ['pkg_Note', 'u_456'] -> 'Note'
        ['pkg_Event', 'u_789'] -> 'Event'
    """
    for label in labels:
        if label.startswith('pkg_'):
            return label[4:]  # Remove 'pkg_' prefix
    return None
```

### 3. Entity Conversion
Once the type is extracted, the script converts the Neo4j node to the appropriate Django entity format:

```python
if entity_type == 'Person':
    person_data = {
        'id': entity_uuid,
        'type': 'Person',
        'first_name': props.get('firstName', ''),
        'last_name': props.get('lastName', ''),
        # ... other Person fields
    }
    people_by_id[entity_uuid] = person_data

elif entity_type == 'Note':
    note_data = {
        'id': entity_uuid,
        'type': 'Note',
        'date': props.get('date'),
        # ... other Note fields
    }
    notes_by_id[entity_uuid] = note_data

# ... similar for other types
```

## Special Cases

### Event → Note Mapping
Events (`pkg_Event`) are automatically converted to Notes:

```python
elif entity_type == 'Event':
    # Treat Event as Note
    event_data = {
        **common_data,
        'type': 'Note',  # Changed to Note
        'date': props.get('date', props.get('eventDate'))
    }
    notes_by_id[entity_uuid] = event_data
```

### Unknown Types
If an entity type is not recognized, it's logged in the skip log:

```python
else:
    # Unknown entity type - store as generic entity
    print(f"  Warning: Unknown entity type '{entity_type}' for node {node_id}")
    skipped_log['unknown_entity_types'].append({
        'node_id': node_id,
        'entity_type': entity_type,
        'labels': labels,
        'display': props.get('display', props.get('label', '')),
        'properties': props
    })
```

## User Identification
In addition to the `pkg_` prefix, nodes also have user-specific labels with the `u_` prefix:

```python
def extract_user_id(labels):
    """Extract user ID from labels"""
    for label in labels:
        if label.startswith('u_'):
            return label[2:]  # Remove 'u_' prefix
    return None
```

Example node labels: `['pkg_Person', 'u_bob123']`
- `pkg_Person` → Entity type is `Person`
- `u_bob123` → User ID is `bob123`

## Adding New Entity Types

To add support for a new entity type:

1. **No changes needed to prefix handling** - The `get_entity_type()` function automatically strips `pkg_`
2. **Add conversion logic** in the entity handling section:

```python
elif entity_type == 'NewType':
    new_type_data = {
        **common_data,
        'custom_field': props.get('customField', ''),
        # ... other fields
    }
    new_types_by_id[entity_uuid] = new_type_data
    node_count += 1
```

3. **Add to output** in the final JSON generation section

## Files
- **Conversion Script**: `/home/ubuntu/monorepo/data-backend/convert_neo4j_test.py`
- **Input**: `/home/ubuntu/data/bldrdojo/full_graph.json` (Neo4j export)
- **Output**: `/home/ubuntu/data/bldrdojo/full_import.json` (Django import format)
- **Skip Log**: `/home/ubuntu/data/bldrdojo/full_import_skip_log.json` (Detailed skip information)
