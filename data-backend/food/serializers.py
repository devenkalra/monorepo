"""Food app serializers."""

from django.db.models import Q, Avg
from rest_framework import serializers
from django.contrib.auth.models import User
from people.models import get_user_display_name
from .models import FoodSpot, Food, FoodSpotList, FoodList, Media, Review, FoodSpotFoodRating


class MediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Media
        fields = ['id', 'photo', 'video', 'youtube_url', 'created_at', 'modified_at']
        read_only_fields = ['id', 'created_at', 'modified_at']


class ReviewSerializer(serializers.ModelSerializer):
    added_by_username = serializers.SerializerMethodField()

    def get_added_by_username(self, obj):
        return get_user_display_name(obj.added_by)

    def validate_rating(self, value):
        if value is None or value < 1 or value > 5:
            raise serializers.ValidationError('Rating must be between 1 and 5.')
        return value

    class Meta:
        model = Review
        fields = ['id', 'added_by', 'added_by_username', 'rating', 'note', 'food_spot', 'food', 'created_at', 'modified_at']
        read_only_fields = ['id', 'added_by', 'created_at', 'modified_at']


class FoodSpotListSerializer(serializers.ModelSerializer):
    """Light serializer for list views."""
    added_by_username = serializers.SerializerMethodField()
    rating_avg = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()

    def get_added_by_username(self, obj):
        return get_user_display_name(obj.added_by)

    def get_rating_avg(self, obj):
        result = Review.objects.filter(food_spot=obj, food__isnull=True).aggregate(avg=Avg('rating'))
        avg = result['avg']
        return round(avg, 1) if avg is not None else None

    def get_rating_count(self, obj):
        return Review.objects.filter(food_spot=obj, food__isnull=True).count()

    my_rating = serializers.SerializerMethodField()

    def get_my_rating(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            r = Review.objects.filter(food_spot=obj, food__isnull=True, added_by=request.user).first()
            return r.rating if r else None
        return None

    food_count = serializers.SerializerMethodField()
    foods = serializers.SerializerMethodField()
    food_rating_avg = serializers.SerializerMethodField()
    food_rating_count = serializers.SerializerMethodField()

    class Meta:
        model = FoodSpot
        fields = ['id', 'name', 'locations', 'description', 'tags', 'photos', 'attachments', 'urls',
                  'added_by', 'added_by_username', 'rating_avg', 'rating_count', 'my_rating', 'food_count', 'foods',
                  'food_rating_avg', 'food_rating_count', 'created_at', 'modified_at']

    def get_food_rating_avg(self, obj):
        """Average of all non-zero average ratings of foods served at this spot."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            foods = obj.foods.filter(Q(private=False) | Q(added_by=request.user))
        else:
            foods = obj.foods.filter(private=False)
        avgs = []
        for f in foods:
            r = FoodSpotFoodRating.objects.filter(food=f, food_spot=obj).aggregate(avg=Avg('rating'))
            avg_val = r['avg']
            if avg_val is not None and avg_val > 0:
                avgs.append(float(avg_val))
        if avgs:
            return round(sum(avgs) / len(avgs), 1)
        return None

    def get_food_rating_count(self, obj):
        return FoodSpotFoodRating.objects.filter(food_spot=obj).count()

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
        result = []
        for f in foods:
            rating_result = FoodSpotFoodRating.objects.filter(
                food=f, food_spot=obj
            ).aggregate(avg=Avg('rating'))
            rating_avg = rating_result['avg']
            data = {'id': f.id, 'name': f.name, 'description': f.description}
            data['rating_avg'] = round(rating_avg, 1) if rating_avg is not None else None
            result.append(data)
        result.sort(key=lambda x: (x['rating_avg'] is None, -(x['rating_avg'] or 0)))
        return result


class FoodSpotDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested foods, media, reviews."""
    added_by_username = serializers.SerializerMethodField()
    rating_avg = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()

    def get_added_by_username(self, obj):
        return get_user_display_name(obj.added_by)

    def get_rating_avg(self, obj):
        result = Review.objects.filter(food_spot=obj, food__isnull=True).aggregate(avg=Avg('rating'))
        avg = result['avg']
        return round(avg, 1) if avg is not None else None

    def get_rating_count(self, obj):
        return Review.objects.filter(food_spot=obj, food__isnull=True).count()

    my_rating = serializers.SerializerMethodField()

    def get_my_rating(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            r = Review.objects.filter(food_spot=obj, food__isnull=True, added_by=request.user).first()
            return r.rating if r else None
        return None

    foods = serializers.SerializerMethodField()
    media = MediaSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)

    class Meta:
        model = FoodSpot
        fields = ['id', 'name', 'locations', 'description', 'tags', 'photos', 'attachments', 'urls',
                  'added_by', 'added_by_username', 'rating_avg', 'rating_count', 'my_rating', 'foods', 'media', 'reviews',
                  'created_at', 'modified_at']

    def get_foods(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            foods = obj.foods.filter(Q(private=False) | Q(added_by=request.user)).order_by('name')
        else:
            foods = obj.foods.filter(private=False).order_by('name')
        # Include rating for each food at this spot
        result = []
        for f in foods:
            rating_result = FoodSpotFoodRating.objects.filter(
                food=f, food_spot=obj
            ).aggregate(avg=Avg('rating'))
            rating_avg = rating_result['avg']
            rating_count = FoodSpotFoodRating.objects.filter(food=f, food_spot=obj).count()
            data = FoodListSerializer(f, context=self.context).data
            data['rating_avg'] = round(rating_avg, 1) if rating_avg is not None else None
            data['rating_count'] = rating_count
            if request and request.user.is_authenticated:
                my_r = FoodSpotFoodRating.objects.filter(
                    food=f, food_spot=obj, added_by=request.user
                ).first()
                data['my_rating'] = my_r.rating if my_r else None
                data['my_review'] = my_r.note if my_r and my_r.note else None
            else:
                data['my_rating'] = None
                data['my_review'] = None
            # Include all reviews for this food at this spot
            reviews_qs = FoodSpotFoodRating.objects.filter(food=f, food_spot=obj).select_related('added_by').order_by('-modified_at')
            data['reviews'] = [
                {
                    'id': str(r.id),
                    'rating': r.rating,
                    'note': r.note or None,
                    'added_by_username': get_user_display_name(r.added_by),
                    'modified_at': r.modified_at.isoformat() if r.modified_at else None,
                }
                for r in reviews_qs[:20]
            ]
            result.append(data)
        # Sort by average rating descending (foods with no rating last)
        result.sort(key=lambda f: (f['rating_avg'] is None, -(f['rating_avg'] or 0)))
        return result


class FoodSpotFoodRatingSerializer(serializers.ModelSerializer):
    """Serializer for rating/review of a food at a specific spot."""
    added_by_username = serializers.SerializerMethodField()

    def get_added_by_username(self, obj):
        return get_user_display_name(obj.added_by)

    def validate_rating(self, value):
        if value is None or value < 1 or value > 5:
            raise serializers.ValidationError('Rating must be between 1 and 5.')
        return value

    class Meta:
        model = FoodSpotFoodRating
        fields = ['id', 'food', 'food_spot', 'rating', 'note', 'added_by', 'added_by_username', 'created_at', 'modified_at']
        read_only_fields = ['id', 'added_by', 'created_at', 'modified_at']


class FoodSpotFoodRatingWriteSerializer(serializers.ModelSerializer):
    """Write serializer for creating/updating food-at-spot rating/review."""

    def validate_rating(self, value):
        if value is None or value < 1 or value > 5:
            raise serializers.ValidationError('Rating must be between 1 and 5.')
        return value

    class Meta:
        model = FoodSpotFoodRating
        fields = ['food', 'food_spot', 'rating', 'note']

    def validate(self, attrs):
        food = attrs['food']
        food_spot = attrs['food_spot']
        if not food_spot.foods.filter(id=food.id).exists():
            raise serializers.ValidationError(
                {'food': 'This food is not served at the selected spot.'}
            )
        return attrs

    def create(self, validated_data):
        rating, _ = FoodSpotFoodRating.objects.update_or_create(
            food=validated_data['food'],
            food_spot=validated_data['food_spot'],
            added_by=self.context['request'].user,
            defaults={
                'rating': validated_data['rating'],
                'note': validated_data.get('note', ''),
            },
        )
        return rating


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
    served_at_names = serializers.SerializerMethodField()
    rating_avg = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()

    def get_added_by_username(self, obj):
        return get_user_display_name(obj.added_by)

    def get_rating_avg(self, obj):
        """Average of all food ratings across all spots where this food is served."""
        r = FoodSpotFoodRating.objects.filter(food=obj).aggregate(avg=Avg('rating'))
        avg_val = r['avg']
        return round(avg_val, 1) if avg_val is not None else None

    def get_rating_count(self, obj):
        return FoodSpotFoodRating.objects.filter(food=obj).count()

    class Meta:
        model = Food
        fields = ['id', 'name', 'description', 'alsocalled', 'tags', 'photos', 'attachments', 'urls',
                  'added_by', 'added_by_username', 'served_at_names', 'rating_avg', 'rating_count',
                  'created_at', 'modified_at']

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
        result = []
        for spot in spots:
            data = FoodSpotListSerializer(spot, context=self.context).data
            # Add rating/reviews for this food at this spot
            rating_result = FoodSpotFoodRating.objects.filter(
                food=obj, food_spot=spot
            ).aggregate(avg=Avg('rating'))
            rating_avg = rating_result['avg']
            rating_count = FoodSpotFoodRating.objects.filter(food=obj, food_spot=spot).count()
            data['rating_avg'] = round(rating_avg, 1) if rating_avg is not None else None
            data['rating_count'] = rating_count
            if request and request.user.is_authenticated:
                my_r = FoodSpotFoodRating.objects.filter(
                    food=obj, food_spot=spot, added_by=request.user
                ).first()
                data['my_rating'] = my_r.rating if my_r else None
                data['my_review'] = my_r.note if my_r and my_r.note else None
            else:
                data['my_rating'] = None
                data['my_review'] = None
            reviews_qs = FoodSpotFoodRating.objects.filter(
                food=obj, food_spot=spot
            ).select_related('added_by').order_by('-modified_at')
            data['reviews'] = [
                {
                    'id': str(r.id),
                    'rating': r.rating,
                    'note': r.note or None,
                    'added_by_username': get_user_display_name(r.added_by),
                    'modified_at': r.modified_at.isoformat() if r.modified_at else None,
                }
                for r in reviews_qs[:20]
            ]
            result.append(data)
        # Sort by average rating descending (spots with no rating last)
        result.sort(key=lambda s: (s['rating_avg'] is None, -(s['rating_avg'] or 0)))
        return result


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
        result = []
        for s in spots:
            data = {'id': s.id, 'name': s.name, 'photos': s.photos, 'added_by_username': get_user_display_name(s.added_by)}
            r_spot = Review.objects.filter(food_spot=s, food__isnull=True).aggregate(avg=Avg('rating'))
            data['rating_avg'] = round(r_spot['avg'], 1) if r_spot['avg'] is not None else None
            data['food_rating_avg'] = None
            avgs = []
            foods_data = []
            foods_qs = s.foods.filter(Q(private=False) | Q(added_by=request.user)) if request and request.user.is_authenticated else s.foods.filter(private=False)
            for f in foods_qs:
                r_f = FoodSpotFoodRating.objects.filter(food=f, food_spot=s).aggregate(avg=Avg('rating'))
                avg_val = r_f['avg']
                foods_data.append({'id': f.id, 'name': f.name, 'rating_avg': round(avg_val, 1) if avg_val is not None else None})
                if avg_val is not None and avg_val > 0:
                    avgs.append(float(avg_val))
            data['foods'] = sorted(foods_data, key=lambda x: (x['rating_avg'] is None, -(x['rating_avg'] or 0)))
            data['food_rating_avg'] = round(sum(avgs) / len(avgs), 1) if avgs else None
            data['food_rating_count'] = FoodSpotFoodRating.objects.filter(food_spot=s).count()
            data['rating_count'] = Review.objects.filter(food_spot=s, food__isnull=True).count()
            result.append(data)
        return result


class SpotListWriteSerializer(serializers.ModelSerializer):
    spots = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
        write_only=True,
    )

    class Meta:
        model = FoodSpotList
        fields = ['id', 'name', 'spots', 'created_at', 'modified_at']
        read_only_fields = ['id', 'created_at', 'modified_at']

    def _get_allowed_spot_ids(self, instance=None):
        """Return set of spot IDs the user may assign: visible spots + spots already on this list."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return set()
        allowed = set(
            FoodSpot.objects.filter(Q(private=False) | Q(added_by=request.user)).values_list('id', flat=True)
        )
        if instance:
            allowed |= set(instance.spots.values_list('id', flat=True))
        return allowed

    def validate_spots(self, value):
        allowed = self._get_allowed_spot_ids(self.instance)
        invalid = [str(sid) for sid in value if sid not in allowed]
        if invalid:
            raise serializers.ValidationError(
                f"Spot(s) not found or not allowed: {', '.join(invalid)}"
            )
        return value

    def create(self, validated_data):
        spots_ids = validated_data.pop('spots', [])
        instance = super().create(validated_data)
        if spots_ids:
            instance.spots.set(FoodSpot.objects.filter(id__in=spots_ids))
        return instance

    def update(self, instance, validated_data):
        spots_ids = validated_data.pop('spots', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if spots_ids is not None:
            instance.spots.set(FoodSpot.objects.filter(id__in=spots_ids))
        return instance


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
        result = []
        for f in foods:
            r = FoodSpotFoodRating.objects.filter(food=f).aggregate(avg=Avg('rating'))
            spots = f.served_at.filter(Q(private=False) | Q(added_by=request.user)) if request and request.user.is_authenticated else f.served_at.filter(private=False)
            result.append({
                'id': f.id, 'name': f.name, 'photos': f.photos,
                'rating_avg': round(r['avg'], 1) if r['avg'] is not None else None,
                'rating_count': FoodSpotFoodRating.objects.filter(food=f).count(),
                'added_by_username': get_user_display_name(f.added_by),
                'served_at_names': [s.name for s in spots],
            })
        result.sort(key=lambda x: (x['rating_avg'] is None, -(x['rating_avg'] or 0)))
        return result


class FoodItemListWriteSerializer(serializers.ModelSerializer):
    foods = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
        write_only=True,
    )

    class Meta:
        model = FoodList
        fields = ['id', 'name', 'foods', 'created_at', 'modified_at']
        read_only_fields = ['id', 'created_at', 'modified_at']

    def _get_allowed_food_ids(self, instance=None):
        """Return set of food IDs the user may assign: visible foods + foods already on this list."""
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
        allowed = self._get_allowed_food_ids(self.instance)
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
