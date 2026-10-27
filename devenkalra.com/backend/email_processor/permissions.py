from rest_framework.permissions import BasePermission

from core.views import get_user_role


class IsSuperuserRole(BasePermission):
    """Site role superuser (staff/superuser or SOCIAL_SUPERUSERS email)."""

    def has_permission(self, request, view):
        return get_user_role(request) == 'superuser'
