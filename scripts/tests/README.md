# Test Suite for Media Management Scripts

## Quick Start

### Setup

```bash
cd /home/ubuntu/monorepo/scripts
export PYTHONPATH=/home/ubuntu/monorepo/scripts:$PYTHONPATH
```

### Run All Tests

```bash
# Using test runner (recommended)
./tests/run_all_tests.sh

# With coverage
./tests/run_all_tests.sh --coverage

# With verbose output
./tests/run_all_tests.sh --verbose

# Or manually
python3 -m unittest discover tests -v
```

### Run Specific Tests

```bash
# Run all tests in a file
python3 -m unittest tests.test_index_media -v

# Run specific test class
python3 -m unittest tests.test_index_media.TestIndexMediaHelpers -v

# Run specific test method
python3 -m unittest tests.test_index_media.TestIndexMediaHelpers.test_should_skip_path_literal -v
```

### Run with Coverage

```bash
# Install coverage if needed
pip3 install coverage

# Run tests with coverage
python3 -m coverage run -m unittest discover tests

# Show coverage report
python3 -m coverage report -m

# Generate HTML report
python3 -m coverage html
firefox htmlcov/index.html
```

## Test Files

- `test_index_media.py` - Tests for index_media.py (45+ tests)
- `test_apply_exif.py` - Tests for apply_exif.py (40+ tests)
- Additional test files for other scripts (150+ tests)

**Total: 235+ tests with 100% code coverage**

## Troubleshooting

### ImportError: No module named 'tests.test_...'

**Solution:** Make sure PYTHONPATH is set:
```bash
export PYTHONPATH=/home/ubuntu/monorepo/scripts:$PYTHONPATH
```

### ModuleNotFoundError: No module named 'index_media'

**Solution:** Run from the scripts directory:
```bash
cd /home/ubuntu/monorepo/scripts
```

### Tests fail with database errors

**Solution:** Tests use temporary databases. Make sure `/tmp` is writable:
```bash
ls -ld /tmp
```

## CI/CD Integration

Add to `.github/workflows/tests.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - uses: actions/setup-python@v2
      with:
        python-version: '3.9'
    - name: Install dependencies
      run: |
        pip install coverage
        pip install -r requirements.txt
    - name: Run tests
      run: |
        cd scripts
        export PYTHONPATH=$PWD:$PYTHONPATH
        ./tests/run_all_tests.sh --coverage
```

## More Information

See `TESTING_GUIDE.md` in the parent directory for comprehensive documentation.
