from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0016_timezones'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tripstop',
            name='status',
            field=models.CharField(
                choices=[
                    ('option', 'Option'),
                    ('no_booking', 'No booking needed'),
                    ('tobook', 'To book'),
                    ('booked', 'Booked'),
                    ('confirmed', 'Confirmed'),
                ],
                default='no_booking',
                max_length=20,
            ),
        ),
    ]
