from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    TripDayViewSet,
    TripLodgingViewSet,
    TripMediaViewSet,
    TripStopAttachmentViewSet,
    TripStopViewSet,
    TripViewSet,
)

router = DefaultRouter()
router.register(r'trips', TripViewSet, basename='trip')
router.register(r'days', TripDayViewSet, basename='trip-day')
router.register(r'lodgings', TripLodgingViewSet, basename='trip-lodging')
router.register(r'stops', TripStopViewSet, basename='trip-stop')
router.register(r'media', TripMediaViewSet, basename='trip-media')
router.register(r'attachments', TripStopAttachmentViewSet, basename='trip-attachment')

urlpatterns = [
    path('', include(router.urls)),
]
