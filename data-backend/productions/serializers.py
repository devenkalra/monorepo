from rest_framework import serializers

from .constants import ASSET_STATUS_TODO, PRODUCTION_TYPES
from .models import Production, ProductionAssetStatus, Scene, SceneAsset
from .timing import (
    TimecodeError,
    apply_duration_edit,
    apply_end_edit,
    asset_name_key,
    format_timecode,
    parse_timecode,
    recompute_scene_times,
    teleprompter_text,
)


def _request_user(serializer):
    request = serializer.context.get('request')
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return user
    return None


def _clean_tags(value):
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(',')]
        return [part for part in parts if part]
    if not isinstance(value, list):
        raise serializers.ValidationError('Tags must be a list of strings.')
    tags = []
    for item in value:
        name = str(item).strip()
        if name:
            tags.append(name)
    return tags


def _clean_assets(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise serializers.ValidationError('Assets must be a list of names.')
    names = []
    for item in value:
        if isinstance(item, dict):
            name = str(item.get('name') or '').strip()
        else:
            name = str(item).strip()
        if name:
            names.append(name)
    return names


def replace_scene_assets(scene, names):
    scene.assets.all().delete()
    SceneAsset.objects.bulk_create(
        [SceneAsset(scene=scene, name=name, sort_order=index) for index, name in enumerate(names)]
    )


def persist_scene_times(production):
    scenes = list(production.scenes.order_by('sort_order', 'id'))
    recompute_scene_times(scenes)
    if scenes:
        Scene.objects.bulk_update(scenes, ['start_seconds', 'duration_seconds'])
    return scenes


def scene_payload(scene):
    assets = [asset.name for asset in scene.assets.all()]
    return {
        'id': scene.id,
        'sort_order': scene.sort_order,
        'title': scene.title,
        'scene_type': scene.scene_type,
        'start_seconds': str(scene.start_seconds),
        'duration_seconds': str(scene.duration_seconds),
        'end_seconds': str(scene.end_seconds),
        'start': format_timecode(scene.start_seconds),
        'duration': format_timecode(scene.duration_seconds),
        'end': format_timecode(scene.end_seconds),
        'visuals': scene.visuals,
        'voiceover': scene.voiceover,
        'music': scene.music,
        'fx_cues': scene.fx_cues,
        'notes': scene.notes,
        'assets': assets,
    }


def build_asset_todos(production, scenes=None):
    if scenes is None:
        scenes = list(production.scenes.prefetch_related('assets').order_by('sort_order', 'id'))
    grouped = {}
    for scene in scenes:
        for asset in scene.assets.all():
            key = asset_name_key(asset.name)
            if not key:
                continue
            row = grouped.setdefault(
                key,
                {'name': asset.name, 'scenes': []},
            )
            row['scenes'].append({
                'id': scene.id,
                'title': scene.title,
                'scene_type': scene.scene_type,
                'sort_order': scene.sort_order,
            })
    statuses = {row.name_key: row for row in production.asset_statuses.all()}
    todos = []
    for key, row in grouped.items():
        status = statuses.get(key)
        todos.append({
            'name': row['name'],
            'name_key': key,
            'status': status.status if status else ASSET_STATUS_TODO,
            'scenes': row['scenes'],
        })
    return todos


class ProductionListSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source='production_type')
    type_label = serializers.SerializerMethodField()
    scene_count = serializers.IntegerField(read_only=True)
    total_duration = serializers.SerializerMethodField()

    class Meta:
        model = Production
        fields = [
            'id', 'title', 'subtitle', 'type', 'type_label', 'description', 'tags',
            'is_archived', 'scene_count', 'total_duration', 'created_at', 'modified_on',
        ]

    def get_type_label(self, obj):
        return obj.get_production_type_display()

    def get_total_duration(self, obj):
        total = getattr(obj, 'total_duration', None)
        if total is None:
            return '0:00'
        return format_timecode(total)


