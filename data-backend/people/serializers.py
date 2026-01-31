from django.db.models import Q
from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Entity, Person, Note, Location, Movie, Book, Container, Asset, Org, EntityRelation, Tag

class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


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
