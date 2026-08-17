import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0005_tripstop_description'),
    ]

    operations = [
        migrations.AddField(
            model_name='tripstopattachment',
            name='lodging',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='attachments',
                to='trips.triplodging',
            ),
        ),
        migrations.AlterField(
            model_name='tripstopattachment',
            name='stop',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='attachments',
                to='trips.tripstop',
            ),
        ),
        migrations.AddIndex(
            model_name='tripstopattachment',
            index=models.Index(fields=['user', 'lodging'], name='tripattach_user_lodge_idx'),
        ),
        migrations.AddConstraint(
            model_name='tripstopattachment',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(('lodging__isnull', True), ('stop__isnull', False))
                    | models.Q(('lodging__isnull', False), ('stop__isnull', True))
                ),
                name='tripattach_stop_or_lodging',
            ),
        ),
    ]
