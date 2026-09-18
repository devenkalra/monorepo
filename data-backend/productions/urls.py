from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProductionViewSet, SceneViewSet

router = DefaultRouter()
router.register(r'productions', ProductionViewSet, basename='production')
router.register(r'scenes', SceneViewSet, basename='production-scene')

urlpatterns = [
    path('', include(router.urls)),
]
