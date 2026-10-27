from rest_framework import serializers

from .models import ChangeLog, ReviewItem, SourceFile, SyncRun
from .runner import apply_refusal


class SourceFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceFile
        fields = ['id', 'kind', 'original_name', 'size', 'rows', 'uploaded_at']


class SyncRunSerializer(serializers.ModelSerializer):
    files = SourceFileSerializer(many=True, read_only=True)
    output = SourceFileSerializer(read_only=True)
    has_snapshot = serializers.SerializerMethodField()
    applied_by = serializers.SerializerMethodField()
    apply_blocker = serializers.SerializerMethodField()
    warning_count = serializers.SerializerMethodField()

    class Meta:
        model = SyncRun
        fields = ['id', 'source', 'mode', 'status', 'options', 'files', 'plan', 'max_ops', 'ops', 'stats', 'error',
                  'phase', 'progress_done', 'progress_total', 'cancel_requested', 'created_by', 'created_at',
                  'started_at', 'finished_at', 'has_snapshot', 'applied_by', 'apply_blocker', 'warning_count',
                  'output']

    def get_has_snapshot(self, run):
        return bool(run.snapshot_path)

    def get_applied_by(self, run):
        return [r.pk for r in run.applied_by.all()]

    def get_apply_blocker(self, run):
        if run.mode != SyncRun.Mode.DRY:
            return None
        return apply_refusal(run)

    def get_warning_count(self, run):
        return len(run.warnings or [])


class SyncRunDetailSerializer(SyncRunSerializer):
    change_counts = serializers.SerializerMethodField()

    class Meta(SyncRunSerializer.Meta):
        fields = SyncRunSerializer.Meta.fields + ['actions', 'warnings', 'unknown_groups', 'unknown_sources',
                                                  'change_counts']

    def get_change_counts(self, run):
        qs = run.changes.all()
        return {'total': qs.count(), 'failed': qs.filter(ok=False).count()}


class ChangeLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChangeLog
        fields = ['id', 'op', 'task_id', 'task_name', 'field', 'before', 'after', 'ok', 'error', 'at']


class ReviewItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewItem
        fields = ['id', 'source', 'key', 'name', 'company', 'title', 'suggested_task_id', 'suggested_task_name',
                  'note', 'decision', 'chosen_task_id', 'decided_by', 'decided_at', 'last_seen_run', 'updated_at']
