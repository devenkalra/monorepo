from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0004_entity_detail_cache'),
    ]

    operations = [
        migrations.CreateModel(
            name='Lookup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, default='', max_length=255)),
                ('columns', models.JSONField(blank=True, default=dict)),
                ('rows', models.JSONField(blank=True, default=list)),
                ('summary', models.JSONField(blank=True, default=dict)),
                ('clickup_as_of', models.CharField(blank=True, default='', max_length=40)),
                ('google_as_of', models.CharField(blank=True, default='', max_length=40)),
                ('checked_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
