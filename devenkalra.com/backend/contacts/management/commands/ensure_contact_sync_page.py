from django.core.management.base import BaseCommand

from contacts.pages import ensure_contact_sync_page


class Command(BaseCommand):
    help = 'Create the Contact Sync CMS page and menu item if they are missing.'

    def handle(self, *args, **options):
        page, created, menu, menu_created = ensure_contact_sync_page()
        self.stdout.write(
            f"Page {page.slug}: {'created' if created else 'exists'}; "
            f"menu: {'created' if menu_created else 'exists'} (id={menu.id})"
        )
