# CI/CD Quick Start Guide

## 🚀 Get Your Tests Running in CI in 5 Minutes

This guide will help you set up continuous integration for your integration test suite.

## Option 1: GitHub Actions (Recommended for GitHub Users)

### ✅ Pros
- Already configured and ready to go
- Zero additional setup needed
- Free for public repos, 2000 minutes/month for private

### 📋 Steps

1. **Verify the configuration file exists**
   ```bash
   ls .github/workflows/integration-tests.yml
   ```
   ✅ File already exists in your repo!

2. **Commit and push to GitHub**
   ```bash
   git add .github/workflows/integration-tests.yml
   git commit -m "Add GitHub Actions CI configuration"
   git push origin main
   ```

3. **Watch it run!**
   - Go to: `https://github.com/YOUR_USERNAME/YOUR_REPO/actions`
   - You'll see the workflow running
   - Wait ~4-5 minutes for completion

4. **Add status badge to README** (optional)
   ```markdown
   [![Tests](https://github.com/YOUR_USERNAME/YOUR_REPO/workflows/Integration%20Tests/badge.svg)](https://github.com/YOUR_USERNAME/YOUR_REPO/actions)
   ```

### ✅ Done!
Your tests will now run automatically on every push and pull request.

---

## Option 2: CircleCI

### ✅ Pros
- Better free tier for private repos (30,000 credits/month)
- Superior debugging tools (SSH into builds)
- Works with GitHub, Bitbucket, GitLab

### 📋 Steps

1. **Verify the configuration file exists**
   ```bash
   ls .circleci/config.yml
   ```
   ✅ File already exists in your repo!

2. **Sign up for CircleCI**
   - Go to: https://circleci.com/signup/
   - Click "Sign Up with GitHub"
   - Authorize CircleCI

3. **Add your project**
   - Click "Projects" in sidebar
   - Find your repository
   - Click "Set Up Project"
   - CircleCI detects `.circleci/config.yml` automatically
   - Click "Start Building"

4. **Watch it run!**
   - CircleCI dashboard shows build progress
   - Wait ~4-5 minutes for completion

5. **Add status badge to README** (optional)
   ```markdown
   [![CircleCI](https://circleci.com/gh/YOUR_USERNAME/YOUR_REPO.svg?style=svg)](https://circleci.com/gh/YOUR_USERNAME/YOUR_REPO)
   ```

### ✅ Done!
Your tests will now run automatically on every push and pull request.

---

## What Happens in CI?

Both platforms run the same comprehensive test suite:

### 1. **Setup Services** (~60 seconds)
   - PostgreSQL 15
   - MeiliSearch v1.5
   - Neo4j 5
   - Redis 7

### 2. **Install Dependencies** (~30 seconds)
   - Python 3.11
   - All packages from `requirements.txt`

### 3. **Run Migrations** (~10 seconds)
   - Create database schema
   - Set up tables

### 4. **Run Tests** (~80 seconds)
   - All 21 integration tests
   - Full stack verification

### 5. **Store Results** (~5 seconds)
   - Upload test results
   - Save artifacts

### Total Time: ~3-4 minutes

---

## Verify It's Working

### Success Indicators

✅ **GitHub Actions**:
- Green checkmark on commits
- "All checks have passed" on PRs
- Build log shows: `Ran 21 tests in ~80s OK`

✅ **CircleCI**:
- Green status in dashboard
- Email notification (if configured)
- Build log shows: `Ran 21 tests in ~80s OK`

### If Tests Fail

1. **Check the logs**
   - GitHub: Click on failed check → View details
   - CircleCI: Click on failed build → View logs

2. **Common issues**:
   - Service not ready (increase wait time)
   - Migration errors (check database schema)
   - Timeout (increase timeout in config)

3. **Debug locally**:
   ```bash
   ./run_integration_tests.sh
   ```
   If tests pass locally but fail in CI, it's likely a timing issue.

---

## Configure Branch Protection

Prevent merging broken code:

### GitHub

1. Go to: Settings → Branches
2. Add rule for `main` branch
3. Check "Require status checks to pass"
4. Select: `test` (GitHub Actions) or `ci/circleci: test` (CircleCI)
5. Save

### Result
- ✅ Can't merge if tests fail
- ✅ Can't merge if tests haven't run
- ✅ Code quality guaranteed

---

## Advanced Configuration

### Run Tests Only on Specific Branches

**GitHub Actions** (`.github/workflows/integration-tests.yml`):
```yaml
on:
  push:
    branches: [ main, develop ]  # Only these branches
  pull_request:
    branches: [ main ]  # Only PRs to main
```

**CircleCI** (`.circleci/config.yml`):
```yaml
workflows:
  test-and-lint:
    jobs:
      - test:
          filters:
            branches:
              only:
                - main
                - develop
```

### Skip CI on Certain Commits

Add `[skip ci]` to commit message:
```bash
git commit -m "Update README [skip ci]"
```

### Run Tests in Parallel

**GitHub Actions**:
```yaml
strategy:
  matrix:
    python-version: [3.9, 3.10, 3.11]
```

**CircleCI**:
```yaml
parallelism: 4
```

---

## Cost Estimates

### GitHub Actions (Private Repo)

- **Free tier**: 2,000 minutes/month
- **Per build**: ~5 minutes
- **Builds per month**: ~400 builds (free)
- **Cost**: $0 for typical usage

### CircleCI (Private Repo)

- **Free tier**: 30,000 credits/month
- **Per build**: ~250 credits
- **Builds per month**: ~120 builds (free)
- **Cost**: $0 for typical usage

### Both Are Free for Most Projects! 🎉

---

## Monitoring

### GitHub Actions
- **Dashboard**: `github.com/YOUR_REPO/actions`
- **Notifications**: Settings → Notifications
- **Insights**: Actions tab → Workflow runs

### CircleCI
- **Dashboard**: `app.circleci.com/pipelines/github/YOUR_REPO`
- **Notifications**: Project Settings → Notifications
- **Insights**: Insights tab → Performance

---

## Troubleshooting

### "Workflow file is invalid"

**Problem**: YAML syntax error

**Solution**:
```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('.github/workflows/integration-tests.yml'))"
```

### "Service connection refused"

**Problem**: Service not ready

**Solution**: Increase wait time in health checks (already generous in our config)

### "Tests timeout"

**Problem**: Tests taking too long

**Solution**: Increase timeout:
```yaml
timeout-minutes: 15  # Increase from 10
```

### "Out of credits/minutes"

**Problem**: Exceeded free tier

**Solutions**:
1. Reduce build frequency (only main branch)
2. Skip CI on docs changes
3. Upgrade to paid plan

---

## Next Steps

1. ✅ **Enable CI** (follow steps above)
2. ✅ **Configure branch protection**
3. ✅ **Add status badge to README**
4. ✅ **Set up notifications**
5. ✅ **Monitor first few builds**

---

## Support

- **GitHub Actions**: https://docs.github.com/en/actions
- **CircleCI**: https://circleci.com/docs/
- **Test Suite**: See `INTEGRATION_TESTS.md`
- **Comparison**: See `CI_COMPARISON.md`

---

## Summary

✅ **Configuration files ready**: Both GitHub Actions and CircleCI configs included

✅ **Zero code changes needed**: Just enable the platform

✅ **Comprehensive testing**: All 21 tests run automatically

✅ **Fast feedback**: Results in ~4 minutes

✅ **Free for most projects**: Both platforms have generous free tiers

**Choose your platform and get started in 5 minutes!** 🚀
