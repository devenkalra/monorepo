"""
Create CMS page + menu entry for Email Processor (superuser only).

Usage:
  python add_email_processor_page.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import Page, MenuItem


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
    page, created = Page.objects.update_or_create(
        slug='email-processor',
        defaults={
            'title': 'Email Processor',
            'content': (
                'Intelligent Gmail processor: watch inbox, classify with OpenAI, '
                'route writing ideas to ClickUp and images to Static Files. '
                'Superuser review queue for low-confidence items.'
            ),
            'roles_with_access': 'superuser',
            'category': 'Apps',
        },
    )
    menu, menu_created = MenuItem.objects.update_or_create(
        page=page,
        parent=apps_folder,
        defaults={
            'title': 'Email Processor',
            'order': 30,
            'show_in_menu': True,
            'roles_with_access': 'superuser',
        },
    )
    print(
        f"Page {page.slug}: {'created' if created else 'updated'}; "
        f"menu: {'created' if menu_created else 'updated'} (id={menu.id})"
    )


if __name__ == '__main__':
    main()
