import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import Page, MenuItem

print("Adding Time Keeper page and menu items...")

# 1. Create Page
p, created = Page.objects.get_or_create(
    slug='time-keeper',
    defaults={
        'title': 'Time Keeping Widget',
        'content': '# Time Keeping Widget\nThis page hosts a high-end timekeeping dashboard featuring a local Clock, a World Clock with multiple timezones, a Stopwatch, and a countdown Timer.\n\nThe widgets feature circular progress visualizers that let you see values from far away, complete with sub-dials showing adjustable temporal resolutions.',
        'is_protected': False
    }
)
if created:
    print("Created Page 'time-keeper'")
else:
    print("Page 'time-keeper' already exists")

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
        
    # 4. Create Time Keeping Widget under Custom Apps
    m_widget, c_widget = MenuItem.objects.get_or_create(
        title='Time Keeping Widget',
        parent=m_custom_apps,
        defaults={'page': p, 'order': 1}
    )
    if c_widget:
        print("Created menu item 'Time Keeping Widget'")
    else:
        print("Menu item 'Time Keeping Widget' already exists")
except MenuItem.DoesNotExist:
    print("Error: 'Personal Life' root menu item not found. Please run seed.py first.")
