from rest_framework import serializers
from .models import (
    AssetPhoto, AssetCategory, AssetTag, AssetArea, AssetItem,
)


class AssetCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetCategory
        fields = ['id', 'name', 'description', 'created_at', 'modified_at']


class AssetTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetTag
        fields = ['id', 'name', 'created_at', 'modified_at']


class AssetPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetPhoto
        fields = [
            'id', 'image', 'description', 'sort_order',
            'content_type', 'object_id',
            'created_at', 'modified_at',
        ]
        read_only_fields = ['content_type', 'object_id', 'sort_order']


class AssetBaseFieldsMixin(serializers.ModelSerializer):
    category_detail = AssetCategorySerializer(source='category', read_only=True)
    tags_detail = AssetTagSerializer(source='tags', many=True, read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=AssetCategory.objects.all(),
        source='category',
        allow_null=True,
        required=False,
        write_only=True,
    )
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=AssetTag.objects.all(),
        source='tags',
        many=True,
        required=False,
        write_only=True,
    )
    photos = AssetPhotoSerializer(many=True, read_only=True)
    full_path = serializers.SerializerMethodField()

    def get_full_path(self, obj):
        if hasattr(obj, 'full_path'):
            return obj.full_path()
        return obj.name


class AssetAreaSerializer(AssetBaseFieldsMixin):
    parent_area_id = serializers.PrimaryKeyRelatedField(
        queryset=AssetArea.objects.all(),
        source='parent_area',
        allow_null=True,
        required=False,
        write_only=True,
    )
    descendant_container_count = serializers.SerializerMethodField()
    descendant_item_count = serializers.SerializerMethodField()

    class Meta:
        model = AssetArea
        fields = [
            'id', 'name', 'description',
            'category', 'category_id', 'category_detail',
            'tags', 'tag_ids', 'tags_detail',
            'locator_code', 'locator_type',
            'parent_area', 'parent_area_id',
            'photos', 'full_path',
            'descendant_container_count', 'descendant_item_count',
            'created_at', 'modified_at',
        ]
        read_only_fields = [
            'category', 'tags', 'parent_area',
            'descendant_container_count', 'descendant_item_count',
        ]

    def _area_count(self, obj, key):
        counts = self.context.get('area_counts')
        if counts is None:
            from .counts import compute_area_descendant_counts
            counts = compute_area_descendant_counts()
            self.context['area_counts'] = counts
        return counts.get(obj.id, {}).get(key, 0)

    def get_descendant_container_count(self, obj):
        return self._area_count(obj, 'containers')

    def get_descendant_item_count(self, obj):
        return self._area_count(obj, 'items')


class AssetItemSerializer(AssetBaseFieldsMixin):
    area_id = serializers.PrimaryKeyRelatedField(
        queryset=AssetArea.objects.all(),
        source='area',
        allow_null=True,
        required=False,
        write_only=True,
    )

    class Meta:
        model = AssetItem
        fields = [
            'id', 'name', 'description',
            'category', 'category_id', 'category_detail',
            'tags', 'tag_ids', 'tags_detail',
            'locator_code', 'locator_type',
            'area', 'area_id',
            'photos', 'full_path',
            'created_at', 'modified_at',
        ]
        read_only_fields = ['category', 'tags', 'area']
