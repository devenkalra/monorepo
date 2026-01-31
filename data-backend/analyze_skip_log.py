#!/usr/bin/env python3
"""Analyze and create a detailed report from the skip log"""
import json
from collections import Counter

skip_log_file = '/home/ubuntu/data/bldrdojo/full_import_skip_log.json'
report_file = '/home/ubuntu/data/bldrdojo/skip_report.txt'

with open(skip_log_file, 'r') as f:
    skip_log = json.load(f)

report = []
report.append("=" * 80)
report.append("NEO4J TO DJANGO IMPORT - DETAILED SKIP REPORT")
report.append("=" * 80)
report.append("")

# 1. Unknown Entity Types
report.append("1. UNKNOWN ENTITY TYPES")
report.append("-" * 80)
if skip_log['unknown_entity_types']:
    report.append(f"Total: {len(skip_log['unknown_entity_types'])} nodes")
    report.append("")
    for item in skip_log['unknown_entity_types']:
        report.append(f"  Node ID: {item['node_id']}")
        report.append(f"  Entity Type: {item['entity_type']}")
        report.append(f"  Display: {item['display']}")
        report.append(f"  Labels: {', '.join(item['labels'])}")
        report.append(f"  Properties: {json.dumps(item['properties'], indent=4)}")
        report.append("")
else:
    report.append("  None")
report.append("")

# 2. Non-Entity Nodes
report.append("2. NON-ENTITY NODES (System/Internal Nodes)")
report.append("-" * 80)
report.append(f"Total: {len(skip_log['non_entity_nodes'])} nodes")
report.append("")

# Group by label types
label_groups = {}
for item in skip_log['non_entity_nodes']:
    # Get primary label (non-user label)
    primary_labels = [l for l in item['labels'] if not l.startswith('u_')]
    if primary_labels:
        label_key = ', '.join(sorted(primary_labels))
    else:
        label_key = 'Unknown'
    
    if label_key not in label_groups:
        label_groups[label_key] = []
    label_groups[label_key].append(item)

for label_key, items in sorted(label_groups.items(), key=lambda x: len(x[1]), reverse=True):
    report.append(f"  {label_key}: {len(items)} nodes")

report.append("")
report.append("  Sample non-entity nodes (first 5):")
for item in skip_log['non_entity_nodes'][:5]:
    report.append(f"    Node ID: {item['node_id']}")
    report.append(f"    Labels: {', '.join(item['labels'])}")
    if item['properties']:
        # Show only key properties
        key_props = {k: v for k, v in list(item['properties'].items())[:3]}
        report.append(f"    Sample Properties: {json.dumps(key_props)}")
    report.append("")

report.append("")

# 3. Skipped Relations
report.append("3. SKIPPED RELATIONS")
report.append("-" * 80)
report.append(f"Total: {len(skip_log['skipped_relations'])} relations")
report.append("")

# Group by relation type
rel_type_groups = {}
for item in skip_log['skipped_relations']:
    rel_type = item['relation_type']
    if rel_type not in rel_type_groups:
        rel_type_groups[rel_type] = []
    rel_type_groups[rel_type].append(item)

report.append("  Relations by Type:")
for rel_type, items in sorted(rel_type_groups.items(), key=lambda x: len(x[1]), reverse=True):
    report.append(f"    {rel_type}: {len(items)} relations")

report.append("")
report.append("  Reason for Skipping:")

# Analyze why relations were skipped
skip_reasons = Counter()
for item in skip_log['skipped_relations']:
    if not item['start_in_mapping'] and not item['end_in_mapping']:
        skip_reasons['Both nodes not in entity mapping'] += 1
    elif not item['start_in_mapping']:
        skip_reasons['Start node not in entity mapping'] += 1
    elif not item['end_in_mapping']:
        skip_reasons['End node not in entity mapping'] += 1

for reason, count in skip_reasons.most_common():
    report.append(f"    {reason}: {count} relations")

report.append("")
report.append("  Sample skipped relations (first 10):")
for item in skip_log['skipped_relations'][:10]:
    report.append(f"    Relation: {item['start_node_id']} --[{item['relation_type']}]--> {item['end_node_id']}")
    report.append(f"      Start labels: {', '.join(item['start_labels'])}")
    report.append(f"      End labels: {', '.join(item['end_labels'])}")
    report.append(f"      Start in mapping: {item['start_in_mapping']}")
    report.append(f"      End in mapping: {item['end_in_mapping']}")
    report.append("")

report.append("")

# 4. Tag Relations Without Entity
report.append("4. TAG RELATIONS WITHOUT ENTITY")
report.append("-" * 80)
if skip_log['tag_relations_without_entity']:
    report.append(f"Total: {len(skip_log['tag_relations_without_entity'])} tag relations")
    report.append("")
    report.append("  These are __HAS_TAG relations where the entity was not converted:")
    for item in skip_log['tag_relations_without_entity'][:20]:
        report.append(f"    Entity Node ID: {item['start_node_id']}")
        report.append(f"    Tag Node ID: {item['end_node_id']}")
        report.append(f"    Tag Name: {item['tag_name']}")
        report.append("")
else:
    report.append("  None")

report.append("")

# 5. Tag Relations Without Tag Name
report.append("5. TAG RELATIONS WITHOUT TAG NAME")
report.append("-" * 80)
if skip_log['tag_relations_without_tag']:
    report.append(f"Total: {len(skip_log['tag_relations_without_tag'])} tag relations")
    report.append("")
    for item in skip_log['tag_relations_without_tag']:
        report.append(f"    Start Node ID: {item['start_node_id']}")
        report.append(f"    End Node ID: {item['end_node_id']}")
        report.append(f"    End Node Properties: {json.dumps(item['end_node_properties'])}")
        report.append("")
else:
    report.append("  None")

report.append("")
report.append("=" * 80)
report.append("END OF REPORT")
report.append("=" * 80)

# Write report
report_text = '\n'.join(report)
with open(report_file, 'w') as f:
    f.write(report_text)

print(f"✅ Detailed skip report created: {report_file}")
print(f"\nReport has {len(report)} lines")
print("\nSummary:")
print(f"  Unknown entity types: {len(skip_log['unknown_entity_types'])}")
print(f"  Non-entity nodes: {len(skip_log['non_entity_nodes'])}")
print(f"  Skipped relations: {len(skip_log['skipped_relations'])}")
print(f"  Tag relations without entity: {len(skip_log['tag_relations_without_entity'])}")
print(f"  Tag relations without tag: {len(skip_log['tag_relations_without_tag'])}")
