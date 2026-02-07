# Integration Test Suite - Complete Guide

## Overview

This is a **comprehensive integration test suite** for a multi-service architecture consisting of:
- Django REST API backend
- PostgreSQL relational database
- MeiliSearch full-text search engine
- Neo4j graph database

The test suite verifies that all services work together correctly through Django signals and API endpoints.

## Why Integration Tests?

### Unit Tests Are Not Enough

Unit tests in isolation cannot catch bugs like:
- ❌ Signals not registered for specific entity types (Org, Location, Movie)
- ❌ MeiliSearch not indexing certain models
- ❌ Tag counts not updating across hierarchies
- ❌ Relations not cascading on delete
- ❌ Multi-service sync failures

### Real-World Bug Examples

These tests would have caught our recent bugs:

**Bug 1: Globe Theatre Not Searchable**
- **Cause**: `post_save` signal not registered for `Org` model
- **Test**: `test_02_all_entity_types_indexing` - Creates one of each entity type and verifies MeiliSearch indexing
- **Result**: Would have failed immediately, showing Org entities aren't indexed

**Bug 2: Tag Counts Wrong After Bulk Delete**
- **Cause**: Tag count updates not firing for all entity types
- **Test**: `test_05_bulk_operations` - Bulk deletes and verifies tag counts
- **Result**: Would have shown incorrect counts

**Bug 3: Hierarchical Tag Search Not Working**
- **Cause**: Tag expansion logic issues
- **Test**: `test_16_hierarchical_tag_expansion` - Tests parent tag returns all children
- **Result**: Would have shown missing entities in results

## Test Suite Structure

### 20 Core Integration Tests

Each test follows the pattern:
1. **Create** - Via API or ORM
2. **Verify PostgreSQL** - Data persisted correctly
3. **Verify MeiliSearch** - Data indexed correctly
4. **Update** - Modify data
5. **Verify Sync** - All services updated
6. **Delete** - Remove data
7. **Verify Cleanup** - All services cleaned up

### Test Categories

#### Entity Lifecycle (Tests 1, 11)
- Full CRUD operations
- Service synchronization
- Tag management

#### Entity Type Coverage (Tests 2, 6, 17)
- All 8 entity types tested
- Type-specific fields
- Cross-type operations

#### Tag System (Tests 3, 10, 12, 13, 16, 18)
- Hierarchical tags (e.g., `Location/US/California`)
- Tag counting (parent counts include children)
- Tag persistence (zero-count tags remain)
- Special characters in tags
- Concurrent tag updates

#### Relations (Tests 4, 14, 19)
- Entity relations
- Relation type validation
- Cascading deletes
- Neo4j sync

#### Search & Filtering (Tests 9, 20)
- Multi-filter searches
- Display-only search
- Tag-based filtering
- Type filtering

#### Bulk Operations (Tests 5, 19)
- Bulk delete by filter
- Count endpoint
- Relation cleanup

#### Data Integrity (Tests 7, 8, 15)
- Import/export roundtrip
- Multi-user isolation
- Empty/null handling

#### Stress Tests (Test 21)
- Large batch imports (100+ entities)
- Performance under load

## Quick Start

### 1. Start Services

```bash
cd /home/ubuntu/monorepo/data-backend
docker compose -f docker-compose.local.yml up -d
```

### 2. Verify Services

```bash
docker compose -f docker-compose.local.yml ps
```

All services should show "Up" and "healthy".

### 3. Run Tests

```bash
./run_integration_tests.sh
```

### 4. View Results

Expected output:
```
.....................
----------------------------------------------------------------------
Ran 21 tests in 245.123s

OK
```

## Detailed Test Descriptions

### Test 1: Person Full Lifecycle
**What**: Complete CRUD cycle for Person entity  
**Why**: Verifies basic entity operations work across all services  
**Covers**: Create, read, update, delete, tag management, MeiliSearch sync

### Test 2: All Entity Types Indexing
**What**: Creates one of each entity type and verifies MeiliSearch indexing  
**Why**: Catches missing signal registrations (our recent bug!)  
**Covers**: Person, Note, Location, Movie, Book, Container, Asset, Org

### Test 3: Hierarchical Tags
**What**: Tests tag hierarchy creation and searching  
**Why**: Verifies parent tags return all children (e.g., "Location/US" returns "Location/US/California")  
**Covers**: Tag creation, counting, hierarchical search, count updates

### Test 4: Relations and Neo4j
**What**: Tests entity relations and Neo4j sync  
**Why**: Verifies relations work and sync to graph database  
**Covers**: Relation creation, reverse relations, cascading deletes

### Test 5: Bulk Operations
**What**: Tests bulk delete with filters  
**Why**: Verifies large-scale operations work correctly  
**Covers**: Count endpoint, bulk delete, MeiliSearch cleanup

### Test 6: Tag Filtering All Types
**What**: Verifies tag search works for all entity types  
**Why**: Ensures no entity type is excluded from tag searches  
**Covers**: Cross-type tag filtering

