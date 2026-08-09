from rest_framework import serializers

from .models import GmailAccount, SavedPrompt, UserPreference


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
