from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0006_mail_campaign'),
    ]

    operations = [
        migrations.AddField(
            model_name='mailcampaign',
            name='body_html_template',
            field=models.TextField(blank=True, default='',
                                   help_text='HTML body from a Gmail draft template'),
        ),
        migrations.AddField(
            model_name='mailcampaign',
            name='source_draft_id',
            field=models.CharField(blank=True, default='',
                                   help_text='Gmail draft id used as the template source', max_length=64),
        ),
        migrations.AlterField(
            model_name='mailcampaign',
            name='body_template',
            field=models.TextField(blank=True, default='',
                                   help_text='Plain-text body (fallback / preview)'),
        ),
    ]
