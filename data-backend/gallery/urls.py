from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    GalleryItemViewSet,
    GalleryShareViewSet,
    GalleryShowViewSet,
    GalleryUploadView,
    GalleryViewSet,
    GenerateShowView,
    ShowBuildJobView,
    MediaBrowserView,
    PublicGalleryUnlockView,
    PublicGalleryView,
    ensure_username,
)

router = DefaultRouter()
router.register(r'galleries', GalleryViewSet, basename='gallery')
router.register(r'items', GalleryItemViewSet, basename='gallery-item')
router.register(r'shares', GalleryShareViewSet, basename='gallery-share')
router.register(r'shows', GalleryShowViewSet, basename='gallery-show')

urlpatterns = [
    path('public/<str:username>/<slug:slug>/', PublicGalleryView.as_view(), name='gallery-public'),
    path(
        'public/<str:username>/<slug:slug>/unlock/',
        PublicGalleryUnlockView.as_view(),
        name='gallery-public-unlock',
    ),
    path('shows/generate/', GenerateShowView.as_view(), name='gallery-show-generate'),
    path('show-jobs/<uuid:job_id>/', ShowBuildJobView.as_view(), name='gallery-show-job'),
    path('media-browser/', MediaBrowserView.as_view(), name='gallery-media-browser'),
    path('upload/', GalleryUploadView.as_view(), name='gallery-upload'),
    path('ensure-username/', ensure_username, name='gallery-ensure-username'),
    path('', include(router.urls)),
]
