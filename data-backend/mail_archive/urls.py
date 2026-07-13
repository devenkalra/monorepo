from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmailAccountViewSet, ImportConfigViewSet, EmailViewSet

router = DefaultRouter()
router.register(r'accounts', EmailAccountViewSet, basename='email-account')
router.register(r'configs', ImportConfigViewSet, basename='import-config')
router.register(r'emails', EmailViewSet, basename='email')

urlpatterns = [
    path('', include(router.urls)),
]
