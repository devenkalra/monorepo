# Generated migration for UserProfile with displayname
# Made idempotent for production where table may already exist

from django.db import migrations


def create_userprofile_if_not_exists(apps, schema_editor):
    """Create people_userprofile table if it doesn't exist (idempotent)."""
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'people_userprofile'
        """)
        if cursor.fetchone():
            return
        cursor.execute("""
            CREATE TABLE people_userprofile (
                id BIGSERIAL PRIMARY KEY,
                displayname VARCHAR(255) NULL,
                user_id INTEGER NOT NULL UNIQUE REFERENCES auth_user(id) ON DELETE CASCADE
            )
        """)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency('auth.User'),
        ('people', '0002_update_tag_for_production'),
    ]

    operations = [
        migrations.RunPython(create_userprofile_if_not_exists, noop),
    ]
