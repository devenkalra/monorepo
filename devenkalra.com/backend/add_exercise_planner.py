import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import Page, MenuItem

print("Adding Exercise Planner page and menu items...")

# 1. Create Page
p, created = Page.objects.get_or_create(
    slug='exercise-planner',
    defaults={
        'title': 'Exercise Planner & Timer',
        'content': '# Exercise Planner & Timer\nThis page hosts a high-end exercise event planner and active workout player featuring multi-step exercises, custom hold timers, rep counters, visual concentric timers, and auto-generated audio cues.\n\nDefine your workout steps, add illustration media (images, mp4s, or YouTube links) for form check, and click Start Workout to begin your session.',
        'is_protected': False
    }
)
if created:
    print("Created Page 'exercise-planner'")
else:
    # Ensure the title is correct if it already exists
    p.title = 'Exercise Planner & Timer'
    p.save()
    print("Page 'exercise-planner' updated")

# 2. Get Personal Life root menu
try:
    m_personal = MenuItem.objects.get(title='Personal Life', parent=None)
    
    # 3. Create Custom Apps under Personal Life
    m_custom_apps, c_custom = MenuItem.objects.get_or_create(
        title='Custom Apps',
        parent=m_personal,
        defaults={'page': None, 'order': 4}
    )
    if c_custom:
        print("Created menu item 'Custom Apps'")
    else:
        print("Menu item 'Custom Apps' already exists")
        
    # 4. Create Exercise Planner & Timer under Custom Apps
    m_widget, c_widget = MenuItem.objects.get_or_create(
        title='Exercise Planner',
        parent=m_custom_apps,
        defaults={'page': p, 'order': 3}
    )
    if c_widget:
        print("Created menu item 'Exercise Planner'")
    else:
        m_widget.page = p
        m_widget.order = 3
        m_widget.save()
        print("Updated menu item 'Exercise Planner'")
except MenuItem.DoesNotExist:
    print("Error: 'Personal Life' root menu item not found. Please run seed.py first.")
except Exception as e:
    print(f"Error during menu linking: {e}")
