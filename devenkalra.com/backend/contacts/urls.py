from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (CheckView, EntityDetailView, EntityListView, GoogleDisconnectView, GoogleOAuthCallbackView,
                    GoogleOAuthStartView, ReviewItemViewSet, SettingsView, StatusView, SyncRunViewSet, UploadView)

router = DefaultRouter()
router.register(r'runs', SyncRunViewSet, basename='contacts-run')
router.register(r'reviews', ReviewItemViewSet, basename='contacts-review')

urlpatterns = [
    path('status/', StatusView.as_view(), name='contacts-status'),
    path('check/', CheckView.as_view(), name='contacts-check'),
    path('settings/', SettingsView.as_view(), name='contacts-settings'),
    path('uploads/', UploadView.as_view(), name='contacts-uploads'),
    path('oauth/start/', GoogleOAuthStartView.as_view(), name='contacts-oauth-start'),
    path('oauth/callback/', GoogleOAuthCallbackView.as_view(), name='contacts-oauth-callback'),
    path('google/disconnect/', GoogleDisconnectView.as_view(), name='contacts-google-disconnect'),
    path('entities/', EntityListView.as_view(), name='contacts-entities'),
    path('entities/<str:task_id>/', EntityDetailView.as_view(), name='contacts-entity'),
    path('', include(router.urls)),
]
