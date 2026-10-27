"""Google OAuth (web flow) and People API client for the contacts sync."""
import base64
import json
import secrets
import time
import urllib.parse
import urllib.request

from django.conf import settings

from .models import ContactsState, GoogleAccount

READ_SCOPE = 'https://www.googleapis.com/auth/contacts.readonly'
WRITE_SCOPE = 'https://www.googleapis.com/auth/contacts'
IDENTITY_SCOPES = ['openid', 'email']
TOKEN_URI = 'https://oauth2.googleapis.com/token'
STATE_KEY = 'oauth_state'
STATE_TTL_S = 15 * 60


def _client():
    cid = getattr(settings, 'CONTACTS_GOOGLE_CLIENT_ID', '') or settings.GOOGLE_CLIENT_ID
    secret = getattr(settings, 'CONTACTS_GOOGLE_CLIENT_SECRET', '') or settings.GOOGLE_CLIENT_SECRET
    return cid, secret


def redirect_uri(request):
    return (getattr(settings, 'CONTACTS_OAUTH_REDIRECT_URI', '') or
            request.build_absolute_uri('/api/contacts/oauth/callback/'))


def authorize_url(request, write=False):
    cid, _ = _client()
    if not cid:
        raise ValueError('GOOGLE_CLIENT_ID is not configured.')
    state = secrets.token_urlsafe(24)
    ContactsState.put(STATE_KEY, {'state': state, 'write': bool(write), 'at': time.time()})
    params = {
        'client_id': cid,
        'redirect_uri': redirect_uri(request),
        'response_type': 'code',
        'scope': ' '.join([WRITE_SCOPE if write else READ_SCOPE] + IDENTITY_SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
        'state': state,
    }
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params)


def consume_state(state):
    """True once for the state issued by authorize_url (and not older than 15 minutes)."""
    saved = ContactsState.get(STATE_KEY) or {}
    ContactsState.put(STATE_KEY, {})
    return bool(state) and secrets.compare_digest(str(saved.get('state') or ''), str(state)) and \
        time.time() - float(saved.get('at') or 0) < STATE_TTL_S


def _post_token(fields):
    cid, secret = _client()
    data = urllib.parse.urlencode({'client_id': cid, 'client_secret': secret, **fields}).encode()
    req = urllib.request.Request(TOKEN_URI, data=data, method='POST',
                                 headers={'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _id_token_email(id_token):
    try:
        payload = id_token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get('email', '')
    except (IndexError, ValueError):
        return ''


def connect(code, request):
    tokens = _post_token({'code': code, 'redirect_uri': redirect_uri(request), 'grant_type': 'authorization_code'})
    refresh = tokens.get('refresh_token')
    if not refresh:
        raise ValueError('Google returned no refresh token. Remove the app at myaccount.google.com/permissions '
                         'and connect again.')
    account = GoogleAccount.objects.order_by('id').first() or GoogleAccount()
    account.email = _id_token_email(tokens.get('id_token', ''))
    account.refresh_token = refresh
    account.scopes = tokens.get('scope', '')
    account.last_error = ''
    account.save()
    GoogleAccount.objects.exclude(pk=account.pk).delete()
    return account


def people_service(account=None, token_file=None, write=False):
    """People API client from the stored account, or from a CLI-style token JSON file."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if token_file:
        creds = Credentials.from_authorized_user_file(str(token_file))
    else:
        account = account or GoogleAccount.objects.order_by('id').first()
        if not account or not account.refresh_token:
            raise ValueError('Connect Google first.')
        if write and not account.can_write:
            raise ValueError('Writeback needs write access to Google Contacts; grant it from the Overview tab.')
        cid, secret = _client()
        creds = Credentials(token=None, refresh_token=account.refresh_token, token_uri=TOKEN_URI,
                            client_id=cid, client_secret=secret)
    return build('people', 'v1', credentials=creds, cache_discovery=False)
