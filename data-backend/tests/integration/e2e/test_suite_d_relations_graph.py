"""
Suite D - Relations and Graph-Dependent Queries E2E (BDD Overview)

Feature: Relation APIs and graph-dependent search behavior are correct end-to-end.

Scenario: Relation CRUD and reverse-link behavior
    Given owned entities for the authenticated user
    When relations are created and deleted
    Then relation records are returned by relation endpoints and removed on delete

Scenario: Graph context endpoints
    Given linked entities
    When /relations and /llm_context are requested
    Then payload contracts are valid and invalid direction is rejected

Scenario: Relation-filtered search/count/delete_all
    Given relation-linked entities and a unique query marker
    When relation_entity + relation_type filters are applied on /api/search endpoints
    Then list/count reflect the linked set and delete_all deletes only matching records

Scenario: Cross-user relation ownership enforcement
    Given one entity owned by current user and one by another user
    When creating a relation across mixed ownership
    Then API rejects the operation

Scenario: Deep rich graph across all entity types
    Given entities across Person, Note, Location, Movie, Book, Container, Asset, and Org
    When many schema-valid relations are created (including repeated relation types)
    Then each entity type participates in the graph with multiple connections
"""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone

from .client import E2EApiClient
from .cleanup import cleanup_suite_state
from .config import load_config


