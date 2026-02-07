# Environment Configuration Summary

## ✅ Configuration Status

### Backend (Django) - **FULLY PARAMETERIZED** ✅

All configuration values are now read from environment variables with sensible defaults for development.

#### Key Settings Parameterized:

1. **Core Django Settings**
   - `SECRET_KEY` → `DJANGO_SECRET_KEY` env var
   - `DEBUG` → `DJANGO_DEBUG` env var (defaults to True for dev)
   - `ALLOWED_HOSTS` → `DJANGO_ALLOWED_HOSTS` env var (comma-separated)

2. **Database Configuration**
   - PostgreSQL password → `POSTGRES_PASSWORD` env var
   - Redis password → `REDIS_PASSWORD` env var
   - Neo4j password → `NEO4J_PASSWORD` env var
   - MeiliSearch key → `MEILI_MASTER_KEY` env var

3. **Service URLs**
   - MeiliSearch → `MEILISEARCH_URL` env var
   - Neo4j → `NEO4J_URI` env var
   - Vector Service → `VECTOR_SERVICE_URL` env var

4. **JWT Configuration**
   - JWT secret → `JWT_SECRET_KEY` env var
   - Access token lifetime → `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` env var
   - Refresh token lifetime → `JWT_REFRESH_TOKEN_LIFETIME_DAYS` env var

5. **CORS Configuration**
   - Allowed origins → `CORS_ALLOWED_ORIGINS` env var (comma-separated)

### Frontend (React) - **FULLY PARAMETERIZED** ✅

All API URLs are now dynamically determined based on the environment.

#### How It Works:

**Development Mode** (localhost:5173):
```javascript
getApiBaseUrl() → 'http://localhost:8000'
getMediaUrl('/media/photo.jpg') → 'http://localhost:8000/media/photo.jpg'
```

**Production Mode** (bldrdojo.com):
```javascript
getApiBaseUrl() → '' (empty string, uses nginx proxy)
getMediaUrl('/media/photo.jpg') → '/media/photo.jpg' (served by nginx)
```

#### Files Using Environment-Aware URLs:

- ✅ `src/services/api.js` - Main API wrapper with auto-auth
- ✅ `src/utils/apiUrl.js` - URL helper functions
- ✅ `src/contexts/AuthContext.jsx` - Authentication
- ✅ `src/components/GoogleCallback.jsx` - OAuth callback
- ✅ `src/components/GoogleLoginButton.jsx` - OAuth initiation
- ✅ `src/components/EntityList.jsx` - Media URLs
- ✅ `src/components/EntityDetail.jsx` - Media URLs
- ✅ `src/components/RichTextEditor.jsx` - Image uploads

---

## 🔄 How to Switch Between Environments

### Local Development

**Backend:**
```bash
# Use .env.local or no .env file (uses defaults)
docker compose up -d
```

**Frontend:**
```bash
cd frontend
npm run dev
# Runs on localhost:5173, automatically connects to localhost:8000
```

### Production Deployment

**1. Configure `.env` file:**
```bash
cd /home/ubuntu/monorepo/data-backend
cp .env.production.template .env
# Edit .env with production values
nano .env
```

**2. Set production values:**
```bash
DJANGO_SECRET_KEY=<50+ char random string>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=bldrdojo.com,www.bldrdojo.com
CORS_ALLOWED_ORIGINS=https://bldrdojo.com,https://www.bldrdojo.com
# ... etc (see .env.production.template)
```

**3. Build frontend:**
```bash
cd frontend
npm run build
# Creates dist/ folder with production build
```

**4. Deploy:**
```bash
docker compose build
docker compose up -d
```

**Frontend automatically detects production:**
- Hostname is NOT localhost → uses empty API base URL
- Port is NOT 5173 → uses empty API base URL
- Nginx proxies `/api/` to backend
- Nginx serves `/media/` static files

---

## 🧪 Testing Configuration

### Test Backend Environment Variables

```bash
cd /home/ubuntu/monorepo/data-backend

docker compose exec backend python << 'EOF'
import os
from django.conf import settings

print('SECRET_KEY:', settings.SECRET_KEY[:20] + '...')
print('DEBUG:', settings.DEBUG)
print('ALLOWED_HOSTS:', settings.ALLOWED_HOSTS)
print('CORS_ALLOWED_ORIGINS:', settings.CORS_ALLOWED_ORIGINS)
print('MEILISEARCH_URL:', settings.MEILISEARCH_URL)
print('NEO4J_URI:', settings.NEO4J_URI)

# Check passwords are set
print('POSTGRES_PASSWORD:', '***' if os.environ.get('POSTGRES_PASSWORD') else 'NOT SET')
print('MEILI_MASTER_KEY:', '***' if os.environ.get('MEILI_MASTER_KEY') else 'NOT SET')
print('NEO4J_PASSWORD:', '***' if os.environ.get('NEO4J_PASSWORD') else 'NOT SET')
EOF
```

### Test Frontend URL Detection

