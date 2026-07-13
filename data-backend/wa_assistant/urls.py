"""WhatsApp Assistant URL configuration."""
from django.urls import path
from . import views

urlpatterns = [
    path('webhook/', views.webhook, name='wa_webhook'),
]
