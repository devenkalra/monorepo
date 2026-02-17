"""
Celery tasks for long-running operations with progress tracking
"""
from celery import shared_task
from django.core.cache import cache
from django.contrib.auth import get_user_model
import logging
import json
import uuid

User = get_user_model()
logger = logging.getLogger(__name__)


def update_task_progress(task_id, current, total, status='processing', message='', errors=None):
    """Update task progress in cache"""
    progress_data = {
        'task_id': task_id,
        'current': current,
        'total': total,
        'percentage': int((current / total * 100)) if total > 0 else 0,
        'status': status,  # 'processing', 'completed', 'failed', 'cancelled'
        'message': message,
        'errors': errors or []
    }
    cache.set(f'task_progress_{task_id}', progress_data, timeout=3600)  # 1 hour
    logger.info(f"Progress update for {task_id}: {current}/{total} ({progress_data['percentage']}%) - {message}")
    return progress_data


def check_task_cancelled(task_id):
    """Check if task has been cancelled"""
    return cache.get(f'task_cancel_{task_id}', False)


@shared_task(bind=True)
def reindex_user_entities(self, user_id):
    """Reindex all entities for a user with progress tracking"""
    from people.models import Entity
    from people.sync import meili_sync
    
    task_id = self.request.id
    logger.info(f"Starting reindex task {task_id} for user {user_id}")
    
    # Write initial progress immediately
    update_task_progress(task_id, 0, 1, 'processing', 'Starting reindex...')
    
    try:
        user = User.objects.get(id=user_id)
        entities = Entity.objects.filter(user=user)
        total = entities.count()
        
        if total == 0:
            update_task_progress(task_id, 0, 0, 'completed', 'No entities to reindex')
            return {'success': True, 'indexed': 0, 'total': 0, 'errors': 0}
        
        indexed = 0
        errors = []
        
        for i, entity in enumerate(entities, 1):
            # Check if cancelled
            if check_task_cancelled(task_id):
                update_task_progress(task_id, indexed, total, 'cancelled', f'Cancelled after {indexed} entities')
                return {'success': False, 'cancelled': True, 'indexed': indexed, 'total': total}
            
            try:
                meili_sync.sync_entity(entity)
                indexed += 1
            except Exception as e:
                error_msg = f"{entity.type} '{entity.display}': {str(e)}"
                errors.append(error_msg)
                logger.error(f"Reindex error: {error_msg}")
            
            # Update progress every 10 entities or on last entity
            if i % 10 == 0 or i == total:
                update_task_progress(
                    task_id, i, total, 'processing',
                    f'Reindexing... {i}/{total} entities processed'
                )
        
        # Mark as completed
        update_task_progress(
            task_id, indexed, total, 'completed',
            f'Reindex complete: {indexed}/{total} entities indexed',
            errors[:10]  # Store first 10 errors
        )
        
        logger.info(f"Reindex task {task_id} completed: {indexed}/{total} indexed, {len(errors)} errors")
        
        return {
            'success': True,
            'indexed': indexed,
            'total': total,
            'errors': len(errors),
            'error_details': errors[:10]
        }
        
    except Exception as e:
        logger.error(f"Reindex task {task_id} failed: {str(e)}")
        update_task_progress(task_id, 0, 0, 'failed', f'Error: {str(e)}')
        raise


