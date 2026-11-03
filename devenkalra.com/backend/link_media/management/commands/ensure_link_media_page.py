from django.core.management.base import BaseCommand

from link_media.pages import ensure_link_media_page


class Command(BaseCommand):
    help = 'Create or update the Link Media CMS page and menu item.'

    def handle(self, *args, **options):
        page, created, menu, menu_created = ensure_link_media_page()
        self.stdout.write(
            f"Page {page.slug}: {'created' if created else 'updated'}; "
            f"menu: {'created' if menu_created else 'updated'} (id={menu.id})"
        )
