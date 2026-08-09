# Generated manually for gmail_assistant

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='GmailAccount',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254)),
                ('label', models.CharField(blank=True, default='', max_length=120)),
                ('refresh_token', models.TextField()),
                ('scopes', models.TextField(blank=True, default='')),
                ('is_active', models.BooleanField(default=False)),
                ('last_error', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gmail_accounts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['email'],
            },
        ),
        migrations.CreateModel(
            name='UserPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('zero_knowledge', models.BooleanField(default=False)),
                ('llm_context_size', models.PositiveIntegerField(default=8192)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='gmail_assistant_prefs', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='SavedPrompt',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('label', models.CharField(max_length=120)),
                ('prompt', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gmail_saved_prompts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['label'],
            },
        ),
        migrations.CreateModel(
            name='EmailSummary',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('gmail_id', models.CharField(max_length=64)),
                ('thread_id', models.CharField(blank=True, default='', max_length=64)),
                ('subject', models.TextField(blank=True, default='')),
                ('from_addr', models.TextField(blank=True, default='')),
                ('snippet', models.TextField(blank=True, default='')),
                ('date_iso', models.CharField(blank=True, default='', max_length=64)),
                ('internal_date_ms', models.BigIntegerField(default=0)),
                ('brief_summary', models.TextField(blank=True, default='')),
                ('key_points', models.JSONField(blank=True, default=list)),
                ('details', models.TextField(blank=True, default='')),
                ('category', models.CharField(blank=True, default='', max_length=40)),
                ('category_confidence', models.FloatField(default=0)),
                ('labels', models.JSONField(blank=True, default=list)),
                ('status', models.CharField(default='active', max_length=20)),
                ('model', models.CharField(blank=True, default='', max_length=120)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='summaries', to='gmail_assistant.gmailaccount')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gmail_summaries', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='LlmJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('summarize', 'Summarize'), ('process', 'Process')], max_length=20)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('celery_task_id', models.CharField(blank=True, default='', max_length=64)),
                ('gmail_ids', models.JSONField(blank=True, default=list)),
                ('prompt', models.TextField(blank=True, default='')),
                ('result', models.TextField(blank=True, default='')),
                ('progress', models.JSONField(blank=True, default=dict)),
                ('errors', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='llm_jobs', to='gmail_assistant.gmailaccount')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gmail_llm_jobs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='gmailaccount',
            constraint=models.UniqueConstraint(fields=('user', 'email'), name='gmail_assistant_account_user_email_uniq'),
        ),
        migrations.AddIndex(
            model_name='gmailaccount',
            index=models.Index(fields=['user', 'is_active'], name='gmail_assis_user_id_0f3c8a_idx'),
        ),
        migrations.AddConstraint(
            model_name='savedprompt',
            constraint=models.UniqueConstraint(fields=('user', 'label'), name='gmail_assistant_prompt_user_label_uniq'),
        ),
        migrations.AddConstraint(
            model_name='emailsummary',
            constraint=models.UniqueConstraint(fields=('account', 'gmail_id'), name='gmail_assistant_summary_account_mid_uniq'),
        ),
        migrations.AddIndex(
            model_name='emailsummary',
            index=models.Index(fields=['user', 'account'], name='gmail_assis_user_id_a1b2c3_idx'),
        ),
        migrations.AddIndex(
            model_name='emailsummary',
            index=models.Index(fields=['gmail_id'], name='gmail_assis_gmail_i_d4e5f6_idx'),
        ),
    ]
