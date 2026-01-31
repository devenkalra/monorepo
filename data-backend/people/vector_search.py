"""
Vector Search Service using ChromaDB for semantic search
"""

import os
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


class VectorSearchService:
    """Service for semantic search using ChromaDB"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Import Django settings here to avoid import-time issues
        from django.conf import settings
        
        # Force CPU usage to avoid CUDA issues
        os.environ['CUDA_VISIBLE_DEVICES'] = ''
        
        # Initialize ChromaDB client
        vector_db_path = getattr(settings, 'VECTOR_DB_PATH', settings.BASE_DIR / 'vector_db')
        self.client = chromadb.PersistentClient(
            path=str(vector_db_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="conversations",
            metadata={"description": "Semantic search for chat conversations"}
        )
        
        # Initialize embedding model
        model_name = getattr(settings, 'VECTOR_MODEL', 'all-MiniLM-L6-v2')
        self.model = SentenceTransformer(model_name)
        
        self._initialized = True
    
    def index_turn(self, turn):
        """Index a conversation turn for semantic search
        
        Args:
            turn: ConversationTurn model instance
        """
        try:
            # Generate embedding
            embedding = self.model.encode(turn.content, show_progress_bar=False).tolist()
            
            # Prepare metadata
            metadata = {
                'conversation_id': str(turn.conversation.id),
                'conversation_label': turn.conversation.label,
                'turn_number': turn.turn_number,
                'role': turn.role,
                'source': turn.conversation.source,
                'token_count': turn.token_count
            }
            
            if turn.timestamp:
                metadata['timestamp'] = turn.timestamp.isoformat()
            
            if turn.conversation.started_at:
                metadata['conversation_date'] = turn.conversation.started_at.isoformat()
            
            # Upsert to collection (add or update)
            self.collection.upsert(
                ids=[str(turn.id)],
                embeddings=[embedding],
                documents=[turn.content],
                metadatas=[metadata]
            )
            
            # Update turn with embedding ID
            if not turn.embedding_id:
                turn.embedding_id = str(turn.id)
                turn.save(update_fields=['embedding_id'])
            
            return True
            
        except Exception as e:
            print(f"Error indexing turn {turn.id}: {e}")
            return False
    
    def search(self, query, limit=5, min_score=0.0, source=None, **filters):
        """Semantic search across all conversation turns
        
        Args:
            query: Search query string
            limit: Maximum number of results
            min_score: Minimum similarity score (0-1)
            source: Filter by conversation source ('chatgpt', 'gemini', etc.)
            **filters: Additional metadata filters
            
        Returns:
            Dictionary with search results
        """
        try:
            # Generate query embedding
            query_embedding = self.model.encode(query, show_progress_bar=False).tolist()
            
            # Build where filter
            where = {}
            if source:
                where['source'] = source
            where.update(filters)
            
            # Search
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where=where if where else None
            )
            
            # Filter by min_score if specified
            if min_score > 0.0 and results['distances'] and results['distances'][0]:
                filtered_results = {
                    'ids': [[]],
                    'distances': [[]],
                    'documents': [[]],
                    'metadatas': [[]]
                }
                
                for i, distance in enumerate(results['distances'][0]):
                    similarity = 1 - (distance / 2)  # Convert distance to similarity
                    if similarity >= min_score:
                        filtered_results['ids'][0].append(results['ids'][0][i])
                        filtered_results['distances'][0].append(distance)
                        filtered_results['documents'][0].append(results['documents'][0][i])
                        filtered_results['metadatas'][0].append(results['metadatas'][0][i])
                
                return filtered_results
            
            return results
            
        except Exception as e:
            print(f"Error searching: {e}")
            return {'ids': [[]], 'distances': [[]], 'documents': [[]], 'metadatas': [[]]}
    
    def delete_turn(self, turn_id):
        """Remove a turn from the vector index
        
        Args:
            turn_id: UUID of the turn to delete
        """
        try:
            self.collection.delete(ids=[str(turn_id)])
            return True
        except Exception as e:
            print(f"Error deleting turn {turn_id}: {e}")
            return False
    
    def delete_conversation(self, conversation_id):
        """Remove all turns of a conversation from the vector index
        
        Args:
            conversation_id: UUID of the conversation
        """
        try:
            # Get all turn IDs for this conversation
            results = self.collection.get(
                where={"conversation_id": str(conversation_id)}
            )
            
            if results['ids']:
                self.collection.delete(ids=results['ids'])
            
            return True
        except Exception as e:
            print(f"Error deleting conversation {conversation_id}: {e}")
            return False
    
    def get_stats(self):
        """Get statistics about the vector database"""
        try:
            count = self.collection.count()
            
            # Sample to get source breakdown
            sample_size = min(1000, count)
            if sample_size > 0:
                sample = self.collection.get(limit=sample_size)
                
                sources = {}
                conversations = set()
                
                if sample['metadatas']:
                    for metadata in sample['metadatas']:
                        source = metadata.get('source', 'unknown')
                        sources[source] = sources.get(source, 0) + 1
                        conversations.add(metadata.get('conversation_id', ''))
                
                return {
                    'total_turns': count,
                    'unique_conversations': len(conversations),
                    'sources': sources
                }
            
            return {
                'total_turns': 0,
                'unique_conversations': 0,
                'sources': {}
            }
            
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {
                'total_turns': 0,
                'unique_conversations': 0,
                'sources': {}
            }


# Singleton instance
# Lazy initialization to avoid hanging on module import
# vector_search = VectorSearchService()

def get_vector_search_service():
    """Get or create the vector search service instance"""
    global _vector_search_instance
    if '_vector_search_instance' not in globals():
        _vector_search_instance = VectorSearchService()
    return _vector_search_instance
