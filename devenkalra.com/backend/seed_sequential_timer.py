import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import Page, MenuItem

print("Seeding Sequential Timer page and menu item...")

# 1. Read HTML page content
html_path = os.path.join(os.path.dirname(__file__), 'seed_data', 'sequential-timer.html')
if not os.path.exists(html_path):
    raise FileNotFoundError(f"Seeding file not found at {html_path}")

with open(html_path, 'r', encoding='utf-8') as f:
    html_content = f.read()

# 2. Create or update Page model
p_seq_timer, created = Page.objects.update_or_create(
    slug='sequential-timer',
    defaults={
        'title': 'Sequential Timer',
        'content': html_content,
        'render_as_html': True,
        'is_protected': False
    }
)

if created:
    print("Created Page 'sequential-timer'")
else:
    print("Updated Page 'sequential-timer'")

# 3. Wire into navigation menus
try:
    # Find Personal Life menu
    m_personal = MenuItem.objects.get(title='Personal Life', parent=None)
    
    # Get or create Custom Apps submenu
    m_custom_apps, c_custom = MenuItem.objects.get_or_create(
        title='Custom Apps',
        parent=m_personal,
        defaults={'page': None, 'order': 4}
    )
    if c_custom:
        print("Created menu item 'Custom Apps'")
        
    # Get or create Sequential Timer submenu
    m_widget, c_widget = MenuItem.objects.get_or_create(
        title='Sequential Timer',
        parent=m_custom_apps,
        defaults={
            'page': p_seq_timer,
            'order': 2
        }
    )
    if c_widget:
        print("Created menu item 'Sequential Timer'")
    else:
        # If it already exists, make sure the page relation is correctly updated
        m_widget.page = p_seq_timer
        m_widget.save()
        print("Updated menu item 'Sequential Timer' association")
        
    print("Database seeding of Sequential Timer completed successfully!")

except MenuItem.DoesNotExist:
    print("Error: 'Personal Life' root menu item not found. Please run seed.py first.")
except Exception as e:
    print(f"Error during menu linking: {e}")
