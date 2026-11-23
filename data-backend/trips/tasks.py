from celery import shared_task


@shared_task(bind=True, name='trips.generate_suggestions')
def generate_suggestions(self, batch_id: int):
    from . import ai
    from .models import TripSuggestionBatch

    batch = TripSuggestionBatch.objects.select_related('trip', 'day', 'user').filter(pk=batch_id).first()
    if batch is None:
        return {'ok': False, 'error': 'missing'}
    try:
        ai.generate(batch)
    except Exception as exc:  # noqa: BLE001 - any failure is shown to the user on the batch
        batch.status = TripSuggestionBatch.STATUS_FAILED
        batch.error = str(exc)[:1000]
    else:
        batch.status = TripSuggestionBatch.STATUS_DONE
    batch.save(update_fields=['status', 'error', 'modified_on'])
    return {'ok': batch.status == TripSuggestionBatch.STATUS_DONE}
