import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0003_tripstopattachment'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TripLodging',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_on', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=255)),
                ('address', models.CharField(blank=True, default='', max_length=500)),
                ('phone', models.CharField(blank=True, default='', max_length=64)),
                ('url', models.CharField(blank=True, default='', max_length=2000)),
                ('confirmation', models.CharField(blank=True, default='', max_length=128)),
                ('notes', models.TextField(blank=True, default='')),
                ('check_in_time', models.TimeField(blank=True, null=True)),
                ('check_out_time', models.TimeField(blank=True, null=True)),
                ('trip', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lodgings', to='trips.trip')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='trip_lodgings', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name', 'id'],
            },
        ),
        migrations.AddIndex(
            model_name='triplodging',
            index=models.Index(fields=['user', 'trip'], name='triplodge_user_trip_idx'),
        ),
        migrations.AddField(
            model_name='tripday',
            name='lodging',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='days', to='trips.triplodging'),
        ),
    ]
