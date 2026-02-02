"""
API Integration Tests for Import/Export Functionality

Tests data import and export operations.
"""
import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from people.models import Person, Location, Movie, EntityRelation

User = get_user_model()


class ImportExportAPITestCase(TestCase):
    """Test import and export operations via API"""
    
    def setUp(self):
        """Set up test client and user"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_export_entities(self):
        """Test exporting entities"""
        # Create test entities
        person = Person.objects.create(
            user=self.user,
            display='Alice Smith',
            first_name='Alice',
            last_name='Smith',
            tags=['friend']
        )
        location = Location.objects.create(
            user=self.user,
            display='San Francisco',
            city='San Francisco'
        )
        
        response = self.client.get('/api/entities/export/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Parse response
        data = response.json()
        self.assertIn('entities', data)
        self.assertIn('relations', data)
        
        # Check entities
        self.assertGreaterEqual(len(data['entities']), 2)
        
        # Verify entity structure
        entity_displays = [e['display'] for e in data['entities']]
        self.assertIn('Alice Smith', entity_displays)
        self.assertIn('San Francisco', entity_displays)
    
    def test_export_with_relations(self):
        """Test that export includes relations"""
        person1 = Person.objects.create(
            user=self.user,
            display='Alice',
            first_name='Alice'
        )
        person2 = Person.objects.create(
            user=self.user,
            display='Bob',
            first_name='Bob'
        )
        
        # Create relation
        EntityRelation.objects.create(
            from_entity=person1.id,
            to_entity=person2.id,
            relation_type='IS_FRIEND_OF'
        )
        
        response = self.client.get('/api/entities/export/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertIn('relations', data)
        self.assertGreater(len(data['relations']), 0)
        
        # Check relation structure
        relation = data['relations'][0]
        self.assertIn('from_entity', relation)
        self.assertIn('to_entity', relation)
        self.assertIn('relation_type', relation)
    
    def test_export_with_urls(self):
        """Test that export includes URLs"""
        person = Person.objects.create(
            user=self.user,
            display='Web Developer',
            urls=[
                {'url': 'https://example.com', 'caption': 'Website'},
                {'url': 'https://github.com/user', 'caption': 'GitHub'}
            ]
        )
        
        response = self.client.get('/api/entities/export/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        entity = next((e for e in data['entities'] if e['display'] == 'Web Developer'), None)
        self.assertIsNotNone(entity)
        self.assertIn('urls', entity)
        self.assertEqual(len(entity['urls']), 2)
    
    def test_import_entities(self):
        """Test importing entities"""
        import_data = {
            'entities': [
                {
                    'id': '11111111-1111-1111-1111-111111111111',
                    'type': 'Person',
                    'display': 'Imported Person',
                    'first_name': 'Imported',
                    'last_name': 'Person',
                    'tags': ['imported']
                },
                {
                    'id': '22222222-2222-2222-2222-222222222222',
                    'type': 'Location',
                    'display': 'Imported Location',
                    'city': 'New York'
                }
            ],
            'relations': []
        }
        
        response = self.client.post(
            '/api/entities/import_data/',
            data=json.dumps(import_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify entities were created
        person = Person.objects.filter(display='Imported Person').first()
        self.assertIsNotNone(person)
        self.assertEqual(person.first_name, 'Imported')
        self.assertEqual(person.user, self.user)
        
        location = Location.objects.filter(display='Imported Location').first()
        self.assertIsNotNone(location)
        self.assertEqual(location.city, 'New York')
    
    def test_import_with_relations(self):
        """Test importing entities with relations"""
        import_data = {
            'entities': [
                {
                    'id': '11111111-1111-1111-1111-111111111111',
                    'type': 'Person',
                    'display': 'Person A',
                    'first_name': 'A'
                },
                {
                    'id': '22222222-2222-2222-2222-222222222222',
                    'type': 'Person',
                    'display': 'Person B',
                    'first_name': 'B'
                }
            ],
            'relations': [
                {
                    'from_entity': '11111111-1111-1111-1111-111111111111',
                    'to_entity': '22222222-2222-2222-2222-222222222222',
                    'relation_type': 'IS_FRIEND_OF'
                }
            ]
        }
        
        response = self.client.post(
            '/api/entities/import_data/',
            data=json.dumps(import_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify relation was created
        person_a = Person.objects.filter(display='Person A').first()
        person_b = Person.objects.filter(display='Person B').first()
        
        relation = EntityRelation.objects.filter(
            from_entity=person_a.id,
            to_entity=person_b.id,
            relation_type='IS_FRIEND_OF'
        ).first()
        self.assertIsNotNone(relation)
    
    def test_import_with_urls(self):
        """Test importing entities with URLs"""
        import_data = {
            'entities': [
                {
                    'id': '11111111-1111-1111-1111-111111111111',
                    'type': 'Person',
                    'display': 'Person with URLs',
                    'urls': [
                        {'url': 'https://example.com', 'caption': 'Website'}
                    ]
                }
            ],
            'relations': []
        }
        
        response = self.client.post(
            '/api/entities/import_data/',
            data=json.dumps(import_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify URLs were imported
        person = Person.objects.filter(display='Person with URLs').first()
        self.assertIsNotNone(person)
        self.assertEqual(len(person.urls), 1)
        self.assertEqual(person.urls[0]['url'], 'https://example.com')
    
    def test_import_invalid_entity_type(self):
        """Test that import rejects invalid entity types"""
        import_data = {
            'entities': [
                {
                    'id': '11111111-1111-1111-1111-111111111111',
                    'type': 'InvalidType',
                    'display': 'Invalid Entity'
                }
            ],
            'relations': []
        }
        
        response = self.client.post(
            '/api/entities/import_data/',
            data=json.dumps(import_data),
            content_type='application/json'
        )
        # Should either skip or return error
        # Check that no entity was created
        from people.models import Entity
        entity = Entity.objects.filter(display='Invalid Entity').first()
        self.assertIsNone(entity)
    
    def test_import_duplicate_ids(self):
        """Test importing entities with duplicate IDs"""
        # Create existing entity
        existing = Person.objects.create(
            user=self.user,
            display='Existing Person',
            first_name='Existing'
        )
        
        import_data = {
            'entities': [
                {
                    'id': str(existing.id),
                    'type': 'Person',
                    'display': 'Updated Person',
                    'first_name': 'Updated'
                }
            ],
            'relations': []
        }
        
        response = self.client.post(
            '/api/entities/import_data/',
            data=json.dumps(import_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify entity was updated (not duplicated)
        person_count = Person.objects.filter(id=existing.id).count()
        self.assertEqual(person_count, 1)
        
        person = Person.objects.get(id=existing.id)
        self.assertEqual(person.display, 'Updated Person')
    
    def test_import_empty_data(self):
        """Test importing empty data"""
        import_data = {
            'entities': [],
            'relations': []
        }
        
        response = self.client.post(
            '/api/entities/import_data/',
            data=json.dumps(import_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_import_malformed_json(self):
        """Test that malformed JSON is rejected"""
        response = self.client.post(
            '/api/entities/import_data/',
            data='{ invalid json',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_export_import_roundtrip(self):
        """Test that exported data can be re-imported"""
        # Create test data
        person = Person.objects.create(
            user=self.user,
            display='Test Person',
            first_name='Test',
            tags=['test']
        )
        location = Location.objects.create(
            user=self.user,
            display='Test Location',
            city='Test City'
        )
        EntityRelation.objects.create(
            from_entity=person.id,
            to_entity=location.id,
            relation_type='LIVES_AT'
        )
        
        # Export
        export_response = self.client.get('/api/entities/export/')
        self.assertEqual(export_response.status_code, status.HTTP_200_OK)
        export_data = export_response.json()
        
        # Delete all entities
        Person.objects.all().delete()
        Location.objects.all().delete()
        EntityRelation.objects.all().delete()
        
        # Re-import
        import_response = self.client.post(
            '/api/entities/import_data/',
            data=json.dumps(export_data),
            content_type='application/json'
        )
        self.assertEqual(import_response.status_code, status.HTTP_200_OK)
        
        # Verify data was restored
        person = Person.objects.filter(display='Test Person').first()
        self.assertIsNotNone(person)
        
        location = Location.objects.filter(display='Test Location').first()
        self.assertIsNotNone(location)
        
        relation = EntityRelation.objects.filter(
            from_entity=person.id,
            to_entity=location.id
        ).first()
        self.assertIsNotNone(relation)
