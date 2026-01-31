# Local Testing Guide

Complete guide for testing the bldrdojo.com stack on your local machine or staging environment.

## 🎯 Overview

The local setup provides:
- **All services** running in Docker containers
- **Hot reload** for both backend and frontend
- **Debug mode** enabled
- **Exposed ports** for direct access
- **Lower resource** requirements
- **No SSL** required
- **Console email** backend

## 📋 Prerequisites

### Required Software
```bash
# Docker
Docker version 20.10+
Docker Compose version 2.0+

# Git (to clone the repository)
git version 2.0+
```

### System Requirements
- **CPU**: 2+ cores
- **RAM**: 4GB minimum (8GB recommended)
- **Disk**: 10GB free space
- **OS**: macOS, Linux, or Windows with WSL2

### Install Docker

**macOS:**
```bash
# Install Docker Desktop
# Download from: https://www.docker.com/products/docker-desktop
```

**Linux:**
```bash
# Install Docker and Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

**Windows:**
```bash
# Install Docker Desktop for Windows
# Download from: https://www.docker.com/products/docker-desktop
# Requires WSL2
```

## 🚀 Quick Start (5 minutes)

### Step 1: Clone/Navigate to Project

```bash
cd /path/to/monorepo/data-backend
```

### Step 2: Start All Services

```bash
# Use the local compose file
docker-compose -f docker-compose.local.yml up -d

# View logs
docker-compose -f docker-compose.local.yml logs -f
```

### Step 3: Wait for Services

```bash
# Check service health (takes 30-60 seconds)
docker-compose -f docker-compose.local.yml ps

# Wait until all show "healthy" or "running"
```

### Step 4: Initialize Database

```bash
# Migrations are auto-run, but you can manually trigger
docker-compose -f docker-compose.local.yml exec backend python manage.py migrate

# Create superuser
docker-compose -f docker-compose.local.yml exec backend python manage.py createsuperuser
```

### Step 5: Access Application

- **Frontend**: http://localhost:5174
- **Backend API**: http://localhost:8001/api/
- **Admin Panel**: http://localhost:8001/admin/
- **Health Check**: http://localhost:8001/api/health/

### Direct Service Access

- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **MeiliSearch**: http://localhost:7700
- **Neo4j HTTP**: http://localhost:7474
- **Neo4j Bolt**: bolt://localhost:7687
- **Vector Service**: http://localhost:5000

## 📊 Service Details

### Connection Strings

```bash
# PostgreSQL
DATABASE_URL=postgresql://postgres:localdevpassword@localhost:5432/entitydb

# Redis
REDIS_URL=redis://:localredispass@localhost:6379/0

# MeiliSearch
MEILISEARCH_URL=http://localhost:7700
MEILI_MASTER_KEY=localmeilikey

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_AUTH=neo4j/localneo4jpass

# Vector Service
VECTOR_SERVICE_URL=http://localhost:5000
```

### Default Credentials

| Service | Username | Password |
|---------|----------|----------|
| PostgreSQL | postgres | localdevpassword |
| Redis | - | localredispass |
| MeiliSearch | - | localmeilikey |
| Neo4j | neo4j | localneo4jpass |

## 🛠️ Development Workflow

### Making Code Changes

**Backend (Django):**
```bash
# Edit Python files in data-backend/
# Changes auto-reload via Django runserver

# If you need to restart:
docker-compose -f docker-compose.local.yml restart backend
```

**Frontend (React):**
```bash
# Edit files in frontend/src/
# Vite dev server auto-reloads

# If you need to restart:
docker-compose -f docker-compose.local.yml restart frontend-dev
```

### Running Migrations

```bash
# Create migration
docker-compose -f docker-compose.local.yml exec backend python manage.py makemigrations

# Apply migration
docker-compose -f docker-compose.local.yml exec backend python manage.py migrate
```

### Accessing Django Shell

```bash
docker-compose -f docker-compose.local.yml exec backend python manage.py shell
```

### Accessing Database

```bash
# PostgreSQL shell
docker-compose -f docker-compose.local.yml exec db psql -U postgres -d entitydb

# Or from host (if psql installed)
psql postgresql://postgres:localdevpassword@localhost:5432/entitydb
```

### Accessing Redis

```bash
# Redis CLI
docker-compose -f docker-compose.local.yml exec redis redis-cli -a localredispass

# Test connection
docker-compose -f docker-compose.local.yml exec redis redis-cli -a localredispass ping
```

## 🧪 Testing

### Run Backend Tests

```bash
# Run all tests
docker-compose -f docker-compose.local.yml exec backend python manage.py test

# Run specific test
docker-compose -f docker-compose.local.yml exec backend python manage.py test people.tests.test_entities

# Run with coverage
docker-compose -f docker-compose.local.yml exec backend coverage run --source='.' manage.py test
docker-compose -f docker-compose.local.yml exec backend coverage report
```

### Manual Testing

1. **Test User Registration:**
   ```bash
   curl -X POST http://localhost:8001/api/auth/registration/ \
     -H "Content-Type: application/json" \
     -d '{"username":"testuser","email":"test@example.com","password1":"testpass123","password2":"testpass123"}'
   ```

2. **Test Login:**
   ```bash
   curl -X POST http://localhost:8001/api/auth/login/ \
     -H "Content-Type: application/json" \
     -d '{"username":"testuser","password":"testpass123"}'
   ```

3. **Test Health Check:**
   ```bash
   curl http://localhost:8001/api/health/
   curl http://localhost:8001/api/health/detailed/
   ```

4. **Test Frontend:**
   - Open http://localhost:5174 in browser
   - Register a new account
   - Create entities
   - Test search functionality

## 📦 Data Management

### Backup Local Data

```bash
# Backup database
docker-compose -f docker-compose.local.yml exec db pg_dump -U postgres entitydb > local_backup.sql

