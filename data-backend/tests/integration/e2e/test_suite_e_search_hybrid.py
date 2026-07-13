"""
Suite E - Search and Hybrid Ranking E2E (BDD Overview)

Feature: Search APIs provide correct filtering, ranking, pagination, and lifecycle behavior.

Scenario: Partial and case-insensitive text search
    Given entities with searchable terms
    When /api/search is queried with partial and mixed-case text
    Then matching entities are returned.

Scenario: Type/tag/field filters
    Given entities with type-specific fields and hierarchical tags
    When type/tags/display/first_name/last_name/gender filters are used
    Then result sets match requested constraints.

Scenario: Relation-based filters
    Given relation-linked entities
    When relation_entity and relation_type filters are used
    Then list and count endpoints return relation-consistent subsets.

Scenario: Sorting and pagination
    Given multiple entities with distinct display values
    When sort_by, page, and page_size are supplied
    Then ordering and pagination metadata are correct.

Scenario: Search index lifecycle on create/update/delete
    Given a uniquely named entity
    When it is created, updated, and deleted
    Then search reflects each lifecycle stage.
"""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone

from .client import E2EApiClient
from .cleanup import cleanup_suite_state
from .config import load_config


class SuiteESearchHybridE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        log_title: Suite E Setup
        id: E-00
        feature: Search Setup
        scenario: Authenticate user and clean suite state
        objective: Ensure deterministic search dataset for suite E
        """
        cls.cfg = load_config()
        cls.client = E2EApiClient(cls.cfg.base_url, cls.cfg.timeout_seconds)
        cls.run_id = f"E2E-E-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        cls.short_label = f"E2E{datetime.now(timezone.utc).strftime('%S')}"

        cls.created_entity_ids = []
        cls.created_relation_ids = []

        login = cls.client.login(cls.cfg.email, cls.cfg.password)
        if login.status_code not in (200, 201):
            raise RuntimeError(f"Suite E login failed: {login.status_code} {login.body}")

        cleanup_stats = cleanup_suite_state(cls.client)
        print(
            f"[Suite E setup] cleaned entities={cleanup_stats['entities']} tags={cleanup_stats['tags']}"
        )

    @classmethod
    def tearDownClass(cls):
        # Keep end state for interactive verification.
        return

    def tearDown(self):
        outcome = getattr(self, "_outcome", None)
        result = getattr(outcome, "result", None) if outcome else None
        failed = False
        if result is not None:
            for test_obj, _tb in list(result.errors) + list(result.failures):
                if test_obj is self or getattr(test_obj, "test_case", None) is self:
                    failed = True
                    break

        self.client.finalize_test_outcome(self._testMethodName, failed)

    @staticmethod
    def _items(payload):
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            return payload["results"]
        return []

    def _create_entity(self, endpoint: str, payload: dict) -> str:
        response = self.client.post(endpoint, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        data = self.client.json_or_empty(response)
        entity_id = data.get("id")
        self.assertTrue(entity_id, f"Missing id in create response: {data}")
        self.created_entity_ids.append(entity_id)
        return entity_id

    def _create_relation(self, from_entity: str, to_entity: str, relation_type: str) -> str:
        response = self.client.post(
            "/api/relations/",
            json={
                "from_entity": from_entity,
                "to_entity": to_entity,
                "relation_type": relation_type,
            },
        )
        self.assertIn(response.status_code, (200, 201), response.text)
        relation_id = self.client.json_or_empty(response).get("id")
        self.assertTrue(relation_id)
        self.created_relation_ids.append(relation_id)
        return relation_id

    def _wait_search_ids(self, query_string: str, expected_ids: set[str], timeout_s: float = 6.0) -> list[dict]:
        deadline = time.time() + timeout_s
        latest_items = []
        while time.time() < deadline:
            resp = self.client.get(query_string)
            if resp.status_code == 200:
                payload = self.client.json_or_empty(resp)
                latest_items = self._items(payload)
                ids = {item.get("id") for item in latest_items if isinstance(item, dict)}
                if expected_ids.issubset(ids):
                    return latest_items
            time.sleep(0.25)
        return latest_items

    def _wait_search_count(self, query_string: str, expected_count: int, timeout_s: float = 6.0) -> int:
        deadline = time.time() + timeout_s
        latest_count = -1
        while time.time() < deadline:
            resp = self.client.get(query_string)
            if resp.status_code == 200:
                payload = self.client.json_or_empty(resp)
                latest_count = int(payload.get("count", 0))
                if latest_count == expected_count:
                    return latest_count
            time.sleep(0.25)
        return latest_count

    def test_01_partial_and_case_insensitive_search(self):
        """
        log_title: Search Text Match
        id: E-01
        feature: Hybrid Search
        scenario: Query with partial and mixed-case strings
        objective: Validate partial and case-insensitive retrieval
        """
        person_id = self._create_entity(
            "/api/people/",
            {
                "display": f"William Shakespeare {self.short_label}",
                "first_name": "William",
                "last_name": "Shakespeare",
                "tags": [self.run_id, "SuiteE", "Literature/Shakespeare"],
            },
        )
        movie_id = self._create_entity(
            "/api/movies/",
            {
                "display": f"The Godfather {self.short_label}",
                "year": 1972,
                "language": "English",
                "country": "United States",
                "tags": [self.run_id, "SuiteE", "Media/Godfather"],
            },
        )

        partial_items = self._wait_search_ids(f"/api/search/?q=Shak%20{self.short_label}", {person_id})
        partial_ids = {item.get("id") for item in partial_items if isinstance(item, dict)}
        self.assertIn(person_id, partial_ids)

        case_items = self._wait_search_ids(f"/api/search/?q=GODFATHER%20{self.short_label}", {movie_id})
        case_ids = {item.get("id") for item in case_items if isinstance(item, dict)}
        self.assertIn(movie_id, case_ids)

    def test_02_filters_type_tags_and_person_fields(self):
        """
        log_title: Search Filters
        id: E-02
        feature: Search Filters
        scenario: Filter by type/tags/display/person fields
        objective: Validate filter semantics and hierarchical tag expansion
        """
        p1 = self._create_entity(
            "/api/people/",
            {
                "display": f"Filter William {self.short_label}",
                "first_name": "William",
                "last_name": "Shakespeare",
                "gender": "Male",
                "tags": [self.run_id, "SuiteE", "Literature/Shakespeare"],
            },
        )
        p2 = self._create_entity(
            "/api/people/",
            {
                "display": f"Filter Emilia {self.short_label}",
                "first_name": "Emilia",
                "last_name": "Clarke",
                "gender": "Female",
                "tags": [self.run_id, "SuiteE", "Media/GameOfThrones"],
            },
        )
        movie_id = self._create_entity(
            "/api/movies/",
            {
                "display": f"Filter Movie {self.short_label}",
                "year": 2011,
                "language": "English",
                "country": "United States",
                "tags": [self.run_id, "SuiteE", "Media/GameOfThrones"],
            },
        )

        type_items = self._wait_search_ids("/api/search/?type=Person", {p1, p2})
        type_ids = {item.get("id") for item in type_items if isinstance(item, dict)}
        self.assertIn(p1, type_ids)
        self.assertIn(p2, type_ids)
        self.assertNotIn(movie_id, type_ids)

        tag_items = self._wait_search_ids("/api/search/?tags=Literature", {p1})
        tag_ids = {item.get("id") for item in tag_items if isinstance(item, dict)}
        self.assertIn(p1, tag_ids)

        fn_resp = self.client.get("/api/search/?first_name=William")
        self.assertEqual(fn_resp.status_code, 200, fn_resp.text)
        fn_ids = {item.get("id") for item in self._items(self.client.json_or_empty(fn_resp)) if isinstance(item, dict)}
        self.assertIn(p1, fn_ids)

        ln_resp = self.client.get("/api/search/?last_name=Shakespeare")
        self.assertEqual(ln_resp.status_code, 200, ln_resp.text)
        ln_ids = {item.get("id") for item in self._items(self.client.json_or_empty(ln_resp)) if isinstance(item, dict)}
        self.assertIn(p1, ln_ids)

        g_resp = self.client.get("/api/search/?gender=Female")
        self.assertEqual(g_resp.status_code, 200, g_resp.text)
        g_ids = {item.get("id") for item in self._items(self.client.json_or_empty(g_resp)) if isinstance(item, dict)}
        self.assertIn(p2, g_ids)

        disp_items = self._wait_search_ids(f"/api/search/?display=William%20{self.short_label}", {p1})
        disp_ids = {item.get("id") for item in disp_items if isinstance(item, dict)}
        self.assertIn(p1, disp_ids)

    def test_03_relation_filtered_list_and_count_consistency(self):
        """
        log_title: Search Relation Filter
        id: E-03
        feature: Relation Filter
        scenario: Use relation_entity and relation_type on list and count
        objective: Validate relation-filter consistency between endpoints
        """
        anchor = self._create_entity(
            "/api/people/",
            {
                "display": f"Anchor {self.short_label}",
                "first_name": "Anchor",
                "last_name": "Node",
                "tags": [self.run_id, "SuiteE", "RelationAnchor"],
            },
        )
        t1 = self._create_entity(
            "/api/people/",
            {
                "display": f"Related One {self.short_label}",
                "first_name": "Related",
                "last_name": "One",
                "tags": [self.run_id, "SuiteE", "RelationTarget"],
            },
        )
        t2 = self._create_entity(
            "/api/people/",
            {
                "display": f"Related Two {self.short_label}",
                "first_name": "Related",
                "last_name": "Two",
                "tags": [self.run_id, "SuiteE", "RelationTarget"],
            },
        )
        self._create_relation(anchor, t1, "IS_FRIEND_OF")
        self._create_relation(anchor, t2, "IS_FRIEND_OF")

        list_url = f"/api/search/?relation_entity={anchor}&relation_type=IS_FRIEND_OF&sort_by=display"
        count_url = f"/api/search/count/?relation_entity={anchor}&relation_type=IS_FRIEND_OF"

        list_items = self._wait_search_ids(list_url, {t1, t2})
        list_ids = {item.get("id") for item in list_items if isinstance(item, dict)}
        self.assertIn(t1, list_ids)
        self.assertIn(t2, list_ids)

        count = self._wait_search_count(count_url, expected_count=2)
        self.assertEqual(count, 2)

    def test_04_sorting_and_pagination(self):
        """
        log_title: Search Paging Sort
        id: E-04
        feature: Paging and Sort
        scenario: Query sorted/paged results
        objective: Validate deterministic display sort and pagination metadata
        """
        self._create_entity(
            "/api/notes/",
            {
                "display": f"Alpha {self.short_label}",
                "description": "Pagination sort test",
                "tags": [self.run_id, "SuiteE", "PagingSort"],
            },
        )
        self._create_entity(
            "/api/notes/",
            {
                "display": f"Beta {self.short_label}",
                "description": "Pagination sort test",
                "tags": [self.run_id, "SuiteE", "PagingSort"],
            },
        )
        self._create_entity(
            "/api/notes/",
            {
                "display": f"Gamma {self.short_label}",
                "description": "Pagination sort test",
                "tags": [self.run_id, "SuiteE", "PagingSort"],
            },
        )

        p1 = self.client.get(f"/api/search/?q={self.short_label}&sort_by=display&page=1&page_size=2")
        self.assertEqual(p1.status_code, 200, p1.text)
        p1_payload = self.client.json_or_empty(p1)
        self.assertEqual(int(p1_payload.get("page", 0)), 1)
        self.assertEqual(int(p1_payload.get("page_size", 0)), 2)
        self.assertGreaterEqual(int(p1_payload.get("count", 0)), 3)
        self.assertGreaterEqual(int(p1_payload.get("total_pages", 0)), 2)

        p2 = self.client.get(f"/api/search/?q={self.short_label}&sort_by=display&page=2&page_size=2")
        self.assertEqual(p2.status_code, 200, p2.text)
        p2_payload = self.client.json_or_empty(p2)
        self.assertEqual(int(p2_payload.get("page", 0)), 2)

        # Basic ordering assertion on page 1 when sorted by display.
        p1_items = self._items(p1_payload)
        displays = [str(item.get("display", "")) for item in p1_items if isinstance(item, dict)]
        self.assertEqual(displays, sorted(displays))

    def test_05_search_lifecycle_create_update_delete(self):
        """
        log_title: Search Lifecycle
        id: E-05
        feature: Meili Lifecycle
        scenario: Create then update then delete searchable entity
        objective: Verify search reflects lifecycle transitions
        """
        created_display = f"Lifecycle Seed {self.short_label}"
        updated_display = f"Lifecycle Updated {self.short_label}"

        person_id = self._create_entity(
            "/api/people/",
            {
                "display": created_display,
                "first_name": "Lifecycle",
                "last_name": "Entity",
                "tags": [self.run_id, "SuiteE", "Lifecycle"],
            },
        )

        created_items = self._wait_search_ids(f"/api/search/?q=Lifecycle%20Seed%20{self.short_label}", {person_id})
        created_ids = {item.get("id") for item in created_items if isinstance(item, dict)}
        self.assertIn(person_id, created_ids)

        patch_resp = self.client.patch(f"/api/people/{person_id}/", json={"display": updated_display})
        self.assertEqual(patch_resp.status_code, 200, patch_resp.text)

        updated_items = self._wait_search_ids(f"/api/search/?q=Lifecycle%20Updated%20{self.short_label}", {person_id})
        updated_ids = {item.get("id") for item in updated_items if isinstance(item, dict)}
        self.assertIn(person_id, updated_ids)

        del_resp = self.client.post(
            f"/api/search/delete_all/?q=Lifecycle%20Updated%20{self.short_label}&type=Person"
        )
        self.assertEqual(del_resp.status_code, 200, del_resp.text)
        del_payload = self.client.json_or_empty(del_resp)
        self.assertGreaterEqual(int(del_payload.get("deleted", 0)), 1)

        verify = self.client.get(f"/api/entities/{person_id}/")
        self.assertEqual(verify.status_code, 404, verify.text)
        if person_id in self.created_entity_ids:
            self.created_entity_ids.remove(person_id)

    def test_06_list_count_endpoint_consistency_same_filters(self):
        """
        log_title: Search Count Sync
        id: E-06
        feature: List Count Consistency
        scenario: Compare /api/search count field to /api/search/count for same params
        objective: Prevent select-all undercount regressions for identical filters
        """
        p1 = self._create_entity(
            "/api/people/",
            {
                "display": f"Count Alice {self.short_label}",
                "first_name": "Alice",
                "last_name": "Count",
                "gender": "Female",
                "tags": [self.run_id, "SuiteE", "Count/Consistency"],
            },
        )
        p2 = self._create_entity(
            "/api/people/",
            {
                "display": f"Count Avery {self.short_label}",
                "first_name": "Avery",
                "last_name": "Count",
                "gender": "Female",
                "tags": [self.run_id, "SuiteE", "Count/Consistency"],
            },
        )

        list_url = (
            "/api/search/?type=Person"
            f"&tags=Count/Consistency&q=Count%20{self.short_label}"
            "&gender=Female"
        )
        count_url = (
            "/api/search/count/?type=Person"
            f"&tags=Count/Consistency&q=Count%20{self.short_label}"
            "&gender=Female"
        )

        list_items = self._wait_search_ids(list_url, {p1, p2})
        list_ids = {item.get("id") for item in list_items if isinstance(item, dict)}
        self.assertIn(p1, list_ids)
        self.assertIn(p2, list_ids)

        list_resp = self.client.get(list_url)
        self.assertEqual(list_resp.status_code, 200, list_resp.text)
        list_payload = self.client.json_or_empty(list_resp)
        list_count = int(list_payload.get("count", 0))

        count_value = self._wait_search_count(count_url, expected_count=list_count)
        self.assertEqual(count_value, list_count)


if __name__ == "__main__":
    unittest.main(verbosity=2)
