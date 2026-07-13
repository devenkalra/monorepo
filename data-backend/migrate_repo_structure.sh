#!/bin/bash
# migrate_repo_structure.sh
# Reorganizes repository to separate production code from development artifacts

set -e  # Exit on error

cd "$(dirname "$0")"

echo "================================================"
echo "Repository Structure Migration"
echo "================================================"
echo ""
echo "This script will reorganize the repository to:"
echo "  - Move documentation to docs/"
echo "  - Move tests to tests/"
echo "  - Move dev tools to dev-tools/"
echo "  - Move CI/CD configs to .dev/"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "Creating new directory structure..."

# Create new directories
mkdir -p docs/{deployment,setup,features,testing,ci-cd,fixes,architecture}
mkdir -p tests/{integration,unit,scripts,fixtures}
mkdir -p dev-tools
mkdir -p .dev

echo "✓ Directories created"
echo ""
echo "Moving documentation files..."

# Deployment docs
for file in DEPLOYMENT.md DEPLOYMENT_CHECKLIST.md DEPLOYMENT_QUICK_START.md \
            DEPLOYMENT_SUMMARY.md PRODUCTION_DEPLOYMENT.md \
            PRODUCTION_SECURITY_CHECKLIST.md STAGING_ENVIRONMENT.md \
            ENVIRONMENT_CONFIGURATION_SUMMARY.md; do
    [ -f "$file" ] && mv "$file" docs/deployment/ && echo "  → docs/deployment/$file"
done

# Setup docs
for file in QUICK_START.md LOCAL_TESTING.md GOOGLE_OAUTH_SETUP.md \
            VECTOR_SERVICE_GUIDE.md; do
    [ -f "$file" ] && mv "$file" docs/setup/ && echo "  → docs/setup/$file"
done

# Feature docs
for file in CHAT_INTEGRATION_COMPLETE.md CHAT_INTEGRATION_PLAN.md \
            CAPTION_FEATURE.md MULTI_USER_COMPLETE.md \
            MULTI_USER_IMPLEMENTATION.md MULTI_USER_STATUS.md \
            HTML_CONVERSATION_DESCRIPTIONS.md IMPORT_REPORTING.md \
            IMPORT_UI_EXAMPLE.md; do
    [ -f "$file" ] && mv "$file" docs/features/ && echo "  → docs/features/$file"
done

# Testing docs
for file in TESTING.md TESTING_QUICK_REFERENCE.md TEST_RESULTS.md \
            TEST_SUITE_SUMMARY.md INTEGRATION_TESTING.md \
            INTEGRATION_TEST_SUMMARY.md BROWSER_TESTING_GUIDE.md \
            FRONTEND_TEST_RESULTS.md API_COVERAGE_ANALYSIS.md; do
    [ -f "$file" ] && mv "$file" docs/testing/ && echo "  → docs/testing/$file"
done

# CI/CD docs
for file in CIRCLECI_SETUP.md CI_COMPARISON.md CI_QUICK_START.md \
            CI_SETUP_COMPLETE.md; do
    [ -f "$file" ] && mv "$file" docs/ci-cd/ && echo "  → docs/ci-cd/$file"
done

# Fix/bug docs
for file in BUGS_FOUND_BY_TESTS.md EXPORT_FIX.md IMPORT_COMPLETE_SUMMARY.md \
            IMPORT_FIX_SUMMARY.md NEO4J_CONVERSION.md NEO4J_PREFIX_HANDLING.md \
            PHOTO_ATTACHMENT_CONVERSION.md THUMBNAIL_FIX.md URLS_FIX.md \
            TEST_MIGRATION_FIX.md QUICK_AUTH_GUIDE.md; do
    [ -f "$file" ] && mv "$file" docs/fixes/ && echo "  → docs/fixes/$file"
done

# Architecture docs
for file in TEST_ARCHITECTURE.md; do
    [ -f "$file" ] && mv "$file" docs/architecture/ && echo "  → docs/architecture/$file"
done

# Keep REPOSITORY_ORGANIZATION.md in docs/
[ -f "REPOSITORY_ORGANIZATION.md" ] && mv "REPOSITORY_ORGANIZATION.md" docs/ && echo "  → docs/REPOSITORY_ORGANIZATION.md"

echo ""
echo "Moving test files..."

# Test scripts
for file in test_*.py; do
    [ -f "$file" ] && mv "$file" tests/scripts/ && echo "  → tests/scripts/$file"
done

# Test runner scripts
for file in run_tests.sh list_tests.sh; do
    [ -f "$file" ] && mv "$file" tests/ && echo "  → tests/$file"
done

