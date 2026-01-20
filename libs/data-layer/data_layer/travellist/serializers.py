# listmanager/serializers.py
from rest_framework import serializers
from .models import Item, ListItem, Tag, Category, List

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name"]

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class ItemSerializer(serializers.ModelSerializer):
    # Use PrimaryKeyRelatedField for writing IDs
    # queryset is required so DRF can validate the IDs exist
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), allow_null=True,
                                                  required=False)
    tags = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        many=True,
        required=False
    )
    class Meta:
        model = Item
        fields = ["id", "name", "description", "category", "tags"]

    def to_representation(self, instance):
        """Convert IDs to full objects when sending data to React"""
        rep = super().to_representation(instance)
        rep['category'] = CategorySerializer(instance.category).data
        rep['tags'] = TagSerializer(instance.tags.all(), many=True).data
        return rep

class ItemSerializerX(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Item
        fields = ["id", "name", "description", "category", "tags"]

class ListItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.all(), source="item", write_only=True
    )

    class Meta:
        model = ListItem
        fields = ["id", "item", "item_id", "need", "done", "in_list"]

class ListSerializer(serializers.ModelSerializer):
    class Meta:
        model = List
        fields = ["id", "name", "initial_tags", "created_at", "modified_on"]
