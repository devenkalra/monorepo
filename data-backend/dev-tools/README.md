# Development Tools

This directory contains development utilities and helper scripts.

## Available Tools

### Data Analysis
- **analyze_skip_log.py** - Analyze import skip logs

### Entity Verification
- **check_all_entities.py** - Check all entities
- **check_base_entities.py** - Check base entities
- **check_entities.py** - Entity verification
- **check_import_status.py** - Check import status

### Data Management
- **clear_user_data.py** - Clear user data for testing
- **extract_test_data.py** - Extract test data from production
- **verify_import.py** - Verify import results

### Conversion Tools
- **convert_neo4j_export.py** - Convert Neo4j exports
- **convert_neo4j_test.py** - Test Neo4j conversion

### Debugging
- **debug_import.py** - Debug import issues

### Setup Scripts
- **setup_google_oauth.sh** - Setup Google OAuth
- **test-local.sh** - Run local tests

## Usage

These tools are for development only and should not be deployed to production.

### Example
```bash
# Check import status
python dev-tools/check_import_status.py

# Clear test user data
python dev-tools/clear_user_data.py --user testuser
```
