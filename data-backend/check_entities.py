#!/usr/bin/env python3
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from people.models import Person, Note, Location, Movie, Book, Container, Asset, Org
from django.contrib.auth import get_user_model

User = get_user_model()
bob = User.objects.filter(email='bob@example.com').first()

if not bob:
    print("Bob user not found!")
else:
    print(f"Bob user: {bob}")
    print(f"\nEntities for Bob:")
    print(f"  People: {Person.objects.filter(user=bob).count()}")
    print(f"  Notes: {Note.objects.filter(user=bob).count()}")
    print(f"  Locations: {Location.objects.filter(user=bob).count()}")
    print(f"  Movies: {Movie.objects.filter(user=bob).count()}")
    print(f"  Books: {Book.objects.filter(user=bob).count()}")
    print(f"  Containers: {Container.objects.filter(user=bob).count()}")
    print(f"  Assets: {Asset.objects.filter(user=bob).count()}")
    print(f"  Orgs: {Org.objects.filter(user=bob).count()}")
    
    print(f"\nPeople details:")
    for p in Person.objects.filter(user=bob):
        print(f"  - {p.id}: {p.display} (type={p.type})")
