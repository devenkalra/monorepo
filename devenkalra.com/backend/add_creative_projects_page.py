import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import Page, MenuItem

def create_creative_projects_page():
    print("Creating/updating Creative Projects page...")
    
    # 1. Create Page
    creative_page, created = Page.objects.update_or_create(
        slug="creative-projects",
        defaults={
            "title": "Creative Projects",
            "content": "This page displays tasks and subtasks from the ClickUp Creative Space.",
            "is_protected": True,
            "render_as_html": False
        }
    )
    print(f"Creative Projects page {'created' if created else 'updated'}.")

    # 2. Link to MenuItem
    try:
        # Search for Workflow category menu item
        m_workflow = MenuItem.objects.get(title="Workflow")
        
        menu_item, item_created = MenuItem.objects.get_or_create(
            title="Creative Projects",
            parent=m_workflow,
            defaults={'page': creative_page, 'order': 3}
        )
        # Update page pointer if item already existed
        if not item_created:
            menu_item.page = creative_page
            menu_item.save()
            
        print(f"Mapped Creative Projects menu item under Workflow ('{'created' if item_created else 'updated'}').")
        
    except MenuItem.DoesNotExist:
        print("Workflow menu item not found. Creating a root-level 'Creative Projects' menu item...")
        menu_item, item_created = MenuItem.objects.get_or_create(
            title="Creative Projects",
            defaults={'page': creative_page, 'order': 5}
        )
        if not item_created:
            menu_item.page = creative_page
            menu_item.save()
        print("Root level menu item configured.")

if __name__ == '__main__':
    create_creative_projects_page()
