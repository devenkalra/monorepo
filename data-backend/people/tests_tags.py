from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from .models import Person, Note, Tag
from .tests import PatchMixin

class TagTests(PatchMixin, APITestCase):
    def setUp(self):
        self.start_patches()
        
    def test_auto_create_tags(self):
        # Create Entity with tags
        Person.objects.create(first_name="Alice", tags=["work", "work/project-x", "personal"])
        
        # Verify Tags created
        self.assertEqual(Tag.objects.count(), 3)
        self.assertTrue(Tag.objects.filter(name="work").exists())
        self.assertTrue(Tag.objects.filter(name="work/project-x").exists())
        
    def test_dedup_tags(self):
        # Create two entities with same tag
        Person.objects.create(first_name="Alice", tags=["foo"])
        Note.objects.create(description="Bar", tags=["foo"])
        
        # Should only be one Tag object
        self.assertEqual(Tag.objects.count(), 1)
        
    def test_api_filter_tags(self):
        Tag.objects.create(name="work/alpha")
        Tag.objects.create(name="work/beta")
        Tag.objects.create(name="home/chores")
        
        # Search startswith 'work/'
        url = reverse('tag-list') + '?name__istartswith=work/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Sorting is not guaranteed by default unless ordered in model/view, but let's check count and content
        self.assertEqual(len(response.data), 2)
        names = sorted([t['name'] for t in response.data])
        self.assertEqual(names, ['work/alpha', 'work/beta'])
