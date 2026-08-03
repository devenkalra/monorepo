from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AssetCategoryViewSet, AssetTagViewSet,
    AssetAreaViewSet, AssetBoxViewSet, AssetItemViewSet,
)

router = DefaultRouter()
router.register(r'categories', AssetCategoryViewSet, basename='asset-category')
router.register(r'tags', AssetTagViewSet, basename='asset-tag')
router.register(r'areas', AssetAreaViewSet, basename='asset-area')
router.register(r'boxes', AssetBoxViewSet, basename='asset-box')
router.register(r'items', AssetItemViewSet, basename='asset-item')

urlpatterns = [
    path('', include(router.urls)),
]
