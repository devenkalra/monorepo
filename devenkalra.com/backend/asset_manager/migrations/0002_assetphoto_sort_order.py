from django.db import migrations, models


def seed_sort_order(apps, schema_editor):
    """Preserve previous display order (newest first) as ascending sort_order."""
    AssetPhoto = apps.get_model('asset_manager', 'AssetPhoto')
    groups = {}
    for photo in AssetPhoto.objects.all().order_by('-created_at', '-id'):
        key = (photo.content_type_id, photo.object_id)
        groups.setdefault(key, []).append(photo)
    for photos in groups.values():
        for index, photo in enumerate(photos):
            photo.sort_order = index
            photo.save(update_fields=['sort_order'])


class Migration(migrations.Migration):

    dependencies = [
        ('asset_manager', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='assetphoto',
            name='sort_order',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Lower values appear first; the first image is used as the cover.',
            ),
        ),
        migrations.AlterModelOptions(
            name='assetphoto',
            options={
                'ordering': ['sort_order', 'id'],
                'verbose_name': 'Asset photo',
                'verbose_name_plural': 'Asset photos',
            },
        ),
        migrations.RunPython(seed_sort_order, migrations.RunPython.noop),
    ]
