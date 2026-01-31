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

class EntityViewSet(viewsets.ReadOnlyModelViewSet):
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

class RecentEntityViewSet(viewsets.ReadOnlyModelViewSet):
    """Return the most recently modified entities.
    Supports an optional `limit` query parameter (default 20).
    """
    serializer_class = EntitySerializer
    permission_classes = [IsAuthenticated]
    # No pagination – we control the number via `limit`
    def get_queryset(self):
        limit = self.request.query_params.get('limit')
        try:
            limit = int(limit) if limit is not None else 20
        except ValueError:
            limit = 20
        return Entity.objects.filter(user=self.request.user).order_by('-updated_at')[:limit]

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
                'entities': EntitySerializer(entities, many=True).data,
                'people': PersonSerializer(people, many=True).data,
                'notes': NoteSerializer(notes, many=True).data,
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
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated], parser_classes=[MultiPartParser, FormParser])
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
            
            # Track import statistics
            stats = {
                'entities_created': 0,
                'entities_updated': 0,
                'people_created': 0,
                'people_updated': 0,
                'notes_created': 0,
                'notes_updated': 0,
                'relations_created': 0,
                'relations_updated': 0,
                'tags_created': 0,
                'errors': []
            }
            
            # Import tags first (they're referenced by other entities)
            for tag_data in data.get('tags', []):
                try:
                    tag, created = Tag.objects.get_or_create(
                        name=tag_data['name'],
                        defaults={'count': 0}  # Will be recalculated
                    )
                    if created:
                        stats['tags_created'] += 1
                except Exception as e:
                    stats['errors'].append(f"Tag import error: {str(e)}")
            
            # Import entities (generic)
            entity_id_map = {}  # Map old IDs to current IDs (for relations)
            for entity_data in data.get('entities', []):
                try:
                    entity_id = entity_data['id']
                    entity_data_clean = {k: v for k, v in entity_data.items() 
                                        if k not in ['id', 'user', 'created_at', 'updated_at']}
                    
                    # Check if entity exists
                    existing_entity = Entity.objects.filter(id=entity_id, user=request.user).first()
                    
                    if existing_entity:
                        # Update existing entity
                        for key, value in entity_data_clean.items():
                            setattr(existing_entity, key, value)
                        existing_entity.save()
                        entity_id_map[entity_id] = existing_entity.id
                        stats['entities_updated'] += 1
                    else:
                        # Create new entity with the same ID
                        entity = Entity.objects.create(id=entity_id, user=request.user, **entity_data_clean)
                        entity_id_map[entity_id] = entity.id
                        stats['entities_created'] += 1
                except Exception as e:
                    stats['errors'].append(f"Entity import error: {str(e)}")
            
            # Import people
            logger.info(f"Importing {len(data.get('people', []))} people")
            for person_data in data.get('people', []):
                try:
                    person_id = person_data['id']
                    person_data_clean = {k: v for k, v in person_data.items() 
                                        if k not in ['id', 'user', 'created_at', 'updated_at']}
                    
                    logger.info(f"Processing person {person_id}: {person_data_clean.get('display', 'N/A')}")
                    
                    # Check if person exists
                    existing_person = Person.objects.filter(id=person_id, user=request.user).first()
                    logger.info(f"Existing person check: {existing_person}")
                    
                    if existing_person:
                        # Update existing person
                        for key, value in person_data_clean.items():
                            setattr(existing_person, key, value)
                        existing_person.save()
                        entity_id_map[person_id] = existing_person.id
                        stats['people_updated'] += 1
                        logger.info(f"Updated person {person_id}")
                    else:
                        # Create new person with the same ID
                        person = Person.objects.create(id=person_id, user=request.user, **person_data_clean)
                        entity_id_map[person_id] = person.id
                        stats['people_created'] += 1
                        logger.info(f"Created person {person_id}")
                except Exception as e:
                    error_msg = f"Person import error: {str(e)}"
                    logger.error(error_msg)
                    stats['errors'].append(error_msg)
            
            # Import notes
            for note_data in data.get('notes', []):
                try:
                    note_id = note_data['id']
                    note_data_clean = {k: v for k, v in note_data.items() 
                                      if k not in ['id', 'user', 'created_at', 'updated_at']}
                    
                    # Check if note exists
                    existing_note = Note.objects.filter(id=note_id, user=request.user).first()
                    
                    if existing_note:
                        # Update existing note
                        for key, value in note_data_clean.items():
                            setattr(existing_note, key, value)
                        existing_note.save()
                        entity_id_map[note_id] = existing_note.id
                        stats['notes_updated'] += 1
                    else:
                        # Create new note with the same ID
                        note = Note.objects.create(id=note_id, user=request.user, **note_data_clean)
                        entity_id_map[note_id] = note.id
                        stats['notes_created'] += 1
                except Exception as e:
                    stats['errors'].append(f"Note import error: {str(e)}")
            
            # Import locations
            for location_data in data.get('locations', []):
                try:
                    location_id = location_data['id']
                    location_data_clean = {k: v for k, v in location_data.items() 
                                          if k not in ['id', 'user', 'created_at', 'updated_at']}
                    
                    # Check if location exists
                    existing_location = Location.objects.filter(id=location_id, user=request.user).first()
                    
                    if existing_location:
                        # Update existing location
                        for key, value in location_data_clean.items():
                            setattr(existing_location, key, value)
                        existing_location.save()
                        entity_id_map[location_id] = existing_location.id
                        stats['locations_updated'] = stats.get('locations_updated', 0) + 1
                    else:
                        # Create new location with the same ID
                        location = Location.objects.create(id=location_id, user=request.user, **location_data_clean)
                        entity_id_map[location_id] = location.id
                        stats['locations_created'] = stats.get('locations_created', 0) + 1
                except Exception as e:
                    stats['errors'].append(f"Location import error: {str(e)}")
            
            # Import movies
            for movie_data in data.get('movies', []):
                try:
                    movie_id = movie_data['id']
                    movie_data_clean = {k: v for k, v in movie_data.items() 
                                       if k not in ['id', 'user', 'created_at', 'updated_at']}
                    
                    # Check if movie exists
                    existing_movie = Movie.objects.filter(id=movie_id, user=request.user).first()
                    
                    if existing_movie:
                        # Update existing movie
                        for key, value in movie_data_clean.items():
                            setattr(existing_movie, key, value)
                        existing_movie.save()
                        entity_id_map[movie_id] = existing_movie.id
                        stats['movies_updated'] = stats.get('movies_updated', 0) + 1
                    else:
                        # Create new movie with the same ID
                        movie = Movie.objects.create(id=movie_id, user=request.user, **movie_data_clean)
                        entity_id_map[movie_id] = movie.id
                        stats['movies_created'] = stats.get('movies_created', 0) + 1
                except Exception as e:
                    stats['errors'].append(f"Movie import error: {str(e)}")
            
            # Import books
            for book_data in data.get('books', []):
                try:
                    book_id = book_data['id']
                    book_data_clean = {k: v for k, v in book_data.items() 
                                      if k not in ['id', 'user', 'created_at', 'updated_at']}
                    
                    # Check if book exists
                    existing_book = Book.objects.filter(id=book_id, user=request.user).first()
                    
                    if existing_book:
                        # Update existing book
                        for key, value in book_data_clean.items():
                            setattr(existing_book, key, value)
                        existing_book.save()
                        entity_id_map[book_id] = existing_book.id
                        stats['books_updated'] = stats.get('books_updated', 0) + 1
                    else:
                        # Create new book with the same ID
                        book = Book.objects.create(id=book_id, user=request.user, **book_data_clean)
                        entity_id_map[book_id] = book.id
                        stats['books_created'] = stats.get('books_created', 0) + 1
                except Exception as e:
                    stats['errors'].append(f"Book import error: {str(e)}")
            
            # Import containers
            for container_data in data.get('containers', []):
                try:
                    container_id = container_data['id']
                    container_data_clean = {k: v for k, v in container_data.items() 
                                           if k not in ['id', 'user', 'created_at', 'updated_at']}
                    
                    existing_container = Container.objects.filter(id=container_id, user=request.user).first()
                    
                    if existing_container:
                        for key, value in container_data_clean.items():
                            setattr(existing_container, key, value)
                        existing_container.save()
                        entity_id_map[container_id] = existing_container.id
                        stats['containers_updated'] = stats.get('containers_updated', 0) + 1
                    else:
                        container = Container.objects.create(id=container_id, user=request.user, **container_data_clean)
                        entity_id_map[container_id] = container.id
                        stats['containers_created'] = stats.get('containers_created', 0) + 1
                except Exception as e:
                    stats['errors'].append(f"Container import error: {str(e)}")
            
            # Import assets
            for asset_data in data.get('assets', []):
                try:
                    asset_id = asset_data['id']
                    asset_data_clean = {k: v for k, v in asset_data.items() 
                                       if k not in ['id', 'user', 'created_at', 'updated_at']}
                    
                    existing_asset = Asset.objects.filter(id=asset_id, user=request.user).first()
                    
                    if existing_asset:
                        for key, value in asset_data_clean.items():
                            setattr(existing_asset, key, value)
                        existing_asset.save()
                        entity_id_map[asset_id] = existing_asset.id
                        stats['assets_updated'] = stats.get('assets_updated', 0) + 1
                    else:
                        asset = Asset.objects.create(id=asset_id, user=request.user, **asset_data_clean)
                        entity_id_map[asset_id] = asset.id
                        stats['assets_created'] = stats.get('assets_created', 0) + 1
                except Exception as e:
                    stats['errors'].append(f"Asset import error: {str(e)}")
            
            # Import orgs
            for org_data in data.get('orgs', []):
                try:
                    org_id = org_data['id']
                    org_data_clean = {k: v for k, v in org_data.items() 
                                     if k not in ['id', 'user', 'created_at', 'updated_at']}
                    
                    existing_org = Org.objects.filter(id=org_id, user=request.user).first()
                    
                    if existing_org:
                        for key, value in org_data_clean.items():
                            setattr(existing_org, key, value)
                        existing_org.save()
                        entity_id_map[org_id] = existing_org.id
                        stats['orgs_updated'] = stats.get('orgs_updated', 0) + 1
                    else:
                        org = Org.objects.create(id=org_id, user=request.user, **org_data_clean)
                        entity_id_map[org_id] = org.id
                        stats['orgs_created'] = stats.get('orgs_created', 0) + 1
                except Exception as e:
                    stats['errors'].append(f"Org import error: {str(e)}")
            
            # Import relations (after all entities exist)
            for relation_data in data.get('relations', []):
                try:
                    relation_id = relation_data.get('id')
                    old_from_id = relation_data.get('from_entity') or relation_data.get('source_entity')
                    old_to_id = relation_data.get('to_entity') or relation_data.get('target_entity')
                    
                    # Map old IDs to current IDs
                    if old_from_id in entity_id_map and old_to_id in entity_id_map:
                        from_entity_id = entity_id_map[old_from_id]
                        to_entity_id = entity_id_map[old_to_id]
                        relation_type = relation_data['relation_type']
                        
                        # Check if relation exists (by ID or by unique constraint)
                        existing_relation = None
                        if relation_id:
                            existing_relation = EntityRelation.objects.filter(id=relation_id).first()
                        
                        if not existing_relation:
                            # Check by unique constraint (from_entity, to_entity, relation_type)
                            existing_relation = EntityRelation.objects.filter(
                                from_entity_id=from_entity_id,
                                to_entity_id=to_entity_id,
                                relation_type=relation_type
                            ).first()
                        
                        if existing_relation:
                            # Relation already exists, just count as updated
                            stats['relations_updated'] += 1
                        else:
                            # Create new relation
                            if relation_id:
                                EntityRelation.objects.create(
                                    id=relation_id,
                                    from_entity_id=from_entity_id,
                                    to_entity_id=to_entity_id,
                                    relation_type=relation_type
                                )
                            else:
                                EntityRelation.objects.create(
                                    from_entity_id=from_entity_id,
                                    to_entity_id=to_entity_id,
                                    relation_type=relation_type
                                )
                            stats['relations_created'] += 1
                except Exception as e:
                    stats['errors'].append(f"Relation import error: {str(e)}")
            
            return Response({
                'success': True,
                'message': 'Import completed',
                'stats': stats
            })
            
        except Exception as e:
            return Response(
                {'error': f'Import failed: {str(e)}'},
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
        """Return tags from user's entities only"""
        # Get all unique tag names from user's entities
        user_entities = Entity.objects.filter(user=self.request.user)
        all_tags = set()
        for entity in user_entities:
            if entity.tags:
                all_tags.update(entity.tags)
        
        # Return Tag objects for these names
        return Tag.objects.filter(name__in=all_tags)

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
        matching_tags = [db_tag for db_tag in all_tags 
                        if db_tag == tag or db_tag.startswith(f'{tag}/')]
        
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
        
        # Perform Meilisearch query with user filter
        results = meili_sync.search(query, filter_str=filter_str)
        
        # If we have relation filtering, intersect the results with relation entity IDs
        if relation_entity_ids is not None:
            # Filter results to only include entities that are in the relation set
            relation_id_set = set(relation_entity_ids)
            results = [r for r in results if r.get('id') in relation_id_set]
        
        return Response(results)


# ConversationViewSet and ConversationTurnViewSet removed - conversations are now Note entities
# Use NoteViewSet with semantic_search action instead
