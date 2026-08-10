import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('gmail_assistant', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SummarizeSchedule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('label', models.CharField(max_length=120)),
                ('prompt', models.TextField(blank=True, default='')),
                ('start_date', models.CharField(blank=True, default='', max_length=32)),
                ('end_date', models.CharField(blank=True, default='', max_length=32)),
                ('days', models.PositiveIntegerField(blank=True, null=True)),
                ('keyword', models.CharField(blank=True, default='', max_length=200)),
                ('max_results', models.PositiveIntegerField(default=100)),
                ('interval_hours', models.PositiveIntegerField(default=24)),
                ('force', models.BooleanField(default=False)),
                ('enabled', models.BooleanField(default=True)),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
                ('last_status', models.CharField(blank=True, default='', max_length=40)),
                ('last_error', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'account',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='summarize_schedules',
                        to='gmail_assistant.gmailaccount',
                    ),
                ),
                (
                    'last_job',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='+',
                        to='gmail_assistant.llmjob',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='gmail_summarize_schedules',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['label'],
            },
        ),
        migrations.AddConstraint(
            model_name='summarizeschedule',
            constraint=models.UniqueConstraint(
                fields=('user', 'label'),
                name='gmail_assistant_schedule_user_label_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='summarizeschedule',
            constraint=models.CheckConstraint(
                check=models.Q(interval_hours__gte=1) & models.Q(interval_hours__lte=168),
                name='gmail_assistant_schedule_interval_1_168',
            ),
        ),
    ]
