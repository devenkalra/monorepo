from datetime import datetime, timezone
from pathlib import Path

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from people.models import Entity, FileReference, UserProfile
from people.utils import save_file_deduplicated

from .access import mark_share_unlocked, require_gallery_perm, resolve_access
from .analyze import ensure_item_analysis
from .constants import ACCESS_PUBLIC, MEDIA_IMAGE, MEDIA_VIDEO, ROLE_ADD, ROLE_EDIT
from .generate import start_generate_job
from .models import Gallery, GalleryItem, GalleryShare, GalleryShow, ShowBuildJob, UserMedia
from .presets import DEFAULT_STYLE, PRESETS
from .serializers import (
    GalleryDetailSerializer,
    GalleryItemSerializer,
    GalleryListSerializer,
    GalleryShareSerializer,
    GalleryShowSerializer,
    GalleryWriteSerializer,
    PublicGalleryUnlockSerializer,
    ReorderSerializer,
    ShowBuildJobSerializer,
    SortSerializer,
)
from .tasks import generate_item_thumbnail
from .utils import ensure_public_username, guess_media_type, normalize_photo, photo_source_key


def _deny(access, detail='Forbidden'):
    code = 'forbidden'
    if access.get('needs_login'):
        code = 'login_required'
        detail = 'Login required to view this gallery.'
    elif access.get('needs_share_password'):
        code = 'share_password_required'
        detail = 'Share password required.'
    elif access.get('needs_signup'):
        code = 'signup_required'
        detail = 'Create an account with your invited email to view this gallery.'
    return Response({'detail': detail, 'code': code}, status=status.HTTP_403_FORBIDDEN)


