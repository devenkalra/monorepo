# Staging Environment Setup Guide

## Overview

A staging environment is a production-like environment used for testing changes before deploying to production. It should mirror production as closely as possible while being isolated and safe to break.

**Purpose:**
- Test new features before production
- Verify deployment procedures
- Test database migrations
- Validate integrations
- Performance testing
- User acceptance testing (UAT)

---

## Architecture

### Staging vs Production

| Aspect | Staging | Production |
|--------|---------|------------|
| **Domain** | staging.yourdomain.com | app.yourdomain.com |
| **Server** | Smaller instance (2GB RAM) | Full instance (8GB RAM) |
| **Data** | Anonymized production copy | Real user data |
| **SSL** | Yes (Let's Encrypt) | Yes (Let's Encrypt) |
| **Monitoring** | Optional | Required |
| **Backups** | Weekly | Daily |
| **Purpose** | Testing | Live users |

---

## Option 1: Staging on Same Server (Recommended for Small Teams)

This approach runs staging on the same server as production using different ports and domains.

### Advantages
- Lower cost (one server)
- Easier to manage
- Shares resources efficiently

### Disadvantages
- Staging issues could affect production
- Limited isolation
- Resource contention

### Setup Steps

#### Step 1: Update DNS

Add DNS A record for staging subdomain:
```
staging.yourdomain.com → your.server.ip
```

#### Step 2: Create Staging Directory

```bash
# SSH into your server
ssh user@your.server.ip

# Create staging directory
sudo mkdir -p /opt/data-backend-staging
sudo chown $USER:$USER /opt/data-backend-staging
cd /opt/data-backend-staging

# Clone repository
git clone <your-repo-url> .
# Or copy from production
cp -r /opt/data-backend/* .
```

#### Step 3: Create Staging Environment File

```bash
cd /opt/data-backend-staging
cp .env.production .env.staging
nano .env.staging
```

**Edit `.env.staging`:**

```bash
# Django Settings
DEBUG=False
SECRET_KEY=different-secret-key-for-staging
ALLOWED_HOSTS=staging.yourdomain.com
DJANGO_SETTINGS_MODULE=config.settings

# Database (different database!)
POSTGRES_DB=staging_db
POSTGRES_USER=staging_user
POSTGRES_PASSWORD=staging-password-different-from-prod
DATABASE_URL=postgresql://staging_user:staging-password@db-staging:5432/staging_db

# Redis (different instance)
REDIS_URL=redis://redis-staging:6379/0

# Neo4j (different instance)
NEO4J_URI=bolt://neo4j-staging:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=staging-neo4j-password

# MeiliSearch (different instance)
MEILISEARCH_URL=http://meilisearch-staging:7700
MEILI_MASTER_KEY=staging-meili-key

# Security
CORS_ALLOWED_ORIGINS=https://staging.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://staging.yourdomain.com

# Email (use test email service)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
# Or use Mailtrap for testing
# EMAIL_HOST=smtp.mailtrap.io
# EMAIL_PORT=2525
# EMAIL_HOST_USER=your-mailtrap-user
# EMAIL_HOST_PASSWORD=your-mailtrap-password

# Environment indicator
ENVIRONMENT=staging
```

#### Step 4: Create Staging Docker Compose

```bash
nano /opt/data-backend-staging/docker-compose.staging.yml
```

