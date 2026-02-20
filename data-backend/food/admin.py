"""Food app admin."""

from django.contrib import admin
from .models import FoodSpot, Food, FoodSpotList, FoodList, Media, Review, FoodSpotFoodRating


@admin.register(FoodSpot)
class FoodSpotAdmin(admin.ModelAdmin):
    list_display = ['name', 'locations_summary', 'added_by', 'created_at']

    @admin.display(description='Locations')
    def locations_summary(self, obj):
        if not obj.locations:
            return '-'
        parts = [obj.locations[0].get('street'), obj.locations[0].get('city'), obj.locations[0].get('state')]
        addr = ', '.join(p for p in parts if p)
        if len(obj.locations) > 1:
            addr += f' (+{len(obj.locations) - 1})'
        return addr or '-'


@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    list_display = ['name', 'added_by', 'created_at']
    filter_horizontal = ['served_at']


@admin.register(FoodSpotList)
class FoodSpotListAdmin(admin.ModelAdmin):
    list_display = ['name', 'added_by', 'created_at']
    filter_horizontal = ['spots']


@admin.register(FoodList)
class FoodListAdmin(admin.ModelAdmin):
    list_display = ['name', 'added_by', 'created_at']
    filter_horizontal = ['foods']


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = ['id', 'food_spot', 'food', 'created_at']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['id', 'rating', 'added_by', 'food_spot', 'food', 'created_at']


@admin.register(FoodSpotFoodRating)
class FoodSpotFoodRatingAdmin(admin.ModelAdmin):
    list_display = ['id', 'food', 'food_spot', 'rating', 'added_by', 'created_at']
