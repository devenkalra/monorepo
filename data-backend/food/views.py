"""Food app API views."""

from django.db.models import Q, Avg, Value, FloatField
from django.db.models.functions import Coalesce
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend

from .models import FoodSpot, Food, FoodSpotList, FoodList, Media, Review, FoodSpotFoodRating
from .serializers import (
    FoodSpotListSerializer, FoodSpotDetailSerializer, FoodSpotWriteSerializer,
    FoodListSerializer, FoodDetailSerializer, FoodWriteSerializer,
    SpotListSerializer, SpotListWriteSerializer,
    FoodItemListSerializer, FoodItemListWriteSerializer,
    MediaSerializer, ReviewSerializer,
    FoodSpotFoodRatingSerializer, FoodSpotFoodRatingWriteSerializer,
)
from .permissions import IsFoodSpotOwner, IsFoodOwner, IsFoodSpotListOwner, IsFoodListOwner


class FoodSpotViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly, IsFoodSpotOwner]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'tags']
    ordering_fields = ['name', 'created_at', 'modified_at', 'food_rating_avg']
    ordering = ['-food_rating_avg', '-modified_at']

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            qs = FoodSpot.objects.filter(Q(private=False) | Q(added_by=user))
        else:
            qs = FoodSpot.objects.filter(private=False)
        if self.action == 'list':
            qs = qs.annotate(
                food_rating_avg=Coalesce(Avg('food_ratings__rating'), Value(0), output_field=FloatField())
            ).order_by('-food_rating_avg', '-modified_at')
        return qs

    def get_serializer_class(self):
        if self.action in ('list',):
            return FoodSpotListSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return FoodSpotWriteSerializer
        return FoodSpotDetailSerializer

    def perform_create(self, serializer):
        serializer.save(added_by=self.request.user)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx


class FoodViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly, IsFoodOwner]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'alsocalled', 'tags']
    filterset_fields = []
    ordering_fields = ['name', 'created_at', 'modified_at', 'rating_avg']
    ordering = ['-rating_avg', '-modified_at']

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            qs = Food.objects.filter(Q(private=False) | Q(added_by=user))
        else:
            qs = Food.objects.filter(private=False)
        if self.action == 'list':
            qs = qs.annotate(
                rating_avg=Coalesce(Avg('ratings_at_spots__rating'), Value(0), output_field=FloatField())
            ).order_by('-rating_avg', '-modified_at')
        return qs

    def get_serializer_class(self):
        if self.action in ('list',):
            return FoodListSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return FoodWriteSerializer
        return FoodDetailSerializer

    def perform_create(self, serializer):
        serializer.save(added_by=self.request.user)


class MediaViewSet(viewsets.ModelViewSet):
    serializer_class = MediaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Media.objects.filter(
            Q(food_spot__isnull=True) | Q(food_spot__private=False) | Q(food_spot__added_by=user)
        ).filter(
            Q(food__isnull=True) | Q(food__private=False) | Q(food__added_by=user)
        )


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Review.objects.filter(
            Q(food_spot__isnull=True) | Q(food_spot__private=False) | Q(food_spot__added_by=user)
        ).filter(
            Q(food__isnull=True) | Q(food__private=False) | Q(food__added_by=user)
        )

    def perform_create(self, serializer):
        serializer.save(added_by=self.request.user)


class FoodSpotFoodRatingViewSet(viewsets.ModelViewSet):
    """Create/update rating for a food at a specific spot. POST upserts (one rating per user per food per spot)."""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FoodSpotFoodRating.objects.filter(added_by=self.request.user)

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return FoodSpotFoodRatingWriteSerializer
        return FoodSpotFoodRatingSerializer


class FoodSpotListViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsFoodSpotListOwner]

    def get_queryset(self):
        return FoodSpotList.objects.filter(added_by=self.request.user)

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return SpotListWriteSerializer
        return SpotListSerializer

    def perform_create(self, serializer):
        serializer.save(added_by=self.request.user)


class FoodListViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsFoodListOwner]

    def get_queryset(self):
        return FoodList.objects.filter(added_by=self.request.user)

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return FoodItemListWriteSerializer
        return FoodItemListSerializer

    def perform_create(self, serializer):
        serializer.save(added_by=self.request.user)
