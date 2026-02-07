# System Context Document

## Project Overview
Django REST API backend with React frontend for entity management system. Deployed at https://bldrdojo.com using Docker Compose.

## Architecture

### Services (Docker Compose)
- **backend**: Django + Gunicorn (Python 3.11)
- **frontend**: React + Nginx (serves static files and proxies API)
- **db**: PostgreSQL 15
- **redis**: Redis 7 (caching)
- **meilisearch**: MeiliSearch v1.5 (search engine)
- **neo4j**: Neo4j 5 (graph database for relations)
- **vector-service**: Flask service for vector embeddings

### Key Ports
- 80/443: Frontend (Nginx)
- Backend runs on internal port 8000 (not exposed, proxied by Nginx)

## Critical Configuration

### Media Files (DO NOT CHANGE)
- **MEDIA_ROOT**: `BASE_DIR / 'media'` (inside container: `/app/media/`)
- **MEDIA_URL**: `/media/`
- **Docker volume**: `media_volume` mounted at `/app/media/` in both backend and frontend
- **Nginx serves**: `/media/` → `/app/media/`
- Tests are written assuming this structure

### Database (UPDATED)
- **Engine**: PostgreSQL 15 (was SQLite, now fixed)
- **Settings**: Always uses PostgreSQL via `POSTGRES_*` environment variables
- **Connection**: Direct via POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT
- **Note**: Do NOT use DATABASE_URL (has issues with special characters in password)
- **Local password**: `dbpassword`
- **Production password**: From `.env` file on server

### Static Files
- **STATIC_ROOT**: `/app/staticfiles/`
- **Docker volume**: `static_volume` mounted at `/app/staticfiles/`

### MeiliSearch Settings (FIXED)
- **Settings names**: `MEILISEARCH_URL` and `MEILI_MASTER_KEY`
- **Code uses**: `settings.MEILISEARCH_URL` and `settings.MEILI_MASTER_KEY` (fixed in people/sync.py)
- **URL**: `http://meilisearch:7700` (internal Docker network)

### Database
- **PostgreSQL**: Main data storage
- **Volume**: `bldrdojo-postgres-data` (persistent)
- **Connection**: Via DATABASE_URL environment variable

### SSL/HTTPS
- **Status**: ✅ Working correctly
- **Certificates**: Located at `/etc/nginx/ssl/` in frontend container
- **Mounted from**: `./ssl/` directory on host
- **Files**: `fullchain.pem` and `privkey.pem`
- **Nginx config**: Uses modern `http2 on;` directive (not deprecated `listen ... http2`)

## Current Issues

### 1. User Registration - Username Required ❌
**Problem**: Registration endpoint requires username field despite settings configured for email-only auth.

**Current Settings**:
```python
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email', 'password1', 'password2']
ACCOUNT_USER_MODEL_USERNAME_FIELD = 'username'
```

**CustomRegisterSerializer**: Attempts to make username optional and auto-populate with email.

**Status**: Backend container keeps restarting due to allauth configuration conflicts. Needs investigation.

### 2. Google OAuth Callback URL ✅ FIXED
**Problem**: Was hardcoded to localhost.

**Solution**: 
- Added `GOOGLE_OAUTH_CALLBACK_URL` setting
- Updated `people/social_auth_views.py` to use setting
- Docker compose sets default to `https://bldrdojo.com/auth/google/callback`

**Action Required**: Update Google Cloud Console to add `https://bldrdojo.com/auth/google/callback` to authorized redirect URIs.

### 3. Media File Thumbnails ⚠️
**Problem**: Thumbnails are generated but may not be accessible.

**Code**: `people/utils.py` - `save_file_deduplicated()` function generates thumbnails using Pillow.

**Status**: Need to verify thumbnails are being created and served correctly.

### 4. MeiliSearch Integration ✅ FIXED
**Problem**: Was looking for wrong setting names (`MEILI_URL` instead of `MEILISEARCH_URL`).

**Solution**: Fixed `people/sync.py` to use correct setting names.

**Action Required**: Rebuild backend and run `python manage.py reindex_meilisearch`.

### 5. Entity Creation ✅ FIXED
**Problem**: POST was sending `"id": "new"` which backend rejected.

**Solution**: Fixed `EntityDetail.jsx` to remove `id` field when it's `"new"` or `null`.

**Action Required**: Rebuild frontend.

## Data Persistence

### What's Persistent (Survives Rebuilds)
- ✅ PostgreSQL database (`bldrdojo-postgres-data` volume)
- ✅ Uploaded media files (`bldrdojo-media` volume)
- ✅ MeiliSearch index (`bldrdojo-meilisearch-data` volume)
- ✅ Neo4j graph data (`bldrdojo-neo4j-data` volume)
- ✅ Redis data (`bldrdojo-redis-data` volume)
- ✅ Vector embeddings (`bldrdojo-vector-data` volume)

### What's NOT Persistent
- ❌ Container state
- ❌ Application code (rebuilt from Dockerfile)

### Safe Commands
```bash
docker compose restart <service>
docker compose stop <service>
docker compose rm -f <service>
docker rmi <image>
docker compose build --no-cache <service>
docker compose up -d <service>
```

### DANGEROUS Commands (Will Delete Data)
```bash
docker compose down -v  # Deletes volumes!
docker volume rm <volume_name>
```

## Build Process

### Backend Rebuild
```bash
docker compose stop backend
docker compose rm -f backend
docker rmi data-backend-backend
docker compose build --no-cache backend
docker compose up -d backend
```

### Frontend Rebuild
```bash
cd frontend
npm install  # If dependencies changed
npm run build
cd ..
docker compose up -d --build frontend
```

## Environment Variables

