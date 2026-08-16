from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VacTagViewSet, VacCategoryViewSet, VacItemViewSet,
    VacListViewSet, VacListItemViewSet,
)

router = DefaultRouter()
router.register(r'tags', VacTagViewSet, basename='vac-tag')
router.register(r'categories', VacCategoryViewSet, basename='vac-category')
router.register(r'items', VacItemViewSet, basename='vac-item')
router.register(r'lists', VacListViewSet, basename='vac-list')
router.register(r'list-items', VacListItemViewSet, basename='vac-list-item')

urlpatterns = [
    path('', include(router.urls)),
]
