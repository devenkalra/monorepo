"""Food app models - FoodSpot, Food, Media, Review."""

import uuid
from django.db import models
from django.contrib.auth.models import User


class FoodSpot(models.Model):
    """A place that serves food (restaurant, cafe, etc.)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    added_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='food_spots')
    name = models.CharField(max_length=255)
    # Each location: {street, city, state, country, postal_code, phone}
    locations = models.JSONField(default=list, blank=True, null=True)
    description = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True, null=True)  # Single-level tags, e.g. ["vegan", "breakfast"]
    photos = models.JSONField(default=list, blank=True, null=True)  # Same scheme as people: list of {url, thumbnail_url} or url strings
    attachments = models.JSONField(default=list, blank=True, null=True)
    urls = models.JSONField(default=list, blank=True, null=True)  # External links e.g. YouTube
    private = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-modified_at']
        indexes = [
            models.Index(fields=['added_by']),
            models.Index(fields=['private']),
        ]

    def __str__(self):
        return self.name


class Food(models.Model):
    """A food item that can be served at multiple spots."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    added_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='foods')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    alsocalled = models.CharField(max_length=500, blank=True)
    served_at = models.ManyToManyField(FoodSpot, blank=True, related_name='foods')
    tags = models.JSONField(default=list, blank=True, null=True)  # Single-level tags, e.g. ["dessert", "spicy"]
    photos = models.JSONField(default=list, blank=True, null=True)
    attachments = models.JSONField(default=list, blank=True, null=True)
    urls = models.JSONField(default=list, blank=True, null=True)
    private = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-modified_at']
        indexes = [
            models.Index(fields=['added_by']),
            models.Index(fields=['private']),
        ]

    def __str__(self):
        return self.name


class Media(models.Model):
    """Photo, video, or YouTube link attached to a FoodSpot or Food."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    photo = models.URLField(blank=True)
    video = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    food_spot = models.ForeignKey(FoodSpot, null=True, blank=True, on_delete=models.CASCADE, related_name='media')
    food = models.ForeignKey(Food, null=True, blank=True, on_delete=models.CASCADE, related_name='media')
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Media'

    def __str__(self):
        if self.youtube_url:
            return f"Media (YouTube)"
        if self.photo:
            return "Media (Photo)"
        if self.video:
            return "Media (Video)"
        return "Media"


class FoodSpotList(models.Model):
    """User-created list of food spots."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    added_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='food_spot_lists')
    name = models.CharField(max_length=255)
    spots = models.ManyToManyField(FoodSpot, blank=True, related_name='spot_lists')
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-modified_at']
        verbose_name = 'Food spot list'
        verbose_name_plural = 'Food spot lists'

    def __str__(self):
        return self.name


class FoodList(models.Model):
    """User-created list of foods."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    added_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='food_lists')
    name = models.CharField(max_length=255)
    foods = models.ManyToManyField(Food, blank=True, related_name='food_lists')
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-modified_at']
        verbose_name = 'Food list'
        verbose_name_plural = 'Food lists'

    def __str__(self):
        return self.name


class Review(models.Model):
    """Review/rating for a FoodSpot (spot-level rating)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    added_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='food_reviews')
    rating = models.PositiveSmallIntegerField()  # 1-5
    note = models.TextField(blank=True)
    food_spot = models.ForeignKey(FoodSpot, null=True, blank=True, on_delete=models.CASCADE, related_name='reviews')
    food = models.ForeignKey(Food, null=True, blank=True, on_delete=models.CASCADE, related_name='reviews')
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Review {self.rating}/5"


class FoodSpotFoodRating(models.Model):
    """Rating and review for a Food as served at a specific FoodSpot (1-5 + optional note)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    food = models.ForeignKey(Food, on_delete=models.CASCADE, related_name='ratings_at_spots')
    food_spot = models.ForeignKey(FoodSpot, on_delete=models.CASCADE, related_name='food_ratings')
    added_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='food_spot_food_ratings')
    rating = models.PositiveSmallIntegerField()  # 1-5
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['food', 'food_spot', 'added_by'],
                name='unique_food_spot_rating_per_user',
            ),
        ]
        indexes = [
            models.Index(fields=['food_spot', 'food']),
        ]

    def __str__(self):
        return f"{self.food.name} @ {self.food_spot.name}: {self.rating}/5"
