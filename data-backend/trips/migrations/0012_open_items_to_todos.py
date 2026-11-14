import re

from django.db import migrations

_LIST_MARKER = re.compile(r'^(?:[-*+]|\d+[.)])(?:\s+|$)(?:\[[ xX]\](?:\s+|$))?')


def forwards(apps, schema_editor):
    Trip = apps.get_model('trips', 'Trip')
    TripTodo = apps.get_model('trips', 'TripTodo')
    for trip in Trip.objects.exclude(open_items=''):
        lines = (_LIST_MARKER.sub('', line.strip()).strip() for line in trip.open_items.splitlines())
        base = TripTodo.objects.filter(trip=trip).count()
        TripTodo.objects.bulk_create([
            TripTodo(user_id=trip.user_id, trip=trip, text=text, sort_order=base + i)
            for i, text in enumerate(line for line in lines if line)
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0011_event_kind_todos'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.RemoveField(model_name='trip', name='open_items'),
    ]
