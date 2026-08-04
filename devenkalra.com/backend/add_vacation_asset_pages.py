"""
Create CMS pages + menu entries for Vacation List and Asset Manager apps.

Usage (inside container or venv):
  python add_vacation_asset_pages.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import Page, MenuItem


APPS = [
    {
        'title': 'Vacation List',
        'slug': 'vacation-list',
        'content': 'Packing lists for trips. Manage catalog items and tags in admin; check off items here.',
        'roles_with_access': 'user,superuser',
    },
    {
        'title': 'Asset Manager',
        'slug': 'asset-manager',
        'content': 'Physical inventory: nested areas (folders) and items. Full editing also available in Django admin.',
        'roles_with_access': 'user,superuser',
    },
]


def ensure_apps_folder():
    folder, _ = MenuItem.objects.get_or_create(
        title='Apps',
        parent=None,
        defaults={
            'order': 90,
            'show_in_menu': True,
            'roles_with_access': 'superuser',
        },
    )
    if not folder.roles_with_access:
        folder.roles_with_access = 'superuser'
        folder.save(update_fields=['roles_with_access'])
    return folder


def main():
    apps_folder = ensure_apps_folder()
    for i, spec in enumerate(APPS):
        page, created = Page.objects.update_or_create(
            slug=spec['slug'],
            defaults={
                'title': spec['title'],
                'content': spec['content'],
                'roles_with_access': spec['roles_with_access'],
                'category': 'Apps',
            },
        )
        menu, menu_created = MenuItem.objects.update_or_create(
            page=page,
            parent=apps_folder,
            defaults={
                'title': spec['title'],
                'order': 10 + i,
                'show_in_menu': True,
                'roles_with_access': spec['roles_with_access'],
            },
        )
        action = 'created' if created else 'updated'
        menu_action = 'created' if menu_created else 'updated'
        print(f"Page {page.slug}: {action}; menu item: {menu_action} (id={menu.id})")


if __name__ == '__main__':
    main()
