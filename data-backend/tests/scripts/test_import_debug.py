#!/usr/bin/env python3
"""Debug import to see what's happening"""
import json
import sys

# Read the import file
import_file = sys.argv[1] if len(sys.argv) > 1 else '/home/ubuntu/data/bldrdojo/test_import.json'

with open(import_file, 'r') as f:
    data = json.load(f)

print("Import file structure:")
print(f"  export_version: {data.get('export_version')}")
print(f"  export_date: {data.get('export_date')}")
print(f"  tags: {len(data.get('tags', []))}")
print(f"  entities: {len(data.get('entities', []))}")
print(f"  people: {len(data.get('people', []))}")
print(f"  notes: {len(data.get('notes', []))}")
print(f"  locations: {len(data.get('locations', []))}")
print(f"  movies: {len(data.get('movies', []))}")
print(f"  books: {len(data.get('books', []))}")
print(f"  containers: {len(data.get('containers', []))}")
print(f"  assets: {len(data.get('assets', []))}")
print(f"  orgs: {len(data.get('orgs', []))}")
print(f"  relations: {len(data.get('relations', []))}")

# Check if people have all required fields
if data.get('people'):
    print("\nFirst person data:")
    person = data['people'][0]
    for key, value in person.items():
        print(f"  {key}: {value!r}")
    
    # Check for any fields that might cause issues
    print("\nChecking for problematic fields:")
    if 'type' in person:
        print(f"  ✓ Has 'type' field: {person['type']}")
    if 'display' in person:
        print(f"  ✓ Has 'display' field: {person['display']}")