def _import_entity_type_helper(model_class, entity_data_list, entity_id_map, stats, type_name, user, task_id=None, processed_ref=None, total_items=0):
    """Helper to import entities of a specific type"""
    created_key = f'{type_name}_created'
    updated_key = f'{type_name}_updated'
    skipped_key = f'{type_name}_skipped'
    
    for i, entity_data in enumerate(entity_data_list, 1):
        # Check for cancellation
        if task_id and check_task_cancelled(task_id):
            update_task_progress(task_id, processed_ref[0] if processed_ref else 0, total_items, 
                               'cancelled', f'Import cancelled during {type_name} - rolling back')
            # Raise to exit transaction, will be caught by outer except
            raise Exception('TASK_CANCELLED_BY_USER')
        
        try:
            original_id = entity_data['id']
            display_name = entity_data.get('display') or entity_data.get('name') or entity_data.get('first_name', 'N/A')
            
            # Clean data
            entity_data_clean = {k: v for k, v in entity_data.items()
                               if k not in ['id', 'user', 'created_at', 'updated_at']}
            
            # Check if entity exists for this user
            existing_entity = model_class.objects.filter(id=original_id, user=user).first()
            
            if existing_entity:
                # Check if update needed
                needs_update = any(getattr(existing_entity, key, None) != value 
                                 for key, value in entity_data_clean.items())
                
                if needs_update:
                    for key, value in entity_data_clean.items():
                        setattr(existing_entity, key, value)
                    existing_entity.save()
                    entity_id_map[original_id] = existing_entity.id
                    stats[updated_key] += 1
                else:
                    entity_id_map[original_id] = existing_entity.id
                    stats[skipped_key] += 1
            else:
                # Create new entity
                new_id = original_id
                if model_class.objects.filter(id=original_id).exists():
                    new_id = uuid.uuid4()
                
                entity = model_class.objects.create(id=new_id, user=user, **entity_data_clean)
                entity_id_map[original_id] = entity.id
                stats[created_key] += 1
                
        except Exception as e:
            error_msg = f"{type_name} '{display_name}': {str(e)}"
            stats['errors'].append(error_msg)
        
        # Update progress frequently
        if task_id and processed_ref is not None:
            processed_ref[0] += 1
            # Update every item for small imports, every 3 items for larger
            update_freq = 1 if len(entity_data_list) < 20 else 3
            if i % update_freq == 0 or i == len(entity_data_list):
                update_task_progress(
                    task_id, 
                    processed_ref[0], 
                    total_items, 
                    'processing',
                    f'Importing {type_name}: {i}/{len(entity_data_list)} ({processed_ref[0]}/{total_items} total)'
                )
                # Small delay to make progress visible
                import time
                time.sleep(0.1)


