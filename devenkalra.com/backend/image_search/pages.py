from core.models import MenuItem, Page


PAGE_SLUG = 'image-search'
ROLES = 'user,superuser'


def ensure_image_search_page():
    page, created = Page.objects.update_or_create(
        slug=PAGE_SLUG,
        defaults={
            'title': 'Image Search',
            'content': (
                'Search Bing images, filter by size and quality, and download matches. '
                'Sign in required.'
            ),
            'roles_with_access': ROLES,
            'category': 'Apps',
        },
    )
    menu, menu_created = MenuItem.objects.update_or_create(
        page=page,
        parent=None,
        defaults={
            'title': 'Image Search',
            'order': 86,
            'show_in_menu': True,
            'roles_with_access': ROLES,
        },
    )
    MenuItem.objects.filter(page=page).exclude(pk=menu.pk).delete()
    return page, created, menu, menu_created
