from django.contrib import admin

from .models import ChangeLog, EntityEdit, ImportedTask, ReviewItem, SourceFile, SyncRun


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SyncRun)
class SyncRunAdmin(ReadOnlyAdmin):
    list_display = ('id', 'source', 'mode', 'status', 'ops', 'max_ops', 'created_by', 'created_at', 'finished_at')
    list_filter = ('source', 'mode', 'status')
    exclude = ('actions',)


@admin.register(ChangeLog)
class ChangeLogAdmin(ReadOnlyAdmin):
    list_display = ('id', 'run', 'op', 'task_name', 'field', 'ok', 'at')
    list_filter = ('op', 'ok')
    search_fields = ('task_id', 'task_name', 'field')


@admin.register(ReviewItem)
class ReviewItemAdmin(ReadOnlyAdmin):
    list_display = ('name', 'source', 'suggested_task_name', 'decision', 'decided_at')
    list_filter = ('source', 'decision')
    search_fields = ('name', 'key', 'suggested_task_name')


@admin.register(ImportedTask)
class ImportedTaskAdmin(ReadOnlyAdmin):
    list_display = ('source_id', 'target_id', 'list_key', 'run', 'created_at')
    search_fields = ('source_id', 'target_id', 'import_key')


@admin.register(EntityEdit)
class EntityEditAdmin(ReadOnlyAdmin):
    list_display = ('id', 'task_name', 'ok', 'edited_by', 'at')
    list_filter = ('ok',)
    search_fields = ('task_id', 'task_name', 'edited_by')


@admin.register(SourceFile)
class SourceFileAdmin(ReadOnlyAdmin):
    list_display = ('original_name', 'kind', 'rows', 'size', 'uploaded_at')
