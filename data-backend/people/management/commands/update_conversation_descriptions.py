"""
Django management command to update conversation descriptions with HTML content
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from people.models import Conversation


class Command(BaseCommand):
    help = 'Update conversation descriptions with HTML-formatted content'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--conversation-id',
            type=str,
            help='Update only a specific conversation by ID'
        )
        parser.add_argument(
            '--source',
            type=str,
            help='Update only conversations from a specific source'
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Update only conversations for a specific user (username or email)'
        )
    
    def handle(self, *args, **options):
        conversation_id = options.get('conversation_id')
        source = options.get('source')
        user_identifier = options.get('user')
        
        # Build queryset
        queryset = Conversation.objects.all()
        
        if conversation_id:
            queryset = queryset.filter(id=conversation_id)
        
        if source:
            queryset = queryset.filter(source=source)
        
        if user_identifier:
            try:
                user = User.objects.get(username=user_identifier)
            except User.DoesNotExist:
                try:
                    user = User.objects.get(email=user_identifier)
                except User.DoesNotExist:
                    raise CommandError(f'User not found: {user_identifier}')
            queryset = queryset.filter(user=user)
        
        total = queryset.count()
        self.stdout.write(f'Updating {total} conversation(s)...\n')
        
        updated = 0
        for conversation in queryset:
            try:
                # Generate and update description
                conversation.update_description()
                updated += 1
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ Updated: {conversation.display}'
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'  ✗ Failed to update {conversation.display}: {e}'
                    )
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Successfully updated {updated}/{total} conversations'
            )
        )
