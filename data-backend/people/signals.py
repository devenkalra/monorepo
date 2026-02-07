from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from .models import Entity, Person, Note, Location, Movie, Book, Container, Asset, Org, EntityRelation, Tag
from .sync import neo4j_sync, meili_sync

print("=" * 80)
print("SIGNALS MODULE LOADED - Entity sync signals are registered")
print("=" * 80)

def _adjust_tag_counts(tag_name: str, delta: int, user):
    """Increment or decrement count for a tag and all its ancestors.
    `delta` should be +1 for addition, -1 for removal.
    """
    parts = tag_name.split('/')
    for i in range(1, len(parts) + 1):
        ancestor = '/'.join(parts[:i])
        tag_obj, _ = Tag.objects.get_or_create(name=ancestor, user=user)
        tag_obj.count = max(tag_obj.count + delta, 0)
        # Keep the tag even if count is 0 - user might want to reuse it
        tag_obj.save()

# Cache old tags before saving to compute differences
@receiver(pre_save, sender=Entity)
@receiver(pre_save, sender=Person)
@receiver(pre_save, sender=Note)
@receiver(pre_save, sender=Location)
@receiver(pre_save, sender=Movie)
@receiver(pre_save, sender=Book)
@receiver(pre_save, sender=Container)
@receiver(pre_save, sender=Asset)
@receiver(pre_save, sender=Org)
def cache_entity_tags(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._old_tags = set(old.tags or [])
        except sender.DoesNotExist:
            instance._old_tags = set()
    else:
        instance._old_tags = set()

# Sync entity and manage tag counts after save
@receiver(post_save, sender=Entity)
@receiver(post_save, sender=Person)
@receiver(post_save, sender=Note)
@receiver(post_save, sender=Location)
@receiver(post_save, sender=Movie)
@receiver(post_save, sender=Book)
@receiver(post_save, sender=Container)
@receiver(post_save, sender=Asset)
@receiver(post_save, sender=Org)
def sync_entity_save(sender, instance, created=False, **kwargs):
    # Sync with external services
    # print(f"Signal: Syncing entity {instance.id} to external services")  # Too verbose during import
    neo4j_sync.sync_entity(instance)
    meili_sync.sync_entity(instance)

    # Update tag counts (including hierarchy)
    new_tags = set(instance.tags or [])
    old_tags = getattr(instance, '_old_tags', set())
    added = new_tags - old_tags
    removed = old_tags - new_tags
    for tag_name in added:
        _adjust_tag_counts(tag_name, +1, instance.user)
    for tag_name in removed:
        _adjust_tag_counts(tag_name, -1, instance.user)

# Sync entity deletion and decrement tag counts (including hierarchy)
@receiver(post_delete, sender=Entity)
@receiver(post_delete, sender=Person)
@receiver(post_delete, sender=Note)
@receiver(post_delete, sender=Location)
@receiver(post_delete, sender=Movie)
@receiver(post_delete, sender=Book)
@receiver(post_delete, sender=Container)
@receiver(post_delete, sender=Asset)
@receiver(post_delete, sender=Org)
def sync_entity_delete(sender, instance, **kwargs):
    print(f"Signal: Deleting entity {instance.id} from external services")
    neo4j_sync.delete_entity(instance.id)
    meili_sync.delete_entity(instance.id)
    for tag_name in (instance.tags or []):
        _adjust_tag_counts(tag_name, -1, instance.user)

# Relation sync signals (unchanged)
@receiver(post_save, sender=EntityRelation)
def sync_relation_save(sender, instance, **kwargs):
    neo4j_sync.sync_relation(instance.from_entity.id, instance.to_entity.id, instance.relation_type)

@receiver(post_delete, sender=EntityRelation)
def sync_relation_delete(sender, instance, **kwargs):
    neo4j_sync.delete_relation(instance.from_entity.id, instance.to_entity.id, instance.relation_type)


# Note signals for vector search
@receiver(post_save, sender=Note)
def sync_note_save(sender, instance, created, **kwargs):
    """Auto-sync Note to vector database for semantic search"""
    try:
        from .vector_search_client import get_vector_search_client
        client = get_vector_search_client()
        if client.health_check():
            client.index_note(instance)
    except Exception as e:
        print(f"Error syncing note to vector DB: {e}")


@receiver(post_delete, sender=Note)
def sync_note_delete(sender, instance, **kwargs):
    """Remove Note from vector database"""
    try:
        from .vector_search_client import get_vector_search_client
        client = get_vector_search_client()
        if client.health_check():
            client.delete_note(instance.id)
    except Exception as e:
        print(f"Error deleting note from vector DB: {e}")
