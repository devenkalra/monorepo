import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FlightPath',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('path_id', models.CharField(max_length=64)),
                ('document', models.JSONField(default=dict)),
                ('map_overlay', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'owner',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='flightstudio_paths',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['path_id'],
            },
        ),
        migrations.AddIndex(
            model_name='flightpath',
            index=models.Index(fields=['owner', 'path_id'], name='flightstudi_owner_i_7c4a2f_idx'),
        ),
        migrations.AddConstraint(
            model_name='flightpath',
            constraint=models.UniqueConstraint(fields=('owner', 'path_id'), name='fs_owner_path_id_uniq'),
        ),
    ]
