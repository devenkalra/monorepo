import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('gallery', '0004_galleryitem_analysis'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShowBuildJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('analyzing', 'Analyzing'), ('planning', 'Planning'), ('compiling', 'Compiling'), ('ready', 'Ready'), ('failed', 'Failed')], default='queued', max_length=20)),
                ('prompt', models.TextField(blank=True, default='')),
                ('style', models.CharField(blank=True, default='', max_length=32)),
                ('target_seconds', models.FloatField(blank=True, null=True)),
                ('item_ids', models.JSONField(blank=True, default=list)),
                ('title', models.CharField(blank=True, default='', max_length=255)),
                ('plan', models.JSONField(blank=True, default=dict)),
                ('log', models.JSONField(blank=True, default=list)),
                ('warnings', models.JSONField(blank=True, default=list)),
                ('error', models.TextField(blank=True, default='')),
                ('celery_task_id', models.CharField(blank=True, default='', max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('gallery', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='show_jobs', to='gallery.gallery')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gallery_show_jobs', to=settings.AUTH_USER_MODEL)),
                ('show', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='build_jobs', to='gallery.galleryshow')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
