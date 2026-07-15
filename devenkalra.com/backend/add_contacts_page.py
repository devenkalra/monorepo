import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import Page, MenuItem


def create_contacts_page():
    print("Creating/updating Contacts page...")

    contacts_page, created = Page.objects.update_or_create(
        slug='contacts',
        defaults={
            'title': 'Contacts',
            'content': 'This page displays contacts from ClickUp Space \'Consulting\' and List \'Contacts\'.',
            'roles_with_access': 'user,superuser',
            'render_as_html': False
        }
    )
    print(f"Contacts page {'created' if created else 'updated'}.")

    try:
        workflow_menu = MenuItem.objects.get(title='Workflow')

        menu_item, item_created = MenuItem.objects.get_or_create(
            title='Contacts',
            parent=workflow_menu,
            defaults={'page': contacts_page, 'order': 4}
        )

        if not item_created:
            menu_item.page = contacts_page
            menu_item.order = 4
            menu_item.save()

        print(f"Mapped Contacts menu item under Workflow ({'created' if item_created else 'updated'}).")
    except MenuItem.DoesNotExist:
        print("Workflow menu item not found. Creating root-level 'Contacts' menu item...")
        menu_item, item_created = MenuItem.objects.get_or_create(
            title='Contacts',
            defaults={'page': contacts_page, 'order': 6}
        )
        if not item_created:
            menu_item.page = contacts_page
            menu_item.order = 6
            menu_item.save()
        print("Root-level Contacts menu item configured.")


if __name__ == '__main__':
    create_contacts_page()
