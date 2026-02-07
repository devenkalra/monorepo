# Production Security & Configuration Checklist

## ✅ Environment Variables Verification

### Critical Security Variables
All sensitive data MUST be stored in `.env` file and NEVER committed to git.

#### 1. Django Core Settings
- [ ] `DJANGO_SECRET_KEY` - Unique 50+ character random string
  ```bash
  python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
- [ ] `DJANGO_DEBUG=False` - MUST be False in production
- [ ] `DJANGO_ALLOWED_HOSTS` - Set to your domain(s)
- [ ] `DJANGO_CSRF_TRUSTED_ORIGINS` - Set to https://yourdomain.com

#### 2. Database Passwords
- [ ] `POSTGRES_PASSWORD` - Strong password (20+ chars)
- [ ] `REDIS_PASSWORD` - Strong password (20+ chars)
- [ ] `NEO4J_PASSWORD` - Strong password (20+ chars)
- [ ] `MEILI_MASTER_KEY` - At least 16 characters

#### 3. JWT Configuration
- [ ] `JWT_SECRET_KEY` - Separate from Django secret (50+ chars)
- [ ] `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` - Default: 60
- [ ] `JWT_REFRESH_TOKEN_LIFETIME_DAYS` - Default: 7

#### 4. CORS Configuration
- [ ] `CORS_ALLOWED_ORIGINS` - Only your production domain(s)
  ```
  CORS_ALLOWED_ORIGINS=https://bldrdojo.com,https://www.bldrdojo.com
  ```

#### 5. OAuth Credentials (if using)
- [ ] `GOOGLE_CLIENT_ID` - From Google Cloud Console
- [ ] `GOOGLE_CLIENT_SECRET` - From Google Cloud Console
- [ ] `GITHUB_CLIENT_ID` - From GitHub Developer Settings
- [ ] `GITHUB_CLIENT_SECRET` - From GitHub Developer Settings

---

## 🔍 Settings.py Verification

### Confirm All Hardcoded Values Are Removed

Run this check:
```bash
cd /home/ubuntu/monorepo/data-backend
grep -n "localhost\|127.0.0.1\|django-insecure\|DEBUG = True" config/settings.py
```

**Expected Result:** No matches (or only in comments/defaults)

### Key Settings to Verify

1. **SECRET_KEY** - Uses `os.environ.get('DJANGO_SECRET_KEY', ...)`
2. **DEBUG** - Uses `os.environ.get('DJANGO_DEBUG', 'True') == 'True'`
3. **ALLOWED_HOSTS** - Parses from `DJANGO_ALLOWED_HOSTS` env var
4. **CORS_ALLOWED_ORIGINS** - Parses from `CORS_ALLOWED_ORIGINS` env var
5. **Database URLs** - All use environment variables
6. **JWT Settings** - Uses `JWT_SECRET_KEY` from env

---

## 🌐 Frontend URL Configuration

### Verify No Hardcoded localhost URLs

Run this check:
```bash
cd /home/ubuntu/monorepo/data-backend/frontend/src
grep -r "localhost:8000\|127.0.0.1:8000" --include="*.jsx" --include="*.js" | grep -v "test\|apiUrl.js"
```

**Expected Result:** No matches (except in `apiUrl.js` and test files)

### Files That Should Use `getApiBaseUrl()`

- ✅ `src/services/api.js` - API fetch wrapper
- ✅ `src/contexts/AuthContext.jsx` - Authentication
- ✅ `src/components/GoogleCallback.jsx` - OAuth callback
- ✅ `src/components/GoogleLoginButton.jsx` - OAuth initiation
- ✅ All other components use `api.fetch()` wrapper

### How `getApiBaseUrl()` Works

```javascript
// Development (localhost:5173)
getApiBaseUrl() → 'http://localhost:8000'

