import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gallery', '0005_showbuildjob'),
        ('trips', '0002_stop_time_duration'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TripStopAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_on', models.DateTimeField(auto_now=True)),
                ('kind', models.CharField(choices=[('document', 'Document'), ('url', 'URL'), ('picture', 'Picture'), ('location', 'Location')], max_length=20)),
                ('title', models.CharField(blank=True, default='', max_length=255)),
                ('url', models.CharField(blank=True, default='', max_length=2000)),
                ('osm_url', models.CharField(blank=True, default='', max_length=2000)),
                ('address', models.CharField(blank=True, default='', max_length=500)),
                ('lat', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('lng', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('asset', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='trip_attachments', to='gallery.usermedia')),
                ('stop', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='trips.tripstop')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='trip_attachments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.AddIndex(
            model_name='tripstopattachment',
            index=models.Index(fields=['user', 'stop'], name='tripattach_user_stop_idx'),
        ),
    ]
