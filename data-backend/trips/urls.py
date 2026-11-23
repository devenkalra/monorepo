from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    PublicTripView,
    TripCommentViewSet,
    TripDayViewSet,
    TripLegViewSet,
    TripLodgingViewSet,
    TripMediaViewSet,
    TripShareViewSet,
    TripStopAttachmentViewSet,
    TripStopViewSet,
    TripSuggestionBatchViewSet,
    TripSuggestionViewSet,
    TripTodoViewSet,
    TripViewSet,
)

router = DefaultRouter()
router.register(r'trips', TripViewSet, basename='trip')
router.register(r'legs', TripLegViewSet, basename='trip-leg')
router.register(r'days', TripDayViewSet, basename='trip-day')
router.register(r'lodgings', TripLodgingViewSet, basename='trip-lodging')
router.register(r'stops', TripStopViewSet, basename='trip-stop')
router.register(r'media', TripMediaViewSet, basename='trip-media')
router.register(r'attachments', TripStopAttachmentViewSet, basename='trip-attachment')
router.register(r'todos', TripTodoViewSet, basename='trip-todo')
router.register(r'assistant', TripSuggestionBatchViewSet, basename='trip-assistant')
router.register(r'suggestions', TripSuggestionViewSet, basename='trip-suggestion')
router.register(r'shares', TripShareViewSet, basename='trip-share')
router.register(r'comments', TripCommentViewSet, basename='trip-comment')

urlpatterns = [
    path('public/<str:token>/', PublicTripView.as_view(), name='trip-public'),
    path('', include(router.urls)),
]
