#!/usr/bin/env python3
"""
Vector Search Service

A standalone service for semantic search using ChromaDB.
Runs independently from Django to avoid initialization issues.

Usage:
    python vector_service.py [--port 8002] [--host 0.0.0.0]
"""

from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
import os
import argparse

app = Flask(__name__)

# Global instances
model = None
chroma_client = None
collection = None

def init_vector_search():
    """Initialize the vector search components"""
    global model, chroma_client, collection
    
    print("Initializing vector search service...")
    
    # Initialize sentence transformer
    print("Loading sentence transformer model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    # Initialize ChromaDB
    print("Connecting to ChromaDB...")
    db_path = os.path.join(os.path.dirname(__file__), 'chroma_db')
    os.makedirs(db_path, exist_ok=True)
    
    chroma_client = chromadb.PersistentClient(
        path=db_path,
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=True
        )
    )
    
    # Get or create collection
    collection = chroma_client.get_or_create_collection(
        name="conversation_turns",
        metadata={"hnsw:space": "cosine"}
    )
    
    print(f"✓ Vector search service initialized")
    print(f"  Collection: {collection.name}")
    print(f"  Documents: {collection.count()}")


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'model': 'all-MiniLM-L6-v2',
        'collection': collection.name if collection else None,
        'document_count': collection.count() if collection else 0
    })


@app.route('/index', methods=['POST'])
def index_document():
    """Index a document (Note entity)"""
    try:
        data = request.json
        
        # Extract data
        doc_id = data['id']
        user_id = data.get('user_id', '')
        label = data.get('label', '')
        content = data['content']
        tags = data.get('tags', [])
        doc_type = data.get('type', 'Note')
        
        # Generate embedding
        embedding = model.encode(content).tolist()
        
        # Upsert to ChromaDB
        collection.upsert(
            ids=[str(doc_id)],
            embeddings=[embedding],
            documents=[content],
            metadatas=[{
                'user_id': str(user_id),
                'label': label,
                'tags': ','.join(tags) if isinstance(tags, list) else str(tags),
                'type': doc_type
            }]
        )
        
        return jsonify({
            'success': True,
            'id': doc_id,
            'message': 'Document indexed successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/search', methods=['POST'])
def search():
    """Semantic search"""
    try:
        data = request.json
        
        query = data['query']
        limit = data.get('limit', 10)
        min_score = data.get('min_score', 0.0)
        user_id = data.get('user_id')
        tags = data.get('tags', [])
        
        # Generate query embedding
        query_embedding = model.encode(query).tolist()
        
        # Build where clause for filtering
        where_clause = {}
        if user_id:
            where_clause['user_id'] = str(user_id)
        
        # Note: ChromaDB doesn't support complex tag filtering in where clause
        # We'll filter by tags in post-processing if needed
        
        # Search
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=limit * 2 if tags else limit,  # Get more if we need to filter by tags
            where=where_clause if where_clause else None,
            include=['documents', 'distances', 'metadatas']
        )
        
        # Format results
        formatted_results = []
        if results['ids'] and len(results['ids']) > 0:
            for i, doc_id in enumerate(results['ids'][0]):
                distance = results['distances'][0][i]
                similarity = 1 - distance  # Convert distance to similarity
                
                if similarity < min_score:
                    continue
                
                metadata = results['metadatas'][0][i]
                
                # Filter by tags if specified
                if tags:
                    doc_tags = metadata.get('tags', '').split(',')
                    if not any(tag in doc_tags for tag in tags):
                        continue
                
                formatted_results.append({
                    'id': doc_id,
                    'content': results['documents'][0][i],
                    'metadata': metadata,
                    'similarity': similarity,
                    'distance': distance
                })
                
                if len(formatted_results) >= limit:
                    break
        
        return jsonify({
            'success': True,
            'results': formatted_results,
            'count': len(formatted_results)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/delete/<doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    """Delete a document from the index"""
    try:
        collection.delete(ids=[str(doc_id)])
        return jsonify({
            'success': True,
            'message': f'Document {doc_id} deleted'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/stats', methods=['GET'])
def stats():
    """Get statistics"""
    try:
        user_id = request.args.get('user_id')
        
        total_count = collection.count()
        
        # Get user-specific count if user_id provided
        user_count = None
        if user_id:
            results = collection.get(
                where={'conversation_user_id': str(user_id)},
                include=[]
            )
            user_count = len(results['ids']) if results['ids'] else 0
        
        return jsonify({
            'success': True,
            'total_documents': total_count,
            'user_documents': user_count,
            'collection': collection.name
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def main():
    parser = argparse.ArgumentParser(description='Vector Search Service')
    parser.add_argument('--port', type=int, default=8002, help='Port to run on (default: 8002)')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to (default: 127.0.0.1)')
    args = parser.parse_args()
    
    # Initialize
    init_vector_search()
    
    # Run Flask app
    print(f"\n🚀 Starting Vector Search Service on http://{args.host}:{args.port}")
    print(f"   Health check: http://{args.host}:{args.port}/health\n")
    
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == '__main__':
    main()
