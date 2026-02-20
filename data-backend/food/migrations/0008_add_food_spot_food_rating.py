# Generated manually for FoodSpotFoodRating model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('food', '0007_add_private_field'),
    ]

    operations = [
        migrations.CreateModel(
            name='FoodSpotFoodRating',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('rating', models.PositiveSmallIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('added_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='food_spot_food_ratings', to=settings.AUTH_USER_MODEL)),
                ('food', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ratings_at_spots', to='food.food')),
                ('food_spot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='food_ratings', to='food.foodspot')),
            ],
            options={
                'ordering': ['-modified_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='foodspotfoodrating',
            constraint=models.UniqueConstraint(fields=('food', 'food_spot', 'added_by'), name='unique_food_spot_rating_per_user'),
        ),
        migrations.AddIndex(
            model_name='foodspotfoodrating',
            index=models.Index(fields=['food_spot', 'food'], name='food_foodsp_food_sp_3a8b2a_idx'),
        ),
    ]
