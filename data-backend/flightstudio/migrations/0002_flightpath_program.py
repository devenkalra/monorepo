from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('flightstudio', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='flightpath',
            name='program',
            field=models.JSONField(blank=True, default=None, null=True),
        ),
    ]
