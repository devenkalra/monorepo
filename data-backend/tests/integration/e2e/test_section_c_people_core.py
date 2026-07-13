"""
Section C - People Core CRUD E2E (BDD Overview)

Feature: People domain core API behavior is correct end-to-end for authenticated users.

Scenario: CRUD matrix across all entity types
    Given an authenticated user and valid payloads for Person, Note, Location, Movie, Book,
    Container, Asset, and Org
    When each entity is created, retrieved, patched, read via the generic /api/entities endpoint,
    and then deleted
    Then each step returns expected HTTP status codes and patched fields persist as expected

Scenario: Tag create/list/delete and tag cleanup on linked entities
    Given an entity linked to a tag and a manually created tag
    When tags are listed and the linked tag is deleted
    Then the deleted linked tag is removed from entity tags and both tag deletions succeed

Scenario: Recent entities endpoint behavior
    Given multiple newly created entities
    When /api/entities/recent is queried with limit and pagination/sort parameters
    Then response shape and item limits/pagination metadata match expectations

Scenario: Relations action and LLM context contract
    Given two entities connected by a relation
    When relations and llm_context endpoints are requested
    Then outgoing/incoming relation structures are returned and invalid direction is rejected

Scenario: Common multi-valued fields and person phones round-trip
    Given payloads that include urls, photos, attachments, and locations for each entity type,
    and phones for person
    When those entities are created and patched
    Then both type-specific retrieve and generic /api/entities retrieve return persisted arrays
"""

from __future__ import annotations

import io
import time
import unittest
from datetime import datetime

from .client import E2EApiClient
from .cleanup import cleanup_suite_state
from .config import load_config


