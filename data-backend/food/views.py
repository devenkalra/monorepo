"""Food app API views."""

from django.db.models import Q
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import FoodSpot, Food, Media, Review
from .serializers import (
    FoodSpotListSerializer, FoodSpotDetailSerializer, FoodSpotWriteSerializer,
    FoodListSerializer, FoodDetailSerializer, FoodWriteSerializer,
    MediaSerializer, ReviewSerializer,
)
from .permissions import IsFoodSpotOwner, IsFoodOwner


class FoodSpotViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsFoodSpotOwner]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'tags']
    ordering_fields = ['name', 'created_at', 'modified_at']
    ordering = ['-modified_at']

    def get_queryset(self):
        return FoodSpot.objects.filter(added_by=self.request.user)

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
    permission_classes = [IsAuthenticated, IsFoodOwner]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'alsocalled', 'tags']
    filterset_fields = []
    ordering_fields = ['name', 'created_at', 'modified_at']
    ordering = ['-modified_at']

    def get_queryset(self):
        return Food.objects.filter(added_by=self.request.user)

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
            Q(food_spot__added_by=user) | Q(food__added_by=user)
        )


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Review.objects.filter(
            Q(food_spot__added_by=user) | Q(food__added_by=user)
        )
