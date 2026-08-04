from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vacation_list', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='vaclist',
            name='is_archived',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='Archived lists are hidden from the default list picker.',
            ),
        ),
    ]
