"""Role-based access helpers for Trips (owner / editor / viewer)."""

from django.db.models import Q

from .models import Trip, TripShare

ROLE_OWNER = 'owner'
ROLE_EDITOR = TripShare.ROLE_EDITOR
ROLE_VIEWER = TripShare.ROLE_VIEWER


def _user_email(user):
    return (getattr(user, 'email', '') or '').strip().lower()


def _share_match_q(user, prefix=''):
    q = Q(**{f'{prefix}user': user})
    email = _user_email(user)
    if email:
        q |= Q(**{f'{prefix}email__iexact': email})
    return q


def accessible_trips(user, *, write=False):
    """Return a queryset of Trip rows readable (or editable when write=True) by `user`."""
    if not user or not user.is_authenticated:
        return Trip.objects.none()
    share_q = _share_match_q(user, prefix='shares__')
    if write:
        q = Q(user=user) | (share_q & Q(shares__role=ROLE_EDITOR))
    else:
        q = Q(user=user) | share_q
    return Trip.objects.filter(q).distinct()


def owned_trips(user):
    if not user or not user.is_authenticated:
        return Trip.objects.none()
    return Trip.objects.filter(user=user)


def trip_role(trip, user):
    """Return 'owner', 'editor', 'viewer', or None."""
    if not trip or not user or not user.is_authenticated:
        return None
    if trip.user_id == user.id:
        return ROLE_OWNER
    email = _user_email(user)
    shares_cache = getattr(trip, '_prefetched_objects_cache', {}).get('shares')
    if shares_cache is not None:
        best = None
        for share in shares_cache:
            if share.user_id == user.id or (email and share.email.lower() == email):
                if share.role == ROLE_EDITOR:
                    return ROLE_EDITOR
                best = share.role
        return best
    qs = TripShare.objects.filter(trip=trip).filter(_share_match_q(user))
    roles = set(qs.values_list('role', flat=True))
    if ROLE_EDITOR in roles:
        return ROLE_EDITOR
    if ROLE_VIEWER in roles:
        return ROLE_VIEWER
    return None


def can_view_trip(trip, user):
    return trip_role(trip, user) is not None


def can_edit_trip(trip, user):
    return trip_role(trip, user) in (ROLE_OWNER, ROLE_EDITOR)


def is_trip_owner(trip, user):
    return trip_role(trip, user) == ROLE_OWNER


def user_display_label(user):
    if not user:
        return ''
    name = (getattr(user, 'get_full_name', lambda: '')() or '').strip()
    if name:
        return name
    display = (getattr(user, 'displayname', '') or '').strip()
    if display:
        return display
    if getattr(user, 'email', ''):
        return user.email
    return getattr(user, 'username', '') or f'User #{user.pk}'