```yaml
version: '3.8'

services:
  db-staging:
    image: postgres:15-alpine
    container_name: staging-db
    restart: always
    volumes:
      - postgres_staging_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    ports:
      - "5433:5432"  # Different external port
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - staging

  redis-staging:
    image: redis:7-alpine
    container_name: staging-redis
    restart: always
    volumes:
      - redis_staging_data:/data
    command: redis-server --appendonly yes
    ports:
      - "6381:6379"  # Different external port
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - staging

  neo4j-staging:
    image: neo4j:5-community
    container_name: staging-neo4j
    restart: always
    volumes:
      - neo4j_staging_data:/data
      - neo4j_staging_logs:/logs
    environment:
      - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}
      - NEO4J_PLUGINS=["apoc"]
    ports:
      - "7475:7474"  # Different external port
      - "7688:7687"  # Different external port
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p ${NEO4J_PASSWORD} 'RETURN 1'"]
      interval: 30s
      timeout: 10s
      retries: 5
    networks:
      - staging

  meilisearch-staging:
    image: getmeili/meilisearch:v1.5
    container_name: staging-meilisearch
    restart: always
    volumes:
      - meilisearch_staging_data:/meili_data
    environment:
      - MEILI_MASTER_KEY=${MEILI_MASTER_KEY}
      - MEILI_ENV=production
    ports:
      - "7702:7700"  # Different external port
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:7700/health"]
      interval: 30s
      timeout: 10s
      retries: 5
    networks:
      - staging

  backend-staging:
    build:
      context: .
      dockerfile: Dockerfile.production
    container_name: staging-backend
    restart: always
    volumes:
      - ./media-staging:/app/media
      - ./staticfiles-staging:/app/staticfiles
    env_file:
      - .env.staging
    depends_on:
      db-staging:
        condition: service_healthy
      redis-staging:
        condition: service_healthy
      neo4j-staging:
        condition: service_healthy
      meilisearch-staging:
        condition: service_healthy
    command: >
      sh -c "
        python manage.py collectstatic --noinput &&
        python manage.py migrate --noinput &&
        gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120
      "
    ports:
      - "8001:8000"  # Different external port
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - staging

  frontend-staging:
    build:
      context: ./frontend
      dockerfile: Dockerfile.production
      args:
        - VITE_API_URL=https://staging.yourdomain.com/api
    container_name: staging-frontend
    restart: always
    ports:
      - "3001:80"  # Different external port
    networks:
      - staging

volumes:
  postgres_staging_data:
  redis_staging_data:
  neo4j_staging_data:
  neo4j_staging_logs:
  meilisearch_staging_data:

networks:
  staging:
    driver: bridge
```

#### Step 5: Configure Nginx for Staging

```bash
sudo nano /etc/nginx/sites-available/data-backend-staging
```

```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name staging.yourdomain.com;
    
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS Server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name staging.yourdomain.com;

    # SSL certificates (will be added by certbot)
    # ssl_certificate /etc/letsencrypt/live/staging.yourdomain.com/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/staging.yourdomain.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header X-Robots-Tag "noindex, nofollow" always;  # Prevent search indexing
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # Staging banner (optional)
    add_header X-Environment "staging" always;

    client_max_body_size 100M;

    access_log /var/log/nginx/staging-access.log;
    error_log /var/log/nginx/staging-error.log;

    # Frontend
    location / {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:8001/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # Django Admin
    location /admin/ {
        proxy_pass http://localhost:8001/admin/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Static files
    location /static/ {
        alias /opt/data-backend-staging/staticfiles-staging/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Media files
    location /media/ {
        alias /opt/data-backend-staging/media-staging/;
        expires 1y;
        add_header Cache-Control "public";
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/data-backend-staging /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

#### Step 6: Get SSL Certificate for Staging

```bash
sudo certbot --nginx -d staging.yourdomain.com
```

#### Step 7: Start Staging Environment

```bash
cd /opt/data-backend-staging

# Build and start
docker-compose -f docker-compose.staging.yml build
docker-compose -f docker-compose.staging.yml up -d

# Check status
docker-compose -f docker-compose.staging.yml ps

# Create superuser
docker-compose -f docker-compose.staging.yml exec backend-staging python manage.py createsuperuser
```

#### Step 8: Copy Production Data to Staging (Optional)

```bash
# Backup production database
cd /opt/data-backend
./scripts/backup.sh staging-seed

# Copy to staging
cd /opt/data-backend-staging

# Restore database only
./scripts/restore.sh staging-seed --db-only

# Anonymize sensitive data
docker-compose -f docker-compose.staging.yml exec backend-staging python manage.py shell << EOF
from django.contrib.auth import get_user_model
User = get_user_model()

# Anonymize user emails
for user in User.objects.all():
    user.email = f"user{user.id}@staging.example.com"
    user.save()

