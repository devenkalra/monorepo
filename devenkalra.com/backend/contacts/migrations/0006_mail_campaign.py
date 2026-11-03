from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0005_lookup'),
    ]

    operations = [
        migrations.CreateModel(
            name='MailCampaign',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, default='', max_length=255)),
                ('subject_template', models.CharField(max_length=500)),
                ('body_template', models.TextField()),
                ('delivery', models.CharField(choices=[('draft', 'Gmail drafts'), ('send', 'Send')],
                                              default='draft', max_length=8)),
                ('status', models.CharField(
                    choices=[('draft', 'Draft'), ('ready', 'Ready'), ('running', 'Running'),
                             ('paused', 'Paused'), ('waiting_quota', 'Waiting for daily quota'),
                             ('completed', 'Completed'), ('cancelled', 'Cancelled'), ('failed', 'Failed')],
                    db_index=True, default='draft', max_length=16)),
                ('daily_limit', models.PositiveIntegerField(
                    default=1200, help_text='Max successful deliveries per calendar day (UTC)')),
                ('per_minute', models.PositiveIntegerField(
                    default=20, help_text='Max deliveries claimed per worker tick')),
                ('created_by', models.CharField(blank=True, default='', max_length=255)),
                ('error', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('last_tick_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-id'],
            },
        ),
        migrations.CreateModel(
            name='MailCampaignRecipient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task_id', models.CharField(db_index=True, max_length=32)),
                ('email', models.EmailField(max_length=254)),
                ('name', models.CharField(blank=True, default='', max_length=500)),
                ('merge_data', models.JSONField(blank=True, default=dict)),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('sending', 'Sending'), ('sent', 'Sent'),
                             ('drafted', 'Drafted'), ('skipped', 'Skipped'), ('failed', 'Failed')],
                    db_index=True, default='pending', max_length=16)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('last_error', models.TextField(blank=True, default='')),
                ('provider_message_id', models.CharField(blank=True, default='', max_length=128)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('campaign', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='recipients', to='contacts.mailcampaign')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.AddConstraint(
            model_name='mailcampaignrecipient',
            constraint=models.UniqueConstraint(fields=('campaign', 'email'),
                                               name='contacts_mail_campaign_email'),
        ),
    ]
