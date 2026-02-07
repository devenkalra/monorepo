# Testing Guide

This document describes the testing strategy and how to run tests for the Data Backend application.

## Table of Contents

1. [Overview](#overview)
2. [Backend Tests](#backend-tests)
3. [Frontend Tests](#frontend-tests)
4. [Running Tests](#running-tests)
5. [Writing New Tests](#writing-new-tests)
6. [Continuous Integration](#continuous-integration)
7. [Troubleshooting](#troubleshooting)

## Overview

The application has comprehensive test coverage at multiple levels:

- **Backend API Tests**: Django unit and integration tests
- **Frontend Component Tests**: React component tests using Vitest
- **End-to-End Tests**: Full-stack integration tests

### Test Structure

```
data-backend/
├── people/tests/              # Backend tests
│   ├── test_api_entities.py   # Entity CRUD tests
│   ├── test_api_relations.py  # Relation tests
│   ├── test_api_search.py     # Search & filtering tests
│   └── test_api_import_export.py  # Import/export tests
├── frontend/src/tests/        # Frontend tests
│   ├── setup.js               # Test setup
│   ├── EntityDetail.test.jsx  # Component tests
│   └── e2e/                   # E2E tests
│       └── critical-flows.test.js
└── run_tests.sh               # Backend test runner
```

## Backend Tests

### Test Categories

#### 1. Entity CRUD Tests (`test_api_entities.py`)
Tests entity creation, retrieval, update, and deletion for all entity types:
- Person, Location, Movie, Book, Container, Asset, Org, Note
- Field validation
- User isolation
- Timestamps
- URLs, photos, attachments

#### 2. Relation Tests (`test_api_relations.py`)
Tests entity relationships:
- Creating relations between different entity types
- Symmetric vs asymmetric relations
- Reverse relation creation
- Relation validation
- Relation deletion

#### 3. Search Tests (`test_api_search.py`)
Tests search and filtering functionality:
- Text search (partial, case-insensitive)
- Type filtering
- Tag filtering
- Combined filters
- Special characters and Unicode
- User isolation

#### 4. Import/Export Tests (`test_api_import_export.py`)
Tests data import and export:
- Export format validation
- Import with entities and relations
- Duplicate ID handling
- Round-trip (export → import)
- Error handling

### Running Backend Tests

#### Run All Tests
```bash
cd /home/ubuntu/monorepo/data-backend
./run_tests.sh
```

#### Run with Coverage
```bash
./run_tests.sh --coverage
```

Coverage report will be generated in `htmlcov/index.html`.

#### Run Specific Test File
```bash
./run_tests.sh --test test_api_entities
```

#### Run Specific Test Class or Method
```bash
python manage.py test people.tests.test_api_entities.EntityAPITestCase.test_create_person
```

#### Verbose Output
```bash
./run_tests.sh --verbose
```

### Backend Test Requirements

- Django test database (automatically created)
- All dependencies from `requirements.txt`
- MeiliSearch (mocked in tests)

## Frontend Tests

### Test Categories

#### 1. Component Tests (`EntityDetail.test.jsx`)
Tests React components in isolation:
- Rendering
- User interactions
- State management
- Props handling
- Edit mode
- Relations display
- Filtering and collapsing

#### 2. End-to-End Tests (`e2e/critical-flows.test.js`)
Tests complete user workflows:
- Entity creation flow
- Entity update flow
- Relation management
- Search and filtering
- Import/export
- URL management
- Error handling

### Running Frontend Tests

#### Install Dependencies
```bash
cd /home/ubuntu/monorepo/data-backend/frontend
npm install
```

You'll need to add these dev dependencies:
```bash
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom @vitest/ui
```

#### Run All Tests
```bash
./run_tests.sh
```

Or using npm:
```bash
npm test
```

#### Run with Coverage
```bash
./run_tests.sh --coverage
# or
npm run test:coverage
```

#### Watch Mode (for development)
```bash
./run_tests.sh --watch
# or
npm run test:watch
```

#### Open Vitest UI
```bash
./run_tests.sh --ui
# or
npm run test:ui
```

#### Run E2E Tests Only
```bash
./run_tests.sh --e2e
```

**Note**: E2E tests require a running backend server. Start it with:
```bash
cd /home/ubuntu/monorepo/data-backend
docker-compose -f docker-compose.local.yml up
```

## Running Tests

### Quick Start

1. **Backend tests**:
   ```bash
   cd /home/ubuntu/monorepo/data-backend
   ./run_tests.sh --coverage
   ```

2. **Frontend tests**:
   ```bash
   cd /home/ubuntu/monorepo/data-backend/frontend
   npm install  # First time only
   ./run_tests.sh --coverage
   ```

3. **E2E tests** (requires running backend):
   ```bash
   # Terminal 1: Start backend
   cd /home/ubuntu/monorepo/data-backend
   docker-compose -f docker-compose.local.yml up
   
   # Terminal 2: Run E2E tests
   cd /home/ubuntu/monorepo/data-backend/frontend
   ./run_tests.sh --e2e
   ```

### Pre-commit Testing

Before committing changes, run:
```bash
# Backend
cd /home/ubuntu/monorepo/data-backend
./run_tests.sh --coverage

# Frontend
cd frontend
./run_tests.sh --coverage
```

## Writing New Tests

### Backend Test Template

```python
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()

class MyTestCase(TestCase):
    def setUp(self):
        """Set up test client and user"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_my_feature(self):
        """Test description"""
        # Arrange
        data = {'key': 'value'}
        
        # Act
        response = self.client.post('/api/endpoint/', data, format='json')
        
        # Assert
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['key'], 'value')
```

### Frontend Component Test Template

```javascript
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import MyComponent from '../components/MyComponent';

describe('MyComponent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders correctly', () => {
    render(
      <BrowserRouter>
        <MyComponent prop="value" />
      </BrowserRouter>
    );

    expect(screen.getByText('Expected Text')).toBeInTheDocument();
  });

  it('handles user interaction', async () => {
    const onAction = vi.fn();
    
    render(
      <BrowserRouter>
        <MyComponent onAction={onAction} />
      </BrowserRouter>
    );

    const button = screen.getByRole('button', { name: /action/i });
    fireEvent.click(button);

    await waitFor(() => {
      expect(onAction).toHaveBeenCalled();
    });
  });
});
```

### E2E Test Template

```javascript
import { describe, it, expect, beforeAll, afterAll } from 'vitest';

describe('My Feature Flow - E2E', () => {
  let authToken;
  const API_BASE = 'http://localhost:8000';

  beforeAll(async () => {
    // Authenticate
    const response = await fetch(`${API_BASE}/api/auth/login/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: 'test@example.com',
        password: 'testpass123'
      }),
    });
    const data = await response.json();
    authToken = data.access;
  });

  it('completes the flow', async () => {
    // Test implementation
  });
});
```

## Continuous Integration

### GitHub Actions Example

Create `.github/workflows/test.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          cd data-backend
          pip install -r requirements.txt
      - name: Run tests
        run: |
          cd data-backend
          ./run_tests.sh --coverage

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Node
        uses: actions/setup-node@v2
        with:
          node-version: '18'
      - name: Install dependencies
        run: |
          cd data-backend/frontend
          npm install
      - name: Run tests
        run: |
          cd data-backend/frontend
          npm test
