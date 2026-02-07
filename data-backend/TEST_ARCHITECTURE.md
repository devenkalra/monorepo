# Integration Test Architecture

## System Under Test

```
┌─────────────────────────────────────────────────────────────┐
│                     Django REST API                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │   Models   │  │   Views    │  │ Serializers│            │
│  └─────┬──────┘  └──────┬─────┘  └──────┬─────┘            │
│        │                 │                │                  │
│        └─────────────────┴────────────────┘                  │
│                          │                                   │
│                    ┌─────▼─────┐                            │
│                    │  Signals  │                            │
│                    └─────┬─────┘                            │
└──────────────────────────┼──────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
    ┌────────┐      ┌────────────┐    ┌─────────┐
    │PostgreSQL│     │MeiliSearch │    │  Neo4j  │
    │          │     │            │    │         │
    │ Entities │     │   Search   │    │Relations│
    │   Tags   │     │   Index    │    │  Graph  │
    │Relations │     │            │    │         │
    └────────┘      └────────────┘    └─────────┘
```

## Test Flow

```
┌──────────────────────────────────────────────────────────────┐
│                     Test Execution                            │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  1. CREATE ENTITY (via API or ORM)                           │
│     POST /api/people/ {"first_name": "John", ...}            │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  2. DJANGO PROCESSES REQUEST                                  │
│     ├─ Serializer validates data                             │
│     ├─ View creates model instance                           │
│     └─ Model.save() called                                   │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  3. SIGNALS FIRE (post_save)                                 │
│     ├─ sync_entity_save() → MeiliSearch                      │
│     ├─ sync_entity_save() → Neo4j                            │
│     └─ _adjust_tag_counts() → Tag model                      │
└──────────────────────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
    ┌─────────┐      ┌──────────┐    ┌─────────┐
    │PostgreSQL│      │MeiliSearch│   │  Neo4j  │
    │  WRITE  │      │   INDEX   │    │  SYNC   │
    └─────────┘      └──────────┘    └─────────┘
          │                │                │
          └────────────────┼────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  4. TEST VERIFIES ALL SERVICES                               │
│     ├─ Assert entity in PostgreSQL                           │
│     ├─ Assert entity in MeiliSearch                          │
│     ├─ Assert tags created with correct counts               │
│     └─ Assert searchable by tag                              │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  5. UPDATE ENTITY                                             │
│     PATCH /api/people/{id}/ {"tags": ["New/Tag"]}            │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  6. VERIFY UPDATE SYNCED                                      │
│     ├─ Assert PostgreSQL updated                             │
│     ├─ Assert MeiliSearch updated                            │
│     └─ Assert tag counts adjusted                            │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  7. DELETE ENTITY                                             │
│     DELETE /api/people/{id}/                                  │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  8. VERIFY CLEANUP                                            │
│     ├─ Assert entity deleted from PostgreSQL                 │
│     ├─ Assert entity deleted from MeiliSearch                │
│     ├─ Assert relations cascaded                             │
│     └─ Assert tag counts decremented                         │
└──────────────────────────────────────────────────────────────┘
```

## Test Categories

```
┌─────────────────────────────────────────────────────────────┐
│                   Integration Tests (21)                     │
└─────────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│Entity Lifecycle│ │  Tag System  │  │  Relations   │
│              │  │              │  │              │
│ • Create     │  │ • Hierarchical│ │ • Creation   │
│ • Read       │  │ • Counting   │  │ • Validation │
│ • Update     │  │ • Persistence│  │ • Cascading  │
│ • Delete     │  │ • Special    │  │ • Neo4j Sync │
│ • Sync       │  │   Characters │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│Search/Filter │  │Bulk Operations│ │Data Integrity│
│              │  │              │  │              │
│ • Multi-filter│ │ • Count      │  │ • Import     │
│ • Display    │  │ • Bulk Delete│  │ • Export     │
│ • Tags       │  │ • Cleanup    │  │ • Multi-User │
│ • Type       │  │              │  │ • Edge Cases │
└──────────────┘  └──────────────┘  └──────────────┘
```

## Entity Type Coverage

