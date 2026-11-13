from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0006_attachment_lodging'),
    ]

    operations = [
        migrations.AddField(
            model_name='tripstop',
            name='kind',
            field=models.CharField(
                choices=[('activity', 'Activity'), ('travel', 'Travel')],
                default='activity',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='tripstop',
            name='travel_mode',
            field=models.CharField(
                blank=True,
                choices=[
                    ('flight', 'Flight'),
                    ('drive', 'Drive'),
                    ('walk', 'Walk'),
                    ('boat', 'Boat'),
                ],
                default='',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='tripstop',
            name='arrive_loc',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
