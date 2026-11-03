from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0008_mail_campaign_from'),
    ]

    operations = [
        migrations.AddField(
            model_name='mailcampaign',
            name='attachments',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Frozen draft attachments: [{filename, mime_type, content_id, inline, data_b64}]',
            ),
        ),
    ]