### Test 7: Import/Export Roundtrip
**What**: Exports data, deletes it, imports it back  
**Why**: Verifies data integrity through export/import cycle  
**Covers**: Export format, import parsing, tag preservation

### Test 8: Multi-User Isolation
**What**: Tests that users can only access their own data  
**Why**: Critical security feature  
**Covers**: Data isolation in PostgreSQL and MeiliSearch

### Test 9: Complex Search Filters
**What**: Tests multiple filter combinations  
**Why**: Verifies advanced search functionality  
**Covers**: Type, tag, display, query filters

### Test 10: Tag Persistence
**What**: Verifies tags persist when count reaches zero  
**Why**: Tags should work like Gmail labels (reusable)  
**Covers**: Zero-count tag persistence

### Test 11: MeiliSearch Sync on Update
**What**: Updates entity and verifies MeiliSearch reflects changes  
**Why**: Ensures MeiliSearch stays in sync with PostgreSQL  
**Covers**: Update sync, tag changes

### Test 12: Special Characters in Tags
**What**: Tests tags with spaces, dashes, dots, parentheses  
**Why**: Ensures tag system handles edge cases  
**Covers**: Special character handling

### Test 13: Concurrent Tag Updates
**What**: Multiple entities updating same tag  
**Why**: Verifies tag counts remain accurate  
**Covers**: Concurrent updates, count consistency

### Test 14: Relation Type Validation
**What**: Tests valid and invalid relation types  
**Why**: Ensures relation constraints work  
**Covers**: Validation rules

### Test 15: Empty and Null Tags
**What**: Tests entities with no tags  
**Why**: Ensures edge cases don't break indexing  
**Covers**: Empty arrays, null values

### Test 16: Hierarchical Tag Expansion
**What**: Parent tag search returns all children  
**Why**: Core feature of hierarchical tags  
**Covers**: Tag expansion logic, search accuracy

### Test 17: Type-Specific Fields
**What**: Tests entity type-specific fields are indexed  
**Why**: Ensures all fields are searchable  
**Covers**: Person (profession, gender), Location (city, state), Movie (year, language)

### Test 18: Tag Tree API
**What**: Tests tag tree API structure  
**Why**: Verifies frontend can build tag tree  
**Covers**: Hierarchical structure, counts

### Test 19: Bulk Delete with Relations
**What**: Bulk delete entities with relations  
**Why**: Verifies relations cascade properly  
**Covers**: Cascading deletes, orphan prevention

### Test 20: Display Field Search
**What**: Display filter searches only display fields  
**Why**: Ensures field-specific search works  
**Covers**: Restricted search scope

### Test 21: Large Batch Import (Stress)
**What**: Imports 100 entities with hierarchical tags  
**Why**: Tests performance and stability  
**Covers**: Batch processing, MeiliSearch queue handling

## Running Specific Tests

### Single Test
```bash
docker compose -f docker-compose.local.yml exec backend python manage.py test \
  people.tests.test_integration_full_stack.FullStackIntegrationTest.test_01_person_full_lifecycle \
  --verbosity=2
```

### Test Category
```bash
# Only stress tests
docker compose -f docker-compose.local.yml exec backend python manage.py test \
  people.tests.test_integration_full_stack.MeiliSearchStressTest \
  --verbosity=2
```

### With Debug Output
```bash
docker compose -f docker-compose.local.yml exec backend python manage.py test \
  people.tests.test_integration_full_stack \
  --verbosity=2 \
  --debug-mode
```

## Troubleshooting

### Test Fails: "Connection refused"

**Cause**: Services not running  
**Fix**:
```bash
docker compose -f docker-compose.local.yml up -d
docker compose -f docker-compose.local.yml ps  # Verify all healthy
```

### Test Fails: "Document not found in MeiliSearch"

**Cause**: MeiliSearch indexing too slow  
**Fix**: Edit `people/tests/test_integration_full_stack.py`, increase wait time:
```python
self.wait_for_meilisearch(2)  # Increase from 0.5 to 2 seconds
```

### Test Fails: "Tag count incorrect"

**Cause**: Signals not registered for all entity types  
**Fix**: Check `people/signals.py`:
```python
@receiver(post_save, sender=Entity)
@receiver(post_save, sender=Person)
@receiver(post_save, sender=Note)
@receiver(post_save, sender=Location)  # Must include ALL types
@receiver(post_save, sender=Movie)
@receiver(post_save, sender=Book)
@receiver(post_save, sender=Container)
@receiver(post_save, sender=Asset)
@receiver(post_save, sender=Org)
def sync_entity_save(sender, instance, created=False, **kwargs):
    # ...
```

### Tests Hang

**Cause**: Waiting for MeiliSearch tasks that never complete  
**Debug**:
```bash
# Check MeiliSearch health
curl http://localhost:7701/health

# Check MeiliSearch tasks
curl http://localhost:7701/tasks?limit=10 \
  -H "Authorization: Bearer masterKey"
```

### All Tests Fail

**Cause**: Database migration issues  
**Fix**:
```bash
docker compose -f docker-compose.local.yml exec backend python manage.py migrate
```

## Performance Expectations