// Production (bldrdojo.com)
getApiBaseUrl() → '' (empty string, uses nginx proxy)
```

---

## 🐳 Docker Compose Verification

### Environment Variables in docker-compose.yml

Check that docker-compose.yml passes environment variables correctly:

```yaml
backend:
  environment:
    - DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
    - DJANGO_DEBUG=${DJANGO_DEBUG}
    - DJANGO_ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS}
    - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    - REDIS_PASSWORD=${REDIS_PASSWORD}
    - MEILI_MASTER_KEY=${MEILI_MASTER_KEY}
    - NEO4J_PASSWORD=${NEO4J_PASSWORD}
    - MEILISEARCH_URL=${MEILISEARCH_URL}
    - NEO4J_URI=${NEO4J_URI}
    - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    - CORS_ALLOWED_ORIGINS=${CORS_ALLOWED_ORIGINS}
```

### Services Configuration

- [ ] **Neo4j** - Does NOT have `env_file: - .env` (causes config errors)
- [ ] **MeiliSearch** - Has `MEILI_MASTER_KEY` set correctly
- [ ] **Backend** - Has all required environment variables
- [ ] **Frontend** - Built with production settings

---

## 🔐 SSL/TLS Configuration

### Nginx SSL Settings

In `frontend/default.conf`:

- [ ] SSL certificates are in `/etc/nginx/ssl/`
- [ ] HTTP redirects to HTTPS
- [ ] Strong SSL ciphers configured
- [ ] HSTS headers enabled

### Let's Encrypt Certificates

```bash
# Verify certificates exist
ls -la /home/ubuntu/monorepo/data-backend/ssl/

# Should contain:
# - fullchain.pem
# - privkey.pem
```

### Certificate Renewal

```bash
# Test renewal
sudo certbot renew --dry-run

# Setup auto-renewal (cron)
sudo crontab -e
# Add: 0 3 * * * certbot renew --quiet --post-hook "docker compose -f /home/ubuntu/monorepo/data-backend/docker-compose.yml restart frontend"
```

---

## 🧪 Testing Environment Variables

### Test Backend Configuration

```bash
cd /home/ubuntu/monorepo/data-backend

# Check if environment variables are loaded
docker compose exec backend python -c "
import os
print('SECRET_KEY:', os.environ.get('DJANGO_SECRET_KEY', 'NOT SET')[:10] + '...')
print('DEBUG:', os.environ.get('DJANGO_DEBUG', 'NOT SET'))
print('ALLOWED_HOSTS:', os.environ.get('DJANGO_ALLOWED_HOSTS', 'NOT SET'))
print('POSTGRES_PASSWORD:', '***' if os.environ.get('POSTGRES_PASSWORD') else 'NOT SET')
print('MEILI_MASTER_KEY:', '***' if os.environ.get('MEILI_MASTER_KEY') else 'NOT SET')
print('NEO4J_PASSWORD:', '***' if os.environ.get('NEO4J_PASSWORD') else 'NOT SET')
print('JWT_SECRET_KEY:', '***' if os.environ.get('JWT_SECRET_KEY') else 'NOT SET')
print('CORS_ALLOWED_ORIGINS:', os.environ.get('CORS_ALLOWED_ORIGINS', 'NOT SET'))
"
```

### Test Database Connections

```bash
# Test PostgreSQL
docker compose exec backend python manage.py dbshell -c "\conninfo"

# Test Redis
docker compose exec backend python -c "
import redis
from django.conf import settings
r = redis.from_url(settings.REDIS_URL if hasattr(settings, 'REDIS_URL') else 'redis://redis:6379')
r.ping()
print('Redis: OK')
"

# Test MeiliSearch
docker compose exec backend python -c "
import meilisearch
from django.conf import settings
client = meilisearch.Client(settings.MEILISEARCH_URL, settings.MEILI_MASTER_KEY)
print('MeiliSearch:', client.health())
"

