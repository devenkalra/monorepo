"""Food app API views."""

from django.db.models import Q
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
    ordering_fields = ['name', 'created_at', 'modified_at']
    ordering = ['-modified_at']

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            return FoodSpot.objects.filter(Q(private=False) | Q(added_by=user))
        return FoodSpot.objects.filter(private=False)

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
    ordering_fields = ['name', 'created_at', 'modified_at']
    ordering = ['-modified_at']

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            return Food.objects.filter(Q(private=False) | Q(added_by=user))
        return Food.objects.filter(private=False)

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
