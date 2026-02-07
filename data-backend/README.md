# Data Backend Application

A full-stack personal data management application built with Django, React, and Neo4j.

## Features

- 📝 **Entity Management** - People, Notes, Locations, Movies, Books, Organizations, Assets, Containers
- 🔗 **Relationships** - Create and manage complex relationships between entities
- 🔍 **Full-Text Search** - Powered by MeiliSearch
- 📎 **Attachments** - Upload photos, documents with automatic thumbnail generation
- 🔖 **Tags** - Organize entities with flexible tagging
- 🌐 **URLs** - Attach and manage URLs with captions
- 🔐 **Authentication** - Secure user authentication with JWT
- 📱 **Responsive UI** - Modern React interface with dark mode

## Quick Start

### Development

```bash
# Start all services
docker-compose -f docker-compose.local.yml up

# Access the application
Frontend: http://localhost:5173
Backend API: http://localhost:8000/api/
Admin: http://localhost:8000/admin/
```

See [Development Guide](#development) for details.

### Production Deployment

```bash
# Quick deployment (30 minutes)
See: DEPLOYMENT_QUICK_START.md

# Comprehensive guide (2-3 hours)
See: PRODUCTION_DEPLOYMENT.md
```

## Documentation

### Getting Started
- **[Development Setup](#development)** - Local development environment
- **[API Documentation](#api-documentation)** - REST API reference
- **[Testing Guide](TESTING.md)** - Running tests

### Deployment
- **[Production Deployment](PRODUCTION_DEPLOYMENT.md)** - Complete deployment guide
- **[Quick Start](DEPLOYMENT_QUICK_START.md)** - 30-minute deployment
- **[Deployment Checklist](DEPLOYMENT_CHECKLIST.md)** - Interactive checklist
- **[Deployment Summary](DEPLOYMENT_SUMMARY.md)** - Overview

### Testing
- **[Testing Guide](TESTING.md)** - Comprehensive testing documentation
- **[Quick Reference](TESTING_QUICK_REFERENCE.md)** - Common test commands
- **[Test Suite Summary](TEST_SUITE_SUMMARY.md)** - Overview of all tests
- **[Integration Tests](INTEGRATION_TESTING.md)** - Full-stack testing with Playwright

### Operations
- **[Backup & Restore](#backup--restore)** - Data backup procedures
- **[Monitoring](#monitoring)** - Health checks and logging
- **[Troubleshooting](#troubleshooting)** - Common issues and solutions

## Technology Stack

### Backend
- **Django 4.2+** - Web framework
- **Django REST Framework** - API
- **PostgreSQL 15** - Primary database
- **Neo4j 5** - Graph database for relationships
- **Redis 7** - Caching and sessions
- **MeiliSearch 1.5** - Full-text search
- **Gunicorn** - WSGI server (production)

### Frontend
- **React 19** - UI framework
- **Vite** - Build tool
- **Tailwind CSS** - Styling
- **React Router** - Navigation

### Infrastructure
- **Docker & Docker Compose** - Containerization
- **Nginx** - Reverse proxy (production)
- **Let's Encrypt** - SSL certificates (production)

## Development

### Prerequisites

- Docker & Docker Compose
- Git
- 8GB RAM recommended

### Setup

```bash
# Clone repository
git clone <repository-url>
cd data-backend

# Copy environment file
cp .env.example .env

# Start services
docker-compose -f docker-compose.local.yml up

# Create superuser (in another terminal)
docker-compose -f docker-compose.local.yml exec backend python manage.py createsuperuser

# Access the application
# Frontend: http://localhost:5173
# Backend: http://localhost:8000
# Admin: http://localhost:8000/admin/
```

### Running Tests

```bash
# Backend tests
./run_tests.sh

# Frontend tests
cd frontend && npm test

# Integration tests
cd frontend && npx playwright test --ui
```

See [TESTING.md](TESTING.md) for comprehensive testing guide.

## API Documentation

### Authentication

```bash
# Register
POST /api/auth/register/
{
  "email": "user@example.com",
  "username": "username",
  "password": "password123"
}

# Login
POST /api/auth/login/
{
  "email": "user@example.com",
  "password": "password123"
}
```

### Entities

```bash
# List entities
GET /api/entities/

# Create entity
POST /api/people/
{
  "first_name": "John",
  "last_name": "Doe",
  "display": "John Doe"
}

# Get entity
GET /api/entities/{id}/

# Update entity
PUT /api/entities/{id}/

# Delete entity
DELETE /api/entities/{id}/
```

### Relations

```bash
# Get entity relations
GET /api/entities/{id}/relations/

# Create relation
POST /api/relations/
{
  "from_entity": "uuid",
  "to_entity": "uuid",
  "relation_type": "IS_FRIEND_OF"
}
```

### Search

```bash
# Search entities
GET /api/search/?q=query&type=Person&tags=tag1,tag2
```

## Backup & Restore

### Create Backup

```bash
# Manual backup
./scripts/backup.sh [backup-name]

# Setup automated daily backups
./scripts/setup_automated_backups.sh daily

# Verify backup
./scripts/verify_backup.sh backup_name
```

### Restore from Backup

```bash
# Dry run (preview)
./scripts/restore.sh backup_name --dry-run

# Full restore
./scripts/restore.sh backup_name

# Database only
./scripts/restore.sh backup_name --db-only
```

## Monitoring

### Health Checks

```bash
# Check all services
docker-compose -f docker-compose.local.yml ps

# View logs
docker-compose -f docker-compose.local.yml logs -f [service]

# Check backend health
curl http://localhost:8000/api/

# Run health check script (production)
./scripts/health_check.sh
```

### Logs

```bash
# Backend logs
docker-compose logs -f backend

# Frontend logs
docker-compose logs -f frontend

# Database logs
docker-compose logs -f db

# All logs
docker-compose logs -f
```

## Troubleshooting

### Common Issues

#### Services Won't Start

```bash
# Check logs
docker-compose logs [service]

# Restart services
docker-compose restart

# Rebuild containers
docker-compose build --no-cache
docker-compose up
```

#### Database Connection Error

```bash
# Check database is running
docker-compose ps db

# Check database logs
docker-compose logs db

# Reset database (WARNING: deletes data)
docker-compose down -v
docker-compose up
```

#### Search Not Working

```bash
# Reindex MeiliSearch
docker-compose exec backend python manage.py shell
>>> from people.sync import sync_all_to_meilisearch
>>> sync_all_to_meilisearch()
```

#### Port Already in Use

```bash
# Find process using port
lsof -ti:8000

# Kill process
kill -9 $(lsof -ti:8000)
```

## Project Structure

```
data-backend/
├── config/                 # Django settings
├── people/                 # Main Django app
│   ├── models.py          # Entity models
│   ├── views.py           # API views
│   ├── serializers.py     # DRF serializers
│   ├── constants.py       # Relation schemas
│   ├── sync.py            # Neo4j & MeiliSearch sync
│   └── tests/             # Backend tests
├── frontend/              # React application
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── api.js         # API client
│   │   └── main.jsx       # Entry point
│   └── tests/             # Frontend tests
├── scripts/               # Utility scripts
│   ├── backup.sh          # Backup script
│   ├── restore.sh         # Restore script
│   └── deploy_production.sh
├── media/                 # Uploaded files
├── staticfiles/           # Static assets
├── docker-compose.local.yml
├── docker-compose.production.yml
└── requirements.txt       # Python dependencies
```

## Contributing

### Development Workflow

1. Create feature branch
2. Make changes
3. Run tests
4. Submit pull request

### Code Style

- **Python:** PEP 8, use `black` formatter
- **JavaScript:** ESLint configuration
- **Git:** Conventional commits

### Running Tests Before Commit

```bash
# Backend tests
./run_tests.sh

# Frontend tests
cd frontend && npm test

# Integration tests
cd frontend && npx playwright test
```

## License

[Your License Here]

## Support

For issues or questions:
- Check [Troubleshooting](#troubleshooting)
- Review [Documentation](#documentation)
- Open an issue on GitHub

---

## Quick Links

- 📖 [Full Documentation](#documentation)
- 🚀 [Production Deployment](PRODUCTION_DEPLOYMENT.md)
- 🧪 [Testing Guide](TESTING.md)
- 💾 [Backup Scripts](scripts/)
- 🔧 [Troubleshooting](#troubleshooting)

---

**Version:** 1.0.0  
**Last Updated:** 2026-02-01
