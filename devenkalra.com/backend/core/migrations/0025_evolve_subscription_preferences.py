from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copy_is_active_to_blog_prefs(apps, schema_editor):
    """Existing active contacts keep blog opt-in; new defaults stay False."""
    Subscription = apps.get_model('core', 'Subscription')
    for sub in Subscription.objects.filter(is_active=True):
        sub.blog_subscribed = True
        sub.notify_on_article = True
        sub.save(update_fields=['blog_subscribed', 'notify_on_article'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0024_page_content_blank'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='blog_subscribed',
            field=models.BooleanField(
                default=False,
                help_text='Opted in to the blog mailing list',
            ),
        ),
        migrations.AddField(
            model_name='subscription',
            name='notify_on_article',
            field=models.BooleanField(
                default=False,
                help_text='Email when a new blog article is published',
            ),
        ),
        migrations.AddField(
            model_name='subscription',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='subscription',
            name='user',
            field=models.ForeignKey(
                blank=True,
                help_text='Linked Django user when known (social or staff login)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='subscriptions',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='is_active',
            field=models.BooleanField(
                default=True,
                help_text='Master switch: inactive contacts are excluded from all outreach',
            ),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='provider',
            field=models.CharField(
                blank=True,
                default='google',
                help_text='Social auth provider (e.g. google, github), if any',
                max_length=50,
            ),
        ),
        migrations.AlterModelOptions(
            name='subscription',
            options={
                'ordering': ['-subscribed_at'],
                'verbose_name': 'Subscription / preferences',
                'verbose_name_plural': 'Subscriptions / preferences',
            },
        ),
        migrations.RunPython(copy_is_active_to_blog_prefs, migrations.RunPython.noop),
    ]
