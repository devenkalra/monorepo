from django.contrib.auth.models import User
from rest_framework import serializers

from people.models import UserProfile

from .constants import ROLE_CHOICES
from .models import Gallery, GalleryItem, GalleryShare, GalleryShow
from .utils import ensure_public_username, guess_media_type


class GalleryItemSerializer(serializers.ModelSerializer):
    display_url = serializers.CharField(read_only=True)

    class Meta:
        model = GalleryItem
        fields = [
            'id',
            'gallery',
            'sort_order',
            'media_type',
            'url',
            'external_url',
            'thumbnail_url',
            'title',
            'caption',
            'filename',
            'source_photo_key',
            'thumbnail_status',
            'display_url',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at', 'thumbnail_status', 'display_url']

    def validate(self, attrs):
        url = attrs.get('url', getattr(self.instance, 'url', ''))
        external = attrs.get('external_url', getattr(self.instance, 'external_url', ''))
        if not url and not external:
            raise serializers.ValidationError('Provide url or external_url.')
        if 'media_type' not in attrs:
            attrs['media_type'] = guess_media_type(external or url)
        return attrs


class GalleryShareSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = GalleryShare
        fields = [
            'id',
            'gallery',
            'email',
            'role',
            'active',
            'password',
            'created_at',
            'last_accessed_at',
        ]
        read_only_fields = ['id', 'created_at', 'last_accessed_at']

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        if not password:
            raise serializers.ValidationError({'password': 'Required when creating a share.'})
        share = GalleryShare(**validated_data)
        share.set_password(password)
        share.save()
        return share

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class GalleryShowSerializer(serializers.ModelSerializer):
    class Meta:
        model = GalleryShow
        fields = [
            'id',
            'gallery',
            'slug',
            'title',
            'config',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class GalleryListSerializer(serializers.ModelSerializer):
    owner_username = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(read_only=True, required=False)
    public_path = serializers.SerializerMethodField()

    class Meta:
        model = Gallery
        fields = [
            'id',
            'title',
            'slug',
            'description',
            'cover',
            'access_mode',
            'allow_download',
            'source_entity',
            'owner_username',
            'item_count',
            'public_path',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'owner_username', 'public_path']

    def get_owner_username(self, obj):
        return ensure_public_username(obj.owner)

    def get_public_path(self, obj):
        return f'/{ensure_public_username(obj.owner)}/gallery/{obj.slug}'


class GalleryDetailSerializer(GalleryListSerializer):
    items = GalleryItemSerializer(many=True, read_only=True)
    shows = GalleryShowSerializer(many=True, read_only=True)
    shares = GalleryShareSerializer(many=True, read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta(GalleryListSerializer.Meta):
        fields = GalleryListSerializer.Meta.fields + [
            'items',
            'shows',
            'shares',
            'permissions',
        ]

    def get_permissions(self, obj):
        access = self.context.get('access') or {}
        return {
            'can_view': access.get('can_view', False),
            'can_add': access.get('can_add', False),
            'can_edit': access.get('can_edit', False),
            'is_owner': access.get('is_owner', False),
            'role': access.get('role'),
            'allow_download': bool(obj.allow_download and access.get('can_view')),
            'needs_login': access.get('needs_login', False),
            'needs_share_password': access.get('needs_share_password', False),
            'needs_signup': access.get('needs_signup', False),
        }


class GalleryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gallery
        fields = [
            'id',
            'title',
            'slug',
            'description',
            'cover',
            'access_mode',
            'allow_download',
            'source_entity',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        # owner is injected by ViewSet.perform_create via serializer.save(owner=...)
        ensure_public_username(self.context['request'].user)
        return Gallery.objects.create(**validated_data)


class PublicGalleryUnlockSerializer(serializers.Serializer):
    password = serializers.CharField()


class ReorderSerializer(serializers.Serializer):
    item_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=True)


class SortSerializer(serializers.Serializer):
    by = serializers.ChoiceField(choices=['title', 'filename', 'created_at', 'media_type'])
    direction = serializers.ChoiceField(choices=['asc', 'desc'], default='asc')
