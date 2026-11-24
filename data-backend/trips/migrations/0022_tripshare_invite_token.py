import secrets

from django.db import migrations, models


def populate_invite_tokens(apps, schema_editor):
    TripShare = apps.get_model('trips', 'TripShare')
    for share in TripShare.objects.filter(models.Q(invite_token__isnull=True) | models.Q(invite_token='')):
        share.invite_token = secrets.token_urlsafe(24)
        share.save(update_fields=['invite_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0021_sharing_and_comments'),
    ]

    operations = [
        migrations.AddField(
            model_name='tripshare',
            name='invite_token',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.RunPython(populate_invite_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='tripshare',
            name='invite_token',
            field=models.CharField(blank=True, default='', max_length=64, unique=True),
        ),
    ]
