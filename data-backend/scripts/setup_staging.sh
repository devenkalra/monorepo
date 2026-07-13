#!/bin/bash
#
# Staging Environment Setup Script
#
# This script automates the setup of a staging environment
#
# Usage:
#   ./scripts/setup_staging.sh [same-server|separate-server]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SETUP_TYPE="${1:-same-server}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Staging Environment Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ "$SETUP_TYPE" != "same-server" ] && [ "$SETUP_TYPE" != "separate-server" ]; then
    echo -e "${RED}Error: Invalid setup type${NC}"
    echo "Usage: ./scripts/setup_staging.sh [same-server|separate-server]"
    exit 1
fi

echo -e "${YELLOW}Setup type:${NC} $SETUP_TYPE"
echo ""

# Check if running on production server
if [ -d "/opt/data-backend" ] && [ "$SETUP_TYPE" = "same-server" ]; then
    echo -e "${YELLOW}Detected production installation${NC}"
    PROD_DIR="/opt/data-backend"
else
    PROD_DIR=""
fi

# Staging directory
if [ "$SETUP_TYPE" = "same-server" ]; then
    STAGING_DIR="/opt/data-backend-staging"
else
    STAGING_DIR="/opt/data-backend"
fi

echo -e "${YELLOW}Staging directory:${NC} $STAGING_DIR"
echo ""

# Confirmation
read -p "Continue with staging setup? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Setup cancelled"
    exit 0
fi
echo ""

# Create staging directory
echo -e "${YELLOW}Creating staging directory...${NC}"
if [ ! -d "$STAGING_DIR" ]; then
    sudo mkdir -p "$STAGING_DIR"
    sudo chown $USER:$USER "$STAGING_DIR"
    echo -e "${GREEN}✓ Directory created${NC}"
else
    echo -e "${YELLOW}Directory already exists${NC}"
fi
echo ""

# Clone or copy code
echo -e "${YELLOW}Setting up code...${NC}"
cd "$STAGING_DIR"

