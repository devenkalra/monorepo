"""
Social authentication views for Google OAuth
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from django.conf import settings


class GoogleLogin(SocialLoginView):
    """
    Google OAuth2 login view
    
    POST /api/auth/google/
    Body: {
        "access_token": "google_access_token",
        "code": "authorization_code"  # Alternative to access_token
    }
    """
    adapter_class = GoogleOAuth2Adapter
    callback_url = settings.GOOGLE_OAUTH_CALLBACK_URL  # Frontend callback URL from settings
    client_class = OAuth2Client


@api_view(['GET'])
@permission_classes([AllowAny])
def google_login_redirect(request):
    """
    Returns the Google OAuth URL for the frontend to redirect to
    
    GET /api/auth/google/url/
    Response: {
        "url": "https://accounts.google.com/o/oauth2/v2/auth?..."
    }
    """
    from allauth.socialaccount.providers.google.provider import GoogleProvider
    from allauth.socialaccount.models import SocialApp
    
    try:
        # Get Google OAuth app credentials
        social_app = SocialApp.objects.get(provider=GoogleProvider.id)
        
        # Build OAuth URL using configured callback URL
        redirect_uri = settings.GOOGLE_OAUTH_CALLBACK_URL
        scope = "openid profile email"
        
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={social_app.client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"scope={scope}&"
            f"response_type=code&"
            f"access_type=offline&"
            f"prompt=consent"
        )
        
        return Response({
            "url": auth_url,
            "client_id": social_app.client_id,
            "redirect_uri": redirect_uri
        })
    except SocialApp.DoesNotExist:
        return Response(
            {"error": "Google OAuth not configured. Please add credentials in Django admin."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def google_callback(request):
    """
    Handle Google OAuth callback
    
    POST /api/auth/google/callback/
    Body: {
        "code": "authorization_code"
    }
    """
    from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
    from allauth.socialaccount.providers.oauth2.client import OAuth2Client
    from dj_rest_auth.registration.views import SocialLoginView
    
    code = request.data.get('code')
    if not code:
        return Response(
            {"error": "Authorization code is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Use the SocialLoginView to handle the OAuth flow
    view = GoogleLogin.as_view()
    return view(request._request)
