# Vector Search Service Architecture

## Overview

The vector search functionality runs as a **separate standalone service** independent of Django. This architecture solves initialization issues and provides better scalability.

## Architecture

```
┌─────────────────┐         ┌──────────────────────┐         ┌─────────────────┐
│                 │         │                      │         │                 │
│  Django (8001)  │────────▶│  Vector Service      │────────▶│   ChromaDB      │
│                 │  HTTP   │  (Flask, 8002)       │         │   (Persistent)  │
│                 │         │                      │         │                 │
└─────────────────┘         └──────────────────────┘         └─────────────────┘
        │                            │
        │                            │
        ▼                            ▼
  Django Signals              Sentence Transformers
  (Auto-index turns)          (Generate embeddings)
```

## Components

### 1. Vector Service (`vector_service.py`)
- **Port**: 8002 (default)
- **Framework**: Flask
- **Purpose**: Handles all vector search operations
- **Features**:
  - Index conversation turns
  - Semantic search
  - Delete turns/conversations
  - Statistics

### 2. Vector Search Client (`people/vector_search_client.py`)
- **Purpose**: Django client for communicating with vector service
- **Features**:
  - HTTP-based communication
  - Health checks
  - Automatic fallback if service is down

### 3. Django Signals (`people/signals.py`)
- **Purpose**: Auto-index turns when saved
- **Behavior**: Checks if vector service is healthy before indexing

## Starting the Services

### 1. Start Vector Service

```bash
cd /home/ubuntu/monorepo/data-backend
source .venv/bin/activate
python vector_service.py
```

The service will:
- Load the sentence transformer model
- Connect to ChromaDB
- Start listening on http://localhost:8002

### 2. Start Django

```bash
cd /home/ubuntu/monorepo/data-backend
source .venv/bin/activate
python manage.py runserver 8001
```

Django will:
- Connect to the vector service via HTTP
- Auto-index new conversation turns (if vector service is running)

## API Endpoints

### Vector Service Endpoints

#### Health Check
```bash
GET http://localhost:8002/health
```

Response:
```json
{
  "status": "healthy",
  "model": "all-MiniLM-L6-v2",
  "collection": "conversation_turns",
  "document_count": 42
}
```

#### Index a Turn
```bash
POST http://localhost:8002/index
Content-Type: application/json

{
  "turn_id": "uuid",
  "conversation_id": "uuid",
  "conversation_title": "My Conversation",
  "conversation_user_id": "user_id",
  "source": "chatgpt",
  "content": "What is Python?",
  "turn_number": 1,
  "role": "user",
  "timestamp": "2024-01-15T10:00:00Z"
}
```

#### Semantic Search
```bash
POST http://localhost:8002/search
Content-Type: application/json

{
  "query": "python programming",
  "limit": 10,
  "min_score": 0.5,
  "user_id": "user_id"
}
```

#### Delete Turn
```bash
DELETE http://localhost:8002/delete_turn/<turn_id>
```

#### Delete Conversation
```bash
DELETE http://localhost:8002/delete_conversation/<conversation_id>
```

#### Statistics
```bash
GET http://localhost:8002/stats?user_id=<user_id>
```

## Configuration

### Django Settings (`config/settings.py`)

```python
VECTOR_SERVICE_URL = 'http://localhost:8002'
```

### Vector Service Settings

Edit `vector_service.py` to change:
- Port: `--port 8002`
- Host: `--host 0.0.0.0` (for external access)
- Model: Change `SentenceTransformer('all-MiniLM-L6-v2')`
- Database path: Modify `db_path` variable

## Benefits of This Architecture

1. **No Initialization Hang**: Vector service loads independently
2. **Scalability**: Can run on separate server
3. **Resilience**: Django works even if vector service is down
4. **Flexibility**: Easy to swap out vector service implementation
5. **Performance**: Dedicated resources for embeddings

## Troubleshooting

### Vector Service Won't Start

Check logs:
```bash
tail -f /tmp/vector_service.log
```

Common issues:
- Port 8002 already in use
- ChromaDB database corruption
- Missing dependencies (flask, sentence-transformers)

### Django Can't Connect to Vector Service

1. Check if vector service is running:
```bash
curl http://localhost:8002/health
```

2. Check Django logs for connection errors

3. Verify `VECTOR_SERVICE_URL` in settings.py

### Turns Not Being Indexed

1. Check vector service health
2. Check Django signals are enabled
3. Manually test indexing:
```python
from people.vector_search_client import get_vector_search_client
client = get_vector_search_client()
print(client.health_check())
```

## Production Deployment

### Systemd Service Files

#### Vector Service (`/etc/systemd/system/vector-service.service`)

```ini
[Unit]
Description=Vector Search Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/monorepo/data-backend
Environment="PATH=/home/ubuntu/monorepo/data-backend/.venv/bin"
ExecStart=/home/ubuntu/monorepo/data-backend/.venv/bin/python vector_service.py --host 0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Django Service (`/etc/systemd/system/django.service`)

```ini
[Unit]
Description=Django Application
After=network.target vector-service.service
Requires=vector-service.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/monorepo/data-backend
Environment="PATH=/home/ubuntu/monorepo/data-backend/.venv/bin"
ExecStart=/home/ubuntu/monorepo/data-backend/.venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:8001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable vector-service django
sudo systemctl start vector-service django
```

## Monitoring

### Check Service Status
```bash
# Vector service
curl http://localhost:8002/health

# Django
curl http://localhost:8001/api/conversations/stats/
```

### View Logs
```bash
# Vector service
tail -f /tmp/vector_service.log

# Django
tail -f /tmp/django.log
```

### Monitor Performance
```bash
# Check document count
curl http://localhost:8002/stats

# Test search performance
time curl -X POST http://localhost:8002/search -H "Content-Type: application/json" -d '{"query":"test","limit":10}'
```

## Migration from Old Architecture

If you have an existing ChromaDB database from the old integrated approach:

1. Stop Django
2. Move the old `chroma_db` directory to the new location
3. Start vector service (it will use the existing database)
4. Start Django

The vector service will automatically use the existing ChromaDB data.

## Future Enhancements

- [ ] Add authentication to vector service
- [ ] Implement rate limiting
- [ ] Add caching layer (Redis)
- [ ] Support multiple embedding models
- [ ] Add batch indexing endpoint
- [ ] Implement async indexing with Celery
- [ ] Add metrics and monitoring (Prometheus)
