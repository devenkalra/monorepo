# Replace single location with multiple locations (street, city, state, country, postal_code, phone)

from django.db import migrations, models


def migrate_location_to_locations(apps, schema_editor):
    FoodSpot = apps.get_model('food', 'FoodSpot')
    for spot in FoodSpot.objects.all():
        if spot.location and spot.location.strip():
            spot.locations = [{
                'street': spot.location,
                'city': '',
                'state': '',
                'country': '',
                'postal_code': '',
                'phone': '',
            }]
        else:
            spot.locations = []
        spot.save(update_fields=['locations'])


def reverse_migrate(apps, schema_editor):
    FoodSpot = apps.get_model('food', 'FoodSpot')
    for spot in FoodSpot.objects.all():
        if spot.locations and len(spot.locations) > 0:
            parts = []
            loc = spot.locations[0]
            for k in ['street', 'city', 'state', 'country', 'postal_code']:
                if loc.get(k):
                    parts.append(str(loc[k]))
            spot.location = ', '.join(parts) if parts else ''
        else:
            spot.location = ''
        spot.save(update_fields=['location'])


class Migration(migrations.Migration):

    dependencies = [
        ('food', '0003_foodspot_food_tags'),
    ]

    operations = [
        migrations.AddField(
            model_name='foodspot',
            name='locations',
            field=models.JSONField(blank=True, default=list, null=True),
        ),
        migrations.RunPython(migrate_location_to_locations, reverse_migrate),
        migrations.RemoveField(
            model_name='foodspot',
            name='location',
        ),
    ]
