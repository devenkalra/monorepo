# Repository Reorganization - Quick Start

## TL;DR

Reorganize the repository to separate production code from development files, reducing Docker image size by ~60%.

## Before & After

### Before (Current)
```
data-backend/
├── *.md (40+ documentation files)
├── test_*.py (15+ test scripts)
├── check_*.py, analyze_*.py (10+ dev tools)
├── .circleci/, .github/
├── config/, people/, frontend/ (production code)
└── manage.py, requirements.txt, Dockerfile
```
**Docker image**: ~500MB

### After (Proposed)
```
data-backend/
├── docs/          # All documentation
├── tests/         # All tests
├── dev-tools/     # Development utilities
├── .dev/          # CI/CD configs
├── config/, people/, frontend/ (production code)
└── manage.py, requirements.txt, Dockerfile
```
**Docker image**: ~200MB (60% reduction)

---

## Quick Migration (5 minutes)

### Step 1: Run Migration Script
```bash
cd /home/ubuntu/monorepo/data-backend
./migrate_repo_structure.sh
```

This will:
- ✅ Move 40+ docs to `docs/`
- ✅ Move 15+ tests to `tests/`
- ✅ Move 10+ dev tools to `dev-tools/`
- ✅ Move CI/CD configs to `.dev/`
- ✅ Create README files in each directory

### Step 2: Update .dockerignore
```bash
# Backup current .dockerignore
cp .dockerignore .dockerignore.backup

# Use new .dockerignore
mv .dockerignore.new .dockerignore
```

### Step 3: Test Docker Build
```bash
# Build image
docker build -t data-backend:test .

# Check image size
docker images data-backend:test

# Should be ~200MB instead of ~500MB
```

### Step 4: Verify Tests Still Work
```bash
# Run integration tests
./tests/run_tests.sh

# Should see: "Ran 37 tests in ~98s - OK"
```

### Step 5: Commit Changes
```bash
git add .
git commit -m "Reorganize repository: separate production from development files"
```

---

## What Gets Excluded from Docker

### Excluded (via .dockerignore):
- ❌ `docs/` - All documentation
- ❌ `tests/` - All test files
- ❌ `dev-tools/` - Development utilities
- ❌ `.dev/` - CI/CD configs
- ❌ `*.md` (except README.md)
- ❌ Frontend tests and configs
- ❌ Development databases (chroma_db, vector_db)
- ❌ Media uploads (development)
- ❌ Logs and backups

### Included (production code):
- ✅ `config/` - Django settings
- ✅ `people/` - Main app (excluding tests/)
- ✅ `frontend/src/` - React source
- ✅ `static/` - Static files
- ✅ `scripts/` - Production scripts (backup, deploy)
- ✅ `manage.py`, `requirements.txt`
- ✅ `Dockerfile`, `docker-compose.yml`
- ✅ `README.md`

---

## Directory Guide

### 📁 `docs/` - All Documentation
```
docs/
├── deployment/      # Production deployment guides
├── setup/           # Local development setup
├── features/        # Feature documentation
├── testing/         # Testing guides
├── ci-cd/           # CI/CD setup
├── fixes/           # Bug fixes and resolutions
└── architecture/    # System architecture
```

**Access**: `cat docs/testing/TEST_SUITE_SUMMARY.md`

### 🧪 `tests/` - All Tests
```
tests/
├── integration/     # Integration tests (symlink)
├── unit/            # Unit tests (future)
├── scripts/         # Standalone test scripts
├── fixtures/        # Test data
└── run_tests.sh     # Test runner
```

**Run**: `./tests/run_tests.sh`

### 🔧 `dev-tools/` - Development Utilities
```
dev-tools/
├── analyze_*.py     # Analysis tools
├── check_*.py       # Verification scripts
├── convert_*.py     # Data conversion
├── debug_*.py       # Debugging tools
└── *.sh             # Helper scripts
```

**Use**: `python dev-tools/check_entities.py`

### ⚙️ `.dev/` - CI/CD Configs
```
.dev/
├── .circleci/               # CircleCI config
├── .github/                 # GitHub Actions
└── docker-compose.local.yml # Local dev compose
```

