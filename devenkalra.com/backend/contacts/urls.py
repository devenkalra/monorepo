from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (CheckView, EntityActionsView, EntityBulkView, EntityCreateView, EntityDetailView,
                    EntityListView, GoogleContactDetailView, GoogleContactsBulkCreateView,
                    GoogleContactsBulkUpdateView, GoogleContactsView, GoogleDisconnectView, GoogleLabelsView,
                    GoogleOAuthCallbackView, GoogleOAuthStartView, LookupViewSet, MailCampaignActionView,
                    MailCampaignDetailView, MailCampaignListView, MailDraftDetailView, MailDraftListView,
                    MailSendAsListView, ReviewItemViewSet, SettingsView, StatusView, SyncRunViewSet,
                    UploadView)

router = DefaultRouter()
router.register(r'runs', SyncRunViewSet, basename='contacts-run')
router.register(r'reviews', ReviewItemViewSet, basename='contacts-review')
router.register(r'lookups', LookupViewSet, basename='contacts-lookup')

urlpatterns = [
    path('status/', StatusView.as_view(), name='contacts-status'),
    path('check/', CheckView.as_view(), name='contacts-check'),
    path('settings/', SettingsView.as_view(), name='contacts-settings'),
    path('uploads/', UploadView.as_view(), name='contacts-uploads'),
    path('oauth/start/', GoogleOAuthStartView.as_view(), name='contacts-oauth-start'),
    path('oauth/callback/', GoogleOAuthCallbackView.as_view(), name='contacts-oauth-callback'),
    path('google/disconnect/', GoogleDisconnectView.as_view(), name='contacts-google-disconnect'),
    path('google/labels/', GoogleLabelsView.as_view(), name='contacts-google-labels'),
    path('google/contacts/', GoogleContactsView.as_view(), name='contacts-google-contacts'),
    path('google/contacts/bulk-update/', GoogleContactsBulkUpdateView.as_view(),
         name='contacts-google-contacts-bulk-update'),
    path('google/contacts/bulk-create/', GoogleContactsBulkCreateView.as_view(),
         name='contacts-google-contacts-bulk-create'),
    path('google/contacts/<path:resource_name>/', GoogleContactDetailView.as_view(),
         name='contacts-google-contact'),
    path('entities/', EntityListView.as_view(), name='contacts-entities'),
    path('entities/create/', EntityCreateView.as_view(), name='contacts-entity-create'),
    path('entities/bulk/', EntityBulkView.as_view(), name='contacts-entities-bulk'),
    path('entities/actions/', EntityActionsView.as_view(), name='contacts-entities-actions'),
    path('entities/<str:task_id>/', EntityDetailView.as_view(), name='contacts-entity'),
    path('mail-campaigns/', MailCampaignListView.as_view(), name='contacts-mail-campaigns'),
    path('mail-campaigns/drafts/', MailDraftListView.as_view(), name='contacts-mail-drafts'),
    path('mail-campaigns/drafts/<str:draft_id>/', MailDraftDetailView.as_view(),
         name='contacts-mail-draft'),
    path('mail-campaigns/send-as/', MailSendAsListView.as_view(), name='contacts-mail-send-as'),
    path('mail-campaigns/<int:campaign_id>/', MailCampaignDetailView.as_view(),
         name='contacts-mail-campaign'),
    path('mail-campaigns/<int:campaign_id>/action/', MailCampaignActionView.as_view(),
         name='contacts-mail-campaign-action'),
    path('', include(router.urls)),
]
