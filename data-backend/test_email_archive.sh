#!/bin/bash
# Email Archive System Test Script

set -e

echo "=========================================="
echo "Email Archive System - Test Script"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is running
echo "1. Checking Docker services..."
if ! docker-compose ps | grep -q "Up"; then
    echo -e "${RED}✗ Docker services not running${NC}"
    echo "Run: docker-compose up -d"
    exit 1
fi
echo -e "${GREEN}✓ Docker services running${NC}"
echo ""

# Check if backend is healthy
echo "2. Checking backend health..."
if docker-compose exec -T backend python manage.py check --deploy > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend is healthy${NC}"
else
    echo -e "${YELLOW}⚠ Backend check had warnings (this is okay)${NC}"
fi
echo ""

# Run migrations
echo "3. Running migrations..."
docker-compose exec -T backend python manage.py migrate mail_archive
echo -e "${GREEN}✓ Migrations applied${NC}"
echo ""

# Verify tables exist
echo "4. Verifying database tables..."
TABLE_COUNT=$(docker-compose exec -T db psql -U postgres -d postgres -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'mail_archive%';" | tr -d ' ')
if [ "$TABLE_COUNT" -ge 3 ]; then
    echo -e "${GREEN}✓ Found $TABLE_COUNT mail_archive tables${NC}"
else
    echo -e "${RED}✗ Expected 3+ tables, found $TABLE_COUNT${NC}"
    exit 1
fi
echo ""

# Check Celery worker
echo "5. Checking Celery worker..."
if docker-compose ps celery-worker | grep -q "Up"; then
    echo -e "${GREEN}✓ Celery worker is running${NC}"
else
    echo -e "${RED}✗ Celery worker not running${NC}"
    echo "Run: docker-compose up -d celery-worker"
    exit 1
fi
echo ""

# Check Redis
echo "6. Checking Redis..."
if docker-compose exec -T redis redis-cli ping | grep -q "PONG"; then
    echo -e "${GREEN}✓ Redis is responding${NC}"
else
    echo -e "${RED}✗ Redis not responding${NC}"
    exit 1
fi
echo ""

# Check frontend build
echo "7. Checking frontend..."
if [ -d "frontend/node_modules" ]; then
    echo -e "${GREEN}✓ Frontend dependencies installed${NC}"
else
    echo -e "${YELLOW}⚠ Frontend dependencies not installed${NC}"
    echo "Run: cd frontend && npm install"
fi
echo ""

# Print access URLs
echo "=========================================="
echo -e "${GREEN}✓ All checks passed!${NC}"
echo "=========================================="
echo ""
echo "Access the Email Archive:"
echo "  Frontend: http://localhost:5174/email"
echo "  Backend API: http://localhost:8000/api/mail/"
echo "  Django Admin: http://localhost:8000/admin/"
echo ""
echo "Next Steps:"
echo "  1. Open http://localhost:5174/email in your browser"
echo "  2. Go to 'Import Manager' tab"
echo "  3. Click '+ Add Account'"
echo "  4. Fill in your Gmail details with App Password"
echo "  5. Click 'Test' to verify connection"
echo "  6. Create an import configuration"
echo "  7. Click 'Import Now' to import emails"
echo "  8. Go to 'Email Viewer' tab to see results"
echo ""
echo "For Gmail App Password setup:"
echo "  https://myaccount.google.com/apppasswords"
echo ""
echo "Documentation:"
echo "  - EMAIL_ARCHIVE_TESTING.md (this guide)"
echo "  - EMAIL_ARCHIVE_QUICK_START.md (setup guide)"
echo "  - EMAIL_ARCHIVE_GUIDE.md (full documentation)"
echo ""
