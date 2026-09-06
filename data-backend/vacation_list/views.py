from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .models import VacTag, VacCategory, VacItem, VacList, VacListItem

_ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
_MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _validate_item_image(uploaded):
    if not uploaded:
        return 'Image file required.'
    if uploaded.size and uploaded.size > _MAX_IMAGE_BYTES:
        return 'Image must be 8 MB or smaller.'
    content_type = (getattr(uploaded, 'content_type', '') or '').lower()
    if content_type and content_type not in _ALLOWED_IMAGE_TYPES:
        return 'Image must be a JPEG, PNG, GIF, or WebP file.'
    try:
        from PIL import Image
        uploaded.seek(0)
        image = Image.open(uploaded)
        image.verify()
        uploaded.seek(0)
    except Exception:
        return 'Could not read that file as an image.'
    return None
from .serializers import (
    VacTagSerializer, VacCategorySerializer, VacItemSerializer,
    VacListSerializer, VacListItemSerializer,
)


class UserScopedMixin:
    def get_queryset(self):
        qs = super().get_queryset()
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return qs.none()
        return qs.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class VacTagViewSet(UserScopedMixin, viewsets.ModelViewSet):
    queryset = VacTag.objects.all()
    serializer_class = VacTagSerializer
    pagination_class = None


class VacCategoryViewSet(UserScopedMixin, viewsets.ModelViewSet):
    queryset = VacCategory.objects.all()
    serializer_class = VacCategorySerializer
    pagination_class = None


