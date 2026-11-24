from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0022_tripshare_invite_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='notify_on_comments',
            field=models.BooleanField(default=False),
        ),
    ]
