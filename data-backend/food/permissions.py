"""Food app permissions - read: non-private or owner; write: owner only."""

from rest_framework import permissions


class IsFoodSpotOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return request.method in permissions.SAFE_METHODS and not obj.private
        if request.method in permissions.SAFE_METHODS:
            return not obj.private or obj.added_by_id == request.user.id
        return obj.added_by_id == request.user.id


class IsFoodOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return request.method in permissions.SAFE_METHODS and not obj.private
        if request.method in permissions.SAFE_METHODS:
            return not obj.private or obj.added_by_id == request.user.id
        return obj.added_by_id == request.user.id


class IsFoodSpotListOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.added_by_id == request.user.id


class IsFoodListOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.added_by_id == request.user.id
