from django.core.management.base import BaseCommand

from audio_library.pages import ensure_music_library_page


class Command(BaseCommand):
    help = 'Create or update the Music Library CMS page and menu item.'

    def handle(self, *args, **options):
        page, created, menu, menu_created = ensure_music_library_page()
        self.stdout.write(
            f"Page {page.slug}: {'created' if created else 'updated'}; "
            f"menu: {'created' if menu_created else 'updated'} (id={menu.id})"
        )
