from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ListItemViewSet, CategoryViewSet, TagViewSet, ItemViewSet

router = DefaultRouter()
router.register(r'listitem', ListItemViewSet)
router.register(r'item', ItemViewSet)
router.register(r'category', CategoryViewSet)
router.register(r'tag', TagViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
