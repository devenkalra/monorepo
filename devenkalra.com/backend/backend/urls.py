"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.views.static import serve
from django.views.generic.base import RedirectView
from pathlib import Path
from django.db.models import Q
import mimetypes


def serve_media_with_db_fallback(request, path=""):
    media_root = Path(settings.MEDIA_ROOT).resolve()
    requested_path = Path(path)

    # Prevent path traversal attempts.
    if requested_path.is_absolute() or ".." in requested_path.parts:
        raise Http404('Not found')

    candidate = (media_root / requested_path).resolve()
    if str(candidate).startswith(str(media_root)) and candidate.is_file():
        return FileResponse(candidate.open('rb'))

    # Fallback: resolve via core_staticfile rows when local file is missing.
    from core.models import StaticFile

    basename = requested_path.name
    static_file = StaticFile.objects.filter(
        Q(file=str(requested_path)) |
        Q(file__endswith='/' + basename) |
        Q(filename=basename)
    ).order_by('-uploaded_at').first()

    if static_file:
        if static_file.file and static_file.file.name:
            storage = static_file.file.storage
            if storage.exists(static_file.file.name):
                fh = storage.open(static_file.file.name, 'rb')
                content_type, _ = mimetypes.guess_type(static_file.file.name)
                response = FileResponse(fh, content_type=content_type or 'application/octet-stream')
                return response

        if static_file.file_url:
            return HttpResponseRedirect(static_file.file_url)

    raise Http404('Not found')


def serve_spa_or_asset(request, path=""):
    # Never serve SPA content for Django-owned routes.
    reserved_prefixes = ('api', 'admin', 'static')
    if path in reserved_prefixes or any(path.startswith(f'{prefix}/') for prefix in reserved_prefixes):
        raise Http404('Not found')

    dist_root = Path(settings.BASE_DIR) / 'frontend_dist'

    # Serve built frontend assets directly when the file exists.
    if path:
        candidate = (dist_root / path).resolve()
        if str(candidate).startswith(str(dist_root.resolve())) and candidate.is_file():
            return FileResponse(candidate.open('rb'))

    index_file = dist_root / 'index.html'
    if not index_file.exists():
        raise Http404('Frontend build output not found')
    return FileResponse(index_file.open('rb'))
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path('admin', RedirectView.as_view(url='/admin/', permanent=False)),
    path('admin/', admin.site.urls),
    re_path(r'^api/media/(?P<path>.*)$', serve_media_with_db_fallback),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/', include('core.urls')),
    path('api/vacation/', include('vacation_list.urls')),
    path('api/assets/', include('asset_manager.urls')),
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    re_path(r'^(?P<path>.*)$', serve_spa_or_asset),
]