```
┌─────────────────────────────────────────────────────────────┐
│              All Entity Types Tested (8)                     │
└─────────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
    ┌────────┐        ┌────────┐        ┌────────┐
    │ Person │        │  Note  │        │Location│
    │        │        │        │        │        │
    │ • Name │        │• Display│       │ • City │
    │ • Email│        │• Content│       │ • State│
    │ • Phone│        │        │        │• Country│
    └────────┘        └────────┘        └────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
    ┌────────┐        ┌────────┐        ┌────────┐
    │ Movie  │        │  Book  │        │Container│
    │        │        │        │        │        │
    │ • Year │        │ • Year │        │• Display│
    │• Language│      │• Language│      │        │
    └────────┘        └────────┘        └────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
                    ▼             ▼
                ┌────────┐    ┌────────┐
                │ Asset  │    │  Org   │
                │        │    │        │
                │ • Value│    │ • Name │
                │        │    │ • Kind │
                └────────┘    └────────┘
```

## Tag Hierarchy Testing

```
┌─────────────────────────────────────────────────────────────┐
│                  Hierarchical Tags                           │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
                      ┌─────────┐
                      │Location │  ← Search returns ALL below
                      └────┬────┘
                           │
                ┌──────────┴──────────┐
                │                     │
                ▼                     ▼
            ┌───────┐             ┌───────┐
            │  US   │             │  UK   │
            └───┬───┘             └───┬───┘
                │                     │
        ┌───────┴───────┐            │
        │               │            │
        ▼               ▼            ▼
    ┌──────────┐   ┌────────┐   ┌────────┐
    │California│   │New York│   │ London │
    └──────────┘   └────────┘   └────────┘
        │
        ▼
    ┌──────────┐
    │    SF    │
    └──────────┘

Test Cases:
• Search "Location" → Returns ALL entities with any Location/* tag
• Search "Location/US" → Returns US, California, New York, SF
• Search "Location/US/California" → Returns California, SF
• Search "Location/UK" → Returns UK, London
```

