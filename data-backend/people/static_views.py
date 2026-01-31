"""
Views for serving static pages (login, api tester, etc.)
"""
from django.http import FileResponse
from django.conf import settings
from pathlib import Path


def login_page(request):
    """Serve the login.html page"""
    login_file = Path(settings.BASE_DIR) / 'static' / 'login.html'
    return FileResponse(open(login_file, 'rb'), content_type='text/html')


def api_tester_page(request):
    """Serve the API tester page"""
    tester_file = Path(settings.BASE_DIR) / 'static' / 'api-tester.html'
    return FileResponse(open(tester_file, 'rb'), content_type='text/html')