# Make test scripts executable
chmod +x tests/*.sh 2>/dev/null || true

# Create symlink to integration tests (keep in people/tests for Django discovery)
if [ -f "people/tests/test_integration_full_stack.py" ]; then
    ln -sf ../../people/tests/test_integration_full_stack.py tests/integration/test_integration_full_stack.py 2>/dev/null || true
    echo "  → tests/integration/ (symlink created)"
fi

echo ""
echo "Moving development tools..."

# Dev tools
for file in analyze_skip_log.py check_all_entities.py check_base_entities.py \
            check_entities.py check_import_status.py clear_user_data.py \
            convert_neo4j_export.py convert_neo4j_test.py debug_import.py \
            extract_test_data.py verify_import.py setup_google_oauth.sh \
            test-local.sh; do
    [ -f "$file" ] && mv "$file" dev-tools/ && echo "  → dev-tools/$file"
done

# Make dev tool scripts executable
chmod +x dev-tools/*.sh 2>/dev/null || true

echo ""
echo "Moving CI/CD configs..."

# Move CI/CD directories
if [ -d ".circleci" ]; then
    mv .circleci .dev/ && echo "  → .dev/.circleci/"
fi

if [ -d ".github" ]; then
    mv .github .dev/ && echo "  → .dev/.github/"
fi

# Copy (don't move) docker-compose.local.yml as it's still used locally
if [ -f "docker-compose.local.yml" ]; then
    cp docker-compose.local.yml .dev/ && echo "  → .dev/docker-compose.local.yml (copied)"
fi

echo ""
echo "Creating README files..."

# Create README in docs
cat > docs/README.md << 'EOF'
# Documentation

This directory contains all project documentation organized by category.

## Directory Structure

- **deployment/** - Production deployment guides and checklists
- **setup/** - Local development setup instructions
- **features/** - Feature implementation documentation
- **testing/** - Testing guides and results
- **ci-cd/** - CI/CD setup and configuration
- **fixes/** - Bug fixes and issue resolutions
- **architecture/** - System architecture documentation

## Quick Links

- [Repository Organization](REPOSITORY_ORGANIZATION.md)
- [Quick Start Guide](setup/QUICK_START.md)
- [Deployment Checklist](deployment/DEPLOYMENT_CHECKLIST.md)
- [Testing Guide](testing/TESTING.md)
- [API Coverage](testing/API_COVERAGE_ANALYSIS.md)
- [Bugs Found](fixes/BUGS_FOUND_BY_TESTS.md)
EOF

# Create README in tests
cat > tests/README.md << 'EOF'
# Tests

This directory contains all test files and testing utilities.

## Directory Structure

- **integration/** - Integration tests (symlink to people/tests/)
- **unit/** - Unit tests (future)
- **scripts/** - Standalone test scripts
- **fixtures/** - Test data and fixtures

## Running Tests

### All Integration Tests
```bash
cd /home/ubuntu/monorepo/data-backend
./tests/run_tests.sh
```

### Specific Test Class
```bash
docker compose -f docker-compose.local.yml exec backend \
  python manage.py test people.tests.test_integration_full_stack.AllEntityTypesCRUDTest
```

### Individual Test Scripts
```bash
python tests/scripts/test_search.py
```

See [Testing Documentation](../docs/testing/) for more details.
EOF

# Create README in dev-tools
cat > dev-tools/README.md << 'EOF'
# Development Tools

This directory contains development utilities and helper scripts.

## Available Tools

### Data Analysis
- **analyze_skip_log.py** - Analyze import skip logs

### Entity Verification
- **check_all_entities.py** - Check all entities
- **check_base_entities.py** - Check base entities
- **check_entities.py** - Entity verification
- **check_import_status.py** - Check import status

### Data Management
- **clear_user_data.py** - Clear user data for testing
- **extract_test_data.py** - Extract test data from production
- **verify_import.py** - Verify import results

### Conversion Tools
- **convert_neo4j_export.py** - Convert Neo4j exports
- **convert_neo4j_test.py** - Test Neo4j conversion

### Debugging
- **debug_import.py** - Debug import issues

### Setup Scripts
- **setup_google_oauth.sh** - Setup Google OAuth
- **test-local.sh** - Run local tests

## Usage

These tools are for development only and should not be deployed to production.

### Example
```bash
# Check import status
python dev-tools/check_import_status.py

# Clear test user data
python dev-tools/clear_user_data.py --user testuser
```
EOF

# Create README in .dev
cat > .dev/README.md << 'EOF'
# Development Configuration

This directory contains CI/CD configurations and development-specific files.

## Contents

- **.circleci/** - CircleCI configuration
- **.github/** - GitHub Actions workflows
- **docker-compose.local.yml** - Local development Docker Compose

## Usage

These configurations are for development and CI/CD only.
They are excluded from production Docker images via `.dockerignore`.
EOF

echo "✓ README files created"
echo ""
echo "================================================"
echo "✓ Repository reorganization complete!"
echo "================================================"
echo ""
echo "Summary:"
echo "  📁 Documentation moved to docs/"
echo "  🧪 Tests moved to tests/"
echo "  🔧 Dev tools moved to dev-tools/"
echo "  ⚙️  CI/CD configs moved to .dev/"
echo ""
echo "File counts:"
echo "  docs/: $(find docs -type f | wc -l) files"
echo "  tests/: $(find tests -type f | wc -l) files"
echo "  dev-tools/: $(find dev-tools -type f | wc -l) files"
echo "  .dev/: $(find .dev -type f 2>/dev/null | wc -l) files"
echo ""
echo "Next steps:"
echo "  1. Review the changes:"
echo "     git status"
echo ""
echo "  2. Update .dockerignore (see REPOSITORY_ORGANIZATION.md)"
echo ""
echo "  3. Test Docker build:"
echo "     docker build -t test-build ."
echo ""
echo "  4. Verify tests still work:"
echo "     ./tests/run_tests.sh"
echo ""
echo "  5. Commit changes:"
echo "     git add ."
echo "     git commit -m 'Reorganize repository structure'"
echo ""
echo "For rollback instructions, see docs/REPOSITORY_ORGANIZATION.md"
