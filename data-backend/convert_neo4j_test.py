#!/usr/bin/env python3
"""
Convert Neo4j test export to Django import format
Handles all entity types, relationships, and tags
"""
import json
import uuid
from datetime import datetime
from collections import defaultdict

# Generate a unique namespace for this conversion
NAMESPACE_UUID = uuid.uuid4()

# Detailed logging for skipped items
skipped_log = {
    'unknown_entity_types': [],
    'non_entity_nodes': [],
    'skipped_relations': [],
    'tag_relations_without_entity': [],
    'tag_relations_without_tag': []
}

def generate_uuid(neo4j_id, user_id=None):
    """Generate deterministic UUID from Neo4j ID"""
    namespace_str = f"{NAMESPACE_UUID}:{user_id or 'default'}"
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, namespace_str)
    return str(uuid.uuid5(namespace, str(neo4j_id)))

def parse_date(date_str):
    """Parse various date formats to ISO format"""
    if not date_str:
        return None
    
    # Handle different date formats
    for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S.%fZ']:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime('%Y-%m-%d')
        except:
            continue
    return None

def extract_user_id(labels):
    """Extract user ID from labels"""
    for label in labels:
        if label.startswith('u_'):
            return label[2:]  # Remove 'u_' prefix
    return None

def is_entity_node(labels):
    """Check if node is an entity (not system node like __TAG, Feedback, etc.)"""
    # Entity nodes have pkg_ prefix
    return any(label.startswith('pkg_') for label in labels)

def get_entity_type(labels):
    """Extract entity type from labels"""
    for label in labels:
        if label.startswith('pkg_'):
            return label[4:]  # Remove 'pkg_' prefix
    return None

def is_tag_node(labels):
    """Check if node is a tag"""
    return '__TAG' in labels

def parse_json_field(value):
    """Parse JSON string field"""
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except:
        return []

# Storage for converted data
entities_by_id = {}
people_by_id = {}
notes_by_id = {}
locations_by_id = {}
movies_by_id = {}
books_by_id = {}
containers_by_id = {}
assets_by_id = {}
orgs_by_id = {}
tags_by_name = {}
relations = []

# Track Neo4j ID to Django UUID mapping
id_mapping = {}

input_file = '/home/ubuntu/data/bldrdojo/full_graph.json'
output_file = '/home/ubuntu/data/bldrdojo/full_import.json'

print("Converting Neo4j export to Django import format...")
print(f"Namespace UUID for this conversion: {NAMESPACE_UUID}\n")

# First pass: Convert nodes
node_count = 0
tag_count = 0
other_node_count = 0