### Backend (docker-compose.yml)
- `DJANGO_SETTINGS_MODULE=config.settings`
- `DATABASE_URL` (PostgreSQL connection)
- `REDIS_URL`
- `MEILISEARCH_URL=http://meilisearch:7700`
- `MEILI_MASTER_KEY`
- `NEO4J_URI=bolt://neo4j:7687`
- `NEO4J_USER`, `NEO4J_PASSWORD`
- `GOOGLE_OAUTH_CALLBACK_URL` (default: https://bldrdojo.com/auth/google/callback)

### Additional from .env file
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`

## Authentication

### Current Users
- Test users: `alice@example.com` / `testpass123`, `bob@example.com` / `testpass123`
- Users are stored in Django's default User model
- JWT tokens stored in localStorage on frontend

### Auth Flow
1. Login: POST `/api/auth/login/` → returns JWT tokens
2. Frontend stores: `access_token`, `refresh_token`, `current_user` in localStorage
3. API requests: Include `Authorization: Bearer <access_token>` header
4. Google OAuth: Redirects to Google → callback at `/auth/google/callback` → exchanges code for tokens

## API Endpoints

### Entity Types
- `/api/people/` - Person entities
- `/api/notes/` - Note entities
- `/api/locations/` - Location entities
- `/api/movies/` - Movie entities
- `/api/books/` - Book entities
- `/api/containers/` - Container entities
- `/api/assets/` - Asset entities
- `/api/orgs/` - Organization entities

### Other Endpoints
- `/api/entities/` - Generic entity endpoint
- `/api/relations/` - Entity relations
- `/api/upload/` - File upload
- `/api/search/` - MeiliSearch search
- `/api/tags/` - Tag management
- `/api/auth/` - Authentication (login, logout, register, Google OAuth)

## Frontend

### Key Files
- `src/services/api.js` - API client with automatic auth headers
- `src/utils/apiUrl.js` - API base URL logic (localhost in dev, relative in prod)
- `src/contexts/AuthContext.jsx` - Authentication state management
- `src/components/EntityDetail.jsx` - Entity create/edit form
- `src/components/GoogleCallback.jsx` - Google OAuth callback handler

### Build Configuration
- **Vite config**: `vite.config.js`
- **Source maps**: Enabled for debugging
- **Minification**: Disabled for easier debugging (can re-enable for production)

## Testing

### Test Files
- Multiple test files in root directory (`test_*.py`)
- Frontend integration tests in `frontend/tests/`
- Tests assume media files at `/media/` path

## Nginx Configuration

### Frontend (default.conf)
- HTTP (port 80): Redirects to HTTPS (except `/health` endpoint)
- HTTPS (port 443): Serves React app and proxies backend
- Proxies: `/api/`, `/admin/`, `/accounts/` → `http://backend:8000`
- Serves: `/static/` → `/app/staticfiles/`, `/media/` → `/app/media/`
- React routing: `try_files $uri $uri/ /index.html`
- Error pages: 404 → `/index.html` (for client-side routing)

## Known Working Features
- ✅ HTTPS/SSL
- ✅ User login (email/password)
- ✅ Entity CRUD operations
- ✅ File uploads (images, PDFs)
- ✅ Thumbnail generation (Pillow)
- ✅ Search (MeiliSearch)
- ✅ Relations between entities
- ✅ Rich text editor (TipTap)
- ✅ Multi-user support (entities owned by users)

## TODO / Needs Testing
- ⚠️ User registration (currently broken)
- ⚠️ Google OAuth (callback URL fixed, needs testing)
- ⚠️ MeiliSearch reindexing (after fixing setting names)
- ⚠️ Media file serving (after volume mount fix)

## Important Notes

### Don't Change Without Good Reason
1. Media file paths (`/app/media/`, `MEDIA_ROOT`)
2. Volume mount points in docker-compose.yml
3. Database connection settings
4. Existing test assumptions

### When Making Changes
1. Check if it affects existing tests
2. Verify volumes are correctly mounted
3. Test that data persists after rebuild
4. Check both backend and frontend logs for errors

### Debugging Tips
```bash
# Check logs
docker compose logs <service> --tail 50

# Check if service is running
docker compose ps

# Check volumes
docker volume ls | grep bldrdojo

# Inspect volume
docker volume inspect <volume_name>

# Execute commands in container
docker compose exec <service> <command>

# Check Django settings
docker compose exec backend python manage.py shell -c "from django.conf import settings; print(settings.MEDIA_ROOT)"
```

## Recent Changes (This Session)

1. ✅ Fixed MeiliSearch setting names in `people/sync.py` - now uses `MEILISEARCH_URL` and `MEILI_MASTER_KEY`
2. ✅ Fixed entity creation to not send `"id": "new"` in POST - `EntityDetail.jsx`
3. ✅ Fixed Google OAuth callback URL to use environment variable - `social_auth_views.py` and `settings.py`
4. ✅ Fixed nginx http2 deprecation warning - `frontend/default.conf`
5. ✅ Added source maps to frontend build - `vite.config.js`
6. ✅ **CRITICAL: Switched from SQLite to PostgreSQL** - `settings.py` and `requirements.txt`
7. ✅ Fixed migration 0013 to use PostgreSQL syntax (UUID, timestamp) instead of SQLite
8. ✅ Added `import_file` action to `NoteViewSet` - `people/views.py`
9. ✅ Fixed docker-compose volume mounts for media files (both use `/app/media/`)
10. ✅ Fixed nginx to serve media from `/app/media/`
11. ⚠️ User registration still broken (allauth configuration issues)

## Next Steps

1. Fix user registration (resolve allauth configuration conflicts)
2. Test Google OAuth flow end-to-end
3. Rebuild backend with MeiliSearch fix and reindex
4. Verify media files and thumbnails are accessible
5. Test entity creation with new frontend build
