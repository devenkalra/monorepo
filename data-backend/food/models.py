"""Food app models - FoodSpot, Food, Media, Review."""

from django.db import models
from django.contrib.auth.models import User


class FoodSpot(models.Model):
    """A place that serves food (restaurant, cafe, etc.)."""

    added_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='food_spots')
    name = models.CharField(max_length=255)
    # Each location: {street, city, state, country, postal_code, phone}
    locations = models.JSONField(default=list, blank=True, null=True)
    description = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True, null=True)  # Single-level tags, e.g. ["vegan", "breakfast"]
    photos = models.JSONField(default=list, blank=True, null=True)  # Same scheme as people: list of {url, thumbnail_url} or url strings
    attachments = models.JSONField(default=list, blank=True, null=True)
    urls = models.JSONField(default=list, blank=True, null=True)  # External links e.g. YouTube
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-modified_at']
        indexes = [
            models.Index(fields=['added_by']),
        ]

    def __str__(self):
        return self.name


class Food(models.Model):
    """A food item that can be served at multiple spots."""

    added_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='foods')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    alsocalled = models.CharField(max_length=500, blank=True)
    served_at = models.ManyToManyField(FoodSpot, blank=True, related_name='foods')
    tags = models.JSONField(default=list, blank=True, null=True)  # Single-level tags, e.g. ["dessert", "spicy"]
    photos = models.JSONField(default=list, blank=True, null=True)
    attachments = models.JSONField(default=list, blank=True, null=True)
    urls = models.JSONField(default=list, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-modified_at']
        indexes = [
            models.Index(fields=['added_by']),
        ]

    def __str__(self):
        return self.name


class Media(models.Model):
    """Photo, video, or YouTube link attached to a FoodSpot or Food."""

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


class Review(models.Model):
    """Review for a FoodSpot or Food."""

    added_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='food_reviews')
    rating = models.PositiveSmallIntegerField()
    note = models.TextField(blank=True)
    food_spot = models.ForeignKey(FoodSpot, null=True, blank=True, on_delete=models.CASCADE, related_name='reviews')
    food = models.ForeignKey(Food, null=True, blank=True, on_delete=models.CASCADE, related_name='reviews')
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Review {self.rating}/5"