if [ -z "$(ls -A $STAGING_DIR)" ]; then
    if [ -n "$PROD_DIR" ]; then
        echo "Copying from production..."
        cp -r "$PROD_DIR"/* .
        cp -r "$PROD_DIR"/.env.example .
        echo -e "${GREEN}✓ Code copied from production${NC}"
    else
        echo -e "${YELLOW}Please clone your repository:${NC}"
        echo "  git clone <your-repo-url> $STAGING_DIR"
        exit 1
    fi
else
    echo -e "${YELLOW}Directory not empty, skipping code setup${NC}"
fi
echo ""

# Create .env.staging
echo -e "${YELLOW}Creating staging environment file...${NC}"
if [ ! -f ".env.staging" ]; then
    if [ -f ".env.production" ]; then
        cp .env.production .env.staging
    elif [ -f ".env.example" ]; then
        cp .env.example .env.staging
    else
        echo -e "${RED}Error: No environment template found${NC}"
        exit 1
    fi
    
    # Update staging-specific values
    sed -i 's/DEBUG=False/DEBUG=False/' .env.staging
    sed -i 's/production_db/staging_db/g' .env.staging
    sed -i 's/prod_user/staging_user/g' .env.staging
    sed -i 's/app\.yourdomain\.com/staging.yourdomain.com/g' .env.staging
    
    echo -e "${GREEN}✓ .env.staging created${NC}"
    echo -e "${YELLOW}⚠ Please edit .env.staging with staging-specific values:${NC}"
    echo "  - SECRET_KEY (generate new)"
    echo "  - Database passwords"
    echo "  - ALLOWED_HOSTS"
    echo "  - CORS_ALLOWED_ORIGINS"
else
    echo -e "${YELLOW}.env.staging already exists${NC}"
fi
echo ""

# Create docker-compose.staging.yml
echo -e "${YELLOW}Creating staging Docker Compose file...${NC}"
if [ ! -f "docker-compose.staging.yml" ]; then
    if [ -f "docker-compose.production.yml" ]; then
        cp docker-compose.production.yml docker-compose.staging.yml
        
        # Update container names and ports
        if [ "$SETUP_TYPE" = "same-server" ]; then
            sed -i 's/prod-/staging-/g' docker-compose.staging.yml
            sed -i 's/5432:5432/5433:5432/' docker-compose.staging.yml
            sed -i 's/6379:6379/6381:6379/' docker-compose.staging.yml
            sed -i 's/7474:7474/7475:7474/' docker-compose.staging.yml
            sed -i 's/7687:7687/7688:7687/' docker-compose.staging.yml
            sed -i 's/7700:7700/7702:7700/' docker-compose.staging.yml
            sed -i 's/8000:8000/8001:8000/' docker-compose.staging.yml
            sed -i 's/80:80/3001:80/' docker-compose.staging.yml
        fi
        
        # Update volume names
        sed -i 's/postgres_data/postgres_staging_data/g' docker-compose.staging.yml
        sed -i 's/redis_data/redis_staging_data/g' docker-compose.staging.yml
        sed -i 's/neo4j_data/neo4j_staging_data/g' docker-compose.staging.yml
        sed -i 's/meilisearch_data/meilisearch_staging_data/g' docker-compose.staging.yml
        
        # Update network name
        sed -i 's/backend:/staging:/' docker-compose.staging.yml
        sed -i 's/- backend/- staging/' docker-compose.staging.yml
        
        echo -e "${GREEN}✓ docker-compose.staging.yml created${NC}"
    else
        echo -e "${RED}Error: docker-compose.production.yml not found${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}docker-compose.staging.yml already exists${NC}"
fi
echo ""

# Create Nginx configuration
if [ "$SETUP_TYPE" = "same-server" ]; then
    echo -e "${YELLOW}Creating Nginx configuration...${NC}"
    
    NGINX_CONFIG="/etc/nginx/sites-available/data-backend-staging"
    
    if [ ! -f "$NGINX_CONFIG" ]; then
        echo -e "${YELLOW}Please enter your staging domain (e.g., staging.yourdomain.com):${NC}"
        read STAGING_DOMAIN
        
        sudo tee "$NGINX_CONFIG" > /dev/null << EOF
server {
    listen 80;
    listen [::]:80;
    server_name $STAGING_DOMAIN;
    
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $STAGING_DOMAIN;

    # SSL certificates (will be added by certbot)
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    add_header X-Robots-Tag "noindex, nofollow" always;
    add_header X-Environment "staging" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    client_max_body_size 100M;

    access_log /var/log/nginx/staging-access.log;
    error_log /var/log/nginx/staging-error.log;

    location / {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
    }

    location /api/ {
        proxy_pass http://localhost:8001/api/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /admin/ {
        proxy_pass http://localhost:8001/admin/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /static/ {
        alias $STAGING_DIR/staticfiles-staging/;
        expires 1y;
    }

    location /media/ {
        alias $STAGING_DIR/media-staging/;
        expires 1y;
    }
}
EOF
        
        # Enable site
        sudo ln -s "$NGINX_CONFIG" /etc/nginx/sites-enabled/ 2>/dev/null || true
        
        # Test configuration
        sudo nginx -t
        
        # Reload Nginx
        sudo systemctl reload nginx
        
        echo -e "${GREEN}✓ Nginx configured${NC}"
        echo ""
        
        # Get SSL certificate
        echo -e "${YELLOW}Getting SSL certificate...${NC}"
        echo "Run: sudo certbot --nginx -d $STAGING_DOMAIN"
    else
        echo -e "${YELLOW}Nginx configuration already exists${NC}"
    fi
fi
echo ""

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Staging Setup Complete! ✓${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo ""
echo -e "1. Edit staging configuration:"
echo -e "   ${YELLOW}nano $STAGING_DIR/.env.staging${NC}"
echo ""
echo -e "2. Get SSL certificate (if same-server):"
echo -e "   ${YELLOW}sudo certbot --nginx -d staging.yourdomain.com${NC}"
echo ""
echo -e "3. Build and start staging:"
echo -e "   ${YELLOW}cd $STAGING_DIR${NC}"
echo -e "   ${YELLOW}docker-compose -f docker-compose.staging.yml build${NC}"
echo -e "   ${YELLOW}docker-compose -f docker-compose.staging.yml up -d${NC}"
echo ""
echo -e "4. Create superuser:"
echo -e "   ${YELLOW}docker-compose -f docker-compose.staging.yml exec backend-staging python manage.py createsuperuser${NC}"
echo ""
echo -e "5. (Optional) Copy production data:"
echo -e "   ${YELLOW}cd $PROD_DIR && ./scripts/backup.sh staging-seed${NC}"
echo -e "   ${YELLOW}cd $STAGING_DIR && ./scripts/restore.sh staging-seed${NC}"
echo ""
echo -e "${BLUE}Documentation:${NC}"
echo -e "   See STAGING_ENVIRONMENT.md for complete guide"
echo ""
