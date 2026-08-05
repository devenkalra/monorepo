from django.contrib.contenttypes.models import ContentType
from django.db.models import Max
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .counts import compute_area_descendant_counts, inventory_summary
from .models import (
    AssetPhoto, AssetCategory, AssetTag, AssetArea, AssetItem,
)
from .serializers import (
    AssetCategorySerializer, AssetTagSerializer, AssetPhotoSerializer,
    AssetAreaSerializer, AssetItemSerializer,
)


class AssetAuthMixin:
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]


class AssetPhotoActionsMixin:
    """Upload, delete, and reorder photos on an asset entity."""

    def _photo_qs(self, obj):
        ct = ContentType.objects.get_for_model(obj.__class__)
        return AssetPhoto.objects.filter(content_type=ct, object_id=obj.pk)

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser, JSONParser])
    def photos(self, request, pk=None):
        obj = self.get_object()
        image = request.FILES.get('image')
        if not image:
            return Response({'detail': 'image file required'}, status=status.HTTP_400_BAD_REQUEST)
        qs = self._photo_qs(obj)
        max_order = qs.aggregate(m=Max('sort_order'))['m']
        sort_order = 0 if max_order is None else max_order + 1
        photo = AssetPhoto.objects.create(
            image=image,
            description=request.data.get('description', ''),
            sort_order=sort_order,
            content_type=ContentType.objects.get_for_model(obj.__class__),
            object_id=obj.pk,
        )
        return Response(
            AssetPhotoSerializer(photo, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=['delete'],
        url_path=r'photos/(?P<photo_id>[^/.]+)',
    )
    def delete_photo(self, request, pk=None, photo_id=None):
        obj = self.get_object()
        try:
            photo = self._photo_qs(obj).get(pk=photo_id)
        except AssetPhoto.DoesNotExist:
            return Response({'detail': 'Photo not found.'}, status=status.HTTP_404_NOT_FOUND)
        photo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='reorder-photos')
    def reorder_photos(self, request, pk=None):
        """Set display order; first id becomes the cover image."""
        obj = self.get_object()
        photo_ids = request.data.get('photo_ids')
        if not isinstance(photo_ids, list) or not photo_ids:
            return Response(
                {'detail': 'photo_ids must be a non-empty list of photo ids.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        photos = {p.id: p for p in self._photo_qs(obj)}
        missing = [pid for pid in photo_ids if pid not in photos]
        if missing:
            return Response(
                {'detail': f'Unknown photo ids for this asset: {missing}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for index, photo_id in enumerate(photo_ids):
            photo = photos[photo_id]
            if photo.sort_order != index:
                photo.sort_order = index
                photo.save(update_fields=['sort_order', 'modified_at'])
        ordered = [
            AssetPhotoSerializer(photos[pid], context={'request': request}).data
            for pid in photo_ids
        ]
        return Response({'photos': ordered})


class AssetCategoryViewSet(AssetAuthMixin, viewsets.ModelViewSet):
    queryset = AssetCategory.objects.all()
    serializer_class = AssetCategorySerializer


class AssetTagViewSet(AssetAuthMixin, viewsets.ModelViewSet):
    queryset = AssetTag.objects.all()
    serializer_class = AssetTagSerializer


def _nullish(value):
    return value is not None and str(value).lower() in ('', 'null', 'none')


class AssetAreaViewSet(AssetAuthMixin, AssetPhotoActionsMixin, viewsets.ModelViewSet):
    queryset = AssetArea.objects.select_related('category', 'parent_area').prefetch_related('tags', 'photos')
    serializer_class = AssetAreaSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        # One tree walk per request; shared across all serialized areas.
        if 'area_counts' not in ctx:
            ctx['area_counts'] = compute_area_descendant_counts()
        return ctx

    def get_queryset(self):
        qs = super().get_queryset()
        parent = self.request.query_params.get('parent_area')
        q = self.request.query_params.get('q')
        if parent is not None:
            if _nullish(parent):
                qs = qs.filter(parent_area__isnull=True)
            else:
                qs = qs.filter(parent_area_id=parent)
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Inventory-wide totals for the root location display."""
        data = inventory_summary()
        return Response({
            'container_count': data['container_count'],
            'item_count': data['item_count'],
            'unlocated_item_count': data['unlocated_item_count'],
        })


class AssetItemViewSet(AssetAuthMixin, AssetPhotoActionsMixin, viewsets.ModelViewSet):
    queryset = AssetItem.objects.select_related('category', 'area').prefetch_related('tags', 'photos')
    serializer_class = AssetItemSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get('q')
        area = self.request.query_params.get('area')
        category = self.request.query_params.get('category')
        tag = self.request.query_params.get('tag')
        unlocated = self.request.query_params.get('unlocated')
        if q:
            qs = qs.filter(name__icontains=q)
        if unlocated is not None and str(unlocated).lower() in ('1', 'true', 'yes'):
            qs = qs.filter(area__isnull=True)
        elif area is not None:
            if _nullish(area):
                qs = qs.filter(area__isnull=True)
            else:
                qs = qs.filter(area_id=area)
        if category:
            qs = qs.filter(category_id=category)
        if tag:
            qs = qs.filter(tags__id=tag)
        return qs.distinct()
