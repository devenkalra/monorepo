from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0007_mail_campaign_html_draft'),
    ]

    operations = [
        migrations.AddField(
            model_name='mailcampaign',
            name='from_email',
            field=models.EmailField(
                blank=True, default='',
                help_text='Verified Gmail send-as address used as From', max_length=254),
        ),
        migrations.AddField(
            model_name='mailcampaign',
            name='from_name',
            field=models.CharField(
                blank=True, default='',
                help_text='Display name for the From header', max_length=255),
        ),
    ]
