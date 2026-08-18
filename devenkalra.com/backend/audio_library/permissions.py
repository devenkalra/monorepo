from rest_framework.permissions import BasePermission

from core.views import get_user_role


class IsSuperuserRole(BasePermission):
    def has_permission(self, request, view):
        return get_user_role(request) == 'superuser'
