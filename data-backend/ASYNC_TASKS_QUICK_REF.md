# Async Tasks Quick Reference

One-page reference for the async tasks system.

## Quick Start

### Start Services
```bash
docker compose up -d  # Production
docker compose -f docker-compose.local.yml up -d  # Development
```

### Check Status
```bash
docker compose ps celery-worker
docker compose logs -f celery-worker
```

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/entities/reindex/` | POST | Start reindex |
| `/api/entities/import-async/` | POST | Start import |
| `/api/entities/export-async/` | START | Start export |
| `/api/entities/tasks/{id}/progress/` | GET | Check progress |
| `/api/entities/tasks/{id}/cancel/` | POST | Cancel task |
| `/api/entities/tasks/{id}/download/` | GET | Download export |

## Task Status Values

- `processing` - Task is running
- `completed` - Task finished successfully
- `failed` - Task encountered an error
- `cancelled` - Task was cancelled by user

## Progress Response Format

```json
{
  "task_id": "abc-123",
  "current": 50,
  "total": 100,
  "percentage": 50,
  "status": "processing",
  "message": "Processing...",
  "errors": []
}
```

## Common Commands

### Celery Worker

```bash
# View logs
docker compose logs -f celery-worker

# Restart worker
docker compose restart celery-worker

# Check active tasks
docker compose exec celery-worker celery -A config inspect active

# Check registered tasks
docker compose exec celery-worker celery -A config inspect registered

# Worker stats
docker compose exec celery-worker celery -A config inspect stats
```

### Redis Cache

```bash
# Connect to Redis
docker compose exec redis redis-cli -a ${REDIS_PASSWORD}

# List progress keys
KEYS task_progress_*

# Get progress
GET task_progress_abc-123

# List cancel flags
KEYS task_cancel_*

# Clear all task data
FLUSHDB
```

### Testing

```bash
# Run async task tests
docker compose exec backend python manage.py test people.tests.test_async_tasks

# Run specific test
docker compose exec backend python manage.py test people.tests.test_async_tasks.AsyncTasksTest.test_reindex_task_progress

# Verbose output
docker compose exec backend python manage.py test people.tests.test_async_tasks -v 2
```

## File Locations

| File | Purpose |
|------|---------|
| `config/celery.py` | Celery configuration |
| `people/tasks.py` | Task definitions |
| `people/views.py` | API endpoints |
| `frontend/src/components/ProgressModal.jsx` | Progress UI |
| `people/tests/test_async_tasks.py` | Tests |

## Environment Variables

```bash
REDIS_URL=redis://:password@redis:6379/0
REDIS_PASSWORD=your_password
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Worker not starting | Check logs, verify Redis connection |
| Tasks not processing | Restart worker, check DB connections |
| Progress not updating | Check Redis cache, verify task_id |
| High memory | Reduce concurrency, add max-tasks-per-child |

## Configuration

### Celery Settings (config/settings.py)
```python
CELERY_BROKER_URL = 'redis://redis:6379/0'
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_RESULT_EXPIRES = 3600  # 1 hour
```

### Worker Concurrency (docker-compose.yml)
```yaml
command: celery -A config worker --loglevel=info --concurrency=2
```

## Monitoring Checklist

- [ ] Worker is running
- [ ] Tasks are completing
- [ ] No errors in logs
- [ ] Memory usage < 500MB
- [ ] Response time < 2s

## Emergency Procedures

### Stop All Tasks
```bash
docker compose exec celery-worker celery -A config control shutdown
docker compose restart celery-worker
```

### Clear Task Queue
```bash
docker compose exec celery-worker celery -A config purge
```

### Fallback to Sync
If async system fails, users can use:
- `POST /api/entities/import_data/` (sync import)
- `GET /api/entities/export/` (sync export)

## Performance Tuning

### Increase Concurrency
```yaml
command: celery -A config worker --concurrency=4
```

### Add More Workers
```yaml
celery-worker:
  deploy:
    replicas: 3
```

### Adjust Timeouts
```python
CELERY_TASK_TIME_LIMIT = 60 * 60  # 1 hour
```

## Development Tips

### Add New Async Task

1. Define task in `people/tasks.py`:
```python
@shared_task(bind=True)
def my_task(self, user_id):
    task_id = self.request.id
    # ... implementation
```

2. Add endpoint in `people/views.py`:
```python
@action(detail=False, methods=['post'])
def my_action(self, request):
    task = my_task.delay(request.user.id)
    return Response({'task_id': task.id})
```

3. Update frontend to show progress

### Test Task Locally

```python
from people.tasks import reindex_user_entities
result = reindex_user_entities.delay(user_id=1)
print(result.id)  # Task ID
```

## Key Metrics

- **Task completion rate**: > 95%
- **Average duration**: < 5 minutes
- **Error rate**: < 5%
- **Cancellation rate**: < 10%
- **Memory per worker**: < 500MB

## Links

- Full Guide: `ASYNC_TASKS_GUIDE.md`
- Summary: `ASYNC_TASKS_SUMMARY.md`
- Deployment: `ASYNC_TASKS_DEPLOYMENT.md`

---

**Version:** 1.0 | **Last Updated:** 2026-02-08