class SuiteDRelationsGraphE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        log_title: Suite D Setup
        id: D-00
        feature: Relations Setup
        scenario: Authenticate primary user for suite D
        objective: Ensure primary API client is authenticated
        """
        cls.cfg = load_config()
        cls.client = E2EApiClient(cls.cfg.base_url, cls.cfg.timeout_seconds)
        cls.run_id = f"E2E-D-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        cls.short_label = f"E2E{datetime.now(timezone.utc).strftime('%S')}"

        cls.created_entity_ids_primary = []
        cls.created_relation_ids = []

        cls.secondary_client = None
        cls.secondary_email = f"suite-d-{cls.run_id.lower()}@example.com"
        cls.secondary_password = "TestPassword123!"
        cls.created_entity_ids_secondary = []

        login = cls.client.login(cls.cfg.email, cls.cfg.password)
        if login.status_code not in (200, 201):
            raise RuntimeError(f"Primary login failed: {login.status_code} {login.body}")

        cleanup_stats = cleanup_suite_state(cls.client)
        print(
            f"[Suite D setup] cleaned entities={cleanup_stats['entities']} tags={cleanup_stats['tags']}"
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

    def _create_entity(self, endpoint: str, payload: dict, owner: str = "primary") -> str:
        target = self.client if owner == "primary" else self.secondary_client
        response = target.post(endpoint, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        data = target.json_or_empty(response)
        entity_id = data.get("id")
        self.assertTrue(entity_id, f"Missing id in create response: {data}")
        if owner == "primary":
            self.created_entity_ids_primary.append(entity_id)
        else:
            self.created_entity_ids_secondary.append(entity_id)
        return entity_id

    def _wait_for_relation_count(self, relation_entity_id: str, relation_type: str, min_count: int, timeout_s: float = 4.0):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            resp = self.client.get(
                f"/api/search/count/?relation_entity={relation_entity_id}&relation_type={relation_type}"
            )
            if resp.status_code == 200:
                payload = self.client.json_or_empty(resp)
                if int(payload.get("count", 0)) >= min_count:
                    return payload
            time.sleep(0.2)
        return None

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
        self.assertTrue(relation_id, f"Missing relation id: {response.text}")
        self.created_relation_ids.append(relation_id)
        return relation_id

    def _relation_totals(self, entity_id: str) -> tuple[int, int]:
        response = self.client.get(f"/api/entities/{entity_id}/relations/?direction=both")
        self.assertEqual(response.status_code, 200, response.text)
        payload = self.client.json_or_empty(response)
        outgoing = payload.get("outgoing") or []
        incoming = payload.get("incoming") or []
        return len(outgoing), len(incoming)

    def _ensure_secondary_user_client(self) -> E2EApiClient | None:
        if self.secondary_client is not None:
            return self.secondary_client

        register_client = E2EApiClient(self.cfg.base_url, self.cfg.timeout_seconds)
        register_resp = register_client.post(
            "/api/auth/registration/",
            add_auth=False,
            json={
                "email": self.secondary_email,
                "password1": self.secondary_password,
                "password2": self.secondary_password,
            },
        )
        if register_resp.status_code not in (200, 201, 204, 400):
            return None

        secondary = E2EApiClient(self.cfg.base_url, self.cfg.timeout_seconds)
        login = secondary.login(self.secondary_email, self.secondary_password)
        if login.status_code not in (200, 201):
            return None

        self.secondary_client = secondary
        return secondary

    def test_01_relation_create_delete_and_reverse_visibility(self):
        """
        log_title: Relation CRUD
        id: D-01
        feature: Relation CRUD
        scenario: Create and delete relation between owned people
        objective: Validate relation create/delete and reverse visibility via relations endpoint
        """
        p1 = self._create_entity(
            "/api/people/",
            {
                "display": f"Maya Chen {self.short_label}",
                "first_name": "Maya",
                "last_name": "Chen",
                "tags": [self.run_id, "SuiteD"],
            },
        )
        p2 = self._create_entity(
            "/api/people/",
            {
                "display": f"Arjun Patel {self.short_label}",
                "first_name": "Arjun",
                "last_name": "Patel",
                "tags": [self.run_id, "SuiteD"],
            },
        )

        with self.client.log_call_purpose("Create Person relation"):
            create_rel = self.client.post(
                "/api/relations/",
                json={
                    "from_entity": p1,
                    "to_entity": p2,
                    "relation_type": "IS_FRIEND_OF",
                },
            )
        self.assertIn(create_rel.status_code, (200, 201), create_rel.text)
        rel_data = self.client.json_or_empty(create_rel)
        rel_id = rel_data.get("id")
        self.assertTrue(rel_id)
        self.created_relation_ids.append(rel_id)

        rels_p2 = self.client.get(f"/api/entities/{p2}/relations/?direction=outgoing")
        self.assertEqual(rels_p2.status_code, 200, rels_p2.text)
        payload = self.client.json_or_empty(rels_p2)
        outgoing = payload.get("outgoing") or []
        self.assertTrue(any(r.get("entity", {}).get("id") == p1 for r in outgoing))

        delete_rel = self.client.delete(f"/api/relations/{rel_id}/")
        self.assertEqual(delete_rel.status_code, 204, delete_rel.text)

        verify_deleted = self.client.get(f"/api/relations/{rel_id}/")
        self.assertEqual(verify_deleted.status_code, 404, verify_deleted.text)

        if rel_id in self.created_relation_ids:
            self.created_relation_ids.remove(rel_id)

    def test_02_relations_endpoint_and_llm_context_contract(self):
        """
        log_title: Relations Context
        id: D-02
        feature: Graph Context
        scenario: Fetch relations and llm_context for linked entities
        objective: Validate response contract and invalid direction guardrail
        """
        movie_id = self._create_entity(
            "/api/movies/",
            {
                "display": f"The Godfather {self.short_label}",
                "year": 1972,
                "language": "English",
                "country": "United States",
                "tags": [self.run_id, "SuiteD", "Godfather"],
            },
        )
        actor_id = self._create_entity(
            "/api/people/",
            {
                "display": f"Al Pacino {self.short_label}",
                "first_name": "Al",
                "last_name": "Pacino",
                "tags": [self.run_id, "SuiteD", "Godfather"],
            },
        )

        create_rel = self.client.post(
            "/api/relations/",
            json={
                "from_entity": movie_id,
                "to_entity": actor_id,
                "relation_type": "HAS_ACTOR",
            },
        )
        self.assertIn(create_rel.status_code, (200, 201), create_rel.text)
        rel_id = self.client.json_or_empty(create_rel).get("id")
        if rel_id:
            self.created_relation_ids.append(rel_id)

        rel_resp = self.client.get(f"/api/entities/{movie_id}/relations/?direction=both")
        self.assertEqual(rel_resp.status_code, 200, rel_resp.text)
        rel_data = self.client.json_or_empty(rel_resp)
        self.assertIn("outgoing", rel_data)
        self.assertIn("incoming", rel_data)
        self.assertIn("text_block", rel_data)
        self.assertTrue(any(item.get("entity", {}).get("id") == actor_id for item in rel_data.get("outgoing", [])))

        llm_ctx = self.client.get(f"/api/entities/{movie_id}/llm_context/")
        self.assertEqual(llm_ctx.status_code, 200, llm_ctx.text)
        llm_payload = self.client.json_or_empty(llm_ctx)
        self.assertIsInstance(llm_payload.get("text_block"), str)
        self.assertIn("Godfather", llm_payload.get("text_block", ""))

        bad_direction = self.client.get(f"/api/entities/{movie_id}/relations/?direction=invalid")
        self.assertEqual(bad_direction.status_code, 400, bad_direction.text)

    def test_03_relation_filtered_search_count_and_delete_all(self):
        """
        log_title: Relation Filter Search
        id: D-03
        feature: Graph Filtered Search
        scenario: Use relation_entity and relation_type on list/count/delete_all endpoints
        objective: Validate graph-dependent filter behavior through search APIs
        """
        anchor_id = self._create_entity(
            "/api/people/",
            {
                "display": f"Anchor Person {self.short_label}",
                "first_name": "Anchor",
                "last_name": "User",
                "tags": [self.run_id, "SuiteD", "Anchor"],
            },
        )
        target_display = f"Target Shakespeare {self.short_label}"
        target_id = self._create_entity(
            "/api/people/",
            {
                "display": target_display,
                "first_name": "Will",
                "last_name": "Shakespeare",
                "tags": [self.run_id, "SuiteD", "Target"],
            },
        )

        rel_create = self.client.post(
            "/api/relations/",
            json={
                "from_entity": anchor_id,
                "to_entity": target_id,
                "relation_type": "IS_FRIEND_OF",
            },
        )
        self.assertIn(rel_create.status_code, (200, 201), rel_create.text)
        rel_id = self.client.json_or_empty(rel_create).get("id")
        if rel_id:
            self.created_relation_ids.append(rel_id)

        waited = self._wait_for_relation_count(anchor_id, "IS_FRIEND_OF", 1)
        self.assertIsNotNone(waited, "Timed out waiting for relation filter count to become visible")

        list_resp = self.client.get(
            f"/api/search/?relation_entity={anchor_id}&relation_type=IS_FRIEND_OF&sort_by=display"
        )
        self.assertEqual(list_resp.status_code, 200, list_resp.text)
        list_payload = self.client.json_or_empty(list_resp)
        results = self._items(list_payload)
        self.assertGreaterEqual(len(results), 1)
        result_ids = {item.get("id") for item in results if isinstance(item, dict)}
        self.assertIn(target_id, result_ids)

        count_resp = self.client.get(
            f"/api/search/count/?relation_entity={anchor_id}&relation_type=IS_FRIEND_OF"
        )
        self.assertEqual(count_resp.status_code, 200, count_resp.text)
        count_payload = self.client.json_or_empty(count_resp)
        self.assertGreaterEqual(int(count_payload.get("count", 0)), 1)

        delete_resp = self.client.post(
            f"/api/search/delete_all/?relation_entity={anchor_id}&relation_type=IS_FRIEND_OF&q=Target Shakespeare"
        )
        self.assertEqual(delete_resp.status_code, 200, delete_resp.text)
        deleted_payload = self.client.json_or_empty(delete_resp)
        self.assertGreaterEqual(int(deleted_payload.get("deleted", 0)), 1)

        verify_target = self.client.get(f"/api/entities/{target_id}/")
        self.assertEqual(verify_target.status_code, 404, verify_target.text)
        if target_id in self.created_entity_ids_primary:
            self.created_entity_ids_primary.remove(target_id)

    def test_04_reject_cross_user_relation_creation(self):
        """
        log_title: Cross User Relation Guard
        id: D-04
        feature: Ownership Enforcement
        scenario: Attempt relation creation across mixed ownership entities
        objective: Ensure relation creation is blocked when one entity is not owned by caller
        """
        secondary = self._ensure_secondary_user_client()
        if secondary is None:
            self.skipTest("Secondary user registration/login not available in this environment")

        primary_person = self._create_entity(
            "/api/people/",
            {
                "display": f"Primary Owner {self.short_label}",
                "first_name": "Primary",
                "last_name": "Owner",
                "tags": [self.run_id, "SuiteD", "OwnerA"],
            },
        )
        secondary_person = self._create_entity(
            "/api/people/",
            {
                "display": f"Secondary Owner {self.short_label}",
                "first_name": "Secondary",
                "last_name": "Owner",
                "tags": [self.run_id, "SuiteD", "OwnerB"],
            },
            owner="secondary",
        )

        cross_create = self.client.post(
            "/api/relations/",
            json={
                "from_entity": primary_person,
                "to_entity": secondary_person,
                "relation_type": "IS_FRIEND_OF",
            },
        )
        self.assertIn(cross_create.status_code, (403, 404), cross_create.text)

    def test_05_deep_rich_graph_all_entity_types(self):
        """
        log_title: Deep Graph
        id: D-05
        feature: Rich Graph Topology
        scenario: Build a dense graph with repeated relation types across all entity types
        objective: Ensure each entity type has multiple connections and graph context stays rich
        """
        # People
        shakespeare = self._create_entity(
            "/api/people/",
            {
                "display": f"William Shakespeare {self.short_label}",
                "first_name": "William",
                "last_name": "Shakespeare",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )
        grrm = self._create_entity(
            "/api/people/",
            {
                "display": f"George Martin {self.short_label}",
                "first_name": "George",
                "last_name": "Martin",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )
        coppola = self._create_entity(
            "/api/people/",
            {
                "display": f"Francis Coppola {self.short_label}",
                "first_name": "Francis",
                "last_name": "Coppola",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )
        pacino = self._create_entity(
            "/api/people/",
            {
                "display": f"Al Pacino {self.short_label}",
                "first_name": "Al",
                "last_name": "Pacino",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )

        # Non-person entity types
        note_1 = self._create_entity(
            "/api/notes/",
            {
                "display": f"Graph Research Notes {self.short_label}",
                "description": "Dense graph relation test notes.",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )
        note_2 = self._create_entity(
            "/api/notes/",
            {
                "display": f"Adaptation Mapping Notes {self.short_label}",
                "description": "Cross-media links and entities.",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )

        loc_1 = self._create_entity(
            "/api/locations/",
            {
                "display": f"London Stage {self.short_label}",
                "city": "London",
                "country": "United Kingdom",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )
        loc_2 = self._create_entity(
            "/api/locations/",
            {
                "display": f"Studio Lot {self.short_label}",
                "city": "Los Angeles",
                "country": "United States",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )

        movie_1 = self._create_entity(
            "/api/movies/",
            {
                "display": f"The Godfather {self.short_label}",
                "year": 1972,
                "language": "English",
                "country": "United States",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )
        movie_2 = self._create_entity(
            "/api/movies/",
            {
                "display": f"Game of Thrones {self.short_label}",
                "year": 2011,
                "language": "English",
                "country": "United States",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )
        movie_3 = self._create_entity(
            "/api/movies/",
            {
                "display": f"Shakespeare in Love {self.short_label}",
                "year": 1998,
                "language": "English",
                "country": "United Kingdom",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )

        book_1 = self._create_entity(
            "/api/books/",
            {
                "display": f"Hamlet {self.short_label}",
                "year": 1603,
                "language": "English",
                "country": "England",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )
        book_2 = self._create_entity(
            "/api/books/",
            {
                "display": f"A Game of Thrones {self.short_label}",
                "year": 1996,
                "language": "English",
                "country": "United States",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )

        container_1 = self._create_entity(
            "/api/containers/",
            {
                "display": f"Archive Crate A {self.short_label}",
                "description": "Primary archive crate",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )
        container_2 = self._create_entity(
            "/api/containers/",
            {
                "display": f"Archive Crate B {self.short_label}",
                "description": "Nested container",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )

        asset_1 = self._create_entity(
            "/api/assets/",
            {
                "display": f"Cinema Camera {self.short_label}",
                "value": "2500.00",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )
        asset_2 = self._create_entity(
            "/api/assets/",
            {
                "display": f"Annotated Script {self.short_label}",
                "value": "500.00",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )

        org_1 = self._create_entity(
            "/api/orgs/",
            {
                "display": f"Classic Cinema Guild {self.short_label}",
                "name": "Classic Cinema Guild",
                "kind": "Company",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )
        org_2 = self._create_entity(
            "/api/orgs/",
            {
                "display": f"Royal Stage Society {self.short_label}",
                "name": "Royal Stage Society",
                "kind": "Club",
                "tags": [self.run_id, "SuiteD", "GraphRich"],
            },
        )

        # Dense, valid relations (including repeated relation types from same source)
        self._create_relation(shakespeare, grrm, "IS_COLLEAGUE_OF")
        self._create_relation(shakespeare, pacino, "IS_FRIEND_OF")

        self._create_relation(org_1, pacino, "HAS_EMPLOYEE")
        self._create_relation(org_1, coppola, "HAS_EMPLOYEE")
        self._create_relation(org_1, grrm, "HAS_MEMBER")
        self._create_relation(org_2, shakespeare, "HAS_MEMBER")

        self._create_relation(org_1, loc_2, "IS_LOCATED_AT")
        self._create_relation(org_2, loc_1, "IS_LOCATED_AT")
        self._create_relation(loc_2, loc_1, "IS_LOCATED_IN")

        self._create_relation(movie_1, pacino, "HAS_ACTOR")
        self._create_relation(movie_1, coppola, "HAS_DIRECTOR")
        self._create_relation(movie_2, pacino, "HAS_ACTOR")
        self._create_relation(movie_2, grrm, "HAS_DIRECTOR")
        self._create_relation(movie_3, shakespeare, "HAS_ACTOR")

        self._create_relation(book_1, shakespeare, "HAS_AS_AUTHOR")
        self._create_relation(book_2, grrm, "HAS_AS_AUTHOR")
        self._create_relation(book_2, movie_2, "INSPIRED")
        self._create_relation(book_1, loc_1, "IS_LOCATED_IN")

        self._create_relation(container_2, container_1, "IS_CONTAINED_IN")
        self._create_relation(container_1, loc_2, "IS_LOCATED_IN")
        self._create_relation(asset_1, container_1, "IS_LOCATED_IN")
        self._create_relation(asset_2, container_2, "IS_LOCATED_IN")

        # Repeated same relation type from same source Note entity.
        self._create_relation(note_1, movie_1, "IS_RELATED_TO")
        self._create_relation(note_1, movie_2, "IS_RELATED_TO")
        self._create_relation(note_1, book_1, "IS_RELATED_TO")
        self._create_relation(note_2, org_1, "IS_RELATED_TO")
        self._create_relation(note_2, asset_1, "IS_RELATED_TO")

        # Verify each entity type participates with multiple connections.
        for entity_id, min_total in [
            (shakespeare, 3),
            (note_1, 3),
            (loc_2, 3),
            (movie_1, 3),
            (book_2, 2),
            (container_1, 3),
            (asset_1, 2),
            (org_1, 4),
        ]:
            outgoing, incoming = self._relation_totals(entity_id)
            self.assertGreaterEqual(
                outgoing + incoming,
                min_total,
                f"Entity {entity_id} expected >= {min_total} total relations, got {outgoing + incoming}",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
