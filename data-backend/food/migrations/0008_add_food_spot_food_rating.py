# Generated manually for FoodSpotFoodRating model
# Made idempotent for production where table may already exist

from django.db import migrations, connection


def noop(apps, schema_editor):
    pass


def create_foodspotfoodrating_if_not_exists(apps, schema_editor):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'food_foodspotfoodrating'
        """)
        if cursor.fetchone():
            return
        cursor.execute("""
            CREATE TABLE food_foodspotfoodrating (
                id UUID PRIMARY KEY,
                rating SMALLINT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                modified_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                added_by_id INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
                food_id UUID NOT NULL REFERENCES food_food(id) ON DELETE CASCADE,
                food_spot_id UUID NOT NULL REFERENCES food_foodspot(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX unique_food_spot_rating_per_user
            ON food_foodspotfoodrating (food_id, food_spot_id, added_by_id)
        """)
        cursor.execute("""
            CREATE INDEX food_foodsp_food_sp_3a8b2a_idx
            ON food_foodspotfoodrating (food_spot_id, food_id)
        """)


class Migration(migrations.Migration):

    dependencies = [
        ('food', '0007_add_private_field'),
    ]

    operations = [
        migrations.RunPython(create_foodspotfoodrating_if_not_exists, noop),
    ]
