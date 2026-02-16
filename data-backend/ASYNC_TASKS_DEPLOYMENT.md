# Async Tasks Deployment Checklist

Quick reference for deploying the async tasks feature.

## Pre-Deployment Checklist

- [ ] Review `ASYNC_TASKS_GUIDE.md` for architecture details
- [ ] Review `ASYNC_TASKS_SUMMARY.md` for implementation overview
- [ ] Ensure Redis is running and accessible
- [ ] Backup current database (optional but recommended)

## Deployment Steps

### 1. Update Dependencies

```bash
cd /home/ubuntu/monorepo/data-backend
pip install -r requirements.txt
```

**New dependencies:**
- `celery>=5.3.0`
- `redis>=5.0.0`

### 2. Update Environment Variables

Ensure `.env` file has:
```bash
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
REDIS_PASSWORD=your_redis_password
```

### 3. Build Frontend

```bash
cd frontend
npm install  # If ProgressModal dependencies are missing
npm run build
cd ..
```

### 4. Rebuild Docker Images

```bash
# Production
docker compose build backend frontend

# Development
docker compose -f docker-compose.local.yml build backend
```

### 5. Start Services

```bash
# Production
docker compose up -d

# Development
docker compose -f docker-compose.local.yml up -d
```

This will start:
- Django backend
- Celery worker (NEW)
- Redis
- All other existing services

### 6. Verify Deployment

```bash
# Check all services are running
docker compose ps

# Verify Celery worker
docker compose logs celery-worker --tail=50

# Check backend health
curl http://localhost:8000/api/health/

# Check Redis connection
docker compose exec backend python -c "from django.core.cache import cache; cache.set('test', 1); print('Redis OK')"
```

### 7. Test Async Tasks

#### Test Reindex
```bash
# Via API (requires authentication token)
curl -X POST http://localhost:8000/api/entities/reindex/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### Test via UI
1. Login to application
2. Click user menu
3. Click "Reindex Search"
4. Verify progress modal appears
5. Wait for completion

### 8. Monitor Initial Tasks

```bash
# Watch Celery worker logs
docker compose logs -f celery-worker

# Check active tasks
docker compose exec celery-worker celery -A config inspect active

# Check Redis cache
docker compose exec redis redis-cli -a ${REDIS_PASSWORD} KEYS "task_*"
```

## Post-Deployment Verification

### Functional Tests

- [ ] Reindex works and shows progress
- [ ] Import works and shows progress
- [ ] Export works and shows progress
- [ ] Cancel button works
- [ ] Progress updates in real-time
- [ ] Errors are displayed correctly
- [ ] Export download works after completion

### Performance Tests

- [ ] Tasks complete in reasonable time
- [ ] UI remains responsive during tasks
- [ ] Multiple concurrent tasks work
- [ ] Memory usage is acceptable

### Integration Tests

Run the test suite:
```bash
docker compose exec backend python manage.py test people.tests.test_async_tasks -v 2
```

Expected: All tests pass

## Rollback Plan

If issues occur:

### 1. Quick Rollback (Keep Celery)
```bash
# Stop Celery worker
docker compose stop celery-worker

# Users can still use sync endpoints:
# - POST /api/entities/import_data/
# - GET /api/entities/export/
```

### 2. Full Rollback
```bash
# Restore previous docker-compose.yml (without celery-worker)
git checkout HEAD~1 docker-compose.yml

# Rebuild and restart
docker compose up -d --build
```

## Troubleshooting

### Celery Worker Not Starting

**Symptoms:** `celery-worker` container exits immediately

**Solutions:**
1. Check logs: `docker compose logs celery-worker`
2. Verify Redis connection in logs
3. Check environment variables are set
4. Restart: `docker compose restart celery-worker`

### Tasks Not Processing

**Symptoms:** Tasks start but never complete

**Solutions:**
1. Check worker is running: `docker compose ps celery-worker`
2. Check worker logs for errors
3. Verify database connections
4. Check MeiliSearch/Neo4j are accessible
5. Restart worker: `docker compose restart celery-worker`

### Progress Not Updating

**Symptoms:** Progress modal shows 0% forever

**Solutions:**
1. Check browser console for errors
2. Verify API endpoint: `/api/entities/tasks/{id}/progress/`
3. Check Redis cache: `docker compose exec redis redis-cli -a ${REDIS_PASSWORD} GET task_progress_{id}`
4. Verify task is actually running in worker logs

### High Memory Usage

**Symptoms:** Celery worker using too much RAM

**Solutions:**
1. Reduce concurrency in docker-compose.yml: `--concurrency=1`
2. Add max tasks per child: `--max-tasks-per-child=100`
3. Restart worker periodically
4. Scale horizontally (multiple workers)

## Monitoring

### Key Metrics to Watch

1. **Task Completion Rate**
   ```bash
   docker compose exec celery-worker celery -A config inspect stats
   ```

2. **Task Duration**
   - Check logs for task timing
   - Monitor user complaints

3. **Error Rate**
   - Check worker logs for exceptions
   - Monitor progress errors in UI

4. **Resource Usage**
   ```bash
   docker stats celery-worker
   ```

### Alerts to Set Up

- Celery worker down
- Redis connection failures
- Task timeout rate > 5%
- Worker memory > 1GB
- Task queue depth > 100

## Maintenance

### Daily
- Check worker logs for errors
- Verify tasks are completing

### Weekly
- Review task completion rates
- Check for stuck tasks
- Monitor resource usage trends

### Monthly
- Review and optimize slow tasks
- Update dependencies
- Review and adjust timeouts

## Production Considerations

### Scaling

To handle more concurrent tasks:

```yaml
# In docker-compose.yml
celery-worker:
  deploy:
    replicas: 3  # Run 3 workers
  command: celery -A config worker --loglevel=info --concurrency=4
```

### Monitoring Tools

Consider adding:
- Flower (Celery monitoring UI)
- Prometheus + Grafana
- Sentry for error tracking

### Backup Strategy

- Redis persistence is enabled (appendonly)
- Task results expire after 1 hour
- No critical data stored in Redis

## Success Criteria

Deployment is successful when:
- ✅ All services start without errors
- ✅ Celery worker processes tasks
- ✅ Progress updates work in UI
- ✅ Tasks complete successfully
- ✅ Cancellation works
- ✅ All tests pass
- ✅ No increase in error rates
- ✅ User experience improves (no frozen UI)

## Support

If you encounter issues:
1. Check logs: `docker compose logs celery-worker`
2. Review `ASYNC_TASKS_GUIDE.md`
3. Check troubleshooting section above
4. Test with sync endpoints as fallback

## Deployment Timeline

Estimated time: **30-45 minutes**

- Dependencies: 5 min
- Build: 10 min
- Deploy: 5 min
- Verification: 10 min
- Testing: 10 min
- Documentation: 5 min

## Next Steps After Deployment

1. Monitor for 24 hours
2. Gather user feedback
3. Optimize based on usage patterns
4. Consider adding WebSocket support
5. Plan for task history feature

---

**Last Updated:** 2026-02-08
**Version:** 1.0
**Status:** Production Ready
