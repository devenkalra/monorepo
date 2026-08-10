"""Gmail Assistant URL configuration — mounted at /api/gmail/."""

from django.urls import path

from . import views

urlpatterns = [
    path('status/', views.status_view, name='gmail-status'),
    path('preferences/', views.preferences_view, name='gmail-preferences'),
    path('accounts/', views.accounts_list, name='gmail-accounts'),
    path(
        'accounts/<uuid:account_id>/activate/',
        views.account_activate,
        name='gmail-account-activate',
    ),
    path(
        'accounts/<uuid:account_id>/',
        views.account_disconnect,
        name='gmail-account-disconnect',
    ),
    path('oauth/start/', views.oauth_start, name='gmail-oauth-start'),
    path('oauth/callback/', views.oauth_callback, name='gmail-oauth-callback'),
    path('query/preview/', views.query_preview, name='gmail-query-preview'),
    path('search/', views.search, name='gmail-search'),
    path('prompts/', views.prompts_view, name='gmail-prompts'),
    path('prompts/<uuid:prompt_id>/', views.prompt_delete, name='gmail-prompt-delete'),
    path('labels/', views.labels_view, name='gmail-labels'),
    path('emails/bulk/', views.bulk_action, name='gmail-bulk'),
    path('emails/<str:gmail_id>/', views.email_detail, name='gmail-email-detail'),
    path('schedules/', views.schedules_view, name='gmail-schedules'),
    path(
        'schedules/<uuid:schedule_id>/',
        views.schedule_detail,
        name='gmail-schedule-detail',
    ),
    path(
        'schedules/<uuid:schedule_id>/run/',
        views.schedule_run_now,
        name='gmail-schedule-run',
    ),
    path('summarize/', views.summarize, name='gmail-summarize'),
    path('process/', views.process_prompt, name='gmail-process'),
    path('tasks/<str:task_id>/progress/', views.task_progress, name='gmail-task-progress'),
]
