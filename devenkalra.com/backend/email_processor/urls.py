from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CommandCenterView,
    CommandSelectionView,
    EmailMessageViewSet,
    GmailOAuthCallbackView,
    GmailOAuthStartView,
    MailboxViewSet,
    PubSubPushView,
    SavedSearchViewSet,
    WorkflowRunViewSet,
)

router = DefaultRouter()
router.register(r'mailbox', MailboxViewSet, basename='email-mailbox')
router.register(r'messages', EmailMessageViewSet, basename='email-message')
router.register(r'runs', WorkflowRunViewSet, basename='email-run')
router.register(r'saved-searches', SavedSearchViewSet, basename='email-saved-search')

urlpatterns = [
    path('oauth/start/', GmailOAuthStartView.as_view(), name='email-oauth-start'),
    path('oauth/callback/', GmailOAuthCallbackView.as_view(), name='email-oauth-callback'),
    path('pubsub/', PubSubPushView.as_view(), name='email-pubsub'),
    path('command/', CommandCenterView.as_view(), name='email-command'),
    path('command/selection/', CommandSelectionView.as_view(), name='email-command-selection'),
    path('', include(router.urls)),
]
