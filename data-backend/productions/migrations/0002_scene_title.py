from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productions', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='scene',
            name='title',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
