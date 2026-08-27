from django.core.management.base import BaseCommand

from image_search.pages import ensure_image_search_page


class Command(BaseCommand):
    help = 'Create or update the Image Search CMS page and menu item.'

    def handle(self, *args, **options):
        page, created, menu, menu_created = ensure_image_search_page()
        self.stdout.write(
            f"Page {page.slug}: {'created' if created else 'updated'}; "
            f"menu: {'created' if menu_created else 'updated'} (id={menu.id})"
        )
