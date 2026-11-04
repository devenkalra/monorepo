from django.contrib import admin

from .models import LinkRedirect


@admin.register(LinkRedirect)
class LinkRedirectAdmin(admin.ModelAdmin):
    list_display = ('slug', 'title', 'target_url', 'is_public', 'permanent', 'hit_count', 'updated_at')
    list_filter = ('is_public', 'permanent')
    search_fields = ('slug', 'title', 'target_url')
    readonly_fields = ('hit_count', 'created_at', 'updated_at')
