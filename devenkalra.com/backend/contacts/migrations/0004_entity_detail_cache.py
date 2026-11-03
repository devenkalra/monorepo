from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0003_entity_editor'),
    ]

    operations = [
        migrations.CreateModel(
            name='EntityDetailCache',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task_id', models.CharField(max_length=64, unique=True)),
                ('payload', models.JSONField(default=dict)),
                ('date_updated', models.CharField(
                    blank=True, default='',
                    help_text='ClickUp date_updated when the payload was stored',
                    max_length=32,
                )),
                ('cached_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
