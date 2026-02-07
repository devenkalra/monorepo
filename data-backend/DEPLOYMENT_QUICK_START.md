# Production Deployment - Quick Start

**For detailed instructions, see [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md)**

## Prerequisites

- Ubuntu 22.04+ server with 4GB+ RAM
- Domain name with DNS pointing to server
- Root/sudo access

## Quick Deploy (30 minutes)

### 1. Prepare Server

```bash
# SSH into server
ssh root@your.server.ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install Nginx & Certbot
sudo apt install nginx certbot python3-certbot-nginx -y

# Configure firewall
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

**Log out and back in** for Docker group to take effect.

### 2. Deploy Application

```bash
# Create app directory
sudo mkdir -p /opt/data-backend
sudo chown $USER:$USER /opt/data-backend
cd /opt/data-backend

# Clone code (or copy from dev machine)
git clone <your-repo-url> .
# OR: rsync -av /local/path/ user@server:/opt/data-backend/

# Create production environment
cp .env.example .env.production
nano .env.production
```

**Edit `.env.production`:**
- Set `DEBUG=False`
- Generate `SECRET_KEY`: `python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- Set `ALLOWED_HOSTS=app.yourdomain.com`
- Set strong passwords for DB, Neo4j, MeiliSearch
- Configure CORS origins
- Set email SMTP settings

### 3. Create Production Docker Files

**Create `docker-compose.production.yml`** - See [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md#step-3-create-production-docker-compose)

**Create `Dockerfile.production`** - See [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md#41-backend-production-dockerfile)

**Create `frontend/Dockerfile.production`** - See [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md#42-frontend-production-dockerfile)

**Update frontend API URL** in `frontend/src/api.js`:
```javascript
const API_BASE_URL = import.meta.env.PROD 
  ? 'https://app.yourdomain.com/api'
  : 'http://localhost:8000/api';
```

### 4. Configure Nginx

```bash
# Create Nginx config
sudo nano /etc/nginx/sites-available/data-backend
```

Paste config from [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md#51-create-nginx-site-configuration)

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/data-backend /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### 5. Get SSL Certificate

```bash
sudo certbot --nginx -d app.yourdomain.com
```

Follow prompts, choose redirect HTTP to HTTPS.

### 6. Start Application

```bash
cd /opt/data-backend

# Build and start
docker-compose -f docker-compose.production.yml build
docker-compose -f docker-compose.production.yml up -d

# Create superuser
docker-compose -f docker-compose.production.yml exec backend python manage.py createsuperuser

# Check status
docker-compose -f docker-compose.production.yml ps
```

### 7. Verify

```bash
# Test locally
curl http://localhost:8000/api/

# Test via domain
curl https://app.yourdomain.com/api/

# Visit in browser
https://app.yourdomain.com
```

### 8. Setup Backups

```bash
chmod +x scripts/*.sh
./scripts/setup_automated_backups.sh daily
```

## Done! 🎉

Your application is now live at **https://app.yourdomain.com**

---

## Common Commands

```bash
# View logs
docker-compose -f docker-compose.production.yml logs -f

# Restart service
docker-compose -f docker-compose.production.yml restart backend

# Run migrations
docker-compose -f docker-compose.production.yml exec backend python manage.py migrate

# Create backup
./scripts/backup.sh

# Restore backup
./scripts/restore.sh backup_name

# Update application
git pull
docker-compose -f docker-compose.production.yml build
docker-compose -f docker-compose.production.yml up -d
```

---

## Troubleshooting

### 502 Bad Gateway
```bash
# Check backend logs
docker-compose -f docker-compose.production.yml logs backend

# Check if backend is running
docker-compose -f docker-compose.production.yml ps
```

### Database Connection Error
```bash
# Check database logs
docker-compose -f docker-compose.production.yml logs db

# Verify credentials in .env.production
```

### SSL Certificate Issues
```bash
# Renew certificate
sudo certbot renew

# Check certificate
sudo certbot certificates
```

---

## Next Steps

1. ✅ Test all functionality
2. ✅ Set up monitoring
3. ✅ Configure alerts
4. ✅ Test backup/restore
5. ✅ Document admin procedures
6. ✅ Set up staging environment
7. ✅ Configure CI/CD

---

## Support

- **Full Guide:** [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md)
- **Checklist:** [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)
- **Backup Guide:** See `scripts/backup.sh`
