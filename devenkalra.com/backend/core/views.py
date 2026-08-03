from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from django.utils import timezone as django_timezone

from rest_framework import status, viewsets, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.authentication import TokenAuthentication
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes


from .models import Page, MenuItem, Project, WorkflowIdea, BookReview, MusicTrack, Recipe, PageData, BlogCategory, BlogTag, BlogPost, Comment, Subscription, NoteNode
from .serializers import (
    PageSerializer, MenuItemSerializer, MenuItemCRUDSerializer, ProjectSerializer,
    WorkflowIdeaSerializer, BookReviewSerializer, MusicTrackSerializer, RecipeSerializer,
    BlogCategorySerializer, BlogTagSerializer, BlogPostSerializer, CommentSerializer,
    NoteNodeSerializer, NoteNodeTreeSerializer,
)

import os

def get_social_superusers():
    env_val = os.environ.get('SOCIAL_SUPERUSERS', 'deven@kalra.com')
    return [email.strip().lower() for email in env_val.split(',') if email.strip()]

def get_user_role(request):
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.is_staff:
            return "superuser"
        if request.user.email and request.user.email.lower() in get_social_superusers():
            return "superuser"
        return "user"
    
    social_user = request.session.get('social_user')
    if social_user:
        email = social_user.get('email')
        if email and email.lower() in get_social_superusers():
            return "superuser"
        return "user"
    return None

