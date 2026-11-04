from django.conf import settings
from django.db.models import F
from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LinkRedirect, validate_slug, validate_target_url
from .permissions import IsSuperuserRole


def public_base_url(request=None):
    base = (getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
    if base:
        return base
    if request is not None:
        return request.build_absolute_uri('/').rstrip('/')
    return ''


def absolute_link(item, request=None):
    return f'{public_base_url(request)}/{item.slug}'


def serialize_item(item, request=None):
    return {
        'id': item.id,
        'slug': item.slug,
        'title': item.title,
        'target_url': item.target_url,
        'url': absolute_link(item, request),
        'path': f'/{item.slug}',
        'is_public': item.is_public,
        'permanent': item.permanent,
        'hit_count': item.hit_count,
        'created_at': item.created_at.isoformat() if item.created_at else None,
        'updated_at': item.updated_at.isoformat() if item.updated_at else None,
    }


def try_root_redirect(path):
    """If `path` is a single public redirect slug, return an HttpResponseRedirect."""
    slug = (path or '').strip('/').strip().lower()
    if not slug or '/' in slug:
        return None
    item = LinkRedirect.objects.filter(slug=slug, is_public=True).first()
    if not item or not item.target_url:
        return None
    LinkRedirect.objects.filter(pk=item.pk).update(hit_count=F('hit_count') + 1)
    if item.permanent:
        return HttpResponsePermanentRedirect(item.target_url)
    return HttpResponseRedirect(item.target_url)


class LinkRedirectListCreateView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsSuperuserRole]
    parser_classes = [JSONParser]

    def get(self, request):
        rows = LinkRedirect.objects.all()[:500]
        return Response({
            'items': [serialize_item(r, request) for r in rows],
            'base_url': f'{public_base_url(request)}/',
        })

    def post(self, request):
        slug = (request.data.get('slug') or '').strip().lower()
        title = (request.data.get('title') or '').strip()
        target_url = (request.data.get('target_url') or '').strip()
        if not slug:
            slug = LinkRedirect.suggest_slug(title or target_url or 'link')
        try:
            validate_slug(slug)
            validate_target_url(target_url)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)
        if LinkRedirect.objects.filter(slug=slug).exists():
            return Response({'detail': f'Slug "{slug}" is already in use.'}, status=409)

        is_public = str(request.data.get('is_public', '1')).lower() not in ('0', 'false', 'no')
        permanent = str(request.data.get('permanent', '0')).lower() in ('1', 'true', 'yes')
        item = LinkRedirect(
            slug=slug,
            title=title or slug,
            target_url=target_url,
            is_public=is_public,
            permanent=permanent,
        )
        item.full_clean()
        item.save()
        return Response(serialize_item(item, request), status=status.HTTP_201_CREATED)


class LinkRedirectDetailView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsSuperuserRole]
    parser_classes = [JSONParser]

    def get_object(self, pk):
        return get_object_or_404(LinkRedirect, pk=pk)

    def get(self, request, pk):
        return Response(serialize_item(self.get_object(pk), request))

    def patch(self, request, pk):
        item = self.get_object(pk)
        if 'title' in request.data:
            item.title = (request.data.get('title') or '').strip()
        if 'is_public' in request.data:
            item.is_public = str(request.data.get('is_public')).lower() not in ('0', 'false', 'no')
        if 'permanent' in request.data:
            item.permanent = str(request.data.get('permanent')).lower() in ('1', 'true', 'yes')
        if 'target_url' in request.data:
            target_url = (request.data.get('target_url') or '').strip()
            try:
                validate_target_url(target_url)
            except Exception as e:
                return Response({'detail': str(e)}, status=400)
            item.target_url = target_url
        if 'slug' in request.data:
            new_slug = (request.data.get('slug') or '').strip().lower()
            try:
                validate_slug(new_slug)
            except Exception as e:
                return Response({'detail': str(e)}, status=400)
            if LinkRedirect.objects.filter(slug=new_slug).exclude(pk=item.pk).exists():
                return Response({'detail': f'Slug "{new_slug}" is already in use.'}, status=409)
            item.slug = new_slug
        item.full_clean()
        item.save()
        return Response(serialize_item(item, request))

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
