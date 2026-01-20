import meilisearch
from neo4j import GraphDatabase
from django.conf import settings

# --- Configuration ---
# In production, ensure these are loaded from your settings.py
NEO4J_URI = getattr(settings, 'NEO4J_URI', "bolt://localhost:7687")
NEO4J_AUTH = getattr(settings, 'NEO4J_AUTH', ("neo4j", "password"))
MEILI_URL = getattr(settings, 'MEILI_URL', "http://localhost:7700")
MEILI_KEY = getattr(settings, 'MEILI_KEY', "masterKey123")


class SyncEngine:
    def __init__(self):
        self.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        self.meili_client = meilisearch.Client(MEILI_URL, MEILI_KEY)

        # Ensure Meili indexes exist
        self.meili_client.create_index('files', {'primaryKey': 'id'})
        self.meili_client.create_index('folders', {'primaryKey': 'id'})

        # Configure MeiliSearch attributes
        self.meili_client.index('files').update_filterable_attributes(['mime_type', 'folder_id', 'volume'])
        self.meili_client.index('files').update_searchable_attributes(['name', 'metadata'])

    def close(self):
        self.neo4j_driver.close()

    # --- Neo4j Logic ---

    def _neo4j_merge_folder(self, tx, folder_data):
        query = """
        MERGE (f:Folder {uuid: $id})
        SET f.name = $name, f.created_at = $created_at
        """
        tx.run(query, **folder_data)

        if folder_data.get('parent_id'):
            rel_query = """
            MATCH (child:Folder {uuid: $id})
            MATCH (parent:Folder {uuid: $parent_id})
            MERGE (parent)-[:CONTAINS]->(child)
            """
            tx.run(rel_query, id=folder_data['id'], parent_id=folder_data['parent_id'])

    def _neo4j_merge_file(self, tx, file_data):
        query = """
        MERGE (f:File {uuid: $id})
        SET f.name = $name, 
            f.size = $size, 
            f.mime_type = $mime_type
        """
        tx.run(query, **file_data)

        if file_data.get('folder_id'):
            rel_query = """
            MATCH (file:File {uuid: $id})
            MATCH (folder:Folder {uuid: $folder_id})
            MERGE (folder)-[:CONTAINS]->(file)
            """
            tx.run(rel_query, id=file_data['id'], folder_id=file_data['folder_id'])

    def sync_folder_graph(self, folder_instance):
        data = {
            'id': str(folder_instance.id),
            'name': folder_instance.name,
            'created_at': str(folder_instance.created_at),
            'parent_id': str(folder_instance.parent.id) if folder_instance.parent else None
        }
        with self.neo4j_driver.session() as session:
            session.execute_write(self._neo4j_merge_folder, data)

    def sync_file_graph(self, file_instance):
        data = {
            'id': str(file_instance.id),
            'name': file_instance.name,
            'size': file_instance.size_bytes,
            'mime_type': file_instance.mime_type,
            'folder_id': str(file_instance.folder.id) if file_instance.folder else None
        }
        with self.neo4j_driver.session() as session:
            session.execute_write(self._neo4j_merge_file, data)

    def delete_node(self, uuid_str):
        query = "MATCH (n {uuid: $uuid}) DETACH DELETE n"
        with self.neo4j_driver.session() as session:
            session.run(query, uuid=uuid_str)

    # --- MeiliSearch Logic ---

    def sync_folder_search(self, folder_instance):
        doc = {
            'id': str(folder_instance.id),
            'name': folder_instance.name,
            'type': 'folder'
        }
        self.meili_client.index('folders').add_documents([doc])

    def sync_file_search(self, file_instance):
        doc = {
            'id': str(file_instance.id),
            'name': file_instance.name,
            'mime_type': file_instance.mime_type,
            'size': file_instance.size_bytes,
            'volume': file_instance.volume,
            'folder_id': str(file_instance.folder_id),
            'type': 'file',
            **file_instance.metadata
        }
        self.meili_client.index('files').add_documents([doc])

    def delete_document(self, index_name, doc_id):
        self.meili_client.index(index_name).delete_document(doc_id)


# Singleton instance
# TODO Add sync to other dbs
#engine = SyncEngine()
engine=None