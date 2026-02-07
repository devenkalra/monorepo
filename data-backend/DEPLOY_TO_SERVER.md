# Deploy to Server Instructions

## Files Changed in This Session

Copy these files from dev machine to server:

```bash
# Core configuration
config/settings.py
requirements.txt

# Backend code
people/sync.py
people/views.py
people/social_auth_views.py
people/migrations/0013_change_entityrelation_id_to_uuid.py

# Docker configuration
docker-compose.yml

# Frontend
frontend/default.conf
frontend/vite.config.js
frontend/src/components/EntityDetail.jsx

# Documentation
SYSTEM_CONTEXT.md
GOOGLE_OAUTH_FIX.md
```

## Deployment Steps

### 1. Copy Files to Server

```bash
# From your dev machine
scp config/settings.py deploy@bldrdojo.com:/home/deploy/data-backend/config/
scp requirements.txt deploy@bldrdojo.com:/home/deploy/data-backend/
scp people/sync.py deploy@bldrdojo.com:/home/deploy/data-backend/people/
scp people/views.py deploy@bldrdojo.com:/home/deploy/data-backend/people/
scp people/social_auth_views.py deploy@bldrdojo.com:/home/deploy/data-backend/people/
scp people/migrations/0013_change_entityrelation_id_to_uuid.py deploy@bldrdojo.com:/home/deploy/data-backend/people/migrations/
scp docker-compose.yml deploy@bldrdojo.com:/home/deploy/data-backend/
scp frontend/default.conf deploy@bldrdojo.com:/home/deploy/data-backend/frontend/
scp frontend/vite.config.js deploy@bldrdojo.com:/home/deploy/data-backend/frontend/
scp frontend/src/components/EntityDetail.jsx deploy@bldrdojo.com:/home/deploy/data-backend/frontend/src/components/
scp SYSTEM_CONTEXT.md deploy@bldrdojo.com:/home/deploy/data-backend/
```

### 2. Reset PostgreSQL (Required - Password Mismatch)

```bash
# SSH to server
ssh deploy@bldrdojo.com

cd /home/deploy/data-backend

# Stop all services
docker compose down

# Remove PostgreSQL volume (will delete existing data - DB is new anyway)
docker volume rm bldrdojo-postgres-data

# Verify password in .env matches what you expect
cat .env | grep POSTGRES_PASSWORD
```

### 3. Rebuild and Start Services

```bash
# Build backend and frontend with new code
docker compose build --no-cache backend frontend

# Start all services
docker compose up -d

# Monitor startup
docker compose logs -f backend
```

Press Ctrl+C when you see "Booting worker with pid" messages (backend started successfully).

### 4. Verify Everything Works

```bash
# Check database connection
docker compose exec backend python manage.py shell -c "from django.db import connection; print('DB:', connection.settings_dict['ENGINE'], connection.settings_dict['NAME'])"

# Check tables exist
docker compose exec db psql -U postgres -d entitydb -c "\dt" | grep "auth_user\|people_entity"

# Create test user
docker compose exec backend python manage.py shell -c "from django.contrib.auth.models import User; u = User.objects.create_user('alice@example.com', 'alice@example.com', 'testpass123'); print('User created:', u.email)"

# Verify user in database
docker compose exec db psql -U postgres -d entitydb -c "SELECT id, username, email FROM auth_user;"

# Test registration endpoint
curl -X POST https://bldrdojo.com/api/auth/registration/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password1":"testpass123","password2":"testpass123"}'

# Test Google OAuth URL
curl -s https://bldrdojo.com/api/auth/google/url/ | python3 -m json.tool

# Test media file upload (need to login first and get token)

# Reindex MeiliSearch
docker compose exec backend python manage.py reindex_meilisearch
```

## Expected Results

- ✅ Backend starts without crashing
- ✅ PostgreSQL connection successful
- ✅ Users persist across rebuilds (in PostgreSQL volume)
- ✅ Google OAuth callback URL points to https://bldrdojo.com
- ✅ Media files accessible at /media/ URLs
- ✅ Import endpoint works at /api/notes/import_file/

## Known Issues Still to Fix

1. **User Registration**: Username field still required - needs investigation
2. **MeiliSearch**: Need to reindex after deployment
3. **Google OAuth**: Need to update redirect URI in Google Console

## Rollback (If Needed)

If something breaks, you can rollback the PostgreSQL change:

1. Stop services: `docker compose down`
2. Remove volumes: `docker volume rm bldrdojo-postgres-data`
3. Restore old settings.py with SQLite
4. Rebuild and restart

But note: **SQLite data will not persist across container rebuilds!**
