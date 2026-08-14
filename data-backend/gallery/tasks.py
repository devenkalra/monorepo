from celery import shared_task


@shared_task(bind=True, name='gallery.generate_item_thumbnail')
def generate_item_thumbnail(self, item_id: str):
    from .models import GalleryItem
    from .utils import generate_video_thumbnail

    try:
        item = GalleryItem.objects.get(id=item_id)
    except GalleryItem.DoesNotExist:
        return {'ok': False, 'error': 'missing'}

    if not item.url:
        item.thumbnail_status = 'n/a'
        item.save(update_fields=['thumbnail_status'])
        return {'ok': False, 'error': 'external'}

    thumb = generate_video_thumbnail(item.url)
    if thumb:
        item.thumbnail_url = thumb
        item.thumbnail_status = 'ready'
        item.save(update_fields=['thumbnail_url', 'thumbnail_status'])
        return {'ok': True, 'thumbnail_url': thumb}

    item.thumbnail_status = 'failed'
    item.save(update_fields=['thumbnail_status'])
    return {'ok': False, 'error': 'ffmpeg'}
