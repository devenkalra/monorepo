"""
Custom permission classes for multi-user data isolation
"""

from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to view/edit it.
    """
    
    def has_object_permission(self, request, view, obj):
        # Check if the object has a user field
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        # For Entity subclasses that inherit user field
        if hasattr(obj, 'entity_ptr'):
            return obj.entity_ptr.user == request.user
        
        return False


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners to edit, but anyone to view.
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only to owner
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        if hasattr(obj, 'entity_ptr'):
            return obj.entity_ptr.user == request.user
        
        return False


class BothEntitiesOwned(permissions.BasePermission):
    """
    For EntityRelation: both from_entity and to_entity must belong to the user.
    """
    
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'from_entity') and hasattr(obj, 'to_entity'):
            return (obj.from_entity.user == request.user and 
                    obj.to_entity.user == request.user)
        return False
