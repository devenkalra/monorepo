from django.core.management.base import BaseCommand

from email_processor.sync import renew_watch


class Command(BaseCommand):
    help = 'Renew Gmail users.watch registration'

    def handle(self, *args, **options):
        result = renew_watch()
        self.stdout.write(self.style.SUCCESS(str(result)))
