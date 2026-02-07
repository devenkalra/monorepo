# Integration Testing Guide

## Overview

Integration tests test the complete application stack from the frontend perspective using real browser automation with Playwright. These tests simulate actual user interactions and verify the entire system works together correctly.

## What's Different from Unit Tests?

| Aspect | Unit Tests (Vitest) | Integration Tests (Playwright) |
|--------|---------------------|--------------------------------|
| **Scope** | Individual components | Full application flow |
| **Browser** | Simulated (jsdom) | Real browser (Chromium) |
| **Backend** | Mocked | Real backend required |
| **Speed** | Fast (~1s per test) | Slower (~5-10s per test) |
| **Purpose** | Component logic | User experience |
| **When to Run** | Every commit | Before deployment |

## Test Structure

```
frontend/
├── tests/
│   └── integration/
│       ├── auth.setup.js          # Authentication setup
│       ├── 01-entity-crud.spec.js # Entity CRUD tests
│       ├── 02-relations.spec.js   # Relations tests
│       └── 03-ui-interactions.spec.js # UI tests
├── playwright.config.js           # Playwright configuration
└── run_integration_tests.sh       # Test runner script
```

## Test Coverage

### 01-entity-crud.spec.js (8 tests)
Tests complete entity lifecycle through the UI:
- ✅ Create new Person entity
- ✅ View entity details
- ✅ Edit existing entity
- ✅ Delete entity
- ✅ Create different entity types (Location, Movie, Org)
- ✅ Add and display URLs
- ✅ Filter entities by search

### 02-relations.spec.js (5 tests)
Tests relationship management:
- ✅ Create relation between two people
- ✅ Display relation in both directions (reverse relation)
- ✅ Filter relations by search
- ✅ Expand and collapse relation groups
- ✅ Delete a relation

### 03-ui-interactions.spec.js (10 tests)
Tests UI behavior and state management:
- ✅ Navigate using browser back/forward buttons
- ✅ Switch between Details and Relations tabs
- ✅ Preserve edit mode when switching tabs
- ✅ Cancel edit without saving changes
- ✅ Close detail panel
- ✅ Display entity type badge
- ✅ Show validation errors
- ✅ Handle rapid clicking gracefully
- ✅ Maintain scroll position
- ✅ Show loading states

**Total: 23 integration tests**

## Prerequisites

### 1. Backend Must Be Running

```bash
cd /home/ubuntu/monorepo/data-backend
docker-compose -f docker-compose.local.yml up
```

The backend must be accessible at `http://localhost:8000`

### 2. Test User Account

The tests use these credentials:
- Email: `test@example.com`
- Password: `testpass123`

The test will create this user if it doesn't exist.

### 3. Playwright Installed

```bash
cd /home/ubuntu/monorepo/data-backend/frontend
npm install --save-dev @playwright/test --legacy-peer-deps
npx playwright install chromium
```

## Running Integration Tests

### Quick Start

```bash
cd /home/ubuntu/monorepo/data-backend/frontend

# Using the test runner script (recommended)
./run_integration_tests.sh

# Or using npm
npm run test:integration
```

### Advanced Options

#### Run with UI (Interactive)
```bash
./run_integration_tests.sh --ui
# or
npm run test:integration:ui
```

This opens the Playwright UI where you can:
- See tests running in real-time
- Inspect each step
- Time travel through test execution
- Debug failures interactively

#### Run in Headed Mode (Show Browser)
```bash
./run_integration_tests.sh --headed
# or
npm run test:integration:headed
```

Watch the browser execute tests in real-time.

#### Debug Mode
```bash
./run_integration_tests.sh --debug
# or
npm run test:integration:debug
```

Pauses execution and allows step-by-step debugging.

#### Run Specific Test File
```bash
./run_integration_tests.sh --test 01-entity-crud
# or
npx playwright test tests/integration/01-entity-crud.spec.js
```

#### Run Specific Test
```bash
npx playwright test --grep "should create a new Person entity"
```

### View Test Report

After running tests, view the HTML report:

```bash
npx playwright show-report
```

This opens a detailed report with:
- Test results
- Screenshots of failures
- Videos of test execution
- Step-by-step traces

## Writing New Integration Tests

### Basic Test Structure

```javascript
import { test, expect } from '@playwright/test';

test.describe('Feature Name', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('should do something', async ({ page }) => {
    // Arrange: Set up test data
    await page.click('button:has-text("Add Entity")');
    
    // Act: Perform action
    await page.fill('input[placeholder*="Display name"]', 'Test Entity');
    await page.click('button:has-text("Save")');
    
    // Assert: Verify result
    await expect(page.locator('text=Test Entity')).toBeVisible();
  });
});
```

### Best Practices

#### 1. Use Descriptive Selectors
```javascript
// Good
await page.click('button:has-text("Save")');
await page.fill('input[placeholder*="Display name"]', 'Name');

// Avoid
await page.click('.btn-primary');
await page.fill('#input-1', 'Name');
```

#### 2. Wait for Network to Settle
```javascript
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1000); // For animations
```

