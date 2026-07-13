#!/bin/bash
# Run comprehensive integration tests

set -e

echo "=================================="
echo "Running Integration Tests"
echo "=================================="
echo ""
echo "Prerequisites:"
echo "- All services must be running (backend, postgres, meilisearch, neo4j)"
echo "- Use docker-compose.local.yml for local testing"
echo ""

# Check if services are running
if ! docker compose -f docker-compose.local.yml ps | grep -q "Up"; then
    echo "ERROR: Services are not running!"
    echo "Start them with: docker compose -f docker-compose.local.yml up -d"
    exit 1
fi

echo "Services are running. Starting tests..."
echo ""

# Clean up any existing test database
echo "Cleaning up any existing test database..."
docker compose -f docker-compose.local.yml exec -T db psql -U postgres -c "DROP DATABASE IF EXISTS test_entitydb;" > /dev/null 2>&1

# Run the integration tests
docker compose -f docker-compose.local.yml exec -T backend python manage.py test people.tests.test_integration_full_stack --verbosity=2

echo ""
echo "=================================="
echo "Integration Tests Complete"
echo "=================================="