## Signal Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Entity.save()                             │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  pre_save signal: cache_entity_tags()                       │
│  ├─ Store old tags in instance._old_tags                    │
│  └─ Used later to compute tag count changes                 │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  PostgreSQL COMMIT                                           │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  post_save signal: sync_entity_save()                       │
│  ├─ Sync to MeiliSearch (update_documents)                  │
│  ├─ Sync to Neo4j (create/update node)                      │
│  └─ Call _adjust_tag_counts()                               │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  _adjust_tag_counts()                                        │
│  ├─ Compare old_tags vs new_tags                            │
│  ├─ Increment counts for added tags (+ hierarchy)           │
│  ├─ Decrement counts for removed tags (+ hierarchy)         │
│  └─ Keep tags at count=0 (don't delete)                     │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Test Verification Point                                     │
│  ├─ Entity in PostgreSQL ✓                                  │
│  ├─ Entity in MeiliSearch ✓                                 │
│  ├─ Tags created with counts ✓                              │
│  └─ Searchable by tag ✓                                     │
└─────────────────────────────────────────────────────────────┘
```

## Test Isolation

```
┌─────────────────────────────────────────────────────────────┐
│                    Test Method                               │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  setUp()                                                     │
│  ├─ Create test user                                        │
│  ├─ Authenticate API client                                 │
│  └─ Wait for MeiliSearch to be ready                        │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  test_XX_feature()                                           │
│  ├─ Create test data                                        │
│  ├─ Perform operations                                      │
│  ├─ Assert results                                          │
│  └─ All data scoped to test user                            │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  tearDown()                                                  │
│  ├─ Delete all entities (cascades to relations)             │
│  ├─ Delete all tags                                         │
│  ├─ Delete test user                                        │
│  └─ Wait for MeiliSearch to process deletions               │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
                    Next Test (Clean Slate)
```

## Why TransactionTestCase?

```
┌─────────────────────────────────────────────────────────────┐
│              TestCase (Django Default)                       │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Wraps entire test in database transaction                   │
│  ├─ Fast (no actual commits)                                │
│  ├─ Signals may not fire correctly                          │
│  ├─ External services don't see data                        │
│  └─ ❌ Can't test multi-service integration                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│          TransactionTestCase (Our Choice)                    │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Each operation commits to database                          │
│  ├─ Slower (real commits)                                   │
│  ├─ Signals fire correctly                                  │
│  ├─ External services see data                              │
│  └─ ✅ Can test multi-service integration                    │
└─────────────────────────────────────────────────────────────┘
```

## Timing and Waits

```
┌─────────────────────────────────────────────────────────────┐
│                    Operation                                 │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Django saves to PostgreSQL (synchronous)                    │
│  ├─ Immediate                                               │
│  └─ Can verify immediately                                  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Signal fires: sync to MeiliSearch (asynchronous)           │
│  ├─ Task queued                                             │
│  ├─ Task processed in background                            │
│  └─ Need to wait before verifying                           │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  wait_for_meilisearch(0.5)  ← Strategic wait                │
│  ├─ Single entity: 0.5s                                     │
│  ├─ Bulk operation: 1-2s                                    │
│  └─ Large batch: 3s                                         │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Verify MeiliSearch (now safe)                              │
│  ├─ Entity indexed ✓                                        │
│  └─ Searchable ✓                                            │
└─────────────────────────────────────────────────────────────┘
```

## Test Execution Order

```
Tests run in order (test_01, test_02, ..., test_21)

Each test is independent:
├─ Has its own user
├─ Creates its own data
├─ Cleans up completely
└─ Next test starts fresh

Total execution: ~3-5 minutes
├─ 20 core tests: ~2-4 minutes
└─ 1 stress test: ~30 seconds
```

## Coverage Matrix

```
┌──────────────┬────────┬──────────┬───────────┬────────┐
│ Entity Type  │ Create │  Update  │  Delete   │ Search │
├──────────────┼────────┼──────────┼───────────┼────────┤
│ Person       │   ✓    │    ✓     │     ✓     │   ✓    │
│ Note         │   ✓    │    ✓     │     ✓     │   ✓    │
│ Location     │   ✓    │    ✓     │     ✓     │   ✓    │
│ Movie        │   ✓    │    ✓     │     ✓     │   ✓    │
│ Book         │   ✓    │    ✓     │     ✓     │   ✓    │
│ Container    │   ✓    │    ✓     │     ✓     │   ✓    │
│ Asset        │   ✓    │    ✓     │     ✓     │   ✓    │
│ Org          │   ✓    │    ✓     │     ✓     │   ✓    │
└──────────────┴────────┴──────────┴───────────┴────────┘

┌──────────────┬────────┬──────────┬───────────┬────────┐
│ Service      │ Create │  Update  │  Delete   │ Search │
├──────────────┼────────┼──────────┼───────────┼────────┤
│ PostgreSQL   │   ✓    │    ✓     │     ✓     │   ✓    │
│ MeiliSearch  │   ✓    │    ✓     │     ✓     │   ✓    │
│ Neo4j        │   ✓    │    ✓     │     ✓     │   ✓    │
└──────────────┴────────┴──────────┴───────────┴────────┘

┌──────────────┬────────┬──────────┬───────────┬────────┐
│ Feature      │ Tested │ Coverage │  Variants │ Status │
├──────────────┼────────┼──────────┼───────────┼────────┤
│ Tags         │   ✓    │   100%   │     6     │   ✓    │
│ Relations    │   ✓    │   100%   │     3     │   ✓    │
│ Search       │   ✓    │   100%   │     4     │   ✓    │
│ Bulk Ops     │   ✓    │   100%   │     2     │   ✓    │
│ Import/Export│   ✓    │   100%   │     1     │   ✓    │
│ Multi-User   │   ✓    │   100%   │     1     │   ✓    │
└──────────────┴────────┴──────────┴───────────┴────────┘
```

## Key Insights

### Why This Architecture Works

1. **TransactionTestCase** - Real commits, signals fire
2. **Strategic Waits** - Account for async MeiliSearch
3. **Complete Cleanup** - Each test isolated
4. **All Entity Types** - Catches type-specific bugs
5. **All Services** - Verifies full integration

### What Gets Caught

- ✅ Missing signal registrations
- ✅ MeiliSearch indexing failures
- ✅ Tag count inconsistencies
- ✅ Relation cascading issues
- ✅ Multi-user data leaks
- ✅ Search filter bugs
- ✅ Import/export data loss

### What Makes It Comprehensive

- Tests **all 8 entity types**
- Tests **all 3 services** (PostgreSQL, MeiliSearch, Neo4j)
- Tests **all operations** (CRUD, search, bulk)
- Tests **all features** (tags, relations, import/export)
- Tests **edge cases** (empty tags, special characters)
- Tests **performance** (100+ entity batch)

This architecture ensures that your multi-service system works correctly as a whole, not just in isolated pieces.
