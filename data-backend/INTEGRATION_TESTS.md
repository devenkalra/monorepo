# Comprehensive Integration Test Suite

## Overview

This test suite provides comprehensive integration testing for the entire stack:
- **Django Backend**: Models, views, serializers, signals
- **PostgreSQL**: Data persistence, relations, cascading deletes
- **MeiliSearch**: Full-text search, filtering, tag hierarchies
- **Neo4j**: Entity relations (via signals)
- **Multi-service coordination**: Signal-based sync across all services

## Test Coverage

### 1. Entity Lifecycle Tests (`test_01_person_full_lifecycle`)
- ✅ Create entity via API
- ✅ Verify in PostgreSQL
- ✅ Verify in MeiliSearch
- ✅ Update entity and verify sync
- ✅ Delete entity and verify cleanup
- ✅ Tag count management

### 2. All Entity Types (`test_02_all_entity_types_indexing`)
Tests that **ALL** entity types are properly indexed:
- ✅ Person
- ✅ Note
- ✅ Location
- ✅ Movie
- ✅ Book
- ✅ Container
- ✅ Asset
- ✅ Org

This test was critical in catching the bug where signals weren't registered for all entity types.

### 3. Hierarchical Tags (`test_03_hierarchical_tags`)
- ✅ Tag hierarchy creation (e.g., `Location/US/California`)
- ✅ Parent tag counting (includes all children)
- ✅ Hierarchical search (parent returns all children)
- ✅ Tag count updates on entity changes
- ✅ Tag persistence at zero count

### 4. Relations and Neo4j (`test_04_relations_and_neo4j`)
- ✅ Entity relation creation
- ✅ Reverse relation auto-creation
- ✅ Relation type validation
- ✅ Cascading deletes
- ✅ Neo4j sync (via signals)

### 5. Bulk Operations (`test_05_bulk_operations`)
- ✅ Count endpoint accuracy
- ✅ Bulk delete by filter
- ✅ MeiliSearch cleanup on bulk delete
- ✅ Tag count updates on bulk operations

### 6. Tag Filtering (`test_06_tag_filtering_all_types`)
- ✅ Tag search across all entity types
- ✅ Verify all types returned in results

### 7. Import/Export Roundtrip (`test_07_import_export_roundtrip`)
- ✅ Export data with tags and relations
- ✅ Import data back
- ✅ Verify data integrity
- ✅ Verify MeiliSearch re-indexing

### 8. Multi-User Isolation (`test_08_multi_user_isolation`)
- ✅ User data isolation in PostgreSQL
- ✅ User data isolation in MeiliSearch
- ✅ User cannot access other user's entities
- ✅ Tag isolation per user

### 9. Complex Search Filters (`test_09_search_with_multiple_filters`)
- ✅ Type filtering
- ✅ Tag + type combination
- ✅ Display name search
- ✅ Full-text query search

### 10. Tag Persistence (`test_10_tag_persistence_on_zero_count`)
- ✅ Tags persist when count reaches zero
- ✅ Tags available for reuse (like Gmail labels)

### 11. MeiliSearch Sync (`test_11_meilisearch_sync_on_update`)
- ✅ Updates reflected in MeiliSearch
- ✅ Tag changes synced
- ✅ Field changes synced

### 12. Special Characters (`test_12_special_characters_in_tags`)
- ✅ Tags with spaces
- ✅ Tags with dashes, underscores, dots
- ✅ Tags with parentheses
- ✅ Search with special characters

### 13. Concurrent Tag Updates (`test_13_concurrent_tag_updates`)
- ✅ Tag count accuracy with multiple updates
- ✅ Add/remove tag operations
- ✅ Count consistency

### 14. Relation Type Validation (`test_14_relation_type_validation`)
- ✅ Valid relations succeed
- ✅ Invalid relations fail with ValidationError

### 15. Empty and Null Tags (`test_15_empty_and_null_tags`)
- ✅ Empty tag arrays handled correctly
- ✅ Null tags handled correctly
- ✅ MeiliSearch indexing with no tags

### 16. Hierarchical Tag Expansion (`test_16_hierarchical_tag_expansion`)
- ✅ Parent tag returns all children
- ✅ Sibling tags isolated
- ✅ Deep hierarchies (A/B/C/D)
- ✅ Multiple branches (A/B and A/X)

### 17. Type-Specific Fields (`test_17_entity_type_specific_fields`)
- ✅ Person: profession, gender, emails, phones
- ✅ Location: city, state, country, postal_code
- ✅ Movie: year, language, country
- ✅ All fields indexed and searchable

### 18. Tag Tree API (`test_18_tag_tree_api`)
- ✅ Hierarchical structure returned
- ✅ Correct counts at all levels
- ✅ All tag levels present

### 19. Bulk Delete with Relations (`test_19_bulk_delete_with_relations`)
- ✅ Relations cascade on bulk delete
- ✅ No orphaned relations

### 20. Display Field Search (`test_20_display_field_search_restriction`)
- ✅ Display filter searches only display fields
- ✅ General search searches all fields

### Stress Tests

#### Large Batch Import (`test_large_batch_import`)
- ✅ Import 100 entities
- ✅ Verify all indexed
- ✅ Hierarchical search at scale

## Running the Tests

### Prerequisites

