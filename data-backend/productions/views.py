from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .constants import ASSET_STATUSES, ASSET_STATUS_TODO, PRODUCTION_TYPES, SCENE_TYPE_PRESETS
from .generate import GenerateError, generate_production
from .llm import llm_available
from .models import Production, ProductionAssetStatus, Scene, SceneAsset
from .serializers import (
    ProductionListSerializer,
    ProductionSerializer,
    SceneSerializer,
    persist_scene_times,
    scene_payload,
)
from .timing import asset_name_key, teleprompter_text
from .transfer import TransferError, export_document, export_filename, import_productions as load_productions


class UserScopedMixin:
    def get_queryset(self):
        qs = super().get_queryset()
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return qs.none()
        return qs.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ProductionViewSet(UserScopedMixin, viewsets.ModelViewSet):
    queryset = Production.objects.all()
    pagination_class = None

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductionListSerializer
        return ProductionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'list':
            qs = qs.annotate(
                scene_count=Count('scenes'),
                total_duration=Sum('scenes__duration_seconds'),
            )
            show_archived = str(self.request.query_params.get('archived', '')).lower() in (
                '1', 'true', 'yes',
            )
            if not show_archived:
                qs = qs.filter(is_archived=False)
            production_type = self.request.query_params.get('type')
            if production_type:
                qs = qs.filter(production_type=production_type)
            search = (self.request.query_params.get('q') or '').strip()
            if search:
                qs = qs.filter(
                    Q(title__icontains=search)
                    | Q(subtitle__icontains=search)
                    | Q(description__icontains=search)
                    | Q(tags__icontains=search)
                )
            return qs
        return qs.prefetch_related(
            Prefetch('scenes', queryset=Scene.objects.prefetch_related('assets').order_by('sort_order', 'id')),
            'asset_statuses',
        )

    def _export_response(self, productions, filename):
        payload = export_document(productions)
        response = Response(payload)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @action(detail=False, methods=['get'])
    def meta(self, request):
        return Response({
            'types': [{'value': value, 'label': label} for value, label in PRODUCTION_TYPES],
            'scene_types': SCENE_TYPE_PRESETS,
            'asset_statuses': [{'value': value, 'label': label} for value, label in ASSET_STATUSES],
        })

    @action(detail=False, methods=['post'])
    def generate(self, request):
        prompt = (request.data.get('prompt') or '').strip()
        if not prompt:
            return Response({'detail': 'Prompt is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not llm_available():
            return Response(
                {'detail': 'No LLM configured. Set OPENAI_API_KEY or LOCALAI_URL.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        production_type = (request.data.get('type') or '').strip()
        try:
            production = generate_production(
                user=request.user,
                prompt=prompt,
                production_type=production_type,
            )
        except GenerateError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        production = self.get_queryset().get(pk=production.pk)
        return Response(
            ProductionSerializer(production, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['get'])
    def export(self, request):
        productions = list(self.get_queryset())
        return self._export_response(productions, export_filename())

    @action(detail=True, methods=['get'], url_path='export')
    def export_one(self, request, pk=None):
        production = self.get_object()
        return self._export_response([production], export_filename(production))

    @action(detail=False, methods=['post'], url_path='import')
    def import_productions(self, request):
        try:
            created = load_productions(request.user, request.data)
        except TransferError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        ids = [row.pk for row in created]
        productions = list(self.get_queryset().filter(pk__in=ids))
        productions.sort(key=lambda row: ids.index(row.pk))
        return Response(
            {
                'count': len(productions),
                'productions': ProductionSerializer(productions, many=True, context={'request': request}).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        production = self.get_object()
        production.is_archived = True
        production.save(update_fields=['is_archived', 'modified_on'])
        return Response(ProductionSerializer(production, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        production = self.get_object()
        production.is_archived = False
        production.save(update_fields=['is_archived', 'modified_on'])
        return Response(ProductionSerializer(production, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        source = self.get_object()
        with transaction.atomic():
            dest = Production.objects.create(
                user=request.user,
                title=f'Copy of {source.title}',
                subtitle=source.subtitle,
                production_type=source.production_type,
                description=source.description,
                tags=list(source.tags or []),
                is_archived=False,
            )
            for scene in source.scenes.prefetch_related('assets').order_by('sort_order', 'id'):
                copy = Scene.objects.create(
                    user=request.user,
                    production=dest,
                    sort_order=scene.sort_order,
                    title=scene.title,
                    scene_type=scene.scene_type,
                    start_seconds=scene.start_seconds,
                    duration_seconds=scene.duration_seconds,
                    visuals=scene.visuals,
                    voiceover=scene.voiceover,
                    music=scene.music,
                    fx_cues=scene.fx_cues,
                    notes=scene.notes,
                )
                SceneAsset.objects.bulk_create([
                    SceneAsset(scene=copy, name=asset.name, sort_order=asset.sort_order)
                    for asset in scene.assets.all()
                ])
            ProductionAssetStatus.objects.bulk_create([
                ProductionAssetStatus(
                    production=dest,
                    name_key=row.name_key,
                    display_name=row.display_name,
                    status=row.status,
                )
                for row in source.asset_statuses.all()
            ])
        dest = self.get_queryset().get(pk=dest.pk)
        return Response(ProductionSerializer(dest, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def teleprompter(self, request, pk=None):
        production = self.get_object()
        text = teleprompter_text(production.scenes.all())
        return Response({'text': text})

    @action(detail=True, methods=['patch'], url_path='assets')
    def assets(self, request, pk=None):
        production = self.get_object()
        name = (request.data.get('name') or '').strip()
        key = asset_name_key(name)
        status_value = request.data.get('status') or ASSET_STATUS_TODO
        allowed = {value for value, _label in ASSET_STATUSES}
        if not key:
            return Response({'detail': 'Asset name is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if status_value not in allowed:
            return Response({'detail': 'Invalid asset status.'}, status=status.HTTP_400_BAD_REQUEST)
        row, _created = ProductionAssetStatus.objects.update_or_create(
            production=production,
            name_key=key,
            defaults={'display_name': name, 'status': status_value},
        )
        return Response({
            'name': row.display_name,
            'name_key': row.name_key,
            'status': row.status,
        })


class SceneViewSet(UserScopedMixin, viewsets.ModelViewSet):
    queryset = Scene.objects.all()
    serializer_class = SceneSerializer
    pagination_class = None

    def get_queryset(self):
        return super().get_queryset().select_related('production').prefetch_related('assets')

    def _renumber(self, production):
        scenes = list(production.scenes.order_by('sort_order', 'id'))
        for index, scene in enumerate(scenes):
            if scene.sort_order != index:
                scene.sort_order = index
        if scenes:
            Scene.objects.bulk_update(scenes, ['sort_order'])
        persist_scene_times(production)

    @action(detail=True, methods=['post'])
    def move(self, request, pk=None):
        scene = self.get_object()
        direction = request.data.get('direction')
        scenes = list(scene.production.scenes.order_by('sort_order', 'id'))
        index = next(i for i, row in enumerate(scenes) if row.id == scene.id)
        if direction == 'up' and index > 0:
            scenes[index], scenes[index - 1] = scenes[index - 1], scenes[index]
        elif direction == 'down' and index < len(scenes) - 1:
            scenes[index], scenes[index + 1] = scenes[index + 1], scenes[index]
        else:
            return Response(scene_payload(scene))
        for i, row in enumerate(scenes):
            row.sort_order = i
        Scene.objects.bulk_update(scenes, ['sort_order'])
        persist_scene_times(scene.production)
        scene.refresh_from_db()
        return Response(scene_payload(scene))

    def perform_destroy(self, instance):
        production = instance.production
        instance.delete()
        self._renumber(production)
