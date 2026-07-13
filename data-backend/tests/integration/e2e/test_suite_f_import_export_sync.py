"""
Suite F - Import/Export Sync E2E (BDD Overview)

Feature: Synchronous import/export APIs preserve entity graph and payload integrity.

Scenario: Export full snapshot
    Given a user-owned graph
    When /api/entities/export/ is requested
    Then entities/relations/tags are exported with expected shape.

Scenario: Export selected entities with relation hops
    Given linked entities
    When /api/entities/export-selected/ is called with max_hops
    Then exported network reflects requested closure depth.

Scenario: Import exported snapshot
    Given an exported snapshot file
    When /api/entities/import_data/ is called
    Then entities and relations are restored.

Scenario: Re-import idempotency
    Given the same snapshot imported twice
    When import is repeated
    Then entity count does not grow unexpectedly.
"""

from __future__ import annotations

import io
import json
import time
import unittest
from datetime import datetime, timezone

from .client import E2EApiClient
from .cleanup import cleanup_suite_state
from .config import load_config


class SuiteFImportExportSyncE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        log_title: Suite F Setup
        id: F-00
        feature: Import Export Setup
        scenario: Authenticate and clean state
        objective: Ensure deterministic import/export baseline
        """
        cls.cfg = load_config()
        cls.client = E2EApiClient(cls.cfg.base_url, cls.cfg.timeout_seconds)
        cls.slow_client = E2EApiClient(cls.cfg.base_url, max(cls.cfg.timeout_seconds, 180))
        cls.run_id = f"E2E-F-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        cls.short_label = f"E2E{datetime.now(timezone.utc).strftime('%S')}"

        login = cls.client.login(cls.cfg.email, cls.cfg.password)
        if login.status_code not in (200, 201):
            raise RuntimeError(f"Suite F login failed: {login.status_code} {login.body}")
        slow_login = cls.slow_client.login(cls.cfg.email, cls.cfg.password)
        if slow_login.status_code not in (200, 201):
            raise RuntimeError(f"Suite F slow-client login failed: {slow_login.status_code} {slow_login.body}")

        cleanup_stats = cleanup_suite_state(cls.client)
        print(
            f"[Suite F setup] cleaned entities={cleanup_stats['entities']} tags={cleanup_stats['tags']}"
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

    def _count_entities(self) -> int:
        resp = self.client.get("/api/entities/?limit=10000")
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = self.client.json_or_empty(resp)
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            return int(payload.get("count", 0))
        return 0

    def _create_entity(self, endpoint: str, payload: dict) -> str:
        resp = self.client.post(endpoint, json=payload)
        self.assertEqual(resp.status_code, 201, resp.text)
        data = self.client.json_or_empty(resp)
        entity_id = data.get("id")
        self.assertTrue(entity_id)
        return str(entity_id)

    def _create_relation(self, from_entity: str, to_entity: str, relation_type: str) -> str:
        resp = self.client.post(
            "/api/relations/",
            json={
                "from_entity": from_entity,
                "to_entity": to_entity,
                "relation_type": relation_type,
            },
        )
        self.assertIn(resp.status_code, (200, 201), resp.text)
        relation_id = self.client.json_or_empty(resp).get("id")
        self.assertTrue(relation_id)
        return str(relation_id)

    def _seed_snapshot_fixture(self):
        person_id = self._create_entity(
            "/api/people/",
            {
                "display": f"William Shakespeare {self.short_label}",
                "first_name": "William",
                "last_name": "Shakespeare",
                "tags": [self.run_id, "SuiteF", "Literature/Shakespeare"],
            },
        )
        movie_id = self._create_entity(
            "/api/movies/",
            {
                "display": f"Shakespeare in Love {self.short_label}",
                "year": 1998,
                "language": "English",
                "country": "United Kingdom",
                "tags": [self.run_id, "SuiteF", "Media/Shakespeare"],
            },
        )
        book_id = self._create_entity(
            "/api/books/",
            {
                "display": f"Hamlet {self.short_label}",
                "year": 1603,
                "language": "English",
                "country": "England",
                "tags": [self.run_id, "SuiteF", "Literature/Shakespeare"],
            },
        )
        note_id = self._create_entity(
            "/api/notes/",
            {
                "display": f"Export Notes {self.short_label}",
                "description": "Snapshot fixture for import/export suite",
                "tags": [self.run_id, "SuiteF", "Notes"],
            },
        )
        self._create_relation(movie_id, person_id, "HAS_ACTOR")
        self._create_relation(book_id, movie_id, "INSPIRED")
        self._create_relation(note_id, book_id, "IS_RELATED_TO")
        return {
            "person": person_id,
            "movie": movie_id,
            "book": book_id,
            "note": note_id,
        }

    def test_01_export_full_snapshot_shape(self):
        """
        log_title: Export Snapshot
        id: F-01
        feature: Export Sync
        scenario: Export full user dataset
        objective: Validate payload shape and included graph collections
        """
        self._seed_snapshot_fixture()

        export_resp = self.client.get("/api/entities/export/")
        self.assertEqual(export_resp.status_code, 200, export_resp.text)

        payload = json.loads(export_resp.text)
        self.assertEqual(payload.get("export_version"), "1.0")
        self.assertIsInstance(payload.get("entities"), list)
        self.assertGreaterEqual(len(payload.get("entities") or []), 4)
        self.assertIsInstance(payload.get("relations"), list)
        self.assertGreaterEqual(len(payload.get("relations") or []), 3)
        self.assertIsInstance(payload.get("tags"), list)

    def test_02_export_selected_hops(self):
        """
        log_title: Export Selected
        id: F-02
        feature: Export Selected
        scenario: Export relation-closure subsets with max_hops
        objective: Validate selected export network semantics
        """
        ids = self._seed_snapshot_fixture()

        hop0_resp = self.client.post(
            "/api/entities/export-selected/",
            json={"entity_ids": [ids["person"]], "max_hops": 0},
        )
        self.assertEqual(hop0_resp.status_code, 200, hop0_resp.text)
        hop0 = json.loads(hop0_resp.text)
        hop0_entities = hop0.get("entities") or []
        hop0_ids = {item.get("id") for item in hop0_entities if isinstance(item, dict)}
        self.assertIn(ids["person"], hop0_ids)
        self.assertEqual(len(hop0_ids), 1)

        hop1_resp = self.client.post(
            "/api/entities/export-selected/",
            json={"entity_ids": [ids["book"]], "max_hops": 1},
        )
        self.assertEqual(hop1_resp.status_code, 200, hop1_resp.text)
        hop1 = json.loads(hop1_resp.text)
        hop1_entities = hop1.get("entities") or []
        hop1_ids = {item.get("id") for item in hop1_entities if isinstance(item, dict)}
        self.assertIn(ids["book"], hop1_ids)
        # At least one relation neighbor should be included at hop 1.
        self.assertGreaterEqual(len(hop1_ids), 2)

    def test_03_import_snapshot_restore(self):
        """
        log_title: Import Snapshot
        id: F-03
        feature: Import Sync
        scenario: Import from exported snapshot file
        objective: Validate restore and created/skipped style stats response
        """
        self._seed_snapshot_fixture()

        export_resp = self.client.get("/api/entities/export/")
        self.assertEqual(export_resp.status_code, 200, export_resp.text)
        export_json = export_resp.text

        cleanup_stats = cleanup_suite_state(self.client)
        self.assertGreaterEqual(cleanup_stats["entities"], 1)

        import_resp = self.slow_client.post(
            "/api/entities/import_data/",
            files={"file": ("suite_f_import.json", io.BytesIO(export_json.encode("utf-8")), "application/json")},
        )
        self.assertEqual(import_resp.status_code, 200, import_resp.text)
        import_payload = self.client.json_or_empty(import_resp)
        self.assertTrue(import_payload.get("success"))
        self.assertIn("stats", import_payload)

        restored_count = self._count_entities()
        self.assertGreaterEqual(restored_count, 4)

    def test_04_reimport_idempotency_count_stability(self):
        """
        log_title: Reimport Idempotency
        id: F-04
        feature: Import Reimport Semantics
        scenario: Import identical snapshot twice
        objective: Validate repeated import does not create duplicate entities
        """
        self._seed_snapshot_fixture()

        export_resp = self.client.get("/api/entities/export/")
        self.assertEqual(export_resp.status_code, 200, export_resp.text)
        export_json = export_resp.text

        cleanup_suite_state(self.client)

        import_1 = self.slow_client.post(
            "/api/entities/import_data/",
            files={"file": ("suite_f_import_once.json", io.BytesIO(export_json.encode("utf-8")), "application/json")},
        )
        self.assertEqual(import_1.status_code, 200, import_1.text)
        count_after_1 = self._count_entities()
        self.assertGreaterEqual(count_after_1, 4)

        import_2 = self.slow_client.post(
            "/api/entities/import_data/",
            files={"file": ("suite_f_import_twice.json", io.BytesIO(export_json.encode("utf-8")), "application/json")},
        )
        self.assertEqual(import_2.status_code, 200, import_2.text)

        # Give async side-effects/signals a short moment to settle.
        time.sleep(0.5)
        count_after_2 = self._count_entities()

        self.assertEqual(count_after_2, count_after_1)
        import_2_payload = self.client.json_or_empty(import_2)
        self.assertTrue(import_2_payload.get("success"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
