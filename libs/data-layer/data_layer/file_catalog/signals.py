from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import File, Folder
from .sync_engine import engine
import logging

logger = logging.getLogger(__name__)

# --- Folder Signals ---

@receiver(post_save, sender=Folder)
def sync_folder_save(sender, instance, **kwargs):
    try:
        # Sync to Graph
        engine.sync_folder_graph(instance)
        # Sync to Search Index
        engine.sync_folder_search(instance)
    except Exception as e:
        logger.error(f"Failed to sync Folder {instance.id}: {e}")

@receiver(post_delete, sender=Folder)
def sync_folder_delete(sender, instance, **kwargs):
    try:
        engine.delete_node(str(instance.id))
        engine.delete_document('folders', str(instance.id))
    except Exception as e:
        logger.error(f"Failed to delete Folder {instance.id} from sync targets: {e}")

# --- File Signals ---

@receiver(post_save, sender=File)
def sync_file_save(sender, instance, **kwargs):
    try:
        engine.sync_file_graph(instance)
        engine.sync_file_search(instance)
    except Exception as e:
        logger.error(f"Failed to sync File {instance.id}: {e}")

@receiver(post_delete, sender=File)
def sync_file_delete(sender, instance, **kwargs):
    try:
        engine.delete_node(str(instance.id))
        engine.delete_document('files', str(instance.id))
    except Exception as e:
        logger.error(f"Failed to delete File {instance.id} from sync targets: {e}")