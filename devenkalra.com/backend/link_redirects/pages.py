from core.models import MenuItem, Page


PAGE_SLUG = 'link-redirects'
ROLES = 'superuser'


def ensure_link_redirects_page():
    page, created = Page.objects.update_or_create(
        slug=PAGE_SLUG,
        defaults={
            'title': 'Link Redirects',
            'content': (
                'Create short root URLs that forward elsewhere '
                '(https://devenkalra.com/rsvp → Google Form). Superuser only.'
            ),
            'roles_with_access': ROLES,
            'category': 'Apps',
        },
    )
    menu, menu_created = MenuItem.objects.update_or_create(
        page=page,
        parent=None,
        defaults={
            'title': 'Link Redirects',
            'order': 88,
            'show_in_menu': True,
            'roles_with_access': ROLES,
        },
    )
    MenuItem.objects.filter(page=page).exclude(pk=menu.pk).delete()
    return page, created, menu, menu_created
