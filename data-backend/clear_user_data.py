#!/usr/bin/env python3
"""Clear all entities for a user"""
import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from people.models import Entity, EntityRelation
from django.contrib.auth import get_user_model

User = get_user_model()

email = sys.argv[1] if len(sys.argv) > 1 else 'bob@example.com'
user = User.objects.filter(email=email).first()

if not user:
    print(f"User {email} not found!")
else:
    print(f"Clearing all data for {email}...")
    
    # Delete all relations first (they reference entities)
    relations_count = EntityRelation.objects.filter(from_entity__user=user).count()
    EntityRelation.objects.filter(from_entity__user=user).delete()
    print(f"  Deleted {relations_count} relations")
    
    # Delete all entities
    entities_count = Entity.objects.filter(user=user).count()
    Entity.objects.filter(user=user).delete()
    print(f"  Deleted {entities_count} entities")
    
    print("✅ Done!")
