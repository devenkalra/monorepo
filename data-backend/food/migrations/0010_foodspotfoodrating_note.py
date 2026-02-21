# Add note field to FoodSpotFoodRating for reviews
# Made idempotent for production where column may already exist

from django.db import migrations, connection


def noop(apps, schema_editor):
    pass


def add_note_if_not_exists(apps, schema_editor):
    with connection.cursor() as cursor:
        cursor.execute("""
            ALTER TABLE food_foodspotfoodrating
            ADD COLUMN IF NOT EXISTS note TEXT NOT NULL DEFAULT ''
        """)


class Migration(migrations.Migration):

    dependencies = [
        ('food', '0009_alter_foodspotfoodrating_options_and_more'),
    ]

    operations = [
        migrations.RunPython(add_note_if_not_exists, noop),
    ]
