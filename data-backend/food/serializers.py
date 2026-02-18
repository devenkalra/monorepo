"""Food app serializers."""

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import FoodSpot, Food, Media, Review


class MediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Media
        fields = ['id', 'photo', 'video', 'youtube_url', 'created_at', 'modified_at']
        read_only_fields = ['id', 'created_at', 'modified_at']


class ReviewSerializer(serializers.ModelSerializer):
    added_by_username = serializers.CharField(source='added_by.username', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'added_by', 'added_by_username', 'rating', 'note', 'created_at', 'modified_at']
        read_only_fields = ['id', 'added_by', 'created_at', 'modified_at']


class FoodSpotListSerializer(serializers.ModelSerializer):
    """Light serializer for list views."""
    added_by_username = serializers.CharField(source='added_by.username', read_only=True)
    food_count = serializers.SerializerMethodField()
    foods = serializers.SerializerMethodField()

    class Meta:
        model = FoodSpot
        fields = ['id', 'name', 'locations', 'description', 'tags', 'photos', 'attachments', 'urls',
                  'added_by', 'added_by_username', 'food_count', 'foods', 'created_at', 'modified_at']

    def get_food_count(self, obj):
        return obj.foods.count()

    def get_foods(self, obj):
        return [{'id': f.id, 'name': f.name, 'description': f.description}
                for f in obj.foods.all().order_by('name')]


class FoodSpotDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested foods, media, reviews."""
    added_by_username = serializers.CharField(source='added_by.username', read_only=True)
    foods = serializers.SerializerMethodField()
    media = MediaSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)

    class Meta:
        model = FoodSpot
        fields = ['id', 'name', 'locations', 'description', 'tags', 'photos', 'attachments', 'urls',
                  'added_by', 'added_by_username', 'foods', 'media', 'reviews', 'created_at', 'modified_at']

    def get_foods(self, obj):
        foods = obj.foods.all().order_by('name')
        return FoodListSerializer(foods, many=True).data


class FoodSpotWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodSpot
        fields = ['id', 'name', 'locations', 'description', 'tags', 'photos', 'attachments', 'urls',
                  'created_at', 'modified_at']
        read_only_fields = ['id', 'created_at', 'modified_at']


class FoodListSerializer(serializers.ModelSerializer):
    """Light serializer for list views."""
    added_by_username = serializers.CharField(source='added_by.username', read_only=True)
    served_at_names = serializers.SerializerMethodField()

    class Meta:
        model = Food
        fields = ['id', 'name', 'description', 'alsocalled', 'tags', 'photos', 'attachments', 'urls',
                  'added_by', 'added_by_username', 'served_at_names', 'created_at', 'modified_at']

    def get_served_at_names(self, obj):
        return [s.name for s in obj.served_at.all()]


class FoodDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested media, reviews, served_at."""
    added_by_username = serializers.CharField(source='added_by.username', read_only=True)
    media = MediaSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    served_at = FoodSpotListSerializer(many=True, read_only=True)

    class Meta:
        model = Food
        fields = ['id', 'name', 'description', 'alsocalled', 'tags', 'photos', 'attachments', 'urls',
                  'added_by', 'added_by_username', 'served_at', 'media', 'reviews', 'created_at', 'modified_at']


class FoodWriteSerializer(serializers.ModelSerializer):
    served_at = serializers.PrimaryKeyRelatedField(many=True, queryset=FoodSpot.objects.all(), required=False)

    class Meta:
        model = Food
        fields = ['id', 'name', 'description', 'alsocalled', 'tags', 'served_at', 'photos', 'attachments', 'urls',
                  'created_at', 'modified_at']
        read_only_fields = ['id', 'created_at', 'modified_at']