@shared_task(bind=True)
def import_entities_async(self, user_id, data_json):
    """Import entities asynchronously with progress tracking"""
    from people.models import (Entity, Person, Note, Location, Movie, Book, 
                               Container, Asset, Org, EntityRelation, Tag)
    from django.db import transaction
    
    task_id = self.request.id
    logger.info(f"Starting import task {task_id} for user {user_id}")
    
    # Write initial progress immediately
    update_task_progress(task_id, 0, 1, 'processing', 'Starting import...')
    
    # Small delay to ensure frontend can see initial progress
    import time
    time.sleep(0.5)
    
    # Count entities before import for verification
    initial_entity_count = Entity.objects.filter(user_id=user_id).count() if 'Entity' in dir() else 0
    logger.info(f"Initial entity count for user {user_id}: {initial_entity_count}")
    
    # Wrap entire import in a transaction so cancellation rolls back everything
    # Disable signals during import to prevent MeiliSearch/Neo4j sync until commit
    from django.db.models.signals import post_save, post_delete, pre_save
    from people import signals as people_signals
    
    try:
        # Disconnect all entity sync signals
        post_save.disconnect(people_signals.sync_entity_save, sender=Entity)
        post_save.disconnect(people_signals.sync_entity_save, sender=Person)
        post_save.disconnect(people_signals.sync_entity_save, sender=Note)
        post_save.disconnect(people_signals.sync_entity_save, sender=Location)
        post_save.disconnect(people_signals.sync_entity_save, sender=Movie)
        post_save.disconnect(people_signals.sync_entity_save, sender=Book)
        post_save.disconnect(people_signals.sync_entity_save, sender=Container)
        post_save.disconnect(people_signals.sync_entity_save, sender=Asset)
        post_save.disconnect(people_signals.sync_entity_save, sender=Org)
        
        with transaction.atomic():
            logger.info(f"Starting transaction for import task {task_id} (signals disabled)")
            user = User.objects.get(id=user_id)
            data = json.loads(data_json)
            
            # Count total items
            total_items = (
                len(data.get('tags', [])) +
                len(data.get('people', [])) +
                len(data.get('notes', [])) +
                len(data.get('locations', [])) +
                len(data.get('movies', [])) +
                len(data.get('books', [])) +
                len(data.get('containers', [])) +
                len(data.get('assets', [])) +
                len(data.get('orgs', [])) +
                len(data.get('relations', []))
            )
            
            if total_items == 0:
                update_task_progress(task_id, 0, 0, 'completed', 'No data to import')
                return {'success': True, 'message': 'No data to import'}
            
            processed = 0
            stats = {
                'tags_created': 0, 'tags_skipped': 0,
                'people_created': 0, 'people_updated': 0, 'people_skipped': 0,
                'notes_created': 0, 'notes_updated': 0, 'notes_skipped': 0,
                'locations_created': 0, 'locations_updated': 0, 'locations_skipped': 0,
                'movies_created': 0, 'movies_updated': 0, 'movies_skipped': 0,
                'books_created': 0, 'books_updated': 0, 'books_skipped': 0,
                'containers_created': 0, 'containers_updated': 0, 'containers_skipped': 0,
                'assets_created': 0, 'assets_updated': 0, 'assets_skipped': 0,
                'orgs_created': 0, 'orgs_updated': 0, 'orgs_skipped': 0,
                'relations_created': 0, 'relations_skipped': 0,
                'errors': [], 'warnings': []
            }
            
            # Import tags
            update_task_progress(task_id, processed, total_items, 'processing', 'Importing tags...')
            for tag_data in data.get('tags', []):
                if check_task_cancelled(task_id):
                    update_task_progress(task_id, processed, total_items, 'cancelled', 'Import cancelled - rolling back')
                    # Raise to exit transaction, will be caught by outer except
                    raise Exception('TASK_CANCELLED_BY_USER')
                
                try:
                    tag, created = Tag.objects.get_or_create(
                        name=tag_data['name'], user=user, defaults={'count': 0}
                    )
                    stats['tags_created' if created else 'tags_skipped'] += 1
                except Exception as e:
                    stats['errors'].append(f"Tag '{tag_data.get('name')}': {str(e)}")
                
                processed += 1
                if processed % 10 == 0:
                    update_task_progress(task_id, processed, total_items, 'processing', 
                                       f'Importing... {processed}/{total_items}')
            
            entity_id_map = {}
            
            # Import entities
            entity_types = [
                (Person, 'people'), (Note, 'notes'), (Location, 'locations'),
                (Movie, 'movies'), (Book, 'books'), (Container, 'containers'),
                (Asset, 'assets'), (Org, 'orgs')
            ]
            
            # Use a mutable reference for processed count so helper can update it
            processed_ref = [processed]
            
            for model_class, type_name in entity_types:
                entity_list = data.get(type_name, [])
                if entity_list:
                    update_task_progress(task_id, processed_ref[0], total_items, 'processing', 
                                       f'Starting {type_name} import...')
                    _import_entity_type_helper(
                        model_class, entity_list, entity_id_map, 
                        stats, type_name, user,
                        task_id=task_id,
                        processed_ref=processed_ref,
                        total_items=total_items
                    )
            
            processed = processed_ref[0]
            
            # Import relations
            update_task_progress(task_id, processed, total_items, 'processing', 'Importing relations...')
            for relation_data in data.get('relations', []):
                if check_task_cancelled(task_id):
                    update_task_progress(task_id, processed, total_items, 'cancelled', 'Import cancelled - rolling back')
                    # Raise to exit transaction, will be caught by outer except
                    raise Exception('TASK_CANCELLED_BY_USER')
                
                try:
                    old_from_id = relation_data.get('from_entity') or relation_data.get('source_entity')
                    old_to_id = relation_data.get('to_entity') or relation_data.get('target_entity')
                    relation_type = relation_data.get('relation_type')
                    
                    if old_from_id not in entity_id_map or old_to_id not in entity_id_map:
                        stats['relations_skipped'] += 1
                        continue
                    
                    from_entity_id = entity_id_map[old_from_id]
                    to_entity_id = entity_id_map[old_to_id]
                    
                    existing = EntityRelation.objects.filter(
                        from_entity_id=from_entity_id,
                        to_entity_id=to_entity_id,
                        relation_type=relation_type
                    ).first()
                    
                    if existing:
                        stats['relations_skipped'] += 1
                    else:
                        EntityRelation.objects.create(
                            from_entity_id=from_entity_id,
                            to_entity_id=to_entity_id,
                            relation_type=relation_type
                        )
                        stats['relations_created'] += 1
                except Exception as e:
                    stats['errors'].append(f"Relation: {str(e)}")
                
                processed += 1
                if processed % 10 == 0:
                    update_task_progress(task_id, processed, total_items, 'processing', 
                                       f'Importing... {processed}/{total_items}')
            
            # Calculate summary
            total_created = sum([stats.get(f'{t}_created', 0) for _, t in entity_types])
            total_updated = sum([stats.get(f'{t}_updated', 0) for _, t in entity_types])
            
            stats['summary'] = {
                'total_created': total_created,
                'total_updated': total_updated,
                'total_relations': stats['relations_created']
            }
        
            update_task_progress(task_id, total_items, total_items, 'completed',
                               f'Import complete: {total_created} created, {total_updated} updated',
                               stats['errors'][:10])
            
            logger.info(f"Transaction committed successfully - now syncing to MeiliSearch/Neo4j")
            
        # Transaction committed successfully - now reconnect signals and sync all entities
        # Reconnect signals
        post_save.connect(people_signals.sync_entity_save, sender=Entity)
        post_save.connect(people_signals.sync_entity_save, sender=Person)
        post_save.connect(people_signals.sync_entity_save, sender=Note)
        post_save.connect(people_signals.sync_entity_save, sender=Location)
        post_save.connect(people_signals.sync_entity_save, sender=Movie)
        post_save.connect(people_signals.sync_entity_save, sender=Book)
        post_save.connect(people_signals.sync_entity_save, sender=Container)
        post_save.connect(people_signals.sync_entity_save, sender=Asset)
        post_save.connect(people_signals.sync_entity_save, sender=Org)
        
        # Sync all imported entities to MeiliSearch/Neo4j
        logger.info(f"Syncing {total_created + total_updated} entities to MeiliSearch/Neo4j")
        from people.sync import meili_sync
        synced = 0
        for entity_id in entity_id_map.values():
            try:
                entity = Entity.objects.get(id=entity_id)
                meili_sync.sync_entity(entity)
                synced += 1
            except Exception as e:
                logger.error(f"Failed to sync entity {entity_id}: {str(e)}")
        
        logger.info(f"Synced {synced} entities to external services")
        
        return {'success': True, 'stats': stats}
        
    except Exception as e:
        error_msg = str(e)
        
        # Reconnect signals in case of any exception
        try:
            post_save.connect(people_signals.sync_entity_save, sender=Entity)
            post_save.connect(people_signals.sync_entity_save, sender=Person)
            post_save.connect(people_signals.sync_entity_save, sender=Note)
            post_save.connect(people_signals.sync_entity_save, sender=Location)
            post_save.connect(people_signals.sync_entity_save, sender=Movie)
            post_save.connect(people_signals.sync_entity_save, sender=Book)
            post_save.connect(people_signals.sync_entity_save, sender=Container)
            post_save.connect(people_signals.sync_entity_save, sender=Asset)
            post_save.connect(people_signals.sync_entity_save, sender=Org)
        except:
            pass  # Signals might already be connected
        
        # Check if this was a cancellation
        if 'TASK_CANCELLED_BY_USER' in error_msg:
            logger.info(f"Import task {task_id} cancelled by user - transaction rolled back")
            logger.info(f"Exception raised, exited atomic block - all DB changes should be rolled back")
            logger.info(f"MeiliSearch/Neo4j were NOT synced because signals were disabled")
            
            # Verify rollback worked
            final_entity_count = Entity.objects.filter(user_id=user_id).count()
            logger.info(f"Final entity count for user {user_id}: {final_entity_count} (initial was {initial_entity_count})")
            
            if final_entity_count != initial_entity_count:
                logger.error(f"ROLLBACK FAILED! Entity count changed from {initial_entity_count} to {final_entity_count}")
            else:
                logger.info(f"Rollback successful - entity count unchanged")
            
            update_task_progress(task_id, 0, total_items if 'total_items' in locals() else 0, 
                               'cancelled', 'Import cancelled - all changes rolled back')
            # Return success=False but don't raise - this allows Celery to complete normally
            # The transaction has already been rolled back by exiting the atomic() block
            return {'success': False, 'cancelled': True, 'message': 'Import cancelled and rolled back'}
        else:
            logger.error(f"Import task {task_id} failed: {error_msg}")
            update_task_progress(task_id, 0, total_items if 'total_items' in locals() else 0, 
                               'failed', f'Error: {error_msg}')
            raise
    finally:
        # Ensure signals are reconnected no matter what
        try:
            post_save.connect(people_signals.sync_entity_save, sender=Entity)
            post_save.connect(people_signals.sync_entity_save, sender=Person)
            post_save.connect(people_signals.sync_entity_save, sender=Note)
            post_save.connect(people_signals.sync_entity_save, sender=Location)
            post_save.connect(people_signals.sync_entity_save, sender=Movie)
            post_save.connect(people_signals.sync_entity_save, sender=Book)
            post_save.connect(people_signals.sync_entity_save, sender=Container)
            post_save.connect(people_signals.sync_entity_save, sender=Asset)
            post_save.connect(people_signals.sync_entity_save, sender=Org)
        except:
            pass


