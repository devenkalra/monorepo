#!/usr/bin/env python3
"""
Convert Neo4j export to Django import format
Extracts Person and Note nodes with their relationships
"""

import json
import sys
import uuid
import random
from datetime import datetime
from collections import defaultdict

# Generate a unique namespace for this import to avoid UUID collisions
# This ensures each import gets unique IDs even if the source data is the same
IMPORT_NAMESPACE = str(uuid.uuid4())

def extract_node_data(node):
    """Extract relevant data from a Neo4j node"""
    props = node.get('properties', {})
    labels = node.get('labels', [])
    
    # Determine type from labels
    node_type = None
    for label in labels:
        if label.startswith('t_'):
            node_type = label[2:]  # Remove 't_' prefix
            break
    
    if not node_type:
        return None
    
    # Extract user ID from labels (u_xxx)
    user_id = None
    for label in labels:
        if label.startswith('u_'):
            user_id = label[2:]
            break
    
    return {
        'neo4j_id': node.get('id'),
        'type': node_type,
        'properties': props,
        'user_id': user_id,
        'labels': labels
    }

def convert_person_to_entity(person_data):
    """Convert Person node to Entity format"""
    props = person_data['properties']
    
    # Generate UUID from neo4j_id using the import-specific namespace
    # This ensures different imports get different UUIDs (no collisions between users)
    original_id = props.get('id', person_data['neo4j_id'])
    namespace = uuid.UUID(IMPORT_NAMESPACE)
    entity_id = str(uuid.uuid5(namespace, f"person-{original_id}"))
    
    # Parse date of birth
    dob = props.get('dob', '')
    dob_formatted = None
    if dob:
        try:
            # Try to parse various date formats
            from datetime import datetime as dt
            for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y']:
                try:
                    dob_formatted = dt.strptime(dob, fmt).strftime('%Y-%m-%d')
                    break
                except ValueError:
                    continue
        except:
            pass
    
    # Parse photo data
    photos = []
    photo_str = props.get('photo', '')
    if photo_str:
        try:
            import json as json_lib
            photos = json_lib.loads(photo_str) if isinstance(photo_str, str) else photo_str
        except:
            pass
    
    return {
        'id': entity_id,
        'type': 'Person',
        'label': props.get('label', props.get('display', f"Person_{entity_id}")),
        'description': props.get('description', ''),
        'tags': [],  # Will add tags if needed
        'created_at': props.get('created_at', datetime.now().isoformat()),
        'updated_at': props.get('modified_at', datetime.now().isoformat()),
        # Person-specific fields (matching Django model)
        'first_name': props.get('firstName', ''),
        'last_name': props.get('lastName', ''),
        'gender': props.get('gender', 'Unspecified'),
        'dob': dob_formatted,
        'emails': [],
        'phones': [],
        'profession': '',
        'photos': photos,
        'urls': [],
        'attachments': [],
        'locations': [],
    }

def convert_note_to_entity(note_data):
    """Convert Note node to Entity format"""
    props = note_data['properties']
    
    # Generate UUID from neo4j_id using the import-specific namespace
    original_id = props.get('id', note_data['neo4j_id'])
    namespace = uuid.UUID(IMPORT_NAMESPACE)
    entity_id = str(uuid.uuid5(namespace, f"note-{original_id}"))
    
    return {
        'id': entity_id,
        'type': 'Note',
        'label': props.get('label', props.get('title', f"Note_{entity_id}")),
        'description': props.get('description', props.get('content', '')),
        'tags': props.get('tags', '').split(',') if props.get('tags') else [],
        'created_at': props.get('created_at', datetime.now().isoformat()),
        'updated_at': props.get('modified_at', datetime.now().isoformat()),
        'date': props.get('date', None),
        'photos': [],
        'urls': [],
        'attachments': [],
        'locations': [],
    }

