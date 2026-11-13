from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0008_tripday_notes'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='trip',
            name='notes',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='trip',
            name='open_items',
            field=models.TextField(blank=True, default=''),
        ),
    ]
