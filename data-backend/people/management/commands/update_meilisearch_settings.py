from django.core.management.base import BaseCommand
from people.sync import meili_sync

class Command(BaseCommand):
    help = 'Update MeiliSearch index settings (filterable attributes)'

    def handle(self, *args, **options):
        if not meili_sync.helper:
            self.stdout.write(self.style.ERROR('MeiliSearch is not configured'))
            return
        
        self.stdout.write('Updating MeiliSearch filterable attributes...')
        
        try:
            # Update filterable attributes
            meili_sync.helper.client.index(meili_sync.index_name).update_filterable_attributes([
                'type', 'tags', 'gender', 'first_name', 'last_name', 'user_id'
            ])
            
            self.stdout.write(self.style.SUCCESS('✓ Successfully updated MeiliSearch settings'))
            self.stdout.write('  Filterable attributes: type, tags, gender, first_name, last_name, user_id')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error updating MeiliSearch settings: {e}'))
