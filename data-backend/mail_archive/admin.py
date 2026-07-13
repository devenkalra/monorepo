from django.contrib import admin
from .models import EmailAccount, ImportConfig, Email


@admin.register(EmailAccount)
class EmailAccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'email_address', 'user', 'imap_host', 'is_active', 'last_sync']
    list_filter = ['is_active', 'user']
    search_fields = ['name', 'email_address', 'imap_host']
    readonly_fields = ['created_at', 'updated_at', 'last_sync']


@admin.register(ImportConfig)
class ImportConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'account', 'mailbox', 'is_active', 'max_emails']
    list_filter = ['is_active', 'account']
    search_fields = ['name', 'from_filter', 'to_filter', 'subject_filter']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Email)
class EmailAdmin(admin.ModelAdmin):
    list_display = ['subject', 'from_address', 'date', 'account', 'has_attachments', 'created_at']
    list_filter = ['account', 'has_attachments', 'date']
    search_fields = ['subject', 'from_address', 'message_id']
    readonly_fields = ['created_at', 'updated_at', 'message_id', 'eml_file_path']
    date_hierarchy = 'date'