class PeopleCoreCrudE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        log_title: Test User Login
        feature: Auth Bootstrap
        scenario: Authenticate E2E user before Section C scenarios
        objective: Ensure a valid access token exists for all API calls in this suite
        """
        cls.cfg = load_config()
        cls.client = E2EApiClient(cls.cfg.base_url, cls.cfg.timeout_seconds)
        cls.run_id = f"E2E-C-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        cls.created_entity_ids = []
        cls.created_tag_names = []

        login_result = cls.client.login(cls.cfg.email, cls.cfg.password)
        if login_result.status_code not in (200, 201):
            raise RuntimeError(f"Login failed for E2E setup: {login_result.status_code} {login_result.body}")

        cleanup_stats = cleanup_suite_state(cls.client)
        print(
            f"[Suite C setup] cleaned entities={cleanup_stats['entities']} tags={cleanup_stats['tags']}"
        )

    @classmethod
    def tearDownClass(cls):
        # Keep end state for interactive verification.
        return

    @staticmethod
    def _items(payload):
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            return payload["results"]
        return []

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

    def _create_entity(self, endpoint: str, payload: dict) -> str:
        response = self.client.post(endpoint, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        data = self.client.json_or_empty(response)
        entity_id = data.get("id")
        self.assertTrue(entity_id, f"Missing id in create response: {data}")
        self.created_entity_ids.append(entity_id)
        return entity_id

    @staticmethod
    def _tiny_png_bytes() -> bytes:
        from PIL import Image

        buf = io.BytesIO()
        image = Image.new("RGB", (16, 16), (52, 152, 219))
        image.save(buf, format="PNG")
        return buf.getvalue()

    def _upload_image_and_assert_metadata(self, filename: str) -> dict:
        file_data = self._tiny_png_bytes()
        response = self.client.post(
            "/api/upload/",
            files={"file": (filename, io.BytesIO(file_data), "image/png")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        payload = self.client.json_or_empty(response)

        # Upload API contract: url/path/hash and derivative metadata for image uploads.
        self.assertIn("url", payload)
        self.assertIn("path", payload)
        self.assertIn("sha256", payload)
        self.assertIn("thumbnail_url", payload)
        self.assertTrue(str(payload.get("url", "")).startswith("/media/"))
        self.assertTrue(str(payload.get("thumbnail_url", "")).startswith("/media/"))

        return payload

    def test_01_entity_crud_matrix_all_types(self):
        """
        log_title: Entity CRUD
        id: C-01
        feature: People Core CRUD
        scenario: Create/retrieve/patch/generic-retrieve/delete for every entity type
        objective: Validate typed endpoints and /api/entities parity on core CRUD behavior
        """
        matrix = [
            {
                "name": "Person",
                "endpoint": "/api/people/",
                "create": {
                    "display": f"{self.run_id} | Dr. Mary Jane O'Connor, PhD",
                    "first_name": "Mary Jane",
                    "last_name": "O'Connor-Singh",
                    "description": "Senior data engineer; enjoys long-form notes, APIs, and clean migrations.",
                    "tags": [self.run_id, "People/Colleagues", "R&D-Team"],
                },
                "patch": {"profession": "Principal Engineer, Data Platforms"},
                "assert_patch_field": "profession",
                "assert_patch_value": "Principal Engineer, Data Platforms",
            },
            {
                "name": "Note",
                "endpoint": "/api/notes/",
                "create": {
                    "display": f"{self.run_id} | Sprint Retro: Q3 Planning",
                    "description": "Agenda: API parity, search relevance, and import idempotency.\nAction items: validate edge-cases + rollout plan.",
                    "tags": [self.run_id, "Work/Meetings", "Planning-Q3"],
                    "date": "2026-07-12",
                },
                "patch": {"description": "Updated notes: prioritize customer-impact fixes, then optimize indexing throughput."},
                "assert_patch_field": "description",
                "assert_patch_value": "Updated notes: prioritize customer-impact fixes, then optimize indexing throughput.",
            },
            {
                "name": "Location",
                "endpoint": "/api/locations/",
                "create": {
                    "display": f"{self.run_id} | Apt #5B, 221B Baker St.",
                    "address1": "221B Baker Street",
                    "address2": "Apt #5B",
                    "city": "San Francisco",
                    "state": "California",
                    "country": "United States",
                    "postal_code": "94107",
                    "tags": [self.run_id, "Location/Home", "North-America"],
                },
                "patch": {"city": "Oakland"},
                "assert_patch_field": "city",
                "assert_patch_value": "Oakland",
            },
            {
                "name": "Movie",
                "endpoint": "/api/movies/",
                "create": {
                    "display": f"{self.run_id} | Spider-Man: No Way Home (Team Rewatch)",
                    "description": "Weekend watchlist pick; discussed in movie-night channel.",
                    "year": 2021,
                    "language": "English",
                    "country": "United States",
                    "tags": [self.run_id, "Media/Movies", "Weekend-Plans"],
                },
                "patch": {"year": 2022},
                "assert_patch_field": "year",
                "assert_patch_value": 2022,
            },
            {
                "name": "Book",
                "endpoint": "/api/books/",
                "create": {
                    "display": f"{self.run_id} | The Hitchhiker's Guide to the Galaxy, Vol. 1",
                    "year": 1979,
                    "language": "English",
                    "country": "United Kingdom",
                    "summary": "Classic sci-fi satire; favorite quote: Don't Panic.",
                    "tags": [self.run_id, "Reading/Favorites", "Sci-Fi"],
                },
                "patch": {"summary": "Re-read notes: witty, fast, and surprisingly relevant to modern systems design."},
                "assert_patch_field": "summary",
                "assert_patch_value": "Re-read notes: witty, fast, and surprisingly relevant to modern systems design.",
            },
            {
                "name": "Container",
                "endpoint": "/api/containers/",
                "create": {
                    "display": f"{self.run_id} | Garage Shelf Bin - 'Winter Gear'",
                    "description": "Black storage tote on rack B2; includes ski gloves, beanies, and spare thermals.",
                    "tags": [self.run_id, "Home/Storage", "Seasonal-Winter"],
                },
                "patch": {"description": "Moved to rack C1; now also contains extra charging cables and labels."},
                "assert_patch_field": "description",
                "assert_patch_value": "Moved to rack C1; now also contains extra charging cables and labels.",
            },
            {
                "name": "Asset",
                "endpoint": "/api/assets/",
                "create": {
                    "display": f"{self.run_id} | MacBook Pro 16\" (M3 Max)",
                    "description": "Primary workstation, space black, serial tracked in secure inventory.",
                    "value": "3499.99",
                    "acquired_on": "2025-11-18",
                    "tags": [self.run_id, "Assets/Hardware", "Work-Equipment"],
                },
                "patch": {"value": "3299.50"},
                "assert_patch_field": "value",
                "assert_patch_value": "3299.5",
            },
            {
                "name": "Org",
                "endpoint": "/api/orgs/",
                "create": {
                    "display": f"{self.run_id} | St. John's Research & Development, LLC",
                    "name": "St. John's Research & Development, LLC",
                    "kind": "Company",
                    "tags": [self.run_id, "Work/Partners", "Org-External"],
                },
                "patch": {"name": "St. John's Research & Development, LLC (West Coast)"},
                "assert_patch_field": "name",
                "assert_patch_value": "St. John's Research & Development, LLC (West Coast)",
            },
        ]

        for item in matrix:
            with self.subTest(entity_type=item["name"]):
                self.client.set_subtest_phrase(f"{item['name']} CRUD")
                try:
                    print(f"\n  [test_01][{item['name']}] START endpoint={item['endpoint']}")
                    print(f"  [test_01][{item['name']}] CREATE payload={item['create']}")
                    with self.client.log_call_purpose(f"Create {item['name']}"):
                        entity_id = self._create_entity(item["endpoint"], item["create"])
                    print(f"  [test_01][{item['name']}] CREATED id={entity_id}")

                    with self.client.log_call_purpose(f"Get {item['name']} by ID"):
                        retrieve = self.client.get(f"{item['endpoint']}{entity_id}/")
                    print(
                        f"  [test_01][{item['name']}] RETRIEVE status={retrieve.status_code} id={entity_id}"
                    )
                    self.assertEqual(retrieve.status_code, 200, retrieve.text)
                    retrieve_data = self.client.json_or_empty(retrieve)
                    self.assertEqual(retrieve_data.get("id"), entity_id)

                    print(f"  [test_01][{item['name']}] PATCH payload={item['patch']}")
                    patch_field = item["assert_patch_field"]
                    with self.client.log_call_purpose(f"Update {patch_field}"):
                        patch_resp = self.client.patch(f"{item['endpoint']}{entity_id}/", json=item["patch"])
                    print(
                        f"  [test_01][{item['name']}] PATCH status={patch_resp.status_code} id={entity_id}"
                    )
                    self.assertEqual(patch_resp.status_code, 200, patch_resp.text)
                    patch_data = self.client.json_or_empty(patch_resp)
                    self.assertIn(item["assert_patch_field"], patch_data)

                    # Compare stringified values to avoid decimal vs float formatting variance.
                    self.assertEqual(
                        str(patch_data.get(item["assert_patch_field"])),
                        str(item["assert_patch_value"]),
                    )
                    print(
                        f"  [test_01][{item['name']}] PATCH ASSERT "
                        f"{item['assert_patch_field']}={patch_data.get(item['assert_patch_field'])}"
                    )

                    with self.client.log_call_purpose("Get via /api/entities"):
                        generic_retrieve = self.client.get(f"/api/entities/{entity_id}/")
                    print(
                        f"  [test_01][{item['name']}] GENERIC RETRIEVE status={generic_retrieve.status_code} "
                        f"id={entity_id}"
                    )
                    self.assertEqual(generic_retrieve.status_code, 200, generic_retrieve.text)
                    generic_data = self.client.json_or_empty(generic_retrieve)
                    self.assertEqual(generic_data.get("id"), entity_id)
                    self.assertIn("entity_text_block", generic_data)

                    with self.client.log_call_purpose(f"Delete {item['name']}"):
                        delete_resp = self.client.delete(f"{item['endpoint']}{entity_id}/")
                    print(f"  [test_01][{item['name']}] DELETE status={delete_resp.status_code} id={entity_id}")
                    self.assertEqual(delete_resp.status_code, 204, delete_resp.text)

                    with self.client.log_call_purpose("Confirm deleted (404)"):
                        post_delete = self.client.get(f"{item['endpoint']}{entity_id}/")
                    print(
                        f"  [test_01][{item['name']}] VERIFY DELETE status={post_delete.status_code} "
                        f"id={entity_id}"
                    )
                    self.assertEqual(post_delete.status_code, 404, post_delete.text)

                    if entity_id in self.created_entity_ids:
                        self.created_entity_ids.remove(entity_id)

                    print(f"  [test_01][{item['name']}] DONE id={entity_id}")
                finally:
                    self.client.set_subtest_phrase(None)

    def test_02_tag_create_list_delete_and_entity_tag_cleanup(self):
        """
        log_title: Test Tag Lifecycle and Cleanup
        id: C-02
        feature: Tag Management
        scenario: Create/list/delete tags and remove deleted tag references from entities
        objective: Ensure tag API and entity tag cleanup behavior are consistent
        """
        person_id = self._create_entity(
            "/api/people/",
            {
                "display": f"{self.run_id} | Priya N. Raman (Tag Owner)",
                "first_name": "Priya N.",
                "last_name": "Raman",
                "tags": [f"{self.run_id}-TagA"],
            },
        )

        tag_name = f"{self.run_id}-ManualTag"
        create_tag = self.client.post("/api/tags/", json={"name": tag_name, "count": 1})
        self.assertIn(create_tag.status_code, (200, 201), create_tag.text)
        self.created_tag_names.append(tag_name)

        list_tags = self.client.get("/api/tags/")
        self.assertEqual(list_tags.status_code, 200, list_tags.text)
        items = self._items(self.client.json_or_empty(list_tags))
        names = {item.get("name") for item in items if isinstance(item, dict)}
        self.assertIn(tag_name, names)

        # Delete a tag that exists on entity and validate entity tags are updated.
        linked_tag = f"{self.run_id}-TagA"
        self.created_tag_names.append(linked_tag)
        del_linked = self.client.delete(f"/api/tags/{quote(linked_tag, safe='')}/")
        self.assertEqual(del_linked.status_code, 204, del_linked.text)

        person_after = self.client.get(f"/api/people/{person_id}/")
        self.assertEqual(person_after.status_code, 200, person_after.text)
        person_data = self.client.json_or_empty(person_after)
        self.assertNotIn(linked_tag, person_data.get("tags") or [])

        del_manual = self.client.delete(f"/api/tags/{quote(tag_name, safe='')}/")
        self.assertEqual(del_manual.status_code, 204, del_manual.text)

    def test_03_recent_entities_limit_pagination_and_sort(self):
        """
        log_title: Test Recent Entities Pagination and Sorting
        id: C-03
        feature: Recent Entities
        scenario: Query /api/entities/recent with limit and page/sort controls
        objective: Verify response shape and pagination semantics
        """
        created = []
        for idx in range(3):
            entity_id = self._create_entity(
                "/api/people/",
                {
                    "display": f"{self.run_id} | Recent Activity Person #{idx+1}",
                    "first_name": ["Avery", "Noah", "Leah"][idx],
                    "last_name": ["Patel", "O'Brien", "Kim-Santos"][idx],
                    "tags": [self.run_id],
                },
            )
            created.append(entity_id)
            time.sleep(0.05)

        limit_resp = self.client.get("/api/entities/recent/?limit=2")
        self.assertEqual(limit_resp.status_code, 200, limit_resp.text)
        limit_items = self._items(self.client.json_or_empty(limit_resp))
        self.assertLessEqual(len(limit_items), 2)

        paged_resp = self.client.get("/api/entities/recent/?page=1&page_size=2&sort_by=display")
        self.assertEqual(paged_resp.status_code, 200, paged_resp.text)
        payload = self.client.json_or_empty(paged_resp)
        self.assertIsInstance(payload, dict)
        self.assertIn("results", payload)
        self.assertIn("count", payload)
        self.assertIn("total_pages", payload)

    def test_04_entity_relations_action_and_llm_context(self):
        """
        log_title: Test Relations and LLM Context Endpoints
        id: C-04
        feature: Entity Relations
        scenario: Create relation, fetch relations and llm_context, validate invalid direction handling
        objective: Confirm graph context contract and guardrails
        """
        p1_id = self._create_entity(
            "/api/people/",
            {
                "display": f"{self.run_id} | Ana-Maria Torres",
                "first_name": "Ana-Maria",
                "last_name": "Torres",
                "tags": [self.run_id],
            },
        )
        p2_id = self._create_entity(
            "/api/people/",
            {
                "display": f"{self.run_id} | Liam O'Neill",
                "first_name": "Liam",
                "last_name": "O'Neill",
                "tags": [self.run_id],
            },
        )

        rel_create = self.client.post(
            "/api/relations/",
            json={
                "from_entity": p1_id,
                "to_entity": p2_id,
                "relation_type": "IS_FRIEND_OF",
            },
        )
        self.assertIn(rel_create.status_code, (200, 201), rel_create.text)

        rel_resp = self.client.get(f"/api/entities/{p1_id}/relations/?direction=both")
        self.assertEqual(rel_resp.status_code, 200, rel_resp.text)
        rel_data = self.client.json_or_empty(rel_resp)
        self.assertIn("outgoing", rel_data)
        self.assertIn("incoming", rel_data)
        self.assertIn("text_block", rel_data)
        self.assertTrue(any(item.get("entity", {}).get("id") == p2_id for item in rel_data.get("outgoing", [])))

        llm_ctx = self.client.get(f"/api/entities/{p1_id}/llm_context/")
        self.assertEqual(llm_ctx.status_code, 200, llm_ctx.text)
        llm_data = self.client.json_or_empty(llm_ctx)
        self.assertIsInstance(llm_data.get("text_block"), str)

        bad_direction = self.client.get(f"/api/entities/{p1_id}/relations/?direction=invalid")
        self.assertEqual(bad_direction.status_code, 400, bad_direction.text)

    def test_05_common_multivalue_fields_and_person_phones_roundtrip(self):
        """
        log_title: Test Common Multi-value Fields with Real Uploads
        id: C-05
        feature: Multi-value Fields
        scenario: Upload files and persist urls/photos/attachments/locations across entity types plus person phones
        objective: Ensure upload-derived media URLs and multi-valued fields round-trip via typed and generic endpoints
        """
        create_photo_upload = self._upload_image_and_assert_metadata(
            f"{self.run_id}-shared-photo-create.png"
        )
        create_attachment_upload = self._upload_image_and_assert_metadata(
            f"{self.run_id}-shared-attachment-create.png"
        )
        patch_photo_upload = self._upload_image_and_assert_metadata(
            f"{self.run_id}-shared-photo-patch.png"
        )
        patch_attachment_upload = self._upload_image_and_assert_metadata(
            f"{self.run_id}-shared-attachment-patch.png"
        )

        common_create = {
            "urls": [
                "https://example.com/profiles/jane-doe?ref=e2e",
                "https://intranet.example.org/wiki/Project-Atlas",
            ],
            "photos": [create_photo_upload["url"]],
            "attachments": [create_attachment_upload["url"]],
            "locations": [
                "HQ - Building A, Floor 5",
                "Remote: Montreal, QC",
            ],
        }
        common_patch = {
            "urls": [
                "https://example.com/profiles/jane-doe?ref=e2e-updated",
                "https://docs.example.org/design/api-v3",
            ],
            "photos": [patch_photo_upload["url"]],
            "attachments": [patch_attachment_upload["url"]],
            "locations": ["Satellite Office - Suite #210"],
        }

        cases = [
            {
                "name": "Person",
                "endpoint": "/api/people/",
                "create_extra": {
                    "first_name": "Alex",
                    "last_name": "O'Brien",
                    "phones": ["+1-415-555-0101", "+1 (650) 555-0199"],
                },
                "patch_extra": {"phones": ["+1-415-555-0111"]},
            },
            {
                "name": "Note",
                "endpoint": "/api/notes/",
                "create_extra": {"date": "2026-07-12", "description": "Common array fields smoke test."},
                "patch_extra": {},
            },
            {
                "name": "Location",
                "endpoint": "/api/locations/",
                "create_extra": {
                    "city": "San Jose",
                    "state": "California",
                    "country": "United States",
                    "postal_code": "95113",
                },
                "patch_extra": {},
            },
            {
                "name": "Movie",
                "endpoint": "/api/movies/",
                "create_extra": {"year": 2019, "language": "English", "country": "United States"},
                "patch_extra": {},
            },
            {
                "name": "Book",
                "endpoint": "/api/books/",
                "create_extra": {"year": 2021, "language": "English", "country": "United States", "summary": "Array field test."},
                "patch_extra": {},
            },
            {
                "name": "Container",
                "endpoint": "/api/containers/",
                "create_extra": {"description": "Common field validation container."},
                "patch_extra": {},
            },
            {
                "name": "Asset",
                "endpoint": "/api/assets/",
                "create_extra": {"value": "1250.00", "acquired_on": "2026-01-05"},
                "patch_extra": {},
            },
            {
                "name": "Org",
                "endpoint": "/api/orgs/",
                "create_extra": {"name": "Northwind Research Group", "kind": "Company"},
                "patch_extra": {},
            },
        ]

        for case in cases:
            with self.subTest(entity_type=case["name"]):
                self.client.set_subtest_phrase(f"{case['name']} common multi-value roundtrip")
                try:
                    payload = {
                        "display": f"{self.run_id} | Common Fields {case['name']}",
                        "tags": [self.run_id, "Common-Fields"],
                        **common_create,
                        **case["create_extra"],
                    }
                    entity_id = self._create_entity(case["endpoint"], payload)

                    type_get = self.client.get(f"{case['endpoint']}{entity_id}/")
                    self.assertEqual(type_get.status_code, 200, type_get.text)
                    type_data = self.client.json_or_empty(type_get)
                    self.assertEqual(type_data.get("urls"), common_create["urls"])
                    self.assertEqual(type_data.get("photos"), common_create["photos"])
                    self.assertEqual(type_data.get("attachments"), common_create["attachments"])
                    self.assertEqual(type_data.get("locations"), common_create["locations"])
                    if case["name"] == "Person":
                        self.assertEqual(type_data.get("phones"), case["create_extra"]["phones"])

                    patch_payload = {
                        **common_patch,
                        **case["patch_extra"],
                    }
                    patch_resp = self.client.patch(f"{case['endpoint']}{entity_id}/", json=patch_payload)
                    self.assertEqual(patch_resp.status_code, 200, patch_resp.text)

                    generic_get = self.client.get(f"/api/entities/{entity_id}/")
                    self.assertEqual(generic_get.status_code, 200, generic_get.text)
                    generic_data = self.client.json_or_empty(generic_get)
                    self.assertEqual(generic_data.get("urls"), common_patch["urls"])
                    self.assertEqual(generic_data.get("photos"), common_patch["photos"])
                    self.assertEqual(generic_data.get("attachments"), common_patch["attachments"])
                    self.assertEqual(generic_data.get("locations"), common_patch["locations"])
                    if case["name"] == "Person":
                        self.assertEqual(generic_data.get("phones"), case["patch_extra"]["phones"])

                    delete_resp = self.client.delete(f"{case['endpoint']}{entity_id}/")
                    self.assertEqual(delete_resp.status_code, 204, delete_resp.text)
                    if entity_id in self.created_entity_ids:
                        self.created_entity_ids.remove(entity_id)
                finally:
                    self.client.set_subtest_phrase(None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
