from rest_framework import serializers
from .models import VacTag, VacCategory, VacItem, VacList, VacListItem


def _request_user(serializer):
    request = serializer.context.get('request')
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return user
    return None


def _set_pk_queryset(field, qs):
    field.queryset = qs
    child = getattr(field, 'child_relation', None)
    if child is not None:
        child.queryset = qs


class VacTagSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = VacTag
        fields = ['id', 'user', 'name', 'created_at', 'modified_on']


class VacCategorySerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = VacCategory
        fields = ['id', 'user', 'name', 'created_at', 'modified_on']


class VacItemSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    category_detail = VacCategorySerializer(source='category', read_only=True)
    tags_detail = VacTagSerializer(source='tags', many=True, read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=VacCategory.objects.none(),
        source='category',
        allow_null=True,
        required=False,
        write_only=True,
    )
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=VacTag.objects.none(),
        source='tags',
        many=True,
        required=False,
        write_only=True,
    )

    class Meta:
        model = VacItem
        fields = [
            'id', 'user', 'name', 'name_group', 'description',
            'category', 'category_id', 'category_detail',
            'tags', 'tag_ids', 'tags_detail',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['category', 'tags']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        cats = VacCategory.objects.filter(user=user) if user else VacCategory.objects.none()
        tags = VacTag.objects.filter(user=user) if user else VacTag.objects.none()
        _set_pk_queryset(self.fields['category_id'], cats)
        _set_pk_queryset(self.fields['tag_ids'], tags)


class VacListItemSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    item_detail = VacItemSerializer(source='item', read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=VacItem.objects.none(),
        source='item',
        write_only=True,
    )
    in_list_id = serializers.PrimaryKeyRelatedField(
        queryset=VacList.objects.none(),
        source='in_list',
        write_only=True,
        required=False,
    )

    class Meta:
        model = VacListItem
        fields = [
            'id', 'user', 'item', 'item_id', 'item_detail',
            'need', 'done', 'in_list', 'in_list_id',
            'created_at', 'modified_on',
        ]
        read_only_fields = ['item', 'in_list']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        items = VacItem.objects.filter(user=user) if user else VacItem.objects.none()
        lists = VacList.objects.filter(user=user) if user else VacList.objects.none()
        _set_pk_queryset(self.fields['item_id'], items)
        _set_pk_queryset(self.fields['in_list_id'], lists)


class VacListSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    initial_tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=VacTag.objects.none(),
        source='initial_tags',
        many=True,
        required=False,
    )
    initial_tags_detail = VacTagSerializer(source='initial_tags', many=True, read_only=True)
    item_count = serializers.IntegerField(source='list_items.count', read_only=True)
    # Create-only population options (not stored on the model)
    populate = serializers.ChoiceField(
        choices=['blank', 'all_items', 'copy'],
        required=False,
        write_only=True,
        default='blank',
    )
    copy_from_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = VacList
        fields = [
            'id', 'user', 'name', 'is_archived',
            'initial_tags', 'initial_tag_ids', 'initial_tags_detail',
            'item_count', 'created_at', 'modified_on',
            'populate', 'copy_from_id',
        ]
        read_only_fields = ['initial_tags']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = _request_user(self)
        tags = VacTag.objects.filter(user=user) if user else VacTag.objects.none()
        _set_pk_queryset(self.fields['initial_tag_ids'], tags)
