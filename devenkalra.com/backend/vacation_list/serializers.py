from rest_framework import serializers
from .models import VacTag, VacCategory, VacItem, VacList, VacListItem


class VacTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = VacTag
        fields = ['id', 'name', 'created_at', 'modified_on']


class VacCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = VacCategory
        fields = ['id', 'name', 'created_at', 'modified_on']


class VacItemSerializer(serializers.ModelSerializer):
    category_detail = VacCategorySerializer(source='category', read_only=True)
    tags_detail = VacTagSerializer(source='tags', many=True, read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=VacCategory.objects.all(),
        source='category',
        allow_null=True,
        required=False,
        write_only=True,
    )
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=VacTag.objects.all(),
        source='tags',
        many=True,
        required=False,
        write_only=True,
    )

    class Meta:
        model = VacItem
        fields = [
            'id', 'name', 'name_group', 'description',
            'category', 'category_id', 'category_detail',
            'tags', 'tag_ids', 'tags_detail',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['category', 'tags']


class VacListItemSerializer(serializers.ModelSerializer):
    item_detail = VacItemSerializer(source='item', read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=VacItem.objects.all(),
        source='item',
        write_only=True,
    )
    in_list_id = serializers.PrimaryKeyRelatedField(
        queryset=VacList.objects.all(),
        source='in_list',
        write_only=True,
        required=False,
    )

    class Meta:
        model = VacListItem
        fields = [
            'id', 'item', 'item_id', 'item_detail',
            'need', 'done', 'in_list', 'in_list_id',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['item', 'in_list']


class VacListSerializer(serializers.ModelSerializer):
    initial_tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=VacTag.objects.all(),
        source='initial_tags',
        many=True,
        required=False,
    )
    initial_tags_detail = VacTagSerializer(source='initial_tags', many=True, read_only=True)
    item_count = serializers.IntegerField(source='list_items.count', read_only=True)

    class Meta:
        model = VacList
        fields = [
            'id', 'name', 'initial_tags', 'initial_tag_ids', 'initial_tags_detail',
            'item_count', 'created_at', 'modified_on',
        ]
        read_only_fields = ['initial_tags']
