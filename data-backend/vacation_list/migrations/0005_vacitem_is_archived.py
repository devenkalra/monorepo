from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vacation_list', '0004_vacitem_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='vacitem',
            name='is_archived',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='Archived items are hidden from the catalog but stay on packing lists.',
            ),
        ),
    ]
