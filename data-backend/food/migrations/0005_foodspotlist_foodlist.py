# Add FoodSpotList and FoodList models

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('food', '0004_foodspot_locations'),
    ]

    operations = [
        migrations.CreateModel(
            name='FoodSpotList',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('added_by', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='food_spot_lists', to=settings.AUTH_USER_MODEL)),
                ('spots', models.ManyToManyField(blank=True, related_name='spot_lists', to='food.foodspot')),
            ],
            options={
                'verbose_name': 'Food spot list',
                'verbose_name_plural': 'Food spot lists',
                'ordering': ['-modified_at'],
            },
        ),
        migrations.CreateModel(
            name='FoodList',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('added_by', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='food_lists', to=settings.AUTH_USER_MODEL)),
                ('foods', models.ManyToManyField(blank=True, related_name='food_lists', to='food.food')),
            ],
            options={
                'verbose_name': 'Food list',
                'verbose_name_plural': 'Food lists',
                'ordering': ['-modified_at'],
            },
        ),
    ]
