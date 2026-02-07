# CircleCI Integration Test Setup

## Overview

This CircleCI configuration runs the comprehensive integration test suite for the data-backend application. It sets up all required services (PostgreSQL, MeiliSearch, Neo4j, Redis) and runs 21 integration tests that verify the entire stack works correctly.

## Configuration File

**Location**: `.circleci/config.yml`

## Services Configured

The CI pipeline runs the following services as Docker containers:

### 1. **Python 3.11** (Primary Container)
- Runs Django application
- Executes tests
- Handles migrations

### 2. **PostgreSQL 15.3**
- Primary database for entities, tags, relations
- Database: `entitydb`
- User: `postgres`
- Password: `postgres`

### 3. **MeiliSearch v1.5**
- Full-text search engine
- Master key: `masterKey`
- Analytics disabled for CI

### 4. **Neo4j 5 Community**
- Graph database for entity relations
- User: `neo4j`
- Password: `testpassword`
- APOC procedures enabled

### 5. **Redis 7.0**
- Caching and session storage

## Workflow

The CI pipeline has two jobs that run sequentially:

### 1. **Lint Job**
- Runs flake8 code quality checks
- Runs Django system checks
- Fast feedback on code quality issues

### 2. **Test Job** (runs after lint passes)
1. **Checkout code** from repository
2. **Install dependencies** from `requirements.txt`
3. **Wait for services** to be ready (with health checks)
4. **Run migrations** to set up database schema
5. **Run integration tests** (all 21 tests)
6. **Store test results** and artifacts

## Environment Variables

The following environment variables are configured:

### Django Settings
```yaml
DJANGO_SETTINGS_MODULE: config.settings
SECRET_KEY: test-secret-key-for-ci
DEBUG: "False"
ALLOWED_HOSTS: localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS: http://localhost:8000
```

### Database
```yaml
POSTGRES_DB: entitydb
POSTGRES_USER: postgres
POSTGRES_PASSWORD: postgres
POSTGRES_HOST: localhost
POSTGRES_PORT: 5432
DATABASE_URL: postgresql://postgres:postgres@localhost:5432/entitydb
```

### MeiliSearch
```yaml
MEILISEARCH_URL: http://localhost:7700
MEILI_MASTER_KEY: masterKey
```

### Neo4j
```yaml
NEO4J_URI: bolt://localhost:7687
NEO4J_USER: neo4j
NEO4J_PASSWORD: testpassword
```

### Redis
```yaml
REDIS_URL: redis://localhost:6379/0
```

## Setup Instructions

### 1. Enable CircleCI for Your Repository

