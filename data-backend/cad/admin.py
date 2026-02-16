"""CAD admin registration."""

from django.contrib import admin
from .models import CADModel


@admin.register(CADModel)
class CADModelAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "user", "created_at", "updated_at"]
    list_filter = ["created_at"]
    search_fields = ["name", "script"]
    raw_id_fields = ["user"]
