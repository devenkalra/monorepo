from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
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
from .llm_text import build_text_block, relation_sentence
from .import_validation import validate_import_payload
from .import_v2_executor import execute_import_v2, ImportV2ExecutionError, normalize_legacy_snapshot_to_v2
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from io import StringIO
from people.sync import meili_sync
import tempfile
import os
import json


def _prune_export_value(value):
    """Recursively remove null/empty values from exported payloads."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    if isinstance(value, list):
        pruned_items = []
        for item in value:
            pruned_item = _prune_export_value(item)
            if pruned_item is not None:
                pruned_items.append(pruned_item)
        return pruned_items or None
    if isinstance(value, dict):
        pruned_dict = {}
        for key, item in value.items():
            pruned_item = _prune_export_value(item)
            if pruned_item is not None:
                pruned_dict[key] = pruned_item
        return pruned_dict or None
    return value


def _sanitize_entity_records(records):
    """Remove internal ownership field and prune null/empty values."""
    cleaned = []
    for record in records or []:
        if isinstance(record, dict):
            record = dict(record)
            record.pop('user', None)
        pruned = _prune_export_value(record)
        if pruned is not None:
            cleaned.append(pruned)
    return cleaned


def _build_entity_export_records(people, notes, locations, movies, books, containers, assets, orgs):
    """Return a unified entity list for export payloads."""
    return (
        _sanitize_entity_records(PersonSerializer(people, many=True).data)
        + _sanitize_entity_records(NoteSerializer(notes, many=True).data)
        + _sanitize_entity_records(LocationSerializer(locations, many=True).data)
        + _sanitize_entity_records(MovieSerializer(movies, many=True).data)
        + _sanitize_entity_records(BookSerializer(books, many=True).data)
        + _sanitize_entity_records(ContainerSerializer(containers, many=True).data)
        + _sanitize_entity_records(AssetSerializer(assets, many=True).data)
        + _sanitize_entity_records(OrgSerializer(orgs, many=True).data)
    )


def _group_entities_for_legacy_import(data):
    """Support both old type-specific arrays and unified entities array."""
    grouped = {
        'people': list(data.get('people', []) or []),
        'notes': list(data.get('notes', []) or []),
        'locations': list(data.get('locations', []) or []),
        'movies': list(data.get('movies', []) or []),
        'books': list(data.get('books', []) or []),
        'containers': list(data.get('containers', []) or []),
        'assets': list(data.get('assets', []) or []),
        'orgs': list(data.get('orgs', []) or []),
    }

    type_to_bucket = {
        'Person': 'people',
        'Note': 'notes',
        'Location': 'locations',
        'Movie': 'movies',
        'Book': 'books',
        'Container': 'containers',
        'Asset': 'assets',
        'Org': 'orgs',
    }

    for entity in data.get('entities', []) or []:
        if not isinstance(entity, dict):
            continue
        bucket = type_to_bucket.get(entity.get('type'))
        if bucket:
            grouped[bucket].append(entity)

    return grouped


def _validate_payload_user_matches_request(payload, request_user):
    """Validate optional payload user metadata against authenticated user."""
    payload_user = payload.get('user')
    if not payload_user or not isinstance(payload_user, dict):
        return True, None

    payload_username = payload_user.get('username')
    if payload_username and payload_username != request_user.username:
        return False, 'Import user.username does not match authenticated user'

    payload_email = payload_user.get('email')
    if payload_email and payload_email != request_user.email:
        return False, 'Import user.email does not match authenticated user'

    return True, None

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

    def retrieve(self, request, *args, **kwargs):
        """Override retrieve to return subclass-specific serialized data"""
        instance = self.get_object()
        serialized = self._serialize_entity(instance=instance, request=request)
        text_parts = build_text_block(entity=serialized, outgoing=[])
        response_data = dict(serialized)
        response_data['entity_sentences'] = text_parts['entity_sentences']
        response_data['entity_text_block'] = "\n".join(text_parts['entity_sentences'])
        return Response(response_data)

    def _serialize_entity(self, instance, request):
        entity_type = instance.type

        type_info = {
            'Person': (Person, PersonSerializer),
            'Note': (Note, NoteSerializer),
            'Location': (Location, LocationSerializer),
            'Movie': (Movie, MovieSerializer),
            'Book': (Book, BookSerializer),
            'Container': (Container, ContainerSerializer),
            'Asset': (Asset, AssetSerializer),
            'Org': (Org, OrgSerializer),
        }.get(entity_type)

        if type_info:
            model_cls, serializer_cls = type_info
            try:
                casted_instance = model_cls.objects.get(id=instance.id)
                serializer = serializer_cls(casted_instance, context={'request': request})
                return serializer.data
            except model_cls.DoesNotExist:
                pass

        serializer = self.get_serializer(instance)
        return serializer.data
    
    @action(detail=True, methods=['get'])
    def relations(self, request, pk=None):
        """Get all relations (both outgoing and incoming) for an entity"""
        entity = self.get_object()
        direction = str(request.query_params.get('direction', 'both')).strip().lower()
        include_outgoing = direction in {'both', 'outgoing'}
        include_incoming = direction in {'both', 'incoming'}

        if not include_outgoing and not include_incoming:
            return Response(
                {
                    'detail': "Invalid direction. Use one of: both, outgoing, incoming.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Get outgoing relations
        outgoing_data = []
        if include_outgoing:
            outgoing = EntityRelation.objects.filter(from_entity=entity)
            for rel in outgoing:
                rel_text = relation_sentence(
                    subject_name=entity.display or str(entity.id),
                    relation_type=rel.relation_type,
                    target_name=rel.to_entity.display or str(rel.to_entity.id),
                )
                outgoing_data.append({
                    'id': rel.id,
                    'direction': 'outgoing',
                    'relation_type': rel.relation_type,
                    'entity': {
                        'id': rel.to_entity.id,
                        'display': rel.to_entity.display,
                        'type': rel.to_entity.type
                    },
                    'created_at': rel.created_at,
                    'text': rel_text,
                })
        
        # Get incoming relations
        incoming_data = []
        if include_incoming:
            incoming = EntityRelation.objects.filter(to_entity=entity)
            for rel in incoming:
                rel_text = relation_sentence(
                    subject_name=rel.from_entity.display or str(rel.from_entity.id),
                    relation_type=rel.relation_type,
                    target_name=entity.display or str(entity.id),
                )
                incoming_data.append({
                    'id': rel.id,
                    'direction': 'incoming',
                    'relation_type': rel.relation_type,
                    'entity': {
                        'id': rel.from_entity.id,
                        'display': rel.from_entity.display,
                        'type': rel.from_entity.type
                    },
                    'created_at': rel.created_at,
                    'text': rel_text,
                })
        
        outgoing_lines = [row['text'] for row in outgoing_data]
        incoming_lines = [row['text'] for row in incoming_data]

        return Response({
            'direction': direction,
            'outgoing': outgoing_data,
            'incoming': incoming_data,
            'outgoing_text_block': "\n".join(outgoing_lines),
            'incoming_text_block': "\n".join(incoming_lines),
            'text_block': "\n".join(outgoing_lines + incoming_lines),
        })

    @action(detail=True, methods=['get'])
    def llm_context(self, request, pk=None):
        """Return only a single text block for LLM context."""
        entity = self.get_object()
        serialized = self._serialize_entity(instance=entity, request=request)

        outgoing_qs = EntityRelation.objects.filter(from_entity=entity)
        outgoing_data = []
        for rel in outgoing_qs:
            outgoing_data.append(
                {
                    'id': rel.id,
                    'direction': 'outgoing',
                    'relation_type': rel.relation_type,
                    'entity': {
                        'id': rel.to_entity.id,
                        'display': rel.to_entity.display,
                        'type': rel.to_entity.type,
                    },
                    'created_at': rel.created_at,
                }
            )

        incoming_qs = EntityRelation.objects.filter(to_entity=entity)
        incoming_data = []
        for rel in incoming_qs:
            incoming_data.append(
                {
                    'id': rel.id,
                    'direction': 'incoming',
                    'relation_type': rel.relation_type,
                    'entity': {
                        'id': rel.from_entity.id,
                        'display': rel.from_entity.display,
                        'type': rel.from_entity.type,
                    },
                    'created_at': rel.created_at,
                }
            )

        text_parts = build_text_block(entity=serialized, outgoing=outgoing_data, incoming=incoming_data)
        return Response({'text_block': text_parts['text_block']})

    def _import_entity_type(self, model_class, entity_data_list, entity_id_map, stats, type_name, request_user, logger, force_create=False):
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
                
                # For snapshot restores based on a unified entities array, always create fresh rows.
                existing_entity = None if force_create else model_class.objects.filter(id=original_id, user=request_user).first()
                
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
                    if force_create or model_class.objects.filter(id=original_id).exists():
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

            # First semantic gate: schema validation.
            is_valid, schema_error = validate_import_payload(data)
            if not is_valid:
                return Response(
                    {'error': f'Import schema validation failed: {schema_error}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user_ok, user_error = _validate_payload_user_matches_request(data, request.user)
            if not user_ok:
                return Response({'error': user_error}, status=status.HTTP_400_BAD_REQUEST)

            legacy_unified_snapshot = bool(data.get('entities')) and not any(
                data.get(key) for key in ['people', 'notes', 'locations', 'movies', 'books', 'containers', 'assets', 'orgs']
            ) and data.get('export_version') == '1.0'

            logger.info(
                "import_data: user=%s import_version=%s export_version=%s unified_snapshot=%s entities=%s people=%s notes=%s relations=%s tags=%s",
                request.user.username,
                data.get('import_version'),
                data.get('export_version'),
                legacy_unified_snapshot,
                len(data.get('entities', []) or []),
                len(data.get('people', []) or []),
                len(data.get('notes', []) or []),
                len(data.get('relations', []) or []),
                len(data.get('tags', []) or []),
            )

            if data.get('import_version') == '2.0' or legacy_unified_snapshot:
                try:
                    with transaction.atomic():
                        import_payload = normalize_legacy_snapshot_to_v2(data)
                        logger.info(
                            "import_data: normalized payload entities=%s relations=%s tags=%s",
                            len(import_payload.get('entities', []) or []),
                            len(import_payload.get('relations', []) or []),
                            len(import_payload.get('tags', []) or []),
                        )
                        stats = execute_import_v2(import_payload, request.user)
                except ImportV2ExecutionError as exc:
                    return Response(
                        {
                            'success': False,
                            'error': str(exc),
                            'stats': exc.stats,
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                entity_ids = list(Entity.objects.filter(user=request.user).values_list('id', flat=True))
                synced = 0
                deleted = 0
                if meili_sync.helper:
                    try:
                        existing_docs = meili_sync.helper.client.index(meili_sync.index_name).search(
                            '',
                            {
                                'filter': f'user_id = "{str(request.user.id)}"',
                                'limit': 1000,
                                'showRankingScore': False,
                            },
                        ).get('hits', [])
                        existing_ids = [doc.get('id') for doc in existing_docs if doc.get('id')]
                        if existing_ids:
                            delete_task = meili_sync.helper.client.index(meili_sync.index_name).delete_documents(existing_ids)
                            if hasattr(delete_task, 'task_uid'):
                                meili_sync.helper.client.index(meili_sync.index_name).wait_for_task(delete_task.task_uid)
                            deleted = len(existing_ids)
                    except Exception as cleanup_exc:
                        logger.error(f"Failed to clear stale Meili documents for user {request.user.id}: {cleanup_exc}")

                for entity_id in entity_ids:
                    try:
                        entity = Entity.objects.get(id=entity_id)
                        meili_sync.sync_entity(entity, wait_for_completion=True)
                        synced += 1
                    except Exception as sync_exc:
                        logger.error(f"Failed to sync entity {entity_id} after v2 import: {sync_exc}")

                return Response(
                    {
                        'success': True,
                        'message': 'Import v2 completed',
                        'stats': stats,
                        'meili_cleared': deleted,
                        'meili_synced': synced,
                        'entities_synced': len(entity_ids),
                    },
                    status=status.HTTP_200_OK
                )

            # Validate format
            if 'export_version' not in data and 'import_version' not in data:
                return Response({'error': 'Invalid export file format'}, status=status.HTTP_400_BAD_REQUEST)

            logger.info(f"Starting import for user {request.user.email}")

            # Track import statistics with detailed breakdown
            grouped_entities = _group_entities_for_legacy_import(data)
            force_create_snapshot = bool(data.get('entities')) and not any(
                data.get(key) for key in ['people', 'notes', 'locations', 'movies', 'books', 'containers', 'assets', 'orgs']
            )
            logger.info(
                "import_data legacy path: user=%s force_create_snapshot=%s entities=%s people=%s notes=%s locations=%s movies=%s books=%s containers=%s assets=%s orgs=%s relations=%s tags=%s",
                request.user.username,
                force_create_snapshot,
                len(data.get('entities', []) or []),
                len(grouped_entities['people']),
                len(grouped_entities['notes']),
                len(grouped_entities['locations']),
                len(grouped_entities['movies']),
                len(grouped_entities['books']),
                len(grouped_entities['containers']),
                len(grouped_entities['assets']),
                len(grouped_entities['orgs']),
                len(data.get('relations', []) or []),
                len(data.get('tags', []) or []),
            )
            stats = {
                # File contents
                'file_summary': {
                    'tags_in_file': len(data.get('tags', [])),
                    'entities_in_file': len(data.get('entities', [])),
                    'people_in_file': len(grouped_entities['people']),
                    'notes_in_file': len(grouped_entities['notes']),
                    'locations_in_file': len(grouped_entities['locations']),
                    'movies_in_file': len(grouped_entities['movies']),
                    'books_in_file': len(grouped_entities['books']),
                    'containers_in_file': len(grouped_entities['containers']),
                    'assets_in_file': len(grouped_entities['assets']),
                    'orgs_in_file': len(grouped_entities['orgs']),
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

            # Import people
            logger.info(f"Importing {len(grouped_entities['people'])} people")
            self._import_entity_type(Person, grouped_entities['people'], entity_id_map, stats, 'people', request.user, logger, force_create=force_create_snapshot)

            # Import notes
            logger.info(f"Importing {len(grouped_entities['notes'])} notes")
            self._import_entity_type(Note, grouped_entities['notes'], entity_id_map, stats, 'notes', request.user, logger, force_create=force_create_snapshot)

            # Import locations
            logger.info(f"Importing {len(grouped_entities['locations'])} locations")
            self._import_entity_type(Location, grouped_entities['locations'], entity_id_map, stats, 'locations', request.user, logger, force_create=force_create_snapshot)

            # Import movies
            logger.info(f"Importing {len(grouped_entities['movies'])} movies")
            self._import_entity_type(Movie, grouped_entities['movies'], entity_id_map, stats, 'movies', request.user, logger, force_create=force_create_snapshot)

            # Import books
            logger.info(f"Importing {len(grouped_entities['books'])} books")
            self._import_entity_type(Book, grouped_entities['books'], entity_id_map, stats, 'books', request.user, logger, force_create=force_create_snapshot)

            # Import containers
            logger.info(f"Importing {len(grouped_entities['containers'])} containers")
            self._import_entity_type(Container, grouped_entities['containers'], entity_id_map, stats, 'containers', request.user, logger, force_create=force_create_snapshot)

            # Import assets
            logger.info(f"Importing {len(grouped_entities['assets'])} assets")
            self._import_entity_type(Asset, grouped_entities['assets'], entity_id_map, stats, 'assets', request.user, logger, force_create=force_create_snapshot)

            # Import orgs
            logger.info(f"Importing {len(grouped_entities['orgs'])} orgs")
            self._import_entity_type(Org, grouped_entities['orgs'], entity_id_map, stats, 'orgs', request.user, logger, force_create=force_create_snapshot)

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
            tags = Tag.objects.filter(user=request.user)
            
            export_data = {
                'export_version': '1.0',
                'export_date': timezone.now().isoformat(),
                'user': _prune_export_value({
                    'username': request.user.username,
                    'email': request.user.email
                }),
            }

            entities_payload = _build_entity_export_records(
                people, notes, locations, movies, books, containers, assets, orgs
            )

            # Export only non-empty collections.
            collection_data = {
                'entities': _prune_export_value(entities_payload),
                'relations': _prune_export_value(EntityRelationSerializer(relations, many=True).data),
                'tags': _prune_export_value(TagSerializer(tags, many=True).data),
            }
            export_data.update({key: value for key, value in collection_data.items() if value})
            
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
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated],
            parser_classes=[MultiPartParser, FormParser], url_path='import-async')
    def import_async(self, request):
        """Start async import of entities from JSON file"""
        from people.tasks import import_entities_async
        import json
        
        try:
            if 'file' not in request.FILES:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
            
            uploaded_file = request.FILES['file']
            
            # Read and validate JSON
            try:
                content = uploaded_file.read().decode('utf-8')
                data = json.loads(content)
            except json.JSONDecodeError:
                return Response({'error': 'Invalid JSON file'}, status=status.HTTP_400_BAD_REQUEST)

            # First semantic gate: schema validation.
            is_valid, schema_error = validate_import_payload(data)
            if not is_valid:
                return Response(
                    {'error': f'Import schema validation failed: {schema_error}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user_ok, user_error = _validate_payload_user_matches_request(data, request.user)
            if not user_ok:
                return Response({'error': user_error}, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate format
            if 'export_version' not in data and 'import_version' not in data:
                return Response({'error': 'Invalid export file format'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Start async task
            task = import_entities_async.delay(request.user.id, content)
            
            return Response({
                'success': True,
                'task_id': task.id,
                'message': 'Import started. Use /api/entities/tasks/{task_id}/progress/ to check progress.'
            })
            
        except Exception as e:
            return Response(
                {'error': f'Import failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated], url_path='export-async')
    def export_async(self, request):
        """Start async export of all user's data"""
        from people.tasks import export_entities_async
        
        # Start async task
        task = export_entities_async.delay(request.user.id)
        
        return Response({
            'success': True,
            'task_id': task.id,
            'message': 'Export started. Use /api/entities/tasks/{task_id}/progress/ to check progress.'
        })

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated], url_path='export-selected-async')
    def export_selected_async(self, request):
        """Start async export of selected entities and their relation network (requires Celery)"""
        from people.tasks import export_selected_entities_async

        entity_ids = request.data.get('entity_ids', [])
        if not entity_ids:
            return Response({'error': 'entity_ids is required and must not be empty'}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(entity_ids, list):
            return Response({'error': 'entity_ids must be a list'}, status=status.HTTP_400_BAD_REQUEST)

        max_hops = request.data.get('max_hops', 1)
        task = export_selected_entities_async.delay(request.user.id, entity_ids, max_hops)

        return Response({
            'success': True,
            'task_id': task.id,
            'message': 'Export started. Use /api/entities/tasks/{task_id}/progress/ to check progress.'
        })

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated], url_path='export-selected',
            parser_classes=[JSONParser])
    def export_selected(self, request):
        """Synchronous export of selected entities and their relation network (no Celery required)"""
        from django.http import HttpResponse
        from django.db.models import Q
        import json

        entity_ids = request.data.get('entity_ids') if request.data else None
        if not entity_ids:
            return Response({'error': 'entity_ids is required and must not be empty'}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(entity_ids, list):
            return Response({'error': 'entity_ids must be a list'}, status=status.HTTP_400_BAD_REQUEST)

        entity_ids = [str(eid) for eid in entity_ids]
        user = request.user

        # max_hops: 0 = only selected, 1 = selected + direct relations. Default 1 to avoid full graph.
        max_hops = request.data.get('max_hops', 1) if request.data else 1

        # Validate all selected entities belong to user
        user_entity_ids = set(
            str(eid) for eid in
            Entity.objects.filter(user=user, id__in=entity_ids).values_list('id', flat=True)
        )
        invalid = set(entity_ids) - user_entity_ids
        if invalid:
            return Response({'error': 'Some entities do not belong to you'}, status=status.HTTP_403_FORBIDDEN)

        # Build network: selected + related entities up to max_hops (avoids full graph when connected)
        network_ids = set(entity_ids)
        for _ in range(max_hops):
            relations_qs = EntityRelation.objects.filter(
                from_entity__user=user,
                to_entity__user=user
            ).filter(
                Q(from_entity_id__in=network_ids) | Q(to_entity_id__in=network_ids)
            )
            prev_size = len(network_ids)
            for rel in relations_qs:
                network_ids.add(str(rel.from_entity_id))
                network_ids.add(str(rel.to_entity_id))
            if len(network_ids) == prev_size:
                break

        network_ids_list = list(network_ids)

        # Get entities by type - filter by network_ids_list only (no other entities)
        people = Person.objects.filter(user=user).filter(id__in=network_ids_list)
        notes = Note.objects.filter(user=user).filter(id__in=network_ids_list)
        locations = Location.objects.filter(user=user).filter(id__in=network_ids_list)
        movies = Movie.objects.filter(user=user).filter(id__in=network_ids_list)
        books = Book.objects.filter(user=user).filter(id__in=network_ids_list)
        containers = Container.objects.filter(user=user).filter(id__in=network_ids_list)
        assets = Asset.objects.filter(user=user).filter(id__in=network_ids_list)
        orgs = Org.objects.filter(user=user).filter(id__in=network_ids_list)

        network_relations = EntityRelation.objects.filter(
            from_entity__user=user,
            to_entity__user=user
        ).filter(
            from_entity_id__in=network_ids_list,
            to_entity_id__in=network_ids_list
        )

        tag_names = set()
        for qs in [people, notes, locations, movies, books, containers, assets, orgs]:
            for obj in qs:
                for t in (obj.tags or []):
                    if isinstance(t, str):
                        tag_names.add(t)
        tags = Tag.objects.filter(user=user, name__in=tag_names)

        from datetime import datetime
        export_data = {
            'export_version': '1.0',
            'export_date': timezone.now().isoformat(),
            'export_type': 'selected',
            'user': _prune_export_value({'username': user.username, 'email': user.email}),
        }

        entities_payload = _build_entity_export_records(
            people, notes, locations, movies, books, containers, assets, orgs
        )

        collection_data = {
            'entities': _prune_export_value(entities_payload),
            'relations': _prune_export_value(EntityRelationSerializer(network_relations, many=True).data),
            'tags': _prune_export_value(TagSerializer(tags, many=True).data),
        }
        export_data.update({key: value for key, value in collection_data.items() if value})

        export_json = json.dumps(export_data, indent=2, default=str)
        response = HttpResponse(export_json, content_type='application/json')
        filename = f"entity_export_selected_{user.username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated], 
            url_path='tasks/(?P<task_id>[^/.]+)/download')
    def download_export(self, request, task_id=None):
        """Download completed export file"""
        from django.http import HttpResponse
        from django.core.cache import cache
        from datetime import datetime
        
        # Get export data from cache
        export_json = cache.get(f'export_data_{task_id}')
        
        if not export_json:
            return Response({'error': 'Export data not found or expired'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        # Create response with JSON file
        response = HttpResponse(export_json, content_type='application/json')
        filename = f"entity_export_{request.user.username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated], url_path='tasks/(?P<task_id>[^/.]+)/progress')
    def task_progress(self, request, task_id=None):
        """Get progress of a running task"""
        from django.core.cache import cache
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Checking progress for task_id: {task_id}")
        
        # First check cache for progress data
        progress = cache.get(f'task_progress_{task_id}')
        
        if progress:
            logger.info(f"Found progress in cache: {progress}")
            return Response(progress)
        
        # If not in cache, check Celery task state
        from celery.result import AsyncResult
        result = AsyncResult(task_id)
        
        logger.info(f"Task state: {result.state}, Info: {result.info}")
        
        if result.state == 'PENDING':
            return Response({
                'error': 'Task not found or not started yet',
                'task_id': task_id,
                'details': 'The task may still be queuing or the task_id is invalid'
            }, status=status.HTTP_404_NOT_FOUND)
        elif result.state == 'SUCCESS':
            # Task completed but progress expired from cache
            return Response({
                'task_id': task_id,
                'status': 'completed',
                'current': 100,
                'total': 100,
                'percentage': 100,
                'message': 'Task completed (progress data expired)'
            })
        elif result.state == 'FAILURE':
            return Response({
                'task_id': task_id,
                'status': 'failed',
                'current': 0,
                'total': 0,
                'percentage': 0,
                'message': f'Task failed: {str(result.info)}'
            })
        else:
            # Task is in some other state (STARTED, RETRY, etc.)
            return Response({
                'task_id': task_id,
                'status': result.state.lower(),
                'current': 0,
                'total': 0,
                'percentage': 0,
                'message': f'Task is {result.state}'
            })
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated], url_path='tasks/(?P<task_id>[^/.]+)/cancel')
    def cancel_task(self, request, task_id=None):
        """Cancel a running task"""
        from django.core.cache import cache
        from celery.result import AsyncResult
        
        # Mark task as cancelled in cache
        cache.set(f'task_cancel_{task_id}', True, timeout=3600)
        
        # Try to revoke the Celery task
        result = AsyncResult(task_id)
        result.revoke(terminate=True)
        
        return Response({
            'success': True,
            'message': 'Task cancellation requested'
        })
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def reindex(self, request):
        """Start async reindex of all user's entities in MeiliSearch"""
        from people.tasks import reindex_user_entities
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Start async task
            task = reindex_user_entities.delay(request.user.id)
            logger.info(f"Started reindex task {task.id} for user {request.user.id}")
            
            return Response({
                'success': True,
                'task_id': task.id,
                'message': 'Reindex started. Use /api/entities/tasks/{task_id}/progress/ to check progress.'
            })
        except Exception as e:
            logger.error(f"Failed to start reindex task: {str(e)}")
            return Response({
                'success': False,
                'error': f'Failed to start reindex: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class RecentEntityViewSet(viewsets.ReadOnlyModelViewSet):
    """Return the most recently modified entities.
    Supports optional `limit`, `page`, `page_size`, and `sort_by` query parameters.
    """
    serializer_class = EntitySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Get sorting parameter
        sort_by = self.request.query_params.get('sort_by', 'updated_at')
        
        # Get pagination parameters
        page = self.request.query_params.get('page')
        page_size = self.request.query_params.get('page_size')
        limit = self.request.query_params.get('limit')
        
        queryset = Entity.objects.filter(user=self.request.user)
        
        # Apply sorting
        if sort_by == 'display':
            queryset = queryset.order_by('display')
        elif sort_by == 'display_desc':
            queryset = queryset.order_by('-display')
        elif sort_by == 'type':
            queryset = queryset.order_by('type', '-updated_at')
        elif sort_by == 'created_at':
            queryset = queryset.order_by('-created_at')
        else:  # default to updated_at
            queryset = queryset.order_by('-updated_at')
        
        # Apply limit or pagination
        if page is not None and page_size is not None:
            # Pagination mode - don't apply limit here, will be handled in list()
            return queryset
        elif limit is not None:
            try:
                limit = int(limit)
            except ValueError:
                limit = 20
            return queryset[:limit]
        else:
            return queryset[:20]
    
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
        """Override list to return type-specific serialized data with pagination"""
        queryset = self.get_queryset()
        
        # Check if pagination is requested
        page = request.query_params.get('page')
        page_size = request.query_params.get('page_size')
        
        if page is not None and page_size is not None:
            try:
                page = int(page)
                page_size = int(page_size)
                page = max(1, page)
                page_size = min(max(1, page_size), 100)
            except ValueError:
                page = 1
                page_size = 20
            
            # Get total count
            total_count = queryset.count()
            
            # Apply pagination
            start = (page - 1) * page_size
            end = start + page_size
            queryset = queryset[start:end]
            
            # Serialize each entity with its type-specific serializer
            serialized_data = []
            for entity in queryset:
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
            
            return Response({
                'results': serialized_data,
                'count': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': (total_count + page_size - 1) // page_size
            })
        else:
            # Legacy mode - return simple array
            serialized_data = []
            for entity in queryset:
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
        import logging
        logger = logging.getLogger(__name__)
        
        if 'file' not in request.FILES:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        file_obj = request.FILES['file']
        source = request.POST.get('source', 'unknown')
        
        logger.info(f"Starting ChatGPT import for user {request.user.email}, source: {source}")
        
        try:
            import json
            content = file_obj.read().decode('utf-8')
            data = json.loads(content)
            
            logger.info(f"Parsed JSON, type: {type(data)}, keys: {data.keys() if isinstance(data, dict) else 'N/A'}")
            
            stats = {
                'notes_created': 0,
                'errors': []
            }
            
            # Import conversations as notes
            conversations = data if isinstance(data, list) else [data]
            logger.info(f"Processing {len(conversations)} conversations")
            
            for i, conv in enumerate(conversations, 1):
                logger.info(f"Processing conversation {i}/{len(conversations)}: {conv.get('title', 'No title')}")
                try:
                    # Extract conversation content - check both direct mapping and raw_source.mapping
                    mapping = conv.get('mapping', {})
                    if not mapping and 'raw_source' in conv:
                        mapping = conv.get('raw_source', {}).get('mapping', {})
                    
                    logger.info(f"Conversation has mapping with {len(mapping) if isinstance(mapping, dict) else 0} nodes")
                    
                    # Build description from conversation turns with TOC and navigation
                    if isinstance(mapping, dict):
                        # Sort nodes by creation time if available, handle None values
                        sorted_nodes = sorted(
                            mapping.items(),
                            key=lambda x: (x[1].get('message', {}).get('create_time') or 0) if x[1].get('message') else 0
                        )
                        
                        # First pass: extract all messages and build TOC
                        messages = []
                        toc_items = []
                        
                        for node_id, node_data in sorted_nodes:
                            message = node_data.get('message')
                            if not message:
                                continue
                            
                            author = message.get('author', {})
                            role = author.get('role', 'unknown') if isinstance(author, dict) else 'unknown'
                            
                            content = message.get('content')
                            if not content:
                                continue
                            
                            # Extract text
                            text = None
                            if isinstance(content, dict):
                                parts = content.get('parts', [])
                                if parts and isinstance(parts, list):
                                    text = '\n'.join(str(p) for p in parts if p)
                            elif isinstance(content, str):
                                text = content
                            
                            if text:
                                messages.append({'role': role, 'text': text})
                                
                                # Add to TOC if user message
                                if role == 'user':
                                    truncated = text[:80] + '...' if len(text) > 80 else text
                                    truncated = truncated.replace('\n', ' ')
                                    toc_items.append({
                                        'index': len(messages) - 1,
                                        'text': truncated
                                    })
                        
                        logger.info(f"Extracted {len(messages)} messages, {len(toc_items)} user prompts")
                        
                        # Build HTML with TOC
                        html_parts = []
                        
                        # Add anchor at top
                        html_parts.append('<div id="top"></div>')
                        
                        # Table of Contents
                        if toc_items:
                            html_parts.append('''
                                <div style="margin-bottom: 2rem; padding: 1rem; background-color: rgba(0,0,0,0.03); border-radius: 0.5rem; border: 1px solid rgba(0,0,0,0.1);">
                                    <div style="display: flex; justify-content: space-between; align-items: center; cursor: pointer;" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'">
                                        <h3 style="margin: 0; font-weight: bold; font-size: 1rem; color: inherit;">📋 Table of Contents ({} prompts)</h3>
                                        <span style="font-size: 0.875rem; opacity: 0.6;">▼ Click to expand</span>
                                    </div>
                                    <div style="display: none; margin-top: 1rem; max-height: 300px; overflow-y: auto;">
                            '''.format(len(toc_items)))
                            
                            for item in toc_items:
                                html_parts.append(
                                    f'<div style="margin-bottom: 0.5rem;">'
                                    f'<a href="#msg-{item["index"]}" style="color: #3b82f6; text-decoration: none; font-size: 0.875rem; display: block; padding: 0.25rem; border-radius: 0.25rem;" '
                                    f'onmouseover="this.style.backgroundColor=\'rgba(59,130,246,0.1)\'" onmouseout="this.style.backgroundColor=\'transparent\'">'
                                    f'→ {item["text"]}'
                                    f'</a></div>'
                                )
                            
                            html_parts.append('</div></div>')
                        
                        # Add messages with navigation
                        import markdown
                        for idx, msg in enumerate(messages):
                            role = msg['role']
                            text = msg['text']
                            
                            role_label = role.upper()
                            role_color = '#3b82f6' if role == 'user' else '#10b981'
                            bg_color = '#f0f9ff' if role == 'user' else '#f0fdf4'
                            
                            # Convert markdown to HTML
                            text_html = markdown.markdown(
                                text,
                                extensions=['fenced_code', 'tables', 'nl2br', 'codehilite']
                            )
                            
                            # Fix anchor links: remove target="_blank" from internal anchor links
                            # Replace <a ... href="#..."> with proper anchor link attributes
                            import re
                            text_html = re.sub(
                                r'<a\s+([^>]*?)href="(#[^"]*)"([^>]*?)>',
                                r'<a href="\2">',
                                text_html
                            )
                            
                            # Navigation buttons with dark mode support
                            nav_html = '<div style="display: flex; gap: 0.5rem; margin-bottom: 0.5rem;">'
                            nav_html += '<a href="#top" style="padding: 0.25rem 0.5rem; background-color: rgba(0,0,0,0.1); border-radius: 0.25rem; text-decoration: none; font-size: 0.75rem; color: inherit; opacity: 0.8;">⬆ Top</a>'
                            
                            # Always show Prev button
                            if idx > 0:
                                nav_html += f'<a href="#msg-{idx-1}" style="padding: 0.25rem 0.5rem; background-color: rgba(0,0,0,0.1); border-radius: 0.25rem; text-decoration: none; font-size: 0.75rem; color: inherit; opacity: 0.8;">← Prev</a>'
                            else:
                                nav_html += '<span style="padding: 0.25rem 0.5rem; background-color: rgba(0,0,0,0.05); border-radius: 0.25rem; font-size: 0.75rem; color: inherit; opacity: 0.3;">← Prev</span>'
                            
                            # Always show Next button
                            if idx < len(messages) - 1:
                                nav_html += f'<a href="#msg-{idx+1}" style="padding: 0.25rem 0.5rem; background-color: rgba(0,0,0,0.1); border-radius: 0.25rem; text-decoration: none; font-size: 0.75rem; color: inherit; opacity: 0.8;">Next →</a>'
                            else:
                                nav_html += '<span style="padding: 0.25rem 0.5rem; background-color: rgba(0,0,0,0.05); border-radius: 0.25rem; font-size: 0.75rem; color: inherit; opacity: 0.3;">Next →</span>'
                            
                            nav_html += '</div>'
                            
                            # Use rgba colors that work in both light and dark modes
                            msg_bg_color = 'rgba(59,130,246,0.08)' if role == 'user' else 'rgba(16,185,129,0.08)'
                            
                            html_parts.append(
                                f'<div id="msg-{idx}" style="margin-bottom: 1.5rem; padding: 1rem; background-color: {msg_bg_color}; border-radius: 0.5rem; border-left: 4px solid {role_color}; scroll-margin-top: 6rem;">'
                                f'{nav_html}'
                                f'<div style="font-weight: bold; color: {role_color}; margin-bottom: 0.5rem; font-size: 0.875rem;">{role_label} (Message {idx+1}/{len(messages)})</div>'
                                f'<div style="line-height: 1.6; color: inherit;">{text_html}</div>'
                                f'</div>'
                            )
                        
                        description = ''.join(html_parts)
                    else:
                        description = f'<pre>{str(conv)[:1000]}</pre>'
                    
                    logger.info(f"Built description with {len(messages) if 'messages' in locals() else 0} messages, total length={len(description)}")
                    
                    # Parse date - ChatGPT exports use Unix timestamps
                    date_value = None
                    create_time = conv.get('create_time') or conv.get('update_time')
                    if create_time:
                        try:
                            from datetime import datetime
                            if isinstance(create_time, (int, float)):
                                # Unix timestamp
                                date_value = datetime.fromtimestamp(create_time)
                            elif isinstance(create_time, str):
                                # ISO format string
                                date_value = datetime.fromisoformat(create_time.replace('Z', '+00:00'))
                        except Exception as e:
                            logger.warning(f"Failed to parse date '{create_time}': {str(e)}")
                    
                    # Create note from conversation
                    # TextField supports unlimited length in PostgreSQL
                    note = Note.objects.create(
                        user=request.user,
                        display=conv.get('title', 'Imported Conversation'),
                        description=description,  # No length limit
                        tags=[source, 'imported'],
                        date=date_value
                    )
                    logger.info(f"Successfully created note {note.id}: {note.display}")
                    stats['notes_created'] += 1
                except Exception as e:
                    error_msg = f"Conversation '{conv.get('title', 'unknown')}': {str(e)}"
                    logger.error(f"Failed to create note: {error_msg}")
                    stats['errors'].append(error_msg)
            
            logger.info(f"Import complete: {stats['notes_created']} notes created, {len(stats['errors'])} errors")
            
            return Response({
                'success': True,
                'stats': stats
            })
        except Exception as e:
            logger.error(f"Import failed with exception: {str(e)}")
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
        
        entity_id = request.data.get('entity_id')
        try:
            if entity_id:
                from .utils import save_file_scoped
                result = save_file_scoped(file_obj, entity_id)
            else:
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

    def perform_create(self, serializer):
        """Auto-assign current user on create"""
        serializer.save(user=self.request.user)

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

        # Handle other filters (exact match) to stay consistent with list endpoint
        other_filters = ['first_name', 'last_name', 'gender']
        for key in other_filters:
            val = request.query_params.get(key)
            if val:
                filters.append(f'{key} = "{val}"')
        
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
        
        # Use same MeiliSearch path as list() for consistency with UI results.
        from .sync import meili_sync
        hybrid_params = {
            'semanticRatio': 0.25,
            'embedder': 'default',
        }
        search_query = query if query else ''
        results = meili_sync.search(
            search_query,
            filter_str=filter_str,
            attributes_to_search_on=search_attributes,
            hybrid=hybrid_params,
            ranking_score_threshold=0.82,
            show_ranking_score=True,
            limit=10000,
        )

        # If we have relation filtering, intersect Meili results with relation IDs.
        if relation_entity_ids is not None:
            relation_id_set = set(relation_entity_ids)
            results = [r for r in results if r.get('id') in relation_id_set]

        return Response({'count': len(results)})
    
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
        
        # Pagination parameters
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
            page = max(1, page)
            page_size = min(max(1, page_size), 100)  # Cap at 100
        except ValueError:
            page = 1
            page_size = 20
        
        # Sort parameter
        sort_by = request.query_params.get('sort_by', 'updated_at')
        
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
                return Response({
                    'results': [],
                    'count': 0,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': 0
                })
        
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

        # If we have relation filtering but no other search criteria, use Django ORM with sorting
        if relation_entity_ids is not None and not query and len(filters) == 0:
            queryset = Entity.objects.filter(id__in=relation_entity_ids, user=self.request.user)
            queryset = self._apply_sorting(queryset, sort_by)
            
            # Apply pagination
            total_count = queryset.count()
            start = (page - 1) * page_size
            end = start + page_size
            entities = queryset[start:end]
            
            serialized = EntitySerializer(entities, many=True)
            return Response({
                'results': serialized.data,
                'count': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': (total_count + page_size - 1) // page_size
            })
        
        # Import global instance
        from .sync import meili_sync
        
        # If no query but we have filters, use empty query (MeiliSearch will return all matching filters)
        # MeiliSearch requires at least empty string for query
        search_query = query if query else ''

        # Match the previously working hybrid semantic search payload.
        hybrid_params = {
            'semanticRatio': 0.25,
            'embedder': 'default',
        }
        
        # Perform Meilisearch query with user filter and optional attribute restriction
        results = meili_sync.search(
            search_query,
            filter_str=filter_str,
            attributes_to_search_on=search_attributes,
            hybrid=hybrid_params,
            ranking_score_threshold=0.82,
            show_ranking_score=True,
            limit=10000,
        )
        
        # If we have relation filtering, intersect the results with relation entity IDs
        if relation_entity_ids is not None:
            # Filter results to only include entities that are in the relation set
            relation_id_set = set(relation_entity_ids)
            results = [r for r in results if r.get('id') in relation_id_set]
        
        # Preserve Meili relevance order for text queries unless caller explicitly requests a sort.
        if not (query and sort_by == 'updated_at'):
            results = self._sort_results(results, sort_by)
        
        # Apply pagination
        total_count = len(results)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_results = results[start:end]
        
        return Response({
            'results': paginated_results,
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size
        })
    
    def _apply_sorting(self, queryset, sort_by):
        """Apply sorting to Django ORM queryset"""
        if sort_by == 'display':
            return queryset.order_by('display')
        elif sort_by == 'display_desc':
            return queryset.order_by('-display')
        elif sort_by == 'type':
            return queryset.order_by('type', '-updated_at')
        elif sort_by == 'created_at':
            return queryset.order_by('-created_at')
        else:  # default to updated_at
            return queryset.order_by('-updated_at')
    
    def _sort_results(self, results, sort_by):
        """Apply sorting to list of result dictionaries"""
        if sort_by == 'display':
            return sorted(results, key=lambda x: (x.get('display') or x.get('label') or '').lower())
        elif sort_by == 'display_desc':
            return sorted(results, key=lambda x: (x.get('display') or x.get('label') or '').lower(), reverse=True)
        elif sort_by == 'type':
            return sorted(results, key=lambda x: x.get('type', ''))
        elif sort_by == 'created_at':
            return sorted(results, key=lambda x: x.get('created_at', ''), reverse=True)
        else:  # default to updated_at
            return sorted(results, key=lambda x: x.get('updated_at', ''), reverse=True)


# ConversationViewSet and ConversationTurnViewSet removed - conversations are now Note entities
# Use NoteViewSet with semantic_search action instead
