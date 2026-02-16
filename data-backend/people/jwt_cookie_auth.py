"""
JWT authentication from cookie (auth-token) for API requests.
Used when frontend sends credentials: 'include' and dj-rest-auth sets the cookie.
"""
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.conf import settings


class JWTCookieAuthentication(JWTAuthentication):
    """Authenticate using JWT from auth-token cookie (in addition to Authorization header)."""

    def authenticate(self, request):
        # Try Authorization header first
        header = self.get_header(request)
        if header is not None:
            return super().authenticate(request)

        # Fall back to cookie
        cookie_name = getattr(
            settings,
            'JWT_AUTH_COOKIE',
            getattr(settings, 'REST_AUTH', {}).get('JWT_AUTH_COOKIE', 'auth-token'),
        )
        raw_token = request.COOKIES.get(cookie_name)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
