from django.core.management.base import BaseCommand
from people.models import Entity
from people.sync import meili_sync

class Command(BaseCommand):
    help = 'Re-index all entities in MeiliSearch with user_id field'

    def handle(self, *args, **options):
        entities = Entity.objects.all()
        total = entities.count()
        
        self.stdout.write(f'Re-indexing {total} entities in MeiliSearch...')
        
        for i, entity in enumerate(entities, 1):
            try:
                meili_sync.sync_entity(entity)
                if i % 10 == 0:
                    self.stdout.write(f'  Processed {i}/{total}...')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error syncing entity {entity.id}: {e}'))
        
        self.stdout.write(self.style.SUCCESS(f'✓ Successfully re-indexed {total} entities'))
