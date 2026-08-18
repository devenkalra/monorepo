from core.models import MenuItem, Page


def ensure_music_library_page():
    page, created = Page.objects.update_or_create(
        slug='music-library',
        defaults={
            'title': 'Music Library',
            'content': (
                'Browse and play MP3s from selected NAS folders.'
            ),
            'roles_with_access': '',
            'category': 'Music',
        },
    )
    menu, menu_created = MenuItem.objects.update_or_create(
        page=page,
        parent=None,
        defaults={
            'title': 'Music Library',
            'order': 85,
            'show_in_menu': True,
            'roles_with_access': '',
        },
    )
    return page, created, menu, menu_created
