"""
Simple MeiliSearch helper to replace py_data_helpers.meili.MeiliHelper
"""
import meilisearch
import logging

logger = logging.getLogger(__name__)


class MeiliHelper:
    """Simple wrapper for MeiliSearch operations"""
    
    def __init__(self, url, api_key):
        """Initialize MeiliSearch client"""
        self.client = meilisearch.Client(url, api_key)
        self.index = None
        self.index_name = None
    
    def set_index(self, index_name):
        """Set the current index"""
        self.index_name = index_name
        try:
            self.index = self.client.index(index_name)
        except Exception as e:
            logger.error(f"Failed to set MeiliSearch index {index_name}: {e}")
            # Create index if it doesn't exist
            try:
                self.client.create_index(index_name, {'primaryKey': 'id'})
                self.index = self.client.index(index_name)
            except Exception as create_error:
                logger.error(f"Failed to create MeiliSearch index: {create_error}")
    
    def update_filterable_attributes(self, attributes):
        """Update filterable attributes for the index"""
        if self.index:
            try:
                self.index.update_filterable_attributes(attributes)
            except Exception as e:
                logger.error(f"Failed to update filterable attributes: {e}")
    
    def update_searchable_attributes(self, attributes):
        """Update searchable attributes for the index"""
        if self.index:
            try:
                self.index.update_searchable_attributes(attributes)
            except Exception as e:
                logger.error(f"Failed to update searchable attributes: {e}")
    
    def add_documents(self, documents):
        """Add or update documents in the index"""
        if self.index:
            try:
                return self.index.add_documents(documents)
            except Exception as e:
                logger.error(f"Failed to add documents to MeiliSearch: {e}")
                return None
    
    def update_documents(self, documents):
        """Update documents in the index"""
        if self.index:
            try:
                return self.index.update_documents(documents)
            except Exception as e:
                logger.error(f"Failed to update documents in MeiliSearch: {e}")
                return None
    
    def delete_document(self, document_id):
        """Delete a document from the index"""
        if self.index:
            try:
                return self.index.delete_document(document_id)
            except Exception as e:
                logger.error(f"Failed to delete document from MeiliSearch: {e}")
                return None
    
    def delete_documents(self, document_ids):
        """Delete multiple documents from the index"""
        if self.index:
            try:
                return self.index.delete_documents(document_ids)
            except Exception as e:
                logger.error(f"Failed to delete documents from MeiliSearch: {e}")
                return None
    
    def search(self, query, **kwargs):
        """Search the index"""
        if self.index:
            try:
                return self.index.search(query, kwargs)
            except Exception as e:
                logger.error(f"Failed to search MeiliSearch: {e}")
                return {'hits': [], 'query': query}
        return {'hits': [], 'query': query}
