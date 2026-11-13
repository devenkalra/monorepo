from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0007_tripstop_travel'),
    ]

    operations = [
        migrations.AddField(
            model_name='tripday',
            name='notes',
            field=models.TextField(
                blank=True,
                default='',
                help_text='High-level planning notes for the day (distinct from the travelog journal).',
            ),
        ),
    ]
