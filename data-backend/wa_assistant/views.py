"""
WhatsApp webhook views - verification (GET) and message reception (POST).
"""
import json
import logging
from datetime import datetime
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from .models import WhatsAppMessage, WhatsAppMedia

logger = logging.getLogger(__name__)


def _get_verify_token():
    return (
        getattr(settings, 'WHATSAPP_WEBHOOK_VERIFY_TOKEN', None)
        or __import__('os').environ.get('WHATSAPP_WEBHOOK_VERIFY_TOKEN', '')
    )


def webhook(request):
    """WhatsApp webhook - handles GET (verification) and POST (messages)."""
    if request.method == 'GET':
        return _webhook_verify(request)
    if request.method == 'POST':
        return _webhook_receive(request)
    return HttpResponse('Method Not Allowed', status=405)


def _webhook_verify(request):
    """
    WhatsApp webhook verification (GET).
    Meta sends: hub.mode, hub.verify_token, hub.challenge
    We must verify hub.verify_token matches our token and return hub.challenge.
    """
    mode = request.GET.get('hub.mode')
    token = request.GET.get('hub.verify_token')
    challenge = request.GET.get('hub.challenge')

    expected_token = _get_verify_token()
    if not expected_token:
        logger.warning('WHATSAPP_WEBHOOK_VERIFY_TOKEN not configured')
        return HttpResponse('Verification token not configured', status=500)

    if mode == 'subscribe' and token == expected_token:
        return HttpResponse(challenge or '', content_type='text/plain')
    return HttpResponse('Forbidden', status=403)


def _webhook_receive(request):
    """
    WhatsApp webhook - receive messages and events (POST).
    """
    try:
        body = json.loads(request.body)
    except Exception as e:
        logger.warning('Invalid webhook body: %s', e)
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # WhatsApp sends {"object": "whatsapp_business_account", "entry": [...]}
    if body.get('object') != 'whatsapp_business_account':
        return HttpResponse('', status=200)  # Ignore non-WA events

    for entry in body.get('entry', []):
        for change in entry.get('changes', []):
            if change.get('field') != 'messages':
                continue
            value = change.get('value', {})
            _process_messages(value)

    return HttpResponse('', status=200)


def _process_messages(value):
    """Process incoming messages from webhook payload."""
    metadata = value.get('metadata', {})
    phone_id = metadata.get('phone_number_id', '')
    wa_to = metadata.get('display_phone_number', '') or phone_id

    for msg in value.get('messages', []):
        _process_one_message(msg, phone_id, wa_to)


def _process_one_message(msg: dict, phone_id: str, wa_to: str):
    """Process a single message and save to DB."""
    msg_id = msg.get('id')
    if not msg_id:
        return

    if WhatsAppMessage.objects.filter(wa_message_id=msg_id).exists():
        return  # Already processed

    wa_from = msg.get('from', '')
    ts = msg.get('timestamp')
    wa_timestamp = datetime.fromtimestamp(ts) if ts else None

    msg_type = msg.get('type', 'unknown')
    text_body = ''
    if msg_type == 'text':
        text_body = msg.get('text', {}).get('body', '')

    # Create message record
    wa_msg = WhatsAppMessage.objects.create(
        wa_message_id=msg_id,
        wa_from=wa_from,
        wa_to=wa_to or phone_id,
        wa_timestamp=wa_timestamp,
        msg_type=msg_type,
        text_body=text_body,
        raw_payload=msg,
    )

    # Process media
    media_key = msg_type if msg_type in ('image', 'audio', 'video', 'document', 'sticker') else None
    if media_key:
        media_obj = msg.get(media_key, {})
        media_id = media_obj.get('id')
        if media_id:
            from .tasks import download_whatsapp_media
            try:
                download_whatsapp_media.delay(str(wa_msg.id), media_id, media_obj)
            except Exception:
                download_whatsapp_media(str(wa_msg.id), media_id, media_obj)


