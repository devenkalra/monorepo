# Bldrdojo.com - Production Deployment Guide

Complete guide for deploying the Entity Management System (backend + frontend) to production using Docker Compose.

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Initial Setup](#initial-setup)
4. [SSL Certificate Setup](#ssl-certificate-setup)
5. [Environment Configuration](#environment-configuration)
6. [Building and Deploying](#building-and-deploying)
7. [Database Management](#database-management)
8. [Monitoring and Maintenance](#monitoring-and-maintenance)
9. [Troubleshooting](#troubleshooting)
10. [Backup and Recovery](#backup-and-recovery)

---

## Architecture Overview

### Services

```
┌─────────────────────────────────────────────────────────────┐
│                     bldrdojo.com (Port 80/443)              │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Nginx (Frontend)                                     │  │
│  │  - Serves React SPA                                   │  │
│  │  - Proxies /api/ to backend                          │  │
│  │  - SSL termination                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                          │                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Django Backend (Port 8000)                          │  │
│  │  - REST API                                           │  │
│  │  - Admin interface                                    │  │
│  │  - Authentication                                     │  │
│  └──────────────────────────────────────────────────────┘  │
│           │           │           │           │             │
│  ┌────────┴─────┬─────┴─────┬─────┴─────┬────┴─────────┐  │
│  │ PostgreSQL   │ Redis     │MeiliSearch│ Neo4j        │  │
│  │ (Database)   │ (Cache)   │ (Search)  │ (Graph DB)   │  │
│  └──────────────┴───────────┴───────────┴──────────────┘  │
│                          │                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Vector Service (Flask + ChromaDB)                   │  │
│  │  - Semantic search                                    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow
1. User accesses `https://bldrdojo.com`
2. Nginx serves React frontend
3. API requests go to `/api/*` → proxied to Django backend
4. Backend queries PostgreSQL, Redis, MeiliSearch, Neo4j, and Vector Service
5. Responses flow back through the chain

---

## Prerequisites

### Server Requirements
- **OS**: Ubuntu 20.04+ / Debian 11+ / RHEL 8+
- **CPU**: 2+ cores (4+ recommended)
- **RAM**: 4GB minimum (8GB+ recommended)
- **Disk**: 50GB+ SSD storage
- **Network**: Public IP address with ports 80/443 open

### Software Requirements
```bash
# Docker
Docker version 20.10+
Docker Compose version 2.0+

# Domain
- bldrdojo.com pointing to server IP
- www.bldrdojo.com pointing to server IP (optional)
```

### Install Docker and Docker Compose

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version
```

---

## Initial Setup

### 1. Clone Repository

```bash
cd /opt
sudo mkdir bldrdojo
sudo chown $USER:$USER bldrdojo
cd bldrdojo

# Clone or copy your repository here
# For this guide, assume files are in /opt/bldrdojo/
```

### 2. Create Directory Structure

```bash
cd /opt/bldrdojo

# Create required directories
mkdir -p ssl backups logs logs/nginx

# Set permissions
chmod 700 ssl
chmod 755 backups logs
```

---

## SSL Certificate Setup

### Option 1: Let's Encrypt (Recommended for Production)

```bash
# Install certbot
sudo apt-get install certbot

# Stop any running services on port 80
docker-compose down

# Obtain certificate
sudo certbot certonly --standalone \
  -d bldrdojo.com \
  -d www.bldrdojo.com \
  --email admin@bldrdojo.com \
  --agree-tos \
  --non-interactive

# Copy certificates to project directory
sudo cp /etc/letsencrypt/live/bldrdojo.com/fullchain.pem ssl/
sudo cp /etc/letsencrypt/live/bldrdojo.com/privkey.pem ssl/
sudo chown $USER:$USER ssl/*.pem
sudo chmod 600 ssl/*.pem

# Set up auto-renewal
sudo crontab -e
# Add this line:
# 0 3 * * * certbot renew --quiet && cp /etc/letsencrypt/live/bldrdojo.com/*.pem /opt/bldrdojo/ssl/ && docker-compose -f /opt/bldrdojo/docker-compose.yml restart frontend
```

### Option 2: Self-Signed Certificate (Development/Testing Only)

```bash
cd ssl

# Generate self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout privkey.pem \
  -out fullchain.pem \
  -subj "/C=US/ST=State/L=City/O=Organization/OU=IT/CN=bldrdojo.com"

chmod 600 *.pem
```

---

## Environment Configuration

### 1. Create Environment File

```bash
cd /opt/bldrdojo
cp .env.example .env
```

### 2. Generate Secure Secrets

```bash
# Generate Django secret key
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Generate other passwords
openssl rand -base64 32  # For PostgreSQL
openssl rand -base64 32  # For Redis
openssl rand -base64 32  # For MeiliSearch
openssl rand -base64 32  # For Neo4j
openssl rand -base64 32  # For JWT
```

### 3. Edit .env File

```bash
nano .env
```

**Required Changes:**
```bash
# Django - Update these!
DJANGO_SECRET_KEY=<your-generated-secret-key>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=bldrdojo.com,www.bldrdojo.com

# Database - Update password!
POSTGRES_PASSWORD=<your-secure-password>

# Redis - Update password!
REDIS_PASSWORD=<your-secure-password>

# MeiliSearch - Update key!
MEILI_MASTER_KEY=<your-secure-key>

# Neo4j - Update password!
NEO4J_PASSWORD=<your-secure-password>

# Email - Configure for production
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Google OAuth - Add your credentials
GOOGLE_CLIENT_ID=your-actual-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-actual-client-secret

# JWT
JWT_SECRET_KEY=<your-jwt-secret>

# CORS
CORS_ALLOWED_ORIGINS=https://bldrdojo.com,https://www.bldrdojo.com
```

Save and exit (Ctrl+X, Y, Enter in nano).

### 4. Verify Environment File

```bash
# Check for required variables
grep -E "change-this|your-" .env

# If output shows any placeholders, update them!
```

---

## Building and Deploying

### 1. Build Docker Images

```bash
cd /opt/bldrdojo

# Build all images
docker-compose build

# This will take 5-15 minutes depending on your server
```

### 2. Start Services

```bash
# Start in detached mode
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

### 3. Initialize Database

```bash
# Wait for services to be healthy (30-60 seconds)
docker-compose ps

# Run migrations
docker-compose exec backend python manage.py migrate

# Create superuser
docker-compose exec backend python manage.py createsuperuser

# Collect static files
docker-compose exec backend python manage.py collectstatic --noinput
```

### 4. Configure Google OAuth

```bash
# Access Django shell
docker-compose exec backend python manage.py shell

# Run these Python commands:
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp

# Update site
site = Site.objects.get_current()
site.domain = 'bldrdojo.com'
site.name = 'Bldrdojo'
site.save()

# Create Google OAuth app
google_app, created = SocialApp.objects.get_or_create(
    provider='google',
    defaults={
        'name': 'Google',
        'client_id': 'YOUR_GOOGLE_CLIENT_ID',
        'secret': 'YOUR_GOOGLE_CLIENT_SECRET',
    }
)
google_app.sites.add(site)
google_app.save()

exit()
```

### 5. Verify Deployment

```bash
# Check all containers are running
docker-compose ps

# Test backend health
curl http://localhost:8000/api/health/

# Test frontend
curl http://localhost/health

# View logs
docker-compose logs backend
docker-compose logs frontend
```

### 6. Access Your Application

- **Frontend**: https://bldrdojo.com
- **API**: https://bldrdojo.com/api/
- **Admin Panel**: https://bldrdojo.com/admin/

---

## Database Management

### Backup Database

```bash
# Manual backup
docker-compose exec db pg_dump -U postgres entitydb > backups/backup_$(date +%Y%m%d_%H%M%S).sql

# Or use postgres in container
docker-compose exec db pg_dump -U postgres -Fc entitydb > backups/backup_$(date +%Y%m%d_%H%M%S).dump
```

### Automated Backups

Create backup script:

```bash
cat > /opt/bldrdojo/backup.sh << 'EOF'
#!/bin/bash
cd /opt/bldrdojo
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose exec -T db pg_dump -U postgres -Fc entitydb > backups/backup_$DATE.dump

# Keep only last 30 days
find backups/ -name "backup_*.dump" -mtime +30 -delete

echo "Backup completed: backup_$DATE.dump"
EOF

chmod +x /opt/bldrdojo/backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
# Add line:
# 0 2 * * * /opt/bldrdojo/backup.sh >> /opt/bldrdojo/logs/backup.log 2>&1
```

### Restore Database

```bash
# Stop backend
docker-compose stop backend

# Restore from backup
docker-compose exec -T db psql -U postgres entitydb < backups/backup_20260130_020000.sql

# Or from .dump file
docker-compose exec -T db pg_restore -U postgres -d entitydb -c < backups/backup_20260130_020000.dump

# Start backend
docker-compose start backend
```

---

## Monitoring and Maintenance

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend

# Last 100 lines
docker-compose logs --tail=100 backend
```

### Check Resource Usage

```bash
# Container stats
docker stats

# Disk usage
docker system df

# Clean up unused resources
docker system prune -a
```

### Update Application

```bash
cd /opt/bldrdojo

# Pull latest changes
git pull

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d

# Run migrations
docker-compose exec backend python manage.py migrate

# Collect static files
docker-compose exec backend python manage.py collectstatic --noinput
```

### Scale Services

```bash
# Scale backend workers
docker-compose up -d --scale backend=3

# Note: You may need a load balancer for multiple backend instances
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker-compose logs <service-name>

# Check configuration
docker-compose config

# Restart service
docker-compose restart <service-name>
```

### Database Connection Issues

```bash
# Check database is running
docker-compose ps db

# Test connection
docker-compose exec backend python manage.py dbshell

# Check DATABASE_URL in .env
docker-compose exec backend env | grep DATABASE
```

### SSL Certificate Issues

```bash
# Verify certificate files exist
ls -la ssl/

# Check nginx config
docker-compose exec frontend nginx -t

# View nginx logs
docker-compose logs frontend
```

### Memory Issues

```bash
# Check available memory
free -h

# Add swap if needed
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### High CPU Usage

```bash
# Identify culprit
docker stats

# Check backend workers
docker-compose exec backend ps aux

# Restart service
docker-compose restart backend
```

---

## Backup and Recovery

### Full System Backup

```bash
#!/bin/bash
# full-backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/opt/bldrdojo/backups/full_$DATE

mkdir -p $BACKUP_DIR

# Backup database
docker-compose exec -T db pg_dump -U postgres -Fc entitydb > $BACKUP_DIR/database.dump

# Backup volumes
docker run --rm -v bldrdojo-postgres-data:/data -v $BACKUP_DIR:/backup alpine tar czf /backup/postgres-data.tar.gz -C /data .
docker run --rm -v bldrdojo-media:/data -v $BACKUP_DIR:/backup alpine tar czf /backup/media.tar.gz -C /data .
docker run --rm -v bldrdojo-vector-data:/data -v $BACKUP_DIR:/backup alpine tar czf /backup/vector-data.tar.gz -C /data .

# Backup .env file
cp .env $BACKUP_DIR/

# Create archive
tar czf backups/full_backup_$DATE.tar.gz -C backups full_$DATE

# Clean up temp directory
rm -rf $BACKUP_DIR

echo "Full backup completed: full_backup_$DATE.tar.gz"
```

### Disaster Recovery

```bash
# 1. Extract backup
tar xzf full_backup_20260130_020000.tar.gz

# 2. Stop services
docker-compose down -v

# 3. Restore volumes
docker run --rm -v bldrdojo-postgres-data:/data -v $(pwd)/full_20260130_020000:/backup alpine tar xzf /backup/postgres-data.tar.gz -C /data
docker run --rm -v bldrdojo-media:/data -v $(pwd)/full_20260130_020000:/backup alpine tar xzf /backup/media.tar.gz -C /data
docker run --rm -v bldrdojo-vector-data:/data -v $(pwd)/full_20260130_020000:/backup alpine tar xzf /backup/vector-data.tar.gz -C /data

# 4. Restore .env
cp full_20260130_020000/.env .env

# 5. Start services
docker-compose up -d

# 6. Restore database
docker-compose exec -T db pg_restore -U postgres -d entitydb -c < full_20260130_020000/database.dump
```

---

## Production Checklist

- [ ] SSL certificates installed and working
- [ ] All secrets changed from defaults in `.env`
- [ ] `DJANGO_DEBUG=False` in production
- [ ] Google OAuth configured with production credentials
- [ ] Email configuration tested
- [ ] Automated backups configured
- [ ] Monitoring/alerting setup
- [ ] Firewall configured (only 80, 443, 22 open)
- [ ] Regular security updates scheduled
- [ ] Log rotation configured
- [ ] Domain DNS pointing to server
- [ ] Health checks passing

---

## Security Best Practices

1. **Keep secrets secure**: Never commit `.env` to version control
2. **Regular updates**: Update Docker images monthly
3. **Monitor logs**: Check for suspicious activity
4. **Limit access**: Use SSH keys, disable password auth
5. **Backup regularly**: Test restore procedures
6. **Use strong passwords**: 32+ character random strings
7. **Enable firewall**: Only expose necessary ports
8. **SSL only**: Force HTTPS redirect

---

## Support

For issues or questions:
- Check logs: `docker-compose logs -f`
- Review documentation: This file
- Test locally first
- Contact system administrator

---

**Last Updated**: 2026-01-30  
**Version**: 1.0.0
