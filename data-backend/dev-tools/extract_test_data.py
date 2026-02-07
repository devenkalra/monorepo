#!/usr/bin/env python3
"""
Extract 2 objects of each type from Neo4j export file
"""
import json
from collections import defaultdict

input_file = '/home/ubuntu/data/bldrdojo/full_graph.json'
output_file = '/home/ubuntu/data/bldrdojo/test_sample.json'

# Track objects by type
objects_by_type = defaultdict(list)
type_counts = defaultdict(int)

print("Reading and categorizing objects...")

# Read the file line by line
with open(input_file, 'r') as f:
    for line_num, line in enumerate(f, 1):
        line = line.strip()
        if not line:
            continue
        
        try:
            obj = json.loads(line)
            
            # Determine object type
            obj_type = obj.get('type', 'unknown')
            
            # For nodes, also check labels
            if obj_type == 'node':
                labels = obj.get('labels', [])
                # Get the most specific label (usually the last non-system label)
                specific_labels = [l for l in labels if not l.startswith('__') and not l.startswith('p_') and not l.startswith('u_') and not l.startswith('pkg_') and not l.startswith('t_')]
                if specific_labels:
                    obj_type = f"node:{specific_labels[-1]}"
                else:
                    obj_type = f"node:{','.join(labels[:2])}"
            
            # For relationships, include the relationship type
            elif obj_type == 'relationship':
                rel_type = obj.get('label', 'unknown')
                obj_type = f"relationship:{rel_type}"
            
            # Only keep 2 of each type
            if type_counts[obj_type] < 2:
                objects_by_type[obj_type].append(obj)
                type_counts[obj_type] += 1
                
        except json.JSONDecodeError as e:
            print(f"Error parsing line {line_num}: {e}")
            continue

print(f"\nFound {len(objects_by_type)} different types:")
for obj_type, count in sorted(type_counts.items()):
    print(f"  {obj_type}: {count} objects")

# Write output file
print(f"\nWriting test file to {output_file}...")
with open(output_file, 'w') as f:
    for obj_type in sorted(objects_by_type.keys()):
        for obj in objects_by_type[obj_type]:
            f.write(json.dumps(obj) + '\n')

print(f"✅ Done! Created test file with {sum(type_counts.values())} total objects")
