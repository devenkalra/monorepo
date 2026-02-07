# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0017_container_asset_org'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='entity',
            name='label',
        ),
    ]
