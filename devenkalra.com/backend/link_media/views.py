import mimetypes
import os

from django.conf import settings
from django.db.models import F
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LinkMedia, validate_slug
from .permissions import IsSuperuserRole

MAX_UPLOAD_BYTES = 40 * 1024 * 1024


def public_base_url(request=None):
    base = (getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
    if base:
        return base
    if request is not None:
        return request.build_absolute_uri('/').rstrip('/')
    return ''


def absolute_link(item, request=None):
    return f'{public_base_url(request)}/f/{item.slug}'


def serialize_item(item, request=None):
    return {
        'id': item.id,
        'slug': item.slug,
        'title': item.title,
        'url': absolute_link(item, request),
        'path': f'/f/{item.slug}',
        'content_type': item.content_type,
        'byte_size': item.byte_size,
        'is_public': item.is_public,
        'download_count': item.download_count,
        'filename': os.path.basename(item.file.name) if item.file else '',
        'created_at': item.created_at.isoformat() if item.created_at else None,
        'updated_at': item.updated_at.isoformat() if item.updated_at else None,
    }


def serve_link_media(request, slug):
    """Public short URL: stream the file inline for email / browser use."""
    slug = (slug or '').strip().lower()
    item = get_object_or_404(LinkMedia, slug=slug, is_public=True)
    if not item.file:
        raise Http404('File missing')
    try:
        fh = item.file.open('rb')
    except Exception as e:
        raise Http404(f'File missing: {e}') from e

    LinkMedia.objects.filter(pk=item.pk).update(download_count=F('download_count') + 1)

    content_type = item.content_type or mimetypes.guess_type(item.file.name)[0] \
        or 'application/octet-stream'
    filename = os.path.basename(item.file.name) or item.slug
    response = FileResponse(fh, content_type=content_type)
    # Inline so PDFs/images open in the browser; download still works via Save As.
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    response['Cache-Control'] = 'public, max-age=86400'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


class LinkMediaListCreateView(APIView):
    # Token only — SessionAuthentication would require a CSRF cookie on uploads.
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsSuperuserRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        rows = LinkMedia.objects.all()[:500]
        return Response({
            'items': [serialize_item(r, request) for r in rows],
            'base_url': f'{public_base_url(request)}/f/',
        })

    def post(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'file is required.'}, status=400)
        if upload.size and upload.size > MAX_UPLOAD_BYTES:
            return Response({
                'detail': f'File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)}MB).',
            }, status=400)

        slug = (request.data.get('slug') or '').strip().lower()
        if not slug:
            slug = LinkMedia.suggest_slug(getattr(upload, 'name', '') or 'file')
        try:
            validate_slug(slug)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)
        if LinkMedia.objects.filter(slug=slug).exists():
            return Response({'detail': f'Slug "{slug}" is already in use.'}, status=409)

        title = (request.data.get('title') or '').strip() or (upload.name or slug)
        content_type = (getattr(upload, 'content_type', None) or '').split(';', 1)[0].strip()
        if not content_type:
            content_type = mimetypes.guess_type(upload.name or '')[0] or 'application/octet-stream'
        is_public = str(request.data.get('is_public', '1')).lower() not in ('0', 'false', 'no')

        item = LinkMedia(
            slug=slug,
            title=title,
            content_type=content_type,
            is_public=is_public,
        )
        item.file = upload
        item.full_clean()
        item.save()
        return Response(serialize_item(item, request), status=status.HTTP_201_CREATED)


class LinkMediaDetailView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsSuperuserRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self, pk):
        return get_object_or_404(LinkMedia, pk=pk)

    def get(self, request, pk):
        return Response(serialize_item(self.get_object(pk), request))

    def patch(self, request, pk):
        item = self.get_object(pk)
        if 'title' in request.data:
            item.title = (request.data.get('title') or '').strip()
        if 'is_public' in request.data:
            item.is_public = str(request.data.get('is_public')).lower() not in ('0', 'false', 'no')
        if 'slug' in request.data:
            new_slug = (request.data.get('slug') or '').strip().lower()
            try:
                validate_slug(new_slug)
            except Exception as e:
                return Response({'detail': str(e)}, status=400)
            if LinkMedia.objects.filter(slug=new_slug).exclude(pk=item.pk).exists():
                return Response({'detail': f'Slug "{new_slug}" is already in use.'}, status=409)
            item.slug = new_slug
        upload = request.FILES.get('file')
        if upload:
            if upload.size and upload.size > MAX_UPLOAD_BYTES:
                return Response({
                    'detail': f'File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)}MB).',
                }, status=400)
            # Replace file; keep slug so old email links still work.
            old = item.file.name if item.file else ''
            item.file = upload
            ctype = (getattr(upload, 'content_type', None) or '').split(';', 1)[0].strip()
            item.content_type = ctype or mimetypes.guess_type(upload.name or '')[0] \
                or item.content_type or 'application/octet-stream'
            item.save()
            if old and old != item.file.name:
                try:
                    item.file.storage.delete(old)
                except Exception:
                    pass
        else:
            item.full_clean()
            item.save()
        return Response(serialize_item(item, request))

    def delete(self, request, pk):
        item = self.get_object(pk)
        name = item.file.name if item.file else ''
        item.delete()
        if name:
            try:
                from django.core.files.storage import default_storage
                default_storage.delete(name)
            except Exception:
                pass
        return Response(status=status.HTTP_204_NO_CONTENT)
