# Generated migration for photos, attachments, urls

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('food', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='foodspot',
            name='photos',
            field=models.JSONField(blank=True, default=list, null=True),
        ),
        migrations.AddField(
            model_name='foodspot',
            name='attachments',
            field=models.JSONField(blank=True, default=list, null=True),
        ),
        migrations.AddField(
            model_name='foodspot',
            name='urls',
            field=models.JSONField(blank=True, default=list, null=True),
        ),
        migrations.AddField(
            model_name='food',
            name='photos',
            field=models.JSONField(blank=True, default=list, null=True),
        ),
        migrations.AddField(
            model_name='food',
            name='attachments',
            field=models.JSONField(blank=True, default=list, null=True),
        ),
        migrations.AddField(
            model_name='food',
            name='urls',
            field=models.JSONField(blank=True, default=list, null=True),
        ),
    ]