**In Browser Console (Development):**
```javascript
// On localhost:5173
import { getApiBaseUrl } from './utils/apiUrl';
console.log('API Base:', getApiBaseUrl()); // Should be 'http://localhost:8000'
```

**In Browser Console (Production):**
```javascript
// On bldrdojo.com
import { getApiBaseUrl } from './utils/apiUrl';
console.log('API Base:', getApiBaseUrl()); // Should be '' (empty)
```

### Test API Calls Work

```bash
# Development
curl http://localhost:5173/api/health/

# Production
curl https://bldrdojo.com/api/health/
```

---

## 📋 Environment Variables Reference

### Required for Production

| Variable | Description | Example |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key (50+ chars) | `your-random-50-char-string` |
| `DJANGO_DEBUG` | Debug mode (False for prod) | `False` |
| `DJANGO_ALLOWED_HOSTS` | Allowed domains | `bldrdojo.com,www.bldrdojo.com` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `secure-password-20-chars` |
| `REDIS_PASSWORD` | Redis password | `secure-password-20-chars` |
| `MEILI_MASTER_KEY` | MeiliSearch key (16+ chars) | `secure-key-16-chars-min` |
| `NEO4J_PASSWORD` | Neo4j password | `secure-password-20-chars` |
| `JWT_SECRET_KEY` | JWT signing key (50+ chars) | `your-random-50-char-string` |
| `CORS_ALLOWED_ORIGINS` | CORS allowed origins | `https://bldrdojo.com,https://www.bldrdojo.com` |

### Optional (with defaults)

| Variable | Default | Description |
|----------|---------|-------------|
| `MEILISEARCH_URL` | `http://meilisearch:7700` | MeiliSearch URL |
| `NEO4J_URI` | `bolt://neo4j:7687` | Neo4j connection URI |
| `VECTOR_SERVICE_URL` | `http://vector-service:5000` | Vector service URL |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | `60` | JWT access token lifetime |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | `7` | JWT refresh token lifetime |

---

## 🔒 Security Best Practices

### ✅ What We've Done

1. **No Hardcoded Secrets** - All secrets in `.env` file
2. **Environment-Aware URLs** - Frontend adapts to dev/prod automatically
3. **Secure Defaults** - Production defaults are secure
4. **JWT Separation** - Separate JWT secret from Django secret
5. **CORS Protection** - Only allowed origins can access API
6. **Password Protection** - All services require authentication

### ⚠️ What You Must Do

1. **Generate Strong Secrets** - Use the commands in `PRODUCTION_SECURITY_CHECKLIST.md`
2. **Set DEBUG=False** - In production `.env`
3. **Configure SSL** - Use Let's Encrypt certificates
4. **Restrict CORS** - Only your production domain(s)
5. **Backup `.env`** - Store securely, never commit to git
6. **Monitor Logs** - Check for security issues regularly

---

## 🚀 Quick Start Commands

### Development

```bash
# Backend
cd /home/ubuntu/monorepo/data-backend
docker compose up -d

# Frontend
cd frontend
npm run dev

# Visit: http://localhost:5173
```

### Production

```bash
# 1. Configure .env
cp .env.production.template .env
nano .env  # Fill in production values

# 2. Build frontend
cd frontend
npm run build

# 3. Deploy
cd ..
docker compose build
docker compose up -d

# Visit: https://bldrdojo.com
```

---

## 📝 Verification Checklist

Before deploying to production, verify:

- [ ] All `.env` variables are set with production values
- [ ] `DJANGO_DEBUG=False` in `.env`
- [ ] Strong passwords (20+ chars) for all services
- [ ] `CORS_ALLOWED_ORIGINS` set to production domain only
- [ ] Frontend built with `npm run build`
- [ ] SSL certificates in place
- [ ] No hardcoded localhost URLs in code
- [ ] Test registration, login, and basic functionality

Run the full checklist: `cat PRODUCTION_SECURITY_CHECKLIST.md`

---

## 🆘 Troubleshooting

### Issue: API calls fail with CORS error

**Cause:** `CORS_ALLOWED_ORIGINS` not set correctly

**Fix:**
```bash
# In .env
CORS_ALLOWED_ORIGINS=https://bldrdojo.com,https://www.bldrdojo.com
```

### Issue: "DisallowedHost" error

**Cause:** `DJANGO_ALLOWED_HOSTS` not set correctly

**Fix:**
```bash
# In .env
DJANGO_ALLOWED_HOSTS=bldrdojo.com,www.bldrdojo.com
```

### Issue: Frontend shows 404 for API calls

**Cause:** Nginx not proxying correctly or frontend using wrong URL

**Check:**
1. Nginx config has `/api/` proxy to backend
2. Frontend `getApiBaseUrl()` returns empty string in production
3. Browser is accessing `https://` not `http://`

### Issue: Images not loading

**Cause:** Media URLs not resolving correctly

**Check:**
1. Nginx serves `/media/` from backend mediafiles
2. `getMediaUrl()` is being used in components
3. Backend `MEDIA_ROOT` is set correctly

---

**Last Updated:** 2026-02-03
**Status:** ✅ Fully Parameterized and Production-Ready