@extend_schema_view(
    list=extend_schema(
        tags=['pages'],
        summary='List pages',
        description='Return all pages. Public; content of role-gated pages is still listed but retrieve may 403.',
    ),
    retrieve=extend_schema(
        tags=['pages'],
        summary='Get page by slug',
        description='Fetch a single page by slug. Enforces `roles_with_access` / `allowed_emails`.',
        parameters=[
            OpenApiParameter(
                name='slug',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description='Page slug (URL key)',
            ),
        ],
    ),
    create=extend_schema(
        tags=['pages'],
        summary='Create page',
        description='Create a page. Requires `Authorization: Token <key>`.',
    ),
    update=extend_schema(tags=['pages'], summary='Replace page'),
    partial_update=extend_schema(tags=['pages'], summary='Patch page'),
    destroy=extend_schema(tags=['pages'], summary='Delete page'),
)
class PageViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for pages.

    - list/retrieve: public (retrieve still enforces roles_with_access)
    - create/update/destroy: authenticated
    Lookup is by ``slug`` so clients can use ``/api/pages/<slug>/``.
    """
    queryset = Page.objects.all().order_by('title')
    serializer_class = PageSerializer
    lookup_field = 'slug'
    lookup_value_regex = r'[-a-zA-Z0-9_]+'

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def retrieve(self, request, *args, **kwargs):
        page = self.get_object()
        denied = page_access_denied_response(request, page)
        if denied is not None:
            return denied
        serializer = self.get_serializer(page)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(tags=['menu'], summary='List menu items'),
    retrieve=extend_schema(tags=['menu'], summary='Get menu item'),
    create=extend_schema(tags=['menu'], summary='Create menu item'),
    update=extend_schema(tags=['menu'], summary='Replace menu item'),
    partial_update=extend_schema(tags=['menu'], summary='Patch menu item'),
    destroy=extend_schema(tags=['menu'], summary='Delete menu item'),
)
class MenuItemViewSet(viewsets.ModelViewSet):
    """CRUD for flat menu items (nested public tree remains at GET /menu/)."""
    queryset = MenuItem.objects.all().order_by('order', 'title')
    serializer_class = MenuItemCRUDSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]


@extend_schema_view(
    list=extend_schema(tags=['notes'], summary='List note nodes'),
    retrieve=extend_schema(tags=['notes'], summary='Get note node'),
    create=extend_schema(tags=['notes'], summary='Create folder or page link'),
    update=extend_schema(tags=['notes'], summary='Replace note node'),
    partial_update=extend_schema(tags=['notes'], summary='Patch note node'),
    destroy=extend_schema(tags=['notes'], summary='Delete note node'),
)
class NoteNodeViewSet(viewsets.ModelViewSet):
    """CRUD + nested tree for Notebook → Notes folders and selected pages."""
    queryset = NoteNode.objects.select_related('page', 'parent').all().order_by('order', 'title')
    serializer_class = NoteNodeSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'tree'):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    @extend_schema(tags=['notes'], summary='Get nested Notes folder tree')
    @action(detail=False, methods=['get'], url_path='tree')
    def tree(self, request):
        roots = NoteNode.objects.filter(parent=None).select_related('page').order_by('order', 'title')
        return Response(NoteNodeTreeSerializer(roots, many=True).data)


@extend_schema(tags=['menu'], summary='Get nested navigation menu')
class MenuView(APIView):
    """
    Returns the full hierarchical navigation menu.
    """
    permission_classes = [permissions.AllowAny]

    def _has_menu_access(self, item, user_role):
        allowed_roles = [r.strip().lower() for r in (item.roles_with_access or '').split(',') if r.strip()]
        if not allowed_roles:
            return True
        if not user_role:
            return False
        if user_role == 'superuser':
            return True
        return user_role in allowed_roles

    def get(self, request):
        # Fetch root menu items (items without a parent)
        user_role = get_user_role(request)
        roots = MenuItem.objects.filter(parent=None).order_by('order', 'title')
        roots = [item for item in roots if self._has_menu_access(item, user_role)]
        serializer = MenuItemSerializer(roots, many=True, context={'user_role': user_role})
        return Response(serializer.data)

def page_access_denied_response(request, page):
    """Return a 403 Response if the request may not view ``page``, else None."""
    if not page.roles_with_access:
        return None

    allowed_roles = [r.strip().lower() for r in page.roles_with_access.split(',') if r.strip()]
    if not allowed_roles:
        return None

    user_role = get_user_role(request)
    if not user_role:
        return Response(
            {"detail": "Authentication required.", "roles_with_access": allowed_roles},
            status=status.HTTP_403_FORBIDDEN
        )

    has_access = False
    if user_role == "superuser":
        has_access = True
    elif user_role == "user" and "user" in allowed_roles:
        has_access = True

    if not has_access:
        return Response(
            {
                "detail": "Access denied. You do not have the required role to view this page.",
                "roles_with_access": allowed_roles,
                "no_permission": True,
            },
            status=status.HTTP_403_FORBIDDEN
        )

    if page.allowed_emails:
        social_user = request.session.get('social_user')
        if request.user.is_authenticated:
            user_email = request.user.email
        elif social_user:
            user_email = social_user.get('email')
        else:
            user_email = ""

        allowed = [e.strip().lower() for e in page.allowed_emails.split(',') if e.strip()]
        if not user_email or user_email.lower() not in allowed:
            return Response(
                {
                    "detail": "Access denied. You do not have permission to view this page.",
                    "roles_with_access": allowed_roles,
                    "no_permission": True,
                },
                status=status.HTTP_403_FORBIDDEN
            )

    return None


@extend_schema(tags=['auth'], summary='Login (session + token)')
class LoginView(APIView):
    """
    Handles user login. Supports both session cookie and token-based response.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response(
                {"detail": "Please provide both username and password."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(request, username=username, password=password)
        if user is not None:
            # Log in session for cookie-based authentication
            login(request, user)

            # Generate or get token for API-based headers
            token, created = Token.objects.get_or_create(user=user)

            return Response({
                "detail": "Successfully logged in.",
                "token": token.key,
                "user": {
                    "username": user.username,
                    "email": user.email
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {"detail": "Invalid credentials."}, 
                status=status.HTTP_401_UNAUTHORIZED
            )

class LogoutView(APIView):
    """
    Handles user logout. Clears session and deletes DRF token.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # Clear social user session
        if 'social_user' in request.session:
            del request.session['social_user']
            request.session.modified = True

        if request.user.is_authenticated:
            # Delete token if exists
            try:
                request.user.auth_token.delete()
            except Exception:
                pass
            logout(request)
        
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)

def _user_display_name(user, social_user=None):
    """Prefer human-readable name over internal ids like google_<sub>."""
    if social_user:
        name = (social_user.get('name') or '').strip()
        if name:
            return name
        email = (social_user.get('email') or '').strip()
        if email:
            return email

    full = (user.get_full_name() or '').strip() if user else ''
    if full:
        return full
    if user and user.email:
        return user.email
    return user.username if user else ''


class AuthStatusView(APIView):
    """
    Checks current authentication status. Supports both Django Users and Social Session.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        social_user = request.session.get('social_user')

        if request.user.is_authenticated:
            is_social = bool(
                social_user
                or request.user.username.startswith('google_')
                or request.user.username.startswith('github_')
            )
            return Response({
                "isAuthenticated": True,
                "user": {
                    "username": _user_display_name(request.user, social_user),
                    "email": request.user.email or (social_user or {}).get('email') or '',
                    "isStaff": request.user.is_staff,
                    "type": "social" if is_social else "django",
                    "provider": (social_user or {}).get('provider') if is_social else None,
                    "role": get_user_role(request),
                },
            })

        if social_user:
            return Response({
                "isAuthenticated": True,
                "user": {
                    "username": social_user.get('name') or social_user.get('email'),
                    "email": social_user.get('email'),
                    "isStaff": False,
                    "type": "social",
                    "provider": social_user.get('provider'),
                    "role": get_user_role(request),
                },
            })

        return Response({
            "isAuthenticated": False
        })

class CSRFTokenView(APIView):
    """
    View to retrieve a CSRF token for forms in frontend.
    """
    permission_classes = [permissions.AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"csrfToken": get_token(request)})

# --- Custom App ViewSets ---

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    
    def get_permissions(self):
        # Enforce authentication for project management/viewing
        # Since Ongoing Projects are under Workflow (which is protected)
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=['post'], url_path='bulk_update')
    def bulk_update(self, request):
        project_ids = request.data.get('ids', [])
        status_value = request.data.get('status')
        category_value = request.data.get('category')

        if not project_ids:
            return Response({"detail": "No project IDs provided."}, status=status.HTTP_400_BAD_REQUEST)

        projects = Project.objects.filter(id__in=project_ids)

        update_fields = {}
        if status_value:
            update_fields['status'] = status_value
        if category_value is not None:  # Allow setting category to empty string
            update_fields['category'] = category_value

        if update_fields:
            projects.update(**update_fields)

        return Response({"detail": f"Successfully updated {projects.count()} projects."}, status=status.HTTP_200_OK)

class WorkflowIdeaViewSet(viewsets.ModelViewSet):
    queryset = WorkflowIdea.objects.all()
    serializer_class = WorkflowIdeaSerializer

    def get_permissions(self):
        # Workflow ideas are strictly protected
        return [permissions.IsAuthenticated()]

class BookReviewViewSet(viewsets.ModelViewSet):
    queryset = BookReview.objects.all().order_by('-read_date')
    serializer_class = BookReviewSerializer
    permission_classes = [permissions.AllowAny]  # Publicly viewable

class MusicTrackViewSet(viewsets.ModelViewSet):
    queryset = MusicTrack.objects.all()
    serializer_class = MusicTrackSerializer
    permission_classes = [permissions.AllowAny]  # Publicly viewable

class RecipeViewSet(viewsets.ModelViewSet):
    queryset = Recipe.objects.all()
    serializer_class = RecipeSerializer
    permission_classes = [permissions.AllowAny]  # Publicly viewable


class PageDataDetailView(APIView):
    """
    Retrieves or updates generic JSON data stored for a specific page app.
    GET/POST: Open to anyone (public access for custom apps).
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.AllowAny]

    def get(self, request, page_slug):
        try:
            pd = PageData.objects.get(page_slug=page_slug)
            return Response(pd.data, status=status.HTTP_200_OK)
        except PageData.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)

    def post(self, request, page_slug):
        pd, created = PageData.objects.update_or_create(
            page_slug=page_slug,
            defaults={'data': request.data}
        )
        return Response({"status": "saved"}, status=status.HTTP_200_OK)


import urllib.request
import urllib.parse
import json
from datetime import datetime, timezone as datetime_timezone
from django.conf import settings


def _parse_clickup_date_value(value):
    if value in (None, ''):
        return None

    if isinstance(value, dict):
        for key in ('value', 'date', 'start'):
            nested_value = value.get(key)
            if nested_value not in (None, ''):
                value = nested_value
                break
        else:
            return None

    if isinstance(value, str):
        stripped_value = value.strip()
        if not stripped_value:
            return None

        if stripped_value.isdigit():
            value = int(stripped_value)
        else:
            normalized_value = stripped_value.replace('Z', '+00:00')
            try:
                parsed_datetime = datetime.fromisoformat(normalized_value)
            except ValueError:
                return None
            return parsed_datetime.date()

    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10**12:
            timestamp /= 1000.0
        return datetime.fromtimestamp(timestamp, tz=datetime_timezone.utc).date()

    if isinstance(value, datetime):
        return value.date()

    return None


def _get_clickup_show_after_date(task):
    for custom_field in task.get('custom_fields', []):
        if custom_field.get('name', '').strip().lower() == 'show after':
            return _parse_clickup_date_value(custom_field.get('value'))
    return None


def _is_clickup_task_visible(task):
    show_after_date = _get_clickup_show_after_date(task)
    if show_after_date and show_after_date > django_timezone.localdate():
        return False
    return True

class ClickUpTasksView(APIView):
    """
    Exposes ClickUp tasks and subtasks from the 'Creative Space' dynamically.
    Requires authentication.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        token = getattr(settings, 'CLICKUP_API_TOKEN', '')
        if not token:
            return Response(
                {"detail": "ClickUp API token is not configured on the server. Please check the .env file."},
                status=status.HTTP_400_BAD_REQUEST
            )

        headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }

        # Step 1: Get workspaces
        try:
            req = urllib.request.Request("https://api.clickup.com/api/v2/team", headers=headers)
            with urllib.request.urlopen(req) as resp:
                teams_data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            return Response(
                {"detail": f"Failed to fetch workspaces from ClickUp: {e}"},
                status=status.HTTP_502_BAD_GATEWAY
            )

        teams = teams_data.get('teams', [])
        if not teams:
            return Response(
                {"detail": "No workspaces found associated with this ClickUp account."},
                status=status.HTTP_404_NOT_FOUND
            )

        team_id = teams[0]['id']

        # Step 2: Get spaces to find 'Creative Space'
        try:
            req = urllib.request.Request(f"https://api.clickup.com/api/v2/team/{team_id}/space", headers=headers)
            with urllib.request.urlopen(req) as resp:
                spaces_data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            return Response(
                {"detail": f"Failed to fetch spaces from ClickUp workspace {team_id}: {e}"},
                status=status.HTTP_502_BAD_GATEWAY
            )

        spaces = spaces_data.get('spaces', [])
        target_space = None
        for s in spaces:
            name_lower = s.get('name', '').strip().lower()
            if name_lower in ('creative', 'creative space'):
                target_space = s
                break

        if not target_space:
            return Response(
                {"detail": "Could not find a Space named 'Creative' or 'Creative Space' in ClickUp. Please verify the space name."},
                status=status.HTTP_404_NOT_FOUND
            )

        space_id = target_space['id']
        include_hidden_show_after = request.query_params.get('include_hidden_show_after', '').lower() in ('1', 'true', 'yes', 'on')

        # Step 3: Fetch tasks inside the space (paginated)
        all_tasks = []
        page = 0
        while True:
            query_params = urllib.parse.urlencode({
                "space_ids[]": space_id,
                "subtasks": "true",
                "include_markdown_description": "true",
                "include_closed": "true",
                "page": page
            })
            url = f"https://api.clickup.com/api/v2/team/{team_id}/task?{query_params}"

            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as resp:
                    page_data = json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                return Response(
                    {"detail": f"Failed to fetch tasks on page {page} from ClickUp: {e}"},
                    status=status.HTTP_502_BAD_GATEWAY
                )

            page_tasks = page_data.get('tasks', [])
            all_tasks.extend(page_tasks)

            if len(page_tasks) < 100:
                break
            page += 1

        visible_tasks = all_tasks if include_hidden_show_after else [task for task in all_tasks if _is_clickup_task_visible(task)]

        return Response({
            "space": {
                "id": space_id,
                "name": target_space['name']
            },
            "team_id": team_id,
            "tasks": visible_tasks
        }, status=status.HTTP_200_OK)

    def post(self, request):
        task_id = request.data.get('taskId')
        new_status = request.data.get('status')
        custom_field_id = request.data.get('customFieldId')
        custom_field_value = request.data.get('customFieldValue')

        if not task_id:
            return Response(
                {"detail": "Please provide 'taskId'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        token = getattr(settings, 'CLICKUP_API_TOKEN', '')
        if not token:
            return Response(
                {"detail": "ClickUp API token is not configured on the server. Please check the .env file."},
                status=status.HTTP_400_BAD_REQUEST
            )

        headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }

        if new_status:
            url = f"https://api.clickup.com/api/v2/task/{task_id}"
            data = json.dumps({"status": new_status}).encode('utf-8')
            method = 'PUT'
        elif custom_field_id:
            url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{custom_field_id}"
            try:
                # ClickUp custom fields (numbers) require numeric type values, not strings.
                # Try parsing as float or int, falling back to string if not possible.
                val = float(custom_field_value)
                if val.is_integer():
                    val = int(val)
            except (ValueError, TypeError):
                val = custom_field_value
            data = json.dumps({"value": val}).encode('utf-8')
            method = 'POST'
        else:
            return Response(
                {"detail": "Please provide either 'status' or 'customFieldId' with 'customFieldValue'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req) as resp:
                resp_bytes = resp.read()
                resp_data = json.loads(resp_bytes.decode('utf-8')) if resp_bytes else {}
            return Response({"status": "success", "task": resp_data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"detail": f"Failed to update task in ClickUp: {e}"},
                status=status.HTTP_502_BAD_GATEWAY
            )


class ClickUpContactsView(APIView):
    """
    Exposes ClickUp tasks from Space 'Consulting' and List 'Contacts'.
    Requires authentication.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        token = getattr(settings, 'CLICKUP_API_TOKEN', '')
        if not token:
            return Response(
                {"detail": "ClickUp API token is not configured on the server. Please check the .env file."},
                status=status.HTTP_400_BAD_REQUEST
            )

        headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }

        # Step 1: Get workspaces
        try:
            req = urllib.request.Request("https://api.clickup.com/api/v2/team", headers=headers)
            with urllib.request.urlopen(req) as resp:
                teams_data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            return Response(
                {"detail": f"Failed to fetch workspaces from ClickUp: {e}"},
                status=status.HTTP_502_BAD_GATEWAY
            )

        teams = teams_data.get('teams', [])
        if not teams:
            return Response(
                {"detail": "No workspaces found associated with this ClickUp account."},
                status=status.HTTP_404_NOT_FOUND
            )

        team_id = teams[0]['id']

        # Step 2: Get spaces to find 'Consulting'
        try:
            req = urllib.request.Request(f"https://api.clickup.com/api/v2/team/{team_id}/space", headers=headers)
            with urllib.request.urlopen(req) as resp:
                spaces_data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            return Response(
                {"detail": f"Failed to fetch spaces from ClickUp workspace {team_id}: {e}"},
                status=status.HTTP_502_BAD_GATEWAY
            )

        spaces = spaces_data.get('spaces', [])
        target_space = None
        for s in spaces:
            name_lower = s.get('name', '').strip().lower()
            if name_lower in ('consulting', 'consulting space'):
                target_space = s
                break

        if not target_space:
            return Response(
                {"detail": "Could not find a Space named 'Consulting' in ClickUp. Please verify the space name."},
                status=status.HTTP_404_NOT_FOUND
            )

        space_id = target_space['id']
        include_hidden_show_after = request.query_params.get('include_hidden_show_after', '').lower() in ('1', 'true', 'yes', 'on')

        # Step 3: Fetch tasks inside the consulting space (paginated)
        all_tasks = []
        page = 0
        while True:
            query_params = urllib.parse.urlencode({
                "space_ids[]": space_id,
                "subtasks": "true",
                "include_markdown_description": "true",
                "include_closed": "true",
                "page": page
            })
            url = f"https://api.clickup.com/api/v2/team/{team_id}/task?{query_params}"

            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as resp:
                    page_data = json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                return Response(
                    {"detail": f"Failed to fetch tasks on page {page} from ClickUp: {e}"},
                    status=status.HTTP_502_BAD_GATEWAY
                )

            page_tasks = page_data.get('tasks', [])
            all_tasks.extend(page_tasks)

            if len(page_tasks) < 100:
                break
            page += 1

        visible_tasks = all_tasks if include_hidden_show_after else [task for task in all_tasks if _is_clickup_task_visible(task)]
        contacts_tasks = [
            task for task in visible_tasks
            if (task.get('list') or {}).get('name', '').strip().lower() == 'contacts'
        ]

        list_statuses = []
        contacts_list_id = None
        for task in all_tasks:
            list_obj = task.get('list') or {}
            if list_obj.get('name', '').strip().lower() == 'contacts' and list_obj.get('id'):
                contacts_list_id = list_obj.get('id')
                break

        if contacts_list_id:
            try:
                req = urllib.request.Request(f"https://api.clickup.com/api/v2/list/{contacts_list_id}", headers=headers)
                with urllib.request.urlopen(req) as resp:
                    list_data = json.loads(resp.read().decode('utf-8'))
                list_statuses = list_data.get('statuses', []) or []
            except Exception:
                list_statuses = []

        return Response({
            "space": {
                "id": space_id,
                "name": target_space['name']
            },
            "list": {
                "name": "Contacts",
                "id": contacts_list_id
            },
            "team_id": team_id,
            "statuses": list_statuses,
            "tasks": contacts_tasks
        }, status=status.HTTP_200_OK)

    def post(self, request):
        task_id = request.data.get('taskId')
        new_status = request.data.get('status')
        custom_field_id = request.data.get('customFieldId')
        custom_field_value = request.data.get('customFieldValue')

        if not task_id:
            return Response(
                {"detail": "Please provide 'taskId'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        token = getattr(settings, 'CLICKUP_API_TOKEN', '')
        if not token:
            return Response(
                {"detail": "ClickUp API token is not configured on the server. Please check the .env file."},
                status=status.HTTP_400_BAD_REQUEST
            )

        headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }

        if new_status:
            url = f"https://api.clickup.com/api/v2/task/{task_id}"
            data = json.dumps({"status": new_status}).encode('utf-8')
            method = 'PUT'
        elif custom_field_id:
            url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{custom_field_id}"
            try:
                val = float(custom_field_value)
                if val.is_integer():
                    val = int(val)
            except (ValueError, TypeError):
                val = custom_field_value
            data = json.dumps({"value": val}).encode('utf-8')
            method = 'POST'
        else:
            return Response(
                {"detail": "Please provide either 'status' or 'customFieldId' with 'customFieldValue'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req) as resp:
                resp_bytes = resp.read()
                resp_data = json.loads(resp_bytes.decode('utf-8')) if resp_bytes else {}
            return Response({"status": "success", "task": resp_data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"detail": f"Failed to update task in ClickUp: {e}"},
                status=status.HTTP_502_BAD_GATEWAY
            )


class ClickUpContactActivitiesView(APIView):
    """
    Exposes activity timeline for a contact task.
    Uses ClickUp task comments as activity events.
    Requires authentication.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, task_id):
        token = getattr(settings, 'CLICKUP_API_TOKEN', '')
        if not token:
            return Response(
                {"detail": "ClickUp API token is not configured on the server. Please check the .env file."},
                status=status.HTTP_400_BAD_REQUEST
            )

        headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }

        url = f"https://api.clickup.com/api/v2/task/{task_id}/comment"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as resp:
                payload = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            return Response(
                {"detail": f"Failed to fetch contact activities from ClickUp: {e}"},
                status=status.HTTP_502_BAD_GATEWAY
            )

        comments = payload.get('comments', []) or []
        activities = []

        for comment in comments:
            user_obj = comment.get('user') or {}
            user_name = user_obj.get('username') or user_obj.get('email') or user_obj.get('id') or 'Unknown'

            comment_text = comment.get('comment_text')
            if not comment_text:
                text_items = comment.get('comment') or []
                parts = []
                for item in text_items:
                    if isinstance(item, dict) and item.get('text'):
                        parts.append(str(item.get('text')))
                comment_text = ''.join(parts)

            activities.append({
                "id": comment.get('id'),
                "type": "comment",
                "user": user_name,
                "timestamp": comment.get('date') or comment.get('date_created'),
                "text": comment_text or '',
                "raw": comment,
            })

        activities.sort(key=lambda a: int(a.get('timestamp') or 0), reverse=True)

        return Response({
            "task_id": task_id,
            "activities": activities
        }, status=status.HTTP_200_OK)


from django.db.models import Q
from django.utils import timezone

class BlogCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BlogCategory.objects.all().order_by('name')
    serializer_class = BlogCategorySerializer
    permission_classes = [permissions.AllowAny]

class BlogTagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BlogTag.objects.all().order_by('name')
    serializer_class = BlogTagSerializer
    permission_classes = [permissions.AllowAny]

class BlogPostViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BlogPostSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        import uuid
        user = self.request.user
        now = timezone.now()
        
        token = self.request.query_params.get('token', None)
        is_valid_uuid = False
        if token:
            try:
                uuid.UUID(str(token))
                is_valid_uuid = True
            except ValueError:
                pass

        # If user is superuser (staff, django admin, or social superuser), show drafts too
        if get_user_role(self.request) == 'superuser':
            queryset = BlogPost.objects.all()
        elif is_valid_uuid:
            queryset = BlogPost.objects.filter(
                Q(preview_token=token) | (Q(is_published=True) & (Q(publish_date__isnull=True) | Q(publish_date__lte=now)))
            )
        else:
            queryset = BlogPost.objects.filter(
                Q(is_published=True) & (Q(publish_date__isnull=True) | Q(publish_date__lte=now))
            )

        # Filters
        category_slug = self.request.query_params.get('category', None)
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)

        tag_slug = self.request.query_params.get('tag', None)
        if tag_slug:
            queryset = queryset.filter(tags__slug=tag_slug)

        search_query = self.request.query_params.get('q', None)
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) |
                Q(content__icontains=search_query) |
                Q(summary__icontains=search_query)
            )

        return queryset.distinct()


