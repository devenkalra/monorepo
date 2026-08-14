from django.db.models import Q
from django.contrib.auth.models import User
from rest_framework import serializers
from dj_rest_auth.registration.serializers import RegisterSerializer
from .models import Entity, Person, Note, Location, Movie, Book, Container, Asset, Org, EntityRelation, Tag, UserProfile
from .models import get_user_display_name


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model. displayname is from UserProfile (any characters)."""
    displayname = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    public_username = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'displayname', 'public_username']
        read_only_fields = ['id', 'username']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['displayname'] = get_user_display_name(instance)
        try:
            data['public_username'] = instance.userprofile.public_username or ''
        except UserProfile.DoesNotExist:
            data['public_username'] = ''
        return data

    def update(self, instance, validated_data):
        displayname = validated_data.pop('displayname', None)
        public_username = validated_data.pop('public_username', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        profile, _ = UserProfile.objects.get_or_create(user=instance, defaults={'displayname': displayname or ''})
        if displayname is not None:
            profile.displayname = (displayname or '').strip() or None
        if public_username is not None:
            from gallery.utils import validate_public_username
            cleaned = (public_username or '').strip()
            if cleaned:
                try:
                    cleaned = validate_public_username(cleaned)
                except ValueError as exc:
                    raise serializers.ValidationError({'public_username': str(exc)}) from exc
                if UserProfile.objects.filter(public_username=cleaned).exclude(pk=profile.pk).exists():
                    raise serializers.ValidationError({'public_username': 'That username is taken.'})
                profile.public_username = cleaned
            else:
                profile.public_username = None
        profile.save()
        return instance


class CustomRegisterSerializer(serializers.Serializer):
    """Custom registration serializer that doesn't require username"""
    username = serializers.CharField(required=False, allow_blank=True, write_only=True)
    email = serializers.EmailField(required=True)
    password1 = serializers.CharField(write_only=True, required=True)
    password2 = serializers.CharField(write_only=True, required=True)
    
    def validate_email(self, email):
        """Validate email is not already registered"""
        from allauth.account.adapter import get_adapter
        from allauth.account.models import EmailAddress
        
        email = get_adapter().clean_email(email)
        if email and EmailAddress.objects.is_verified(email):
            raise serializers.ValidationError('A user is already registered with this e-mail address.')
        return email
    
    def validate_password1(self, password):
        """Validate password meets requirements"""
        from allauth.account.adapter import get_adapter
        return get_adapter().clean_password(password)
    
    def validate(self, data):
        """Validate passwords match and set username to email if not provided"""
        if data['password1'] != data['password2']:
            raise serializers.ValidationError("The two password fields didn't match.")
        
        # If username is not provided or empty, use email as username
        if not data.get('username'):
            data['username'] = data['email']
        
        return data
    
    def get_cleaned_data(self):
        """Return cleaned data with email as username if not provided"""
        username = self.validated_data.get('username', '') or self.validated_data.get('email', '')
        return {
            'username': username,
            'password1': self.validated_data.get('password1', ''),
            'email': self.validated_data.get('email', ''),
        }
    
    def save(self, request):
        """Create and save the user"""
        from allauth.account.adapter import get_adapter
        from allauth.account.utils import setup_user_email
        
        adapter = get_adapter()
        user = adapter.new_user(request)
        self.cleaned_data = self.get_cleaned_data()
        user = adapter.save_user(request, user, self, commit=False)
        
        # Clean password one more time before saving
        if "password1" in self.cleaned_data:
            try:
                adapter.clean_password(self.cleaned_data['password1'], user=user)
            except Exception as exc:
                raise serializers.ValidationError(str(exc))
        
        user.save()
        self.custom_signup(request, user)
        setup_user_email(request, user, [])
        return user
    
    def custom_signup(self, request, user):
        """Hook for custom signup logic"""
        pass


class BaseEntitySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)
    referenced_files = serializers.JSONField(write_only=True, required=False, default=list)
    active_scoped_files = serializers.JSONField(write_only=True, required=False, default=list)

    class Meta:
        model = Entity
        fields = '__all__'

    def create(self, validated_data):
        referenced_files = validated_data.pop('referenced_files', [])
        active_scoped_files = validated_data.pop('active_scoped_files', [])
        instance = super().create(validated_data)
        self._sync_files(instance, referenced_files, active_scoped_files)
        return instance

    def update(self, instance, validated_data):
        referenced_files = validated_data.pop('referenced_files', [])
        active_scoped_files = validated_data.pop('active_scoped_files', [])
        instance = super().update(instance, validated_data)
        self._sync_files(instance, referenced_files, active_scoped_files)
        return instance

    def _sync_files(self, instance, referenced_files, active_scoped_files):
        from .models import FileReference
        current_paths = {item['path']: item.get('is_encrypted', False) for item in referenced_files if 'path' in item}
        
        existing_refs = FileReference.objects.filter(entity=instance)
        existing_paths = {ref.file_path: ref for ref in existing_refs}
        
        # Delete unused references
        for path, ref in existing_paths.items():
            if path not in current_paths:
                ref.delete()
                
        # Create new references
        for path, is_enc in current_paths.items():
            if path not in existing_paths:
                FileReference.objects.create(
                    entity=instance,
                    file_path=path,
                    is_encrypted=is_enc
                )
                
        # Clean up unused entity-scoped files
        from django.conf import settings
        import os
        entity_dir = os.path.join(settings.MEDIA_ROOT, str(instance.id))
        if os.path.exists(entity_dir) and os.path.isdir(entity_dir):
            try:
                for entry in os.listdir(entity_dir):
                    entry_path = os.path.join(entity_dir, entry)
                    if os.path.isfile(entry_path):
                        if entry not in active_scoped_files:
                            os.remove(entry_path)
                # If directory is empty, remove it
                if not os.listdir(entity_dir):
                    os.rmdir(entity_dir)
            except Exception as e:
                print(f"Error cleaning up scoped files for entity {instance.id}: {e}")