```

## Troubleshooting

### Backend Tests

#### Database Errors
```bash
# Reset test database
python manage.py test --keepdb=False
```

#### Import Errors
```bash
# Ensure you're in the right directory
cd /home/ubuntu/monorepo/data-backend

# Check Python path
python -c "import sys; print(sys.path)"
```

#### MeiliSearch Connection Errors
Tests should mock MeiliSearch. If you see connection errors, check that mocks are properly set up.

### Frontend Tests

#### Module Not Found
```bash
# Reinstall dependencies
cd frontend
rm -rf node_modules package-lock.json
npm install
```

#### jsdom Errors
Ensure `vitest.config.js` has `environment: 'jsdom'`.

#### React Router Errors
Wrap components in `<BrowserRouter>` in tests.

### E2E Tests

#### Connection Refused
Ensure backend is running:
```bash
docker-compose -f docker-compose.local.yml up
```

#### Authentication Errors
Check that test user exists or create it:
```bash
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> User.objects.create_user(email='test@example.com', password='testpass123')
```

## Test Coverage Goals

- **Backend**: Aim for >80% code coverage
- **Frontend**: Aim for >70% code coverage
- **Critical Paths**: 100% coverage for:
  - Authentication
  - Entity CRUD operations
  - Relation management
  - Import/export

## Best Practices

1. **Write tests first** (TDD) when fixing bugs
2. **Test behavior, not implementation**
3. **Use descriptive test names**
4. **Keep tests independent** (no shared state)
5. **Mock external services** (MeiliSearch, file uploads)
6. **Test edge cases** (empty data, special characters, errors)
7. **Run tests before committing**
8. **Update tests when changing features**

## Resources

- [Django Testing Documentation](https://docs.djangoproject.com/en/stable/topics/testing/)
- [Vitest Documentation](https://vitest.dev/)
- [React Testing Library](https://testing-library.com/react)
- [Testing Best Practices](https://testingjavascript.com/)
