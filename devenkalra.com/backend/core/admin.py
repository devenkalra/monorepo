from django.contrib import admin
from django.utils.html import format_html
from django.shortcuts import render
from django.http import HttpResponseRedirect
from django import forms
from .models import Page, MenuItem, Project, WorkflowIdea, BookReview, MusicTrack, Recipe, StaticFile, PageData, BlogCategory, BlogTag, BlogPost, Comment, Subscription, SiteEvent, NoteNode

class BulkUpdateForm(forms.Form):
    status = forms.ChoiceField(
        choices=[('', '--- No Change ---')] + Project.STATUS_CHOICES, 
        required=False
    )
    category_dropdown = forms.ChoiceField(choices=[], required=False, label="Choose Category")
    category_custom = forms.CharField(max_length=100, required=False, label="Or enter custom category")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Fetch unique categories from existing projects
        categories = list(Project.objects.exclude(category='').values_list('category', flat=True).distinct().order_by('category'))
        self.fields['category_dropdown'].choices = [('', '--- No Change ---')] + [(cat, cat) for cat in categories]

@admin.action(description="Bulk Update Status/Category")
def bulk_update_projects(modeladmin, request, queryset):
    if 'apply' in request.POST:
        form = BulkUpdateForm(request.POST)
        # Re-initialize choice values to pass validation
        categories = list(Project.objects.exclude(category='').values_list('category', flat=True).distinct().order_by('category'))
        form.fields['category_dropdown'].choices = [('', '--- No Change ---')] + [(cat, cat) for cat in categories]
        
        if form.is_valid():
            status_value = form.cleaned_data.get('status')
            category_dropdown = form.cleaned_data.get('category_dropdown')
            category_custom = form.cleaned_data.get('category_custom')
            
            category_value = category_custom.strip() if category_custom else category_dropdown
            
            update_data = {}
            if status_value:
                update_data['status'] = status_value
            if category_value:
                update_data['category'] = category_value
                
            if update_data:
                updated_count = queryset.update(**update_data)
                modeladmin.message_user(request, f"Successfully updated {updated_count} projects.")
            else:
                modeladmin.message_user(request, "No changes were specified for bulk update.")
            return HttpResponseRedirect(request.get_full_path())
    else:
        form = BulkUpdateForm()
        
    return render(request, 'admin/bulk_update_projects.html', {
        'queryset': queryset,
        'form': form,
        'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        'opts': modeladmin.model._meta,
        'select_across': request.POST.get('select_across', '0'),
    })

@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'menu_path', 'slug', 'roles_with_access', 'render_as_html', 'updated_at')
    list_filter = ('category', 'roles_with_access', 'render_as_html')
    search_fields = ('title', 'category', 'content', 'roles_with_access', 'allowed_emails')
    prepopulated_fields = {'slug': ('title',)}

    def menu_path(self, obj):
        menu_item = obj.menu_items.first()
        return str(menu_item) if menu_item else "-"
    menu_path.short_description = "Menu Path"
    menu_path.admin_order_field = 'menu_items__full_path'

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'email',
        'name',
        'provider',
        'user',
        'blog_subscribed',
        'notify_on_article',
        'is_active',
        'subscribed_at',
        'updated_at',
    )
    list_filter = (
        'provider',
        'is_active',
        'blog_subscribed',
        'notify_on_article',
        'subscribed_at',
    )
    search_fields = ('email', 'name', 'user__username', 'user__email')
    raw_id_fields = ('user',)
    ordering = ('-subscribed_at',)
    readonly_fields = ('subscribed_at', 'updated_at')


@admin.register(SiteEvent)
class SiteEventAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'event',
        'path',
        'post',
        'page',
        'ip',
        'country',
        'user',
        'subscription',
        'session_key_short',
    )
    list_filter = ('event', 'country', 'created_at')
    search_fields = (
        'path',
        'ip',
        'referrer',
        'user_agent',
        'session_key',
        'post__slug',
        'post__title',
        'page__slug',
        'page__title',
        'user__email',
        'subscription__email',
    )
    raw_id_fields = ('page', 'post', 'user', 'subscription')
    readonly_fields = (
        'created_at',
        'event',
        'path',
        'page',
        'post',
        'ip',
        'user_agent',
        'country',
        'referrer',
        'session_key',
        'user',
        'subscription',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    @admin.display(description='Session')
    def session_key_short(self, obj):
        key = obj.session_key or ''
        return f'{key[:8]}…' if len(key) > 8 else key


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'parent', 'page', 'roles_with_access', 'show_in_menu', 'order')
    list_filter = ('parent', 'page', 'roles_with_access', 'show_in_menu')
    search_fields = ('title', 'roles_with_access')
    ordering = ('parent', 'order', 'title')

