"""Food app permissions - user must own the resource."""

from rest_framework import permissions


class IsFoodSpotOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.added_by_id == request.user.id


class IsFoodOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.added_by_id == request.user.id


class IsFoodSpotListOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.added_by_id == request.user.id


class IsFoodListOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.added_by_id == request.user.id
