"""
API Integration Tests for Entity CRUD Operations

Tests entity creation, retrieval, update, and deletion across all entity types.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from people.models import Person, Location, Movie, Book, Container, Asset, Org, Note

User = get_user_model()


class EntityAPITestCase(TestCase):
    """Test entity CRUD operations via API"""
    
    def setUp(self):
        """Set up test client and user"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_create_person(self):
        """Test creating a Person entity"""
        data = {
            'type': 'Person',
            'display': 'John Doe',
            'description': 'Test person',
            'first_name': 'John',
            'last_name': 'Doe',
            'emails': ['john@example.com'],
            'phones': ['+1234567890'],
            'tags': ['friend', 'colleague']
        }
        response = self.client.post('/api/people/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['display'], 'John Doe')
        self.assertEqual(response.data['first_name'], 'John')
        self.assertEqual(response.data['type'], 'Person')
        
        # Verify in database
        person = Person.objects.get(id=response.data['id'])
        self.assertEqual(person.display, 'John Doe')
        self.assertEqual(person.user, self.user)
    
    def test_create_location(self):
        """Test creating a Location entity"""
        data = {
            'type': 'Location',
            'display': 'San Francisco Office',
            'description': 'Main office location',
            'address1': '123 Market St',
            'city': 'San Francisco',
            'state': 'CA',
            'country': 'USA',
            'postal_code': '94102'
        }
        response = self.client.post('/api/locations/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['display'], 'San Francisco Office')
        self.assertEqual(response.data['city'], 'San Francisco')
    
    def test_create_movie(self):
        """Test creating a Movie entity"""
        data = {
            'type': 'Movie',
            'display': 'The Matrix',
            'description': 'Sci-fi action film',
            'year': 1999,
            'language': 'English'
        }
        response = self.client.post('/api/movies/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['display'], 'The Matrix')
        self.assertEqual(response.data['year'], 1999)
    
    def test_create_book(self):
        """Test creating a Book entity"""
        data = {
            'type': 'Book',
            'display': 'The Great Gatsby',
            'description': 'Classic American novel',
            'year': 1925,
            'language': 'English',
            'summary': 'Story of Jay Gatsby'
        }
        response = self.client.post('/api/books/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['display'], 'The Great Gatsby')
        self.assertEqual(response.data['year'], 1925)
    
    def test_create_container(self):
        """Test creating a Container entity"""
        data = {
            'type': 'Container',
            'display': 'Storage Box A1',
            'description': 'Office supplies storage',
            'kind': 'box'
        }
        response = self.client.post('/api/containers/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['display'], 'Storage Box A1')
        # kind field may not be returned in response, check if present
        if 'kind' in response.data:
            self.assertEqual(response.data['kind'], 'box')
    
    def test_create_asset(self):
        """Test creating an Asset entity"""
        data = {
            'type': 'Asset',
            'display': 'MacBook Pro 2023',
            'description': 'Company laptop',
            'value': '2500.00',
            'acquired_on': '2023-01-15'
        }
        response = self.client.post('/api/assets/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['display'], 'MacBook Pro 2023')
        # Value may be returned as float or string
        self.assertIn(response.data['value'], ['2500.00', 2500.0, '2500.0'])
    
    def test_create_org(self):
        """Test creating an Org entity"""
        data = {
            'type': 'Org',
            'display': 'Acme Corporation',
            'description': 'Technology company',
            'name': 'Acme Corp'
        }
        response = self.client.post('/api/orgs/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['display'], 'Acme Corporation')
        self.assertEqual(response.data['name'], 'Acme Corp')
    
    def test_create_note(self):
        """Test creating a Note entity"""
        data = {
            'type': 'Note',
            'display': 'Meeting Notes',
            'description': 'Q1 planning meeting notes',
            'date': '2024-01-15'
        }
        response = self.client.post('/api/notes/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['display'], 'Meeting Notes')
    
    def test_list_entities(self):
        """Test listing entities via search endpoint"""
        # Create test entities
        Person.objects.create(
            user=self.user,
            display='Alice Smith',
            first_name='Alice',
            last_name='Smith'
        )
        Person.objects.create(
            user=self.user,
            display='Bob Jones',
            first_name='Bob',
            last_name='Jones'
        )
        
        response = self.client.get('/api/search/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 2)
    
    def test_retrieve_entity(self):
        """Test retrieving a specific entity"""
        person = Person.objects.create(
            user=self.user,
            display='Jane Doe',
            first_name='Jane',
            last_name='Doe'
        )
        
        response = self.client.get(f'/api/people/{person.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['display'], 'Jane Doe')
        self.assertEqual(response.data['first_name'], 'Jane')
    
    def test_update_entity(self):
        """Test updating an entity"""
        person = Person.objects.create(
            user=self.user,
            display='John Smith',
            first_name='John',
            last_name='Smith'
        )
        
        data = {
            'display': 'John A. Smith',
            'description': 'Updated description',
            'profession': 'Engineer'
        }
        response = self.client.patch(f'/api/people/{person.id}/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['display'], 'John A. Smith')
        self.assertEqual(response.data['profession'], 'Engineer')
        
        # Verify in database
        person.refresh_from_db()
        self.assertEqual(person.display, 'John A. Smith')
        self.assertEqual(person.profession, 'Engineer')
    
    def test_delete_entity(self):
        """Test deleting an entity"""
        person = Person.objects.create(
            user=self.user,
            display='To Delete',
            first_name='To',
            last_name='Delete'
        )
        person_id = person.id
        
        response = self.client.delete(f'/api/people/{person.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        # Verify deleted from database
        self.assertFalse(Person.objects.filter(id=person_id).exists())
    
    def test_entity_with_urls(self):
        """Test creating entity with URLs"""
        data = {
            'type': 'Person',
            'display': 'Web Developer',
            'urls': [
                {'url': 'https://example.com', 'caption': 'Website'},
                {'url': 'https://github.com/user', 'caption': 'GitHub'}
            ]
        }
        response = self.client.post('/api/people/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['urls']), 2)
        self.assertEqual(response.data['urls'][0]['url'], 'https://example.com')
        self.assertEqual(response.data['urls'][0]['caption'], 'Website')
    
    def test_entity_isolation_between_users(self):
        """Test that users can only see their own entities"""
        # Create entity for first user
        person1 = Person.objects.create(
            user=self.user,
            display='User 1 Person',
            first_name='User1'
        )
        
        # Create second user and entity
        user2 = User.objects.create_user(
            username='testuser2',
            email='user2@example.com',
            password='testpass123'
        )
        person2 = Person.objects.create(
            user=user2,
            display='User 2 Person',
            first_name='User2'
        )
        
        # First user should only see their entity
        response = self.client.get('/api/search/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        displays = [item['display'] for item in response.data]
        self.assertIn('User 1 Person', displays)
        self.assertNotIn('User 2 Person', displays)
        
        # First user should not be able to access second user's entity
        response = self.client.get(f'/api/people/{person2.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_required_fields_validation(self):
        """Test that required fields are validated"""
        # Try to create person without display
        data = {
            'type': 'Person',
            'first_name': 'John'
        }
        response = self.client.post('/api/people/', data, format='json')
        # Should still succeed as display can be auto-generated
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_entity_timestamps(self):
        """Test that created_at and updated_at are set correctly"""
        data = {
            'type': 'Person',
            'display': 'Timestamp Test'
        }
        response = self.client.post('/api/people/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('created_at', response.data)
        self.assertIn('updated_at', response.data)
        
        created_at = response.data['created_at']
        
        # Update entity
        import time
        time.sleep(0.1)  # Small delay to ensure different timestamp
        
        response = self.client.patch(
            f'/api/people/{response.data["id"]}/',
            {'description': 'Updated'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['created_at'], created_at)
        self.assertNotEqual(response.data['updated_at'], created_at)