class GalleryViewSet(viewsets.ModelViewSet):
    """Owner + collaborator management under /api/gallery/galleries/."""

    lookup_field = 'id'

    def get_permissions(self):
        if self.action in ('list', 'create'):
            return [IsAuthenticated()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        email = (user.email or '').strip()
        qs = Gallery.objects.filter(
            Q(owner=user)
            | Q(
                shares__email__iexact=email,
                shares__active=True,
                shares__role__in=[ROLE_EDIT, ROLE_ADD],
            )
        ).distinct()
        return qs.annotate(item_count=Count('items', distinct=True)).prefetch_related(
            'items', 'shows', 'shares'
        )

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return GalleryWriteSerializer
        if self.action == 'retrieve':
            return GalleryDetailSerializer
        return GalleryListSerializer

    def retrieve(self, request, *args, **kwargs):
        gallery = get_object_or_404(Gallery.objects.prefetch_related('items', 'shows', 'shares'), id=kwargs['id'])
        access = resolve_access(request, gallery)
        if not access['can_view'] and not access['can_edit']:
            # Owners/editors always; if only view via share need unlock — still allow retrieve meta for unlock UI if share matches
            if access.get('needs_share_password') or access.get('needs_login'):
                ser = GalleryDetailSerializer(
                    gallery,
                    context={'request': request, 'access': access},
                )
                data = ser.data
                # Strip items until unlocked
                data['items'] = []
                data['shows'] = []
                data['shares'] = [] if not access.get('is_owner') else data.get('shares')
                return Response(data)
            return _deny(access)
        ser = GalleryDetailSerializer(gallery, context={'request': request, 'access': access})
        data = ser.data
        if not access.get('is_owner') and not access.get('can_edit'):
            data['shares'] = []
        return Response(data)

    def perform_create(self, serializer):
        ensure_public_username(self.request.user)
        serializer.save(owner=self.request.user)

    def update(self, request, *args, **kwargs):
        gallery = self.get_object()
        access = require_gallery_perm(request, gallery, ROLE_EDIT)
        if not access['can_edit']:
            return _deny(access, 'Edit permission required.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        gallery = self.get_object()
        if gallery.owner_id != request.user.id:
            return Response({'detail': 'Only the owner can delete.'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='refresh-from-entity')
    def refresh_from_entity(self, request, id=None):
        gallery = self.get_object()
        access = require_gallery_perm(request, gallery, ROLE_EDIT)
        if not access['can_edit']:
            return _deny(access, 'Edit permission required.')

        entity_id = request.data.get('entity_id') or (gallery.source_entity_id and str(gallery.source_entity_id))
        if not entity_id:
            return Response({'detail': 'entity_id required.'}, status=status.HTTP_400_BAD_REQUEST)
        entity = get_object_or_404(Entity, id=entity_id, user=gallery.owner)
        gallery.source_entity = entity
        gallery.save(update_fields=['source_entity', 'updated_at'])

        existing_keys = set(
            gallery.items.exclude(source_photo_key='').values_list('source_photo_key', flat=True)
        )
        max_order = gallery.items.order_by('-sort_order').values_list('sort_order', flat=True).first()
        next_order = (max_order if max_order is not None else -1) + 1
        created = []
        for photo in entity.photos or []:
            key = photo_source_key(photo)
            if not key or key in existing_keys:
                continue
            norm = normalize_photo(photo)
            url = norm.get('url') or ''
            is_external = url.startswith('http://') or url.startswith('https://')
            media_type = guess_media_type(url)
            item = GalleryItem.objects.create(
                gallery=gallery,
                sort_order=next_order,
                media_type=media_type,
                url='' if is_external else url,
                external_url=url if is_external else '',
                thumbnail_url=norm.get('thumbnail_url') or '',
                title=norm.get('title') or '',
                caption=norm.get('caption') or '',
                filename=norm.get('filename') or '',
                source_photo_key=key,
                thumbnail_status='pending' if media_type == MEDIA_VIDEO and not is_external else 'ready',
            )
            next_order += 1
            existing_keys.add(key)
            created.append(item)
            if item.thumbnail_status == 'pending':
                generate_item_thumbnail.delay(str(item.id))

        return Response(
            {
                'added': len(created),
                'items': GalleryItemSerializer(created, many=True).data,
            }
        )

    @action(detail=True, methods=['post'])
    def reorder(self, request, id=None):
        gallery = self.get_object()
        access = require_gallery_perm(request, gallery, ROLE_EDIT)
        if not access['can_edit']:
            return _deny(access, 'Edit permission required.')
        ser = ReorderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ids = ser.validated_data['item_ids']
        items = {str(i.id): i for i in gallery.items.filter(id__in=ids)}
        for idx, item_id in enumerate(ids):
            item = items.get(str(item_id))
            if item:
                item.sort_order = idx
                item.save(update_fields=['sort_order'])
        return Response({'ok': True})

    @action(detail=True, methods=['post'])
    def sort_items(self, request, id=None):
        gallery = self.get_object()
        access = require_gallery_perm(request, gallery, ROLE_EDIT)
        if not access['can_edit']:
            return _deny(access, 'Edit permission required.')
        ser = SortSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        field = ser.validated_data['by']
        desc = ser.validated_data['direction'] == 'desc'
        order = f'-{field}' if desc else field
        for idx, item in enumerate(gallery.items.order_by(order)):
            if item.sort_order != idx:
                item.sort_order = idx
                item.save(update_fields=['sort_order'])
        return Response(GalleryItemSerializer(gallery.items.all(), many=True).data)


class GalleryItemViewSet(viewsets.ModelViewSet):
    serializer_class = GalleryItemSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_queryset(self):
        return GalleryItem.objects.filter(gallery__owner=self.request.user)

    def create(self, request, *args, **kwargs):
        gallery_id = request.data.get('gallery')
        gallery = get_object_or_404(Gallery, id=gallery_id)
        access = require_gallery_perm(request, gallery, ROLE_ADD)
        if not access['can_add']:
            return _deny(access, 'Add permission required.')
        data = request.data.copy()
        if 'sort_order' not in data:
            max_order = gallery.items.order_by('-sort_order').values_list('sort_order', flat=True).first()
            data['sort_order'] = (max_order if max_order is not None else -1) + 1
        ser = self.get_serializer(data=data)
        ser.is_valid(raise_exception=True)
        item = ser.save()
        if item.media_type == MEDIA_VIDEO and item.url and not item.thumbnail_url:
            item.thumbnail_status = 'pending'
            item.save(update_fields=['thumbnail_status'])
            generate_item_thumbnail.delay(str(item.id))
        elif item.media_type == MEDIA_IMAGE:
            ensure_item_analysis(item)
        return Response(self.get_serializer(item).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        item = self.get_object_for_write()
        if item is None:
            return Response({'detail': 'Not found or no permission.'}, status=status.HTTP_404_NOT_FOUND)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        item = self.get_object_for_write()
        if item is None:
            return Response({'detail': 'Not found or no permission.'}, status=status.HTTP_404_NOT_FOUND)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_object_for_write(self):
        item = get_object_or_404(GalleryItem, id=self.kwargs['id'])
        access = require_gallery_perm(self.request, item.gallery, ROLE_EDIT)
        # add_photos can also remove their additions? Spec: edit for manage; add can add. Allow edit for delete/update.
        if not access['can_edit'] and not access['can_add']:
            return None
        if not access['can_edit']:
            # add_photos: allow update caption on items? keep simple — only edit role for mutate existing
            return None
        return item

    def get_object(self):
        obj = self.get_object_for_write()
        if obj is None:
            from rest_framework.exceptions import NotFound
            raise NotFound()
        return obj


class GalleryShareViewSet(viewsets.ModelViewSet):
    serializer_class = GalleryShareSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_queryset(self):
        return GalleryShare.objects.filter(gallery__owner=self.request.user)

    def create(self, request, *args, **kwargs):
        gallery = get_object_or_404(Gallery, id=request.data.get('gallery'), owner=request.user)
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        share = ser.save(gallery=gallery)
        return Response(self.get_serializer(share).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        if serializer.instance.gallery.owner_id != self.request.user.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied()
        serializer.save()

    def perform_destroy(self, instance):
        if instance.gallery.owner_id != self.request.user.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied()
        instance.delete()


class GalleryShowViewSet(viewsets.ModelViewSet):
    serializer_class = GalleryShowSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        return GalleryShow.objects.filter(gallery__owner=user)

    def create(self, request, *args, **kwargs):
        gallery = get_object_or_404(Gallery, id=request.data.get('gallery'))
        access = require_gallery_perm(request, gallery, ROLE_EDIT)
        if not access['can_edit']:
            return _deny(access, 'Edit permission required.')
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        show = ser.save(gallery=gallery)
        return Response(self.get_serializer(show).data, status=status.HTTP_201_CREATED)

    def get_object(self):
        show = get_object_or_404(GalleryShow, id=self.kwargs['id'])
        access = require_gallery_perm(self.request, show.gallery, ROLE_EDIT)
        if not access['can_edit']:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied()
        return show


class GenerateShowView(APIView):
    """Queue a show build and return a job id for status + log polling."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        gallery = get_object_or_404(Gallery, id=request.data.get('gallery'))
        access = require_gallery_perm(request, gallery, ROLE_EDIT)
        if not access['can_edit']:
            return _deny(access, 'Edit permission required.')

        raw_ids = request.data.get('item_ids')
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {'detail': 'Select at least one image, in the order they should play.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        items_by_id = {str(it.id): it for it in gallery.items.all()}
        ordered = []
        accepted = set()
        for raw in raw_ids:
            key = str(raw)
            item = items_by_id.get(key)
            if not item or (item.media_type and item.media_type != MEDIA_IMAGE):
                continue
            ordered.append(key)
            accepted.add(key)

        if not ordered:
            return Response(
                {'detail': 'None of the selected items are images in this gallery.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        style = (request.data.get('style') or DEFAULT_STYLE).lower()
        if style not in PRESETS:
            style = DEFAULT_STYLE
        title = (request.data.get('title') or 'Show').strip() or 'Show'
        target = request.data.get('target_seconds')
        try:
            target = float(target) if target is not None and target != '' else None
        except (TypeError, ValueError):
            target = None
        prompt = request.data.get('prompt') or ''
        if not isinstance(prompt, str):
            prompt = ''
        prompt = prompt.strip()[:2000]

        job = ShowBuildJob.objects.create(
            gallery=gallery,
            owner=request.user,
            status=ShowBuildJob.STATUS_QUEUED,
            prompt=prompt,
            style=style,
            target_seconds=target,
            item_ids=ordered,
            title=title,
            log=[{
                't': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                'step': 'queued',
                'level': 'info',
                'message': f'Queued {len(ordered)} image(s). Waiting to start…',
            }],
        )
        start_generate_job(job.id)
        return Response(ShowBuildJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class ShowBuildJobView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        job = get_object_or_404(ShowBuildJob.objects.select_related('show', 'gallery'), id=job_id)
        if job.owner_id != request.user.id:
            access = require_gallery_perm(request, job.gallery, ROLE_EDIT)
            if not access['can_edit']:
                return _deny(access, 'Edit permission required.')
        return Response(ShowBuildJobSerializer(job).data)


class PublicGalleryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, username, slug):
        profile = get_object_or_404(UserProfile, public_username__iexact=username)
        gallery = get_object_or_404(
            Gallery.objects.prefetch_related('items', 'shows'),
            owner=profile.user,
            slug=slug,
        )
        access = resolve_access(request, gallery)
        if not access['can_view']:
            # Return shell for unlock / login UI
            if access.get('needs_login') or access.get('needs_share_password') or access.get('needs_signup'):
                ser = GalleryDetailSerializer(
                    gallery, context={'request': request, 'access': access}
                )
                data = ser.data
                data['items'] = []
                data['shows'] = []
                data['shares'] = []
                return Response(data)
            return _deny(access)

        ser = GalleryDetailSerializer(gallery, context={'request': request, 'access': access})
        data = ser.data
        data['shares'] = []
        if not access.get('can_edit'):
            # hide management fields already mostly stripped
            pass
        return Response(data)


class PublicGalleryUnlockView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, username, slug):
        if not request.user.is_authenticated:
            return Response(
                {'detail': 'Login required.', 'code': 'login_required'},
                status=status.HTTP_403_FORBIDDEN,
            )
        profile = get_object_or_404(UserProfile, public_username__iexact=username)
        gallery = get_object_or_404(Gallery, owner=profile.user, slug=slug)
        if gallery.access_mode == ACCESS_PUBLIC:
            return Response({'ok': True, 'detail': 'Public gallery.'})

        ser = PublicGalleryUnlockSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = (request.user.email or '').strip().lower()
        share = gallery.shares.filter(email__iexact=email, active=True).first()
        if not share:
            return Response(
                {'detail': 'You are not on the allow list.', 'code': 'not_invited'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not share.check_password(ser.validated_data['password']):
            return Response({'detail': 'Invalid share password.', 'code': 'bad_password'}, status=status.HTTP_403_FORBIDDEN)
        mark_share_unlocked(request, gallery, share)
        access = resolve_access(request, gallery)
        payload = GalleryDetailSerializer(gallery, context={'request': request, 'access': access}).data
        payload['shares'] = []
        return Response(payload)


def _media_url_from_path(path: str) -> str:
    path = (path or '').replace('\\', '/').lstrip('/')
    if path.startswith('media/'):
        path = path[len('media/') :]
    if path.startswith('/media/'):
        return path
    return f'/media/{path}'


def _register_user_media(owner, *, url, thumbnail_url='', filename='', media_type='', sha256=''):
    if not url or url.startswith('http://') or url.startswith('https://'):
        return None
    media_type = media_type or guess_media_type(url)
    obj, _ = UserMedia.objects.update_or_create(
        owner=owner,
        url=url,
        defaults={
            'thumbnail_url': thumbnail_url or '',
            'filename': filename or Path(url).name,
            'media_type': media_type,
            'sha256': sha256 or '',
        },
    )
    return obj


class MediaBrowserView(APIView):
    """Browse a user's media library and/or entity photos."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        ensure_public_username(request.user)
        q = (request.query_params.get('q') or '').strip().lower()
        source = (request.query_params.get('source') or 'all').lower()
        entity_id = request.query_params.get('entity_id')
        # Optional: browse another gallery owner's library when collaborator has add access
        gallery_id = request.query_params.get('gallery')
        owner = request.user
        if gallery_id:
            gallery = get_object_or_404(Gallery, id=gallery_id)
            access = require_gallery_perm(request, gallery, ROLE_ADD)
            if not access['can_add']:
                return _deny(access, 'Add permission required.')
            owner = gallery.owner

        seen = set()
        results = []

        def add_result(entry):
            url = entry.get('url') or ''
            if not url or url in seen:
                return False
            filename = entry.get('filename') or Path(url.split('?', 1)[0]).name
            hay = f'{url} {filename} {entry.get("caption") or ""} {entry.get("entity_display") or ""}'.lower()
            if q and q not in hay:
                return False
            seen.add(url)
            results.append(
                {
                    'url': url,
                    'thumbnail_url': entry.get('thumbnail_url') or url,
                    'filename': filename,
                    'caption': entry.get('caption') or '',
                    'entity_id': entry.get('entity_id') or '',
                    'entity_display': entry.get('entity_display') or '',
                    'media_type': entry.get('media_type') or guess_media_type(url),
                    'source_photo_key': entry.get('source_photo_key') or url,
                    'source': entry.get('source') or 'library',
                }
            )
            return len(results) >= 500

        if source in ('library', 'all', 'files'):
            for um in UserMedia.objects.filter(owner=owner)[:500]:
                if add_result(
                    {
                        'url': um.url,
                        'thumbnail_url': um.thumbnail_url,
                        'filename': um.filename,
                        'media_type': um.media_type,
                        'source': 'library',
                    }
                ):
                    return Response({'results': results, 'source': source})

            for item in GalleryItem.objects.filter(gallery__owner=owner).exclude(url='')[:500]:
                if add_result(
                    {
                        'url': item.url,
                        'thumbnail_url': item.thumbnail_url,
                        'filename': item.filename,
                        'caption': item.caption,
                        'media_type': item.media_type,
                        'source': 'library',
                    }
                ):
                    return Response({'results': results, 'source': source})

            for ref in FileReference.objects.filter(entity__user=owner).select_related('entity')[:500]:
                url = _media_url_from_path(ref.file_path)
                if add_result(
                    {
                        'url': url,
                        'thumbnail_url': url,
                        'filename': Path(url).name,
                        'entity_id': str(ref.entity_id),
                        'entity_display': ref.entity.display or '',
                        'media_type': guess_media_type(url),
                        'source': 'library',
                    }
                ):
                    return Response({'results': results, 'source': source})

        if source in ('entities', 'all'):
            entities = Entity.objects.filter(user=owner)
            if entity_id:
                entities = entities.filter(id=entity_id)
            for ent in entities.only('id', 'display', 'photos', 'attachments')[:500]:
                for field in ('photos', 'attachments'):
                    for photo in getattr(ent, field, None) or []:
                        norm = normalize_photo(photo)
                        url = norm.get('url') or ''
                        if add_result(
                            {
                                'url': url,
                                'thumbnail_url': norm.get('thumbnail_url') or url,
                                'filename': norm.get('filename') or '',
                                'caption': norm.get('caption') or '',
                                'entity_id': str(ent.id),
                                'entity_display': ent.display or '',
                                'media_type': guess_media_type(url),
                                'source_photo_key': photo_source_key(photo),
                                'source': 'entities',
                            }
                        ):
                            return Response({'results': results, 'source': source})

        return Response({'results': results, 'source': source})


class GalleryUploadView(APIView):
    """Upload local files into /media/ (owner's library) and optionally into a gallery."""

    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        gallery = None
        gallery_id = request.data.get('gallery')
        owner = request.user
        if gallery_id:
            gallery = get_object_or_404(Gallery, id=gallery_id)
            access = require_gallery_perm(request, gallery, ROLE_ADD)
            if not access['can_add']:
                return _deny(access, 'Add permission required.')
            owner = gallery.owner

        try:
            saved = save_file_deduplicated(file_obj)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        url = saved.get('url') or ''
        # Normalize Windows path separators from os.path.join
        url = url.replace('\\', '/')
        if not url.startswith('/'):
            url = f'/{url}' if url.startswith('media/') else f'/media/{url}'
        thumb = (saved.get('thumbnail_url') or '').replace('\\', '/')
        media_type = guess_media_type(url)
        um = _register_user_media(
            owner,
            url=url,
            thumbnail_url=thumb,
            filename=getattr(file_obj, 'name', '') or Path(url).name,
            media_type=media_type,
            sha256=saved.get('sha256') or '',
        )

        item_data = None
        add_to_gallery = str(request.data.get('add_to_gallery', 'true')).lower() in ('1', 'true', 'yes')
        if gallery and add_to_gallery:
            max_order = gallery.items.order_by('-sort_order').values_list('sort_order', flat=True).first()
            item = GalleryItem.objects.create(
                gallery=gallery,
                sort_order=(max_order if max_order is not None else -1) + 1,
                media_type=media_type,
                url=url,
                thumbnail_url=thumb,
                filename=um.filename if um else Path(url).name,
                title='',
                caption='',
                source_photo_key=url,
                thumbnail_status='pending' if media_type == MEDIA_VIDEO else 'ready',
            )
            if item.thumbnail_status == 'pending':
                generate_item_thumbnail.delay(str(item.id))
            elif media_type == MEDIA_IMAGE:
                ensure_item_analysis(item)
            item_data = GalleryItemSerializer(item).data

        return Response(
            {
                'url': url,
                'thumbnail_url': thumb,
                'filename': um.filename if um else Path(url).name,
                'media_type': media_type,
                'sha256': saved.get('sha256') or '',
                'user_media_id': str(um.id) if um else None,
                'item': item_data,
            },
            status=status.HTTP_201_CREATED,
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ensure_username(request):
    name = ensure_public_username(request.user)
    return Response({'public_username': name})
