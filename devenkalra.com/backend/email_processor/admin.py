from django.contrib import admin

from .models import (
    Classification,
    CommandSession,
    EmailJob,
    EmailMessage,
    MailboxAccount,
    SavedSearch,
    WorkflowRun,
)


@admin.register(MailboxAccount)
class MailboxAccountAdmin(admin.ModelAdmin):
    list_display = ('email', 'is_active', 'history_id', 'watch_expiration', 'last_sync_at')
    readonly_fields = ('created_at', 'updated_at')


class ClassificationInline(admin.StackedInline):
    model = Classification
    extra = 0


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    list_display = ('subject', 'from_address', 'status', 'received_at', 'gmail_id')
    list_filter = ('status',)
    search_fields = ('subject', 'from_address', 'gmail_id', 'snippet')
    inlines = [ClassificationInline]


@admin.register(WorkflowRun)
class WorkflowRunAdmin(admin.ModelAdmin):
    list_display = ('kind', 'status', 'message', 'created_at', 'finished_at')
    list_filter = ('kind', 'status')


@admin.register(CommandSession)
class CommandSessionAdmin(admin.ModelAdmin):
    list_display = ('session_key', 'user_id', 'gmail_query', 'item_count', 'expires_at', 'updated_at')
    search_fields = ('session_key', 'prompt', 'gmail_query')
    readonly_fields = ('created_at', 'updated_at', 'items', 'last_action')

    @admin.display(description='Items')
    def item_count(self, obj):
        return len(obj.items or [])


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_id', 'label', 'prompt_short', 'gmail_query', 'updated_at')
    search_fields = ('label', 'prompt', 'gmail_query')
    list_filter = ('user_id',)
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Prompt')
    def prompt_short(self, obj):
        return (obj.prompt or '')[:80]


@admin.register(EmailJob)
class EmailJobAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'job_type', 'status', 'message_label', 'result_summary',
        'attempts', 'error_short', 'updated_at',
    )
    list_filter = ('job_type', 'status')
    search_fields = ('error', 'message__subject', 'message__gmail_id')
    readonly_fields = ('created_at', 'updated_at', 'payload', 'error')
    raw_id_fields = ('mailbox', 'message')

    @admin.display(description='Message')
    def message_label(self, obj):
        if not obj.message_id:
            return '—'
        subj = (obj.message.subject or '(no subject)')[:60]
        return f'#{obj.message_id} {subj}'

    @admin.display(description='Result')
    def result_summary(self, obj):
        result = (obj.payload or {}).get('result') or {}
        if not result:
            return '—'
        if obj.job_type == EmailJob.JobType.CLASSIFY:
            intent = result.get('intent') or '?'
            conf = result.get('confidence')
            conf_s = f'{float(conf):.0%}' if conf is not None else '?'
            nxt = result.get('next') or result.get('message_status') or ''
            summary = (result.get('summary') or '')[:80]
            return f'{intent} {conf_s} → {nxt}' + (f' | {summary}' if summary else '')
        if obj.job_type == EmailJob.JobType.RUN_WORKFLOW:
            return f"{result.get('kind')} {result.get('status')} {result.get('external_ids') or ''}"
        return str(result)[:120]

    @admin.display(description='Error')
    def error_short(self, obj):
        return (obj.error or '')[:80] or '—'
