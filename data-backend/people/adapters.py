"""
Custom adapters for django-allauth
"""
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

User = get_user_model()


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter to auto-connect social accounts to existing users with matching email
    """
    
    def pre_social_login(self, request, sociallogin):
        """
        Invoked just after a user successfully authenticates via a social provider,
        but before the login is actually processed.
        
        If a user with the same email already exists, connect the social account to that user.
        """
        # If the social account is already connected, do nothing
        if sociallogin.is_existing:
            return
        
        # Get the email from the social account
        email = sociallogin.account.extra_data.get('email')
        if not email:
            return
        
        # Check if a user with this email already exists
        try:
            user = User.objects.get(email=email)
            # Connect the social account to the existing user
            sociallogin.connect(request, user)
            print(f"Connected social account to existing user: {user.email}")
        except User.DoesNotExist:
            # No existing user, let the normal flow create a new one
            pass
    
    def is_auto_signup_allowed(self, request, sociallogin):
        """
        Override to allow auto-signup even if email exists.
        The pre_social_login will handle connecting to existing user.
        """
        return True
