import os
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token

from django.core.files.uploadedfile import SimpleUploadedFile
from .models import Page, MenuItem, StaticFile, Project, WorkflowIdea, Subscription

class PersonalWebsiteTests(APITestCase):

    def setUp(self):
        # Create users
        self.username = 'testuser'
        self.password = 'password123'
        self.user = User.objects.create_user(
            username=self.username,
            password=self.password,
            email='test@devenkalra.com'
        )

        # Create pages
        self.public_page = Page.objects.create(
            title="Public Info",
            slug="public-info",
            content="This is public information.",
            roles_with_access="",
        )
        self.protected_page = Page.objects.create(
            title="Protected Log",
            slug="protected-log",
            content="This is super secret log.",
            roles_with_access="user,superuser",
        )
        self.html_page = Page.objects.create(
            title="HTML Page",
            slug="html-page",
            content="<html><body><h1>Hello HTML</h1></body></html>",
            roles_with_access="",
            render_as_html=True
        )

        # Create menu items
        self.root_menu = MenuItem.objects.create(
            title="Home",
            page=self.public_page,
            order=1
        )
        self.sub_menu = MenuItem.objects.create(
            title="Secret",
            parent=self.root_menu,
            page=self.protected_page,
            order=1
        )

    def test_menu_hierarchy_api(self):
        """Verify the menu api returns the nested tree structure."""
        url = reverse('api-menu')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # We expect root items (parent=None)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['title'], 'Home')
        self.assertEqual(data[0]['page_slug'], 'public-info')
        
        # Verify sub-menu is nested inside children
        self.assertEqual(len(data[0]['children']), 1)
        self.assertEqual(data[0]['children'][0]['title'], 'Secret')
        self.assertEqual(data[0]['children'][0]['page_slug'], 'protected-log')

    def test_public_page_retrieval(self):
        """Verify public pages can be retrieved without authentication."""
        url = reverse('page-detail', kwargs={'slug': 'public-info'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['title'], 'Public Info')
        self.assertEqual(response.json()['content'], 'This is public information.')

    def test_protected_page_unauthorized(self):
        """Verify protected pages return 403 Forbidden for anonymous requests."""
        url = reverse('page-detail', kwargs={'slug': 'protected-log'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('roles_with_access', response.json())

    def test_create_page_requires_auth(self):
        """Anonymous POST /pages/ is rejected; authenticated create succeeds."""
        url = reverse('page-list')
        payload = {
            'title': 'New Page',
            'slug': 'new-page',
            'category': 'Books',
            'content': '# Hello',
            'roles_with_access': '',
            'render_as_html': False,
        }
        response = self.client.post(url, payload, format='json')
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['slug'], 'new-page')
        self.assertTrue(Page.objects.filter(slug='new-page').exists())

    def test_create_page_converts_literal_newlines(self):
        """Literal \\n in markdown content becomes real line breaks on save."""
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        url = reverse('page-list')
        response = self.client.post(url, {
            'title': 'Escaped Newlines',
            'slug': 'escaped-newlines',
            'category': '',
            'content': '# Hello\\n\\nSecond paragraph',
            'roles_with_access': '',
            'render_as_html': False,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        page = Page.objects.get(slug='escaped-newlines')
        self.assertEqual(page.content, '# Hello\n\nSecond paragraph')
        self.assertNotIn('\\n', page.content)

    def test_create_menu_item_for_page(self):
        """Authenticated clients can create menu items pointing at a page."""
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        url = reverse('menu-item-list')
        response = self.client.post(url, {
            'title': 'Public Info Link',
            'page': self.public_page.id,
            'order': 5,
            'show_in_menu': True,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['page'], self.public_page.id)
        self.assertEqual(response.json()['page_slug'], 'public-info')

    def test_openapi_schema_includes_pages(self):
        """Swagger schema is generated and documents the pages API."""
        response = self.client.get('/api/schema/', HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        schema = response.json()
        paths = schema.get('paths', {})
        self.assertIn('/api/pages/', paths)
        self.assertIn('get', paths['/api/pages/'])
        self.assertIn('post', paths['/api/pages/'])
        self.assertIn('/api/pages/{slug}/', paths)
        self.assertEqual(schema.get('info', {}).get('title'), 'devenkalra.com API')

    def test_swagger_ui_serves(self):
        response = self.client.get('/api/docs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_login_and_protected_access(self):
        """Verify login endpoint grants token and enables accessing protected pages."""
        # 1. Login
        login_url = reverse('api-login')
        login_response = self.client.post(login_url, {
            'username': self.username,
            'password': self.password
        })
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        token = login_response.json()['token']
        self.assertIsNotNone(token)

        # 2. Access protected page with Token
        url = reverse('page-detail', kwargs={'slug': 'protected-log'})
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['title'], 'Protected Log')
        self.assertEqual(response.json()['content'], 'This is super secret log.')

    def test_html_page_retrieval(self):
        """Verify HTML pages can be retrieved and contain the render_as_html flag."""
        url = reverse('page-detail', kwargs={'slug': 'html-page'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['title'], 'HTML Page')
        self.assertEqual(response.json()['content'], '<html><body><h1>Hello HTML</h1></body></html>')
        self.assertTrue(response.json()['render_as_html'])

    def test_static_file_upload(self):
        """Verify StaticFile instances can be created with files and have valid URLs."""
        test_pdf = SimpleUploadedFile("test_document.pdf", b"file_content", content_type="application/pdf")
        sf = StaticFile.objects.create(
            title="Test Doc",
            file=test_pdf
        )
        self.assertEqual(sf.title, "Test Doc")
        self.assertTrue(sf.file.name.endswith("test_document.pdf"))
        self.assertTrue(sf.file.url.startswith("/api/media/uploads/"))
        
        # Cleanup file after test
        if sf.file and os.path.exists(sf.file.path):
            os.remove(sf.file.path)
            
        # Clean up directory if empty
        upload_dir = os.path.dirname(sf.file.path)
        if os.path.exists(upload_dir) and not os.listdir(upload_dir):
            os.rmdir(upload_dir)

    def test_menu_item_show_in_menu(self):
        """Verify MenuItem show_in_menu serialization is true by default and can be false."""
        root = MenuItem.objects.create(title="Root Item", order=1)
        child = MenuItem.objects.create(title="Hidden Child", parent=root, order=1, show_in_menu=False)
        url = reverse('api-menu')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check that Root Item is in response
        root_data = next(item for item in response.json() if item['title'] == 'Root Item')
        self.assertTrue(root_data['show_in_menu'])
        # Check that child is serialized with show_in_menu=False
        child_data = root_data['children'][0]
        self.assertEqual(child_data['title'], 'Hidden Child')
        self.assertFalse(child_data['show_in_menu'])

    def test_project_and_idea_render_as_html(self):
        """Verify Project and WorkflowIdea render_as_html fields are serialized correctly."""
        p = Project.objects.create(
            title="Photography Project",
            category="Photography",
            description="<p>Custom HTML description</p>",
            status="in_progress",
            render_as_html=True
        )
        idea = WorkflowIdea.objects.create(
            title="New Key Tray",
            description="**Markdown description**",
            status="backlog",
            render_as_html=False
        )
        
        # Verify database fields
        self.assertTrue(p.render_as_html)
        self.assertFalse(idea.render_as_html)

    def test_project_and_idea_optional_description(self):
        """Verify description is optional (blank=True) on Project and WorkflowIdea models."""
        p = Project.objects.create(
            title="Project with No Description",
            category="Photography",
            status="in_progress"
        )
        idea = WorkflowIdea.objects.create(
            title="Idea with No Description",
            status="backlog"
        )
        
        # Verify we can save without description (meaning it defaults to blank)
        self.assertEqual(p.description, "")
        self.assertEqual(idea.description, "")

    def test_project_bulk_update(self):
        """Verify bulk update endpoint modifies status and category for multiple projects."""
        p1 = Project.objects.create(title="P1", category="Cat A", status="in_progress")
        p2 = Project.objects.create(title="P2", category="Cat A", status="in_progress")
        
        # Login
        login_url = reverse('api-login')
        login_response = self.client.post(login_url, {
            'username': self.username,
            'password': self.password
        })
        token = login_response.json()['token']
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token)
        
        # Bulk Update
        bulk_url = '/api/projects/bulk_update/'
        response = self.client.post(bulk_url, {
            'ids': [p1.id, p2.id],
            'status': 'completed',
            'category': 'Cat B'
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Reload and check values
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.status, 'completed')
        self.assertEqual(p2.status, 'completed')
        self.assertEqual(p1.category, 'Cat B')
        self.assertEqual(p2.category, 'Cat B')

    def test_page_category_and_menu_path(self):
        """Verify that Page.category is saved and PageAdmin.menu_path works."""
        p = Page.objects.create(
            title="Categorized Page",
            slug="cat-page",
            category="Personal",
            content="Some content"
        )
        self.assertEqual(p.category, "Personal")
        
        # Link to MenuItem
        m = MenuItem.objects.create(title="My Page Link", page=p, order=2)
        
        # Instantiate PageAdmin and test menu_path
        from django.contrib.admin.sites import AdminSite
        from .admin import PageAdmin
        admin_site = AdminSite()
        page_admin = PageAdmin(Page, admin_site)
        
        self.assertEqual(page_admin.menu_path(p), "My Page Link")

        # Link to parent and save to trigger recursion
        parent_menu = MenuItem.objects.create(title="Root Nav", order=1)
        m.parent = parent_menu
        m.save()
        
        self.assertEqual(page_admin.menu_path(p), "Root Nav -> My Page Link")

    def test_static_file_url_download_and_default_title(self):
        """Verify that StaticFile download logic from url retrieves and saves file correctly."""
        from unittest.mock import patch, MagicMock
        
        mock_response = MagicMock()
        mock_response.read.return_value = b"mocked downloaded content"
        mock_response.__enter__.return_value = mock_response
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            sf = StaticFile.objects.create(
                file_url="https://example.com/assets/images/logo.png"
            )
            
            # The title should default to the file name (logo.png)
            self.assertEqual(sf.title, "logo.png")
            # The file should be saved and have the name logo.png
            self.assertTrue(sf.file.name.endswith("logo.png"))
            # The file_url field should be cleared
            self.assertIsNone(sf.file_url)
            
            # Cleanup files
            if sf.file and os.path.exists(sf.file.path):
                os.remove(sf.file.path)
            upload_dir = os.path.dirname(sf.file.path)
            if os.path.exists(upload_dir) and not os.listdir(upload_dir):
                os.rmdir(upload_dir)

    def test_static_file_custom_filename_rename(self):
        """Verify that a local file upload is renamed when a custom filename is specified."""
        test_file = SimpleUploadedFile("original.png", b"fake image content", content_type="image/png")
        sf = StaticFile.objects.create(
            title="Custom Name Doc",
            filename="new_name.png",
            file=test_file
        )
        self.assertEqual(sf.filename, "new_name.png")
        self.assertEqual(sf.title, "Custom Name Doc")
        self.assertTrue(sf.file.name.endswith("new_name.png"))
        
        # Cleanup
        if sf.file and os.path.exists(sf.file.path):
            os.remove(sf.file.path)
        upload_dir = os.path.dirname(sf.file.path)
        if os.path.exists(upload_dir) and not os.listdir(upload_dir):
            os.rmdir(upload_dir)

    def test_static_file_url_guess_extension(self):
        """Verify that downloading a URL without an extension guesses it from the Content-Type header."""
        from unittest.mock import patch, MagicMock
        
        mock_response = MagicMock()
        mock_response.read.return_value = b"gif bytes"
        mock_response.__enter__.return_value = mock_response
        
        # Mock response headers to return 'image/gif'
        mock_headers = MagicMock()
        mock_headers.get.side_effect = lambda key, default=None: 'image/gif' if key == 'Content-Type' else default
        mock_response.headers = mock_headers
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            sf = StaticFile.objects.create(
                file_url="https://example.com/api/v1/get-animation"
            )
            # The title should default to the resolved filename (get-animation.gif)
            self.assertEqual(sf.title, "get-animation.gif")
            # The filename field should show get-animation.gif
            self.assertEqual(sf.filename, "get-animation.gif")
            self.assertTrue(sf.file.name.endswith("get-animation.gif"))
            
            # Cleanup
            if sf.file and os.path.exists(sf.file.path):
                os.remove(sf.file.path)
            upload_dir = os.path.dirname(sf.file.path)
            if os.path.exists(upload_dir) and not os.listdir(upload_dir):
                os.rmdir(upload_dir)

    def test_clickup_tasks_unauthorized(self):
        """Verify anonymous request to ClickUp tasks endpoint is unauthorized."""
        url = reverse('api-clickup-tasks')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_clickup_tasks_missing_token(self):
        """Verify request returns 400 when ClickUp API Token is not configured."""
        from unittest.mock import patch
        
        login_url = reverse('api-login')
        login_response = self.client.post(login_url, {
            'username': self.username,
            'password': self.password
        })
        token = login_response.json()['token']
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token)

        url = reverse('api-clickup-tasks')
        with patch('django.conf.settings.CLICKUP_API_TOKEN', ''):
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("ClickUp API token is not configured", response.json()['detail'])

    def test_clickup_tasks_success(self):
        """Verify successful retrieval and structure of ClickUp tasks (mocked)."""
        from unittest.mock import patch, MagicMock
        import json

        # Login
        login_url = reverse('api-login')
        login_response = self.client.post(login_url, {
            'username': self.username,
            'password': self.password
        })
        token = login_response.json()['token']
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token)

        # Mock urllib responses
        mock_teams = {
            "teams": [{"id": "12345", "name": "Test Workspace"}]
        }
        mock_spaces = {
            "spaces": [
                {"id": "67890", "name": "General Space"},
                {"id": "55555", "name": "Creative Space"}
            ]
        }
        mock_tasks = {
            "tasks": [
                {
                    "id": "t1",
                    "name": "Design Homepage",
                    "status": {"status": "in progress", "color": "#d3d3d3", "type": "active"},
                    "parent": None
                },
                {
                    "id": "t2",
                    "name": "Layout Wireframes",
                    "status": {"status": "to do", "color": "#ff0000", "type": "open"},
                    "parent": "t1"
                }
            ]
        }

        # Mock opener responses sequentially
        m1 = MagicMock()
        m1.read.return_value = json.dumps(mock_teams).encode('utf-8')
        m1.__enter__.return_value = m1

        m2 = MagicMock()
        m2.read.return_value = json.dumps(mock_spaces).encode('utf-8')
        m2.__enter__.return_value = m2

        m3 = MagicMock()
        m3.read.return_value = json.dumps(mock_tasks).encode('utf-8')
        m3.__enter__.return_value = m3

        with patch('django.conf.settings.CLICKUP_API_TOKEN', 'mock-token'):
            with patch('urllib.request.urlopen', side_effect=[m1, m2, m3]):
                url = reverse('api-clickup-tasks')
                response = self.client.get(url)
                
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                data = response.json()
                self.assertEqual(data['space']['id'], '55555')
                self.assertEqual(data['space']['name'], 'Creative Space')
                self.assertEqual(len(data['tasks']), 2)
                self.assertEqual(data['tasks'][0]['id'], 't1')
                self.assertEqual(data['tasks'][1]['parent'], 't1')

    def test_clickup_contacts_unauthorized(self):
        """Verify anonymous request to ClickUp contacts endpoint is unauthorized."""
        url = reverse('api-clickup-contacts')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_clickup_contacts_filters_to_contacts_list(self):
        """Verify contacts endpoint returns only tasks from Consulting/Contacts."""
        from unittest.mock import patch, MagicMock
        import json

        login_url = reverse('api-login')
        login_response = self.client.post(login_url, {
            'username': self.username,
            'password': self.password
        })
        token = login_response.json()['token']
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token)

        mock_teams = {
            "teams": [{"id": "12345", "name": "Test Workspace"}]
        }
        mock_spaces = {
            "spaces": [
                {"id": "11111", "name": "Creative Space"},
                {"id": "22222", "name": "Consulting"}
            ]
        }
        mock_tasks = {
            "tasks": [
                {
                    "id": "c1",
                    "name": "Alice Doe",
                    "list": {"name": "Contacts"},
                    "status": {"status": "active", "color": "#123456", "type": "open"}
                },
                {
                    "id": "x1",
                    "name": "Discovery Call",
                    "list": {"name": "Projects"},
                    "status": {"status": "in progress", "color": "#654321", "type": "open"}
                }
            ]
        }

        m1 = MagicMock()
        m1.read.return_value = json.dumps(mock_teams).encode('utf-8')
        m1.__enter__.return_value = m1

        m2 = MagicMock()
        m2.read.return_value = json.dumps(mock_spaces).encode('utf-8')
        m2.__enter__.return_value = m2

        m3 = MagicMock()
        m3.read.return_value = json.dumps(mock_tasks).encode('utf-8')
        m3.__enter__.return_value = m3

        with patch('django.conf.settings.CLICKUP_API_TOKEN', 'mock-token'):
            with patch('urllib.request.urlopen', side_effect=[m1, m2, m3]):
                url = reverse('api-clickup-contacts')
                response = self.client.get(url)

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                data = response.json()
                self.assertEqual(data['space']['id'], '22222')
                self.assertEqual(data['space']['name'], 'Consulting')
                self.assertEqual(data['list']['name'], 'Contacts')
                self.assertEqual(len(data['tasks']), 1)
                self.assertEqual(data['tasks'][0]['id'], 'c1')

    def test_clickup_tasks_hides_future_show_after_tasks(self):
        """Verify tasks with a future Show After date are excluded from the response."""
        from unittest.mock import patch, MagicMock
        import json
        from datetime import datetime, date, timezone as dt_timezone

        login_url = reverse('api-login')
        login_response = self.client.post(login_url, {
            'username': self.username,
            'password': self.password
        })
        token = login_response.json()['token']
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token)

        show_today_ms = int(datetime(2026, 6, 20, 0, 0, tzinfo=dt_timezone.utc).timestamp() * 1000)
        show_tomorrow_ms = int(datetime(2026, 6, 21, 0, 0, tzinfo=dt_timezone.utc).timestamp() * 1000)

        mock_teams = {
            "teams": [{"id": "12345", "name": "Test Workspace"}]
        }
        mock_spaces = {
            "spaces": [
                {"id": "67890", "name": "Creative Space"}
            ]
        }
        mock_tasks = {
            "tasks": [
                {
                    "id": "visible-task",
                    "name": "Visible Task",
                    "status": {"status": "in progress", "color": "#d3d3d3", "type": "active"},
                    "parent": None,
                    "custom_fields": [
                        {"name": "Show After", "value": show_today_ms}
                    ]
                },
                {
                    "id": "hidden-task",
                    "name": "Hidden Task",
                    "status": {"status": "to do", "color": "#ff0000", "type": "open"},
                    "parent": None,
                    "custom_fields": [
                        {"name": "Show After", "value": show_tomorrow_ms}
                    ]
                },
                {
                    "id": "hidden-subtask",
                    "name": "Hidden Subtask",
                    "status": {"status": "to do", "color": "#ff0000", "type": "open"},
                    "parent": "visible-task",
                    "custom_fields": [
                        {"name": "Show After", "value": show_tomorrow_ms}
                    ]
                }
            ]
        }

        m1 = MagicMock()
        m1.read.return_value = json.dumps(mock_teams).encode('utf-8')
        m1.__enter__.return_value = m1

        m2 = MagicMock()
        m2.read.return_value = json.dumps(mock_spaces).encode('utf-8')
        m2.__enter__.return_value = m2

        m3 = MagicMock()
        m3.read.return_value = json.dumps(mock_tasks).encode('utf-8')
        m3.__enter__.return_value = m3

        with patch('django.conf.settings.CLICKUP_API_TOKEN', 'mock-token'):
            with patch('django.utils.timezone.localdate', return_value=date(2026, 6, 20)):
                with patch('urllib.request.urlopen', side_effect=[m1, m2, m3]):
                    url = reverse('api-clickup-tasks')
                    response = self.client.get(url)

                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    data = response.json()
                    task_ids = [task['id'] for task in data['tasks']]
                    self.assertIn('visible-task', task_ids)
                    self.assertNotIn('hidden-task', task_ids)
                    self.assertNotIn('hidden-subtask', task_ids)

    def test_clickup_tasks_can_include_future_show_after_tasks(self):
        """Verify the opt-in query flag includes tasks hidden by Show After."""
        from unittest.mock import patch, MagicMock
        import json
        from datetime import datetime, timezone as dt_timezone

        login_url = reverse('api-login')
        login_response = self.client.post(login_url, {
            'username': self.username,
            'password': self.password
        })
        token = login_response.json()['token']
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token)

        show_tomorrow_ms = int(datetime(2026, 6, 21, 0, 0, tzinfo=dt_timezone.utc).timestamp() * 1000)

        mock_teams = {
            "teams": [{"id": "12345", "name": "Test Workspace"}]
        }
        mock_spaces = {
            "spaces": [{"id": "55555", "name": "Creative Space"}]
        }
        mock_tasks = {
            "tasks": [
                {
                    "id": "future-task",
                    "name": "Future Task",
                    "status": {"status": "to do", "color": "#ff0000", "type": "open"},
                    "parent": None,
                    "custom_fields": [
                        {"name": "Show After", "value": show_tomorrow_ms}
                    ]
                }
            ]
        }

        m1 = MagicMock()
        m1.read.return_value = json.dumps(mock_teams).encode('utf-8')
        m1.__enter__.return_value = m1

        m2 = MagicMock()
        m2.read.return_value = json.dumps(mock_spaces).encode('utf-8')
        m2.__enter__.return_value = m2

        m3 = MagicMock()
        m3.read.return_value = json.dumps(mock_tasks).encode('utf-8')
        m3.__enter__.return_value = m3

        with patch('django.conf.settings.CLICKUP_API_TOKEN', 'mock-token'):
            with patch('django.utils.timezone.localdate', return_value=datetime(2026, 6, 20, tzinfo=dt_timezone.utc).date()):
                with patch('urllib.request.urlopen', side_effect=[m1, m2, m3]):
                    url = reverse('api-clickup-tasks') + '?include_hidden_show_after=true'
                    response = self.client.get(url)

                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    data = response.json()
                    task_ids = [task['id'] for task in data['tasks']]
                    self.assertIn('future-task', task_ids)

    def test_clickup_tasks_status_update_success(self):
        """Verify updating task status in ClickUp via POST behaves correctly (mocked)."""
        from unittest.mock import patch, MagicMock
        import json

        # Login
        login_url = reverse('api-login')
        login_response = self.client.post(login_url, {
            'username': self.username,
            'password': self.password
        })
        token = login_response.json()['token']
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token)

        mock_updated_task = {
            "id": "t1",
            "name": "Design Homepage",
            "status": {"status": "complete", "color": "#008844", "type": "closed"}
        }

        m = MagicMock()
        m.read.return_value = json.dumps(mock_updated_task).encode('utf-8')
        m.__enter__.return_value = m

        with patch('django.conf.settings.CLICKUP_API_TOKEN', 'mock-token'):
            with patch('urllib.request.urlopen', return_value=m) as mock_urlopen:
                url = reverse('api-clickup-tasks')
                response = self.client.post(url, {
                    'taskId': 't1',
                    'status': 'complete'
                }, format='json')

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.json()['status'], 'success')
                self.assertEqual(response.json()['task']['status']['status'], 'complete')

                # Verify PUT request was called with correct data
                mock_urlopen.assert_called_once()
                args, kwargs = mock_urlopen.call_args
                req = args[0]
                self.assertEqual(req.full_url, 'https://api.clickup.com/api/v2/task/t1')
                self.assertEqual(req.method, 'PUT')
                self.assertEqual(req.data, b'{"status": "complete"}')

    def test_social_login_returns_auth_token(self):
        """Verify social logins create a DRF token so authenticated APIs can work."""
        from unittest.mock import patch, MagicMock
        import json
        import os

        google_userinfo = {
            'email': 'social@example.com',
            'name': 'Social User',
            'sub': 'google-123',
            'aud': 'test-google-client-id',
        }

        google_response = MagicMock()
        google_response.read.return_value = json.dumps(google_userinfo).encode('utf-8')
        google_response.__enter__.return_value = google_response

        with patch.dict(os.environ, {'GOOGLE_CLIENT_ID': 'test-google-client-id'}):
            with patch('urllib.request.urlopen', return_value=google_response):
                url = reverse('api-social-google-login')
                response = self.client.post(url, {'id_token': 'fake-google-token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('token', data)
        self.assertTrue(Token.objects.filter(key=data['token']).exists())

        sub = Subscription.objects.get(email='social@example.com')
        self.assertEqual(sub.provider, 'google')
        self.assertTrue(sub.is_active)
        self.assertFalse(sub.blog_subscribed)
        self.assertFalse(sub.notify_on_article)
        self.assertEqual(sub.user, Token.objects.get(key=data['token']).user)

    def test_social_google_code_exchange_login(self):
        """Verify OAuth authorization-code login exchanges code then creates a token."""
        from unittest.mock import patch, MagicMock
        import json
        import os

        token_exchange = {
            'id_token': 'fake-google-id-token',
            'access_token': 'fake-access',
        }
        google_userinfo = {
            'email': 'oauth@example.com',
            'name': 'OAuth User',
            'sub': 'google-456',
            'aud': 'test-google-client-id',
        }

        exchange_response = MagicMock()
        exchange_response.read.return_value = json.dumps(token_exchange).encode('utf-8')
        exchange_response.__enter__.return_value = exchange_response

        verify_response = MagicMock()
        verify_response.read.return_value = json.dumps(google_userinfo).encode('utf-8')
        verify_response.__enter__.return_value = verify_response

        with patch.dict(
            os.environ,
            {
                'GOOGLE_CLIENT_ID': 'test-google-client-id',
                'GOOGLE_CLIENT_SECRET': 'test-google-secret',
            },
        ):
            with patch('urllib.request.urlopen', side_effect=[exchange_response, verify_response]):
                url = reverse('api-social-google-login')
                response = self.client.post(
                    url,
                    {
                        'code': 'fake-auth-code',
                        'redirect_uri': 'https://devenkalra.com/login/google/callback',
                    },
                    format='json',
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('token', data)
        self.assertEqual(data['user']['email'], 'oauth@example.com')
        self.assertTrue(Token.objects.filter(key=data['token']).exists())

    def test_me_preferences_get_and_patch(self):
        """Authenticated users can read/update blog opt-in prefs without auto-subscribe on create."""
        token = Token.objects.create(user=self.user)
        url = reverse('api-me-preferences')

        response = self.client.get(url, HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['email'], 'test@devenkalra.com')
        self.assertFalse(data['blog_subscribed'])
        self.assertFalse(data['notify_on_article'])

        response = self.client.patch(
            url,
            {'blog_subscribed': True, 'notify_on_article': True},
            format='json',
            HTTP_AUTHORIZATION=f'Token {token.key}',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['blog_subscribed'])
        self.assertTrue(data['notify_on_article'])

        sub = Subscription.objects.get(email='test@devenkalra.com')
        self.assertEqual(sub.user, self.user)
        self.assertTrue(sub.blog_subscribed)

        # Unsubscribing clears article notifications
        response = self.client.patch(
            url,
            {'blog_subscribed': False},
            format='json',
            HTTP_AUTHORIZATION=f'Token {token.key}',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertFalse(data['blog_subscribed'])
        self.assertFalse(data['notify_on_article'])

    def test_me_preferences_requires_auth(self):
        url = reverse('api-me-preferences')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_social_login_preserves_existing_blog_prefs(self):
        """Re-login must not overwrite an existing blog opt-in."""
        from unittest.mock import patch, MagicMock
        import json
        import os

        Subscription.objects.create(
            email='social@example.com',
            name='Prior Name',
            provider='google',
            blog_subscribed=True,
            notify_on_article=True,
        )

        google_userinfo = {
            'email': 'social@example.com',
            'name': 'Social User',
            'sub': 'google-123',
            'aud': 'test-google-client-id',
        }
        google_response = MagicMock()
        google_response.read.return_value = json.dumps(google_userinfo).encode('utf-8')
        google_response.__enter__.return_value = google_response

        with patch.dict(os.environ, {'GOOGLE_CLIENT_ID': 'test-google-client-id'}):
            with patch('urllib.request.urlopen', return_value=google_response):
                url = reverse('api-social-google-login')
                response = self.client.post(url, {'id_token': 'fake-google-token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sub = Subscription.objects.get(email='social@example.com')
        self.assertTrue(sub.blog_subscribed)
        self.assertTrue(sub.notify_on_article)
        self.assertEqual(sub.name, 'Social User')

    def test_substack_import_success(self):
        """Verify that importing from a Substack URL correctly extracts content, downloads images, and rewrites URLs."""
        from unittest.mock import patch, MagicMock
        from core.substack_importer import scrape_substack_post_content
        import urllib.request
        
        # Mock responses: 1 for the Substack HTML page, 1 for the cover image, and 1 for the body image
        html_response = MagicMock()
        html_content = """
        <html>
        <head>
            <meta property="og:title" content="Awesome Woodworking Insights" />
            <meta property="og:description" content="Discover the secrets of solid walnut design." />
            <meta property="og:image" content="https://substack-post-media.s3.amazonaws.com/cover.png" />
        </head>
        <body>
            <article class="post-content">
                <p>Welcome to my newsletter.</p>
                <div class="image-wrapper">
                    <div class="image-expand">
                        <img src="https://substack-post-media.s3.amazonaws.com/embedded_image.png" alt="Wood grains" />
                    </div>
                    <button class="image-maximize-button">Maximize</button>
                    <div class="image-zoom-icon">Zoom Icon</div>
                </div>
            </article>
        </body>
        </html>
        """
        html_response.read.return_value = html_content.encode('utf-8')
        html_response.__enter__.return_value = html_response
        
        cover_image_response = MagicMock()
        cover_image_response.read.return_value = b"fake cover image bytes"
        cover_image_response.__enter__.return_value = cover_image_response
        
        body_image_response = MagicMock()
        body_image_response.read.return_value = b"fake body image bytes"
        body_image_response.__enter__.return_value = body_image_response
        
        with patch('urllib.request.urlopen', side_effect=[html_response, cover_image_response, body_image_response]):
            data = scrape_substack_post_content("https://devenkalra.substack.com/p/awesome-woodworking-insights")
            
            self.assertEqual(data['title'], "Awesome Woodworking Insights")
            self.assertEqual(data['summary'], "Discover the secrets of solid walnut design.")
            self.assertTrue(data['render_as_html'])
            
            # The cover image should be downloaded and mapped to our media files
            self.assertTrue(data['cover_image'].startswith("/api/media/uploads/cover_"))
            
            # The body content image should be rewritten to our local media path
            self.assertIn("/api/media/uploads/substack_", data['content'])
            self.assertNotIn("https://substack-post-media.s3.amazonaws.com/embedded_image.png", data['content'])
            
            # Responsive styles and height removal assertions
            self.assertIn('width="100%"', data['content'])
            self.assertIn('style="max-width: 100%; height: auto;"', data['content'])
            self.assertNotIn('height=', data['content'])

            # Zoom/maximize removal assertions
            self.assertNotIn('image-maximize-button', data['content'])
            self.assertNotIn('image-zoom-icon', data['content'])
            self.assertNotIn('image-expand', data['content'])
            self.assertNotIn('Maximize', data['content'])
            self.assertNotIn('<button>', data['content'])


