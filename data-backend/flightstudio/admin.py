from django.contrib import admin

from .models import FlightPath


@admin.register(FlightPath)
class FlightPathAdmin(admin.ModelAdmin):
    list_display = ('path_id', 'owner', 'updated_at')
    search_fields = ('path_id',)
    list_filter = ('owner',)
