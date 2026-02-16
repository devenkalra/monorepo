# Async Tasks with Progress Tracking

This guide explains the async task system for long-running operations (import, export, reindex) with real-time progress tracking and cancellation support.

## Overview

Long-running operations now run asynchronously using Celery with Redis as the message broker. Users get:
- Real-time progress updates
- Ability to cancel running tasks
- Automatic recovery from failures
- Better UI responsiveness

## Architecture

### Components

1. **Celery** - Distributed task queue
2. **Redis** - Message broker and progress cache
3. **Django Cache** - Progress state storage
4. **Frontend ProgressModal** - Real-time UI updates

### Task Flow

```
User Action → API Endpoint → Celery Task → Progress Updates → Completion
                                  ↓
                            Redis Cache ← Frontend Polling
```

## Backend Implementation

### Task Definitions

All async tasks are defined in `people/tasks.py`:

- `reindex_user_entities(user_id)` - Reindex all entities in MeiliSearch
- `import_entities_async(user_id, data_json)` - Import entities from JSON
- `export_entities_async(user_id)` - Export all user data

### Progress Tracking

Tasks update progress using `update_task_progress()`:

```python
update_task_progress(
    task_id,
    current=10,      # Current progress
    total=100,       # Total items
    status='processing',  # 'processing', 'completed', 'failed', 'cancelled'
    message='Processing entities...',
    errors=['error1', 'error2']
)
```

Progress is stored in Redis cache with 1-hour expiration.

### Cancellation

Tasks check for cancellation using `check_task_cancelled(task_id)`:

```python
if check_task_cancelled(task_id):
    update_task_progress(task_id, current, total, 'cancelled', 'Task cancelled')
    return {'success': False, 'cancelled': True}
```

## API Endpoints

### Start Async Tasks

**Reindex**
```
POST /api/entities/reindex/
Response: { "success": true, "task_id": "abc-123", "message": "..." }
```

**Import**
```
POST /api/entities/import-async/
Body: multipart/form-data with 'file' field
Response: { "success": true, "task_id": "abc-123", "message": "..." }
```

**Export**
```
POST /api/entities/export-async/
Response: { "success": true, "task_id": "abc-123", "message": "..." }
```

### Check Progress

```
GET /api/entities/tasks/{task_id}/progress/
Response: {
    "task_id": "abc-123",
    "current": 50,
    "total": 100,
    "percentage": 50,
    "status": "processing",
    "message": "Processing...",
    "errors": []
}
```

### Cancel Task

```
POST /api/entities/tasks/{task_id}/cancel/
Response: { "success": true, "message": "Task cancellation requested" }
```

### Download Export

```
GET /api/entities/tasks/{task_id}/download/
Response: JSON file download
```

## Frontend Implementation

### ProgressModal Component

The `ProgressModal` component (`frontend/src/components/ProgressModal.jsx`) provides:

- Real-time progress bar
- Status messages
- Error display
- Cancel button
- Completion notifications

### Usage in UserMenu

```javascript
// Start async task
const response = await api.fetch('/api/entities/reindex/', { method: 'POST' });
const result = await response.json();

if (result.success) {
  setProgressTask({ taskId: result.task_id, taskType: 'reindex' });
}

// Handle completion
const handleReindexComplete = (progressData) => {
  if (progressData.status === 'completed') {
    alert('Reindex completed successfully!');
  }
};
```

### Progress Polling

The ProgressModal automatically polls every 1 second for updates until the task completes, fails, or is cancelled.

## Deployment

### Docker Compose

Both `docker-compose.yml` and `docker-compose.local.yml` include a Celery worker service:

```yaml
celery-worker:
  build:
    context: .
    dockerfile: Dockerfile
  environment:
    - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
    # ... other environment variables
  command: celery -A config worker --loglevel=info --concurrency=2
```

### Starting Services

**Production:**
```bash
docker compose up -d
```

**Development:**
```bash
docker compose -f docker-compose.local.yml up -d
```

### Monitoring Celery

Check Celery worker logs:
```bash
docker compose logs -f celery-worker
```

Check active tasks:
```bash
docker compose exec celery-worker celery -A config inspect active
```

## Configuration

### Celery Settings (config/settings.py)

```python
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_RESULT_EXPIRES = 3600  # 1 hour
```

### Redis Configuration

Redis is used for:
1. Celery message broker
2. Task result backend
3. Progress state cache

## Testing

Run async task tests:

```bash
# Local environment
docker compose -f docker-compose.local.yml exec backend python manage.py test people.tests.test_async_tasks

# Production environment
docker compose exec backend python manage.py test people.tests.test_async_tasks
```

Test coverage includes:
- Task progress tracking
- Task cancellation
- Import/export/reindex functionality
- Error handling
- Invalid task IDs

## Error Handling

### Task Failures

When a task fails:
1. Status is set to 'failed'
2. Error message is stored in progress data
3. Frontend displays error to user
4. Task can be retried by user

### Network Issues

If frontend loses connection:
- Progress polling will retry automatically
- Task continues running on backend
- User can refresh page and check progress again

### Timeout Protection

Tasks have soft and hard time limits:
- Soft limit: 25 minutes (warning)
- Hard limit: 30 minutes (termination)

## Best Practices

### For Backend Development

1. **Update progress frequently** - Every 10 items or 1 second
2. **Check for cancellation** - In long loops
3. **Handle errors gracefully** - Store error messages
4. **Use transactions** - For database operations
5. **Clean up resources** - Even on cancellation

### For Frontend Development

1. **Show progress immediately** - Don't wait for first poll
2. **Handle all states** - processing, completed, failed, cancelled
3. **Provide cancel option** - For all long tasks
4. **Display errors clearly** - With actionable messages
5. **Auto-close on success** - After brief delay

## Troubleshooting

### Task Not Starting

1. Check Celery worker is running: `docker compose ps celery-worker`
2. Check Redis connection: `docker compose exec backend python -c "from django.core.cache import cache; cache.set('test', 1)"`
3. Check logs: `docker compose logs celery-worker`

### Progress Not Updating

1. Verify Redis is accessible
2. Check task_id is correct
3. Verify cache timeout hasn't expired (1 hour)
4. Check browser console for polling errors

### Task Stuck

1. Check Celery worker logs for errors
2. Verify database connections
3. Check MeiliSearch/Neo4j availability
4. Cancel and retry task

## Future Enhancements

Potential improvements:
- WebSocket support for real-time updates (eliminate polling)
- Task scheduling (cron-like)
- Task priority queues
- Batch operations
- Task history/audit log
- Email notifications on completion
- Retry failed tasks automatically

## Related Files

- `people/tasks.py` - Task definitions
- `people/views.py` - API endpoints
- `config/celery.py` - Celery configuration
- `config/settings.py` - Django settings
- `frontend/src/components/ProgressModal.jsx` - Progress UI
- `frontend/src/components/UserMenu.jsx` - Task triggers
- `people/tests/test_async_tasks.py` - Tests
- `docker-compose.yml` - Production deployment
- `docker-compose.local.yml` - Development deployment
