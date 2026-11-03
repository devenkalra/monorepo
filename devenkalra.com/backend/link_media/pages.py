from core.models import MenuItem, Page


PAGE_SLUG = 'link-media'
ROLES = 'superuser'


def ensure_link_media_page():
    page, created = Page.objects.update_or_create(
        slug=PAGE_SLUG,
        defaults={
            'title': 'Link Media',
            'content': (
                'Upload files and get short public URLs for email '
                '(https://devenkalra.com/f/your-slug). Superuser only.'
            ),
            'roles_with_access': ROLES,
            'category': 'Apps',
        },
    )
    menu, menu_created = MenuItem.objects.update_or_create(
        page=page,
        parent=None,
        defaults={
            'title': 'Link Media',
            'order': 87,
            'show_in_menu': True,
            'roles_with_access': ROLES,
        },
    )
    MenuItem.objects.filter(page=page).exclude(pk=menu.pk).delete()
    return page, created, menu, menu_created
