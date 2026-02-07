# Migration to update Tag model for production databases that have the old structure
# This migration is safe to run on both old and new databases

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def check_and_migrate_tags(apps, schema_editor):
    """
    Check if Tag table has the old structure and migrate if needed.
    This is safe to run on both old and new databases.
    """
    from django.db import connection
    
    with connection.cursor() as cursor:
        # Check if 'id' column exists in people_tag
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='people_tag' AND column_name='id'
        """)
        has_id_column = cursor.fetchone() is not None
        
        # Check if 'user_id' column exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='people_tag' AND column_name='user_id'
        """)
        has_user_column = cursor.fetchone() is not None
        
        # If both columns exist, migration already done
        if has_id_column and has_user_column:
            print("Tag table already has correct structure, skipping migration")
            return
        
        print("Migrating Tag table from old structure to new structure...")
        
        # Old structure detected, perform migration
        Entity = apps.get_model('people', 'Entity')
        Tag = apps.get_model('people', 'Tag')
        
        # Get all entities with their tags
        entities = Entity.objects.all()
        tag_users = {}  # tag_name -> set of user_ids
        
        for entity in entities:
            if entity.tags and entity.user_id:
                for tag_name in entity.tags:
                    if tag_name not in tag_users:
                        tag_users[tag_name] = set()
                    tag_users[tag_name].add(entity.user_id)
        
        # Store existing tags
        existing_tags = list(Tag.objects.all())
        
        # Drop old primary key
        cursor.execute('ALTER TABLE people_tag DROP CONSTRAINT IF EXISTS people_tag_pkey CASCADE;')
        
        # Add id column if it doesn't exist
        if not has_id_column:
            cursor.execute('ALTER TABLE people_tag ADD COLUMN id SERIAL;')
        
        # Add user_id column if it doesn't exist
        if not has_user_column:
            cursor.execute(f'''
                ALTER TABLE people_tag 
                ADD COLUMN user_id INTEGER REFERENCES {connection.ops.quote_name("auth_user")} (id) 
                ON DELETE CASCADE;
            ''')
        
        # Make id the primary key
        cursor.execute('ALTER TABLE people_tag ADD PRIMARY KEY (id);')
        
        # Change name to regular field (remove primary key constraint if it exists)
        cursor.execute('ALTER TABLE people_tag ALTER COLUMN name DROP DEFAULT;')
        
        # Clear all tags and recreate with user associations
        Tag.objects.all().delete()
        
        for tag in existing_tags:
            users = tag_users.get(tag.name, set())
            if users:
                for user_id in users:
                    Tag.objects.create(
                        name=tag.name,
                        user_id=user_id,
                        count=tag.count
                    )
            else:
                # Tag not used by any entity, keep it without user
                Tag.objects.create(
                    name=tag.name,
                    user_id=None,
                    count=0
                )
        
        # Add unique constraint
        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS people_tag_name_user_id_unique 
            ON people_tag (name, user_id);
        ''')
        
        print(f"Migration complete: Created {Tag.objects.count()} tag records")


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(
            code=check_and_migrate_tags,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
