"""
Views for serving static pages (login, api tester, etc.)
"""
import re
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponseRedirect, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

DEFAULT_APP_URL = '/app/people/'
_GALLERY_NEXT_RE = re.compile(r'^/[^/]+/gallery(?:/|$)')


def safe_login_next(next_url):
    """Allow only same-origin app paths (prevent open redirects)."""
    if not next_url:
        return DEFAULT_APP_URL
    next_url = next_url.strip()
    if '\n' in next_url or '\r' in next_url or '//' in next_url:
        return DEFAULT_APP_URL
    if next_url.startswith('/app/') or _GALLERY_NEXT_RE.match(next_url):
        return next_url
    return DEFAULT_APP_URL


def _rest_auth_cookie(name, default):
    return getattr(settings, 'REST_AUTH', {}).get(name) or default


def jwt_cookies_are_valid(request):
    """True if dj-rest-auth left a usable access or refresh JWT cookie."""
    access_name = _rest_auth_cookie('JWT_AUTH_COOKIE', 'auth-token')
    refresh_name = _rest_auth_cookie('JWT_AUTH_REFRESH_COOKIE', 'refresh-token')
    raw_access = request.COOKIES.get(access_name)
    if raw_access:
        try:
            AccessToken(raw_access)
            return True
        except TokenError:
            pass
    raw_refresh = request.COOKIES.get(refresh_name)
    if raw_refresh:
        try:
            RefreshToken(raw_refresh)
            return True
        except TokenError:
            pass
    return False


def existing_session_redirect(request):
    """If this browser already has a Django session or JWT cookie, go to the app."""
    if request.user.is_authenticated or jwt_cookies_are_valid(request):
        return safe_login_next(request.GET.get('next'))
    return None


@require_GET
@ensure_csrf_cookie
def csrf_cookie(request):
    """Ensure CSRF cookie is set. Call from SPAs (cad-app, people-app) before API requests."""
    return JsonResponse({'ok': True})


@ensure_csrf_cookie
def login_page(request):
    """Serve the login.html page. ensure_csrf_cookie sets the CSRF cookie for the login form."""
    dest = existing_session_redirect(request)
    if dest:
        return HttpResponseRedirect(dest)
    login_file = Path(settings.BASE_DIR) / 'static' / 'login.html'
    response = FileResponse(open(login_file, 'rb'), content_type='text/html')
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    return response


def api_tester_page(request):
    """Serve the API tester page"""
    tester_file = Path(settings.BASE_DIR) / 'static' / 'api-tester.html'
    return FileResponse(open(tester_file, 'rb'), content_type='text/html')


@require_GET
def gmail_app_dev_redirect(request, rest=''):
    """Local Django does not serve the Vite SPA; send browsers to :5177."""
    if not settings.DEBUG:
        return HttpResponseRedirect('/login/')
    host = request.get_host().split(':')[0]
    if host not in ('localhost', '127.0.0.1'):
        return HttpResponseRedirect('/login/')
    full = request.get_full_path()
    prefix = '/app/gmail'
    suffix = full[len(prefix) :] if full.startswith(prefix) else '/'
    if not suffix.startswith('/'):
        suffix = '/' + suffix
    return HttpResponseRedirect(f'http://{host}:5177/app/gmail{suffix}')
