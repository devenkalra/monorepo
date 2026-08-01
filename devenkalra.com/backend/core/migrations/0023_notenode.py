from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0022_menuitem_roles_with_access'),
    ]

    operations = [
        migrations.CreateModel(
            name='NoteNode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(help_text='Folder name, or display title for a linked page (defaults to page title).', max_length=200)),
                ('order', models.PositiveIntegerField(default=0, help_text='Sort order within the parent folder')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('page', models.ForeignKey(blank=True, help_text='Linked page. Leave blank to create a folder.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='note_nodes', to='core.page')),
                ('parent', models.ForeignKey(blank=True, help_text='Parent folder. Leave blank for root-level items.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='core.notenode')),
            ],
            options={
                'ordering': ['order', 'title'],
            },
        ),
    ]
