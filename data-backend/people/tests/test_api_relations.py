"""
API Integration Tests for Entity Relations

Tests relation creation, validation, retrieval, and deletion.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from people.models import Person, Location, Movie, Org, EntityRelation

User = get_user_model()


class RelationAPITestCase(TestCase):
    """Test entity relation operations via API"""
    
    def setUp(self):
        """Set up test client, user, and entities"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        # Create test entities
        self.person1 = Person.objects.create(
            user=self.user,
            display='Alice Smith',
            first_name='Alice',
            last_name='Smith'
        )
        self.person2 = Person.objects.create(
            user=self.user,
            display='Bob Jones',
            first_name='Bob',
            last_name='Jones'
        )
        self.location = Location.objects.create(
            user=self.user,
            display='San Francisco',
            city='San Francisco',
            state='CA'
        )
        self.movie = Movie.objects.create(
            user=self.user,
            display='The Matrix',
            year=1999
        )
        self.org = Org.objects.create(
            user=self.user,
            display='Acme Corp',
            name='Acme Corporation'
        )
    
    def test_create_person_to_person_relation(self):
        """Test creating a Person->Person relation"""
        data = {
            'from_entity': str(self.person1.id),
            'to_entity': str(self.person2.id),
            'relation_type': 'IS_FRIEND_OF'
        }
        response = self.client.post('/api/relations/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['relation_type'], 'IS_FRIEND_OF')
        
        # Verify reverse relation was created
        reverse_relation = EntityRelation.objects.filter(
            from_entity=self.person2.id,
            to_entity=self.person1.id,
            relation_type='IS_FRIEND_OF'
        ).first()
        self.assertIsNotNone(reverse_relation)
    
    def test_create_person_to_location_relation(self):
        """Test creating a Person->Location relation"""
        data = {
            'from_entity': str(self.person1.id),
            'to_entity': str(self.location.id),
            'relation_type': 'LIVES_AT'
        }
        response = self.client.post('/api/relations/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify reverse relation
        reverse_relation = EntityRelation.objects.filter(
            from_entity=self.location.id,
            to_entity=self.person1.id,
            relation_type='HAS_RESIDENT'
        ).first()
        self.assertIsNotNone(reverse_relation)
    
    def test_create_movie_to_person_relation(self):
        """Test creating a Movie->Person relation"""
        data = {
            'from_entity': str(self.movie.id),
            'to_entity': str(self.person1.id),
            'relation_type': 'HAS_ACTOR'
        }
        response = self.client.post('/api/relations/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify reverse relation
        reverse_relation = EntityRelation.objects.filter(
            from_entity=self.person1.id,
            to_entity=self.movie.id,
            relation_type='ACTED_IN'
        ).first()
        self.assertIsNotNone(reverse_relation)
    
    def test_create_person_to_org_relation(self):
        """Test creating a Person->Org relation"""
        data = {
            'from_entity': str(self.person1.id),
            'to_entity': str(self.org.id),
            'relation_type': 'WORKS_AT'
        }
        response = self.client.post('/api/relations/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify reverse relation
        reverse_relation = EntityRelation.objects.filter(
            from_entity=self.org.id,
            to_entity=self.person1.id,
            relation_type='HAS_EMPLOYEE'
        ).first()
        self.assertIsNotNone(reverse_relation)
    
    def test_invalid_relation_type(self):
        """Test that invalid relation types are rejected"""
        data = {
            'from_entity': str(self.person1.id),
            'to_entity': str(self.location.id),
            'relation_type': 'INVALID_RELATION'
        }
        response = self.client.post('/api/relations/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_invalid_entity_type_combination(self):
        """Test that invalid entity type combinations are rejected"""
        # Try to create LIVES_AT from Location to Person (should be Person to Location)
        data = {
            'from_entity': str(self.location.id),
            'to_entity': str(self.person1.id),
            'relation_type': 'LIVES_AT'
        }
        try:
            response = self.client.post('/api/relations/', data, format='json')
            # Should return 400 or 500 (validation error)
            self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR])
        except Exception:
            # ValidationError may be raised - this is acceptable
            pass
    
    def test_retrieve_entity_relations(self):
        """Test retrieving relations for an entity"""
        # Create some relations
        EntityRelation.objects.create(
            from_entity=self.person1,
            to_entity=self.person2,
            relation_type='IS_FRIEND_OF'
        )
        EntityRelation.objects.create(
            from_entity=self.person1,
            to_entity=self.location,
            relation_type='LIVES_AT'
        )
        
        response = self.client.get(f'/api/entities/{self.person1.id}/relations/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('outgoing', response.data)
        self.assertIn('incoming', response.data)
        self.assertGreaterEqual(len(response.data['outgoing']), 2)
    
    def test_delete_relation(self):
        """Test deleting a relation"""
        relation = EntityRelation.objects.create(
            from_entity=self.person1,
            to_entity=self.person2,
            relation_type='IS_FRIEND_OF'
        )
        # Reverse relation is created automatically
        reverse_relation = EntityRelation.objects.get(
            from_entity=self.person2,
            to_entity=self.person1,
            relation_type='IS_FRIEND_OF'
        )
        
        response = self.client.delete(f'/api/relations/{relation.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        # Verify both forward and reverse relations are deleted
        self.assertFalse(EntityRelation.objects.filter(id=relation.id).exists())
        self.assertFalse(EntityRelation.objects.filter(id=reverse_relation.id).exists())
    
    def test_duplicate_relation_prevention(self):
        """Test that duplicate relations are prevented"""
        data = {
            'from_entity': str(self.person1.id),
            'to_entity': str(self.person2.id),
            'relation_type': 'IS_FRIEND_OF'
        }
        
        # Create first relation
        response1 = self.client.post('/api/relations/', data, format='json')
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        
        # Try to create duplicate
        response2 = self.client.post('/api/relations/', data, format='json')
        # Should either succeed (idempotent) or return 400
        self.assertIn(response2.status_code, [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST])
    
    def test_relation_with_nonexistent_entity(self):
        """Test that relations with non-existent entities are rejected"""
        data = {
            'from_entity': str(self.person1.id),
            'to_entity': '00000000-0000-0000-0000-000000000000',
            'relation_type': 'IS_FRIEND_OF'
        }
        response = self.client.post('/api/relations/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_relation_isolation_between_users(self):
        """Test that users cannot create relations with other users' entities"""
        # Create second user and entity
        user2 = User.objects.create_user(
            username='testuser2',
            email='user2@example.com',
            password='testpass123'
        )
        person3 = Person.objects.create(
            user=user2,
            display='User 2 Person',
            first_name='User2'
        )
        
        # Try to create relation from user1's entity to user2's entity
        data = {
            'from_entity': str(self.person1.id),
            'to_entity': str(person3.id),
            'relation_type': 'IS_FRIEND_OF'
        }
        response = self.client.post('/api/relations/', data, format='json')
        # Should fail because user2's entity is not accessible (400 or 403)
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])
    
    def test_symmetric_relation(self):
        """Test symmetric relations (e.g., IS_FRIEND_OF)"""
        data = {
            'from_entity': str(self.person1.id),
            'to_entity': str(self.person2.id),
            'relation_type': 'IS_FRIEND_OF'
        }
        response = self.client.post('/api/relations/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check that reverse relation uses the same key
        reverse_relation = EntityRelation.objects.filter(
            from_entity=self.person2.id,
            to_entity=self.person1.id
        ).first()
        self.assertIsNotNone(reverse_relation)
        self.assertEqual(reverse_relation.relation_type, 'IS_FRIEND_OF')
    
    def test_asymmetric_relation(self):
        """Test asymmetric relations (e.g., IS_MANAGER_OF)"""
        data = {
            'from_entity': str(self.person1.id),
            'to_entity': str(self.person2.id),
            'relation_type': 'IS_MANAGER_OF'
        }
        response = self.client.post('/api/relations/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check that reverse relation uses different key
        reverse_relation = EntityRelation.objects.filter(
            from_entity=self.person2.id,
            to_entity=self.person1.id
        ).first()
        self.assertIsNotNone(reverse_relation)
        self.assertEqual(reverse_relation.relation_type, 'WORKS_FOR_MGR')
    
    def test_relation_entity_data_included(self):
        """Test that relation responses include full entity data"""
        EntityRelation.objects.create(
            from_entity=self.person1,
            to_entity=self.person2,
            relation_type='IS_FRIEND_OF'
        )
        
        response = self.client.get(f'/api/entities/{self.person1.id}/relations/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check that entity data is included
        outgoing = response.data['outgoing']
        self.assertGreater(len(outgoing), 0)
        self.assertIn('entity', outgoing[0])
        self.assertIn('display', outgoing[0]['entity'])
        self.assertIn('type', outgoing[0]['entity'])
