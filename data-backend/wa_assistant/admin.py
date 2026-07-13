from django.contrib import admin
from .models import WhatsAppMessage, WhatsAppMedia


class WhatsAppMediaInline(admin.TabularInline):
    model = WhatsAppMedia
    extra = 0
    readonly_fields = ['wa_media_id', 'mime_type', 'sha256', 'path', 'url', 'file_size', 'created_at']


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ['wa_message_id', 'wa_from', 'wa_to', 'msg_type', 'wa_timestamp', 'created_at']
    list_filter = ['msg_type', 'created_at']
    search_fields = ['wa_message_id', 'wa_from', 'wa_to', 'text_body']
    readonly_fields = ['wa_message_id', 'wa_from', 'wa_to', 'wa_timestamp', 'msg_type', 'text_body', 'raw_payload', 'created_at']
    inlines = [WhatsAppMediaInline]


@admin.register(WhatsAppMedia)
class WhatsAppMediaAdmin(admin.ModelAdmin):
    list_display = ['wa_media_id', 'message', 'mime_type', 'file_size', 'created_at']
    list_filter = ['mime_type', 'created_at']
    search_fields = ['wa_media_id', 'path']
