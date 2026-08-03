from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0025_evolve_subscription_preferences'),
    ]

    operations = [
        migrations.CreateModel(
            name='SiteEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('event', models.CharField(
                    choices=[('page_view', 'Page view')],
                    db_index=True,
                    default='page_view',
                    max_length=32,
                )),
                ('path', models.CharField(db_index=True, max_length=500)),
                ('ip', models.GenericIPAddressField(blank=True, db_index=True, null=True)),
                ('user_agent', models.CharField(blank=True, default='', max_length=400)),
                ('country', models.CharField(
                    blank=True,
                    default='',
                    help_text='CF-IPCountry when present',
                    max_length=8,
                )),
                ('referrer', models.CharField(blank=True, default='', max_length=500)),
                ('session_key', models.CharField(blank=True, db_index=True, default='', max_length=64)),
                ('page', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='site_events',
                    to='core.page',
                )),
                ('post', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='site_events',
                    to='core.blogpost',
                )),
                ('subscription', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='site_events',
                    to='core.subscription',
                )),
                ('user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='site_events',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Site event',
                'verbose_name_plural': 'Site events',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='siteevent',
            index=models.Index(fields=['-created_at', 'event'], name='core_siteev_created_6d3c1a_idx'),
        ),
        migrations.AddIndex(
            model_name='siteevent',
            index=models.Index(fields=['post', '-created_at'], name='core_siteev_post_id_8a2f0b_idx'),
        ),
        migrations.AddIndex(
            model_name='siteevent',
            index=models.Index(fields=['page', '-created_at'], name='core_siteev_page_id_1c4e9d_idx'),
        ),
    ]