with open(input_file, 'r') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        
        try:
            obj = json.loads(line)
            
            if obj.get('type') == 'node':
                node_id = obj['id']
                labels = obj.get('labels', [])
                props = obj.get('properties', {})
                
                user_id = extract_user_id(labels)
                
                # Handle Tag nodes
                if is_tag_node(labels):
                    tag_name = props.get('name', props.get('path', ''))
                    if tag_name and tag_name not in tags_by_name:
                        tags_by_name[tag_name] = {
                            'name': tag_name,
                            'neo4j_id': node_id
                        }
                        tag_count += 1
                    continue
                
                # Handle Entity nodes
                if is_entity_node(labels):
                    entity_type = get_entity_type(labels)
                    entity_uuid = generate_uuid(node_id, user_id)
                    id_mapping[node_id] = entity_uuid
                    
                    # Common fields
                    common_data = {
                        'id': entity_uuid,
                        'type': entity_type,
                        'display': props.get('display', props.get('label', '')),
                        'description': props.get('description', ''),
                        'tags': [],  # Will be populated from __HAS_TAG relationships
                        'urls': parse_json_field(props.get('url', props.get('urls', []))),
                        'photos': parse_json_field(props.get('photo', props.get('photos', []))),
                        'attachments': [],
                        'locations': []
                    }
                    
                    if entity_type == 'Person':
                        person_data = {
                            **common_data,
                            'first_name': props.get('firstName', ''),
                            'last_name': props.get('lastName', ''),
                            'dob': parse_date(props.get('dob')),
                            'gender': props.get('gender', 'Unspecified'),
                            'emails': [props.get('email', props.get('eMail', ''))] if props.get('email') or props.get('eMail') else [],
                            'phones': [props.get('phone')] if props.get('phone') else [],
                            'profession': props.get('profession', '')
                        }
                        people_by_id[entity_uuid] = person_data
                        node_count += 1
                    
                    elif entity_type == 'Note':
                        note_data = {
                            **common_data,
                            'date': props.get('date')
                        }
                        notes_by_id[entity_uuid] = note_data
                        node_count += 1
                    
                    elif entity_type == 'Location':
                        location_data = {
                            **common_data,
                            'address1': props.get('address1', ''),
                            'address2': props.get('address2', ''),
                            'postal_code': props.get('postalCode', ''),
                            'city': props.get('city', ''),
                            'state': props.get('state', ''),
                            'country': props.get('country', '')
                        }
                        locations_by_id[entity_uuid] = location_data
                        node_count += 1
                    
                    elif entity_type == 'Movie':
                        movie_data = {
                            **common_data,
                            'year': props.get('year'),
                            'language': props.get('language', ''),
                            'country': props.get('country', '')
                        }
                        movies_by_id[entity_uuid] = movie_data
                        node_count += 1
                    
                    elif entity_type == 'Book':
                        book_data = {
                            **common_data,
                            'year': props.get('year'),
                            'language': props.get('language', ''),
                            'country': props.get('country', ''),
                            'summary': props.get('summary', '')
                        }
                        books_by_id[entity_uuid] = book_data
                        node_count += 1
                    
                    elif entity_type == 'Container':
                        container_data = common_data
                        containers_by_id[entity_uuid] = container_data
                        node_count += 1
                    
                    elif entity_type == 'Asset':
                        asset_data = {
                            **common_data,
                            'value': props.get('value'),
                            'acquired_on': props.get('acquiredOn', props.get('acquired_on', ''))
                        }
                        assets_by_id[entity_uuid] = asset_data
                        node_count += 1
                    
                    elif entity_type == 'Org':
                        org_data = {
                            **common_data,
                            'name': props.get('name', props.get('display', '')),
                            'kind': props.get('kind', 'Unspecified')
                        }
                        orgs_by_id[entity_uuid] = org_data
                        node_count += 1
                    
                    elif entity_type == 'Event':
                        # Treat Event as Note for now
                        event_data = {
                            **common_data,
                            'type': 'Note',
                            'date': props.get('date', props.get('eventDate'))
                        }
                        notes_by_id[entity_uuid] = event_data
                        node_count += 1
                    
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
                        other_node_count += 1
                else:
                    # Non-entity node (Feedback, UserContext, etc.)
                    skipped_log['non_entity_nodes'].append({
                        'node_id': node_id,
                        'labels': labels,
                        'properties': props
                    })
                    other_node_count += 1
                    
        except json.JSONDecodeError as e:
            print(f"Error parsing node: {e}")
            continue

print(f"✅ Converted {node_count} entity nodes")
print(f"✅ Found {tag_count} tags")
print(f"ℹ️  Skipped {other_node_count} non-entity nodes\n")

# Second pass: Convert relationships
relation_count = 0
tag_relation_count = 0
skipped_relations = 0

with open(input_file, 'r') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        
        try:
            obj = json.loads(line)
            
            if obj.get('type') == 'relationship':
                rel_type = obj.get('label', '')
                start_node = obj.get('start', {})
                end_node = obj.get('end', {})
                
                start_id = start_node.get('id')
                end_id = end_node.get('id')
                
                # Handle __HAS_TAG relationships
                if rel_type == '__HAS_TAG':
                    # Add tag to entity
                    if start_id in id_mapping:
                        entity_uuid = id_mapping[start_id]
                        tag_name = end_node.get('properties', {}).get('name', '')
                        
                        if tag_name:
                            # Add tag to the appropriate entity dict
                            for entity_dict in [people_by_id, notes_by_id, locations_by_id, movies_by_id, books_by_id, containers_by_id, assets_by_id, orgs_by_id]:
                                if entity_uuid in entity_dict:
                                    if tag_name not in entity_dict[entity_uuid]['tags']:
                                        entity_dict[entity_uuid]['tags'].append(tag_name)
                                    break
                            tag_relation_count += 1
                        else:
                            skipped_log['tag_relations_without_tag'].append({
                                'start_node_id': start_id,
                                'end_node_id': end_id,
                                'end_node_properties': end_node.get('properties', {})
                            })
                    else:
                        skipped_log['tag_relations_without_entity'].append({
                            'start_node_id': start_id,
                            'end_node_id': end_id,
                            'tag_name': end_node.get('properties', {}).get('name', '')
                        })
                    continue
                
                # Handle entity relationships
                if start_id in id_mapping and end_id in id_mapping:
                    from_uuid = id_mapping[start_id]
                    to_uuid = id_mapping[end_id]
                    
                    # Normalize relation type (remove entity type prefixes)
                    clean_rel_type = rel_type
                    if '_' in rel_type:
                        parts = rel_type.split('_')
                        # Check if it's in format EntityType_RELATION_EntityType
                        if len(parts) >= 2:
                            # Take the middle part(s) as the relation type
                            # e.g., "Person_IS_PARENT_OF_Person" -> "IS_PARENT_OF"
                            # e.g., "Container_CONTAINS_Asset" -> "CONTAINS"
                            start_idx = 1 if parts[0].istitle() else 0
                            end_idx = len(parts) - 1 if parts[-1].istitle() else len(parts)
                            clean_rel_type = '_'.join(parts[start_idx:end_idx])
                    
                    relation = {
                        'from_entity': from_uuid,
                        'to_entity': to_uuid,
                        'relation_type': clean_rel_type
                    }
                    relations.append(relation)
                    relation_count += 1
                else:
                    skipped_log['skipped_relations'].append({
                        'start_node_id': start_id,
                        'end_node_id': end_id,
                        'relation_type': rel_type,
                        'start_in_mapping': start_id in id_mapping,
                        'end_in_mapping': end_id in id_mapping,
                        'start_labels': start_node.get('labels', []),
                        'end_labels': end_node.get('labels', [])
                    })
                    skipped_relations += 1
                    
        except json.JSONDecodeError as e:
            print(f"Error parsing relationship: {e}")
            continue

