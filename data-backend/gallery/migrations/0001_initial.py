import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('people', '0009_userprofile_public_username'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Gallery',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=255)),
                ('slug', models.SlugField(max_length=80)),
                ('description', models.TextField(blank=True, default='')),
                ('cover', models.JSONField(blank=True, default=dict)),
                ('access_mode', models.CharField(choices=[('public', 'Public (anyone with link)'), ('restricted', 'Restricted (allow-list)')], default='public', max_length=20)),
                ('allow_download', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='galleries', to=settings.AUTH_USER_MODEL)),
                ('source_entity', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='source_galleries', to='people.entity')),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='GalleryItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('media_type', models.CharField(choices=[('image', 'Image'), ('video', 'Video'), ('other', 'Other')], default='image', max_length=20)),
                ('url', models.CharField(blank=True, default='', max_length=1000)),
                ('external_url', models.URLField(blank=True, default='', max_length=2000)),
                ('thumbnail_url', models.CharField(blank=True, default='', max_length=1000)),
                ('title', models.CharField(blank=True, default='', max_length=255)),
                ('caption', models.TextField(blank=True, default='')),
                ('filename', models.CharField(blank=True, default='', max_length=500)),
                ('source_photo_key', models.CharField(blank=True, default='', max_length=1000)),
                ('thumbnail_status', models.CharField(default='ready', help_text='ready|pending|failed|n/a', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('gallery', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='gallery.gallery')),
            ],
            options={
                'ordering': ['sort_order', 'created_at'],
            },
        ),
        migrations.CreateModel(
            name='GalleryShare',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254)),
                ('password_hash', models.CharField(max_length=128)),
                ('role', models.CharField(choices=[('view', 'View'), ('add_photos', 'Add photos'), ('edit', 'Edit')], default='view', max_length=20)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_accessed_at', models.DateTimeField(blank=True, null=True)),
                ('gallery', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shares', to='gallery.gallery')),
            ],
        ),
        migrations.CreateModel(
            name='GalleryShow',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('slug', models.SlugField(max_length=80)),
                ('title', models.CharField(blank=True, default='', max_length=255)),
                ('config', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('gallery', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shows', to='gallery.gallery')),
            ],
            options={
                'ordering': ['title', 'slug'],
            },
        ),
        migrations.AddIndex(
            model_name='gallery',
            index=models.Index(fields=['owner'], name='gallery_gal_owner_i_7c2e0a_idx'),
        ),
        migrations.AddIndex(
            model_name='gallery',
            index=models.Index(fields=['access_mode'], name='gallery_gal_access__b8c1d2_idx'),
        ),
        migrations.AddConstraint(
            model_name='gallery',
            constraint=models.UniqueConstraint(fields=('owner', 'slug'), name='gallery_owner_slug_uniq'),
        ),
        migrations.AddIndex(
            model_name='galleryitem',
            index=models.Index(fields=['gallery', 'sort_order'], name='gallery_gal_gallery_3a1b2c_idx'),
        ),
        migrations.AddConstraint(
            model_name='galleryshare',
            constraint=models.UniqueConstraint(fields=('gallery', 'email'), name='gallery_share_email_uniq'),
        ),
        migrations.AddConstraint(
            model_name='galleryshow',
            constraint=models.UniqueConstraint(fields=('gallery', 'slug'), name='gallery_show_slug_uniq'),
        ),
    ]
