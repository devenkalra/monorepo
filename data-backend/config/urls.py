"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView
from people.static_views import login_page, api_tester_page
from people.social_auth_views import GoogleLogin, google_login_redirect, google_callback
from people.health_views import health_check, health_detailed

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Health check endpoints
    path('api/health/', health_check, name='health_check'),
    path('api/health/detailed/', health_detailed, name='health_detailed'),
    
    # Static pages
    path('', login_page, name='login'),
    path('login/', login_page, name='login_page'),
    path('api-tester/', api_tester_page, name='api_tester'),
    
    # Authentication endpoints
    path('api/auth/', include('dj_rest_auth.urls')),  # login, logout, user, password reset
    path('api/auth/registration/', include('dj_rest_auth.registration.urls')),  # registration
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Google OAuth endpoints
    path('api/auth/google/', GoogleLogin.as_view(), name='google_login'),
    path('api/auth/google/url/', google_login_redirect, name='google_login_url'),
    path('api/auth/google/callback/', google_callback, name='google_callback'),
    
    # Social authentication (Google, GitHub, etc.) - for traditional flow
    path('accounts/', include('allauth.urls')),  # allauth URLs
    
    # Main API
    path('api/', include('people.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
