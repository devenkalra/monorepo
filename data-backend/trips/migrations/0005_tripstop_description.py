from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0004_triplodging'),
    ]

    operations = [
        migrations.AddField(
            model_name='tripstop',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
    ]
