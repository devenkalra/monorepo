import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

OWNER_EMAIL = 'deven@kalra.com'
VAC_MODELS = ('VacTag', 'VacCategory', 'VacItem', 'VacList', 'VacListItem')


def assign_existing_rows(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    User = apps.get_model(app_label, model_name)
    owner = (
        User.objects.filter(email__iexact=OWNER_EMAIL).order_by('id').first()
        or User.objects.filter(is_superuser=True).order_by('id').first()
        or User.objects.order_by('id').first()
    )
    has_rows = any(
        apps.get_model('vacation_list', name).objects.filter(user__isnull=True).exists()
        for name in VAC_MODELS
    )
    if not has_rows:
        return
    if owner is None:
        raise RuntimeError(
            'vacation_list user migration: existing rows need an owner but no auth user exists.'
        )
    for name in VAC_MODELS:
        Model = apps.get_model('vacation_list', name)
        Model.objects.filter(user__isnull=True).update(user_id=owner.pk)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('vacation_list', '0002_vaclist_is_archived'),
    ]

    operations = [
        migrations.AddField(
            model_name='vaccategory',
            name='user',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vacation_categories',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='vacitem',
            name='user',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vacation_items',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='vaclist',
            name='user',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vacation_lists',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='vaclistitem',
            name='user',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vacation_list_items',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='vactag',
            name='user',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vacation_tags',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(assign_existing_rows, noop_reverse),
        migrations.AlterField(
            model_name='vaccategory',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vacation_categories',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='vacitem',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vacation_items',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='vaclist',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vacation_lists',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='vaclistitem',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vacation_list_items',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='vactag',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vacation_tags',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name='vaccategory',
            index=models.Index(fields=['user'], name='vac_category_user_idx'),
        ),
        migrations.AddIndex(
            model_name='vacitem',
            index=models.Index(fields=['user'], name='vac_item_user_idx'),
        ),
        migrations.AddIndex(
            model_name='vaclist',
            index=models.Index(fields=['user'], name='vac_list_user_idx'),
        ),
        migrations.AddIndex(
            model_name='vaclistitem',
            index=models.Index(fields=['user'], name='vac_listitem_user_idx'),
        ),
        migrations.AddIndex(
            model_name='vactag',
            index=models.Index(fields=['user'], name='vac_tag_user_idx'),
        ),
        migrations.AddConstraint(
            model_name='vaccategory',
            constraint=models.UniqueConstraint(
                fields=('user', 'name'),
                name='vacation_list_vaccategory_user_name_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='vactag',
            constraint=models.UniqueConstraint(
                fields=('user', 'name'),
                name='vacation_list_vactag_user_name_uniq',
            ),
        ),
    ]
