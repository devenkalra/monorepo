from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.core.management import call_command
from .models import Entity, Person, Note, Location, Movie, Book, Container, Asset, Org, EntityRelation, Tag
from .serializers import (
    EntitySerializer, PersonSerializer, NoteSerializer, LocationSerializer, MovieSerializer, BookSerializer,
    ContainerSerializer, AssetSerializer, OrgSerializer, EntityRelationSerializer,
    PersonWithRelationsSerializer, TagSerializer
)
from .utils import save_file_deduplicated
from .permissions import IsOwner, BothEntitiesOwned
from django_filters.rest_framework import DjangoFilterBackend
from io import StringIO
import tempfile
import os
import json

class EntityViewSet(viewsets.ModelViewSet):
    serializer_class = EntitySerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['display', 'description', 'tags']
    filterset_fields = {
        'type': ['exact'],
        'display': ['exact', 'icontains', 'istartswith'],
        'description': ['icontains'],
    }
    
    def get_queryset(self):
        """Return only entities owned by the current user"""
        return Entity.objects.filter(user=self.request.user)
    
    @action(detail=True, methods=['get'])
    def relations(self, request, pk=None):
        """Get all relations (both outgoing and incoming) for an entity"""
        entity = self.get_object()
        
        # Get outgoing relations
        outgoing = EntityRelation.objects.filter(from_entity=entity)
        outgoing_data = []
        for rel in outgoing:
            outgoing_data.append({
                'id': rel.id,
                'direction': 'outgoing',
                'relation_type': rel.relation_type,
                'entity': {
                    'id': rel.to_entity.id,
                    'display': rel.to_entity.display,
                    'type': rel.to_entity.type
                },
                'created_at': rel.created_at
            })
        
        # Get incoming relations
        incoming = EntityRelation.objects.filter(to_entity=entity)
        incoming_data = []
        for rel in incoming:
            incoming_data.append({
                'id': rel.id,
                'direction': 'incoming',
                'relation_type': rel.relation_type,
                'entity': {
                    'id': rel.from_entity.id,
                    'display': rel.from_entity.display,
                    'type': rel.from_entity.type
                },
                'created_at': rel.created_at
            })
        
        return Response({
            'outgoing': outgoing_data,
            'incoming': incoming_data
        })

    def _import_entity_type(self, model_class, entity_data_list, entity_id_map, stats, type_name, request_user, logger):
        """Helper function to import a specific entity type with detailed tracking"""
        import uuid
        created_key = f'{type_name}_created'
        updated_key = f'{type_name}_updated'
        skipped_key = f'{type_name}_skipped'
        
        for entity_data in entity_data_list:
            try:
                original_id = entity_data['id']
                display_name = entity_data.get('display') or entity_data.get('name') or entity_data.get('first_name', 'N/A')
                
                # Clean data - remove fields that shouldn't be set directly
                entity_data_clean = {k: v for k, v in entity_data.items()
                                   if k not in ['id', 'user', 'created_at', 'updated_at']}
                
                # Check if entity with this ID exists for this user
                existing_entity = model_class.objects.filter(id=original_id, user=request_user).first()
                
                if existing_entity:
                    # Check if update is needed (compare data)
                    needs_update = False
                    for key, value in entity_data_clean.items():
                        if getattr(existing_entity, key, None) != value:
                            needs_update = True
                            break
                    logger.info(f"Needs Update")
                    logger.info(f"CUrrent: {existing_entity}")
                    if needs_update:
                        # Update existing entity
                        for key, value in entity_data_clean.items():
                            setattr(existing_entity, key, value)
                        existing_entity.save()
                        entity_id_map[original_id] = existing_entity.id
                        stats[updated_key] += 1
                        logger.info(f"Updated {type_name} '{display_name}' ({original_id})")
                    else:
                        # Entity exists and is identical - skip
                        entity_id_map[original_id] = existing_entity.id
                        stats[skipped_key] += 1
                        logger.info(f"Skipped {type_name} '{display_name}' ({original_id}) - already exists with same data")
                else:
                    # Entity doesn't exist for this user - create new one
                    # Generate new UUID if the original ID is already taken by another user
                    new_id = original_id
                    if model_class.objects.filter(id=original_id).exists():
                        # ID is taken by another user, generate new UUID
                        new_id = uuid.uuid4()
                        logger.info(f"ID {original_id} already exists for another user, using new ID {new_id}")

                    logger.info(f"Needs Update")
                    logger.info(f"Entity Data: {json.dumps(entity_data_clean)}")
                    entity = model_class.objects.create(id=new_id, user=request_user, **entity_data_clean)
                    entity_id_map[original_id] = entity.id  # Map original ID to actual ID (may be different)
                    stats[created_key] += 1
                    logger.info(f"Created {type_name} '{display_name}' ({new_id})")
                    
            except Exception as e:
                error_msg = f"{type_name} '{display_name}' ({original_id}): {str(e)}"
                logger.error(error_msg)
                stats['errors'].append(error_msg)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated],
            parser_classes=[MultiPartParser, FormParser])
    def import_data(self, request):
        """Import entities, notes, and relations from JSON file"""
        from django.db import transaction
        import logging
        logger = logging.getLogger(__name__)

        try:
            if 'file' not in request.FILES:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

            uploaded_file = request.FILES['file']

            # Read and parse JSON
            try:
                import json
                content = uploaded_file.read().decode('utf-8')
                data = json.loads(content)
            except json.JSONDecodeError:
                return Response({'error': 'Invalid JSON file'}, status=status.HTTP_400_BAD_REQUEST)

            # Validate format
            if 'export_version' not in data:
                return Response({'error': 'Invalid export file format'}, status=status.HTTP_400_BAD_REQUEST)

            logger.info(f"Starting import for user {request.user.email}")

            # Track import statistics with detailed breakdown
            stats = {
                # File contents
                'file_summary': {
                    'tags_in_file': len(data.get('tags', [])),
                    'entities_in_file': len(data.get('entities', [])),
                    'people_in_file': len(data.get('people', [])),
                    'notes_in_file': len(data.get('notes', [])),
                    'locations_in_file': len(data.get('locations', [])),
                    'movies_in_file': len(data.get('movies', [])),
                    'books_in_file': len(data.get('books', [])),
                    'containers_in_file': len(data.get('containers', [])),
                    'assets_in_file': len(data.get('assets', [])),
                    'orgs_in_file': len(data.get('orgs', [])),
                    'relations_in_file': len(data.get('relations', [])),
                },
                # Processing results
                'tags_created': 0,
                'tags_skipped': 0,
                'entities_created': 0,
                'entities_updated': 0,
                'entities_skipped': 0,
                'people_created': 0,
                'people_updated': 0,
                'people_skipped': 0,
                'notes_created': 0,
                'notes_updated': 0,
                'notes_skipped': 0,
                'locations_created': 0,
                'locations_updated': 0,
                'locations_skipped': 0,
                'movies_created': 0,
                'movies_updated': 0,
                'movies_skipped': 0,
                'books_created': 0,
                'books_updated': 0,
                'books_skipped': 0,
                'containers_created': 0,
                'containers_updated': 0,
                'containers_skipped': 0,
                'assets_created': 0,
                'assets_updated': 0,
                'assets_skipped': 0,
                'orgs_created': 0,
                'orgs_updated': 0,
                'orgs_skipped': 0,
                'relations_created': 0,
                'relations_updated': 0,
                'relations_skipped': 0,
                'errors': [],
                'warnings': []
            }

            # Import tags first (they're referenced by other entities)
            for tag_data in data.get('tags', []):
                try:
                    tag_name = tag_data['name']
                    tag, created = Tag.objects.get_or_create(
                        name=tag_name,
                        user=request.user,
                        defaults={'count': 0}  # Will be recalculated
                    )
                    if created:
                        stats['tags_created'] += 1
                    else:
                        stats['tags_skipped'] += 1
                except Exception as e:
                    stats['errors'].append(f"Tag '{tag_data.get('name', 'unknown')}': {str(e)}")

            # Map old IDs to current IDs (for relations)
            entity_id_map = {}
            
            # Skip generic 'entities' list if present (legacy exports)
            # We import type-specific entities instead

            # Import people
            logger.info(f"Importing {len(data.get('people', []))} people")
            self._import_entity_type(Person, data.get('people', []), entity_id_map, stats, 'people', request.user, logger)

            # Import notes
            logger.info(f"Importing {len(data.get('notes', []))} notes")
            self._import_entity_type(Note, data.get('notes', []), entity_id_map, stats, 'notes', request.user, logger)

            # Import locations
            logger.info(f"Importing {len(data.get('locations', []))} locations")
            self._import_entity_type(Location, data.get('locations', []), entity_id_map, stats, 'locations', request.user, logger)

            # Import movies
            logger.info(f"Importing {len(data.get('movies', []))} movies")
            self._import_entity_type(Movie, data.get('movies', []), entity_id_map, stats, 'movies', request.user, logger)

            # Import books
            logger.info(f"Importing {len(data.get('books', []))} books")
            self._import_entity_type(Book, data.get('books', []), entity_id_map, stats, 'books', request.user, logger)

            # Import containers
            logger.info(f"Importing {len(data.get('containers', []))} containers")
            self._import_entity_type(Container, data.get('containers', []), entity_id_map, stats, 'containers', request.user, logger)

            # Import assets
            logger.info(f"Importing {len(data.get('assets', []))} assets")
            self._import_entity_type(Asset, data.get('assets', []), entity_id_map, stats, 'assets', request.user, logger)

            # Import orgs
            logger.info(f"Importing {len(data.get('orgs', []))} orgs")
            self._import_entity_type(Org, data.get('orgs', []), entity_id_map, stats, 'orgs', request.user, logger)

            # Import relations (after all entities exist)
            logger.info(f"Importing {len(data.get('relations', []))} relations")
            for relation_data in data.get('relations', []):
                try:
                    relation_id = relation_data.get('id')
                    old_from_id = relation_data.get('from_entity') or relation_data.get('source_entity')
                    old_to_id = relation_data.get('to_entity') or relation_data.get('target_entity')
                    relation_type = relation_data.get('relation_type')

                    # Check if entities exist in the map
                    if old_from_id not in entity_id_map:
                        stats['warnings'].append(f"Relation skipped: from_entity {old_from_id} not found")
                        stats['relations_skipped'] += 1
                        continue
                    
                    if old_to_id not in entity_id_map:
                        stats['warnings'].append(f"Relation skipped: to_entity {old_to_id} not found")
                        stats['relations_skipped'] += 1
                        continue

                    # Map old IDs to current IDs (these may be different if IDs were regenerated)
                    from_entity_id = entity_id_map[old_from_id]
                    to_entity_id = entity_id_map[old_to_id]

                    # Check if relation exists by unique constraint (from_entity, to_entity, relation_type)
                    # Note: We check using the MAPPED IDs, not the original relation ID
                    existing_relation = EntityRelation.objects.filter(
                        from_entity_id=from_entity_id,
                        to_entity_id=to_entity_id,
                        relation_type=relation_type
                    ).first()

                    if existing_relation:
                        # Relation already exists, count as skipped
                        stats['relations_skipped'] += 1
                        logger.info(f"Skipped relation {relation_type} - already exists between mapped entities")
                    else:
                        # Create new relation with mapped entity IDs
                        # Don't preserve the original relation ID - let Django generate a new one
                        EntityRelation.objects.create(
                            from_entity_id=from_entity_id,
                            to_entity_id=to_entity_id,
                            relation_type=relation_type
                        )
                        stats['relations_created'] += 1
                        logger.info(f"Created relation {relation_type} between mapped entities")
                except Exception as e:
                    error_msg = f"Relation {relation_type} ({relation_id}): {str(e)}"
                    logger.error(error_msg)
                    stats['errors'].append(error_msg)

            # Calculate totals
            total_created = sum([
                stats.get('entities_created', 0),
                stats.get('people_created', 0),
                stats.get('notes_created', 0),
                stats.get('locations_created', 0),
                stats.get('movies_created', 0),
                stats.get('books_created', 0),
                stats.get('containers_created', 0),
                stats.get('assets_created', 0),
                stats.get('orgs_created', 0),
            ])
            
            total_updated = sum([
                stats.get('entities_updated', 0),
                stats.get('people_updated', 0),
                stats.get('notes_updated', 0),
                stats.get('locations_updated', 0),
                stats.get('movies_updated', 0),
                stats.get('books_updated', 0),
                stats.get('containers_updated', 0),
                stats.get('assets_updated', 0),
                stats.get('orgs_updated', 0),
            ])
            
            total_skipped = sum([
                stats.get('entities_skipped', 0),
                stats.get('people_skipped', 0),
                stats.get('notes_skipped', 0),
                stats.get('locations_skipped', 0),
                stats.get('movies_skipped', 0),
                stats.get('books_skipped', 0),
                stats.get('containers_skipped', 0),
                stats.get('assets_skipped', 0),
                stats.get('orgs_skipped', 0),
            ])
            
            # Add summary
            stats['summary'] = {
                'total_entities_in_file': sum([
                    stats['file_summary']['entities_in_file'],
                    stats['file_summary']['people_in_file'],
                    stats['file_summary']['notes_in_file'],
                    stats['file_summary']['locations_in_file'],
                    stats['file_summary']['movies_in_file'],
                    stats['file_summary']['books_in_file'],
                    stats['file_summary']['containers_in_file'],
                    stats['file_summary']['assets_in_file'],
                    stats['file_summary']['orgs_in_file'],
                ]),
                'total_created': total_created,
                'total_updated': total_updated,
                'total_skipped': total_skipped,
                'total_errors': len(stats['errors']),
                'total_warnings': len(stats['warnings']),
                'tags_created': stats['tags_created'],
                'tags_skipped': stats['tags_skipped'],
                'relations_created': stats['relations_created'],
                'relations_skipped': stats['relations_skipped'],
            }
            
            logger.info(f"Import completed: {total_created} created, {total_updated} updated, {total_skipped} skipped, {len(stats['errors'])} errors")
            
            return Response({
                'success': True,
                'message': f'Import completed: {total_created} created, {total_updated} updated, {total_skipped} skipped',
                'stats': stats
            })

        except Exception as e:
            return Response(
                {'error': f'Import failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def export(self, request):
        """Export all user's data (entities, notes, relations) as JSON"""
        try:
            from django.http import HttpResponse
            import json
            from datetime import datetime
            
            # Gather all user's data
            entities = Entity.objects.filter(user=request.user)
            people = Person.objects.filter(user=request.user)
            notes = Note.objects.filter(user=request.user)
            locations = Location.objects.filter(user=request.user)
            movies = Movie.objects.filter(user=request.user)
            books = Book.objects.filter(user=request.user)
            containers = Container.objects.filter(user=request.user)
            assets = Asset.objects.filter(user=request.user)
            orgs = Org.objects.filter(user=request.user)
            relations = EntityRelation.objects.filter(
                from_entity__user=request.user,
                to_entity__user=request.user
            )
            tags = Tag.objects.all()  # Tags are global, not user-specific
            
            export_data = {
                'export_version': '1.0',
                'export_date': datetime.now().isoformat(),
                'user': {
                    'username': request.user.username,
                    'email': request.user.email
                },
                # Don't export generic 'entities' - use type-specific lists instead
                'people': PersonSerializer(people, many=True).data,
                'notes': NoteSerializer(notes, many=True).data,
                'locations': LocationSerializer(locations, many=True).data,
                'movies': MovieSerializer(movies, many=True).data,
                'books': BookSerializer(books, many=True).data,
                'containers': ContainerSerializer(containers, many=True).data,
                'assets': AssetSerializer(assets, many=True).data,
                'orgs': OrgSerializer(orgs, many=True).data,
                'relations': EntityRelationSerializer(relations, many=True).data,
                'tags': TagSerializer(tags, many=True).data,
            }
            
            # Create response with JSON file
            response = HttpResponse(
                json.dumps(export_data, indent=2, default=str),
                content_type='application/json'
            )
            filename = f"entity_export_{request.user.username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
            
        except Exception as e:
            return Response(
                {'error': f'Export failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class RecentEntityViewSet(viewsets.ReadOnlyModelViewSet):
    """Return the most recently modified entities.
    Supports an optional `limit` query parameter (default 20).
    """
    serializer_class = EntitySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        limit = self.request.query_params.get('limit')
        try:
            limit = int(limit) if limit is not None else 20
        except ValueError:
            limit = 20
        return Entity.objects.filter(user=self.request.user).order_by('-updated_at')[:limit]
    
    def get_serializer_class(self):
        """Return the appropriate serializer based on entity type"""
        # Map entity types to their serializers
        serializer_map = {
            'Person': PersonSerializer,
            'Note': NoteSerializer,
            'Location': LocationSerializer,
            'Movie': MovieSerializer,
            'Book': BookSerializer,
            'Container': ContainerSerializer,
            'Asset': AssetSerializer,
            'Org': OrgSerializer,
        }
        # For list view, we need to handle mixed types
        return EntitySerializer
    
    def list(self, request, *args, **kwargs):
        """Override list to return type-specific serialized data"""
        queryset = self.get_queryset()
        
        # Serialize each entity with its type-specific serializer
        serialized_data = []
        for entity in queryset:
            # Get the appropriate serializer for this entity type
            serializer_class = {
                'Person': PersonSerializer,
                'Note': NoteSerializer,
                'Location': LocationSerializer,
                'Movie': MovieSerializer,
                'Book': BookSerializer,
                'Container': ContainerSerializer,
                'Asset': AssetSerializer,
                'Org': OrgSerializer,
            }.get(entity.type, EntitySerializer)
            
            # Cast to the specific type if needed
            if entity.type == 'Person':
                entity = Person.objects.get(id=entity.id)
            elif entity.type == 'Note':
                entity = Note.objects.get(id=entity.id)
            elif entity.type == 'Location':
                entity = Location.objects.get(id=entity.id)
            elif entity.type == 'Movie':
                entity = Movie.objects.get(id=entity.id)
            elif entity.type == 'Book':
                entity = Book.objects.get(id=entity.id)
            elif entity.type == 'Container':
                entity = Container.objects.get(id=entity.id)
            elif entity.type == 'Asset':
                entity = Asset.objects.get(id=entity.id)
            elif entity.type == 'Org':
                entity = Org.objects.get(id=entity.id)
            
            serializer = serializer_class(entity)
            serialized_data.append(serializer.data)
        
        return Response(serialized_data)

class PersonViewSet(viewsets.ModelViewSet):
    serializer_class = PersonSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['first_name', 'last_name', 'profession']
    filterset_fields = {
        'first_name': ['exact', 'icontains', 'istartswith'],
        'last_name': ['exact', 'icontains', 'istartswith'],
        'profession': ['exact', 'icontains'],
        'gender': ['exact'],
        'description': ['icontains'], # Inherited from Entity
    }
    
    def get_queryset(self):
        """Return only people owned by the current user"""
        return Person.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.query_params.get('include_relations') == 'true':
            return PersonWithRelationsSerializer
        return super().get_serializer_class()
    
    def perform_create(self, serializer):
        """Auto-assign current user on create"""
        serializer.save(user=self.request.user)

class NoteViewSet(viewsets.ModelViewSet):
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {
        'display': ['exact', 'icontains'],
        'date': ['exact', 'gte', 'lte'],
    }
    
    def get_queryset(self):
        """Return only notes owned by the current user"""
        return Note.objects.filter(user=self.request.user)


    def perform_create(self, serializer):
        """Auto-assign current user on create"""
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated], parser_classes=[MultiPartParser, FormParser])
    def import_file(self, request):
        """Import conversations as Note entities from uploaded JSON file"""
        if 'file' not in request.FILES:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        file_obj = request.FILES['file']
        source = request.POST.get('source', 'unknown')
        
        try:
            import json
            content = file_obj.read().decode('utf-8')
            data = json.loads(content)
            
            stats = {
                'notes_created': 0,
                'errors': []
            }
            
            # Import conversations as notes
            conversations = data if isinstance(data, list) else [data]
            
            for conv in conversations:
                try:
                    # Create note from conversation
                    note = Note.objects.create(
                        user=request.user,
                        display=conv.get('title', 'Imported Conversation'),
                        description=conv.get('mapping', {}) if isinstance(conv.get('mapping'), dict) else str(conv),
                        tags=[source, 'imported'],
                        date=conv.get('create_time') or conv.get('update_time')
                    )
                    stats['notes_created'] += 1
                except Exception as e:
                    stats['errors'].append(str(e))
            
            return Response({
                'success': True,
                'stats': stats
            })
        except Exception as e:
            return Response(
                {'error': f'Import failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class LocationViewSet(viewsets.ModelViewSet):
    serializer_class = LocationSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['address1', 'city', 'state', 'country']
    filterset_fields = {
        'city': ['exact', 'icontains'],
        'state': ['exact', 'icontains'],
        'country': ['exact', 'icontains'],
        'postal_code': ['exact'],
    }
    
    def get_queryset(self):
        """Return only locations owned by the current user"""
        return Location.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """Auto-assign current user on create"""
        serializer.save(user=self.request.user)

class MovieViewSet(viewsets.ModelViewSet):
    serializer_class = MovieSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['display', 'description', 'language', 'country']
    filterset_fields = {
        'year': ['exact', 'gte', 'lte'],
        'language': ['exact', 'icontains'],
        'country': ['exact', 'icontains'],
    }
    
    def get_queryset(self):
        """Return only movies owned by the current user"""
        return Movie.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """Auto-assign current user on create"""
        serializer.save(user=self.request.user)

class BookViewSet(viewsets.ModelViewSet):
    serializer_class = BookSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['display', 'description', 'summary', 'language', 'country']
    filterset_fields = {
        'year': ['exact', 'gte', 'lte'],
        'language': ['exact', 'icontains'],
        'country': ['exact', 'icontains'],
    }
    
    def get_queryset(self):
        """Return only books owned by the current user"""
        return Book.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """Auto-assign current user on create"""
        serializer.save(user=self.request.user)

class ContainerViewSet(viewsets.ModelViewSet):
    serializer_class = ContainerSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['display', 'description']
    
    def get_queryset(self):
        """Return only containers owned by the current user"""
        return Container.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """Auto-assign current user on create"""
        serializer.save(user=self.request.user)

class AssetViewSet(viewsets.ModelViewSet):
    serializer_class = AssetSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['display', 'description']
    filterset_fields = {
        'value': ['exact', 'gte', 'lte'],
    }
    
    def get_queryset(self):
        """Return only assets owned by the current user"""
        return Asset.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """Auto-assign current user on create"""
        serializer.save(user=self.request.user)

class OrgViewSet(viewsets.ModelViewSet):
    serializer_class = OrgSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['name', 'display', 'description']
    filterset_fields = {
        'kind': ['exact'],
    }
    
    def get_queryset(self):
        """Return only orgs owned by the current user"""
        return Org.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """Auto-assign current user on create"""
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated], parser_classes=[MultiPartParser, FormParser])
    def import_file(self, request):
        """Import conversations as Note entities from uploaded JSON file"""
        if 'file' not in request.FILES:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        source = request.data.get('source', 'chatgpt')
        if source not in ['chatgpt', 'gemini', 'claude', 'other']:
            return Response({'error': 'Invalid source'}, status=status.HTTP_400_BAD_REQUEST)
        
        uploaded_file = request.FILES['file']
        
        # Save uploaded file temporarily
        try:
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.json') as tmp_file:
                for chunk in uploaded_file.chunks():
                    tmp_file.write(chunk)
                tmp_path = tmp_file.name
            
            # Call the import_chats command
            out = StringIO()
            call_command(
                'import_chats',
                source=source,
                file=tmp_path,
                user=request.user.username,
                stdout=out,
                stderr=out
            )
            
            # Clean up temp file
            os.unlink(tmp_path)
            
            output = out.getvalue()
            
            # Parse output to get stats
            lines = output.split('\n')
            stats = {
                'success': True,
                'message': 'Import completed successfully',
                'output': output
            }
            
            for line in lines:
                if 'imported' in line.lower() and 'conversation' in line.lower():
                    stats['message'] = line.strip()
            
            return Response(stats, status=status.HTTP_200_OK)
            
        except Exception as e:
            # Clean up temp file on error
            if 'tmp_path' in locals():
                try:
                    os.unlink(tmp_path)
                except:
                    pass
            
            return Response(
                {'error': f'Import failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def semantic_search(self, request):
        """Semantic search across Notes using vector database
        
        Request body:
        {
            "query": "search query",
            "limit": 10,
            "min_score": 0.5,
            "tags": ["Conversation", "ChatGPT"]  // optional
        }
        """
        try:
            from .vector_search_client import get_vector_search_client
            
            query = request.data.get('query')
            if not query:
                return Response({'error': 'Query is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            limit = int(request.data.get('limit', 10))
            min_score = float(request.data.get('min_score', 0.5))
            tags = request.data.get('tags', [])
            
            # Get vector search client
            client = get_vector_search_client()
            
            # Perform search
            search_results = client.search(
                query=query,
                limit=limit,
                min_score=min_score,
                user_id=request.user.id,
                tags=tags
            )
            
            if not search_results.get('success'):
                return Response(
                    {'error': search_results.get('error', 'Search failed')},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Get full Note objects for the results
            note_ids = [result['id'] for result in search_results['results']]
            notes = Note.objects.filter(id__in=note_ids, user=request.user)
            notes_by_id = {str(note.id): note for note in notes}
            
            # Combine search results with Note data
            results = []
            for result in search_results['results']:
                note = notes_by_id.get(result['id'])
                if note:
                    from .serializers import NoteSerializer
                    note_data = NoteSerializer(note).data
                    note_data['similarity'] = result['similarity']
                    note_data['matched_content'] = result['content'][:200] + '...' if len(result['content']) > 200 else result['content']
                    results.append(note_data)
            
            return Response({
                'results': results,
                'count': len(results),
                'query': query
            })
            
        except Exception as e:
            return Response(
                {'error': f'Search failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    


class EntityRelationViewSet(viewsets.ModelViewSet):
    serializer_class = EntityRelationSerializer
    permission_classes = [IsAuthenticated, BothEntitiesOwned]
    
    def get_queryset(self):
        """Return only relations where both entities are owned by the current user"""
        return EntityRelation.objects.filter(
            from_entity__user=self.request.user,
            to_entity__user=self.request.user
        )
    
    def perform_create(self, serializer):
        """Validate both entities belong to user before creating relation"""
        from_entity = serializer.validated_data.get('from_entity')
        to_entity = serializer.validated_data.get('to_entity')
        
        if from_entity.user != self.request.user or to_entity.user != self.request.user:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can only create relations between your own entities")
        
        serializer.save()

class UploadViewSet(viewsets.ViewSet):
    parser_classes = (MultiPartParser, FormParser)

    def create(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            result = save_file_deduplicated(file_obj)
            return Response(result, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TagViewSet(viewsets.ModelViewSet):
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]
    # No filter backends – simple list/retrieve/delete
    lookup_field = 'name'
    lookup_value_regex = '.+'
    
    def get_queryset(self):
        """Return all tags for the current user"""
        return Tag.objects.filter(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        """Delete a tag and remove it from user's entities.
        Hierarchical counters are updated via the existing signals
        (by saving each affected entity after stripping the tag).
        """
        instance = self.get_object()
        tag_name = instance.name
        # Find all user's entities that contain this tag
        for ent in Entity.objects.filter(user=self.request.user):
            tags = ent.tags or []
            if tag_name in tags:
                ent.tags = [t for t in tags if t != tag_name]
                ent.save()
        # Delete the Tag record itself
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class SearchViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def delete_all(self, request):
        """Delete all entities matching the search/filter criteria"""
        query = request.query_params.get('q', '')
        
        # Check for relation-based filtering
        relation_entity_id = request.query_params.get('relation_entity')
        relation_type = request.query_params.get('relation_type')
        
        # Get related entity IDs from Neo4j if relation filter is specified
        relation_entity_ids = None
        if relation_entity_id and relation_type:
            from .sync import neo4j_sync
            relation_entity_ids = neo4j_sync.find_related_entities(relation_entity_id, relation_type)
            
            if not relation_entity_ids:
                return Response({'deleted': 0})
        
        # Build filter string for Meilisearch
        filters = []
        
        # Handle type filter
        type_val = request.query_params.get('type')
        if type_val:
            types = [t.strip() for t in type_val.split(',')]
            if len(types) > 1:
                type_filter = ' OR '.join([f'type = "{t}"' for t in types])
                filters.append(f'({type_filter})')
            else:
                filters.append(f'type = "{types[0]}"')
        
        # Handle tags filter
        tags_val = request.query_params.get('tags')
        if tags_val:
            tags = [t.strip() for t in tags_val.split(',')]
            expanded_tags = []
            for tag in tags:
                expanded_tags.extend(self._expand_hierarchical_tags(tag))
            expanded_tags = list(set(expanded_tags))
            
            if len(expanded_tags) > 1:
                tag_filter = ' OR '.join([f'tags = "{t}"' for t in expanded_tags])
                filters.append(f'({tag_filter})')
            elif len(expanded_tags) == 1:
                filters.append(f'tags = "{expanded_tags[0]}"')
        
        # Handle display filter
        display_val = request.query_params.get('display')
        search_attributes = None
        if display_val and not query:
            query = display_val
            search_attributes = ['display']
        elif display_val and query:
            query = f"{query} {display_val}"
            search_attributes = ['display', 'description', 'tags']
        
        # Add user filter
        user_filter = f'user_id = "{str(self.request.user.id)}"'
        if filters:
            filter_str = f'({" AND ".join(filters)}) AND {user_filter}'
        else:
            filter_str = user_filter

        # Build Django ORM query to delete (more reliable than MeiliSearch for large result sets)
        queryset = Entity.objects.filter(user=self.request.user)
        
        # Apply type filter
        if type_val:
            types = [t.strip() for t in type_val.split(',')]
            queryset = queryset.filter(type__in=types)
        
        # Apply tags filter
        if tags_val:
            tags = [t.strip() for t in tags_val.split(',')]
            expanded_tags = []
            for tag in tags:
                expanded_tags.extend(self._expand_hierarchical_tags(tag))
            expanded_tags = list(set(expanded_tags))
            
            # Filter entities that have any of the expanded tags
            from django.db.models import Q
            tag_query = Q()
            for tag in expanded_tags:
                tag_query |= Q(tags__contains=[tag])
            queryset = queryset.filter(tag_query)
        
        # Apply text search filters (display, description)
        if query or display_val:
            search_text = query if query else display_val
            from django.db.models import Q
            queryset = queryset.filter(
                Q(display__icontains=search_text) |
                Q(description__icontains=search_text)
            )
        
        # Apply relation filter
        if relation_entity_ids is not None:
            queryset = queryset.filter(id__in=relation_entity_ids)
        
        # Delete entities
        try:
            deleted_count = queryset.count()
            queryset.delete()  # Django signals will handle cleanup
            
            return Response({'deleted': deleted_count})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def count(self, request):
        """Return count of entities matching the search/filter criteria"""
        query = request.query_params.get('q', '')
        
        # Check for relation-based filtering
        relation_entity_id = request.query_params.get('relation_entity')
        relation_type = request.query_params.get('relation_type')
        
        # Get related entity IDs from Neo4j if relation filter is specified
        relation_entity_ids = None
        if relation_entity_id and relation_type:
            from .sync import neo4j_sync
            relation_entity_ids = neo4j_sync.find_related_entities(relation_entity_id, relation_type)
            
            if not relation_entity_ids:
                return Response({'count': 0})
        
        # Build filter string for Meilisearch
        filters = []
        
        # Handle type filter
        type_val = request.query_params.get('type')
        if type_val:
            types = [t.strip() for t in type_val.split(',')]
            if len(types) > 1:
                type_filter = ' OR '.join([f'type = "{t}"' for t in types])
                filters.append(f'({type_filter})')
            else:
                filters.append(f'type = "{types[0]}"')
        
        # Handle tags filter (OR for multiple tags, with hierarchical expansion)
        tags_val = request.query_params.get('tags')
        if tags_val:
            tags = [t.strip() for t in tags_val.split(',')]
            expanded_tags = []
            for tag in tags:
                expanded_tags.extend(self._expand_hierarchical_tags(tag))
            expanded_tags = list(set(expanded_tags))
            
            if len(expanded_tags) > 1:
                tag_filter = ' OR '.join([f'tags = "{t}"' for t in expanded_tags])
                filters.append(f'({tag_filter})')
            elif len(expanded_tags) == 1:
                filters.append(f'tags = "{expanded_tags[0]}"')
        
        # Handle display filter
        display_val = request.query_params.get('display')
        search_attributes = None
        if display_val and not query:
            query = display_val
            search_attributes = ['display']
        elif display_val and query:
            query = f"{query} {display_val}"
            search_attributes = ['display', 'description', 'tags']
        
        # Add user filter
        user_filter = f'user_id = "{str(self.request.user.id)}"'
        if filters:
            filter_str = f'({" AND ".join(filters)}) AND {user_filter}'
        else:
            filter_str = user_filter

        # If we have relation filtering but no other search criteria
        if relation_entity_ids is not None and not query and len(filters) == 0:
            count = Entity.objects.filter(id__in=relation_entity_ids, user=self.request.user).count()
            return Response({'count': count})
        
        # Get count from database (more accurate than MeiliSearch estimatedTotalHits)
        # Build Django ORM query based on filters
        queryset = Entity.objects.filter(user=self.request.user)
        
        # Apply type filter
        if type_val:
            types = [t.strip() for t in type_val.split(',')]
            queryset = queryset.filter(type__in=types)
        
        # Apply tags filter
        if tags_val:
            tags = [t.strip() for t in tags_val.split(',')]
            expanded_tags = []
            for tag in tags:
                expanded_tags.extend(self._expand_hierarchical_tags(tag))
            expanded_tags = list(set(expanded_tags))
            
            # Filter entities that have any of the expanded tags
            from django.db.models import Q
            tag_query = Q()
            for tag in expanded_tags:
                tag_query |= Q(tags__contains=[tag])
            queryset = queryset.filter(tag_query)
        
        # Apply text search filters (display, description)
        if query or display_val:
            search_text = query if query else display_val
            from django.db.models import Q
            queryset = queryset.filter(
                Q(display__icontains=search_text) |
                Q(description__icontains=search_text)
            )
        
        # Apply relation filter
        if relation_entity_ids is not None:
            queryset = queryset.filter(id__in=relation_entity_ids)
        
        count = queryset.count()
        return Response({'count': count})
    
    def _expand_hierarchical_tags(self, tag):
        """
        Expand a parent tag to include all its children.
        For example, "Education" should match "Education", "Education/Caltech", "Education/IIT", etc.
        Returns a list of tag patterns to match.
        """
        # Get all tags from user's entities only
        user_entities = Entity.objects.filter(user=self.request.user)
        all_tags = set()
        for entity in user_entities:
            if entity.tags:
                all_tags.update(entity.tags)
        
        if tag.startswith('Location'):
            location_tags = [t for t in all_tags if t.startswith('Location')]
            print(f"DEBUG: All Location tags for user: {location_tags}")
        
        matching_tags = [db_tag for db_tag in all_tags 
                        if db_tag == tag or db_tag.startswith(f'{tag}/')]
        
        print(f"DEBUG: Expanding '{tag}' -> found {len(matching_tags)} matches: {matching_tags}")
        
        # If no matches found, just return the original tag
        return matching_tags if matching_tags else [tag]
    
    def list(self, request):
        query = request.query_params.get('q', '')
        
        # Check for relation-based filtering
        relation_entity_id = request.query_params.get('relation_entity')
        relation_type = request.query_params.get('relation_type')
        
        # Get related entity IDs from Neo4j if relation filter is specified
        relation_entity_ids = None
        if relation_entity_id and relation_type:
            from .sync import neo4j_sync
            relation_entity_ids = neo4j_sync.find_related_entities(relation_entity_id, relation_type)
            
            if not relation_entity_ids:
                # No entities match the relation, return empty
                return Response([])
        
        # Build filter string for Meilisearch
        # Supported filters: type, tags, first_name, last_name, gender
        filters = []
        
        # Handle type filter (OR for multiple types)
        type_val = request.query_params.get('type')
        if type_val:
            types = [t.strip() for t in type_val.split(',')]
            if len(types) > 1:
                type_filter = ' OR '.join([f'type = "{t}"' for t in types])
                filters.append(f'({type_filter})')
            else:
                filters.append(f'type = "{types[0]}"')
        
        # Handle tags filter (OR for multiple tags, with hierarchical expansion)
        tags_val = request.query_params.get('tags')
        if tags_val:
            tags = [t.strip() for t in tags_val.split(',')]
            # Expand each tag to include children
            expanded_tags = []
            for tag in tags:
                expanded_tags.extend(self._expand_hierarchical_tags(tag))
            
            # Remove duplicates
            expanded_tags = list(set(expanded_tags))
            
            if len(expanded_tags) > 1:
                tag_filter = ' OR '.join([f'tags = "{t}"' for t in expanded_tags])
                filters.append(f'({tag_filter})')
            elif len(expanded_tags) == 1:
                filters.append(f'tags = "{expanded_tags[0]}"')
        
        # Handle display filter separately
        display_val = request.query_params.get('display')
        search_attributes = None
        if display_val and not query:
            # If only display filter is specified, use it as the search query restricted to display field
            query = display_val
            search_attributes = ['display']
        elif display_val and query:
            # If both query and display filter, combine them
            query = f"{query} {display_val}"
            search_attributes = ['display', 'description', 'tags']
        
        # Handle other filters (exact match)
        other_filters = ['first_name', 'last_name', 'gender']
        for key in other_filters:
            val = request.query_params.get(key)
            if val:
                filters.append(f'{key} = "{val}"')
        
        # Add user filter to MeiliSearch
        user_filter = f'user_id = "{str(self.request.user.id)}"'
        if filters:
            filter_str = f'({" AND ".join(filters)}) AND {user_filter}'
        else:
            filter_str = user_filter

        # If we have relation filtering but no other search criteria, just return the related entities
        if relation_entity_ids is not None and not query and len(filters) == 0:
            entities = Entity.objects.filter(id__in=relation_entity_ids, user=self.request.user)
            serialized = EntitySerializer(entities, many=True)
            return Response(serialized.data)
        
        # Import global instance
        from .sync import meili_sync
        
        # If no query but we have filters, use empty query (MeiliSearch will return all matching filters)
        # MeiliSearch requires at least empty string for query
        search_query = query if query else ''
        
        # Perform Meilisearch query with user filter and optional attribute restriction
        results = meili_sync.search(search_query, filter_str=filter_str, attributes_to_search_on=search_attributes)
        
        # If we have relation filtering, intersect the results with relation entity IDs
        if relation_entity_ids is not None:
            # Filter results to only include entities that are in the relation set
            relation_id_set = set(relation_entity_ids)
            results = [r for r in results if r.get('id') in relation_id_set]
        
        return Response(results)


# ConversationViewSet and ConversationTurnViewSet removed - conversations are now Note entities
# Use NoteViewSet with semantic_search action instead
