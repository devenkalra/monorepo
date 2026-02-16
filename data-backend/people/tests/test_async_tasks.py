"""
Tests for async tasks with progress tracking
"""
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status
from people.models import Entity, Person, Note, Tag
from people.tasks import reindex_user_entities, import_entities_async, export_entities_async
import json
import time

User = get_user_model()


class AsyncTasksTest(TransactionTestCase):
    """Test async tasks with progress tracking"""
    
    def setUp(self):
        """Set up test data"""
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def tearDown(self):
        """Clean up"""
        cache.clear()
        Entity.objects.all().delete()
        User.objects.all().delete()
    
    def test_reindex_task_progress(self):
        """Test reindex task with progress tracking"""
        # Create some entities
        Person.objects.create(
            user=self.user,
            display='Test Person',
            first_name='Test',
            last_name='Person'
        )
        Note.objects.create(
            user=self.user,
            display='Test Note',
            description='Test content'
        )
        
        # Start reindex task
        response = self.client.post('/api/entities/reindex/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('task_id', data)
        
        task_id = data['task_id']
        
        # Wait a bit for task to process
        time.sleep(2)
        
        # Check progress
        progress_response = self.client.get(f'/api/entities/tasks/{task_id}/progress/')
        self.assertEqual(progress_response.status_code, status.HTTP_200_OK)
        
        progress = progress_response.json()
        self.assertIn('status', progress)
        self.assertIn(progress['status'], ['processing', 'completed'])
    
    def test_task_cancellation(self):
        """Test task cancellation"""
        # Create many entities to have time to cancel
        for i in range(100):
            Person.objects.create(
                user=self.user,
                display=f'Person {i}',
                first_name=f'First{i}',
                last_name=f'Last{i}'
            )
        
        # Start reindex
        response = self.client.post('/api/entities/reindex/')
        task_id = response.json()['task_id']
        
        # Immediately cancel
        cancel_response = self.client.post(f'/api/entities/tasks/{task_id}/cancel/')
        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
        self.assertTrue(cancel_response.json()['success'])
        
        # Wait for cancellation to take effect
        time.sleep(2)
        
        # Check progress shows cancelled
        progress_response = self.client.get(f'/api/entities/tasks/{task_id}/progress/')
        progress = progress_response.json()
        # Task should be cancelled or completed (if it finished before cancel took effect)
        self.assertIn(progress['status'], ['cancelled', 'completed'])
    
    def test_export_async(self):
        """Test async export"""
        # Create test data
        Person.objects.create(
            user=self.user,
            display='Export Test',
            first_name='Export',
            last_name='Test'
        )
        
        # Start export
        response = self.client.post('/api/entities/export-async/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertTrue(data['success'])
        task_id = data['task_id']
        
        # Wait for export to complete
        time.sleep(3)
        
        # Check progress
        progress_response = self.client.get(f'/api/entities/tasks/{task_id}/progress/')
        progress = progress_response.json()
        self.assertEqual(progress['status'], 'completed')
        
        # Download export
        download_response = self.client.get(f'/api/entities/tasks/{task_id}/download/')
        self.assertEqual(download_response.status_code, status.HTTP_200_OK)
        
        # Verify export data
        export_data = json.loads(download_response.content)
        self.assertEqual(export_data['export_version'], '1.0')
        self.assertIn('people', export_data)
        self.assertEqual(len(export_data['people']), 1)
    
    def test_import_async(self):
        """Test async import"""
        # Create export data
        export_data = {
            'export_version': '1.0',
            'tags': [{'name': 'Test Tag'}],
            'people': [{
                'id': '12345678-1234-1234-1234-123456789012',
                'display': 'Import Test',
                'first_name': 'Import',
                'last_name': 'Test',
                'emails': ['import@test.com'],
                'phones': [],
                'tags': []
            }],
            'notes': [],
            'locations': [],
            'movies': [],
            'books': [],
            'containers': [],
            'assets': [],
            'orgs': [],
            'relations': []
        }
        
        # Create file
        import io
        file_content = json.dumps(export_data)
        file = io.BytesIO(file_content.encode())
        file.name = 'test_import.json'
        
        # Start import
        response = self.client.post(
            '/api/entities/import-async/',
            {'file': file},
            format='multipart'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertTrue(data['success'])
        task_id = data['task_id']
        
        # Wait for import to complete
        time.sleep(3)
        
        # Check progress
        progress_response = self.client.get(f'/api/entities/tasks/{task_id}/progress/')
        progress = progress_response.json()
        self.assertEqual(progress['status'], 'completed')
        
        # Verify imported data
        people = Person.objects.filter(user=self.user)
        self.assertEqual(people.count(), 1)
        self.assertEqual(people.first().first_name, 'Import')
    
    def test_progress_not_found(self):
        """Test progress endpoint with invalid task ID"""
        response = self.client.get('/api/entities/tasks/invalid-task-id/progress/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_download_not_found(self):
        """Test download endpoint with invalid task ID"""
        response = self.client.get('/api/entities/tasks/invalid-task-id/download/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