print("Data anonymized")
EOF
```

---

## Option 2: Staging on Separate Server (Recommended for Production)

This approach uses a completely separate server for staging.

### Advantages
- Complete isolation from production
- Can test infrastructure changes
- No resource contention
- More realistic production simulation

### Disadvantages
- Higher cost (two servers)
- More maintenance overhead
- Need to sync data between environments

### Setup Steps

#### Step 1: Provision Staging Server

```bash
# Provision a smaller server (2-4GB RAM is usually sufficient)
# Ubuntu 22.04 LTS
# Static IP address
```

#### Step 2: Setup DNS

```
staging.yourdomain.com → staging.server.ip
```

#### Step 3: Follow Production Deployment

On the staging server, follow the production deployment guide with these changes:

1. **Use staging domain:** `staging.yourdomain.com`
2. **Use `.env.staging`** instead of `.env.production`
3. **Use `docker-compose.staging.yml`** (same as production compose but different container names)
4. **Configure Nginx** for staging domain
5. **Get SSL certificate** for staging domain

```bash
# On staging server
ssh user@staging.server.ip

# Follow PRODUCTION_DEPLOYMENT.md but:
# - Replace all instances of "production" with "staging"
# - Use staging domain
# - Use smaller resource limits (2 workers instead of 4)
```

---

## Option 3: Staging with Docker on Development Machine

For individual testing before pushing to staging server.

```bash
# On your local machine
cd /home/ubuntu/monorepo/data-backend

# Create staging compose
cp docker-compose.local.yml docker-compose.staging-local.yml

# Edit to use production-like settings
nano docker-compose.staging-local.yml

# Start
docker-compose -f docker-compose.staging-local.yml up
```

---

## Staging Workflow

### 1. Development → Staging → Production

```mermaid
Development (local) 
    ↓ (git push to staging branch)
Staging (test)
    ↓ (merge to main, deploy)
Production (live)
```

### 2. Typical Workflow

```bash
# 1. Develop feature locally
git checkout -b feature/new-feature
# ... make changes ...
git commit -m "Add new feature"

# 2. Push to staging branch
git push origin feature/new-feature

# 3. Deploy to staging
ssh user@staging.server.ip
cd /opt/data-backend-staging
git pull origin feature/new-feature
docker-compose -f docker-compose.staging.yml build
docker-compose -f docker-compose.staging.yml up -d

# 4. Test on staging
# Visit https://staging.yourdomain.com
# Run tests, verify functionality

# 5. If tests pass, merge to main
git checkout main
git merge feature/new-feature
git push origin main

# 6. Deploy to production
ssh user@production.server.ip
cd /opt/data-backend
./scripts/deploy_production.sh
```

---

## Data Management

### Syncing Production Data to Staging

```bash
# On production server
cd /opt/data-backend
./scripts/backup.sh staging-sync

# Copy to staging
scp -r ~/backups/data-backend/staging-sync \
  user@staging.server.ip:~/backups/data-backend/

# On staging server
cd /opt/data-backend-staging
./scripts/restore.sh staging-sync

# Anonymize data
docker-compose -f docker-compose.staging.yml exec backend-staging \
  python manage.py anonymize_data
```

### Create Anonymization Script

```bash
nano /opt/data-backend-staging/people/management/commands/anonymize_data.py
```

```python
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from people.models import Person, Note

User = get_user_model()

class Command(BaseCommand):
    help = 'Anonymize sensitive data for staging'

    def handle(self, *args, **options):
        # Anonymize users
        for user in User.objects.all():
            user.email = f"user{user.id}@staging.example.com"
            user.set_password('staging123')
            user.save()
        
        # Anonymize people
        for person in Person.objects.all():
            if person.email:
                person.email = f"person{person.id}@staging.example.com"
            if person.phone:
                person.phone = "555-0100"
            person.save()
        
        # Anonymize notes (optional)
        for note in Note.objects.all():
            if 'confidential' in note.description.lower():
                note.description = "[REDACTED]"
                note.save()
        
        self.stdout.write(self.style.SUCCESS('Data anonymized successfully'))
```

```bash
# Run anonymization
docker-compose -f docker-compose.staging.yml exec backend-staging \
  python manage.py anonymize_data
