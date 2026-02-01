import logging
import json
from django.conf import settings
from neo4j import GraphDatabase
from .meili_helper import MeiliHelper

logger = logging.getLogger(__name__)

class Neo4jSync:
    def __init__(self):
        self._driver = None
        try:
            self._driver = GraphDatabase.driver(settings.NEO4J_URI, auth=settings.NEO4J_AUTH)
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")

    def close(self):
        if self._driver:
            self._driver.close()

    def sync_entity(self, entity):
        if not self._driver: return
        # Base Entity Props
        params = {
            'id': str(entity.id),
            'display': entity.display,
            'description': entity.description,
            'type': entity.type
        }
        
        # If it's a Person, add person props
        labels = "Entity"
        if entity.type:
            labels += f":{entity.type}" # e.g., :Entity:Person

        if entity.type == 'Person':
            params.update({
                'firstName': entity.first_name,
                'lastName': entity.last_name,
                'profession': entity.profession,
                'gender': entity.gender
            })

        if entity.type == 'Note':
            if entity.date:
                # Handle both datetime objects and string dates
                if hasattr(entity.date, 'isoformat'):
                    params['date'] = entity.date.isoformat()
                else:
                    params['date'] = entity.date
        
        if entity.type == 'Location':
            params.update({
                'address1': entity.address1,
                'address2': entity.address2,
                'postalCode': entity.postal_code,
                'city': entity.city,
                'state': entity.state,
                'country': entity.country
            })
        
        if entity.type == 'Movie':
            params.update({
                'year': entity.year,
                'language': entity.language,
                'country': entity.country
            })
        
        if entity.type == 'Book':
            params.update({
                'year': entity.year,
                'language': entity.language,
                'country': entity.country,
                'summary': entity.summary
            })
        
        if entity.type == 'Asset':
            params.update({
                'value': entity.value,
                'acquiredOn': entity.acquired_on
            })
        
        if entity.type == 'Org':
            params.update({
                'name': entity.name,
                'kind': entity.kind
            })

        query = f"""
        MERGE (e:{labels} {{id: $id}})
        SET e += $params
        """
        try:
            with self._driver.session() as session:
                session.run(query, id=str(entity.id), params=params)
        except Exception as e:
            logger.error(f"Error syncing entity to Neo4j: {e}")

    def delete_entity(self, entity_id):
        if not self._driver: return
        query = "MATCH (e {id: $id}) DETACH DELETE e"
        try:
            with self._driver.session() as session:
                session.run(query, id=str(entity_id))
        except Exception as e:
             logger.error(f"Error deleting entity from Neo4j: {e}")

    def sync_relation(self, from_id, to_id, relation_type):
        if not self._driver: return
        # Using MERGE on nodes ensures they exist even if sync_entity hasn't run yet or failed.
        # We attach the 'Entity' label as a baseline.
        query = f"""
        MERGE (a:Entity {{id: $from_id}})
        MERGE (b:Entity {{id: $to_id}})
        MERGE (a)-[r:{relation_type}]->(b)
        """
        try:
            with self._driver.session() as session:
                session.run(query, from_id=str(from_id), to_id=str(to_id))
        except Exception as e:
            logger.error(f"Error syncing relation to Neo4j: {e}")

    def delete_relation(self, from_id, to_id, relation_type):
        if not self._driver: return
        query = f"""
        MATCH (a {{id: $from_id}})-[r:{relation_type}]->(b {{id: $to_id}})
        DELETE r
        """
        try:
            with self._driver.session() as session:
                session.run(query, from_id=str(from_id), to_id=str(to_id))
        except Exception as e:
            logger.error(f"Error deleting relation from Neo4j: {e}")
    
    def find_related_entities(self, entity_id, relation_type):
        """
        Find all entities related to the given entity with the specified relation type.
        Returns a list of entity IDs that have relation_type to the given entity.
        
        For example: find_related_entities(devendra_id, "IS_CHILD_OF") 
        returns IDs of entities where (entity)-[IS_CHILD_OF]->(devendra)
        """
        if not self._driver: return []
        
        query = f"""
        MATCH (a)-[r:{relation_type}]->(b {{id: $entity_id}})
        RETURN a.id as entity_id
        """
        
        try:
            with self._driver.session() as session:
                result = session.run(query, entity_id=str(entity_id))
                return [record["entity_id"] for record in result]
        except Exception as e:
            logger.error(f"Error querying related entities from Neo4j: {e}")
            return []

