# Generated manually for wa_assistant app

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='WhatsAppMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('wa_message_id', models.CharField(db_index=True, max_length=255, unique=True)),
                ('wa_from', models.CharField(db_index=True, max_length=50)),
                ('wa_to', models.CharField(db_index=True, max_length=50)),
                ('wa_timestamp', models.DateTimeField(blank=True, null=True)),
                ('msg_type', models.CharField(max_length=50)),
                ('text_body', models.TextField(blank=True)),
                ('raw_payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='WhatsAppMedia',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('wa_media_id', models.CharField(db_index=True, max_length=255)),
                ('mime_type', models.CharField(blank=True, max_length=128)),
                ('sha256', models.CharField(blank=True, db_index=True, max_length=64)),
                ('path', models.CharField(max_length=512)),
                ('url', models.CharField(max_length=1024)),
                ('thumbnail_url', models.CharField(blank=True, max_length=1024)),
                ('file_size', models.PositiveIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='media', to='wa_assistant.whatsappmessage')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