1. Go to [CircleCI](https://circleci.com/)
2. Sign in with your GitHub/Bitbucket account
3. Click "Projects" in the sidebar
4. Find your repository and click "Set Up Project"
5. CircleCI will automatically detect the `.circleci/config.yml` file

### 2. Configure Project Settings (Optional)

If you need to add secrets or custom environment variables:

1. Go to Project Settings → Environment Variables
2. Add any sensitive values (API keys, passwords, etc.)
3. These will override the defaults in `config.yml`

### 3. Add Status Badge (Optional)

Add a build status badge to your README:

```markdown
[![CircleCI](https://circleci.com/gh/YOUR_USERNAME/YOUR_REPO.svg?style=svg)](https://circleci.com/gh/YOUR_USERNAME/YOUR_REPO)
```

## Service Health Checks

The configuration includes comprehensive health checks to ensure all services are ready before running tests:

### PostgreSQL Health Check
```bash
pg_isready -h localhost -p 5432 -U postgres
```
- Retries: 30 times
- Interval: 2 seconds
- Timeout: 60 seconds

### MeiliSearch Health Check
```bash
curl -f http://localhost:7700/health
```
- Retries: 30 times
- Interval: 2 seconds
- Timeout: 60 seconds

### Neo4j Health Check
```python
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'testpassword'))
driver.verify_connectivity()
```
- Retries: 60 times
- Interval: 2 seconds
- Timeout: 120 seconds

### Redis Health Check
```bash
redis-cli -h localhost ping
```
- Retries: 30 times
- Interval: 2 seconds
- Timeout: 60 seconds

## Test Execution

### Command
```bash
python manage.py test people.tests.test_integration_full_stack --verbosity=2
```

### Timeout
- **10 minutes** - Sufficient for all 21 tests (~80 seconds locally, may be slower in CI)

### Expected Results
```
Ran 21 tests in ~120s
OK
```

## Caching

The configuration caches Python dependencies to speed up subsequent builds:

**Cache Key**: `v1-dependencies-{{ checksum "requirements.txt" }}`

This means:
- ✅ Dependencies are cached between builds
- ✅ Cache is invalidated when `requirements.txt` changes
- ✅ Faster build times (skip pip install on cache hit)

## Test Results & Artifacts

### Test Results
- **Path**: `test-results/`
- **Format**: JUnit XML (if configured)
- **Usage**: CircleCI displays test results in the UI

### Artifacts
- **Path**: `test-results/`
- **Retention**: 30 days (CircleCI default)
- **Access**: Download from CircleCI UI

## Troubleshooting

### Tests Fail Due to Service Not Ready

**Symptom**: Connection refused errors
**Solution**: Increase wait time in health checks:
```yaml
for i in {1..60}; do  # Increase from 30 to 60
```

### Tests Timeout

**Symptom**: "no_output_timeout exceeded"
**Solution**: Increase timeout in test step:
```yaml
no_output_timeout: 15m  # Increase from 10m
```

### Migration Errors

**Symptom**: "table already exists" or "relation does not exist"
**Solution**: Ensure migrations are run in correct order:
```bash
python manage.py migrate --noinput
```

### MeiliSearch Indexing Issues

**Symptom**: Tests fail with "document not found"
**Solution**: Tests already include wait times, but you can increase them:
```python
self.wait_for_meilisearch(3)  # Increase from 2 to 3 seconds
```

### Out of Memory

**Symptom**: "Killed" or OOM errors
**Solution**: Use a larger resource class:
```yaml
resource_class: large  # Add to executor
```

## Performance Optimization

### Current Performance
- **Lint Job**: ~30-60 seconds
- **Test Job**: ~3-5 minutes
- **Total**: ~4-6 minutes

### Optimization Tips

1. **Parallel Test Execution**
   ```yaml
   parallelism: 4
   ```
   Split tests across multiple containers

2. **Docker Layer Caching**
   ```yaml
   setup_remote_docker:
     docker_layer_caching: true
   ```
   Cache Docker images (requires paid plan)

3. **Selective Testing**
   Only run tests for changed files:
   ```yaml
   - run:
       name: Run affected tests
       command: |
         # Custom logic to detect changed files
         python manage.py test --tag=affected
   ```

## Integration with GitHub

### Pull Request Checks

CircleCI automatically runs on:
- ✅ Every push to any branch
- ✅ Every pull request
- ✅ Can block merges if tests fail

### Status Checks

Configure required status checks in GitHub:
1. Go to Repository Settings → Branches
2. Add branch protection rule for `main`
3. Require status checks: `ci/circleci: test`

## Cost Considerations

### Free Tier (CircleCI)
- **Credits**: 30,000 credits/month
- **This Pipeline**: ~200-300 credits per run
- **Estimated Runs**: ~100-150 runs/month on free tier

### Optimization for Free Tier
1. Only run on pull requests and main branch
2. Skip CI on documentation-only changes
3. Use `[skip ci]` in commit messages when appropriate

## Example Workflow

```yaml
# Skip CI for docs-only changes
workflows:
  version: 2
  test-and-lint:
    jobs:
      - lint:
          filters:
            branches:
              ignore:
                - /docs-.*/
      - test:
          requires:
            - lint
          filters:
            branches:
              only:
                - main
                - develop
                - /feature-.*/
```

## Monitoring

### CircleCI Dashboard

Monitor builds at: `https://app.circleci.com/pipelines/github/YOUR_USERNAME/YOUR_REPO`

### Key Metrics
- ✅ Success rate
- ⏱️ Build duration
- 💰 Credit usage
- 📊 Test trends

### Notifications

Configure notifications in CircleCI:
1. Project Settings → Notifications
2. Options:
   - Email on failure
   - Slack integration
   - Webhook on status change

## Next Steps

1. **Enable CircleCI** for your repository
2. **Push a commit** to trigger first build
3. **Monitor results** in CircleCI dashboard
4. **Configure branch protection** in GitHub
5. **Add status badge** to README

## Support

- **CircleCI Docs**: https://circleci.com/docs/
- **Test Suite Docs**: See `INTEGRATION_TESTS.md`
- **Troubleshooting**: See `TEST_FIXES_SUMMARY.md`

## Summary

This CircleCI configuration provides:
- ✅ Comprehensive integration testing
- ✅ All services properly configured
- ✅ Health checks for reliability
- ✅ Fast feedback with caching
- ✅ Test result artifacts
- ✅ Easy to maintain and extend

The pipeline ensures that every code change is tested against the full stack (Django + PostgreSQL + MeiliSearch + Neo4j + Redis) before merging.