**Note**: Still use `docker-compose.local.yml` from root for local development

---

## Benefits

### 1. Smaller Docker Images
- **Before**: 500MB
- **After**: 200MB
- **Savings**: 60% reduction

### 2. Faster Deployments
- Less data to transfer
- Faster image pulls
- Quicker container starts

### 3. Better Security
- No test data in production
- No development scripts accessible
- Reduced attack surface

### 4. Clearer Organization
- Easy to find documentation
- Tests grouped together
- Dev tools separated from production code

### 5. Easier Maintenance
- Clear what's production vs development
- Simpler deployment scripts
- Better for new developers

---

## Common Tasks After Reorganization

### View Documentation
```bash
# List all docs
ls docs/

# Read specific doc
cat docs/testing/TEST_SUITE_SUMMARY.md

# Search docs
grep -r "deployment" docs/
```

### Run Tests
```bash
# All integration tests
./tests/run_tests.sh

# Specific test class
docker compose -f docker-compose.local.yml exec backend \
  python manage.py test people.tests.test_integration_full_stack.FileUploadTest

# Standalone test script
python tests/scripts/test_search.py
```

### Use Dev Tools
```bash
# Check entities
python dev-tools/check_entities.py

# Analyze import logs
python dev-tools/analyze_skip_log.py

# Clear test data
python dev-tools/clear_user_data.py --user testuser
```

### Update CI/CD
```bash
# Edit CircleCI config
vim .dev/.circleci/config.yml

# Edit GitHub Actions
vim .dev/.github/workflows/integration-tests.yml
```

---

## Rollback (if needed)

If something goes wrong:

```bash
# Option 1: Git reset
git reset --hard HEAD

# Option 2: Manual restore
./restore_original_structure.sh  # (if you create this)

# Option 3: Restore from backup
cp .dockerignore.backup .dockerignore
# Then manually move files back
```

---

## Deployment Updates

### Docker Build
No changes needed! The new `.dockerignore` handles exclusions automatically:
```bash
docker build -t myapp:latest .
```

### Docker Compose
Production `docker-compose.yml` remains unchanged:
```yaml
services:
  backend:
    build: .
    # All dev files automatically excluded
```

### CI/CD Pipelines
Update paths if they reference moved files:
```yaml
# Before
- run: cat TESTING.md

# After
- run: cat docs/testing/TESTING.md
```

---

## Verification Checklist

After migration, verify:

- [ ] Docker build succeeds
- [ ] Docker image size reduced (~200MB)
- [ ] All 37 tests pass
- [ ] Documentation accessible in `docs/`
- [ ] Dev tools work from `dev-tools/`
- [ ] CI/CD pipelines updated
- [ ] Local development still works
- [ ] Production deployment works

---

## FAQ

**Q: Will this break my local development?**
A: No! All files are still in the repository, just organized differently. Local development continues to work.

**Q: Do I need to update import paths in Python?**
A: No! Python imports remain the same. Only file locations changed, not module structure.

**Q: What about the tests in `people/tests/`?**
A: They stay there for Django test discovery. We just create a symlink in `tests/integration/` for convenience.

**Q: Can I still run tests the old way?**
A: Yes! `python manage.py test` still works exactly the same.

**Q: Will this affect production?**
A: Only positively! Smaller images, faster deployments, better security.

**Q: How do I undo this?**
A: Run `git reset --hard HEAD` before committing, or manually move files back.

---

## Next Steps

1. **Run migration**: `./migrate_repo_structure.sh`
2. **Update .dockerignore**: `mv .dockerignore.new .dockerignore`
3. **Test build**: `docker build -t test .`
4. **Verify tests**: `./tests/run_tests.sh`
5. **Commit**: `git add . && git commit -m "Reorganize repository structure"`
6. **Update team**: Share this guide with your team
7. **Update CI/CD**: Update any hardcoded paths in pipelines

---

## Support

For detailed information, see:
- [Full Documentation](docs/REPOSITORY_ORGANIZATION.md)
- [Testing Guide](docs/testing/TESTING.md)
- [Deployment Guide](docs/deployment/DEPLOYMENT_CHECKLIST.md)

For issues or questions, check the rollback section above or consult the team.