class MeiliSync:
    def __init__(self):
        try:
            self.helper = MeiliHelper(settings.MEILI_URL, settings.MEILI_KEY)
            self.index_name = 'entities'
            
            # Create index with explicit primary key if it doesn't exist
            try:
                self.helper.client.get_index(self.index_name)
            except Exception:
                # Index doesn't exist, create it with primary key
                self.helper.client.create_index(self.index_name, {'primaryKey': 'id'})
            
            self.helper.set_index(self.index_name)
            
            # Define filterable attributes
            self.helper.client.index(self.index_name).update_filterable_attributes([
                'type', 'tags', 'gender', 'first_name', 'last_name', 'user_id'
            ])
            
            # Define searchable attributes
            self.helper.client.index(self.index_name).update_searchable_attributes([
                'display', 'description', 'first_name', 'last_name', 'name'
            ])
            
            # Define displayed attributes (what gets returned in search results)
            # By default MeiliSearch returns all fields, but if displayedAttributes was set before,
            # we need to ensure urls, photos, and attachments are included
            self.helper.client.index(self.index_name).update_displayed_attributes([
                'id', 'type', 'display', 'description', 'tags', 'urls', 'photos', 'attachments',
                'locations', 'user_id', 'first_name', 'last_name', 'emails', 'phones',
                'profession', 'gender', 'dob', 'date', 'address1', 'address2', 'postal_code',
                'city', 'state', 'country', 'year', 'language', 'name', 'kind'
            ])
        except Exception as e:
            logger.error(f"Failed to init MeiliSearch: {e}")
            self.helper = None

    def sync_entity(self, entity):
        if not self.helper: return
        
        doc = {
            'id': str(entity.id),
            'type': entity.type,
            'display': entity.display,
            'description': entity.description,
            'tags': entity.tags,
            'urls': entity.urls,
            'photos': entity.photos,
            'attachments': entity.attachments,
            'locations': entity.locations,
            'user_id': str(entity.user.id) if entity.user else None
        }
        
        if entity.type == 'Person' and hasattr(entity, 'first_name'):
            doc.update({
                'first_name': entity.first_name,
                'last_name': entity.last_name,
                'emails': entity.emails,
                'phones': entity.phones,
                'profession': entity.profession,
                'gender': entity.gender
            })

        if entity.type == 'Note' and hasattr(entity, 'date'):
            # Handle both datetime objects and string dates
            date_value = None
            if entity.date:
                if hasattr(entity.date, 'isoformat'):
                    date_value = entity.date.isoformat()
                else:
                    date_value = entity.date
            doc.update({
                'date': date_value
            })
        
        if entity.type == 'Location' and hasattr(entity, 'city'):
            doc.update({
                'address1': entity.address1,
                'address2': entity.address2,
                'postal_code': entity.postal_code,
                'city': entity.city,
                'state': entity.state,
                'country': entity.country
            })
        
        if entity.type == 'Movie' and hasattr(entity, 'year'):
            doc.update({
                'year': entity.year,
                'language': entity.language,
                'country': entity.country
            })
        
        if entity.type == 'Book' and hasattr(entity, 'year'):
            doc.update({
                'year': entity.year,
                'language': entity.language,
                'country': entity.country,
                'summary': entity.summary
            })
        
        if entity.type == 'Asset' and hasattr(entity, 'value'):
            doc.update({
                'value': entity.value,
                'acquired_on': entity.acquired_on
            })
        
        if entity.type == 'Org' and hasattr(entity, 'name'):
            doc.update({
                'name': entity.name,
                'kind': entity.kind
            })
            
        try:
            self.helper.client.index(self.index_name).add_documents([doc])
        except Exception as e:
            logger.error(f"Error syncing to MeiliSearch: {e}")

    def delete_entity(self, entity_id):
        if not self.helper: return
        try:
            self.helper.client.index(self.index_name).delete_document(str(entity_id))
        except Exception as e:
            logger.error(f"Error deleting from MeiliSearch: {e}")

    def search(self, query, filter_str=None):
        if not self.helper: return []
        try:
            # Basic search
            params = {'filter': filter_str} if filter_str else {}
            result = self.helper.client.index(self.index_name).search(query, params)
            return result.get('hits', [])
        except Exception as e:
            logger.error(f"Error searching MeiliSearch: {e}")
            return []

# Global instances
neo4j_sync = Neo4jSync()
meili_sync = MeiliSync()