class BlogCommentView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, post_slug):
        try:
            post = BlogPost.objects.get(slug=post_slug)
        except BlogPost.DoesNotExist:
            return Response({"detail": "Blog post not found."}, status=status.HTTP_404_NOT_FOUND)
        
        comments = post.comments.filter(is_approved=True)
        serializer = CommentSerializer(comments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, post_slug):
        try:
            post = BlogPost.objects.get(slug=post_slug)
        except BlogPost.DoesNotExist:
            return Response({"detail": "Blog post not found."}, status=status.HTTP_404_NOT_FOUND)

        # Enforce Authentication Check
        social_user = request.session.get('social_user')
        if request.user.is_authenticated:
            author_name = request.user.username
            author_email = request.user.email
        elif social_user:
            author_name = social_user.get('name')
            author_email = social_user.get('email')
        else:
            return Response({"detail": "You must be logged in via a social account or admin to comment."}, status=status.HTTP_401_UNAUTHORIZED)

        # Anti-spam Honeypot Check
        honeypot = request.data.get('website_url', '')
        if honeypot:
            return Response({"status": "awaiting_moderation"}, status=status.HTTP_201_CREATED)

        content = request.data.get('content', '').strip()
        if not content:
            return Response({"detail": "Please type a comment first."}, status=status.HTTP_400_BAD_REQUEST)

        comment = Comment.objects.create(
            post=post,
            author_name=author_name,
            author_email=author_email,
            content=content,
            is_approved=False
        )

        return Response({"status": "awaiting_moderation"}, status=status.HTTP_201_CREATED)


