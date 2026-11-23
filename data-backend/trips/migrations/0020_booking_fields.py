from django.db import migrations, models


def backfill_lodging_status(apps, schema_editor):
    TripLodging = apps.get_model('trips', 'TripLodging')
    TripLodging.objects.exclude(confirmation='').update(status='confirmed')


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0019_unscheduled_ideas'),
    ]

    operations = [
        migrations.AddField(
            model_name='tripstop',
            name='confirmation',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AddField(
            model_name='triplodging',
            name='status',
            field=models.CharField(
                choices=[
                    ('option', 'Option'),
                    ('no_booking', 'No booking needed'),
                    ('tobook', 'To book'),
                    ('booked', 'Booked'),
                    ('confirmed', 'Confirmed'),
                ],
                default='tobook',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='triplodging',
            name='price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='triplodging',
            name='currency',
            field=models.CharField(
                blank=True,
                default='',
                help_text='ISO code such as THB; blank means the default currency ($).',
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name='triplodging',
            name='person',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.RunPython(backfill_lodging_status, migrations.RunPython.noop),
    ]
