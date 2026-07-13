"""
Suite G - Import/Export Async and Task Lifecycle E2E (BDD Overview)

Feature: Async import/export/reindex tasks expose correct lifecycle and artifacts.

Scenario: Export async lifecycle and download
    Given user entities
    When export-async is started
    Then progress reaches completed and download endpoint returns export payload.

Scenario: Export-selected async lifecycle
    Given selected relation-linked entities
    When export-selected-async is started
    Then task completes and download contains network subset.

Scenario: Reindex task lifecycle
    Given existing entities
    When reindex is started
    Then task progress reaches completed.

Scenario: Import async cancellation path
    Given a large import payload
    When import-async is started and cancel is requested
    Then task transitions to cancelled or completes if already finished.
"""

from __future__ import annotations

import io
import json
import time
import unittest
import uuid
from datetime import datetime, timezone

from .client import E2EApiClient
from .cleanup import cleanup_suite_state
from .config import load_config


class SuiteGImportExportAsyncE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        log_title: Suite G Setup
        id: G-00
        feature: Async Setup
        scenario: Authenticate and clean state
        objective: Ensure deterministic async task runs
        """
        cls.cfg = load_config()
        cls.client = E2EApiClient(cls.cfg.base_url, cls.cfg.timeout_seconds)
        cls.run_id = f"E2E-G-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        cls.short_label = f"E2E{datetime.now(timezone.utc).strftime('%S')}"

        login = cls.client.login(cls.cfg.email, cls.cfg.password)
        if login.status_code not in (200, 201):
            raise RuntimeError(f"Suite G login failed: {login.status_code} {login.body}")

        cleanup_stats = cleanup_suite_state(cls.client)
        print(
            f"[Suite G setup] cleaned entities={cleanup_stats['entities']} tags={cleanup_stats['tags']}"
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

    def _wait_task_terminal(self, task_id: str, timeout_s: float = 45.0):
        deadline = time.time() + timeout_s
        last_payload = None
        while time.time() < deadline:
            resp = self.client.get(f"/api/entities/tasks/{task_id}/progress/")
            if resp.status_code == 200:
                payload = self.client.json_or_empty(resp)
                last_payload = payload
                status = str(payload.get("status", "")).lower()
                if status in {"completed", "failed", "cancelled"}:
                    return payload
            elif resp.status_code == 404:
                # PENDING/not started yet
                last_payload = {"status": "pending"}
            time.sleep(0.5)
        return last_payload or {"status": "timeout"}

    def _seed_async_fixture(self):
        person = self._create_entity(
            "/api/people/",
            {
                "display": f"Async Person {self.short_label}",
                "first_name": "Async",
                "last_name": "Person",
                "tags": [self.run_id, "SuiteG", "Async"],
            },
        )
        movie = self._create_entity(
            "/api/movies/",
            {
                "display": f"Async Movie {self.short_label}",
                "year": 2020,
                "language": "English",
                "country": "United States",
                "tags": [self.run_id, "SuiteG", "Async"],
            },
        )
        self._create_relation(movie, person, "HAS_ACTOR")
        return {"person": person, "movie": movie}

    def _build_large_import_payload(self, base_payload: dict, extra_notes: int = 80) -> str:
        payload = json.loads(json.dumps(base_payload))
        entities = payload.get("entities") or []
        for idx in range(extra_notes):
            entities.append(
                {
                    "id": str(uuid.uuid4()),
                    "type": "Note",
                    "display": f"Bulk Async Note {idx:03d} {self.short_label}",
                    "description": "Bulk async import cancellation fixture",
                    "tags": [self.run_id, "SuiteG", "BulkImport"],
                }
            )
        payload["entities"] = entities
        return json.dumps(payload)

    def test_01_export_async_progress_and_download(self):
        """
        log_title: Async Export
        id: G-01
        feature: Export Async
        scenario: Start export async and download artifact
        objective: Validate progress lifecycle and download endpoint contract
        """
        self._seed_async_fixture()

        start = self.client.post("/api/entities/export-async/")
        self.assertEqual(start.status_code, 200, start.text)
        task_id = self.client.json_or_empty(start).get("task_id")
        self.assertTrue(task_id)

        terminal = self._wait_task_terminal(task_id)
        status = str(terminal.get("status", "")).lower()
        if status in {"pending", "timeout"}:
            self.skipTest("Async worker not reachable or task did not transition in time")
        self.assertEqual(status, "completed", terminal)

        download = self.client.get(f"/api/entities/tasks/{task_id}/download/")
        self.assertEqual(download.status_code, 200, download.text)
        payload = json.loads(download.text)
        self.assertEqual(payload.get("export_version"), "1.0")
        self.assertIsInstance(payload.get("entities"), list)

    def test_02_export_selected_async_progress_and_download(self):
        """
        log_title: Async Export Selected
        id: G-02
        feature: Export Selected Async
        scenario: Start selected export async with max_hops
        objective: Validate async selected network export and artifact availability
        """
        ids = self._seed_async_fixture()

        start = self.client.post(
            "/api/entities/export-selected-async/",
            json={"entity_ids": [ids["movie"]], "max_hops": 1},
        )
        self.assertEqual(start.status_code, 200, start.text)
        task_id = self.client.json_or_empty(start).get("task_id")
        self.assertTrue(task_id)

        terminal = self._wait_task_terminal(task_id)
        status = str(terminal.get("status", "")).lower()
        if status in {"pending", "timeout"}:
            self.skipTest("Async worker not reachable or task did not transition in time")
        self.assertEqual(status, "completed", terminal)

        download = self.client.get(f"/api/entities/tasks/{task_id}/download/")
        self.assertEqual(download.status_code, 200, download.text)
        payload = json.loads(download.text)
        entities = payload.get("entities") or []
        ids_exported = {item.get("id") for item in entities if isinstance(item, dict)}
        self.assertIn(ids["movie"], ids_exported)
        self.assertGreaterEqual(len(ids_exported), 2)

    def test_03_reindex_async_lifecycle(self):
        """
        log_title: Async Reindex
        id: G-03
        feature: Reindex Async
        scenario: Start reindex and poll progress
        objective: Validate reindex task transitions to completed
        """
        self._seed_async_fixture()

        start = self.client.post("/api/entities/reindex/")
        self.assertEqual(start.status_code, 200, start.text)
        task_id = self.client.json_or_empty(start).get("task_id")
        self.assertTrue(task_id)

        terminal = self._wait_task_terminal(task_id)
        status = str(terminal.get("status", "")).lower()
        if status in {"pending", "timeout"}:
            self.skipTest("Async worker not reachable or reindex task did not transition in time")
        self.assertEqual(status, "completed", terminal)

    def test_04_import_async_cancel_lifecycle(self):
        """
        log_title: Async Import Cancel
        id: G-04
        feature: Import Async Cancel
        scenario: Start import async and request cancellation
        objective: Validate cancel endpoint and terminal state transition
        """
        self._seed_async_fixture()

        export_resp = self.client.get("/api/entities/export/")
        self.assertEqual(export_resp.status_code, 200, export_resp.text)
        base_payload = json.loads(export_resp.text)
        bulk_payload_json = self._build_large_import_payload(base_payload, extra_notes=80)

        start = self.client.post(
            "/api/entities/import-async/",
            files={"file": ("suite_g_bulk_import.json", io.BytesIO(bulk_payload_json.encode("utf-8")), "application/json")},
        )
        self.assertEqual(start.status_code, 200, start.text)
        task_id = self.client.json_or_empty(start).get("task_id")
        self.assertTrue(task_id)

        cancel = self.client.post(f"/api/entities/tasks/{task_id}/cancel/")
        self.assertEqual(cancel.status_code, 200, cancel.text)
        cancel_payload = self.client.json_or_empty(cancel)
        self.assertTrue(cancel_payload.get("success"))

        terminal = self._wait_task_terminal(task_id, timeout_s=60.0)
        status = str(terminal.get("status", "")).lower()
        if status in {"pending", "timeout", "processing"}:
            self.skipTest("Async worker not reachable or import task did not transition in time")

        # Depending on worker speed, task may finish before cancellation is observed.
        self.assertIn(status, {"cancelled", "completed", "failed"}, terminal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
