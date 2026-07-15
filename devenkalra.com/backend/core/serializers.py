from rest_framework import serializers
from .models import Page, MenuItem, Project, WorkflowIdea, BookReview, MusicTrack, Recipe, BlogCategory, BlogTag, BlogPost, Comment

class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ['id', 'title', 'category', 'slug', 'content', 'roles_with_access', 'render_as_html', 'created_at', 'updated_at']

class MenuItemSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    page_slug = serializers.CharField(source='page.slug', read_only=True, default=None)
    page_roles_with_access = serializers.CharField(source='page.roles_with_access', read_only=True, default="")

    class Meta:
        model = MenuItem
        fields = ['id', 'title', 'parent', 'page', 'page_slug', 'page_roles_with_access', 'order', 'external_url', 'show_in_menu', 'children']

    def get_children(self, obj):
        # Recursively serialize children and order them
        children_queryset = obj.children.all().order_by('order', 'title')
        return MenuItemSerializer(children_queryset, many=True, context=self.context).data

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