# Backup all volumes
docker run --rm -v bldrdojo-local-postgres-data:/data -v $(pwd):/backup alpine tar czf /backup/local_data.tar.gz -C /data .
```

### Restore Data

```bash
# Restore database
docker-compose -f docker-compose.local.yml exec -T db psql -U postgres entitydb < local_backup.sql

# Restore volumes
docker run --rm -v bldrdojo-local-postgres-data:/data -v $(pwd):/backup alpine tar xzf /backup/local_data.tar.gz -C /data
```

### Reset Everything

```bash
# Stop and remove all containers and volumes
docker-compose -f docker-compose.local.yml down -v

# Restart fresh
docker-compose -f docker-compose.local.yml up -d

# Recreate superuser
docker-compose -f docker-compose.local.yml exec backend python manage.py createsuperuser
```

## 🐛 Debugging

### View Logs

```bash
# All services
docker-compose -f docker-compose.local.yml logs -f

# Specific service
docker-compose -f docker-compose.local.yml logs -f backend
docker-compose -f docker-compose.local.yml logs -f frontend-dev
docker-compose -f docker-compose.local.yml logs -f db

# Last 100 lines
docker-compose -f docker-compose.local.yml logs --tail=100 backend
```

### Access Container Shell

```bash
# Backend
docker-compose -f docker-compose.local.yml exec backend bash

# Database
docker-compose -f docker-compose.local.yml exec db sh

# Frontend
docker-compose -f docker-compose.local.yml exec frontend-dev sh
```

### Check Service Health

```bash
# Status
docker-compose -f docker-compose.local.yml ps

# Detailed health
docker inspect bldrdojo-local-backend | grep -A 20 Health
```

### Common Issues

**Issue: Port already in use**
```bash
# Check what's using the port
lsof -i :5174  # or 8001, 5432, etc.

# Kill the process or change ports in docker-compose.local.yml
```

**Issue: Services won't start**
```bash
# Check logs
docker-compose -f docker-compose.local.yml logs

# Rebuild containers
docker-compose -f docker-compose.local.yml down
docker-compose -f docker-compose.local.yml build --no-cache
docker-compose -f docker-compose.local.yml up -d
```

**Issue: Database connection errors**
```bash
# Check database is running
docker-compose -f docker-compose.local.yml ps db

# Check database logs
docker-compose -f docker-compose.local.yml logs db

# Restart database
docker-compose -f docker-compose.local.yml restart db
```

**Issue: Frontend not updating**
```bash
# Rebuild frontend
docker-compose -f docker-compose.local.yml down frontend-dev
docker-compose -f docker-compose.local.yml build frontend-dev
docker-compose -f docker-compose.local.yml up -d frontend-dev
```

## 🔄 Common Commands

```bash
# Alias for convenience
alias dcl='docker-compose -f docker-compose.local.yml'

# Start services
dcl up -d

# Stop services
dcl down

# Restart service
dcl restart backend

# View logs
dcl logs -f backend

# Execute command
dcl exec backend python manage.py migrate

# Build without cache
dcl build --no-cache

# Remove volumes (clean slate)
dcl down -v

# Check resource usage
docker stats
```

## 📝 Environment Variables

The local setup uses `.env.local` with safe defaults. Key variables:

```bash
DJANGO_DEBUG=True                    # Enable debug mode
DJANGO_ALLOWED_HOSTS=localhost,...   # Allow local access
CORS_ALLOWED_ORIGINS=http://...      # Allow local frontend
EMAIL_BACKEND=console                # Print emails to console
SECURE_SSL_REDIRECT=False            # No SSL required
```

To customize, copy and edit:
```bash
cp .env.local .env.local.custom
# Edit .env.local.custom
# Use: docker-compose -f docker-compose.local.yml --env-file .env.local.custom up
```

## 🚦 Testing Production Config Locally

To test production configuration locally:

```bash
# Use production compose file with local settings
cp .env.example .env.staging
# Edit .env.staging with staging credentials

# Start with production config
docker-compose --env-file .env.staging up -d

# Access via:
# http://localhost (frontend)
# http://localhost:8000 (backend)
```

Note: You'll need SSL certificates even for local production testing.

## 📊 Performance Monitoring

```bash
# Container resource usage
docker stats

# Disk usage
docker system df

# Network inspection
docker network ls
docker network inspect bldrdojo-local-backend-network
```

## 🔒 Security Notes

**⚠️ IMPORTANT:**
- These credentials are for LOCAL TESTING ONLY
- NEVER use these in production
- Always use strong, unique passwords in production
- The local setup has relaxed security for ease of development

## 🎯 Next Steps After Local Testing

1. **Verify all features work locally**
2. **Run test suite**
3. **Test with production-like data**
4. **Document any issues**
5. **Deploy to staging environment**
6. **Deploy to production** (see DEPLOYMENT.md)

## 🆘 Getting Help

### Check Status
```bash
docker-compose -f docker-compose.local.yml ps
docker-compose -f docker-compose.local.yml logs
```

### Logs Location
- Backend logs: Console output
- Database logs: Console output
- Frontend logs: Console output

### Clean Start
```bash
# Nuclear option - reset everything
docker-compose -f docker-compose.local.yml down -v
docker system prune -a
docker volume prune
# Then start fresh
```

## 📚 Additional Resources

- **Production Deployment**: See `DEPLOYMENT.md`
- **Quick Start**: See `QUICK_START.md`
- **API Documentation**: http://localhost:8001/api/
- **Admin Interface**: http://localhost:8001/admin/

---

**Happy Testing! 🎉**
