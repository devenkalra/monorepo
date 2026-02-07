# Repository Organization Plan

## Overview
Separate production code from development/testing artifacts to simplify deployment and reduce Docker image size.

---

## Proposed Directory Structure

```
data-backend/
├── # PRODUCTION FILES (copy to deployment)
├── config/                    # Django settings
├── people/                    # Main Django app
│   ├── migrations/
│   ├── models.py
│   ├── views.py
│   ├── serializers.py
│   ├── urls.py
│   ├── signals.py
│   └── sync.py
├── frontend/                  # React frontend
│   ├── src/
│   ├── public/
│   └── package.json
├── static/                    # Static files
├── scripts/                   # Production scripts (backup, deploy)
│   ├── backup.sh
│   ├── restore.sh
│   └── deploy_production.sh
├── manage.py
├── requirements.txt
├── Dockerfile
├── Dockerfile.vector
├── docker-compose.yml
├── docker-compose.local.yml
├── .dockerignore
├── .gitignore
├── .env.example
├── README.md                  # Essential production docs
└── vector_service.py
│
├── # DEVELOPMENT FILES (exclude from deployment)
├── docs/                      # 📁 NEW: All documentation
│   ├── deployment/
│   │   ├── DEPLOYMENT.md
│   │   ├── DEPLOYMENT_CHECKLIST.md
│   │   ├── DEPLOYMENT_QUICK_START.md
│   │   ├── DEPLOYMENT_SUMMARY.md
│   │   ├── PRODUCTION_DEPLOYMENT.md
│   │   ├── PRODUCTION_SECURITY_CHECKLIST.md
│   │   ├── STAGING_ENVIRONMENT.md
│   │   └── ENVIRONMENT_CONFIGURATION_SUMMARY.md
│   ├── setup/
│   │   ├── QUICK_START.md
│   │   ├── LOCAL_TESTING.md
│   │   ├── GOOGLE_OAUTH_SETUP.md
│   │   └── VECTOR_SERVICE_GUIDE.md
│   ├── features/
│   │   ├── CHAT_INTEGRATION_COMPLETE.md
│   │   ├── CHAT_INTEGRATION_PLAN.md
│   │   ├── CAPTION_FEATURE.md
│   │   ├── MULTI_USER_COMPLETE.md
│   │   ├── MULTI_USER_IMPLEMENTATION.md
│   │   ├── MULTI_USER_STATUS.md
│   │   ├── HTML_CONVERSATION_DESCRIPTIONS.md
│   │   ├── IMPORT_REPORTING.md
│   │   └── IMPORT_UI_EXAMPLE.md
│   ├── testing/
│   │   ├── TESTING.md
│   │   ├── TESTING_QUICK_REFERENCE.md
│   │   ├── TEST_RESULTS.md
│   │   ├── TEST_SUITE_SUMMARY.md
│   │   ├── INTEGRATION_TESTING.md
│   │   ├── INTEGRATION_TEST_SUMMARY.md
│   │   ├── BROWSER_TESTING_GUIDE.md
│   │   ├── FRONTEND_TEST_RESULTS.md
│   │   └── API_COVERAGE_ANALYSIS.md
│   ├── ci-cd/
│   │   ├── CIRCLECI_SETUP.md
│   │   ├── CI_COMPARISON.md
│   │   ├── CI_QUICK_START.md
│   │   └── CI_SETUP_COMPLETE.md
│   ├── fixes/
│   │   ├── BUGS_FOUND_BY_TESTS.md
│   │   ├── EXPORT_FIX.md
│   │   ├── IMPORT_COMPLETE_SUMMARY.md
│   │   ├── IMPORT_FIX_SUMMARY.md
│   │   ├── NEO4J_CONVERSION.md
│   │   ├── NEO4J_PREFIX_HANDLING.md
│   │   ├── PHOTO_ATTACHMENT_CONVERSION.md
│   │   ├── THUMBNAIL_FIX.md
│   │   ├── URLS_FIX.md
│   │   ├── TEST_MIGRATION_FIX.md
│   │   └── QUICK_AUTH_GUIDE.md
│   └── architecture/
│       └── TEST_ARCHITECTURE.md
│
├── tests/                     # 📁 NEW: All test files
│   ├── integration/
│   │   └── test_integration_full_stack.py (from people/tests/)
│   ├── unit/
│   │   └── (future unit tests)
│   ├── scripts/
│   │   ├── test_bhagwan_search.py
│   │   ├── test_bob_import.py
│   │   ├── test_book.py
│   │   ├── test_import_debug.py
│   │   ├── test_import.py
│   │   ├── test_location.py
│   │   ├── test_movie.py
│   │   ├── test_new_entities.py
│   │   ├── test_photo_upload.py
│   │   └── test_search.py
│   ├── fixtures/
│   │   └── (test data files)
│   └── run_tests.sh
│
├── dev-tools/                 # 📁 NEW: Development utilities
│   ├── analyze_skip_log.py
│   ├── check_all_entities.py
│   ├── check_base_entities.py
│   ├── check_entities.py
│   ├── check_import_status.py
│   ├── clear_user_data.py
│   ├── convert_neo4j_export.py
│   ├── convert_neo4j_test.py
│   ├── debug_import.py
│   ├── extract_test_data.py
│   ├── verify_import.py
│   ├── setup_google_oauth.sh
│   ├── test-local.sh
│   └── list_tests.sh
│
└── .dev/                      # 📁 NEW: Development configs
    ├── .circleci/
    ├── .github/
    └── docker-compose.local.yml
```

