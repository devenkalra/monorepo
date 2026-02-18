"""Food app admin."""

from django.contrib import admin
from .models import FoodSpot, Food, Media, Review


@admin.register(FoodSpot)
class FoodSpotAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'added_by', 'created_at']


@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    list_display = ['name', 'added_by', 'created_at']
    filter_horizontal = ['served_at']


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = ['id', 'food_spot', 'food', 'created_at']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['id', 'rating', 'added_by', 'food_spot', 'food', 'created_at']
