from django.core.management.base import BaseCommand

from email_processor.sync import get_active_mailbox, reconcile_mailbox


class Command(BaseCommand):
    help = 'Reconcile Gmail history into the email processor queue'

    def handle(self, *args, **options):
        mailbox = get_active_mailbox()
        if not mailbox:
            self.stderr.write('No active mailbox')
            return
        result = reconcile_mailbox(mailbox)
        self.stdout.write(self.style.SUCCESS(str(result)))
