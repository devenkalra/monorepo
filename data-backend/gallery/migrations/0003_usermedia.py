import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gallery', '0002_rename_gallery_gal_owner_i_7c2e0a_idx_gallery_gal_owner_i_d8aeed_idx_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserMedia',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('url', models.CharField(max_length=1000)),
                ('thumbnail_url', models.CharField(blank=True, default='', max_length=1000)),
                ('filename', models.CharField(blank=True, default='', max_length=500)),
                ('media_type', models.CharField(choices=[('image', 'Image'), ('video', 'Video'), ('other', 'Other')], default='image', max_length=20)),
                ('sha256', models.CharField(blank=True, default='', max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gallery_media', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='usermedia',
            index=models.Index(fields=['owner', '-created_at'], name='gallery_use_owner_i_9a1b2c_idx'),
        ),
        migrations.AddIndex(
            model_name='usermedia',
            index=models.Index(fields=['owner', 'url'], name='gallery_use_owner_i_3d4e5f_idx'),
        ),
        migrations.AddConstraint(
            model_name='usermedia',
            constraint=models.UniqueConstraint(fields=('owner', 'url'), name='gallery_usermedia_owner_url_uniq'),
        ),
    ]
