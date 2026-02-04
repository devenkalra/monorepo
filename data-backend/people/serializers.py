from django.db.models import Q
from django.contrib.auth.models import User
from rest_framework import serializers
from dj_rest_auth.registration.serializers import RegisterSerializer
from .models import Entity, Person, Note, Location, Movie, Book, Container, Asset, Org, EntityRelation, Tag

class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


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


class EntitySerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Entity
        fields = '__all__'
        read_only_fields = ['user', 'created_at', 'updated_at']

class PersonSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Person
        fields = [
            'id', 'type', 'display', 'description', 
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'created_at', 'updated_at', 'user',
            'first_name', 'last_name', 'dob', 'gender', 'emails', 'phones', 'profession'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class NoteSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Note
        fields = [
            'id', 'type', 'display', 'description', 
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'created_at', 'updated_at', 'user',
            'date'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class LocationSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Location
        fields = [
            'id', 'type', 'display', 'description',
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'created_at', 'updated_at', 'user',
            'address1', 'address2', 'postal_code', 'city', 'state', 'country'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class MovieSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Movie
        fields = [
            'id', 'type', 'display', 'description',
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'created_at', 'updated_at', 'user',
            'year', 'language', 'country'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class BookSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Book
        fields = [
            'id', 'type', 'display', 'description',
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'created_at', 'updated_at', 'user',
            'year', 'language', 'country', 'summary'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class ContainerSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Container
        fields = [
            'id', 'type', 'display', 'description',
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'created_at', 'updated_at', 'user'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class AssetSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Asset
        fields = [
            'id', 'type', 'display', 'description',
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'created_at', 'updated_at', 'user',
            'value', 'acquired_on'
        ]
        read_only_fields = ['type', 'created_at', 'updated_at', 'user']

class OrgSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Org
        fields = [
            'id', 'type', 'display', 'description',
            'tags', 'urls', 'photos', 'attachments', 'locations',
            'created_at', 'updated_at', 'user',
            'name', 'kind'
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
