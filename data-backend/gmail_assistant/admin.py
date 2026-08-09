from django.contrib import admin

from . import models


@admin.register(models.GmailAccount)
class GmailAccountAdmin(admin.ModelAdmin):
    list_display = ('email', 'user', 'is_active', 'updated_at')
    search_fields = ('email', 'user__username')
    readonly_fields = ('refresh_token',)


@admin.register(models.UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'zero_knowledge', 'llm_context_size')


@admin.register(models.SavedPrompt)
class SavedPromptAdmin(admin.ModelAdmin):
    list_display = ('label', 'user', 'updated_at')


@admin.register(models.EmailSummary)
class EmailSummaryAdmin(admin.ModelAdmin):
    list_display = ('gmail_id', 'account', 'category', 'updated_at')
    search_fields = ('gmail_id', 'subject')


@admin.register(models.LlmJob)
class LlmJobAdmin(admin.ModelAdmin):
    list_display = ('kind', 'status', 'user', 'created_at')
