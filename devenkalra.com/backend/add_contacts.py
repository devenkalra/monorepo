import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from add_contacts_page import create_contacts_page


if __name__ == '__main__':
    create_contacts_page()
