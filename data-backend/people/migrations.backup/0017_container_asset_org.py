# Generated manually for Container, Asset, Org models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('people', '0016_book'),
    ]

    operations = [
        migrations.CreateModel(
            name='Container',
            fields=[
                ('entity_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='people.entity')),
            ],
            bases=('people.entity',),
        ),
        migrations.CreateModel(
            name='Asset',
            fields=[
                ('entity_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='people.entity')),
                ('value', models.FloatField(blank=True, null=True)),
                ('acquired_on', models.CharField(blank=True, max_length=255, null=True)),
            ],
            bases=('people.entity',),
        ),
        migrations.CreateModel(
            name='Org',
            fields=[
                ('entity_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='people.entity')),
                ('name', models.CharField(blank=True, max_length=255, null=True)),
                ('kind', models.CharField(blank=True, choices=[('School', 'School'), ('University', 'University'), ('Company', 'Company'), ('NonProfit', 'NonProfit'), ('Club', 'Club'), ('Unspecified', 'Unspecified')], default='Unspecified', max_length=50, null=True)),
            ],
            bases=('people.entity',),
        ),
    ]
