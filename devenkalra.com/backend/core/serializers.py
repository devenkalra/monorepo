from rest_framework import serializers
from .models import Page, MenuItem, Project, WorkflowIdea, BookReview, MusicTrack, Recipe, BlogCategory, BlogTag, BlogPost, Comment, NoteNode, normalize_escaped_newlines

class PageSerializer(serializers.ModelSerializer):
    content = serializers.CharField(required=False, allow_blank=True, default="")

    class Meta:
        model = Page
        fields = [
            'id', 'title', 'category', 'slug', 'content',
            'roles_with_access', 'render_as_html', 'allowed_emails',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_content(self, value):
        return normalize_escaped_newlines(value or "")

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


class NoteNodeSerializer(serializers.ModelSerializer):
    """Flat CRUD serializer for note folders and page links."""
    is_folder = serializers.BooleanField(read_only=True)
    page_slug = serializers.CharField(source='page.slug', read_only=True, default=None)
    page_title = serializers.CharField(source='page.title', read_only=True, default=None)

    class Meta:
        model = NoteNode
        fields = [
            'id', 'title', 'parent', 'page', 'page_slug', 'page_title',
            'is_folder', 'order', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'is_folder', 'page_slug', 'page_title', 'created_at', 'updated_at']

    def validate(self, attrs):
        parent = attrs.get('parent', getattr(self.instance, 'parent', None))
        page = attrs.get('page', getattr(self.instance, 'page', None) if self.instance else None)
        # Allow clearing page on update via explicit null
        if self.instance and 'page' in attrs:
            page = attrs['page']

        if parent is not None and parent.page_id is not None:
            raise serializers.ValidationError({'parent': 'Parent must be a folder, not a page link.'})

        if parent is not None and self.instance and parent.pk == self.instance.pk:
            raise serializers.ValidationError({'parent': 'A node cannot be its own parent.'})

        # Cycle check when reparenting
        if parent is not None and self.instance:
            cursor = parent
            while cursor is not None:
                if cursor.pk == self.instance.pk:
                    raise serializers.ValidationError({'parent': 'Cannot create a circular folder hierarchy.'})
                cursor = cursor.parent

        # Default title from page when linking
        title = attrs.get('title')
        if page is not None and not title and not (self.instance and self.instance.title):
            attrs['title'] = page.title
        elif page is not None and not title and self.instance and not attrs.get('title'):
            if 'title' in attrs and not attrs['title']:
                attrs['title'] = page.title

        return attrs

    def create(self, validated_data):
        page = validated_data.get('page')
        if page and not validated_data.get('title'):
            validated_data['title'] = page.title
        return super().create(validated_data)


class NoteNodeTreeSerializer(serializers.ModelSerializer):
    """Nested tree for the Notes sidebar."""
    children = serializers.SerializerMethodField()
    is_folder = serializers.BooleanField(read_only=True)
    page_slug = serializers.CharField(source='page.slug', read_only=True, default=None)
    page_title = serializers.CharField(source='page.title', read_only=True, default=None)

    class Meta:
        model = NoteNode
        fields = [
            'id', 'title', 'parent', 'page', 'page_slug', 'page_title',
            'is_folder', 'order', 'children',
        ]

    def get_children(self, obj):
        kids = obj.children.all().order_by('order', 'title')
        return NoteNodeTreeSerializer(kids, many=True, context=self.context).data