#### 3. Use Unique Test Data
```javascript
const uniqueName = `Test Entity ${Date.now()}`;
```

#### 4. Clean Up After Tests
```javascript
test.afterEach(async ({ page }) => {
  // Delete test entities if needed
});
```

#### 5. Handle Dialogs
```javascript
page.on('dialog', dialog => dialog.accept());
await page.click('button:has-text("Delete")');
```

### Common Patterns

#### Creating an Entity
```javascript
await page.click('button:has-text("Add Entity")');
await page.fill('input[placeholder*="Display name"]', 'Entity Name');
await page.click('button:has-text("Save")');
await page.waitForTimeout(1000);
```

#### Opening an Entity
```javascript
await page.click('text=Entity Name');
await page.waitForTimeout(500);
```

#### Switching Tabs
```javascript
await page.click('button:has-text("Relations")');
await page.waitForTimeout(500);
```

#### Adding a Relation
```javascript
await page.click('button:has-text("Edit")');
await page.click('button:has-text("+ Add Relation")');
await page.fill('input[placeholder*="Type to search"]', 'Search Term');
await page.waitForTimeout(1000);
await page.click('text=Target Entity');
await page.selectOption('select', 'IS_FRIEND_OF');
await page.click('button:has-text("Add"):not(:has-text("Add Relation"))');
```

## Debugging Failed Tests

### 1. View Screenshots
Failed tests automatically capture screenshots:
```bash
ls test-results/
```

### 2. Watch Videos
Tests record videos on failure:
```bash
npx playwright show-report
```

### 3. Use Debug Mode
```bash
./run_integration_tests.sh --debug
```

### 4. Use Console Logs
```javascript
test('debug test', async ({ page }) => {
  page.on('console', msg => console.log('Browser:', msg.text()));
  // Your test code
});
```

### 5. Take Manual Screenshots
```javascript
await page.screenshot({ path: 'debug.png' });
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Start Backend
        run: |
          cd data-backend
          docker-compose -f docker-compose.local.yml up -d
          
      - name: Wait for Backend
        run: |
          timeout 60 bash -c 'until curl -s http://localhost:8000/api/; do sleep 2; done'
      
      - name: Install Dependencies
        run: |
          cd data-backend/frontend
          npm install
          npx playwright install --with-deps chromium
      
      - name: Run Integration Tests
        run: |
          cd data-backend/frontend
          npm run test:integration
      
      - name: Upload Test Results
        if: always()
        uses: actions/upload-artifact@v2
        with:
          name: playwright-report
          path: frontend/playwright-report/
```

## Performance Considerations

### Test Execution Time

- **Entity CRUD tests**: ~60 seconds (8 tests)
- **Relations tests**: ~45 seconds (5 tests)
- **UI Interaction tests**: ~90 seconds (10 tests)
- **Total**: ~3-4 minutes for all tests

### Optimization Tips

1. **Run tests in parallel** (carefully):
   ```javascript
   // In playwright.config.js
   workers: 2, // Run 2 tests at once
   ```

2. **Skip animations**:
   ```javascript
   await page.emulateMedia({ reducedMotion: 'reduce' });
   ```

3. **Reuse authentication**:
   ```javascript
   // Use auth.setup.js to login once
   ```

4. **Use API for setup**:
   ```javascript
   // Create test data via API instead of UI
   await request.post('http://localhost:8000/api/people/', {
     data: { /* ... */ }
   });
   ```

## Troubleshooting

### Backend Not Running
```
Error: Backend is not running on http://localhost:8000
```
**Solution**: Start the backend first:
```bash
cd /home/ubuntu/monorepo/data-backend
docker-compose -f docker-compose.local.yml up
```

### Port Already in Use
```
Error: Port 5173 is already in use
```
**Solution**: Kill the existing process:
```bash
lsof -ti:5173 | xargs kill -9
```

### Tests Timing Out
```
Timeout exceeded while waiting for element
```
**Solution**: Increase timeout or add explicit waits:
```javascript
await page.waitForTimeout(2000);
// or
await expect(element).toBeVisible({ timeout: 10000 });
```

### Flaky Tests
**Solutions**:
1. Add explicit waits after actions
2. Wait for network idle
3. Use more specific selectors
4. Increase timeouts for slow operations

## Comparison with Other Test Types

| Test Type | When to Use | Example |
|-----------|-------------|---------|
| **Unit Tests** | Test component logic | Button click handler |
| **Integration Tests** | Test full user flows | Create entity → Add relation → Delete |
| **E2E API Tests** | Test backend only | POST /api/people/ |
| **Manual Testing** | Exploratory testing | Try to break the UI |

## Resources

- [Playwright Documentation](https://playwright.dev/)
- [Best Practices](https://playwright.dev/docs/best-practices)
- [Debugging Guide](https://playwright.dev/docs/debug)
- [CI/CD Guide](https://playwright.dev/docs/ci)

---

**Last Updated**: 2026-02-01
**Playwright Version**: 1.x
**Status**: Ready to use ✅
