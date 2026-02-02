"""
API Integration Tests for Search and Filtering

Tests search functionality, filtering, and MeiliSearch integration.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from people.models import Person, Location, Movie, Org

User = get_user_model()


class SearchAPITestCase(TestCase):
    """Test search and filtering operations via API"""
    
    def setUp(self):
        """Set up test client, user, and test data"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        # Create test entities with various attributes
        self.person1 = Person.objects.create(
            user=self.user,
            display='Alice Smith',
            first_name='Alice',
            last_name='Smith',
            profession='Engineer',
            tags=['friend', 'colleague']
        )
        self.person2 = Person.objects.create(
            user=self.user,
            display='Bob Jones',
            first_name='Bob',
            last_name='Jones',
            profession='Designer',
            tags=['friend']
        )
        self.person3 = Person.objects.create(
            user=self.user,
            display='Charlie Brown',
            first_name='Charlie',
            last_name='Brown',
            profession='Manager',
            tags=['colleague', 'manager']
        )
        self.location = Location.objects.create(
            user=self.user,
            display='San Francisco Office',
            city='San Francisco',
            state='CA',
            tags=['office']
        )
        self.movie = Movie.objects.create(
            user=self.user,
            display='The Matrix',
            year=1999,
            language='English',
            tags=['sci-fi', 'action']
        )
        self.org = Org.objects.create(
            user=self.user,
            display='Acme Corporation',
            name='Acme Corp',
            tags=['technology']
        )
    
    def test_search_by_name(self):
        """Test searching entities by name"""
        response = self.client.get('/api/search/?q=Alice')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data), 0)
        
        # Check that Alice is in results
        displays = [item['display'] for item in response.data]
        self.assertIn('Alice Smith', displays)
    
    def test_search_partial_match(self):
        """Test partial name matching"""
        response = self.client.get('/api/search/?q=Smi')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        displays = [item['display'] for item in response.data]
        self.assertIn('Alice Smith', displays)
    
    def test_search_case_insensitive(self):
        """Test case-insensitive search"""
        response = self.client.get('/api/search/?q=alice')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        displays = [item['display'] for item in response.data]
        self.assertIn('Alice Smith', displays)
    
    def test_search_by_profession(self):
        """Test searching by profession field"""
        response = self.client.get('/api/search/?q=Engineer')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        displays = [item['display'] for item in response.data]
        self.assertIn('Alice Smith', displays)
    
    def test_search_multiple_results(self):
        """Test search returning multiple results"""
        response = self.client.get('/api/search/?q=friend')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should return both Alice and Bob (both have 'friend' tag)
        displays = [item['display'] for item in response.data]
        self.assertIn('Alice Smith', displays)
        self.assertIn('Bob Jones', displays)
    
    def test_search_no_results(self):
        """Test search with no matching results"""
        response = self.client.get('/api/search/?q=NonexistentName')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)
    
    def test_search_empty_query(self):
        """Test search with empty query returns all entities"""
        response = self.client.get('/api/search/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return all entities for this user
        self.assertGreaterEqual(len(response.data), 6)
    
    def test_filter_by_type(self):
        """Test filtering by entity type"""
        response = self.client.get('/api/search/?type=Person')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # All results should be Person type
        for item in response.data:
            self.assertEqual(item['type'], 'Person')
        
        # Should have 3 persons
        self.assertEqual(len(response.data), 3)
    
    def test_filter_by_multiple_types(self):
        """Test filtering by multiple entity types"""
        response = self.client.get('/api/search/?type=Person&type=Location')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        types = [item['type'] for item in response.data]
        # Should only have Person and Location types
        for t in types:
            self.assertIn(t, ['Person', 'Location'])
    
    def test_filter_by_tag(self):
        """Test filtering by tag"""
        response = self.client.get('/api/search/?tag=friend')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should return entities with 'friend' tag
        displays = [item['display'] for item in response.data]
        self.assertIn('Alice Smith', displays)
        self.assertIn('Bob Jones', displays)
        self.assertNotIn('Charlie Brown', displays)
    
    def test_filter_by_multiple_tags(self):
        """Test filtering by multiple tags (OR logic)"""
        response = self.client.get('/api/search/?tag=friend&tag=manager')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should return entities with either tag
        displays = [item['display'] for item in response.data]
        self.assertIn('Alice Smith', displays)  # has 'friend'
        self.assertIn('Bob Jones', displays)    # has 'friend'
        self.assertIn('Charlie Brown', displays)  # has 'manager'
    
    def test_combined_search_and_filter(self):
        """Test combining search query with filters"""
        response = self.client.get('/api/search/?q=Smith&type=Person')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['display'], 'Alice Smith')
    
    def test_search_returns_required_fields(self):
        """Test that search results include all required fields"""
        response = self.client.get('/api/search/?q=Alice')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data), 0)
        
        entity = response.data[0]
        # Check required fields
        self.assertIn('id', entity)
        self.assertIn('type', entity)
        self.assertIn('display', entity)
        self.assertIn('description', entity)
        self.assertIn('tags', entity)
        self.assertIn('urls', entity)
        self.assertIn('photos', entity)
        self.assertIn('attachments', entity)
    
    def test_search_with_urls(self):
        """Test that URLs are included in search results"""
        person = Person.objects.create(
            user=self.user,
            display='Web Developer',
            urls=[
                {'url': 'https://example.com', 'caption': 'Website'}
            ]
        )
        
        response = self.client.get('/api/search/?q=Web Developer')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Find the entity in results
        entity = next((e for e in response.data if e['id'] == str(person.id)), None)
        self.assertIsNotNone(entity)
        self.assertIn('urls', entity)
        self.assertEqual(len(entity['urls']), 1)
        self.assertEqual(entity['urls'][0]['url'], 'https://example.com')
    
    def test_search_pagination(self):
        """Test search pagination (if implemented)"""
        # Create many entities
        for i in range(25):
            Person.objects.create(
                user=self.user,
                display=f'Test Person {i}',
                first_name=f'Test{i}'
            )
        
        response = self.client.get('/api/search/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return results (exact count depends on pagination settings)
        self.assertGreater(len(response.data), 0)
    
    def test_search_special_characters(self):
        """Test search with special characters"""
        person = Person.objects.create(
            user=self.user,
            display="O'Brien",
            first_name="Patrick",
            last_name="O'Brien"
        )
        
        response = self.client.get('/api/search/?q=O\'Brien')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        displays = [item['display'] for item in response.data]
        self.assertIn("O'Brien", displays)
    
    def test_search_unicode(self):
        """Test search with unicode characters"""
        person = Person.objects.create(
            user=self.user,
            display='José García',
            first_name='José',
            last_name='García'
        )
        
        response = self.client.get('/api/search/?q=José')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        displays = [item['display'] for item in response.data]
        self.assertIn('José García', displays)
    
    def test_search_user_isolation(self):
        """Test that search results are isolated by user"""
        # Create second user and entities
        user2 = User.objects.create_user(
            username='testuser2',
            email='user2@example.com',
            password='testpass123'
        )
        Person.objects.create(
            user=user2,
            display='User 2 Person',
            first_name='User2'
        )
        
        # Search as first user
        response = self.client.get('/api/search/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should not see user2's entities
        displays = [item['display'] for item in response.data]
        self.assertNotIn('User 2 Person', displays)