@admin.register(NoteNode)
class NoteNodeAdmin(admin.ModelAdmin):
    list_display = ('title', 'parent', 'page', 'is_folder_display', 'order', 'updated_at')
    list_filter = ('parent',)
    search_fields = ('title', 'page__title', 'page__slug')
    ordering = ('parent', 'order', 'title')
    raw_id_fields = ('page', 'parent')

    @admin.display(boolean=True, description='Folder')
    def is_folder_display(self, obj):
        return obj.is_folder

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('rank', 'title', 'parent', 'category', 'status', 'render_as_html', 'start_date', 'end_date')
    list_filter = ('parent', 'category', 'status')
    search_fields = ('title', 'description')
    actions = [bulk_update_projects]

@admin.register(WorkflowIdea)
class WorkflowIdeaAdmin(admin.ModelAdmin):
    list_display = ('title', 'priority', 'status', 'render_as_html', 'created_at')
    list_filter = ('priority', 'status')
    search_fields = ('title', 'description')

@admin.register(BookReview)
class BookReviewAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'rating', 'read_date')
    list_filter = ('rating',)
    search_fields = ('title', 'author', 'summary', 'review_content')

@admin.register(MusicTrack)
class MusicTrackAdmin(admin.ModelAdmin):
    list_display = ('title', 'artist', 'genre')
    list_filter = ('genre',)
    search_fields = ('title', 'artist', 'description')

@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ('title', 'prep_time_minutes')
    search_fields = ('title', 'ingredients', 'instructions')

@admin.register(StaticFile)
class StaticFileAdmin(admin.ModelAdmin):
    list_display = ('title', 'filename', 'file', 'copyable_file_url', 'make_local_copy', 'uploaded_at')
    search_fields = ('title',)
    readonly_fields = ('copyable_file_url',)

    def copyable_file_url(self, obj):
        if obj.file:
            url = obj.file.url
        elif obj.file_url:
            url = obj.file_url
        else:
            return "-"
        return format_html('<input type="text" readonly value="{}" style="width: 350px; font-family: monospace; font-size: 11px;" onclick="this.select();" />', url)
    copyable_file_url.short_description = "Copyable URL (Click to Select)"


@admin.register(PageData)
class PageDataAdmin(admin.ModelAdmin):
    list_display = ('page_slug', 'updated_at')
    search_fields = ('page_slug',)


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(BlogTag)
class BlogTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.action(description="Approve selected comments")
def approve_comments(modeladmin, request, queryset):
    updated = queryset.update(is_approved=True)
    modeladmin.message_user(request, f"Successfully approved {updated} comments.")


@admin.action(description="Reject/Unapprove selected comments")
def reject_comments(modeladmin, request, queryset):
    updated = queryset.update(is_approved=False)
    modeladmin.message_user(request, f"Successfully rejected {updated} comments.")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('author_name', 'author_email', 'post', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'created_at')
    search_fields = ('author_name', 'author_email', 'content', 'post__title')
    actions = [approve_comments, reject_comments]


@admin.action(description="Publish selected blog posts")
def publish_posts(modeladmin, request, queryset):
    import django.utils.timezone as timezone
    updated = queryset.update(is_published=True, publish_date=timezone.now())
    modeladmin.message_user(request, f"Successfully published {updated} blog posts.")


@admin.action(description="Revert selected blog posts to Draft")
def draft_posts(modeladmin, request, queryset):
    updated = queryset.update(is_published=False)
    modeladmin.message_user(request, f"Successfully set {updated} blog posts to draft.")


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'is_published', 'publish_date', 'comment_count', 'render_as_html', 'created_at')
    list_filter = ('category', 'is_published', 'render_as_html')
    search_fields = ('title', 'content', 'summary')
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ('tags',)
    actions = [publish_posts, draft_posts]
    readonly_fields = ('shareable_preview_link',)

    def comment_count(self, obj):
        return obj.comments.count()
    comment_count.short_description = "Comments"

    def shareable_preview_link(self, obj):
        from django.conf import settings
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:311').rstrip('/')
        if not obj.id:
            return "-"
        if obj.is_published:
            url = f"{frontend_url}/articles/{obj.slug}"
            return format_html('<span style="color: green; font-weight: bold;">Public</span> | <a href="{url}" target="_blank">Open Public Link</a>', url=url)
        if obj.preview_token:
            url = f"{frontend_url}/articles/{obj.slug}?token={obj.preview_token}"
            return format_html(
                '<a href="{url}" target="_blank">Open Preview Link</a> | Copy path: <input type="text" readonly value="{url}" style="width: 380px; font-family: monospace; font-size: 11px;" onclick="this.select();" />',
                url=url
            )
        return "-"
    shareable_preview_link.short_description = "Shareable Preview Link"

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('import-substack/', self.admin_site.admin_view(self.import_substack_view), name='core_blogpost_import_substack'),
        ]
        return custom_urls + urls

    def import_substack_view(self, request):
        from django.http import JsonResponse
        if request.method != 'POST':
            return JsonResponse({'error': 'Only POST requests are allowed.'}, status=405)
            
        url = request.POST.get('url', '').strip()
        if not url:
            return JsonResponse({'error': 'Substack URL is required.'}, status=400)
            
        try:
            from .substack_importer import scrape_substack_post_content
            data = scrape_substack_post_content(url)
            return JsonResponse(data)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)


