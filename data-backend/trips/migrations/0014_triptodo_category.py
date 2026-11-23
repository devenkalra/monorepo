from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0013_ai_suggestions'),
    ]

    operations = [
        migrations.AddField(
            model_name='triptodo',
            name='category',
            field=models.CharField(blank=True, default='', max_length=60),
        ),
    ]
