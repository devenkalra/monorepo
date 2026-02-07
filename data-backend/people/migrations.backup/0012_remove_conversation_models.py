# Generated manually to remove Conversation and ConversationTurn models

from django.db import migrations


def drop_conversation_tables(apps, schema_editor):
    """Drop conversation tables directly"""
    with schema_editor.connection.cursor() as cursor:
        # Drop tables if they exist
        cursor.execute("DROP TABLE IF EXISTS people_conversationturn")
        cursor.execute("DROP TABLE IF EXISTS people_conversation")


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0011_assign_default_user'),
    ]

    operations = [
        migrations.RunPython(drop_conversation_tables, migrations.RunPython.noop),
    ]
