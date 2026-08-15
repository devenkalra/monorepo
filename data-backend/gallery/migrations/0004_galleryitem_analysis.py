from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gallery', '0003_usermedia'),
    ]

    operations = [
        migrations.AddField(
            model_name='galleryitem',
            name='analysis',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
