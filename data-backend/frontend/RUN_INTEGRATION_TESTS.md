# How to Run Integration Tests - FIXED

## The Problem You Had

**"Page timeout"** errors were caused by:
1. Too many open files (EMFILE error)
2. Tests trying to auto-start the dev server
3. Missing authentication handling in tests

## The Fix

I've fixed all three issues:
1. ✅ Updated Playwright config to not auto-start server
2. ✅ Updated test runner to handle dev server properly
3. ✅ Added automatic login/registration to all tests

## How to Run (Simple Method)

### Step 1: Make sure backend is running

```bash
cd /home/ubuntu/monorepo/data-backend
docker-compose -f docker-compose.local.yml ps | grep backend
```

If it's not running:
```bash
docker-compose -f docker-compose.local.yml up
```

### Step 2: Run the tests

```bash
cd /home/ubuntu/monorepo/data-backend/frontend

# Clean up any stray processes first
pkill -9 node; sleep 2

# Run tests (this will auto-start the dev server)
./run_integration_tests.sh
```

That's it! The script will:
- ✅ Check backend is running
- ✅ Start the dev server automatically
- ✅ Run all 23 tests
- ✅ Clean up the dev server when done

## How to Run (Manual Method)

If the automatic method has issues, do it manually:

### Terminal 1: Start dev server

```bash
cd /home/ubuntu/monorepo/data-backend/frontend
pkill -9 node; sleep 2
npm run dev
```

Keep this running!

### Terminal 2: Run tests

```bash
cd /home/ubuntu/monorepo/data-backend/frontend

# Run all tests
npx playwright test

# Or with UI (recommended)
npx playwright test --ui

# Or specific test
npx playwright test tests/integration/01-entity-crud.spec.js
```

## Interactive Mode (Best for Development)

```bash
# Terminal 1: Start dev server
cd /home/ubuntu/monorepo/data-backend/frontend && npm run dev

# Terminal 2: Open Playwright UI
cd /home/ubuntu/monorepo/data-backend/frontend && npx playwright test --ui
```

The UI lets you:
- 👀 Watch tests run in real-time
- 🔍 Inspect each step
- ⏱️ Time travel through execution
- 🐛 Debug failures interactively

## What Gets Tested

### 01-entity-crud.spec.js (8 tests)
- ✅ Create Person entity
- ✅ View details
- ✅ Edit entity
- ✅ Delete entity
- ✅ Create different types (Location, Movie, Org)
- ✅ Add URLs
- ✅ Search/filter

### 02-relations.spec.js (5 tests)
- ✅ Create relation
- ✅ Verify reverse relation
- ✅ Filter relations
- ✅ Expand/collapse
- ✅ Delete relation

### 03-ui-interactions.spec.js (10 tests)
- ✅ Browser navigation (back/forward)
- ✅ Tab switching
- ✅ Edit mode preservation
- ✅ Cancel edits
- ✅ Close panel
- ✅ Type badges
- ✅ Validation
- ✅ Rapid clicking
- ✅ Scroll position
- ✅ Loading states

**Total: 23 tests, ~3-4 minutes**

## View Results

After tests run:

```bash
npx playwright show-report
```

This shows:
- ✅/❌ Pass/fail for each test
- 📸 Screenshots of failures
- 🎥 Videos of test execution
- 📊 Step-by-step traces
- 🌐 Network activity

## Troubleshooting

### Still getting "EMFILE: too many open files"

```bash
# Kill all node processes
pkill -9 node

# Wait
sleep 2

# Try again
./run_integration_tests.sh
```

### "Backend is not running"

```bash
cd /home/ubuntu/monorepo/data-backend
docker-compose -f docker-compose.local.yml up
```

### "Cannot find button Add Entity"

The tests now handle login automatically. If this still happens:
1. Make sure backend is running
2. Check that the frontend loads at http://localhost:5173
3. Try running tests with `--headed` to see what's happening:
   ```bash
   npx playwright test --headed
   ```

### Tests are slow

This is normal! Integration tests:
- Start a real browser
- Make real API calls
- Wait for animations and network
- Take 5-10 seconds per test

### Want to run just one test?

```bash
# Run specific file
npx playwright test tests/integration/01-entity-crud.spec.js

# Run specific test by name
npx playwright test --grep "should create a new Person entity"
```

## Quick Reference

```bash
# One-liner (automatic)
cd /home/ubuntu/monorepo/data-backend/frontend && pkill -9 node; sleep 2 && ./run_integration_tests.sh

# Manual (two terminals)
# Terminal 1:
cd /home/ubuntu/monorepo/data-backend/frontend && npm run dev

# Terminal 2:
cd /home/ubuntu/monorepo/data-backend/frontend && npx playwright test --ui
```

## What Changed

### Before (Broken)
- ❌ Tests tried to auto-start dev server → EMFILE error
- ❌ No authentication handling → Tests couldn't find UI elements
- ❌ Short timeouts → Tests timed out on slow systems

### After (Fixed)
- ✅ Tests use manually started dev server (or script starts it)
- ✅ Tests automatically login/register as needed
- ✅ Increased timeouts (60s per test, 30s navigation)
- ✅ Better error messages and cleanup

## Success Looks Like

```
Running 23 tests using 1 worker

  ✓  [chromium] › 01-entity-crud.spec.js:16:3 › should create a new Person entity (8.2s)
  ✓  [chromium] › 01-entity-crud.spec.js:32:3 › should view entity details (6.5s)
  ✓  [chromium] › 01-entity-crud.spec.js:45:3 › should edit an existing entity (7.1s)
  ...
  
  23 passed (3.2m)
```

Then view the report:
```bash
npx playwright show-report
```

---

**You're all set! The integration tests are ready to run.** 🎉
