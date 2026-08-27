"""
Create CMS page + menu entry for Image Search (logged-in users).

Usage:
  python add_image_search_page.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from image_search.pages import ensure_image_search_page


def main():
    page, created, menu, menu_created = ensure_image_search_page()
    print(
        f"Page {page.slug}: {'created' if created else 'updated'}; "
        f"menu: {'created' if menu_created else 'updated'} (id={menu.id})"
    )


if __name__ == '__main__':
    main()
