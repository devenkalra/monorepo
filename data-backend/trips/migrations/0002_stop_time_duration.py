from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='tripstop',
            name='start_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tripstop',
            name='duration_minutes',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