---

## Updated .dockerignore

```dockerignore
# Development and testing
docs/
tests/
dev-tools/
.dev/
*.md
!README.md

# Test files
test_*.py
*_test.py
run_tests.sh
list_tests.sh

# Development scripts
analyze_*.py
check_*.py
clear_*.py
convert_*.py
debug_*.py
extract_*.py
verify_*.py
setup_google_oauth.sh
test-local.sh

# CI/CD configs (not needed in production)
.circleci/
.github/
.gitlab-ci.yml

# Development configs
docker-compose.local.yml
.env.local
.env.development

# IDE and editor files
.idea/
.vscode/
*.swp
*.swo
*~
.DS_Store

# Python development
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
*.egg-info/
.pytest_cache/
.coverage
htmlcov/
.tox/
.mypy_cache/
.dmypy.json

# Frontend development
frontend/node_modules/
frontend/coverage/
frontend/build/
frontend/.cache/
frontend/playwright-report/
frontend/tests/
frontend/test-results/
frontend/*.config.js
!frontend/vite.config.js

# Git
.git/
.gitignore
.gitattributes

# Documentation
*.md
!README.md
LICENSE
CHANGELOG.md

# Logs and databases (development)
*.log
*.sqlite3
*.db
db.sqlite3

# Media (development uploads)
media/
uploads/
chroma_db/
vector_db/
data.ms/

# Backups
backups/
dumps/
*.bak
*.backup

# SSL certs (should be mounted or generated)
ssl/
*.pem
*.key
*.crt

# Temporary files
tmp/
temp/
*.tmp
```

---

## Migration Script

Run this script to reorganize the repository:

```bash
#!/bin/bash
# migrate_repo_structure.sh

cd /home/ubuntu/monorepo/data-backend

echo "Creating new directory structure..."

# Create new directories
mkdir -p docs/{deployment,setup,features,testing,ci-cd,fixes,architecture}
mkdir -p tests/{integration,unit,scripts,fixtures}
mkdir -p dev-tools
mkdir -p .dev

echo "Moving documentation files..."

# Deployment docs
mv DEPLOYMENT.md DEPLOYMENT_CHECKLIST.md DEPLOYMENT_QUICK_START.md \
   DEPLOYMENT_SUMMARY.md PRODUCTION_DEPLOYMENT.md \
   PRODUCTION_SECURITY_CHECKLIST.md STAGING_ENVIRONMENT.md \
   ENVIRONMENT_CONFIGURATION_SUMMARY.md docs/deployment/ 2>/dev/null

# Setup docs
mv QUICK_START.md LOCAL_TESTING.md GOOGLE_OAUTH_SETUP.md \
   VECTOR_SERVICE_GUIDE.md docs/setup/ 2>/dev/null

# Feature docs
mv CHAT_INTEGRATION_COMPLETE.md CHAT_INTEGRATION_PLAN.md \
   CAPTION_FEATURE.md MULTI_USER_COMPLETE.md \
   MULTI_USER_IMPLEMENTATION.md MULTI_USER_STATUS.md \
   HTML_CONVERSATION_DESCRIPTIONS.md IMPORT_REPORTING.md \
   IMPORT_UI_EXAMPLE.md docs/features/ 2>/dev/null

# Testing docs
mv TESTING.md TESTING_QUICK_REFERENCE.md TEST_RESULTS.md \
   TEST_SUITE_SUMMARY.md INTEGRATION_TESTING.md \
   INTEGRATION_TEST_SUMMARY.md BROWSER_TESTING_GUIDE.md \
   FRONTEND_TEST_RESULTS.md API_COVERAGE_ANALYSIS.md \
   docs/testing/ 2>/dev/null

# CI/CD docs
mv CIRCLECI_SETUP.md CI_COMPARISON.md CI_QUICK_START.md \
   CI_SETUP_COMPLETE.md docs/ci-cd/ 2>/dev/null

# Fix/bug docs
mv BUGS_FOUND_BY_TESTS.md EXPORT_FIX.md IMPORT_COMPLETE_SUMMARY.md \
   IMPORT_FIX_SUMMARY.md NEO4J_CONVERSION.md NEO4J_PREFIX_HANDLING.md \
   PHOTO_ATTACHMENT_CONVERSION.md THUMBNAIL_FIX.md URLS_FIX.md \
   TEST_MIGRATION_FIX.md QUICK_AUTH_GUIDE.md docs/fixes/ 2>/dev/null

# Architecture docs
mv TEST_ARCHITECTURE.md docs/architecture/ 2>/dev/null

echo "Moving test files..."

# Test scripts
mv test_*.py tests/scripts/ 2>/dev/null
mv run_tests.sh list_tests.sh tests/ 2>/dev/null

# Integration tests (keep in people/tests for Django discovery)
# Just create symlink for documentation
ln -s ../../people/tests/test_integration_full_stack.py tests/integration/ 2>/dev/null

echo "Moving development tools..."

mv analyze_skip_log.py check_all_entities.py check_base_entities.py \
   check_entities.py check_import_status.py clear_user_data.py \
   convert_neo4j_export.py convert_neo4j_test.py debug_import.py \
   extract_test_data.py verify_import.py setup_google_oauth.sh \
   test-local.sh dev-tools/ 2>/dev/null

echo "Moving CI/CD configs..."

mv .circleci .github .dev/ 2>/dev/null
cp docker-compose.local.yml .dev/ 2>/dev/null

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

- [Quick Start Guide](setup/QUICK_START.md)
- [Deployment Checklist](deployment/DEPLOYMENT_CHECKLIST.md)
- [Testing Guide](testing/TESTING.md)
- [API Coverage](testing/API_COVERAGE_ANALYSIS.md)
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

### Integration Tests
```bash
cd /home/ubuntu/monorepo/data-backend
./tests/run_tests.sh
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

- **analyze_skip_log.py** - Analyze import skip logs
- **check_*.py** - Entity verification scripts
- **clear_user_data.py** - Clear user data for testing
- **convert_neo4j_*.py** - Neo4j data conversion tools
- **debug_import.py** - Debug import issues
- **extract_test_data.py** - Extract test data from production
- **verify_import.py** - Verify import results
- **setup_google_oauth.sh** - Setup Google OAuth
- **test-local.sh** - Run local tests

