from rest_framework import serializers
from .models import (
    AssetPhoto, AssetCategory, AssetTag, AssetArea, AssetBox, AssetItem,
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
            'id', 'image', 'description',
            'content_type', 'object_id',
            'created_at', 'modified_at',
        ]
        read_only_fields = ['content_type', 'object_id']


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

    class Meta:
        model = AssetArea
        fields = [
            'id', 'name', 'description',
            'category', 'category_id', 'category_detail',
            'tags', 'tag_ids', 'tags_detail',
            'locator_code', 'locator_type',
            'parent_area', 'parent_area_id',
            'photos', 'full_path',
            'created_at', 'modified_at',
        ]
        read_only_fields = ['category', 'tags', 'parent_area']


class AssetBoxSerializer(AssetBaseFieldsMixin):
    parent_box_id = serializers.PrimaryKeyRelatedField(
        queryset=AssetBox.objects.all(),
        source='parent_box',
        allow_null=True,
        required=False,
        write_only=True,
    )
    area_id = serializers.PrimaryKeyRelatedField(
        queryset=AssetArea.objects.all(),
        source='area',
        allow_null=True,
        required=False,
        write_only=True,
    )

    class Meta:
        model = AssetBox
        fields = [
            'id', 'name', 'description',
            'category', 'category_id', 'category_detail',
            'tags', 'tag_ids', 'tags_detail',
            'locator_code', 'locator_type',
            'parent_box', 'parent_box_id',
            'area', 'area_id',
            'photos', 'full_path',
            'created_at', 'modified_at',
        ]
        read_only_fields = ['category', 'tags', 'parent_box', 'area']


class AssetItemSerializer(AssetBaseFieldsMixin):
    box_id = serializers.PrimaryKeyRelatedField(
        queryset=AssetBox.objects.all(),
        source='box',
        allow_null=True,
        required=False,
        write_only=True,
    )
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
            'box', 'box_id', 'area', 'area_id',
            'photos', 'full_path',
            'created_at', 'modified_at',
        ]
        read_only_fields = ['category', 'tags', 'box', 'area']
