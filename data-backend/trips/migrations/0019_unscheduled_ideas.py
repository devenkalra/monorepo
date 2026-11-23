from django.db import migrations, models
import django.db.models.deletion


def backfill_stop_trip(apps, schema_editor):
    TripStop = apps.get_model('trips', 'TripStop')
    for stop in TripStop.objects.select_related('day').filter(trip__isnull=True, day__isnull=False):
        TripStop.objects.filter(pk=stop.pk).update(trip_id=stop.day.trip_id)


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0018_trip_legs'),
    ]

    operations = [
        migrations.AddField(
            model_name='tripstop',
            name='trip',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='stops',
                to='trips.trip',
            ),
        ),
        migrations.AddField(
            model_name='tripstop',
            name='leg',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ideas',
                to='trips.tripleg',
            ),
        ),
        migrations.AlterField(
            model_name='tripstop',
            name='day',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='stops',
                to='trips.tripday',
            ),
        ),
        migrations.RunPython(backfill_stop_trip, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='tripstop',
            name='trip',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='stops',
                to='trips.trip',
            ),
        ),
        migrations.AddIndex(
            model_name='tripstop',
            index=models.Index(fields=['user', 'trip'], name='tripstop_user_trip_idx'),
        ),
    ]
