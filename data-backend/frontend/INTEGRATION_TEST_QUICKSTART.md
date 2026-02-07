# Integration Tests - Quick Start Guide

## The Problem

You're getting timeouts because of "too many open files" errors when the test runner tries to auto-start the dev server.

## The Solution

**Start the dev server manually first, then run the tests.**

## Step-by-Step Instructions

### Terminal 1: Start Backend (if not already running)

```bash
cd /home/ubuntu/monorepo/data-backend
docker-compose -f docker-compose.local.yml up
```

Wait for it to be ready (you'll see Django startup messages).

### Terminal 2: Start Frontend Dev Server

```bash
cd /home/ubuntu/monorepo/data-backend/frontend

# Kill any stray node processes first
pkill -9 node

# Start the dev server
npm run dev
```

Wait until you see:
```
  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

**Keep this terminal open!**

### Terminal 3: Run Integration Tests

```bash
cd /home/ubuntu/monorepo/data-backend/frontend

# Run all tests
npx playwright test

# Or run with UI (recommended)
npx playwright test --ui

# Or run specific test
npx playwright test tests/integration/01-entity-crud.spec.js
```

## Alternative: Use the Test Runner Script

The script will now auto-start the dev server for you:

```bash
cd /home/ubuntu/monorepo/data-backend/frontend
./run_integration_tests.sh
```

If you get errors, clean up first:

```bash
# Kill all node processes
pkill -9 node

# Wait a moment
sleep 2

# Try again
./run_integration_tests.sh
```

## Troubleshooting

### "EMFILE: too many open files"

**Solution 1: Clean up**
```bash
pkill -9 node
sleep 2
```

**Solution 2: Increase system limits** (if needed)
```bash
ulimit -n 65536
```

### "Page timeout"

**Cause:** Dev server isn't running or took too long to start.

**Solution:** Start dev server manually first (see Terminal 2 above).

### "Backend is not running"

**Solution:** Start backend:
```bash
cd /home/ubuntu/monorepo/data-backend
docker-compose -f docker-compose.local.yml up
```

### Tests are slow

This is normal. Integration tests:
- Start a real browser
- Make real API calls
- Wait for animations
- Take 5-10 seconds per test

Total runtime: ~3-4 minutes for all 23 tests.

## Quick Commands

```bash
# Clean slate
pkill -9 node; sleep 2

# Start dev server (Terminal 1)
cd /home/ubuntu/monorepo/data-backend/frontend && npm run dev

# Run tests (Terminal 2)
cd /home/ubuntu/monorepo/data-backend/frontend && npx playwright test --ui
```

## What Gets Tested

- ✅ Entity CRUD (create, view, edit, delete)
- ✅ Relations (create, view, filter, collapse/expand, delete)
- ✅ UI interactions (navigation, tabs, state management)
- ✅ Search and filtering
- ✅ URL management

**23 tests total, ~3-4 minutes**

## View Results

After tests run:

```bash
npx playwright show-report
```

This shows:
- ✅ Pass/fail for each test
- 📸 Screenshots of failures
- 🎥 Videos of test execution
- 📊 Step-by-step traces

---

**TL;DR:**

```bash
# Terminal 1: Start backend
cd /home/ubuntu/monorepo/data-backend && docker-compose -f docker-compose.local.yml up

# Terminal 2: Start frontend
cd /home/ubuntu/monorepo/data-backend/frontend && npm run dev

# Terminal 3: Run tests
cd /home/ubuntu/monorepo/data-backend/frontend && npx playwright test --ui
```
