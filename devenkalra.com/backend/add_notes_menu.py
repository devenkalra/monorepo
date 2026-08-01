"""Create/attach Notebook → Notes page and menu item for the Notes app."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import Page, MenuItem

NOTES_CONTENT = """# Notes

Browse selected pages in a multi-level folder tree. Use the left panel to navigate folders and pages; the right panel shows a live preview.

Signed-in editors can add folders and link existing site pages into the tree.
"""

print("Setting up Notebook → Notes...")

page, created = Page.objects.get_or_create(
    slug='notes',
    defaults={
        'title': 'Notes',
        'category': 'Notebook',
        'content': NOTES_CONTENT,
        'roles_with_access': '',
    },
)
if created:
    print("Created page slug=notes")
else:
    print("Page slug=notes already exists")
    # Keep short intro if empty
    if not (page.content or '').strip():
        page.content = NOTES_CONTENT
        page.save(update_fields=['content'])

notebook, nb_created = MenuItem.objects.get_or_create(
    title='Notebook',
    parent=None,
    defaults={'page': None, 'order': 5, 'show_in_menu': True},
)
if nb_created:
    print("Created root menu 'Notebook'")
else:
    print("Root menu 'Notebook' already exists")

notes_menu = MenuItem.objects.filter(title='Notes', parent=notebook).order_by('id').first()
if notes_menu is None:
    notes_menu = MenuItem.objects.create(
        title='Notes',
        parent=notebook,
        page=page,
        order=1,
        show_in_menu=True,
    )
    print(f"Created menu Notebook → Notes (id={notes_menu.id})")
else:
    if notes_menu.page_id != page.id:
        notes_menu.page = page
        notes_menu.save()
        print(f"Linked existing Notes menu item (id={notes_menu.id}) to page notes")
    else:
        print(f"Notes menu already linked (id={notes_menu.id})")

print("Done. Open Notebook → Notes in the site menu.")
