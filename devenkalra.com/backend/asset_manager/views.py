from django.contrib.contenttypes.models import ContentType
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import (
    AssetPhoto, AssetCategory, AssetTag, AssetArea, AssetBox, AssetItem,
)
from .serializers import (
    AssetCategorySerializer, AssetTagSerializer, AssetPhotoSerializer,
    AssetAreaSerializer, AssetBoxSerializer, AssetItemSerializer,
)


class AssetAuthMixin:
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]


class AssetCategoryViewSet(AssetAuthMixin, viewsets.ModelViewSet):
    queryset = AssetCategory.objects.all()
    serializer_class = AssetCategorySerializer


class AssetTagViewSet(AssetAuthMixin, viewsets.ModelViewSet):
    queryset = AssetTag.objects.all()
    serializer_class = AssetTagSerializer


class AssetAreaViewSet(AssetAuthMixin, viewsets.ModelViewSet):
    queryset = AssetArea.objects.select_related('category', 'parent_area').prefetch_related('tags', 'photos')
    serializer_class = AssetAreaSerializer


class AssetBoxViewSet(AssetAuthMixin, viewsets.ModelViewSet):
    queryset = AssetBox.objects.select_related('category', 'parent_box', 'area').prefetch_related('tags', 'photos')
    serializer_class = AssetBoxSerializer


class AssetItemViewSet(AssetAuthMixin, viewsets.ModelViewSet):
    queryset = AssetItem.objects.select_related('category', 'box', 'area').prefetch_related('tags', 'photos')
    serializer_class = AssetItemSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get('q')
        area = self.request.query_params.get('area')
        box = self.request.query_params.get('box')
        category = self.request.query_params.get('category')
        tag = self.request.query_params.get('tag')
        if q:
            qs = qs.filter(name__icontains=q)
        if area:
            qs = qs.filter(area_id=area)
        if box:
            qs = qs.filter(box_id=box)
        if category:
            qs = qs.filter(category_id=category)
        if tag:
            qs = qs.filter(tags__id=tag)
        return qs.distinct()

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser, JSONParser])
    def photos(self, request, pk=None):
        item = self.get_object()
        image = request.FILES.get('image')
        if not image:
            return Response({'detail': 'image file required'}, status=status.HTTP_400_BAD_REQUEST)
        photo = AssetPhoto.objects.create(
            image=image,
            description=request.data.get('description', ''),
            content_type=ContentType.objects.get_for_model(AssetItem),
            object_id=item.pk,
        )
        return Response(AssetPhotoSerializer(photo, context={'request': request}).data, status=status.HTTP_201_CREATED)
