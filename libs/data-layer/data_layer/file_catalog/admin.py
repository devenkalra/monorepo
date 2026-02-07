from django.contrib import admin
from django.utils.html import format_html
from .models import File

@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    # 1. Columns to show in the list view
    list_display = (
        'thumbnail_preview',
        'name',
        'volume',
        'file_size_mb',
        'last_seen',
        'created_at_display' # If you want to show creation time
    )

    # 2. Clickable links in the list
    list_display_links = ('name', 'thumbnail_preview')

    # 3. Sidebar Filters
    list_filter = ('volume', 'last_seen')

    # 4. Search Box (Search by name, path, or hash)
    search_fields = ('name', 'path', 'hash')

    # 5. Read-Only Fields
    # It is safer to make hash and size read-only so admins don't
    # accidentally break the integrity of the catalog.
    readonly_fields = ('hash', 'size', 'thumbnail_preview_large')

    # 6. Organize the Edit Form
    fieldsets = (
        ('File Identity', {
            'fields': ('volume', 'path', 'name')
        }),
        ('Metadata', {
            'fields': ('hash', 'size', 'last_seen')
        }),
        ('Visuals', {
            'fields': ('thumbnail', 'thumbnail_preview_large')
        }),
    )

    # --- CUSTOM METHODS ---

    def thumbnail_preview(self, obj):
        """Small preview for the list view"""
        if obj.thumbnail:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 4px;" />',
                obj.thumbnail.url
            )
        return "-"
    thumbnail_preview.short_description = "Preview"

    def thumbnail_preview_large(self, obj):
        """Large preview for the detail view"""
        if obj.thumbnail:
            return format_html(
                '<img src="{}" style="max-width: 300px; max-height: 300px;" />',
                obj.thumbnail.url
            )
        return "No Thumbnail"
    thumbnail_preview_large.short_description = "Thumbnail Preview"

    def file_size_mb(self, obj):
        """Convert bytes to MB for readability"""
        if obj.size:
            mb = obj.size / (1024 * 1024)
            return f"{mb:.2f} MB"
        return "0 MB"
    file_size_mb.short_description = "Size"

    def created_at_display(self, obj):
        # Since we don't have an explicit created_at, we can infer it
        # or just leave it out if not needed.
        # If you added auto_now_add=True field, use that here.
        return "-"
    created_at_display.short_description = "Created"