from rest_framework import serializers
from .models import EmailAccount, ImportConfig, Email


class EmailAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailAccount
        fields = [
            'id', 'name', 'email_address', 'imap_host', 'imap_port', 
            'imap_use_ssl', 'username', 'password', 'is_active', 
            'last_sync', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'created_at': {'read_only': True},
            'updated_at': {'read_only': True},
            'last_sync': {'read_only': True},
        }


class ImportConfigSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_email = serializers.CharField(source='account.email_address', read_only=True)
    
    class Meta:
        model = ImportConfig
        fields = [
            'id', 'account', 'account_name', 'account_email', 'name', 
            'mailbox', 'from_filter', 'to_filter', 'subject_filter', 
            'labels', 'since_date', 'to_date', 'max_emails', 'is_active',
            'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'created_at': {'read_only': True},
            'updated_at': {'read_only': True},
        }


class EmailSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_email = serializers.CharField(source='account.email_address', read_only=True)
    
    class Meta:
        model = Email
        fields = [
            'id', 'account', 'account_name', 'account_email',
            'message_id', 'subject', 'from_address', 'to_addresses', 
            'cc_addresses', 'bcc_addresses', 'date', 'received_date',
            'body_text', 'body_html', 'has_attachments', 'attachment_count',
            'eml_file_path', 'file_size', 'labels', 'thread_id',
            'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'created_at': {'read_only': True},
            'updated_at': {'read_only': True},
            'eml_file_path': {'read_only': True},
            'file_size': {'read_only': True},
        }


class EmailListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views (excludes body content)"""
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = Email
        fields = [
            'id', 'account', 'account_name', 'message_id', 'subject', 
            'from_address', 'to_addresses', 'date', 'has_attachments', 
            'attachment_count', 'labels', 'created_at'
        ]
