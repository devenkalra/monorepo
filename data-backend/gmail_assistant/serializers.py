from rest_framework import serializers

from .models import GmailAccount, SavedPrompt, SummarizeSchedule, UserPreference


class GmailAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = GmailAccount
        fields = (
            'id',
            'email',
            'label',
            'is_active',
            'last_error',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields


class UserPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreference
        fields = ('zero_knowledge', 'llm_context_size', 'updated_at')
        read_only_fields = ('updated_at',)

    def validate_llm_context_size(self, value):
        if value < 8192 or value > 64000:
            raise serializers.ValidationError('llm_context_size must be 8192–64000')
        return value


class SavedPromptSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedPrompt
        fields = ('id', 'label', 'prompt', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class SummarizeScheduleSerializer(serializers.ModelSerializer):
    account_id = serializers.UUIDField(write_only=True, required=False)
    account_email = serializers.EmailField(source='account.email', read_only=True)

    class Meta:
        model = SummarizeSchedule
        fields = (
            'id',
            'label',
            'prompt',
            'start_date',
            'end_date',
            'days',
            'keyword',
            'max_results',
            'interval_hours',
            'force',
            'enabled',
            'account_id',
            'account_email',
            'last_run_at',
            'last_status',
            'last_error',
            'last_job_id',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'account_email',
            'last_run_at',
            'last_status',
            'last_error',
            'last_job_id',
            'created_at',
            'updated_at',
        )

    def validate_interval_hours(self, value):
        if value < 1 or value > 168:
            raise serializers.ValidationError('interval_hours must be 1–168')
        return value

    def validate_max_results(self, value):
        if value < 1 or value > 200:
            raise serializers.ValidationError('max_results must be 1–200')
        return value

    def validate(self, attrs):
        prompt = attrs.get('prompt', getattr(self.instance, 'prompt', ''))
        start_date = attrs.get('start_date', getattr(self.instance, 'start_date', ''))
        end_date = attrs.get('end_date', getattr(self.instance, 'end_date', ''))
        days = attrs.get('days', getattr(self.instance, 'days', None))
        keyword = attrs.get('keyword', getattr(self.instance, 'keyword', ''))
        if not any(
            [
                (prompt or '').strip(),
                (start_date or '').strip(),
                (end_date or '').strip(),
                days is not None,
                (keyword or '').strip(),
            ]
        ):
            raise serializers.ValidationError(
                'Provide a prompt and/or search qualifiers (days/keyword/dates).'
            )
        return attrs
