from rest_framework import serializers
from .models import Page, MenuItem, Project, WorkflowIdea, BookReview, MusicTrack, Recipe, BlogCategory, BlogTag, BlogPost, Comment

class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = [
            'id', 'title', 'category', 'slug', 'content',
            'roles_with_access', 'render_as_html', 'allowed_emails',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class MenuItemSerializer(serializers.ModelSerializer):
    """Nested tree serializer for the public menu endpoint."""
    children = serializers.SerializerMethodField()
    page_slug = serializers.CharField(source='page.slug', read_only=True, default=None)
    page_roles_with_access = serializers.CharField(source='page.roles_with_access', read_only=True, default="")
    roles_with_access = serializers.CharField(read_only=True, default="")

    class Meta:
        model = MenuItem
        fields = ['id', 'title', 'parent', 'page', 'page_slug', 'page_roles_with_access', 'roles_with_access', 'order', 'external_url', 'show_in_menu', 'children']

    def _has_menu_access(self, obj):
        required_roles = [r.strip().lower() for r in (obj.roles_with_access or '').split(',') if r.strip()]
        if not required_roles:
            return True

        user_role = self.context.get('user_role')
        if not user_role:
            return False

        if user_role == 'superuser':
            return True

        return user_role in required_roles

    def get_children(self, obj):
        # Recursively serialize children and order them
        children_queryset = obj.children.all().order_by('order', 'title')
        children_queryset = [child for child in children_queryset if self._has_menu_access(child)]
        return MenuItemSerializer(children_queryset, many=True, context=self.context).data


class MenuItemCRUDSerializer(serializers.ModelSerializer):
    """Flat serializer for menu-item CRUD (create/update/list)."""
    page_slug = serializers.CharField(source='page.slug', read_only=True, default=None)

    class Meta:
        model = MenuItem
        fields = [
            'id', 'title', 'parent', 'page', 'page_slug', 'order',
            'roles_with_access', 'external_url', 'show_in_menu', 'full_path',
        ]
        read_only_fields = ['id', 'full_path', 'page_slug']


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = '__all__'

class WorkflowIdeaSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowIdea
        fields = '__all__'

class BookReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookReview
        fields = '__all__'

class MusicTrackSerializer(serializers.ModelSerializer):
    class Meta:
        model = MusicTrack
        fields = '__all__'

class RecipeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recipe
        fields = '__all__'

class BlogCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogCategory
        fields = ['id', 'name', 'slug']

class BlogTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogTag
        fields = ['id', 'name', 'slug']

class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ['id', 'post', 'author_name', 'author_email', 'content', 'is_approved', 'created_at']
        read_only_fields = ['id', 'is_approved', 'created_at']

class BlogPostSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)
    category_slug = serializers.CharField(source='category.slug', read_only=True, default=None)
    tags_detail = BlogTagSerializer(source='tags', many=True, read_only=True)

    class Meta:
        model = BlogPost
        fields = [
            'id', 'title', 'slug', 'content', 'summary', 'cover_image', 
            'render_as_html', 'category', 'category_name', 'category_slug',
            'tags', 'tags_detail', 'is_published', 'publish_date', 'preview_token', 'created_at', 'updated_at'
        ]
