"""
Views for serving static pages (login, api tester, etc.)
"""
from django.http import FileResponse, HttpResponseRedirect, JsonResponse
from django.conf import settings
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET
from pathlib import Path


@require_GET
@ensure_csrf_cookie
def csrf_cookie(request):
    """Ensure CSRF cookie is set. Call from SPAs (cad-app, people-app) before API requests."""
    return JsonResponse({'ok': True})


@ensure_csrf_cookie
def login_page(request):
    """Serve the login.html page. ensure_csrf_cookie sets the CSRF cookie for the login form."""
    login_file = Path(settings.BASE_DIR) / 'static' / 'login.html'
    return FileResponse(open(login_file, 'rb'), content_type='text/html')


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