class ProductionSerializer(serializers.ModelSerializer):
    type = serializers.ChoiceField(choices=PRODUCTION_TYPES, source='production_type')
    type_label = serializers.SerializerMethodField()
    scenes = serializers.SerializerMethodField()
    asset_todos = serializers.SerializerMethodField()
    teleprompter = serializers.SerializerMethodField()
    total_duration = serializers.SerializerMethodField()

    class Meta:
        model = Production
        fields = [
            'id', 'title', 'subtitle', 'type', 'type_label', 'description', 'tags',
            'is_archived', 'scenes', 'asset_todos', 'teleprompter', 'total_duration',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['is_archived']

    def get_type_label(self, obj):
        return obj.get_production_type_display()

    def get_scenes(self, obj):
        scenes = obj.scenes.all()
        if not any(hasattr(scene, '_prefetched_objects_cache') and 'assets' in scene._prefetched_objects_cache for scene in scenes):
            scenes = obj.scenes.prefetch_related('assets').all()
        return [scene_payload(scene) for scene in scenes]

    def get_asset_todos(self, obj):
        scenes = list(obj.scenes.all())
        return build_asset_todos(obj, scenes)

    def get_teleprompter(self, obj):
        return teleprompter_text(obj.scenes.all())

    def get_total_duration(self, obj):
        last = obj.scenes.order_by('sort_order', 'id').last()
        if not last:
            return '0:00'
        return format_timecode(last.end_seconds)

    def validate_tags(self, value):
        return _clean_tags(value)

    def validate_title(self, value):
        title = (value or '').strip()
        if not title:
            raise serializers.ValidationError('Title is required.')
        return title


class SceneSerializer(serializers.ModelSerializer):
    production_id = serializers.PrimaryKeyRelatedField(
        queryset=Production.objects.none(),
        source='production',
    )
    assets = serializers.JSONField(required=False)
    start = serializers.CharField(required=False, allow_blank=True)
    duration = serializers.CharField(required=False, allow_blank=True)
    end = serializers.CharField(required=False, allow_blank=True)
    start_seconds = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    duration_seconds = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    end_seconds = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    after_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = Scene
        fields = [
            'id', 'production_id', 'sort_order', 'title', 'scene_type',
            'start', 'duration', 'end',
            'start_seconds', 'duration_seconds', 'end_seconds',
            'visuals', 'voiceover', 'music', 'fx_cues', 'notes', 'assets',
            'after_id',
        ]
        read_only_fields = ['sort_order']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        qs = Production.objects.filter(user=user) if user else Production.objects.none()
        self.fields['production_id'].queryset = qs

    def to_representation(self, instance):
        return scene_payload(instance)

    def validate(self, attrs):
        assets = attrs.pop('assets', serializers.empty)
        if assets is not serializers.empty:
            attrs['asset_names'] = _clean_assets(assets)

        after_id = attrs.pop('after_id', None)
        if after_id is not None:
            attrs['after_id'] = after_id

        duration_raw = attrs.pop('duration', None)
        end_raw = attrs.pop('end', None)
        attrs.pop('start', None)
        duration_seconds = attrs.pop('duration_seconds', None)
        end_seconds = attrs.pop('end_seconds', None)
        attrs.pop('start_seconds', None)

        try:
            if duration_raw not in (None, ''):
                attrs['parsed_duration'] = parse_timecode(duration_raw)
            elif duration_seconds is not None:
                attrs['parsed_duration'] = parse_timecode(duration_seconds)
            if end_raw not in (None, ''):
                attrs['parsed_end'] = parse_timecode(end_raw)
            elif end_seconds is not None:
                attrs['parsed_end'] = parse_timecode(end_seconds)
        except TimecodeError as exc:
            raise serializers.ValidationError({'detail': str(exc)}) from exc
        return attrs

    def create(self, validated_data):
        asset_names = validated_data.pop('asset_names', [])
        parsed_duration = validated_data.pop('parsed_duration', None)
        validated_data.pop('parsed_end', None)
        after_id = validated_data.pop('after_id', None)
        production = validated_data['production']
        if parsed_duration is not None:
            validated_data['duration_seconds'] = parsed_duration
        scenes = list(production.scenes.order_by('sort_order', 'id'))
        after = next((row for row in scenes if row.id == after_id), None) if after_id else None
        if after is not None:
            insert_at = after.sort_order + 1
            later = [row for row in scenes if row.sort_order >= insert_at]
            for row in later:
                row.sort_order += 1
            if later:
                Scene.objects.bulk_update(later, ['sort_order'])
            validated_data['sort_order'] = insert_at
        else:
            last = scenes[-1] if scenes else None
            validated_data['sort_order'] = (last.sort_order + 1) if last else 0
        scene = Scene.objects.create(**validated_data)
        replace_scene_assets(scene, asset_names)
        persist_scene_times(production)
        scene.refresh_from_db()
        return scene

    def update(self, instance, validated_data):
        asset_names = validated_data.pop('asset_names', None)
        parsed_duration = validated_data.pop('parsed_duration', None)
        parsed_end = validated_data.pop('parsed_end', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if asset_names is not None:
            replace_scene_assets(instance, asset_names)
        scenes = list(instance.production.scenes.order_by('sort_order', 'id'))
        index = next(i for i, scene in enumerate(scenes) if scene.id == instance.id)
        try:
            if parsed_end is not None:
                apply_end_edit(scenes, index, parsed_end)
            elif parsed_duration is not None:
                apply_duration_edit(scenes, index, parsed_duration)
            else:
                recompute_scene_times(scenes)
        except TimecodeError as exc:
            raise serializers.ValidationError({'detail': str(exc)}) from exc
        Scene.objects.bulk_update(scenes, ['start_seconds', 'duration_seconds'])
        instance.refresh_from_db()
        return instance
