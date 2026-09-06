from django.db import migrations, models
import vacation_list.models


class Migration(migrations.Migration):

    dependencies = [
        ('vacation_list', '0003_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='vacitem',
            name='image',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=vacation_list.models.vac_item_image_upload_to,
            ),
        ),
    ]
