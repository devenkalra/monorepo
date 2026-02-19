from django.core.management.base import BaseCommand
from people.models import Entity
from people.sync import meili_sync


class Command(BaseCommand):
    help = 'Re-index all entities in MeiliSearch. Use --clear-first to remove existing documents before reindexing (avoids duplicates after restore).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-first',
            action='store_true',
            help='Delete all documents from the index before reindexing (use after restore to avoid duplicates)',
        )

    def handle(self, *args, **options):
        if options.get('clear_first') and meili_sync.helper:
            self.stdout.write('Clearing existing documents from MeiliSearch index...')
            try:
                task = meili_sync.helper.client.index(meili_sync.index_name).delete_all_documents()
                if hasattr(task, 'task_uid'):
                    self.stdout.write(f'  Delete task queued (task_uid: {task.task_uid})')
                self.stdout.write(self.style.SUCCESS('  Index cleared'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Could not clear index: {e}'))

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
