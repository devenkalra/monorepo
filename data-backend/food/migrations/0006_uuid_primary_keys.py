# Migrate food app primary keys from integer to UUID.
# Uses PostgreSQL-specific SQL. Back up your database before running.

import uuid
from django.db import migrations, models


def _drop_fk_if_exists(cursor, table, column):
    """Drop FK constraint on table.column if it exists. Returns constraint name or None."""
    cursor.execute("""
        SELECT conname FROM pg_constraint c
        JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = %s AND a.attname = %s AND c.contype = 'f'
    """, [table, column])
    row = cursor.fetchone()
    if row:
        from psycopg2 import sql
        cursor.execute(
            sql.SQL("ALTER TABLE {} DROP CONSTRAINT IF EXISTS {}").format(
                sql.Identifier(table), sql.Identifier(row[0])
            )
        )
        return row[0]
    return None


def migrate_to_uuid(apps, schema_editor):
    """Convert integer PKs to UUIDs for all food models."""
    from django.db import connection

    with connection.cursor() as cursor:
        # 1. FoodSpot
        cursor.execute("ALTER TABLE food_foodspot ADD COLUMN id_uuid UUID UNIQUE")
        cursor.execute("UPDATE food_foodspot SET id_uuid = gen_random_uuid()")

        # Update food_media
        cursor.execute("ALTER TABLE food_media ADD COLUMN food_spot_id_uuid UUID")
        cursor.execute("""
            UPDATE food_media m SET food_spot_id_uuid = s.id_uuid
            FROM food_foodspot s WHERE m.food_spot_id = s.id
        """)
        _drop_fk_if_exists(cursor, 'food_media', 'food_spot_id')
        cursor.execute("ALTER TABLE food_media DROP COLUMN food_spot_id")
        cursor.execute("ALTER TABLE food_media RENAME COLUMN food_spot_id_uuid TO food_spot_id")
        cursor.execute("ALTER TABLE food_media ADD CONSTRAINT food_media_food_spot_id_fkey "
                       "FOREIGN KEY (food_spot_id) REFERENCES food_foodspot(id_uuid) DEFERRABLE INITIALLY DEFERRED")

        # Update food_review
        cursor.execute("ALTER TABLE food_review ADD COLUMN food_spot_id_uuid UUID")
        cursor.execute("""
            UPDATE food_review r SET food_spot_id_uuid = s.id_uuid
            FROM food_foodspot s WHERE r.food_spot_id = s.id
        """)
        _drop_fk_if_exists(cursor, 'food_review', 'food_spot_id')
        cursor.execute("ALTER TABLE food_review DROP COLUMN food_spot_id")
        cursor.execute("ALTER TABLE food_review RENAME COLUMN food_spot_id_uuid TO food_spot_id")
        cursor.execute("ALTER TABLE food_review ADD CONSTRAINT food_review_food_spot_id_fkey "
                       "FOREIGN KEY (food_spot_id) REFERENCES food_foodspot(id_uuid) DEFERRABLE INITIALLY DEFERRED")

        # Update food_food_served_at (M2M through)
        cursor.execute("ALTER TABLE food_food_served_at ADD COLUMN foodspot_id_uuid UUID")
        cursor.execute("""
            UPDATE food_food_served_at t SET foodspot_id_uuid = s.id_uuid
            FROM food_foodspot s WHERE t.foodspot_id = s.id
        """)
        _drop_fk_if_exists(cursor, 'food_food_served_at', 'foodspot_id')
        cursor.execute("ALTER TABLE food_food_served_at DROP COLUMN foodspot_id")
        cursor.execute("ALTER TABLE food_food_served_at RENAME COLUMN foodspot_id_uuid TO foodspot_id")
        cursor.execute("ALTER TABLE food_food_served_at ADD CONSTRAINT food_food_served_at_foodspot_id_fkey "
                       "FOREIGN KEY (foodspot_id) REFERENCES food_foodspot(id_uuid) DEFERRABLE INITIALLY DEFERRED")

        # Update food_foodspotlist_spots (M2M through)
        cursor.execute("ALTER TABLE food_foodspotlist_spots ADD COLUMN foodspot_id_uuid UUID")
        cursor.execute("""
            UPDATE food_foodspotlist_spots t SET foodspot_id_uuid = s.id_uuid
            FROM food_foodspot s WHERE t.foodspot_id = s.id
        """)
        _drop_fk_if_exists(cursor, 'food_foodspotlist_spots', 'foodspot_id')
        cursor.execute("ALTER TABLE food_foodspotlist_spots DROP COLUMN foodspot_id")
        cursor.execute("ALTER TABLE food_foodspotlist_spots RENAME COLUMN foodspot_id_uuid TO foodspot_id")
        cursor.execute("ALTER TABLE food_foodspotlist_spots ADD CONSTRAINT food_foodspotlist_spots_foodspot_id_fkey "
                       "FOREIGN KEY (foodspot_id) REFERENCES food_foodspot(id_uuid) DEFERRABLE INITIALLY DEFERRED")

        # Swap FoodSpot PK
        cursor.execute("ALTER TABLE food_foodspot DROP CONSTRAINT food_foodspot_pkey")
        cursor.execute("ALTER TABLE food_foodspot DROP COLUMN id")
        cursor.execute("ALTER TABLE food_foodspot RENAME COLUMN id_uuid TO id")
        cursor.execute("ALTER TABLE food_foodspot ADD PRIMARY KEY (id)")

        # Fix FK constraints (drop DEFERRABLE, add normal)
        _drop_fk_if_exists(cursor, 'food_media', 'food_spot_id')
        cursor.execute("ALTER TABLE food_media ADD CONSTRAINT food_media_food_spot_id_fkey "
                       "FOREIGN KEY (food_spot_id) REFERENCES food_foodspot(id) ON DELETE CASCADE")
        _drop_fk_if_exists(cursor, 'food_review', 'food_spot_id')
        cursor.execute("ALTER TABLE food_review ADD CONSTRAINT food_review_food_spot_id_fkey "
                       "FOREIGN KEY (food_spot_id) REFERENCES food_foodspot(id) ON DELETE CASCADE")
        _drop_fk_if_exists(cursor, 'food_food_served_at', 'foodspot_id')
        cursor.execute("ALTER TABLE food_food_served_at ADD CONSTRAINT food_food_served_at_foodspot_id_fkey "
                       "FOREIGN KEY (foodspot_id) REFERENCES food_foodspot(id) ON DELETE CASCADE")
        _drop_fk_if_exists(cursor, 'food_foodspotlist_spots', 'foodspot_id')
        cursor.execute("ALTER TABLE food_foodspotlist_spots ADD CONSTRAINT food_foodspotlist_spots_foodspot_id_fkey "
                       "FOREIGN KEY (foodspot_id) REFERENCES food_foodspot(id) ON DELETE CASCADE")

        # 2. Food
        cursor.execute("ALTER TABLE food_food ADD COLUMN id_uuid UUID UNIQUE")
        cursor.execute("UPDATE food_food SET id_uuid = gen_random_uuid()")

        # Update food_media
        cursor.execute("ALTER TABLE food_media ADD COLUMN food_id_uuid UUID")
        cursor.execute("""
            UPDATE food_media m SET food_id_uuid = f.id_uuid
            FROM food_food f WHERE m.food_id = f.id
        """)
        _drop_fk_if_exists(cursor, 'food_media', 'food_id')
        cursor.execute("ALTER TABLE food_media DROP COLUMN food_id")
        cursor.execute("ALTER TABLE food_media RENAME COLUMN food_id_uuid TO food_id")
        cursor.execute("ALTER TABLE food_media ADD CONSTRAINT food_media_food_id_fkey "
                       "FOREIGN KEY (food_id) REFERENCES food_food(id_uuid) ON DELETE CASCADE")

        # Update food_review
        cursor.execute("ALTER TABLE food_review ADD COLUMN food_id_uuid UUID")
        cursor.execute("""
            UPDATE food_review r SET food_id_uuid = f.id_uuid
            FROM food_food f WHERE r.food_id = f.id
        """)
        _drop_fk_if_exists(cursor, 'food_review', 'food_id')
        cursor.execute("ALTER TABLE food_review DROP COLUMN food_id")
        cursor.execute("ALTER TABLE food_review RENAME COLUMN food_id_uuid TO food_id")
        cursor.execute("ALTER TABLE food_review ADD CONSTRAINT food_review_food_id_fkey "
                       "FOREIGN KEY (food_id) REFERENCES food_food(id_uuid) ON DELETE CASCADE")

        # Update food_food_served_at
        cursor.execute("ALTER TABLE food_food_served_at ADD COLUMN food_id_uuid UUID")
        cursor.execute("""
            UPDATE food_food_served_at t SET food_id_uuid = f.id_uuid
            FROM food_food f WHERE t.food_id = f.id
        """)
        _drop_fk_if_exists(cursor, 'food_food_served_at', 'food_id')
        cursor.execute("ALTER TABLE food_food_served_at DROP COLUMN food_id")
        cursor.execute("ALTER TABLE food_food_served_at RENAME COLUMN food_id_uuid TO food_id")
        cursor.execute("ALTER TABLE food_food_served_at ADD CONSTRAINT food_food_served_at_food_id_fkey "
                       "FOREIGN KEY (food_id) REFERENCES food_food(id_uuid) ON DELETE CASCADE")

        # Update food_foodlist_foods
        cursor.execute("ALTER TABLE food_foodlist_foods ADD COLUMN food_id_uuid UUID")
        cursor.execute("""
            UPDATE food_foodlist_foods t SET food_id_uuid = f.id_uuid
            FROM food_food f WHERE t.food_id = f.id
        """)
        _drop_fk_if_exists(cursor, 'food_foodlist_foods', 'food_id')
        cursor.execute("ALTER TABLE food_foodlist_foods DROP COLUMN food_id")
        cursor.execute("ALTER TABLE food_foodlist_foods RENAME COLUMN food_id_uuid TO food_id")
        cursor.execute("ALTER TABLE food_foodlist_foods ADD CONSTRAINT food_foodlist_foods_food_id_fkey "
                       "FOREIGN KEY (food_id) REFERENCES food_food(id_uuid) ON DELETE CASCADE")

        # Swap Food PK
        cursor.execute("ALTER TABLE food_food DROP CONSTRAINT food_food_pkey")
        cursor.execute("ALTER TABLE food_food DROP COLUMN id")
        cursor.execute("ALTER TABLE food_food RENAME COLUMN id_uuid TO id")
        cursor.execute("ALTER TABLE food_food ADD PRIMARY KEY (id)")

        # Fix FK constraints
        _drop_fk_if_exists(cursor, 'food_media', 'food_id')
        cursor.execute("ALTER TABLE food_media ADD CONSTRAINT food_media_food_id_fkey "
                       "FOREIGN KEY (food_id) REFERENCES food_food(id) ON DELETE CASCADE")
        _drop_fk_if_exists(cursor, 'food_review', 'food_id')
        cursor.execute("ALTER TABLE food_review ADD CONSTRAINT food_review_food_id_fkey "
                       "FOREIGN KEY (food_id) REFERENCES food_food(id) ON DELETE CASCADE")
        _drop_fk_if_exists(cursor, 'food_food_served_at', 'food_id')
        cursor.execute("ALTER TABLE food_food_served_at ADD CONSTRAINT food_food_served_at_food_id_fkey "
                       "FOREIGN KEY (food_id) REFERENCES food_food(id) ON DELETE CASCADE")
        _drop_fk_if_exists(cursor, 'food_foodlist_foods', 'food_id')
        cursor.execute("ALTER TABLE food_foodlist_foods ADD CONSTRAINT food_foodlist_foods_food_id_fkey "
                       "FOREIGN KEY (food_id) REFERENCES food_food(id) ON DELETE CASCADE")

        # 3. Media, Review - simple (no FKs from other food models to them)
        cursor.execute("ALTER TABLE food_media ADD COLUMN id_uuid UUID UNIQUE")
        cursor.execute("UPDATE food_media SET id_uuid = gen_random_uuid()")
        cursor.execute("ALTER TABLE food_media DROP CONSTRAINT food_media_pkey")
        cursor.execute("ALTER TABLE food_media DROP COLUMN id")
        cursor.execute("ALTER TABLE food_media RENAME COLUMN id_uuid TO id")
        cursor.execute("ALTER TABLE food_media ADD PRIMARY KEY (id)")

        cursor.execute("ALTER TABLE food_review ADD COLUMN id_uuid UUID UNIQUE")
        cursor.execute("UPDATE food_review SET id_uuid = gen_random_uuid()")
        cursor.execute("ALTER TABLE food_review DROP CONSTRAINT food_review_pkey")
        cursor.execute("ALTER TABLE food_review DROP COLUMN id")
        cursor.execute("ALTER TABLE food_review RENAME COLUMN id_uuid TO id")
        cursor.execute("ALTER TABLE food_review ADD PRIMARY KEY (id)")

        # 4. FoodSpotList
        cursor.execute("ALTER TABLE food_foodspotlist ADD COLUMN id_uuid UUID UNIQUE")
        cursor.execute("UPDATE food_foodspotlist SET id_uuid = gen_random_uuid()")

        cursor.execute("ALTER TABLE food_foodspotlist_spots ADD COLUMN foodspotlist_id_uuid UUID")
        cursor.execute("""
            UPDATE food_foodspotlist_spots t SET foodspotlist_id_uuid = l.id_uuid
            FROM food_foodspotlist l WHERE t.foodspotlist_id = l.id
        """)
        _drop_fk_if_exists(cursor, 'food_foodspotlist_spots', 'foodspotlist_id')
        cursor.execute("ALTER TABLE food_foodspotlist_spots DROP COLUMN foodspotlist_id")
        cursor.execute("ALTER TABLE food_foodspotlist_spots RENAME COLUMN foodspotlist_id_uuid TO foodspotlist_id")
        cursor.execute("ALTER TABLE food_foodspotlist_spots ADD CONSTRAINT food_foodspotlist_spots_foodspotlist_id_fkey "
                       "FOREIGN KEY (foodspotlist_id) REFERENCES food_foodspotlist(id_uuid) ON DELETE CASCADE")

        cursor.execute("ALTER TABLE food_foodspotlist DROP CONSTRAINT food_foodspotlist_pkey")
        cursor.execute("ALTER TABLE food_foodspotlist DROP COLUMN id")
        cursor.execute("ALTER TABLE food_foodspotlist RENAME COLUMN id_uuid TO id")
        cursor.execute("ALTER TABLE food_foodspotlist ADD PRIMARY KEY (id)")

        _drop_fk_if_exists(cursor, 'food_foodspotlist_spots', 'foodspotlist_id')
        cursor.execute("ALTER TABLE food_foodspotlist_spots ADD CONSTRAINT food_foodspotlist_spots_foodspotlist_id_fkey "
                       "FOREIGN KEY (foodspotlist_id) REFERENCES food_foodspotlist(id) ON DELETE CASCADE")

        # 5. FoodList
        cursor.execute("ALTER TABLE food_foodlist ADD COLUMN id_uuid UUID UNIQUE")
        cursor.execute("UPDATE food_foodlist SET id_uuid = gen_random_uuid()")

        cursor.execute("ALTER TABLE food_foodlist_foods ADD COLUMN foodlist_id_uuid UUID")
        cursor.execute("""
            UPDATE food_foodlist_foods t SET foodlist_id_uuid = l.id_uuid
            FROM food_foodlist l WHERE t.foodlist_id = l.id
        """)
        _drop_fk_if_exists(cursor, 'food_foodlist_foods', 'foodlist_id')
        cursor.execute("ALTER TABLE food_foodlist_foods DROP COLUMN foodlist_id")
        cursor.execute("ALTER TABLE food_foodlist_foods RENAME COLUMN foodlist_id_uuid TO foodlist_id")
        cursor.execute("ALTER TABLE food_foodlist_foods ADD CONSTRAINT food_foodlist_foods_foodlist_id_fkey "
                       "FOREIGN KEY (foodlist_id) REFERENCES food_foodlist(id_uuid) ON DELETE CASCADE")

        cursor.execute("ALTER TABLE food_foodlist DROP CONSTRAINT food_foodlist_pkey")
        cursor.execute("ALTER TABLE food_foodlist DROP COLUMN id")
        cursor.execute("ALTER TABLE food_foodlist RENAME COLUMN id_uuid TO id")
        cursor.execute("ALTER TABLE food_foodlist ADD PRIMARY KEY (id)")

        _drop_fk_if_exists(cursor, 'food_foodlist_foods', 'foodlist_id')
        cursor.execute("ALTER TABLE food_foodlist_foods ADD CONSTRAINT food_foodlist_foods_foodlist_id_fkey "
                       "FOREIGN KEY (foodlist_id) REFERENCES food_foodlist(id) ON DELETE CASCADE")


def noop(apps, schema_editor):
    """Reverse migration not supported - would require integer conversion."""
    pass


class Migration(migrations.Migration):
    atomic = False  # Required: PostgreSQL "pending trigger events" when altering FKs in one transaction

    dependencies = [
        ('food', '0005_foodspotlist_foodlist'),
    ]

    operations = [
        migrations.RunPython(migrate_to_uuid, noop),
        # Update Django's migration state only (DB already altered by RunPython)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='foodspot',
                    name='id',
                    field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name='food',
                    name='id',
                    field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name='media',
                    name='id',
                    field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name='review',
                    name='id',
                    field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name='foodspotlist',
                    name='id',
                    field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name='foodlist',
                    name='id',
                    field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
            ],
            database_operations=[],
        ),
    ]
