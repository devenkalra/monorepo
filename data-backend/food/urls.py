"""Food app URL configuration."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'spots', views.FoodSpotViewSet, basename='foodspot')
router.register(r'foods', views.FoodViewSet, basename='food')
router.register(r'spot-lists', views.FoodSpotListViewSet, basename='foodspotlist')
router.register(r'food-lists', views.FoodListViewSet, basename='foodlist')
router.register(r'media', views.MediaViewSet, basename='media')
router.register(r'reviews', views.ReviewViewSet, basename='review')

urlpatterns = [
    path('', include(router.urls)),
]
