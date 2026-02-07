#!/usr/bin/env python3
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from people.models import Entity, Person
from django.contrib.auth import get_user_model

User = get_user_model()

# Check the specific IDs from the import file
target_ids = [
    'aa2b6d88-5e71-5155-9e3a-5d81968692b2',
    '6d4e5f88-0e71-5155-9e3a-5d81968692b2'
]

print("Checking for entities with specific IDs:")
for entity_id in target_ids:
    entity = Entity.objects.filter(id=entity_id).first()
    if entity:
        print(f"\n  ID: {entity_id}")
        print(f"  Display: {entity.display}")
        print(f"  Type: {entity.type}")
        print(f"  User: {entity.user.email if entity.user else 'None'}")
    else:
        print(f"\n  ID: {entity_id} - NOT FOUND")

print(f"\n\nAll entities in database:")
all_entities = Entity.objects.all()
print(f"  Total count: {all_entities.count()}")

for entity in all_entities[:10]:
    print(f"  - {entity.id}: {entity.display} (type={entity.type}, user={entity.user.email if entity.user else 'None'})")
