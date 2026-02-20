"""Food app serializers."""

from django.db.models import Q
from rest_framework import serializers
from django.contrib.auth.models import User
from people.models import get_user_display_name
from .models import FoodSpot, Food, FoodSpotList, FoodList, Media, Review


class MediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Media
        fields = ['id', 'photo', 'video', 'youtube_url', 'created_at', 'modified_at']
        read_only_fields = ['id', 'created_at', 'modified_at']


class ReviewSerializer(serializers.ModelSerializer):
    added_by_username = serializers.SerializerMethodField()

    def get_added_by_username(self, obj):
        return get_user_display_name(obj.added_by)

    class Meta:
        model = Review
        fields = ['id', 'added_by', 'added_by_username', 'rating', 'note', 'created_at', 'modified_at']
        read_only_fields = ['id', 'added_by', 'created_at', 'modified_at']


class FoodSpotListSerializer(serializers.ModelSerializer):
    """Light serializer for list views."""
    added_by_username = serializers.SerializerMethodField()

    def get_added_by_username(self, obj):
        return get_user_display_name(obj.added_by)
    food_count = serializers.SerializerMethodField()
    foods = serializers.SerializerMethodField()

    class Meta:
        model = FoodSpot
        fields = ['id', 'name', 'locations', 'description', 'tags', 'photos', 'attachments', 'urls',
                  'added_by', 'added_by_username', 'food_count', 'foods', 'created_at', 'modified_at']

    def get_food_count(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.foods.filter(Q(private=False) | Q(added_by=request.user)).count()
        return obj.foods.filter(private=False).count()

    def get_foods(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            foods = obj.foods.filter(Q(private=False) | Q(added_by=request.user)).order_by('name')
        else:
            foods = obj.foods.filter(private=False).order_by('name')
        return [{'id': f.id, 'name': f.name, 'description': f.description} for f in foods]


class FoodSpotDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested foods, media, reviews."""
    added_by_username = serializers.SerializerMethodField()

    def get_added_by_username(self, obj):
        return get_user_display_name(obj.added_by)
    foods = serializers.SerializerMethodField()
    media = MediaSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)

    class Meta:
        model = FoodSpot
        fields = ['id', 'name', 'locations', 'description', 'tags', 'photos', 'attachments', 'urls',
                  'added_by', 'added_by_username', 'foods', 'media', 'reviews', 'created_at', 'modified_at']

    def get_foods(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            foods = obj.foods.filter(Q(private=False) | Q(added_by=request.user)).order_by('name')
        else:
            foods = obj.foods.filter(private=False).order_by('name')
        return FoodListSerializer(foods, many=True).data


class FoodSpotWriteSerializer(serializers.ModelSerializer):
    foods = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
        write_only=True,
    )

    class Meta:
        model = FoodSpot
        fields = ['id', 'name', 'locations', 'description', 'tags', 'photos', 'attachments', 'urls',
                  'foods', 'private', 'created_at', 'modified_at']
        read_only_fields = ['id', 'created_at', 'modified_at']

    def _get_allowed_food_ids(self, instance=None):
        """Return set of food IDs the user may assign: visible foods + foods already on this spot."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return set()
        allowed = set(
            Food.objects.filter(Q(private=False) | Q(added_by=request.user)).values_list('id', flat=True)
        )
        if instance:
            allowed |= set(instance.foods.values_list('id', flat=True))
        return allowed

    def validate_foods(self, value):
        instance = self.instance
        allowed = self._get_allowed_food_ids(instance)
        invalid = [str(fid) for fid in value if fid not in allowed]
        if invalid:
            raise serializers.ValidationError(
                f"Food(s) not found or not allowed: {', '.join(invalid)}"
            )
        return value

    def create(self, validated_data):
        foods_ids = validated_data.pop('foods', [])
        instance = super().create(validated_data)
        if foods_ids:
            instance.foods.set(Food.objects.filter(id__in=foods_ids))
        return instance

    def update(self, instance, validated_data):
        foods_ids = validated_data.pop('foods', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if foods_ids is not None:
            instance.foods.set(Food.objects.filter(id__in=foods_ids))
        return instance


class FoodListSerializer(serializers.ModelSerializer):
    """Light serializer for list views."""
    added_by_username = serializers.SerializerMethodField()

    def get_added_by_username(self, obj):
        return get_user_display_name(obj.added_by)
    served_at_names = serializers.SerializerMethodField()

    class Meta:
        model = Food
        fields = ['id', 'name', 'description', 'alsocalled', 'tags', 'photos', 'attachments', 'urls',
                  'added_by', 'added_by_username', 'served_at_names', 'created_at', 'modified_at']

    def get_served_at_names(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            spots = obj.served_at.filter(Q(private=False) | Q(added_by=request.user))
        else:
            spots = obj.served_at.filter(private=False)
        return [s.name for s in spots]


class FoodDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested media, reviews, served_at."""
    added_by_username = serializers.SerializerMethodField()

    def get_added_by_username(self, obj):
        return get_user_display_name(obj.added_by)
    media = MediaSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    served_at = serializers.SerializerMethodField()

    class Meta:
        model = Food
        fields = ['id', 'name', 'description', 'alsocalled', 'tags', 'photos', 'attachments', 'urls',
                  'added_by', 'added_by_username', 'served_at', 'media', 'reviews', 'created_at', 'modified_at']

    def get_served_at(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            spots = obj.served_at.filter(Q(private=False) | Q(added_by=request.user))
        else:
            spots = obj.served_at.filter(private=False)
        return FoodSpotListSerializer(spots, many=True, context=self.context).data


class FoodWriteSerializer(serializers.ModelSerializer):
    served_at = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
        write_only=True,
    )

    class Meta:
        model = Food
        fields = ['id', 'name', 'description', 'alsocalled', 'tags', 'served_at', 'photos', 'attachments', 'urls',
                  'private', 'created_at', 'modified_at']
        read_only_fields = ['id', 'created_at', 'modified_at']

    def _get_allowed_spot_ids(self, instance=None):
        """Return set of spot IDs the user may assign: visible spots + spots already on this food."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return set()
        allowed = set(
            FoodSpot.objects.filter(Q(private=False) | Q(added_by=request.user)).values_list('id', flat=True)
        )
        if instance:
            allowed |= set(instance.served_at.values_list('id', flat=True))
        return allowed

    def validate_served_at(self, value):
        instance = self.instance
        allowed = self._get_allowed_spot_ids(instance)
        invalid = [str(sid) for sid in value if sid not in allowed]
        if invalid:
            raise serializers.ValidationError(
                f"Spot(s) not found or not allowed: {', '.join(invalid)}"
            )
        return value

    def create(self, validated_data):
        served_at_ids = validated_data.pop('served_at', [])
        instance = super().create(validated_data)
        if served_at_ids:
            instance.served_at.set(FoodSpot.objects.filter(id__in=served_at_ids))
        return instance

    def update(self, instance, validated_data):
        served_at_ids = validated_data.pop('served_at', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if served_at_ids is not None:
            instance.served_at.set(FoodSpot.objects.filter(id__in=served_at_ids))
        return instance


# User-created lists of spots/foods
class SpotListSerializer(serializers.ModelSerializer):
    """Serializer for FoodSpotList (user's list of spots)."""
    spots = serializers.SerializerMethodField()

    class Meta:
        model = FoodSpotList
        fields = ['id', 'name', 'spots', 'created_at', 'modified_at']
        read_only_fields = ['id', 'created_at', 'modified_at']

    def get_spots(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            spots = obj.spots.filter(Q(private=False) | Q(added_by=request.user)).order_by('name')
        else:
            spots = obj.spots.filter(private=False).order_by('name')
        return [{'id': s.id, 'name': s.name} for s in spots]


class SpotListWriteSerializer(serializers.ModelSerializer):
    spots = serializers.PrimaryKeyRelatedField(many=True, queryset=FoodSpot.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            self.fields['spots'].queryset = FoodSpot.objects.filter(Q(private=False) | Q(added_by=request.user))

    class Meta:
        model = FoodSpotList
        fields = ['id', 'name', 'spots', 'created_at', 'modified_at']
        read_only_fields = ['id', 'created_at', 'modified_at']


class FoodItemListSerializer(serializers.ModelSerializer):
    """Serializer for FoodList (user's list of foods)."""
    foods = serializers.SerializerMethodField()

    class Meta:
        model = FoodList
        fields = ['id', 'name', 'foods', 'created_at', 'modified_at']
        read_only_fields = ['id', 'created_at', 'modified_at']

    def get_foods(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            foods = obj.foods.filter(Q(private=False) | Q(added_by=request.user)).order_by('name')
        else:
            foods = obj.foods.filter(private=False).order_by('name')
        return [{'id': f.id, 'name': f.name} for f in foods]


class FoodItemListWriteSerializer(serializers.ModelSerializer):
    foods = serializers.PrimaryKeyRelatedField(many=True, queryset=Food.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            self.fields['foods'].queryset = Food.objects.filter(Q(private=False) | Q(added_by=request.user))

    class Meta:
        model = FoodList
        fields = ['id', 'name', 'foods', 'created_at', 'modified_at']
        read_only_fields = ['id', 'created_at', 'modified_at']
