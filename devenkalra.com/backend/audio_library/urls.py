from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AudioMetaView, AudioReindexView, AudioTrackViewSet

router = DefaultRouter()
router.register(r'tracks', AudioTrackViewSet, basename='audio-track')

urlpatterns = [
    path('meta/', AudioMetaView.as_view(), name='audio-meta'),
    path('reindex/', AudioReindexView.as_view(), name='audio-reindex'),
    path('', include(router.urls)),
]