| Test | Expected Time |
|------|--------------|
| test_01_person_full_lifecycle | 2-5s |
| test_02_all_entity_types_indexing | 5-8s |
| test_03_hierarchical_tags | 3-5s |
| test_04_relations_and_neo4j | 2-4s |
| test_05_bulk_operations | 5-10s |
| test_06_tag_filtering_all_types | 5-8s |
| test_07_import_export_roundtrip | 10-15s |
| test_08_multi_user_isolation | 3-5s |
| test_09_search_with_multiple_filters | 3-5s |
| test_10_tag_persistence_on_zero_count | 2-3s |
| test_11_meilisearch_sync_on_update | 2-4s |
| test_12_special_characters_in_tags | 2-3s |
| test_13_concurrent_tag_updates | 2-4s |
| test_14_relation_type_validation | 2-3s |
| test_15_empty_and_null_tags | 2-3s |
| test_16_hierarchical_tag_expansion | 3-5s |
| test_17_entity_type_specific_fields | 3-5s |
| test_18_tag_tree_api | 2-3s |
| test_19_bulk_delete_with_relations | 3-5s |
| test_20_display_field_search_restriction | 2-3s |
| test_large_batch_import | 15-30s |
| **TOTAL** | **3-5 minutes** |

## Continuous Integration

### GitHub Actions

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Start services
        run: docker compose -f docker-compose.local.yml up -d
      
      - name: Wait for services
        run: sleep 30
      
      - name: Run integration tests
        run: ./run_integration_tests.sh
      
      - name: Stop services
        if: always()
        run: docker compose -f docker-compose.local.yml down
```

## Maintenance

### Adding New Entity Types

1. Add to `people/models.py`
2. Add signal receivers in `people/signals.py`:
```python
@receiver(post_save, sender=NewEntityType)
@receiver(post_delete, sender=NewEntityType)
```
3. Add to test in `test_02_all_entity_types_indexing`:
```python
('NewType', NewTypeModel, {'field': 'value', 'tags': ['Test/NewType']}),
```
4. Run tests to verify

### Adding New Features

1. Create new test method: `test_XX_feature_name`
2. Follow pattern: create → verify → update → verify → delete → verify
3. Test all services (PostgreSQL, MeiliSearch, Neo4j)
4. Add to this documentation

## Files

- **Test Code**: `people/tests/test_integration_full_stack.py` (1000+ lines)
- **Test Runner**: `run_integration_tests.sh`
- **Test List**: `list_tests.sh`
- **Documentation**: 
  - `INTEGRATION_TESTS.md` (detailed)
  - `INTEGRATION_TEST_SUMMARY.md` (overview)
  - `QUICK_TEST_GUIDE.md` (quick reference)
  - `TEST_SUITE_README.md` (this file)

## Best Practices

### When to Run Tests

- ✅ After fixing bugs
- ✅ Before deploying
- ✅ After adding features
- ✅ After modifying signals
- ✅ Weekly (catch regressions)
- ✅ In CI/CD pipeline

### Test-Driven Development

1. Write test for new feature
2. Run test (should fail)
3. Implement feature
4. Run test (should pass)
5. Refactor if needed
6. Run test again (should still pass)

### Debugging Failed Tests

1. Run single test with verbosity:
```bash
docker compose -f docker-compose.local.yml exec backend python manage.py test \
  people.tests.test_integration_full_stack.FullStackIntegrationTest.test_XX \
  --verbosity=2
```

2. Check service logs:
```bash
docker compose -f docker-compose.local.yml logs backend
docker compose -f docker-compose.local.yml logs meilisearch
```

3. Inspect database:
```bash
docker compose -f docker-compose.local.yml exec backend python manage.py shell
>>> from people.models import *
>>> Entity.objects.count()
>>> Tag.objects.all()
```

4. Check MeiliSearch:
```bash
docker compose -f docker-compose.local.yml exec backend python manage.py shell
>>> from people.sync import meili_sync
>>> meili_sync.helper.client.index('entities').get_stats()
```

## Success Criteria

All tests should pass with output like:
```
=== Testing Person Full Lifecycle ===
✓ Person lifecycle test passed

=== Testing All Entity Types Indexing ===
Created Person: a1b2c3d4-...
✓ Person indexed correctly
Created Note: e5f6g7h8-...
✓ Note indexed correctly
...
✓ All entity types indexing test passed

...

.....................
----------------------------------------------------------------------
Ran 21 tests in 245.123s

OK
```

## Conclusion

This test suite provides **comprehensive coverage** of your multi-service architecture. It:

- ✅ Tests all 8 entity types
- ✅ Verifies all CRUD operations
- ✅ Validates all search and filter combinations
- ✅ Ensures tag system works correctly (hierarchical, counting, persistence)
- ✅ Confirms relations work properly
- ✅ Tests bulk operations
- ✅ Verifies multi-user isolation
- ✅ Validates import/export integrity
- ✅ Handles edge cases and special characters
- ✅ Stress tests with large batches

**Run these tests regularly** to ensure your system stays healthy and all services remain in sync.

For questions or issues, see the detailed documentation in `INTEGRATION_TESTS.md`.
