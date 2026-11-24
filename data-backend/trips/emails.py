"""Transactional email helpers for trip collaborator invitations."""

import html
import logging
import os
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

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


def _comment_target_label(comment):
    """Short human-readable label for what a TripComment is attached to."""
    if comment.stop_id and comment.stop:
        stop = comment.stop
        if stop.day_id and stop.day and stop.day.date:
            return f'Stop "{stop.text}" ({stop.day.date.strftime("%b %d, %Y")})'
        return f'Idea "{stop.text}"'
    if comment.lodging_id and comment.lodging:
        return f'Lodging "{comment.lodging.name}"'
    if comment.day_id and comment.day:
        day = comment.day
        date_str = day.date.strftime('%b %d, %Y') if day.date else 'Day'
        return f'{date_str} — {day.title}' if day.title else date_str
    if comment.leg_id and comment.leg:
        return f'Leg "{comment.leg.name}"'
    return f'Trip "{comment.trip.title}"'


def build_comment_email(comment, trip_url, request=None):
    """Build (subject, text_body, html_body, reply_to) for a new comment or reply."""
    trip = comment.trip
    author = comment.author
    author_name = _inviter_label(author)
    author_email = (getattr(author, 'email', '') or '').strip()
    target_label = _comment_target_label(comment)
    is_reply = bool(comment.parent_id)
    parent = comment.parent if is_reply else None
    parent_author_name = _inviter_label(parent.author) if parent and parent.author_id else 'a comment'
    parent_snippet = ''
    if parent and parent.body:
        raw_parent = parent.body.strip()
        parent_snippet = raw_parent if len(raw_parent) <= 220 else f'{raw_parent[:217]}…'

    kind_badge = 'New Reply' if is_reply else 'New Comment'
    if comment.stop_id or comment.lodging_id or comment.day_id or comment.leg_id:
        subject_prefix = 'New reply' if is_reply else 'New comment'
        subject = f'{subject_prefix} on "{trip.title}" · {target_label}'
    else:
        subject_prefix = 'New reply' if is_reply else 'New comment'
        subject = f'{subject_prefix} on "{trip.title}"'

    action_line = (
        f'{author_name} replied to {parent_author_name}\'s comment on {target_label}:'
        if is_reply
        else f'{author_name} posted a new comment on {target_label}:'
    )

    text_lines = [
        f'{kind_badge} — {trip.title}',
        '',
        action_line,
        '',
    ]
    if is_reply and parent_snippet:
        text_lines += [
            f'Original comment ({parent_author_name}):',
            f'> {parent_snippet}',
            '',
            'Reply:',
        ]
    text_lines += [
        comment.body.strip(),
        '',
        f'Open Trips: {trip_url}',
    ]
    text_body = '\n'.join(text_lines)

    e_title = html.escape(trip.title)
    e_badge = html.escape(kind_badge)
    e_author = html.escape(author_name)
    e_target = html.escape(target_label)
    e_body = html.escape(comment.body.strip()).replace('\n', '<br>')
    e_url = html.escape(trip_url, quote=True)

    intro_html = (
        f'<strong>{e_author}</strong> replied to <strong>{html.escape(parent_author_name)}</strong> on <strong>{e_target}</strong>:'
        if is_reply
        else f'<strong>{e_author}</strong> posted a new comment on <strong>{e_target}</strong>:'
    )
    parent_html = (
        '<blockquote style="margin:0 0 12px;padding:10px 12px;border-left:3px solid #d6d3d1;'
        'background:#fafaf9;color:#57534e;font-size:13px;line-height:1.45;">'
        f'<div style="font-size:11px;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:4px;color:#78716c;">'
        f'In reply to {html.escape(parent_author_name)}</div>'
        f'{html.escape(parent_snippet).replace(chr(10), "<br>")}'
        '</blockquote>'
        if is_reply and parent_snippet
        else ''
    )

    html_body = (
        '<!doctype html><html><body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;'
        'background:#f7f6f2;padding:24px;color:#202426;">'
        '<div style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e7e5e4;'
        'border-radius:12px;padding:24px;">'
        f'<p style="margin:0 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:0.06em;color:#0f766e;font-weight:600;">{e_badge}</p>'
        f'<h2 style="margin:0 0 10px;font-size:20px;color:#1c1917;">{e_title}</h2>'
        f'<p style="margin:0 0 14px;font-size:14px;line-height:1.5;color:#44403c;">{intro_html}</p>'
        f'{parent_html}'
        '<div style="margin:0 0 20px;padding:14px 16px;background:#f5f5f4;border-radius:8px;'
        f'font-size:15px;line-height:1.55;color:#1c1917;">{e_body}</div>'
        f'<p style="margin:0 0 14px;">'
        f'<a href="{e_url}" style="display:inline-block;background:#0f766e;color:#ffffff;'
        f'text-decoration:none;font-weight:600;padding:10px 18px;border-radius:8px;font-size:14px;">'
        f'Open Trip</a></p>'
        f'<p style="margin:0;color:#78716c;font-size:12px;word-break:break-all;">'
        f'Direct link: <a href="{e_url}" style="color:#0f766e;">{e_url}</a></p>'
        '</div></body></html>'
    )

    reply_to = [author_email] if author_email else None
    return subject, text_body, html_body, reply_to


def send_trip_comment_emails(comment, request=None):
    """Email trip participants (owner + collaborators, excluding the author) about a new comment or reply.

    Never raises on mail-server failure so posting comments is never blocked.
    """
    trip = comment.trip
    author_email = (getattr(comment.author, 'email', '') or '').strip().lower()
    origin = _site_origin(request)
    from_email = (
        getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        or getattr(settings, 'EMAIL_HOST_USER', None)
        or 'noreply@bldrdojo.com'
    )

    # Collect (recipient_email, recipient_url) deduplicated by lowercase email, excluding author.
    recipients = []
    seen = set()
    if author_email:
        seen.add(author_email)

    owner_email = (getattr(trip.user, 'email', '') or '').strip().lower()
    if owner_email and owner_email not in seen and comment.author_id != trip.user_id:
        seen.add(owner_email)
        recipients.append((owner_email, f'{origin}/app/trips/'))

    for share in trip.shares.all():
        s_email = (share.email or '').strip().lower()
        if not s_email or s_email in seen:
            continue
        if share.user_id and share.user_id == comment.author_id:
            continue
        seen.add(s_email)
        if not share.invite_token:
            share.save()
        recipients.append((s_email, f'{origin}/app/trips/?{urlencode({"invite": share.invite_token})}'))

    if not recipients:
        return {'sent': 0, 'failed': 0}

    sent = 0
    failed = 0
    try:
        connection = get_connection(fail_silently=False)
        messages = []
        for to_email, url in recipients:
            subject, text_body, html_body, reply_to = build_comment_email(comment, url, request=request)
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=from_email,
                to=[to_email],
                reply_to=reply_to,
                connection=connection,
            )
            msg.attach_alternative(html_body, 'text/html')
            messages.append(msg)
        sent = connection.send_messages(messages) or 0
    except Exception:  # noqa: BLE001
        logger.exception('Failed to send comment notification emails for comment %s on trip %s', comment.pk, trip.pk)
        failed = len(recipients) - sent

    return {'sent': sent, 'failed': failed}

