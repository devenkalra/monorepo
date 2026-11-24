"""Transactional email helpers for trip collaborator invitations."""

import html
import logging
import os
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from .models import TripShare

logger = logging.getLogger(__name__)


def _inviter_label(user):
    if not user:
        return 'Someone'
    full = f'{getattr(user, "first_name", "")} {getattr(user, "last_name", "")}'.strip()
    if full:
        return full
    display = (getattr(user, 'displayname', '') or '').strip()
    if display:
        return display
    return (getattr(user, 'email', '') or getattr(user, 'username', '') or 'Someone').strip()


def _site_origin(request=None):
    configured = (os.environ.get('SITE_URL') or os.environ.get('PUBLIC_BASE_URL') or '').strip().rstrip('/')
    if configured:
        return configured
    if request is not None:
        try:
            proto = (request.META.get('HTTP_X_FORWARDED_PROTO') or '').split(',')[0].strip()
            host = (
                request.META.get('HTTP_X_FORWARDED_HOST')
                or request.get_host()
                or ''
            ).split(',')[0].strip()
            if host:
                scheme = proto or ('https' if request.is_secure() else 'http')
                return f'{scheme}://{host}'
        except Exception:  # noqa: BLE001
            pass
    return 'https://bldrdojo.com'


def _trip_dates_summary(trip):
    if trip.start_date and trip.end_date:
        if trip.start_date == trip.end_date:
            return trip.start_date.strftime('%b %d, %Y')
        return f'{trip.start_date.strftime("%b %d, %Y")} – {trip.end_date.strftime("%b %d, %Y")}'
    if trip.start_date:
        return f'Starting {trip.start_date.strftime("%b %d, %Y")}'
    return ''


def build_invite_email(share, request=None):
    """Build (subject, text_body, html_body, reply_to) for a TripShare invitation."""
    trip = share.trip
    inviter = share.invited_by or trip.user
    inviter_name = _inviter_label(inviter)
    inviter_email = (getattr(inviter, 'email', '') or '').strip()
    origin = _site_origin(request)
    if not share.invite_token:
        share.save()
    trip_url = f'{origin}/app/trips/?{urlencode({"invite": share.invite_token})}'
    public_url = (
        f'{origin}/app/trips/share/{trip.share_token}'
        if trip.public_enabled and trip.share_token
        else ''
    )

    is_editor = share.role == TripShare.ROLE_EDITOR
    role_label = 'Editor' if is_editor else 'Viewer'
    role_desc = (
        'view the itinerary, edit the route, schedule, ideas, and bookings, and join comments'
        if is_editor
        else 'view the full itinerary and leave comments'
    )
    dates = _trip_dates_summary(trip)
    needs_signup = share.user_id is None

    subject = f'{inviter_name} invited you to "{trip.title}"'

    text_lines = [
        f'Hi,',
        '',
        f'{inviter_name} invited you to collaborate on the trip "{trip.title}" as a {role_label}.',
    ]
    if dates:
        text_lines.append(f'Dates: {dates}')
    text_lines += [
        f'As a {role_label}, you can {role_desc}.',
        '',
        f'Open the trip: {trip_url}',
    ]
    if needs_signup:
        text_lines += [
            '',
            f'Don\'t have an account yet? Create one using {share.email} on the sign-in page '
            'and this trip will appear automatically.',
        ]
    if public_url:
        text_lines += [
            '',
            f'Read-only preview (no sign-in required): {public_url}',
        ]
    text_body = '\n'.join(text_lines)

    e_title = html.escape(trip.title)
    e_inviter = html.escape(inviter_name)
    e_role = html.escape(role_label)
    e_role_desc = html.escape(role_desc)
    e_url = html.escape(trip_url, quote=True)
    e_email = html.escape(share.email)
    dates_html = f'<p style="margin:0 0 12px;color:#57534e;font-size:14px;">{html.escape(dates)}</p>' if dates else ''
    signup_html = (
        f'<p style="margin:16px 0 0;color:#57534e;font-size:13px;">'
        f'Don&#39;t have an account yet? Register with <strong>{e_email}</strong> on the sign-in page '
        f'and this trip will appear automatically.</p>'
        if needs_signup
        else ''
    )
    public_html = (
        f'<p style="margin:12px 0 0;color:#57534e;font-size:13px;">'
        f'Or view a read-only preview without signing in: '
        f'<a href="{html.escape(public_url, quote=True)}" style="color:#0f766e;">{html.escape(public_url)}</a></p>'
        if public_url
        else ''
    )

    html_body = (
        '<!doctype html><html><body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;'
        'background:#f7f6f2;padding:24px;color:#202426;">'
        '<div style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e7e5e4;'
        'border-radius:12px;padding:24px;">'
        f'<p style="margin:0 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:0.06em;color:#78716c;">Trip Invitation</p>'
        f'<h2 style="margin:0 0 8px;font-size:20px;color:#1c1917;">{e_title}</h2>'
        f'{dates_html}'
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.5;">'
        f'<strong>{e_inviter}</strong> invited you as a <strong>{e_role}</strong>. '
        f'You can {e_role_desc}.</p>'
        f'<p style="margin:20px 0;">'
        f'<a href="{e_url}" style="display:inline-block;background:#0f766e;color:#ffffff;'
        f'text-decoration:none;font-weight:600;padding:10px 18px;border-radius:8px;font-size:14px;">'
        f'Open Trip</a></p>'
        f'<p style="margin:0;color:#78716c;font-size:12px;word-break:break-all;">'
        f'Direct link: <a href="{e_url}" style="color:#0f766e;">{e_url}</a></p>'
        f'{signup_html}'
        f'{public_html}'
        '</div></body></html>'
    )

    reply_to = [inviter_email] if inviter_email else None
    return subject, text_body, html_body, reply_to


def send_trip_invite_email(share, request=None):
    """Send an invitation email for ``share`` and return a delivery status dict.

    Never raises on mail-server failure so collaborator access is still granted even if SMTP
    is misconfigured or temporarily unreachable.
    """
    backend = getattr(settings, 'EMAIL_BACKEND', '') or ''
    console_only = backend.endswith('console.EmailBackend')
    from_email = (
        getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        or getattr(settings, 'EMAIL_HOST_USER', None)
        or 'noreply@bldrdojo.com'
    )
    subject, text_body, html_body, reply_to = build_invite_email(share, request=request)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=[share.email],
        reply_to=reply_to,
    )
    msg.attach_alternative(html_body, 'text/html')

    try:
        sent_count = msg.send(fail_silently=False)
        return {
            'sent': bool(sent_count),
            'console_only': console_only,
            'error': '',
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception('Failed to send trip invite email to %s for trip %s', share.email, share.trip_id)
        return {
            'sent': False,
            'console_only': console_only,
            'error': str(exc),
        }