def convert_relationship(rel_data, node_map):
    """Convert Neo4j relationship to EntityRelation format"""
    props = rel_data.get('properties', {})
    rel_type = props.get('type', rel_data.get('label', ''))
    
    # Get start and end node IDs
    start_id = rel_data.get('start', {}).get('id')
    end_id = rel_data.get('end', {}).get('id')
    
    if not start_id or not end_id:
        return None
    
    # Map to entity IDs
    from_entity = node_map.get(start_id)
    to_entity = node_map.get(end_id)
    
    if not from_entity or not to_entity:
        return None
    
    return {
        'from_entity': from_entity,
        'to_entity': to_entity,
        'relation_type': rel_type,
    }

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else '/home/ubuntu/data/bldrdojo/subgraph_500.json'
    output_file = sys.argv[2] if len(sys.argv) > 2 else '/home/ubuntu/data/bldrdojo/import_data.json'
    
    print(f"Reading from: {input_file}")
    print(f"Writing to: {output_file}")
    
    # Collections
    entities = []
    people = []
    notes = []
    relations = []
    
    # Map Neo4j node ID to entity ID
    node_map = {}
    
    # Track unique nodes
    seen_nodes = set()
    
    # Read NDJSON file (multi-line JSON objects)
    with open(input_file, 'r') as f:
        content = f.read()
        
    # Split by '}\n{' to separate JSON objects
    json_objects = content.strip().split('}\n{')
    
    # Fix the splits by adding back the braces
    for i in range(len(json_objects)):
        if i > 0:
            json_objects[i] = '{' + json_objects[i]
        if i < len(json_objects) - 1:
            json_objects[i] = json_objects[i] + '}'
    
    for line_num, json_str in enumerate(json_objects, 1):
        if not json_str.strip():
            continue
        
        try:
            record = json.loads(json_str)
            
            # Process node 'a' if present
            if 'a' in record and record['a'].get('type') == 'node':
                node_data = extract_node_data(record['a'])
                if node_data and node_data['neo4j_id'] not in seen_nodes:
                    seen_nodes.add(node_data['neo4j_id'])
                    
                    if node_data['type'] == 'Person':
                        entity = convert_person_to_entity(node_data)
                        # Only add to people array, not entities (Person extends Entity)
                        people.append(entity)
                        node_map[node_data['neo4j_id']] = entity['id']
                        
                    elif node_data['type'] == 'Note':
                        entity = convert_note_to_entity(node_data)
                        # Only add to notes array, not entities (Note extends Entity)
                        notes.append(entity)
                        node_map[node_data['neo4j_id']] = entity['id']
            
            # Process node 'b' if present
            if 'b' in record and record['b'].get('type') == 'node':
                node_data = extract_node_data(record['b'])
                if node_data and node_data['neo4j_id'] not in seen_nodes:
                    seen_nodes.add(node_data['neo4j_id'])
                    
                    if node_data['type'] == 'Person':
                        entity = convert_person_to_entity(node_data)
                        # Only add to people array, not entities (Person extends Entity)
                        people.append(entity)
                        node_map[node_data['neo4j_id']] = entity['id']
                        
                    elif node_data['type'] == 'Note':
                        entity = convert_note_to_entity(node_data)
                        # Only add to notes array, not entities (Note extends Entity)
                        notes.append(entity)
                        node_map[node_data['neo4j_id']] = entity['id']
            
            # Process relationship if present
            if 'r' in record and record['r'].get('type') == 'relationship':
                rel = convert_relationship(record['r'], node_map)
                if rel:
                    relations.append(rel)
                    
        except json.JSONDecodeError as e:
            print(f"Error parsing object {line_num}: {e}")
            continue
        except Exception as e:
            print(f"Error processing object {line_num}: {e}")
            continue
    
    # Create output in Django import format
    # Note: entities array is empty because Person and Note extend Entity
    # They should only be in their specific arrays
    output = {
        "export_version": "1.0",
        "export_date": datetime.now().isoformat(),
        "user": {
            "username": "imported_user",
            "email": "import@bldrdojo.com",
            "id": "00000000-0000-0000-0000-000000000000"
        },
        "entities": [],  # Empty - Person and Note go in their specific arrays
        "people": people,
        "notes": notes,
        "relations": relations,
        "tags": []  # Extract unique tags if needed
    }
    
    # Write output
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✅ Conversion complete!")
    print(f"   People: {len(people)}")
    print(f"   Notes: {len(notes)}")
    print(f"   Relations: {len(relations)}")
    print(f"\nOutput written to: {output_file}")

if __name__ == '__main__':
    main()