@shared_task(bind=True)
def export_entities_async(self, user_id):
    """Export entities asynchronously with progress tracking"""
    from people.models import (Entity, Person, Note, Location, Movie, Book, 
                               Container, Asset, Org, EntityRelation, Tag)
    from people.serializers import (
        PersonSerializer, NoteSerializer, LocationSerializer, MovieSerializer,
        BookSerializer, ContainerSerializer, AssetSerializer, OrgSerializer,
        EntityRelationSerializer, TagSerializer
    )
    from datetime import datetime
    
    task_id = self.request.id
    logger.info(f"Starting export task {task_id} for user {user_id}")
    
    # Write initial progress immediately
    update_task_progress(task_id, 0, 1, 'processing', 'Starting export...')
    
    try:
        user = User.objects.get(id=user_id)
        
        # Count entities
        total = Entity.objects.filter(user=user).count()
        
        update_task_progress(task_id, 0, total if total > 0 else 1, 'processing', 'Gathering data...')
        
        # Check for cancellation
        if check_task_cancelled(task_id):
            update_task_progress(task_id, 0, total, 'cancelled', 'Export cancelled')
            return {'success': False, 'cancelled': True}
        
        # Gather all data
        people = Person.objects.filter(user=user)
        notes = Note.objects.filter(user=user)
        locations = Location.objects.filter(user=user)
        movies = Movie.objects.filter(user=user)
        books = Book.objects.filter(user=user)
        containers = Container.objects.filter(user=user)
        assets = Asset.objects.filter(user=user)
        orgs = Org.objects.filter(user=user)
        relations = EntityRelation.objects.filter(
            from_entity__user=user,
            to_entity__user=user
        )
        tags = Tag.objects.filter(user=user)
        
        update_task_progress(task_id, total // 2 if total > 0 else 0, total if total > 0 else 1, 
                           'processing', 'Serializing data...')
        
        # Check for cancellation
        if check_task_cancelled(task_id):
            update_task_progress(task_id, total // 2, total, 'cancelled', 'Export cancelled')
            return {'success': False, 'cancelled': True}
        
        export_data = {
            'export_version': '1.0',
            'export_date': datetime.now().isoformat(),
            'user': {'username': user.username, 'email': user.email},
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
        
        # Store export data in cache temporarily
        export_json = json.dumps(export_data, indent=2, default=str)
        cache.set(f'export_data_{task_id}', export_json, timeout=3600)  # 1 hour
        
        update_task_progress(task_id, total if total > 0 else 1, total if total > 0 else 1, 
                           'completed', f'Export complete: {total} entities')
        
        return {'success': True, 'total': total}
        
    except Exception as e:
        logger.error(f"Export task {task_id} failed: {str(e)}")
        update_task_progress(task_id, 0, 0, 'failed', f'Error: {str(e)}')
        raise


@shared_task(bind=True)
def export_selected_entities_async(self, user_id, entity_ids, max_hops=1):
    """
    Export selected entities plus their relation network up to max_hops.
    max_hops=1: selected + direct relations (avoids full graph when connected).
    """
    from people.models import (Entity, Person, Note, Location, Movie, Book,
                               Container, Asset, Org, EntityRelation, Tag)
    from people.serializers import (
        PersonSerializer, NoteSerializer, LocationSerializer, MovieSerializer,
        BookSerializer, ContainerSerializer, AssetSerializer, OrgSerializer,
        EntityRelationSerializer, TagSerializer
    )
    from django.db.models import Q
    from datetime import datetime

    task_id = self.request.id
    logger.info(f"Starting export-selected task {task_id} for user {user_id}, {len(entity_ids)} entities")

    update_task_progress(task_id, 0, 1, 'processing', 'Building export network...')

    try:
        user = User.objects.get(id=user_id)
        entity_ids = [str(eid) for eid in entity_ids]  # Ensure string UUIDs

        # Validate all selected entities belong to user
        user_entity_ids = set(
            Entity.objects.filter(user=user, id__in=entity_ids).values_list('id', flat=True)
        )
        user_entity_ids = {str(eid) for eid in user_entity_ids}
        invalid = set(entity_ids) - user_entity_ids
        if invalid:
            update_task_progress(task_id, 0, 0, 'failed', f'Invalid entity IDs: {invalid}')
            return {'success': False, 'error': 'Some entities do not belong to you'}

        # Build network: selected + related entities up to max_hops
        network_ids = set(entity_ids)
        for _ in range(max_hops):
            relations = EntityRelation.objects.filter(
                from_entity__user=user,
                to_entity__user=user
            ).filter(
                Q(from_entity_id__in=network_ids) | Q(to_entity_id__in=network_ids)
            )
            prev_size = len(network_ids)
            for rel in relations:
                network_ids.add(str(rel.from_entity_id))
                network_ids.add(str(rel.to_entity_id))
            if len(network_ids) == prev_size:
                break

        network_ids = list(network_ids)
        update_task_progress(task_id, 0, len(network_ids), 'processing', f'Serializing {len(network_ids)} entities...')

        if check_task_cancelled(task_id):
            update_task_progress(task_id, 0, len(network_ids), 'cancelled', 'Export cancelled')
            return {'success': False, 'cancelled': True}

        # Get entities by type (each entity appears in exactly one type-specific list)
        people = Person.objects.filter(id__in=network_ids, user=user)
        notes = Note.objects.filter(id__in=network_ids, user=user)
        locations = Location.objects.filter(id__in=network_ids, user=user)
        movies = Movie.objects.filter(id__in=network_ids, user=user)
        books = Book.objects.filter(id__in=network_ids, user=user)
        containers = Container.objects.filter(id__in=network_ids, user=user)
        assets = Asset.objects.filter(id__in=network_ids, user=user)
        orgs = Org.objects.filter(id__in=network_ids, user=user)

        # Relations: only those where BOTH ends are in network
        relations = EntityRelation.objects.filter(
            from_entity__user=user,
            to_entity__user=user,
            from_entity_id__in=network_ids,
            to_entity_id__in=network_ids
        )

        # Tags: collect tag names from all entities' tags JSON, then fetch Tag objects
        tag_names = set()
        for qs in [people, notes, locations, movies, books, containers, assets, orgs]:
            for obj in qs:
                for t in (obj.tags or []):
                    if isinstance(t, str):
                        tag_names.add(t)
        tags = Tag.objects.filter(user=user, name__in=tag_names)

        export_data = {
            'export_version': '1.0',
            'export_date': datetime.now().isoformat(),
            'export_type': 'selected',
            'user': {'username': user.username, 'email': user.email},
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

        export_json = json.dumps(export_data, indent=2, default=str)
        cache.set(f'export_data_{task_id}', export_json, timeout=3600)

        total = len(network_ids)
        update_task_progress(task_id, total, total, 'completed', f'Export complete: {total} entities')

        return {'success': True, 'total': total}

    except Exception as e:
        logger.error(f"Export-selected task {task_id} failed: {str(e)}")
        update_task_progress(task_id, 0, 0, 'failed', f'Error: {str(e)}')
        raise