print(f"✅ Converted {relation_count} entity relationships")
print(f"✅ Applied {tag_relation_count} tags to entities")
print(f"ℹ️  Skipped {skipped_relations} relationships (non-entity nodes)\n")

# Create output JSON in Django export format
output_data = {
    'export_version': '1.0',
    'export_date': datetime.now().isoformat(),
    'tags': list(tags_by_name.values()),
    'entities': [],  # Generic entities (not used in our conversion)
    'people': list(people_by_id.values()),
    'notes': list(notes_by_id.values()),
    'locations': list(locations_by_id.values()),
    'movies': list(movies_by_id.values()),
    'books': list(books_by_id.values()),
    'containers': list(containers_by_id.values()),
    'assets': list(assets_by_id.values()),
    'orgs': list(orgs_by_id.values()),
    'relations': relations
}

# Write output
with open(output_file, 'w') as f:
    json.dump(output_data, f, indent=2)

print(f"✅ Created import file: {output_file}")
print(f"\nSummary:")
print(f"  Tags: {len(tags_by_name)}")
print(f"  People: {len(people_by_id)}")
print(f"  Notes: {len(notes_by_id)}")
print(f"  Locations: {len(locations_by_id)}")
print(f"  Movies: {len(movies_by_id)}")
print(f"  Books: {len(books_by_id)}")
print(f"  Containers: {len(containers_by_id)}")
print(f"  Assets: {len(assets_by_id)}")
print(f"  Orgs: {len(orgs_by_id)}")
print(f"  Relations: {len(relations)}")
print(f"  Total entities: {node_count}")

# Write detailed skip log
skip_log_file = output_file.replace('.json', '_skip_log.json')
with open(skip_log_file, 'w') as f:
    json.dump(skipped_log, f, indent=2)

print(f"\n✅ Created skip log: {skip_log_file}")
print(f"\nSkipped Items Summary:")
print(f"  Unknown entity types: {len(skipped_log['unknown_entity_types'])}")
print(f"  Non-entity nodes: {len(skipped_log['non_entity_nodes'])}")
print(f"  Skipped relations: {len(skipped_log['skipped_relations'])}")
print(f"  Tag relations without entity: {len(skipped_log['tag_relations_without_entity'])}")
print(f"  Tag relations without tag: {len(skipped_log['tag_relations_without_tag'])}")

# Print details of unknown entity types
if skipped_log['unknown_entity_types']:
    print(f"\n⚠️  Unknown Entity Types:")
    from collections import Counter
    type_counts = Counter([item['entity_type'] for item in skipped_log['unknown_entity_types']])
    for entity_type, count in type_counts.items():
        print(f"    {entity_type}: {count} nodes")

# Print sample of skipped relations by type
if skipped_log['skipped_relations']:
    print(f"\n⚠️  Skipped Relations by Type:")
    rel_type_counts = Counter([item['relation_type'] for item in skipped_log['skipped_relations']])
    for rel_type, count in rel_type_counts.most_common(10):
        print(f"    {rel_type}: {count} relations")
