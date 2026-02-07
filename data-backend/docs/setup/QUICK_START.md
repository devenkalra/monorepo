# Bldrdojo.com - Quick Start Guide

Fast deployment guide for bldrdojo.com production environment.

## 🚀 Quick Deploy (5 minutes)

### Step 1: Prepare Server

```bash
# Install Docker & Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Clone/copy project to server
cd /opt
sudo mkdir bldrdojo && sudo chown $USER:$USER bldrdojo
cd bldrdojo
# (Copy your files here)
```

### Step 2: Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env

# Update these required values:
# - DJANGO_SECRET_KEY
# - POSTGRES_PASSWORD
# - REDIS_PASSWORD
# - MEILI_MASTER_KEY
# - NEO4J_PASSWORD
# - GOOGLE_CLIENT_ID
# - GOOGLE_CLIENT_SECRET
```

### Step 3: Setup SSL Certificates

```bash
# Option A: Let's Encrypt (Production)
sudo apt-get install certbot
sudo certbot certonly --standalone -d bldrdojo.com -d www.bldrdojo.com
sudo cp /etc/letsencrypt/live/bldrdojo.com/fullchain.pem ssl/
sudo cp /etc/letsencrypt/live/bldrdojo.com/privkey.pem ssl/
sudo chown $USER:$USER ssl/*.pem

# Option B: Self-Signed (Development)
mkdir -p ssl
cd ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout privkey.pem -out fullchain.pem \
  -subj "/CN=bldrdojo.com"
cd ..
```

### Step 4: Deploy

```bash
# Run automated deployment
./deploy.sh

# Or manual steps:
docker-compose build
docker-compose up -d
docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py collectstatic --noinput
docker-compose exec backend python manage.py createsuperuser
```

### Step 5: Verify

```bash
# Check services
docker-compose ps

# Test health
curl https://bldrdojo.com/health
curl https://bldrdojo.com/api/health/

# View logs
docker-compose logs -f
```

## 🎯 URLs

- **Frontend**: https://bldrdojo.com
- **API**: https://bldrdojo.com/api/
- **Admin**: https://bldrdojo.com/admin/
- **Health**: https://bldrdojo.com/api/health/

## 📋 Common Commands

```bash
# View logs
docker-compose logs -f
docker-compose logs -f backend
docker-compose logs -f frontend

# Restart services
docker-compose restart
docker-compose restart backend

# Stop/Start
docker-compose down
docker-compose up -d

# Access shell
docker-compose exec backend bash
docker-compose exec backend python manage.py shell

# Database backup
docker-compose exec db pg_dump -U postgres entitydb > backup.sql

# Update application
git pull
docker-compose down
docker-compose build
docker-compose up -d
docker-compose exec backend python manage.py migrate
```

## 🔧 Troubleshooting

### Service won't start
```bash
docker-compose logs <service>
docker-compose restart <service>
```

### Database issues
```bash
docker-compose exec backend python manage.py dbshell
```

### SSL certificate issues
```bash
ls -la ssl/
docker-compose exec frontend nginx -t
```

### Reset everything
```bash
docker-compose down -v
rm -rf ssl/* logs/*
# Start over from Step 2
```

## 📚 Full Documentation

See [DEPLOYMENT.md](./DEPLOYMENT.md) for complete documentation including:
- Architecture details
- Backup/restore procedures
- Monitoring setup
- Security best practices
- Disaster recovery

## ✅ Production Checklist

Before going live:

- [ ] SSL certificates configured
- [ ] All secrets changed in `.env`
- [ ] `DJANGO_DEBUG=False`
- [ ] Google OAuth configured
- [ ] Domain DNS pointing to server
- [ ] Firewall configured (ports 80, 443, 22)
- [ ] Automated backups scheduled
- [ ] Superuser account created
- [ ] Test all functionality
- [ ] Monitor logs for errors

## 🆘 Emergency Commands

```bash
# Stop everything immediately
docker-compose down

# Restore from backup
docker-compose down -v
docker-compose up -d db
docker-compose exec -T db psql -U postgres entitydb < backup.sql
docker-compose up -d

# View error logs
docker-compose logs --tail=100 backend
docker-compose logs --tail=100 frontend

# Check disk space
df -h
docker system df

# Clean up disk space
docker system prune -a
```

## 📞 Support

For detailed help, see [DEPLOYMENT.md](./DEPLOYMENT.md)
