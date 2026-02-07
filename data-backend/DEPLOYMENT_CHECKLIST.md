## Production Deployment Checklist

Use this checklist to ensure a smooth deployment to production.

---

### Pre-Deployment

#### Server Setup
- [ ] Ubuntu 22.04+ server provisioned
- [ ] Server has minimum 4GB RAM, 50GB storage
- [ ] SSH access configured
- [ ] Static IP address assigned
- [ ] Domain name registered
- [ ] DNS A record points to server IP

#### Software Installation
- [ ] Docker installed (`docker --version`)
- [ ] Docker Compose installed (`docker-compose --version`)
- [ ] Nginx installed (`nginx -v`)
- [ ] Certbot installed (`certbot --version`)
- [ ] Git installed (`git --version`)
- [ ] Firewall configured (UFW)

#### Configuration Files
- [ ] `.env.production` created with production values
- [ ] `SECRET_KEY` generated (strong random string)
- [ ] Database passwords set (strong, unique)
- [ ] `ALLOWED_HOSTS` configured
- [ ] `CORS_ALLOWED_ORIGINS` configured
- [ ] Email SMTP settings configured
- [ ] Social auth credentials (if using)

---

### Deployment Steps

#### 1. Application Setup
- [ ] Code cloned to `/opt/data-backend`
- [ ] `docker-compose.production.yml` created
- [ ] `Dockerfile.production` created (backend)
- [ ] `frontend/Dockerfile.production` created
- [ ] `frontend/nginx.conf` created
- [ ] Frontend API URL updated for production

#### 2. Nginx Configuration
- [ ] Nginx site config created (`/etc/nginx/sites-available/data-backend`)
- [ ] Site enabled (`/etc/nginx/sites-enabled/data-backend`)
- [ ] Default site removed
- [ ] Nginx config tested (`nginx -t`)
- [ ] Nginx reloaded

#### 3. SSL Certificate
- [ ] SSL certificate obtained (`certbot --nginx`)
- [ ] Certificate auto-renewal tested (`certbot renew --dry-run`)
- [ ] HTTPS redirect configured
- [ ] SSL grade verified (https://www.ssllabs.com/ssltest/)

#### 4. Docker Deployment
- [ ] Docker images built
- [ ] Containers started (`docker-compose up -d`)
- [ ] All containers healthy (`docker-compose ps`)
- [ ] Database migrations run
- [ ] Static files collected
- [ ] Superuser created

#### 5. Verification
- [ ] Website loads (https://your-domain.com)
- [ ] API responds (https://your-domain.com/api/)
- [ ] User registration works
- [ ] User login works
- [ ] Entity creation works
- [ ] File upload works
- [ ] Search works
- [ ] No console errors in browser
- [ ] No errors in server logs

---

### Security Hardening

#### Django Settings
- [ ] `DEBUG = False`
- [ ] `SECRET_KEY` is strong and unique
- [ ] `ALLOWED_HOSTS` properly configured
- [ ] `SECURE_SSL_REDIRECT = True`
- [ ] `SESSION_COOKIE_SECURE = True`
- [ ] `CSRF_COOKIE_SECURE = True`
- [ ] `SECURE_HSTS_SECONDS` set
- [ ] Strong password validation enabled

#### Server Security
- [ ] Firewall enabled (ports 80, 443, 22 only)
- [ ] SSH key authentication (password auth disabled)
- [ ] Fail2ban installed (optional)
- [ ] Automatic security updates enabled
- [ ] Non-root user for application
- [ ] Docker containers run as non-root

#### Secrets Management
- [ ] `.env.production` not in git
- [ ] Database passwords documented securely
- [ ] API keys stored securely
- [ ] Backup of all credentials in password manager

---

### Monitoring & Maintenance

#### Backups
- [ ] Backup script tested (`./scripts/backup.sh`)
- [ ] Automated daily backups configured
- [ ] Backup verification script run
- [ ] Remote backup storage configured
- [ ] Restore procedure tested

#### Logging
- [ ] Log rotation configured
- [ ] Docker container logging configured
- [ ] Nginx logs accessible
- [ ] Application logs accessible
- [ ] Error tracking set up (Sentry, etc.)

#### Monitoring
- [ ] Health check script created
- [ ] Uptime monitoring configured
- [ ] Disk space monitoring
- [ ] Memory usage monitoring
- [ ] Email alerts configured

---

### Post-Deployment

#### Documentation
- [ ] Deployment date recorded
- [ ] Admin credentials documented (securely)
- [ ] Server details documented
- [ ] Maintenance procedures documented
- [ ] Troubleshooting guide reviewed

#### Testing
- [ ] Full user workflow tested
- [ ] Performance testing completed
- [ ] Load testing (if applicable)
- [ ] Mobile responsiveness checked
- [ ] Cross-browser testing

#### Team Handoff
- [ ] Access credentials shared (securely)
- [ ] Documentation shared
- [ ] On-call procedures established
- [ ] Escalation contacts defined

---

### Ongoing Maintenance

#### Daily
- [ ] Check service health
- [ ] Review error logs
- [ ] Monitor disk space

#### Weekly
- [ ] Verify backups completed
- [ ] Review access logs
- [ ] Check for security updates

#### Monthly
- [ ] Test backup restore procedure
- [ ] Review and rotate logs
- [ ] Update dependencies
- [ ] Review performance metrics

#### Quarterly
- [ ] Security audit
- [ ] Disaster recovery drill
- [ ] Review and update documentation
- [ ] Capacity planning review

---

### Emergency Contacts

| Role | Name | Contact | Notes |
|------|------|---------|-------|
| System Admin | _________ | _________ | Primary |
| Developer | _________ | _________ | Code issues |
| DevOps | _________ | _________ | Infrastructure |
| Database Admin | _________ | _________ | DB issues |

---

### Important URLs

- **Production Site:** https://your-domain.com
- **Admin Panel:** https://your-domain.com/admin/
- **API Docs:** https://your-domain.com/api/
- **Monitoring:** _____________
- **Error Tracking:** _____________
- **Backup Storage:** _____________

---

### Rollback Procedure

If deployment fails:

1. **Stop new containers:**
   ```bash
   docker-compose -f docker-compose.production.yml down
   ```

2. **Restore from backup:**
   ```bash
   ./scripts/restore.sh <backup-name>
   ```

3. **Start old version:**
   ```bash
   git checkout <previous-commit>
   docker-compose -f docker-compose.production.yml up -d
   ```

4. **Verify services:**
   ```bash
   ./scripts/health_check.sh
   ```

---

### Sign-Off

**Deployment Completed By:** _______________________  
**Date:** _______________________  
**Verified By:** _______________________  
**Date:** _______________________  

**Notes:**
_____________________________________________________________
_____________________________________________________________
_____________________________________________________________
