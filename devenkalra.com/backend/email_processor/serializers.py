from rest_framework import serializers

from .models import Classification, EmailMessage, MailboxAccount, SavedSearch, WorkflowRun


class ClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classification
        fields = [
            'intent', 'confidence', 'summary', 'reason', 'extracted',
            'suggested_actions', 'risk_flags', 'model', 'bypassed_llm', 'created_at',
        ]


class WorkflowRunSerializer(serializers.ModelSerializer):
    message_subject = serializers.CharField(source='message.subject', read_only=True)

    class Meta:
        model = WorkflowRun
        fields = [
            'id', 'kind', 'status', 'external_ids', 'error',
            'started_at', 'finished_at', 'created_at', 'message', 'message_subject',
        ]


class EmailMessageSerializer(serializers.ModelSerializer):
    classification = ClassificationSerializer(read_only=True)
    runs = WorkflowRunSerializer(many=True, read_only=True)

    class Meta:
        model = EmailMessage
        fields = [
            'id', 'gmail_id', 'thread_id', 'subject', 'from_address', 'to_addresses',
            'snippet', 'received_at', 'label_ids', 'status', 'error',
            'classification', 'runs', 'created_at', 'updated_at',
        ]


class MailboxAccountSerializer(serializers.ModelSerializer):
    has_refresh_token = serializers.SerializerMethodField()

    class Meta:
        model = MailboxAccount
        fields = [
            'id', 'email', 'history_id', 'watch_expiration', 'last_sync_at',
            'last_error', 'is_active', 'has_refresh_token', 'created_at', 'updated_at',
        ]

    def get_has_refresh_token(self, obj):
        return bool(obj.refresh_token)


class SavedSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedSearch
        fields = ['id', 'label', 'prompt', 'gmail_query', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
