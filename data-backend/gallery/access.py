"""Gallery ACL helpers: public vs restricted + per-share password session."""

from django.utils import timezone

from .constants import ACCESS_PUBLIC, ROLE_ADD, ROLE_EDIT, ROLE_VIEW
from .models import Gallery, GalleryShare
from .utils import role_at_least

SHARE_SESSION_KEY = 'gallery_share_unlocks'  # {gallery_id: share_id}


def _session_unlocks(request) -> dict:
    if not hasattr(request, 'session'):
        return {}
    data = request.session.get(SHARE_SESSION_KEY) or {}
    return data if isinstance(data, dict) else {}


def mark_share_unlocked(request, gallery: Gallery, share: GalleryShare):
    unlocks = _session_unlocks(request)
    unlocks[str(gallery.id)] = str(share.id)
    request.session[SHARE_SESSION_KEY] = unlocks
    request.session.modified = True
    share.last_accessed_at = timezone.now()
    share.save(update_fields=['last_accessed_at'])


def clear_share_unlock(request, gallery: Gallery):
    unlocks = _session_unlocks(request)
    unlocks.pop(str(gallery.id), None)
    request.session[SHARE_SESSION_KEY] = unlocks
    request.session.modified = True


def get_unlocked_share(request, gallery: Gallery) -> GalleryShare | None:
    unlocks = _session_unlocks(request)
    share_id = unlocks.get(str(gallery.id))
    if not share_id:
        return None
    try:
        share = gallery.shares.get(id=share_id, active=True)
    except GalleryShare.DoesNotExist:
        return None
    return share


def resolve_access(request, gallery: Gallery) -> dict:
    """
    Returns {
      can_view, can_add, can_edit, is_owner, role,
      needs_login, needs_share_password, needs_signup, share
    }
    """
    user = getattr(request, 'user', None)
    is_auth = bool(user and user.is_authenticated)
    result = {
        'can_view': False,
        'can_add': False,
        'can_edit': False,
        'is_owner': False,
        'role': None,
        'needs_login': False,
        'needs_share_password': False,
        'needs_signup': False,
        'share': None,
    }

    if is_auth and gallery.owner_id == user.id:
        result.update(
            can_view=True,
            can_add=True,
            can_edit=True,
            is_owner=True,
            role=ROLE_EDIT,
        )
        return result

    if gallery.access_mode == ACCESS_PUBLIC:
        result.update(can_view=True, role=ROLE_VIEW)
        return result

    # Restricted
    if not is_auth:
        result['needs_login'] = True
        return result

    email = (user.email or '').strip().lower()
    share = gallery.shares.filter(email__iexact=email, active=True).first()
    if not share:
        # Authenticated but not on allow-list
        return result

    unlocked = get_unlocked_share(request, gallery)
    if not unlocked or unlocked.id != share.id:
        result['needs_share_password'] = True
        result['share'] = share
        return result

    role = share.role
    result.update(
        can_view=True,
        can_add=role_at_least(role, ROLE_ADD),
        can_edit=role_at_least(role, ROLE_EDIT),
        role=role,
        share=share,
    )
    return result


def require_gallery_perm(request, gallery: Gallery, needed: str = ROLE_VIEW) -> dict:
    access = resolve_access(request, gallery)
    if needed == ROLE_VIEW and access['can_view']:
        return access
    if needed == ROLE_ADD and access['can_add']:
        return access
    if needed == ROLE_EDIT and access['can_edit']:
        return access
    return access
