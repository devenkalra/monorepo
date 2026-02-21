# Sync migration state with actual models (RunPython migrations don't update state)
# Database schema already correct; this only updates Django's migration state

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('food', '0013_food_private_foodspot_private_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='FoodSpotFoodRating',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('rating', models.PositiveSmallIntegerField()),
                        ('note', models.TextField(blank=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('modified_at', models.DateTimeField(auto_now=True)),
                        ('added_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='food_spot_food_ratings', to=settings.AUTH_USER_MODEL)),
                        ('food', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ratings_at_spots', to='food.food')),
                        ('food_spot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='food_ratings', to='food.foodspot')),
                    ],
                    options={
                        'indexes': [
                            models.Index(fields=['food_spot', 'food'], name='food_foodsp_food_sp_07aa7e_idx'),
                        ],
                        'constraints': [
                            models.UniqueConstraint(fields=['food', 'food_spot', 'added_by'], name='unique_food_spot_rating_per_user'),
                        ],
                    },
                ),
                migrations.AddField(
                    model_name='food',
                    name='private',
                    field=models.BooleanField(default=False),
                ),
                migrations.AddField(
                    model_name='foodspot',
                    name='private',
                    field=models.BooleanField(default=False),
                ),
                migrations.AddIndex(
                    model_name='food',
                    index=models.Index(fields=['added_by'], name='food_food_added_b_7f3f32_idx'),
                ),
                migrations.AddIndex(
                    model_name='food',
                    index=models.Index(fields=['private'], name='food_food_private_c5f8fd_idx'),
                ),
                migrations.AddIndex(
                    model_name='foodspot',
                    index=models.Index(fields=['added_by'], name='food_foodsp_added_b_745d25_idx'),
                ),
                migrations.AddIndex(
                    model_name='foodspot',
                    index=models.Index(fields=['private'], name='food_foodsp_private_03faea_idx'),
                ),
            ],
            database_operations=[],
        ),
    ]
