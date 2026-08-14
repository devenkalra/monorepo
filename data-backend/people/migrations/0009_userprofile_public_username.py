from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0008_filereference'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='public_username',
            field=models.SlugField(blank=True, max_length=80, null=True, unique=True),
        ),
    ]
