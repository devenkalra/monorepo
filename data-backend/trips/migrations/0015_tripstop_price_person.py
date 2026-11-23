from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('trips', '0014_triptodo_category')]

    operations = [
        migrations.AddField(
            model_name='tripstop',
            name='price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='tripstop',
            name='currency',
            field=models.CharField(
                blank=True, default='', max_length=8,
                help_text='ISO code such as THB; blank means the default currency ($).',
            ),
        ),
        migrations.AddField(
            model_name='tripstop',
            name='person',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
    ]
