# Testing Quick Reference

Quick commands for running tests. See [TESTING.md](./TESTING.md) for detailed documentation.

## Backend Tests

```bash
cd /home/ubuntu/monorepo/data-backend

# Run all tests
./run_tests.sh

# Run with coverage
./run_tests.sh --coverage

# Run specific test file
./run_tests.sh --test test_api_entities

# Verbose output
./run_tests.sh --verbose

# Run specific test method
python manage.py test people.tests.test_api_entities.EntityAPITestCase.test_create_person
```

## Frontend Tests

```bash
cd /home/ubuntu/monorepo/data-backend/frontend

# First time setup
npm install
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom @vitest/ui

# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Watch mode (for development)
npm run test:watch

# Open UI
npm run test:ui

# Run E2E tests (requires running backend)
npm test -- src/tests/e2e
```

## Pre-Commit Checklist

```bash
# 1. Backend tests
cd /home/ubuntu/monorepo/data-backend
./run_tests.sh --coverage

# 2. Frontend tests
cd frontend
npm run test:coverage

# 3. Linting
npm run lint
```

## Test Coverage

View coverage reports:
- **Backend**: Open `htmlcov/index.html` in browser
- **Frontend**: Open `coverage/index.html` in browser

## Common Issues

### Backend: "ModuleNotFoundError"
```bash
cd /home/ubuntu/monorepo/data-backend
pip install -r requirements.txt
```

### Frontend: "Cannot find module"
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### E2E: "Connection refused"
```bash
# Start backend first
docker-compose -f docker-compose.local.yml up
```

## Test Files

### Backend
- `people/tests/test_api_entities.py` - Entity CRUD
- `people/tests/test_api_relations.py` - Relations
- `people/tests/test_api_search.py` - Search & filtering
- `people/tests/test_api_import_export.py` - Import/export

### Frontend
- `frontend/src/tests/EntityDetail.test.jsx` - Component tests
- `frontend/src/tests/e2e/critical-flows.test.js` - E2E tests

## Writing Tests

### Backend Test Template
```python
def test_my_feature(self):
    """Test description"""
    response = self.client.post('/api/endpoint/', data, format='json')
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
```

### Frontend Test Template
```javascript
it('does something', async () => {
  render(<MyComponent />);
  fireEvent.click(screen.getByRole('button'));
  await waitFor(() => {
    expect(screen.getByText('Result')).toBeInTheDocument();
  });
});
```

## Help

For detailed information, see [TESTING.md](./TESTING.md)