class VacItemViewSet(UserScopedMixin, viewsets.ModelViewSet):
    queryset = VacItem.objects.select_related('category').prefetch_related('tags').all()
    serializer_class = VacItemSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        tag = self.request.query_params.get('tag')
        category = self.request.query_params.get('category')
        q = self.request.query_params.get('q')
        if tag:
            # Multi-select: ?tag=1,2 (OR — item matching any selected tag)
            tag_ids = [t.strip() for t in str(tag).split(',') if t.strip()]
            if tag_ids:
                qs = qs.filter(tags__id__in=tag_ids)
        if category:
            qs = qs.filter(category_id=category)
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(name_group__icontains=q)
                | Q(description__icontains=q)
                | Q(tags__name__icontains=q)
            )
        if self.action == 'list':
            archived = self.request.query_params.get('archived')
            if archived is None or str(archived).lower() in ('0', 'false', 'no'):
                qs = qs.filter(is_archived=False)
            elif str(archived).lower() in ('1', 'true', 'yes'):
                qs = qs.filter(is_archived=True)
        return qs.distinct()

    @action(detail=False, methods=['post'], url_path='bulk')
    def bulk(self, request):
        """Bulk update catalog items: { ids, name_group?|category_id?|add_tag_id?|remove_tag_id?|delete? }."""
        ids = request.data.get('ids') or []
        if not ids:
            return Response({'detail': 'ids required.'}, status=status.HTTP_400_BAD_REQUEST)

        qs = VacItem.objects.filter(user=request.user, id__in=ids)
        if not qs.exists():
            return Response({'detail': 'No matching items.'}, status=status.HTTP_400_BAD_REQUEST)

        if request.data.get('delete'):
            deleted = qs.count()
            qs.delete()
            return Response({'deleted': deleted})

        if request.data.get('archive'):
            updated = qs.update(is_archived=True, modified_on=timezone.now())
            return Response({'updated': updated})

        if request.data.get('unarchive'):
            updated = qs.update(is_archived=False, modified_on=timezone.now())
            return Response({'updated': updated})

        if 'name_group' in request.data:
            name_group = str(request.data.get('name_group') or '').strip()
            updated = qs.update(name_group=name_group, modified_on=timezone.now())
            return Response({'updated': updated})

        if 'category_id' in request.data:
            category_id = request.data.get('category_id')
            if category_id in (None, ''):
                updated = qs.update(category=None, modified_on=timezone.now())
                return Response({'updated': updated})
            category = VacCategory.objects.filter(pk=category_id, user=request.user).first()
            if not category:
                return Response({'detail': 'Category not found.'}, status=status.HTTP_400_BAD_REQUEST)
            updated = qs.update(category=category, modified_on=timezone.now())
            return Response({'updated': updated})

        add_tag_id = request.data.get('add_tag_id')
        if add_tag_id not in (None, ''):
            tag = VacTag.objects.filter(pk=add_tag_id, user=request.user).first()
            if not tag:
                return Response({'detail': 'Tag not found.'}, status=status.HTTP_400_BAD_REQUEST)
            to_tag = list(qs.exclude(tags=tag))
            for item in to_tag:
                item.tags.add(tag)
            return Response({'updated': len(to_tag)})

        remove_tag_id = request.data.get('remove_tag_id')
        if remove_tag_id not in (None, ''):
            tag = VacTag.objects.filter(pk=remove_tag_id, user=request.user).first()
            if not tag:
                return Response({'detail': 'Tag not found.'}, status=status.HTTP_400_BAD_REQUEST)
            tagged = list(qs.filter(tags=tag))
            for item in tagged:
                item.tags.remove(tag)
            return Response({'updated': len(tagged)})

        return Response({'detail': 'No changes specified.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=True,
        methods=['post', 'delete'],
        url_path='image',
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def image(self, request, pk=None):
        item = self.get_object()
        if request.method == 'DELETE':
            if item.image:
                item.image.delete(save=False)
                item.image = None
                item.save(update_fields=['image', 'modified_on'])
            return Response(self.get_serializer(item).data)

        uploaded = request.FILES.get('file') or request.FILES.get('image')
        error = _validate_item_image(uploaded)
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)
        if item.image:
            item.image.delete(save=False)
        item.image = uploaded
        item.save(update_fields=['image', 'modified_on'])
        return Response(self.get_serializer(item).data)


class VacListViewSet(UserScopedMixin, viewsets.ModelViewSet):
    queryset = VacList.objects.prefetch_related('initial_tags').all()
    serializer_class = VacListSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        # Only the collection endpoint hides archived lists by default.
        # Detail/actions can still target an archived list (e.g. unarchive).
        if self.action != 'list':
            return qs
        archived = self.request.query_params.get('archived')
        if archived is None:
            return qs.filter(is_archived=False)
        if str(archived).lower() in ('1', 'true', 'yes'):
            return qs.filter(is_archived=True)
        if str(archived).lower() in ('0', 'false', 'no'):
            return qs.filter(is_archived=False)
        if str(archived).lower() in ('all', '*'):
            return qs
        return qs.filter(is_archived=False)

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        vac_list = self.get_object()
        vac_list.is_archived = True
        vac_list.save(update_fields=['is_archived', 'modified_on'])
        return Response(self.get_serializer(vac_list).data)

    @action(detail=True, methods=['post'], url_path='unarchive')
    def unarchive(self, request, pk=None):
        vac_list = self.get_object()
        vac_list.is_archived = False
        vac_list.save(update_fields=['is_archived', 'modified_on'])
        return Response(self.get_serializer(vac_list).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        populate = serializer.validated_data.pop('populate', 'blank') or 'blank'
        copy_from_id = serializer.validated_data.pop('copy_from_id', None)

        if populate == 'copy':
            if not copy_from_id:
                return Response(
                    {'detail': 'copy_from_id is required when populate=copy.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            source_qs = VacList.objects.filter(
                pk=copy_from_id, is_archived=False, user=request.user
            )
            if not source_qs.exists():
                return Response(
                    {'detail': 'Source list not found (or is archived).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        vac_list = serializer.save(user=request.user)
        added = 0
        if vac_list.initial_tags.exists() and populate == 'blank':
            # Keep legacy tag-seed behavior only for blank creates that set tags
            added = vac_list.seed_from_initial_tags()
        elif populate == 'all_items':
            added = vac_list.populate_all_catalog_items()
        elif populate == 'copy':
            source = VacList.objects.get(pk=copy_from_id, user=request.user)
            added = vac_list.copy_items_from(source)

        headers = self.get_success_headers(serializer.data)
        data = self.get_serializer(vac_list).data
        data['added'] = added
        data['populate'] = populate
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['get'])
    def items(self, request, pk=None):
        vac_list = self.get_object()
        qs = vac_list.list_items.select_related('item', 'item__category').prefetch_related('item__tags')
        need = request.query_params.get('need')
        done = request.query_params.get('done')
        if need is not None:
            qs = qs.filter(need=need.lower() in ('1', 'true', 'yes'))
        if done is not None:
            qs = qs.filter(done=done.lower() in ('1', 'true', 'yes'))
        return Response(VacListItemSerializer(qs, many=True, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='seed')
    def seed(self, request, pk=None):
        vac_list = self.get_object()
        added = vac_list.seed_from_initial_tags()
        return Response({'added': added})

    @action(detail=True, methods=['post'], url_path='bulk')
    def bulk(self, request, pk=None):
        """Bulk update list items: { ids: [], need?, done?, remove? }."""
        vac_list = self.get_object()
        ids = request.data.get('ids') or []
        qs = vac_list.list_items.filter(id__in=ids)
        if request.data.get('remove'):
            deleted, _ = qs.delete()
            return Response({'removed': deleted})
        updates = {}
        if 'need' in request.data:
            updates['need'] = bool(request.data.get('need'))
        if 'done' in request.data:
            updates['done'] = bool(request.data.get('done'))
        if updates:
            updated = qs.update(**updates)
            return Response({'updated': updated})
        return Response({'detail': 'No changes specified.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='add-items')
    def add_items(self, request, pk=None):
        """Add catalog VacItems to this list: { item_ids: [] }."""
        vac_list = self.get_object()
        item_ids = request.data.get('item_ids') or []
        if not item_ids:
            return Response({'detail': 'item_ids required.'}, status=status.HTTP_400_BAD_REQUEST)

        existing = set(
            vac_list.list_items.filter(item_id__in=item_ids).values_list('item_id', flat=True)
        )
        to_create = []
        for item in VacItem.objects.filter(id__in=item_ids, user=request.user):
            if item.id in existing:
                continue
            to_create.append(
                VacListItem(item=item, in_list=vac_list, user=request.user, need=True, done=False)
            )
            existing.add(item.id)
        VacListItem.objects.bulk_create(to_create)
        return Response({
            'added': len(to_create),
            'skipped': len(item_ids) - len(to_create),
        })


class VacListItemViewSet(UserScopedMixin, viewsets.ModelViewSet):
    queryset = VacListItem.objects.select_related('item', 'in_list').all()
    serializer_class = VacListItemSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        list_id = self.request.query_params.get('list')
        if list_id:
            qs = qs.filter(in_list_id=list_id)
        return qs
