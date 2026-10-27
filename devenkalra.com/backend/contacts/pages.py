from core.models import MenuItem, Page

PAGE_SLUG = 'contact-sync'
ROLES = 'superuser'


def ensure_contact_sync_page():
    """Create the page and menu item if missing; never overwrite edits made in the CMS."""
    page, created = Page.objects.get_or_create(
        slug=PAGE_SLUG,
        defaults={
            'title': 'Contact Sync',
            'content': '',
            'roles_with_access': ROLES,
            'category': 'Apps',
        },
    )
    menu = MenuItem.objects.filter(page=page).first()
    menu_created = menu is None
    if menu_created:
        menu = MenuItem.objects.create(page=page, parent=None, title='Contact Sync', order=87,
                                       show_in_menu=True, roles_with_access=ROLES)
    return page, created, menu, menu_created
