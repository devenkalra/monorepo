from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_notenode'),
    ]

    operations = [
        migrations.AlterField(
            model_name='page',
            name='content',
            field=models.TextField(blank=True, default='', help_text='Markdown content of the page (may be empty)'),
        ),
    ]
