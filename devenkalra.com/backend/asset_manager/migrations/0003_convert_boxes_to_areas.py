from django.db import migrations, models
import django.db.models.deletion


def convert_boxes_to_areas(apps, schema_editor):
    AssetBox = apps.get_model('asset_manager', 'AssetBox')
    AssetArea = apps.get_model('asset_manager', 'AssetArea')
    AssetItem = apps.get_model('asset_manager', 'AssetItem')
    AssetPhoto = apps.get_model('asset_manager', 'AssetPhoto')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    try:
        box_ct = ContentType.objects.get(app_label='asset_manager', model='assetbox')
        area_ct = ContentType.objects.get(app_label='asset_manager', model='assetarea')
    except ContentType.DoesNotExist:
        return

    box_to_area = {}
    remaining = list(AssetBox.objects.all().order_by('id'))

    while remaining:
        progress = False
        still = []
        for box in remaining:
            if box.parent_box_id and box.parent_box_id not in box_to_area:
                still.append(box)
                continue

            if box.parent_box_id:
                parent_area_id = box_to_area[box.parent_box_id]
            else:
                parent_area_id = box.area_id

            area = AssetArea(
                name=box.name,
                description=box.description or '',
                category_id=box.category_id,
                locator_code=box.locator_code,
                locator_type=box.locator_type or '',
                parent_area_id=parent_area_id,
            )
            area.save()
            # Preserve timestamps after create (auto fields ignore create kwargs)
            AssetArea.objects.filter(pk=area.pk).update(
                created_at=box.created_at,
                modified_at=box.modified_at,
            )
            for tag in box.tags.all():
                area.tags.add(tag)

            AssetPhoto.objects.filter(content_type=box_ct, object_id=box.id).update(
                content_type=area_ct,
                object_id=area.id,
            )
            box_to_area[box.id] = area.id
            progress = True

        if not progress:
            # Break cycles / orphans with missing parents by placing at root
            for box in still:
                area = AssetArea(
                    name=box.name,
                    description=box.description or '',
                    category_id=box.category_id,
                    locator_code=box.locator_code,
                    locator_type=box.locator_type or '',
                    parent_area_id=box.area_id,
                )
                area.save()
                AssetArea.objects.filter(pk=area.pk).update(
                    created_at=box.created_at,
                    modified_at=box.modified_at,
                )
                for tag in box.tags.all():
                    area.tags.add(tag)
                AssetPhoto.objects.filter(content_type=box_ct, object_id=box.id).update(
                    content_type=area_ct,
                    object_id=area.id,
                )
                box_to_area[box.id] = area.id
            break
        remaining = still

    for item in AssetItem.objects.filter(box_id__isnull=False):
        mapped = box_to_area.get(item.box_id)
        AssetItem.objects.filter(pk=item.pk).update(
            area_id=mapped,
            box_id=None,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('asset_manager', '0002_assetphoto_sort_order'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(convert_boxes_to_areas, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='assetitem',
            name='asset_manager_item_not_in_both_box_and_area',
        ),
        migrations.RemoveField(
            model_name='assetitem',
            name='box',
        ),
        migrations.AlterField(
            model_name='assetitem',
            name='area',
            field=models.ForeignKey(
                blank=True,
                help_text='Area containing this item (optional orphan if blank).',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='items',
                to='asset_manager.assetarea',
            ),
        ),
        migrations.DeleteModel(
            name='AssetBox',
        ),
    ]
