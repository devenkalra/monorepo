from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('trips', '0015_tripstop_price_person')]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='timezone',
            field=models.CharField(
                blank=True, default='', max_length=64,
                help_text='IANA zone the trip starts in, e.g. America/Los_Angeles.',
            ),
        ),
        migrations.AddField(
            model_name='tripday',
            name='timezone',
            field=models.CharField(
                blank=True, default='', max_length=64,
                help_text='Blank continues in the zone the previous day ended in.',
            ),
        ),
        migrations.AddField(
            model_name='tripstop',
            name='timezone',
            field=models.CharField(
                blank=True, default='', max_length=64,
                help_text='Blank uses the zone the itinerary is in at this point of the day.',
            ),
        ),
        migrations.AddField(
            model_name='tripstop',
            name='arrive_timezone',
            field=models.CharField(
                blank=True, default='', max_length=64,
                help_text='Travel only; blank arrives in the departure zone. Later items continue in this zone.',
            ),
        ),
    ]