class EntitySerializer(BaseEntitySerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta(BaseEntitySerializer.Meta):
        model = Entity
        fields = '__all__'
        read_only_fields = ['user', 'created_at', 'updated_at']

class PersonSerializer(BaseEntitySerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta(BaseEntitySerializer.Meta):
        model = Person
        fields = [
            'id', 'type', 'display', 'description', 
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'is_encrypted', 'encrypted_data',
            'created_at', 'updated_at', 'user',
            'first_name', 'last_name', 'dob', 'gender', 'emails', 'phones', 'profession',
            'referenced_files', 'active_scoped_files'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class NoteSerializer(BaseEntitySerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta(BaseEntitySerializer.Meta):
        model = Note
        fields = [
            'id', 'type', 'display', 'description', 
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'is_encrypted', 'encrypted_data',
            'created_at', 'updated_at', 'user',
            'date',
            'referenced_files', 'active_scoped_files'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class LocationSerializer(BaseEntitySerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta(BaseEntitySerializer.Meta):
        model = Location
        fields = [
            'id', 'type', 'display', 'description',
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'is_encrypted', 'encrypted_data',
            'created_at', 'updated_at', 'user',
            'address1', 'address2', 'postal_code', 'city', 'state', 'country',
            'referenced_files', 'active_scoped_files'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class MovieSerializer(BaseEntitySerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta(BaseEntitySerializer.Meta):
        model = Movie
        fields = [
            'id', 'type', 'display', 'description',
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'is_encrypted', 'encrypted_data',
            'created_at', 'updated_at', 'user',
            'year', 'language', 'country',
            'referenced_files', 'active_scoped_files'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class BookSerializer(BaseEntitySerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta(BaseEntitySerializer.Meta):
        model = Book
        fields = [
            'id', 'type', 'display', 'description',
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'is_encrypted', 'encrypted_data',
            'created_at', 'updated_at', 'user',
            'year', 'language', 'country', 'summary',
            'referenced_files', 'active_scoped_files'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class ContainerSerializer(BaseEntitySerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta(BaseEntitySerializer.Meta):
        model = Container
        fields = [
            'id', 'type', 'display', 'description',
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'is_encrypted', 'encrypted_data',
            'created_at', 'updated_at', 'user',
            'referenced_files', 'active_scoped_files'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class AssetSerializer(BaseEntitySerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta(BaseEntitySerializer.Meta):
        model = Asset
        fields = [
            'id', 'type', 'display', 'description',
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'is_encrypted', 'encrypted_data',
            'created_at', 'updated_at', 'user',
            'value', 'acquired_on',
            'referenced_files', 'active_scoped_files'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class OrgSerializer(BaseEntitySerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta(BaseEntitySerializer.Meta):
        model = Org
        fields = [
            'id', 'type', 'display', 'description',
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'is_encrypted', 'encrypted_data',
            'created_at', 'updated_at', 'user',
            'name', 'kind',
            'referenced_files', 'active_scoped_files'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']


class PersonWithRelationsSerializer(PersonSerializer):
    relations = serializers.SerializerMethodField()

    class Meta(PersonSerializer.Meta):
        fields = PersonSerializer.Meta.fields + ['relations']

    def get_relations(self, obj):
        # Only return OUTGOING relations (from_entity=obj)
        qs = EntityRelation.objects.filter(from_entity=obj)
        results = []
        for rel in qs:
            results.append({
                'id': rel.id,
                'relation_type': rel.relation_type,
                'target_entity': {
                    'id': rel.to_entity.id,
                    'display': rel.to_entity.display,
                    'type': rel.to_entity.type
                },
                'created_at': rel.created_at
            })
        return results

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['name', 'count']

class EntityRelationSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntityRelation
        fields = ['id', 'from_entity', 'to_entity', 'relation_type', 'created_at']


# Conversation serializers removed - conversations are now Note entities
