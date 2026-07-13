"""Celery tasks for wa_assistant - async media download."""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def download_whatsapp_media(message_id, media_id, media_obj):
    """
    Download media from WhatsApp and save to hierarchical storage.
    Called asynchronously so webhook can return quickly.
    """
    from .models import WhatsAppMessage, WhatsAppMedia
    from .storage import save_bytes_deduplicated
    from .whatsapp_client import download_media

    try:
        wa_msg = WhatsAppMessage.objects.get(id=message_id)
    except WhatsAppMessage.DoesNotExist:
        logger.warning('Message %s not found for media download', message_id)
        return

    if WhatsAppMedia.objects.filter(message=wa_msg, wa_media_id=media_id).exists():
        return  # Already downloaded

    content, mime_type = download_media(media_id)
    if not content:
        logger.warning('Failed to download media %s', media_id)
        return

    ext_map = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/webp': '.webp',
        'audio/ogg': '.ogg',
        'video/mp4': '.mp4',
        'application/pdf': '.pdf',
    }
    ext = ext_map.get(mime_type, '.bin')
    filename = f"wa_{media_id}{ext}"

    result = save_bytes_deduplicated(content, filename, subdir='wa_assistant')

    WhatsAppMedia.objects.create(
        message=wa_msg,
        wa_media_id=media_id,
        mime_type=mime_type or '',
        sha256=result.get('sha256', ''),
        path=result['path'],
        url=result['url'],
        thumbnail_url=result.get('thumbnail_url', ''),
        file_size=len(content),
    )
    logger.info('Downloaded media %s for message %s', media_id, message_id)
