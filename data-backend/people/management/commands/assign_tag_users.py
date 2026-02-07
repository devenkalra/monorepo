from django.core.management.base import BaseCommand
from people.models import Entity, Tag


class Command(BaseCommand):
    help = 'Assign users to existing tags based on entities that use them'

    def handle(self, *args, **options):
        # Get all entities with their tags
        entities = Entity.objects.all()
        tag_users = {}  # tag_name -> set of user_ids
        
        for entity in entities:
            if entity.tags and entity.user_id:
                for tag_name in entity.tags:
                    if tag_name not in tag_users:
                        tag_users[tag_name] = set()
                    tag_users[tag_name].add(entity.user_id)
        
        self.stdout.write(f'Found {len(tag_users)} unique tags across all entities')
        
        # For each tag, create per-user copies
        existing_tags = list(Tag.objects.all())
        created_count = 0
        
        for tag in existing_tags:
            users = tag_users.get(tag.name, set())
            if not users:
                self.stdout.write(self.style.WARNING(f'Tag "{tag.name}" has no users, skipping'))
                continue
                
            for user_id in users:
                # Check if tag already exists for this user
                if not Tag.objects.filter(name=tag.name, user_id=user_id).exists():
                    Tag.objects.create(
                        name=tag.name,
                        user_id=user_id,
                        count=0  # Will be recalculated by signals
                    )
                    created_count += 1
        
        # Delete tags without users
        Tag.objects.filter(user__isnull=True).delete()
        
        self.stdout.write(self.style.SUCCESS(f'Created {created_count} user-specific tags'))
        
        # Recalculate counts
        self.stdout.write('Recalculating tag counts...')
        for tag in Tag.objects.all():
            count = Entity.objects.filter(user=tag.user, tags__contains=[tag.name]).count()
            tag.count = count
            tag.save()
        
        self.stdout.write(self.style.SUCCESS('Done!'))
