#!/usr/bin/env python3
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from people.models import Entity, Person, Note, Location, Movie, Book, Container, Asset, Org
from django.contrib.auth import get_user_model

User = get_user_model()
bob = User.objects.filter(email='bob@example.com').first()

if not bob:
    print("Bob user not found!")
else:
    print(f"Bob user: {bob}")
    print(f"\nBase Entity records for Bob:")
    base_entities = Entity.objects.filter(user=bob)
    print(f"  Count: {base_entities.count()}")
    
    for entity in base_entities:
        print(f"  - {entity.id}: {entity.display} (type={entity.type})")
        
        # Check if it has a subclass
        try:
            if hasattr(entity, 'person'):
                print(f"    -> Has Person subclass")
        except:
            pass
        try:
            if hasattr(entity, 'note'):
                print(f"    -> Has Note subclass")
        except:
            pass