```

---

## Visual Indicators

### Add Staging Banner to Frontend

```javascript
// frontend/src/components/StagingBanner.jsx
export function StagingBanner() {
  if (import.meta.env.PROD && window.location.hostname.includes('staging')) {
    return (
      <div className="bg-yellow-500 text-black px-4 py-2 text-center font-bold">
        ⚠️ STAGING ENVIRONMENT - Test data only
      </div>
    );
  }
  return null;
}

// Add to App.jsx
import { StagingBanner } from './components/StagingBanner';

function App() {
  return (
    <>
      <StagingBanner />
      {/* rest of app */}
    </>
  );
}
```

---

## Testing Checklist

Before promoting staging to production:

- [ ] All automated tests pass
- [ ] Manual testing completed
- [ ] Database migrations tested
- [ ] Performance acceptable
- [ ] Security scan passed
- [ ] Backup/restore tested
- [ ] Error monitoring working
- [ ] Load testing (if applicable)
- [ ] User acceptance testing
- [ ] Documentation updated

---

## Maintenance

### Regular Tasks

**Weekly:**
- [ ] Sync production data to staging
- [ ] Test backup/restore procedure
- [ ] Review staging logs
- [ ] Update dependencies

**Monthly:**
- [ ] Full security scan
- [ ] Performance testing
- [ ] Disaster recovery drill

---

## Automation with CI/CD

### GitHub Actions Example

```yaml
# .github/workflows/deploy-staging.yml
name: Deploy to Staging

on:
  push:
    branches: [ staging ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Deploy to Staging
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.STAGING_HOST }}
          username: ${{ secrets.STAGING_USER }}
          key: ${{ secrets.STAGING_SSH_KEY }}
          script: |
            cd /opt/data-backend-staging
            git pull origin staging
            docker-compose -f docker-compose.staging.yml build
            docker-compose -f docker-compose.staging.yml up -d
            docker-compose -f docker-compose.staging.yml exec -T backend-staging python manage.py migrate
```

---

## Troubleshooting

### Staging and Production Interfering

**Problem:** Staging affects production or vice versa

**Solution:**
- Ensure different ports
- Different database names
- Different Docker networks
- Different container names

### SSL Certificate Issues

**Problem:** Can't get SSL for staging subdomain

**Solution:**
```bash
# Make sure DNS is propagated
nslookup staging.yourdomain.com

# Try manual certificate
sudo certbot certonly --nginx -d staging.yourdomain.com
```

### Data Sync Issues

**Problem:** Can't restore production backup to staging

**Solution:**
```bash
# Check database versions match
docker-compose exec db-staging psql --version

# Try database-only restore
./scripts/restore.sh backup_name --db-only
```

---

## Cost Optimization

### Same Server Staging
- **Cost:** $0 additional (shares production server)
- **Best for:** Small teams, low traffic

### Separate Server Staging
- **Cost:** ~$10-20/month (smaller instance)
- **Best for:** Production apps, teams

### On-Demand Staging
- **Cost:** Spin up only when needed
- **Best for:** Infrequent deployments

---

## Summary

### Quick Setup (Same Server)

```bash
# 1. Create staging directory
sudo mkdir -p /opt/data-backend-staging
cd /opt/data-backend-staging
git clone <repo> .

# 2. Configure environment
cp .env.production .env.staging
# Edit .env.staging with different passwords/ports

# 3. Create docker-compose.staging.yml
# Use different ports and container names

# 4. Configure Nginx
sudo nano /etc/nginx/sites-available/data-backend-staging
sudo ln -s /etc/nginx/sites-available/data-backend-staging /etc/nginx/sites-enabled/

# 5. Get SSL
sudo certbot --nginx -d staging.yourdomain.com

# 6. Start
docker-compose -f docker-compose.staging.yml up -d
```

**Total Time:** 1-2 hours

---

## Resources

- **Production Deployment:** [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md)
- **Backup Scripts:** `scripts/backup.sh`, `scripts/restore.sh`
- **Testing Guide:** [TESTING.md](TESTING.md)

---

**Last Updated:** 2026-02-01
