from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication

from .models import VacTag, VacCategory, VacItem, VacList, VacListItem
from .serializers import (
    VacTagSerializer, VacCategorySerializer, VacItemSerializer,
    VacListSerializer, VacListItemSerializer,
)


class VacAuthMixin:
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]


class VacTagViewSet(VacAuthMixin, viewsets.ModelViewSet):
    queryset = VacTag.objects.all()
    serializer_class = VacTagSerializer


class VacCategoryViewSet(VacAuthMixin, viewsets.ModelViewSet):
    queryset = VacCategory.objects.all()
    serializer_class = VacCategorySerializer


class VacItemViewSet(VacAuthMixin, viewsets.ModelViewSet):
    queryset = VacItem.objects.select_related('category').prefetch_related('tags').all()
    serializer_class = VacItemSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        tag = self.request.query_params.get('tag')
        category = self.request.query_params.get('category')
        q = self.request.query_params.get('q')
        if tag:
            qs = qs.filter(tags__id=tag)
        if category:
            qs = qs.filter(category_id=category)
        if q:
            qs = qs.filter(name__icontains=q)
        return qs.distinct()


class VacListViewSet(VacAuthMixin, viewsets.ModelViewSet):
    queryset = VacList.objects.prefetch_related('initial_tags').all()
    serializer_class = VacListSerializer

    def perform_create(self, serializer):
        vac_list = serializer.save()
        if vac_list.initial_tags.exists():
            vac_list.seed_from_initial_tags()

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
        return Response(VacListItemSerializer(qs, many=True).data)

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


class VacListItemViewSet(VacAuthMixin, viewsets.ModelViewSet):
    queryset = VacListItem.objects.select_related('item', 'in_list').all()
    serializer_class = VacListItemSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        list_id = self.request.query_params.get('list')
        if list_id:
            qs = qs.filter(in_list_id=list_id)
        return qs
