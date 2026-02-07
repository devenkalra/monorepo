"""
Vector Search Client

Client for communicating with the standalone vector search service.
Updated to support Note entities.
"""

import requests
from django.conf import settings


class VectorSearchClient:
    """Client for vector search service"""
    
    def __init__(self, base_url=None):
        if base_url:
            self.base_url = base_url
        else:
            try:
                self.base_url = getattr(settings, 'VECTOR_SERVICE_URL', 'http://localhost:8002')
            except:
                self.base_url = 'http://localhost:8002'
    
    def health_check(self):
        """Check if the vector service is healthy"""
        try:
            response = requests.get(f'{self.base_url}/health', timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def index_note(self, note):
        """Index a Note entity"""
        try:
            # Strip HTML tags from description for better search
            import re
            content = re.sub('<[^<]+?>', '', note.description) if note.description else note.display
            
            data = {
                'id': str(note.id),
                'user_id': str(note.user.id),
                'label': note.display,  # Note uses 'display' not 'label'
                'content': content,
                'tags': note.tags if note.tags else [],
                'type': note.type
            }
            
            response = requests.post(
                f'{self.base_url}/index',
                json=data,
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            print(f"Error indexing note: {e}")
            return {'success': False, 'error': str(e)}
    
    def search(self, query, limit=10, min_score=0.0, user_id=None, tags=None):
        """Perform semantic search"""
        try:
            data = {
                'query': query,
                'limit': limit,
                'min_score': min_score,
                'user_id': str(user_id) if user_id else None,
                'tags': tags if tags else []
            }
            
            response = requests.post(
                f'{self.base_url}/search',
                json=data,
                timeout=30
            )
            
            return response.json()
            
        except Exception as e:
            print(f"Error searching: {e}")
            return {'success': False, 'error': str(e), 'results': []}
    
    def delete_note(self, note_id):
        """Delete a note from the index"""
        try:
            response = requests.delete(
                f'{self.base_url}/delete/{note_id}',
                timeout=5
            )
            return response.json()
        except Exception as e:
            print(f"Error deleting note: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_stats(self, user_id=None):
        """Get statistics"""
        try:
            params = {}
            if user_id:
                params['user_id'] = str(user_id)
            
            response = requests.get(
                f'{self.base_url}/stats',
                params=params,
                timeout=5
            )
            return response.json()
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {'success': False, 'error': str(e)}


# Global client instance
_client_instance = None

def get_vector_search_client():
    """Get or create the vector search client instance"""
    global _client_instance
    if _client_instance is None:
        _client_instance = VectorSearchClient()
    return _client_instance
