# Quick Integration Test Guide

## TL;DR

```bash
# Start services
docker compose -f docker-compose.local.yml up -d

# Run all integration tests
./run_integration_tests.sh

# Expected: All 21 tests pass in ~3-5 minutes
```

## What Gets Tested

✅ **All 8 Entity Types**: Person, Note, Location, Movie, Book, Container, Asset, Org  
✅ **All Services**: Django + PostgreSQL + MeiliSearch + Neo4j  
✅ **All Operations**: Create, Read, Update, Delete, Search, Filter, Bulk  
✅ **All Features**: Tags, Relations, Import/Export, Multi-User  

## Common Commands

### Run All Tests
```bash
./run_integration_tests.sh
```

### Run Single Test
```bash
docker compose -f docker-compose.local.yml exec backend python manage.py test \
  people.tests.test_integration_full_stack.FullStackIntegrationTest.test_01_person_full_lifecycle
```

### Run Only Stress Tests
```bash
docker compose -f docker-compose.local.yml exec backend python manage.py test \
  people.tests.test_integration_full_stack.MeiliSearchStressTest
```

### Run with More Detail
```bash
docker compose -f docker-compose.local.yml exec backend python manage.py test \
  people.tests.test_integration_full_stack --verbosity=2
```

## Troubleshooting

### "Connection refused"
**Problem**: Services not running  
**Fix**: `docker compose -f docker-compose.local.yml up -d`

### "Document not found in MeiliSearch"
**Problem**: MeiliSearch indexing too slow  
**Fix**: Edit test file, increase `wait_for_meilisearch()` time

### Tests hang
**Problem**: Waiting for MeiliSearch tasks  
**Fix**: Check MeiliSearch health: `curl http://localhost:7701/health`

### Tag counts wrong
**Problem**: Signals not firing  
**Fix**: Verify `people/signals.py` has all entity types in `@receiver` decorators

## Test List

1. ✅ Person Full Lifecycle
2. ✅ All Entity Types Indexing
3. ✅ Hierarchical Tags
4. ✅ Relations and Neo4j
5. ✅ Bulk Operations
6. ✅ Tag Filtering All Types
7. ✅ Import/Export Roundtrip
8. ✅ Multi-User Isolation
9. ✅ Complex Search Filters
10. ✅ Tag Persistence on Zero Count
11. ✅ MeiliSearch Sync on Update
12. ✅ Special Characters in Tags
13. ✅ Concurrent Tag Updates
14. ✅ Relation Type Validation
15. ✅ Empty and Null Tags
16. ✅ Hierarchical Tag Expansion
17. ✅ Entity Type-Specific Fields
18. ✅ Tag Tree API
19. ✅ Bulk Delete with Relations
20. ✅ Display Field Search Restriction
21. ✅ Large Batch Import (Stress Test)

## Success Looks Like

```
.....................
----------------------------------------------------------------------
Ran 21 tests in 245.123s

OK
```

## Failure Looks Like

```
FAIL: test_02_all_entity_types_indexing
AssertionError: Org not found in MeiliSearch
```

**Action**: This indicates a real bug! The test caught that Org entities aren't being indexed.

## When to Run

- ✅ After fixing bugs (verify fix works)
- ✅ Before deploying (ensure nothing broke)
- ✅ After adding features (ensure integration works)
- ✅ After modifying signals (ensure sync still works)
- ✅ Weekly (catch regressions early)

## Performance Expectations

| Test Category | Time |
|--------------|------|
| Entity lifecycle | 2-5s |
| Bulk operations | 5-10s |
| Import/export | 10-15s |
| Stress tests | 15-30s |
| **Total** | **3-5 min** |

## Files

- **Test Code**: `people/tests/test_integration_full_stack.py`
- **Test Runner**: `run_integration_tests.sh`
- **Documentation**: `INTEGRATION_TESTS.md`
- **This Guide**: `QUICK_TEST_GUIDE.md`

## Need Help?

See detailed documentation: `INTEGRATION_TESTS.md`
