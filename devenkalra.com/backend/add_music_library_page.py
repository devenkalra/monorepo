"""
Create CMS page + menu entry for Music Library (authenticated users).

Usage:
  python add_music_library_page.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from audio_library.pages import ensure_music_library_page


def main():
    page, created, menu, menu_created = ensure_music_library_page()
    print(
        f"Page {page.slug}: {'created' if created else 'updated'}; "
        f"menu: {'created' if menu_created else 'updated'} (id={menu.id})"
    )


if __name__ == '__main__':
    main()
