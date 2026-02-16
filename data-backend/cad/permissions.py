"""CAD permissions - user must own the model."""

from rest_framework import permissions


class IsCADModelOwner(permissions.BasePermission):
    """Only allow access to CAD models owned by the request user."""

    def has_object_permission(self, request, view, obj):
        return obj.user_id == request.user.id
