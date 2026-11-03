from django.contrib import admin

from .models import LinkMedia


@admin.register(LinkMedia)
class LinkMediaAdmin(admin.ModelAdmin):
    list_display = ('slug', 'title', 'byte_size', 'is_public', 'download_count', 'updated_at')
    list_filter = ('is_public',)
    search_fields = ('slug', 'title')
    readonly_fields = ('byte_size', 'content_type', 'download_count', 'created_at', 'updated_at')