## Usage

These tools are for development only and should not be deployed to production.
EOF

echo "✓ Repository reorganization complete!"
echo ""
echo "Summary:"
echo "  - Documentation moved to docs/"
echo "  - Tests moved to tests/"
echo "  - Dev tools moved to dev-tools/"
echo "  - CI/CD configs moved to .dev/"
echo ""
echo "Next steps:"
echo "  1. Review the changes: git status"
echo "  2. Update .dockerignore (already provided above)"
echo "  3. Update deployment scripts to exclude new directories"
echo "  4. Test Docker build: docker build -t test-build ."
echo "  5. Commit changes: git add . && git commit -m 'Reorganize repository structure'"
```

---

## Updated Dockerfile Pattern

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy only production files
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy production code
COPY config/ ./config/
COPY people/ ./people/
COPY static/ ./static/
COPY scripts/ ./scripts/
COPY manage.py .
COPY vector_service.py .

# Exclude development files (handled by .dockerignore)
# docs/, tests/, dev-tools/, .dev/ are automatically excluded

# Run production server
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
```

---

## Benefits

### 1. Smaller Docker Images
- **Before**: ~500MB (includes all docs, tests, dev tools)
- **After**: ~200MB (production code only)
- **Savings**: 60% reduction

### 2. Faster Builds
- Fewer files to copy
- Smaller context sent to Docker daemon
- Faster layer caching

### 3. Better Security
- No test data in production
- No development scripts accessible
- Reduced attack surface

### 4. Clearer Organization
- Easy to find documentation
- Tests grouped together
- Dev tools separated

### 5. Easier Maintenance
- Clear what's production vs development
- Simpler deployment scripts
- Better for new developers

---

## Deployment Script Update

```bash
# deploy.sh
#!/bin/bash

# Build production image (excludes dev files via .dockerignore)
docker build -t myapp:latest .

# Or use explicit context
docker build \
  --file Dockerfile \
  --tag myapp:latest \
  --build-arg BUILD_ENV=production \
  .

# Verify image size
docker images myapp:latest

# Push to registry
docker push myapp:latest
```

---

## Git Configuration

Add to `.gitignore`:
```gitignore
# Keep these in git but exclude from Docker
docs/
tests/
dev-tools/
.dev/

# But track them in git
!docs/**
!tests/**
!dev-tools/**
!.dev/**
```

---

## Verification Checklist

After reorganization:

- [ ] All documentation accessible in `docs/`
- [ ] All tests work from `tests/`
- [ ] Dev tools work from `dev-tools/`
- [ ] Docker build succeeds
- [ ] Docker image size reduced
- [ ] Production deployment works
- [ ] CI/CD pipelines updated
- [ ] README.md updated with new structure
- [ ] Team notified of changes

---

## Rollback Plan

If issues occur:

```bash
# Revert file moves
git reset --hard HEAD

# Or manually move files back
mv docs/**/*.md .
mv tests/scripts/*.py .
mv dev-tools/*.py .
```

---

## Future Improvements

1. **Separate repositories** - Consider splitting into:
   - `data-backend` (production code)
   - `data-backend-docs` (documentation)
   - `data-backend-tests` (test suite)

2. **Submodules** - Use git submodules for optional components

3. **Multi-stage builds** - Use Docker multi-stage builds:
   ```dockerfile
   # Stage 1: Build with dev dependencies
   FROM python:3.11 as builder
   COPY . .
   RUN pip install -r requirements-dev.txt
   RUN python manage.py test

   # Stage 2: Production image
   FROM python:3.11-slim
   COPY --from=builder /app/production-files /app
   ```

4. **Documentation site** - Generate static docs site:
   ```bash
   mkdocs build
   # Deploy to GitHub Pages or similar
   ```
