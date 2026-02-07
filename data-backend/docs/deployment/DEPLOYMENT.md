# Deployment Guide for bldrdojo.com on Linode Ubuntu 22.04

This guide covers deploying the Django + React application to a Linode server using Docker and nginx.

## Table of Contents
1. [Server Setup](#server-setup)
2. [Install Dependencies](#install-dependencies)
3. [Configure Domain and DNS](#configure-domain-and-dns)
4. [Setup SSL Certificates](#setup-ssl-certificates)
5. [Deploy Application](#deploy-application)
6. [Post-Deployment](#post-deployment)
7. [Maintenance](#maintenance)

---

## 1. Server Setup

### Create Linode Server
1. Log into Linode Cloud Manager
2. Create a new Linode:
   - **Distribution**: Ubuntu 22.04 LTS
   - **Plan**: Dedicated 8GB+ (recommended for Neo4j, MeiliSearch, Vector service)
   - **Region**: Choose closest to your users
   - **Label**: bldrdojo-production
3. Set a strong root password
4. Boot the server

### Initial Server Configuration

```bash
# SSH into your server
ssh root@<your-server-ip>

# Update system packages
apt update && apt upgrade -y

# Set timezone
timedatectl set-timezone America/Los_Angeles  # or your timezone

# Set hostname
hostnamectl set-hostname bldrdojo

# Create a non-root user with sudo privileges
adduser deploy
usermod -aG sudo deploy

# Setup SSH key authentication for deploy user
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

# Configure firewall
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# Disable root SSH login (optional but recommended)
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart sshd

# Switch to deploy user
su - deploy
```

---

## 2. Install Dependencies

### Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add deploy user to docker group
sudo usermod -aG docker deploy

# Start Docker service
sudo systemctl enable docker
sudo systemctl start docker

# Log out and back in for group changes to take effect
exit
# SSH back in as deploy user
ssh deploy@<your-server-ip>

# Verify Docker installation
docker --version
docker compose version
```

### Install Additional Tools

```bash
# Install git
sudo apt install -y git

# Install certbot for SSL certificates
sudo apt install -y certbot

# Install monitoring tools (optional)
sudo apt install -y htop iotop nethogs
```

---

## 3. Configure Domain and DNS

### DNS Configuration in Your Domain Registrar

Add the following DNS records for `bldrdojo.com`:

```
Type    Name    Value                       TTL
A       @       <your-linode-ip>           300
A       www     <your-linode-ip>           300
```

### Verify DNS Propagation

```bash
# Wait for DNS to propagate (can take up to 48 hours, usually minutes)
dig bldrdojo.com
dig www.bldrdojo.com

# Or use online tools like https://dnschecker.org/
```

---

## 4. Setup SSL Certificates

### Option A: Let's Encrypt with Certbot (Recommended)

```bash
# Stop any running containers first
cd /home/deploy/data-backend
docker compose down

# Obtain SSL certificate
sudo certbot certonly --standalone -d bldrdojo.com -d www.bldrdojo.com

# Certificates will be stored at:
# /etc/letsencrypt/live/bldrdojo.com/fullchain.pem
# /etc/letsencrypt/live/bldrdojo.com/privkey.pem

# Create SSL directory for Docker
mkdir -p /home/deploy/data-backend/ssl

# Copy certificates (or create symlinks)
sudo cp /etc/letsencrypt/live/bldrdojo.com/fullchain.pem /home/deploy/data-backend/ssl/
sudo cp /etc/letsencrypt/live/bldrdojo.com/privkey.pem /home/deploy/data-backend/ssl/
sudo chown -R deploy:deploy /home/deploy/data-backend/ssl
sudo chmod 644 /home/deploy/data-backend/ssl/fullchain.pem
sudo chmod 600 /home/deploy/data-backend/ssl/privkey.pem

# Setup auto-renewal
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer

# Create renewal hook to copy new certificates
sudo tee /etc/letsencrypt/renewal-hooks/deploy/copy-certs.sh << 'EOF'
#!/bin/bash
cp /etc/letsencrypt/live/bldrdojo.com/fullchain.pem /home/deploy/data-backend/ssl/
cp /etc/letsencrypt/live/bldrdojo.com/privkey.pem /home/deploy/data-backend/ssl/
chown deploy:deploy /home/deploy/data-backend/ssl/*.pem
chmod 644 /home/deploy/data-backend/ssl/fullchain.pem
chmod 600 /home/deploy/data-backend/ssl/privkey.pem
cd /home/deploy/data-backend && docker compose restart frontend
EOF

sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/copy-certs.sh
```

### Option B: Self-Signed Certificate (Development/Testing Only)

```bash
mkdir -p /home/deploy/data-backend/ssl
cd /home/deploy/data-backend/ssl

# Generate self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout privkey.pem \
  -out fullchain.pem \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=bldrdojo.com"

chmod 644 fullchain.pem
chmod 600 privkey.pem
```

---

## 5. Deploy Application

### Clone Repository

```bash
# Create application directory
cd /home/deploy
git clone <your-repo-url> data-backend
cd data-backend

# Or if you're deploying from local machine, use rsync:
# From your local machine:
# rsync -avz --exclude 'node_modules' --exclude '__pycache__' --exclude '.git' \
#   /home/ubuntu/monorepo/data-backend/ deploy@<your-server-ip>:/home/deploy/data-backend/
```

### Create Environment File

```bash
cd /home/deploy/data-backend

# Create .env file
cat > .env << 'EOF'
# Django Settings
DJANGO_SECRET_KEY=<generate-a-strong-random-key>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=bldrdojo.com,www.bldrdojo.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://bldrdojo.com,https://www.bldrdojo.com

# Database
POSTGRES_DB=entitydb
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<generate-strong-password>

# Redis
REDIS_PASSWORD=<generate-strong-password>

# MeiliSearch
MEILI_MASTER_KEY=<generate-strong-key>

# Neo4j
NEO4J_USER=neo4j
NEO4J_PASSWORD=<generate-strong-password>

# Email (configure based on your provider)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Optional: Sentry for error tracking
# SENTRY_DSN=your-sentry-dsn
EOF

# Secure the .env file
chmod 600 .env

# Generate Django secret key
python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
# Copy the output and update DJANGO_SECRET_KEY in .env

# Generate other passwords
openssl rand -base64 32  # Use for POSTGRES_PASSWORD
openssl rand -base64 32  # Use for REDIS_PASSWORD
openssl rand -base64 32  # Use for MEILI_MASTER_KEY
openssl rand -base64 32  # Use for NEO4J_PASSWORD
```

### Create Required Directories

```bash
cd /home/deploy/data-backend

# Create directories for logs and backups
mkdir -p logs logs/nginx backups

# Set permissions
chmod 755 logs backups
```

### Build and Start Services

```bash
cd /home/deploy/data-backend

# Build Docker images
docker compose build

# Start services
docker compose up -d

# Check service status
docker compose ps

# View logs
docker compose logs -f

# Wait for all services to be healthy (may take 2-3 minutes)
watch docker compose ps
```

### Initialize Database and Create Superuser

```bash
# Run migrations (should already run via docker-compose command)
docker compose exec backend python manage.py migrate

# Create Django superuser
docker compose exec backend python manage.py createsuperuser

# Create initial data (if you have fixtures)
# docker compose exec backend python manage.py loaddata initial_data.json

# Index data in MeiliSearch
docker compose exec backend python manage.py sync_meilisearch
```

---

## 6. Post-Deployment

### Verify Deployment

```bash
# Check all containers are running
docker compose ps

# Test backend API
curl https://bldrdojo.com/api/health/

# Test frontend
curl https://bldrdojo.com/

# Check logs for errors
docker compose logs backend | tail -100
docker compose logs frontend | tail -100
```

### Access Admin Panel

1. Navigate to `https://bldrdojo.com/admin/`
2. Login with superuser credentials
3. Verify data is accessible

### Setup Monitoring

```bash
# Monitor container resource usage
docker stats

# View logs in real-time
docker compose logs -f --tail=100

# Check disk usage
df -h
docker system df
```

### Setup Automated Backups

```bash
# Create backup script
cat > /home/deploy/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/deploy/data-backend/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup PostgreSQL
docker compose exec -T db pg_dump -U postgres entitydb | gzip > "$BACKUP_DIR/postgres_$DATE.sql.gz"

# Backup volumes
docker run --rm -v bldrdojo-postgres-data:/data -v $BACKUP_DIR:/backup alpine tar czf /backup/postgres_volume_$DATE.tar.gz -C /data .
docker run --rm -v bldrdojo-neo4j-data:/data -v $BACKUP_DIR:/backup alpine tar czf /backup/neo4j_volume_$DATE.tar.gz -C /data .
docker run --rm -v bldrdojo-media:/data -v $BACKUP_DIR:/backup alpine tar czf /backup/media_$DATE.tar.gz -C /data .

# Keep only last 7 days of backups
find $BACKUP_DIR -name "*.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
EOF

chmod +x /home/deploy/backup.sh

# Add to crontab (daily at 2 AM)
(crontab -l 2>/dev/null; echo "0 2 * * * /home/deploy/backup.sh >> /home/deploy/logs/backup.log 2>&1") | crontab -
```

---

## 7. Maintenance

### Update Application

```bash
cd /home/deploy/data-backend

# Pull latest code
git pull origin main

# Rebuild and restart services
docker compose build
docker compose up -d

# Run migrations
docker compose exec backend python manage.py migrate

# Collect static files
docker compose exec backend python manage.py collectstatic --noinput

# Restart services
docker compose restart
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f db

# Last 100 lines
docker compose logs --tail=100 backend
```

### Restart Services

```bash
# Restart all services
docker compose restart

# Restart specific service
docker compose restart backend
docker compose restart frontend

# Stop all services
docker compose down

# Start all services
docker compose up -d
```

### Database Management

```bash
# Access PostgreSQL
docker compose exec db psql -U postgres -d entitydb

# Backup database
docker compose exec db pg_dump -U postgres entitydb > backup.sql

# Restore database
cat backup.sql | docker compose exec -T db psql -U postgres -d entitydb

# Access Neo4j browser
# Navigate to http://<server-ip>:7474 (you may need to open this port temporarily)
# Or use cypher-shell:
docker compose exec neo4j cypher-shell -u neo4j -p <NEO4J_PASSWORD>
```

### Clean Up Docker Resources

```bash
# Remove unused images
docker image prune -a

# Remove unused volumes (BE CAREFUL!)
docker volume prune

# Remove unused networks
docker network prune

# Full cleanup (BE VERY CAREFUL!)
docker system prune -a --volumes
```

### Monitor Resource Usage

```bash
# Check disk space
df -h

# Check Docker disk usage
docker system df

# Monitor container resources
docker stats

# Check memory usage
free -h

# Check CPU usage
htop
```

### Troubleshooting

#### Container won't start

```bash
# Check logs
docker compose logs <service-name>

# Check container status
docker compose ps

# Restart container
docker compose restart <service-name>

# Rebuild container
docker compose up -d --build <service-name>
```

#### Database connection issues

```bash
# Check database is running
docker compose ps db

# Check database logs
docker compose logs db

# Verify environment variables
docker compose exec backend env | grep DATABASE

# Test database connection
docker compose exec backend python manage.py dbshell
```

#### SSL certificate issues

```bash
# Check certificate files exist
ls -la /home/deploy/data-backend/ssl/

# Check certificate expiry
sudo certbot certificates

# Renew certificate manually
sudo certbot renew

# Copy new certificates
sudo /etc/letsencrypt/renewal-hooks/deploy/copy-certs.sh
```

#### Out of disk space

```bash
# Check disk usage
df -h

# Clean Docker resources
docker system prune -a

# Remove old backups
find /home/deploy/data-backend/backups -mtime +30 -delete

# Check log file sizes
du -sh /home/deploy/data-backend/logs/*

# Rotate logs
docker compose logs --tail=1000 backend > /tmp/backend.log
docker compose restart backend
```

---

## Security Checklist

- [ ] Firewall configured (UFW)
- [ ] SSH key authentication enabled
- [ ] Root login disabled
- [ ] Strong passwords for all services
- [ ] SSL certificates installed
- [ ] Django DEBUG=False
- [ ] Django SECRET_KEY is random and secure
- [ ] ALLOWED_HOSTS configured
- [ ] CSRF_TRUSTED_ORIGINS configured
- [ ] Database passwords are strong
- [ ] .env file permissions set to 600
- [ ] Regular backups configured
- [ ] Log monitoring setup
- [ ] Security headers configured in nginx

---

## Performance Tuning

### For 8GB+ Linode

Update `docker-compose.yml` resource limits:

```yaml
# Increase Neo4j memory
neo4j:
  environment:
    - NEO4J_dbms_memory_pagecache_size=1G
    - NEO4J_dbms_memory_heap_initial__size=1G
    - NEO4J_dbms_memory_heap_max__size=2G

# Increase backend workers
backend:
  command: >
    sh -c "
      python manage.py migrate &&
      python manage.py collectstatic --noinput &&
      gunicorn --bind 0.0.0.0:8000 --workers 8 --timeout 120 config.wsgi:application
    "
```

---

## Quick Reference Commands

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f

# Restart a service
docker compose restart backend

# Rebuild and restart
docker compose up -d --build

# Run Django management command
docker compose exec backend python manage.py <command>

# Access Django shell
docker compose exec backend python manage.py shell

# Create superuser
docker compose exec backend python manage.py createsuperuser

# Run migrations
docker compose exec backend python manage.py migrate

# Backup database
docker compose exec db pg_dump -U postgres entitydb > backup.sql

# Check service status
docker compose ps

# View resource usage
docker stats
```

---

## Support and Troubleshooting

If you encounter issues:

1. Check logs: `docker compose logs -f`
2. Verify all services are healthy: `docker compose ps`
3. Check disk space: `df -h`
4. Verify DNS: `dig bldrdojo.com`
5. Test SSL: `curl -I https://bldrdojo.com`
6. Check firewall: `sudo ufw status`

For additional help, check:
- Django logs: `/home/deploy/data-backend/logs/`
- Nginx logs: `/home/deploy/data-backend/logs/nginx/`
- Docker logs: `docker compose logs`
