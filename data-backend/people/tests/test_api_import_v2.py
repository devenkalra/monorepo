import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from people.models import EntityRelation, Person

User = get_user_model()


class ImportV2APITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.client.force_authenticate(user=self.user)

    def _post_import(self, payload):
        content = json.dumps(payload).encode("utf-8")
        upload = SimpleUploadedFile("import.json", content, content_type="application/json")
        return self.client.post("/api/entities/import_data/", {"file": upload}, format="multipart")

    def test_v2_create_entity_with_import_ref(self):
        payload = {
            "import_version": "2.0",
            "allow_entity_delete_cascade": True,
            "entities": [
                {
                    "import_op": "create",
                    "import_ref": "person_1",
                    "type": "Person",
                    "display": "Created Person",
                    "first_name": "Created",
                }
            ],
        }

        response = self._post_import(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        person = Person.objects.filter(user=self.user, display="Created Person").first()
        self.assertIsNotNone(person)
        self.assertEqual(person.first_name, "Created")

    def test_v2_create_relation_with_import_refs(self):
        payload = {
            "import_version": "2.0",
            "allow_entity_delete_cascade": True,
            "entities": [
                {
                    "import_op": "create",
                    "import_ref": "parent",
                    "type": "Person",
                    "display": "Parent",
                },
                {
                    "import_op": "create",
                    "import_ref": "child",
                    "type": "Person",
                    "display": "Child",
                },
            ],
            "relations": [
                {
                    "import_op": "create",
                    "import_ref": "rel_1",
                    "from_import_ref": "parent",
                    "to_import_ref": "child",
                    "relation_type": "IS_PARENT_OF",
                }
            ],
        }

        response = self._post_import(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        parent = Person.objects.get(user=self.user, display="Parent")
        child = Person.objects.get(user=self.user, display="Child")
        relation = EntityRelation.objects.filter(
            from_entity=parent,
            to_entity=child,
            relation_type="IS_PARENT_OF",
        ).first()
        self.assertIsNotNone(relation)

    def test_v2_missing_import_op_defaults_to_update_for_id(self):
        person = Person.objects.create(
            user=self.user,
            display="Before",
            description="Keep me",
            first_name="Original",
        )

        payload = {
            "import_version": "2.0",
            "allow_entity_delete_cascade": True,
            "entities": [
                {
                    "id": str(person.id),
                    "display": "After",
                }
            ],
        }

        response = self._post_import(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        person.refresh_from_db()
        self.assertEqual(person.display, "After")
        self.assertEqual(person.description, "Keep me")
        self.assertEqual(person.first_name, "Original")

    def test_v2_replace_clears_unspecified_fields(self):
        person = Person.objects.create(
            user=self.user,
            display="Before Replace",
            description="Will be cleared",
            first_name="First",
            tags=["alpha"],
        )

        payload = {
            "import_version": "2.0",
            "allow_entity_delete_cascade": True,
            "entities": [
                {
                    "import_op": "replace",
                    "id": str(person.id),
                    "type": "Person",
                    "display": "After Replace",
                }
            ],
        }

        response = self._post_import(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        person.refresh_from_db()
        self.assertEqual(person.display, "After Replace")
        self.assertEqual(person.description, "")
        self.assertIsNone(person.first_name)
        self.assertEqual(person.tags, [])

    def test_v2_delete_entity_cascades_relations(self):
        parent = Person.objects.create(user=self.user, display="Parent")
        child = Person.objects.create(user=self.user, display="Child")
        EntityRelation.objects.create(
            from_entity=parent,
            to_entity=child,
            relation_type="IS_PARENT_OF",
        )

        payload = {
            "import_version": "2.0",
            "allow_entity_delete_cascade": True,
            "entities": [
                {
                    "import_op": "delete",
                    "id": str(parent.id),
                }
            ],
        }

        response = self._post_import(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(Person.objects.filter(id=parent.id).exists())
        self.assertEqual(
            EntityRelation.objects.filter(from_entity_id=parent.id).count()
            + EntityRelation.objects.filter(to_entity_id=parent.id).count(),
            0,
        )

    def test_v2_schema_rejects_id_and_import_ref_together(self):
        payload = {
            "import_version": "2.0",
            "allow_entity_delete_cascade": True,
            "entities": [
                {
                    "import_op": "create",
                    "id": "11111111-1111-1111-1111-111111111111",
                    "import_ref": "bad_ref",
                    "type": "Person",
                    "display": "Invalid",
                }
            ],
        }

        response = self._post_import(payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("schema validation failed", response.json().get("error", "").lower())

    def test_v2_duplicate_entity_import_ref_is_hard_failure(self):
        payload = {
            "import_version": "2.0",
            "allow_entity_delete_cascade": True,
            "entities": [
                {
                    "import_op": "create",
                    "import_ref": "dup_ref",
                    "type": "Person",
                    "display": "One",
                },
                {
                    "import_op": "create",
                    "import_ref": "dup_ref",
                    "type": "Person",
                    "display": "Two",
                },
            ],
        }

        response = self._post_import(payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("duplicate entity import_ref", response.json().get("error", "").lower())
        self.assertEqual(Person.objects.filter(user=self.user).count(), 0)

    def test_v2_duplicate_relation_import_ref_is_hard_failure(self):
        payload = {
            "import_version": "2.0",
            "allow_entity_delete_cascade": True,
            "entities": [
                {
                    "import_op": "create",
                    "import_ref": "a",
                    "type": "Person",
                    "display": "A",
                },
                {
                    "import_op": "create",
                    "import_ref": "b",
                    "type": "Person",
                    "display": "B",
                },
            ],
            "relations": [
                {
                    "import_op": "create",
                    "import_ref": "dup_rel",
                    "from_import_ref": "a",
                    "to_import_ref": "b",
                    "relation_type": "IS_PARENT_OF",
                },
                {
                    "import_op": "create",
                    "import_ref": "dup_rel",
                    "from_import_ref": "b",
                    "to_import_ref": "a",
                    "relation_type": "IS_CHILD_OF",
                },
            ],
        }

        response = self._post_import(payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("duplicate relation import_ref", response.json().get("error", "").lower())
        self.assertEqual(Person.objects.filter(user=self.user).count(), 0)
        self.assertEqual(EntityRelation.objects.count(), 0)

    def test_v2_any_operation_error_rolls_back_all_changes(self):
        existing = Person.objects.create(user=self.user, display="Existing")
        payload = {
            "import_version": "2.0",
            "allow_entity_delete_cascade": True,
            "entities": [
                {
                    "import_op": "create",
                    "import_ref": "new_ok",
                    "type": "Person",
                    "display": "Should Rollback",
                },
                {
                    "import_op": "update",
                    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "display": "Invalid Target",
                },
            ],
        }

        response = self._post_import(payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Person.objects.filter(user=self.user, display="Should Rollback").exists())
        existing.refresh_from_db()
        self.assertEqual(existing.display, "Existing")

    def test_v2_mixed_operations_and_relation_rewire(self):
        update_target = Person.objects.create(
            user=self.user,
            display="Update Me",
            description="Keep this",
            first_name="Old",
        )
        replace_target = Person.objects.create(
            user=self.user,
            display="Replace Me",
            description="Will clear",
            first_name="ToClear",
            tags=["x"],
        )
        delete_target = Person.objects.create(user=self.user, display="Delete Me")
        relation_to_delete = EntityRelation.objects.create(
            from_entity=update_target,
            to_entity=replace_target,
            relation_type="IS_FRIEND_OF",
        )

        payload = {
            "import_version": "2.0",
            "allow_entity_delete_cascade": True,
            "entities": [
                {
                    "import_op": "create",
                    "import_ref": "new_person",
                    "type": "Person",
                    "display": "New Person",
                },
                {
                    "import_op": "update",
                    "id": str(update_target.id),
                    "display": "Updated Name",
                },
                {
                    "import_op": "replace",
                    "id": str(replace_target.id),
                    "type": "Person",
                    "display": "Replaced Name",
                },
                {
                    "import_op": "delete",
                    "id": str(delete_target.id),
                },
            ],
            "relations": [
                {
                    "import_op": "create",
                    "import_ref": "new_rel",
                    "from_import_ref": "new_person",
                    "to_entity": str(update_target.id),
                    "relation_type": "IS_CHILD_OF",
                },
                {
                    "import_op": "delete",
                    "id": str(relation_to_delete.id),
                },
            ],
        }

        response = self._post_import(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        update_target.refresh_from_db()
        self.assertEqual(update_target.display, "Updated Name")
        self.assertEqual(update_target.description, "Keep this")

        replace_target.refresh_from_db()
        self.assertEqual(replace_target.display, "Replaced Name")
        self.assertEqual(replace_target.description, "")
        self.assertIsNone(replace_target.first_name)
        self.assertEqual(replace_target.tags, [])

        self.assertFalse(Person.objects.filter(id=delete_target.id).exists())
        self.assertFalse(EntityRelation.objects.filter(id=relation_to_delete.id).exists())

        new_person = Person.objects.filter(user=self.user, display="New Person").first()
        self.assertIsNotNone(new_person)
        self.assertTrue(
            EntityRelation.objects.filter(
                from_entity=new_person,
                to_entity=update_target,
                relation_type="IS_CHILD_OF",
            ).exists()
        )

    def test_import_rejects_mismatched_payload_user(self):
        payload = {
            "import_version": "2.0",
            "allow_entity_delete_cascade": True,
            "user": {
                "username": "someone_else",
                "email": "other@example.com",
            },
            "entities": [
                {
                    "import_op": "create",
                    "import_ref": "person_1",
                    "type": "Person",
                    "display": "Should Not Import",
                }
            ],
        }

        response = self._post_import(payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("does not match authenticated user", response.json().get("error", "").lower())

    def test_v2_accepts_export_metadata_fields(self):
        person = Person.objects.create(
            user=self.user,
            display="Roundtrip Before",
            first_name="Before",
        )

        payload = {
            "import_version": "2.0",
            "export_date": "2026-07-12T06:42:15.700163+00:00",
            "export_type": "selected",
            "user": {
                "username": self.user.username,
                "email": self.user.email,
            },
            "entities": [
                {
                    "id": str(person.id),
                    "type": "Person",
                    "display": "Roundtrip After",
                    "first_name": "After",
                }
            ],
        }

        response = self._post_import(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        person.refresh_from_db()
        self.assertEqual(person.display, "Roundtrip After")
        self.assertEqual(person.first_name, "After")

    def test_legacy_import_accepts_import_version_with_unified_entities(self):
        payload = {
            "import_version": "1.0",
            "user": {
                "username": self.user.username,
                "email": self.user.email,
            },
            "entities": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "type": "Person",
                    "display": "Legacy Unified Person",
                    "first_name": "Legacy",
                }
            ],
            "relations": [],
            "tags": [],
        }

        response = self._post_import(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Person.objects.filter(user=self.user, display="Legacy Unified Person").exists())