import os
import urllib.request
import urllib.parse
import json
from django.conf import settings

class SocialAuthConfigView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({
            "googleClientId": os.environ.get('GOOGLE_CLIENT_ID', ''),
            "githubClientId": os.environ.get('GITHUB_CLIENT_ID', '')
        })


def _verify_google_id_token(id_token):
    """Validate an ID token via Google's tokeninfo endpoint and check audience."""
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(id_token)}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        token_info = json.loads(response.read().decode('utf-8'))

    client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
    aud = token_info.get('aud')
    if client_id and aud and aud != client_id:
        raise ValueError('Google token audience does not match this application.')
    return token_info


def _exchange_google_auth_code(code, redirect_uri):
    """Exchange an OAuth authorization code for tokens (includes id_token)."""
    client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        raise ValueError('Google OAuth is not fully configured on this server (missing client secret).')
    if not redirect_uri:
        raise ValueError('redirect_uri is required for Google code exchange.')

    body = urllib.parse.urlencode({
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=body,
        method='POST',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    with urllib.request.urlopen(req) as response:
        tokens = json.loads(response.read().decode('utf-8'))

    id_token = tokens.get('id_token')
    if not id_token:
        raise ValueError('Google token response did not include an id_token.')
    return id_token


def _upsert_subscription_contact(*, email, name='', provider='', user=None):
    """Create/update a contact row without changing opt-in preference flags.

    Social login links identity (email/name/provider/user) but does not
    imply blog subscription — that requires an explicit Subscribe action.
    """
    email = (email or '').strip()
    if not email:
        return None

    defaults = {'is_active': True}
    if name:
        defaults['name'] = name
    if provider:
        defaults['provider'] = provider
    if user is not None:
        defaults['user'] = user

    sub, _created = Subscription.objects.update_or_create(
        email=email,
        defaults=defaults,
    )
    return sub


def _resolve_preferences_identity(request):
    """Return (email, user, name, provider) for the current request, or Nones."""
    social = request.session.get('social_user') or {}
    user = request.user if getattr(request.user, 'is_authenticated', False) else None

    if user:
        email = (user.email or social.get('email') or '').strip()
        name = _user_display_name(user, social if social else None)
        provider = social.get('provider') or ''
        return email, user, name, provider

    if social:
        email = (social.get('email') or '').strip()
        name = (social.get('name') or '').strip()
        provider = social.get('provider') or ''
        return email, None, name, provider

    return '', None, '', ''


def _preferences_payload(sub):
    return {
        'email': sub.email,
        'name': sub.name,
        'provider': sub.provider,
        'is_active': sub.is_active,
        'blog_subscribed': sub.blog_subscribed,
        'notify_on_article': sub.notify_on_article,
        'subscribed_at': sub.subscribed_at,
        'updated_at': sub.updated_at,
    }


class MePreferencesView(APIView):
    """GET/PATCH contact preferences for the authenticated user (by email)."""
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        email, user, name, provider = _resolve_preferences_identity(request)
        if not email:
            return Response(
                {"detail": "No email on this account; preferences are unavailable."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sub = _upsert_subscription_contact(
            email=email, name=name, provider=provider, user=user,
        )
        return Response(_preferences_payload(sub))

    def patch(self, request):
        email, user, name, provider = _resolve_preferences_identity(request)
        if not email:
            return Response(
                {"detail": "No email on this account; preferences are unavailable."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sub = _upsert_subscription_contact(
            email=email, name=name, provider=provider, user=user,
        )

        data = request.data or {}
        updated = []
        if 'blog_subscribed' in data:
            sub.blog_subscribed = bool(data.get('blog_subscribed'))
            updated.append('blog_subscribed')
        if 'notify_on_article' in data:
            sub.notify_on_article = bool(data.get('notify_on_article'))
            updated.append('notify_on_article')
        if 'is_active' in data:
            sub.is_active = bool(data.get('is_active'))
            updated.append('is_active')

        if updated:
            # Unsubscribing from the blog also turns off article mail.
            if 'blog_subscribed' in updated and not sub.blog_subscribed:
                sub.notify_on_article = False
                if 'notify_on_article' not in updated:
                    updated.append('notify_on_article')
            sub.save(update_fields=list(dict.fromkeys(updated + ['updated_at'])))

        return Response(_preferences_payload(sub))


def _complete_google_social_login(request, token_info):
    email = token_info.get('email')
    name = token_info.get('name', '')
    uid = token_info.get('sub')

    if not email:
        return Response(
            {"detail": "Email address not found in Google account."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    request.session['social_user'] = {
        'email': email,
        'name': name,
        'uid': uid,
        'provider': 'google',
    }
    request.session.modified = True

    first = name.split(' ')[0] if name else ''
    last = ' '.join(name.split(' ')[1:]) if name and len(name.split(' ')) > 1 else ''
    user, _created = User.objects.get_or_create(
        username=f'google_{uid}',
        defaults={
            'email': email,
            'first_name': first,
            'last_name': last,
        },
    )
    updates = []
    if user.email != email:
        user.email = email
        updates.append('email')
    if name and (user.first_name != first or user.last_name != last):
        user.first_name = first
        user.last_name = last
        updates.extend(['first_name', 'last_name'])
    if updates:
        user.save(update_fields=list(dict.fromkeys(updates)))

    _upsert_subscription_contact(
        email=email, name=name, provider='google', user=user,
    )

    auth_token, _ = Token.objects.get_or_create(user=user)
    display = name or email

    return Response({
        "detail": "Successfully authenticated with Google.",
        "token": auth_token.key,
        "user": {
            "username": display,
            "email": email,
            "isStaff": False,
            "type": "social",
            "provider": "google",
            "role": get_user_role(request),
        },
    }, status=status.HTTP_200_OK)


class SocialGoogleLoginView(APIView):
    """
    Google social login.

    Preferred: OAuth authorization-code redirect
      POST { "code": "...", "redirect_uri": "https://…/login/google/callback" }

    Legacy: GIS ID token
      POST { "id_token": "..." }
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        code = request.data.get('code')
        id_token = request.data.get('id_token')
        redirect_uri = request.data.get('redirect_uri')

        try:
            if code:
                id_token = _exchange_google_auth_code(code, redirect_uri)
            elif not id_token:
                return Response(
                    {"detail": "Google authorization code or ID token is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            token_info = _verify_google_id_token(id_token)
        except Exception as e:
            return Response(
                {"detail": f"Failed to verify Google login: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return _complete_google_social_login(request, token_info)

class SocialGithubLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        code = request.data.get('code')
        if not code:
            return Response({"detail": "GitHub authorization code is required."}, status=status.HTTP_400_BAD_REQUEST)

        client_id = os.environ.get('GITHUB_CLIENT_ID', '')
        client_secret = os.environ.get('GITHUB_CLIENT_SECRET', '')

        if not client_id or not client_secret:
            return Response({"detail": "GitHub OAuth parameters are not configured on this server."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 1. Exchange auth code for access token
        try:
            token_url = "https://github.com/login/oauth/access_token"
            data = urllib.parse.urlencode({
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code
            }).encode('utf-8')
            
            req = urllib.request.Request(
                token_url,
                data=data,
                headers={'Accept': 'application/json'}
            )
            with urllib.request.urlopen(req) as response:
                token_res = json.loads(response.read().decode('utf-8'))
        except Exception as e:
            return Response({"detail": f"Failed to exchange GitHub credentials: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        access_token = token_res.get('access_token')
        if not access_token:
            return Response({"detail": f"GitHub token exchange failed: {token_res.get('error_description', 'No access token returned.')}"}, status=status.HTTP_400_BAD_REQUEST)

        headers = {
            'Authorization': f'token {access_token}',
            'User-Agent': 'devenkalra-backend'
        }

        # 2. Fetch user profile
        try:
            user_req = urllib.request.Request("https://api.github.com/user", headers=headers)
            with urllib.request.urlopen(user_req) as response:
                user_info = json.loads(response.read().decode('utf-8'))
        except Exception as e:
            return Response({"detail": f"Failed to retrieve GitHub user profile: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        name = user_info.get('name') or user_info.get('login') or ""
        uid = str(user_info.get('id'))
        email = user_info.get('email')

        # 3. Fetch private emails if email not public on profile
        if not email:
            try:
                emails_req = urllib.request.Request("https://api.github.com/user/emails", headers=headers)
                with urllib.request.urlopen(emails_req) as response:
                    emails_list = json.loads(response.read().decode('utf-8'))
                
                for email_record in emails_list:
                    if email_record.get('primary') and email_record.get('verified'):
                        email = email_record.get('email')
                        break
                if not email:
                    for email_record in emails_list:
                        if email_record.get('verified'):
                            email = email_record.get('email')
                            break
            except Exception as e:
                print("Failed to fetch private GitHub emails:", e)

        if not email:
            return Response({"detail": "Email address not found or verified on your GitHub account."}, status=status.HTTP_400_BAD_REQUEST)

        # Store in session
        request.session['social_user'] = {
            'email': email,
            'name': name,
            'uid': uid,
            'provider': 'github'
        }
        request.session.modified = True

        first = name.split(' ')[0] if name else ''
        last = ' '.join(name.split(' ')[1:]) if name and len(name.split(' ')) > 1 else ''
        user, created = User.objects.get_or_create(
            username=f'github_{uid}',
            defaults={
                'email': email,
                'first_name': first,
                'last_name': last,
            }
        )
        updates = []
        if user.email != email:
            user.email = email
            updates.append('email')
        if name and (user.first_name != first or user.last_name != last):
            user.first_name = first
            user.last_name = last
            updates.extend(['first_name', 'last_name'])
        if updates:
            user.save(update_fields=list(dict.fromkeys(updates)))

        # Link contact identity; do not auto opt-in to blog mail
        _upsert_subscription_contact(
            email=email, name=name, provider='github', user=user,
        )

        auth_token, _ = Token.objects.get_or_create(user=user)

        return Response({
            "detail": "Successfully authenticated with GitHub.",
            "token": auth_token.key,
            "user": {
                "username": name or email,
                "email": email,
                "isStaff": False,
                "type": "social",
                "provider": "github",
                "role": get_user_role(request)
            }
        }, status=status.HTTP_200_OK)