# Test Neo4j
docker compose exec backend python -c "
from neo4j import GraphDatabase
from django.conf import settings
driver = GraphDatabase.driver(settings.NEO4J_URI, auth=settings.NEO4J_AUTH)
driver.verify_connectivity()
print('Neo4j: OK')
driver.close()
"
```

---

## 🚀 Deployment Checklist

### Before Deploying

1. [ ] All `.env` variables are set with production values
2. [ ] `DJANGO_DEBUG=False`
3. [ ] Strong passwords for all services (20+ chars)
4. [ ] SSL certificates are valid and in place
5. [ ] Frontend is built with `npm run build`
6. [ ] No hardcoded localhost URLs in code
7. [ ] Firewall rules allow only ports 80, 443, 22

### After Deploying

1. [ ] Test user registration: https://bldrdojo.com/register
2. [ ] Test user login: https://bldrdojo.com/login
3. [ ] Test entity list loads: https://bldrdojo.com/
4. [ ] Test entity creation, editing, deletion
5. [ ] Test search functionality
6. [ ] Test image uploads
7. [ ] Test relationship management
8. [ ] Check browser console for errors
9. [ ] Check backend logs: `docker compose logs backend`
10. [ ] Verify HTTPS is working (no mixed content warnings)

### Monitoring

```bash
# Check all services are running
docker compose ps

# Check logs
docker compose logs -f --tail=100

# Check resource usage
docker stats

# Check disk space
df -h
```

---

## 🔧 Quick Fixes for Common Issues

### Issue: "DisallowedHost" Error

**Fix:** Update `DJANGO_ALLOWED_HOSTS` in `.env`:
```bash
DJANGO_ALLOWED_HOSTS=bldrdojo.com,www.bldrdojo.com
```

### Issue: CORS Errors in Browser

**Fix:** Update `CORS_ALLOWED_ORIGINS` in `.env`:
```bash
CORS_ALLOWED_ORIGINS=https://bldrdojo.com,https://www.bldrdojo.com
```

### Issue: Frontend Shows Old Cached Version

**Fix:** Clear browser cache or force reload (Ctrl+Shift+R)

Also ensure nginx sends no-cache headers for HTML:
```nginx
location / {
    try_files $uri $uri/ /index.html;
    add_header Cache-Control "no-store, no-cache, must-revalidate";
}
```

### Issue: API Calls Return 401 Unauthorized

**Fix:** Check JWT configuration and ensure tokens are being sent:
1. Open browser DevTools → Application → Local Storage
2. Verify `access_token` exists
3. Check Network tab → Request Headers → Authorization

### Issue: "Failed to init MeiliSearch"

**Fix:** Ensure `MEILI_MASTER_KEY` is at least 16 characters:
```bash
# Generate a new key
openssl rand -base64 24
```

---

## 📝 Generate Strong Secrets

Use these commands to generate secure secrets:

```bash
# Django Secret Key (50+ chars)
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# JWT Secret Key (50+ chars)
openssl rand -base64 50 | tr -d '\n' && echo

# Database Passwords (24 chars)
openssl rand -base64 24 | tr -d '\n' && echo

# MeiliSearch Master Key (32 chars)
openssl rand -base64 32 | tr -d '\n' && echo
```

---

## 🎯 Production Readiness Score

Run all checks above and count:

- **Critical (Must Fix):** SECRET_KEY, DEBUG, passwords, ALLOWED_HOSTS
- **Important (Should Fix):** JWT config, CORS, SSL
- **Nice to Have:** Monitoring, backups, logging

**Target:** 100% of Critical and Important items checked ✅

---

## 📚 Additional Resources

- [Django Deployment Checklist](https://docs.djangoproject.com/en/stable/howto/deployment/checklist/)
- [OWASP Security Guidelines](https://owasp.org/www-project-top-ten/)
- [Docker Security Best Practices](https://docs.docker.com/develop/security-best-practices/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)

---

**Last Updated:** 2026-02-03
**Version:** 1.0