1. All services must be running:
```bash
docker compose -f docker-compose.local.yml up -d
```

2. Verify services are healthy:
```bash
docker compose -f docker-compose.local.yml ps
```

### Run All Tests

```bash
./run_integration_tests.sh
```

Or manually:
```bash
docker compose -f docker-compose.local.yml exec backend python manage.py test people.tests.test_integration_full_stack --verbosity=2
```

### Run Specific Test

```bash
docker compose -f docker-compose.local.yml exec backend python manage.py test people.tests.test_integration_full_stack.FullStackIntegrationTest.test_01_person_full_lifecycle --verbosity=2
```

### Run Only Stress Tests

```bash
docker compose -f docker-compose.local.yml exec backend python manage.py test people.tests.test_integration_full_stack.MeiliSearchStressTest --verbosity=2
```

## Test Architecture

### Why TransactionTestCase?

We use `TransactionTestCase` instead of `TestCase` because:
1. **Signals must fire**: Django's `TestCase` wraps tests in a transaction, which can prevent signals from firing properly
2. **Real database state**: We need to test actual database commits to verify MeiliSearch sync
3. **Service integration**: External services (MeiliSearch, Neo4j) need real data

### Wait Times

Tests include `wait_for_meilisearch()` calls because:
- MeiliSearch indexing is asynchronous
- Tasks are queued and processed in background
- Typical wait: 0.5-2 seconds depending on operation

### Test Isolation

Each test:
1. Creates its own user
2. Creates test data
3. Cleans up all data in `tearDown()`
4. Waits for MeiliSearch to process deletions

## Common Issues

### Tests Fail with "Document not found"

**Cause**: MeiliSearch hasn't finished indexing
**Solution**: Increase wait time in `wait_for_meilisearch()`

### Tests Fail with "Connection refused"

**Cause**: Services not running
**Solution**: 
```bash
docker compose -f docker-compose.local.yml up -d
docker compose -f docker-compose.local.yml ps  # Verify all healthy
```

### Tag Counts Incorrect

**Cause**: Signals not firing for all entity types
**Solution**: Verify `people/signals.py` has `@receiver` decorators for all entity models

### Tests Pass Locally but Fail in CI

**Cause**: Different timing in CI environment
**Solution**: Increase wait times or add retry logic

## Continuous Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      meilisearch:
        image: getmeili/meilisearch:v1.5
        env:
          MEILI_MASTER_KEY: masterKey
        options: >-
          --health-cmd "curl -f http://localhost:7700/health || exit 1"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      neo4j:
        image: neo4j:5-community
        env:
          NEO4J_AUTH: neo4j/testpassword
        options: >-
          --health-cmd "cypher-shell -u neo4j -p testpassword 'RETURN 1'"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      
      - name: Run migrations
        run: |
          python manage.py migrate
      
      - name: Run integration tests
        run: |
          python manage.py test people.tests.test_integration_full_stack --verbosity=2
```

## Test Maintenance

### Adding New Entity Types

When adding a new entity type:

1. Add to `test_02_all_entity_types_indexing`:
```python
('NewType', NewTypeModel, {'field': 'value', 'tags': ['Test/NewType']}),
```

2. Verify signals registered in `people/signals.py`:
```python
@receiver(post_save, sender=NewTypeModel)
```

3. Add type-specific field tests in `test_17_entity_type_specific_fields`

### Adding New Relation Types

1. Add test case in `test_14_relation_type_validation`
2. Test valid and invalid combinations

### Adding New Features

1. Create new test method: `test_XX_feature_name`
2. Follow pattern: create → verify → update → verify → delete → verify
3. Test all services: PostgreSQL, MeiliSearch, Neo4j

## Performance Benchmarks

Expected test execution times (local):

- Individual entity tests: ~2-5 seconds each
- Bulk operation tests: ~5-10 seconds
- Import/export tests: ~10-15 seconds
- Stress tests: ~15-30 seconds
- **Total suite**: ~3-5 minutes

## Debugging Failed Tests

### Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check MeiliSearch Tasks

```python
from people.sync import meili_sync

# In test or Django shell
tasks = meili_sync.helper.client.get_tasks({'limit': 10})
for task in tasks.results:
    print(f"{task.type}: {task.status} - {task.error}")
```

### Check Database State

```python
# In test
print(f"Entities: {Entity.objects.count()}")
print(f"Tags: {Tag.objects.count()}")
print(f"Relations: {EntityRelation.objects.count()}")
```

### Check MeiliSearch Index

```python
stats = meili_sync.helper.client.index('entities').get_stats()
print(f"Documents: {stats.number_of_documents}")
print(f"Indexing: {stats.is_indexing}")
```

## Future Enhancements

- [ ] Add Neo4j query tests (currently tested via signals)
- [ ] Add performance regression tests
- [ ] Add concurrent user tests (multiple users simultaneously)
- [ ] Add file upload tests (photos, attachments)
- [ ] Add URL validation tests
- [ ] Add email/phone validation tests
- [ ] Add pagination tests
- [ ] Add rate limiting tests
- [ ] Add authentication/authorization tests
- [ ] Add API versioning tests

## Related Documentation

- [Testing Quick Reference](TESTING_QUICK_REFERENCE.md)
- [Test Results](TEST_RESULTS.md)
- [Deployment Guide](DEPLOYMENT.md)
