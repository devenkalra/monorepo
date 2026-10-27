import itertools
import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from contacts import runner
from contacts.engine import ClickUp, WriteGuard
from contacts.engine.clickup import TEXT_TYPES
from contacts.engine.errors import SafetyStop
from contacts.engine.relations import split
from contacts.engine.transfer import export_lists, import_lists
from contacts.models import ImportedTask, SyncRun

from .fakes import Resp


def field(fid, name, ftype, options=None):
    f = {"id": fid, "name": name, "type": ftype, "type_config": {}}
    if options:
        f["type_config"]["options"] = options
    return f


def people_fields(prefix):
    return [
        field(f"{prefix}-co", "Company", "short_text"),
        field(f"{prefix}-rel", "Contact Relationship", "drop_down",
              [{"id": f"{prefix}-work", "name": "Work", "orderindex": 0},
               {"id": f"{prefix}-pers", "name": "Personal", "orderindex": 1}]),
        field(f"{prefix}-grp", "Groups", "labels",
              [{"id": f"{prefix}-g1", "label": "Google"}, {"id": f"{prefix}-g2", "label": "Caltech"}]),
        field(f"{prefix}-intro", "Introduced by", "tasks"),
        field(f"{prefix}-seen", "Last synced", "short_text"),
    ]


class FakeWorkspace:
    """A requests.Session stand-in holding several ClickUp lists."""

    def __init__(self):
        self.headers = {}
        self.lists, self.where = {}, {}
        self.writes = []
        self._ids = itertools.count(1)

    def add_list(self, list_id, name, fields, statuses=("to do", "complete"), tasks=()):
        self.lists[list_id] = {"info": {"id": list_id, "name": name, "space": {"id": "S1"},
                                        "statuses": [{"status": s, "type": "open"} for s in statuses]},
                               "fields": fields, "tasks": {}}
        for t in tasks:
            self.put(list_id, t)

    def put(self, list_id, t):
        t.setdefault("status", {"status": "to do"})
        t.setdefault("archived", False)
        t.setdefault("custom_fields", [])
        self.lists[list_id]["tasks"][t["id"]] = t
        self.where[t["id"]] = list_id

    def field_type(self, task_id, fid):
        return next(f["type"] for f in self.lists[self.where[task_id]]["fields"] if f["id"] == fid)

    def request(self, method, url, timeout=None, params=None, json=None):
        path = url.split("/api/v2", 1)[1]
        parts = path.strip("/").split("/")
        if method != "GET":
            self.writes.append((method, path, json))
        if parts[0] == "list":
            lst = self.lists[parts[1]]
            if method == "GET" and len(parts) == 2:
                return Resp(lst["info"])
            if method == "GET" and parts[2] == "field":
                return Resp({"fields": lst["fields"]})
            if method == "GET" and parts[2] == "task":
                arch = (params or {}).get("archived") == "true"
                return Resp({"tasks": [t for t in lst["tasks"].values() if t["archived"] == arch], "last_page": True})
            if method == "POST" and parts[2] == "task":
                types = {f["id"]: f["type"] for f in lst["fields"]}
                if any(types[cf["id"]] in TEXT_TYPES and not isinstance(cf["value"], str)
                       for cf in json.get("custom_fields", [])):
                    return Resp({"err": "Value is not a valid string", "ECODE": "FIELD_018"}, status=400)
                tid = f"n{next(self._ids)}"
                self.put(parts[1], {"id": tid, "name": json["name"], "status": {"status": json.get("status", "to do")},
                                    "markdown_description": json.get("markdown_content", ""),
                                    "tags": [{"name": n} for n in json.get("tags", [])], "parent": json.get("parent"),
                                    "custom_fields": [dict(cf) for cf in json.get("custom_fields", [])]})
                return Resp({"id": tid})
        if parts[0] == "task":
            if parts[1] not in self.where:
                return Resp({"err": "Task not found", "ECODE": "ITEM_013"}, status=404)
            t = self.lists[self.where[parts[1]]]["tasks"][parts[1]]
            if method == "GET" and len(parts) == 2:
                return Resp(dict(t, list={"id": self.where[parts[1]]}))
            t["date_updated"] = str(int(t.get("date_updated") or 1000) + 1)
            if method == "PUT":
                if "markdown_content" in json:
                    t["markdown_description"] = json["markdown_content"]
                if "archived" in json:
                    t["archived"] = json["archived"]
                if "name" in json:
                    t["name"] = json["name"]
                if "status" in json:
                    t["status"] = {"status": json["status"]}
                return Resp({})
            if method == "DELETE" and parts[2] == "field":
                t["custom_fields"] = [cf for cf in t["custom_fields"] if cf["id"] != parts[3]]
                return Resp({})
            if method == "POST" and parts[2] == "field":
                value = json["value"]
                if self.field_type(parts[1], parts[3]) == "tasks":
                    value = [{"id": i} for i in value["add"]]
                t["custom_fields"] = [cf for cf in t["custom_fields"] if cf["id"] != parts[3]] + \
                    [{"id": parts[3], "value": value}]
                return Resp({})
        return Resp({"err": "unexpected"}, status=404)


def cf(fid, value, name="", ftype=""):
    return {"id": fid, "name": name, "type": ftype, "value": value}


def source_workspace():
    ws = FakeWorkspace()
    ws.add_list("P1", "People", people_fields("p"), tasks=[
        {"id": "hakan", "name": "Hakan Ancin",
         "markdown_description": "Met at a conference.\n\n**Relationships**\n*   Spouse of\n"
                                 "    *   [Reeta Sharma](https://app.clickup.com/t/reeta)\n\n**Organizations**\n"
                                 "*   Works at [Google](https://app.clickup.com/t/google) — Staff SWE",
         "custom_fields": [cf("p-co", "Google", "Company", "short_text"),
                           cf("p-rel", 0, "Contact Relationship", "drop_down"),
                           cf("p-grp", ["p-g1", "p-g2"], "Groups", "labels"),
                           cf("p-seen", "1793080979822", "Last synced", "short_text")]},
        {"id": "reeta", "name": "Reeta Sharma",
         "markdown_description": "**Relationships**\n*   Spouse of\n    *   [Hakan Ancin](https://app.clickup.com/t/hakan)",
         "custom_fields": [cf("p-intro", [{"id": "hakan", "name": "Hakan Ancin"}], "Introduced by", "tasks")]},
        {"id": "old", "name": "Merged Person", "archived": True, "markdown_description": "plain notes"},
    ])
    ws.add_list("O1", "Orgs", [field("o-show", "Show After", "date")], statuses=("new organization", "engaged"), tasks=[
        {"id": "google", "name": "Google", "status": {"status": "engaged"},
         "markdown_description": "**People**\n*   Employs\n    *   [Hakan Ancin](https://app.clickup.com/t/hakan) — Staff SWE",
         "custom_fields": [cf("o-show", "1700000000000", "Show After", "date")]},
    ])
    return ws


def lists_on(ws, guard, **ids):
    return {k: ClickUp("tok", v, guard, session=ws) for k, v in ids.items()}


def export(ws):
    data, _ = export_lists(lists_on(ws, WriteGuard(dry=True), people="P1", orgs="O1"))
    return json.loads(json.dumps(data))


def with_targets(ws):
    ws.add_list("P2", "PeopleCopy", people_fields("q"))
    ws.add_list("O2", "OrgsCopy", [field("q-show", "Show After", "date")], statuses=("new organization", "engaged"))
    return ws


class ExportTests(SimpleTestCase):
    def test_export_reads_both_lists_including_archived_tasks(self):
        ws = source_workspace()
        data = export(ws)
        self.assertEqual(ws.writes, [])
        self.assertEqual({t["id"] for t in data["lists"]["people"]["tasks"]}, {"hakan", "reeta", "old"})
        self.assertEqual([t["name"] for t in data["lists"]["orgs"]["tasks"]], ["Google"])
        self.assertTrue(next(t for t in data["lists"]["people"]["tasks"] if t["id"] == "old")["archived"])

    def test_export_lists_every_relationship(self):
        rels = {(r["from_id"], r["label"], r["to_id"], r["to_list"]) for r in export(source_workspace())["relationships"]}
        self.assertEqual(rels, {
            ("hakan", "Spouse of", "reeta", "people"), ("hakan", "Works at", "google", "orgs"),
            ("reeta", "Spouse of", "hakan", "people"), ("reeta", "Introduced by", "hakan", "people"),
            ("google", "Employs", "hakan", "people"),
        })

    def test_section_parser_keeps_notes(self):
        md = "**Organizations**\n- Works at [Google](https://app.clickup.com/t/g1) — VP Eng, 2015-2019"
        self.assertEqual(split(md)[1][0]["note"], "VP Eng, 2015-2019")


class ImportTests(SimpleTestCase):
    def run_import(self, ws, data, *, dry=False, id_map=None, on_mapped=None):
        guard = WriteGuard(dry=dry, writes_enabled=not dry, max_ops=None if dry else 500)
        return import_lists(data, lists_on(ws, guard, people="P2", orgs="O2"), id_map=id_map,
                            on_mapped=on_mapped), guard

    def test_dry_run_writes_nothing(self):
        ws = with_targets(source_workspace())
        (log, _), guard = self.run_import(ws, export(ws), dry=True)
        self.assertEqual(ws.writes, [])
        self.assertEqual(log.stats["CREATE"], 4)
        self.assertGreater(guard.ops, 4)

    def test_import_recreates_tasks_and_rewires_links(self):
        ws = with_targets(source_workspace())
        data = export(ws)
        (log, id_map), _ = self.run_import(ws, data)
        self.assertEqual(log.stats["ERROR"], 0, log.actions)
        people, orgs = ws.lists["P2"]["tasks"], ws.lists["O2"]["tasks"]
        hakan, reeta, google = people[id_map["hakan"]], people[id_map["reeta"]], orgs[id_map["google"]]

        self.assertIn(f"https://app.clickup.com/t/{id_map['reeta']}", hakan["markdown_description"])
        self.assertIn(f"https://app.clickup.com/t/{id_map['google']}", hakan["markdown_description"])
        self.assertNotIn("/t/reeta)", hakan["markdown_description"])
        self.assertTrue(hakan["markdown_description"].startswith("Met at a conference."))
        self.assertIn(f"/t/{id_map['hakan']}", google["markdown_description"])

        values = {c["id"]: c["value"] for c in hakan["custom_fields"]}
        self.assertEqual(values["q-co"], "Google")
        self.assertEqual(values["q-rel"], "q-work")
        self.assertEqual(values["q-grp"], ["q-g1", "q-g2"])
        self.assertEqual(values["q-seen"], "1793080979822")
        intro = {c["id"]: c["value"] for c in reeta["custom_fields"]}["q-intro"]
        self.assertEqual(intro, [{"id": id_map["hakan"]}])
        self.assertEqual(google["status"]["status"], "engaged")
        self.assertTrue(people[id_map["old"]]["archived"])

    def test_refuses_a_target_list_that_has_tasks(self):
        ws = with_targets(source_workspace())
        ws.put("P2", {"id": "someone", "name": "Someone"})
        with self.assertRaises(SafetyStop):
            self.run_import(ws, export(ws))
        self.assertEqual(ws.writes, [])

    def test_refuses_importing_into_the_source_list(self):
        ws = source_workspace()
        with self.assertRaises(SafetyStop):
            import_lists(export(ws), lists_on(ws, WriteGuard(dry=True), people="P1", orgs="O1"))

    def test_resumes_without_recreating_tasks(self):
        ws = with_targets(source_workspace())
        data = export(ws)
        ws.put("P2", {"id": "n99", "name": "Hakan Ancin"})
        (log, id_map), _ = self.run_import(ws, data, id_map={"hakan": "n99"})
        self.assertEqual(log.stats["SKIP"], 1)
        self.assertEqual(log.stats["CREATE"], 3)
        self.assertEqual(id_map["hakan"], "n99")
        self.assertEqual(len(ws.lists["P2"]["tasks"]), 3)

    def test_reports_fields_the_target_list_lacks(self):
        ws = source_workspace()
        ws.add_list("P2", "PeopleCopy", people_fields("q")[:1])
        ws.add_list("O2", "OrgsCopy", [])
        (log, _), _ = self.run_import(ws, export(ws), dry=True)
        self.assertTrue(any("'Groups' won't be imported" in w for w in log.warnings))
        self.assertTrue(any("'Show After' won't be imported" in w for w in log.warnings))


class TransferApiTests(TestCase):
    def setUp(self):
        self.data_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.data_dir, ignore_errors=True)
        ctx = override_settings(CONTACTS_DATA_DIR=self.data_dir, CONTACTS_CLICKUP_TOKEN='tok',
                                CONTACTS_CLICKUP_LIST_ID='111111', CONTACTS_CLICKUP_ORGS_LIST_ID='222222',
                                CONTACTS_CLICKUP_WRITES_ENABLED=True)
        ctx.enable()
        self.addCleanup(ctx.disable)
        admin = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=admin).key}')
        ws = source_workspace()
        ws.lists['111111'] = ws.lists.pop('P1')
        ws.lists['222222'] = ws.lists.pop('O1')
        ws.where = {tid: {'P1': '111111', 'O1': '222222'}[lid] for tid, lid in ws.where.items()}
        ws.add_list('333333', 'PeopleCopy', people_fields('q'))
        ws.add_list('444444', 'OrgsCopy', [field('q-show', 'Show After', 'date')],
                    statuses=('new organization', 'engaged'))
        self.ws = ws
        patcher = mock.patch.object(runner, 'ClickUp', lambda token, list_id, guard: ClickUp(token, list_id, guard,
                                                                                              session=ws))
        patcher.start()
        self.addCleanup(patcher.stop)

    def start(self, body):
        r = self.client.post('/api/contacts/runs/', body, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        run = runner.execute_run(runner.claim(r.json()['id']))
        self.assertEqual(run.status, SyncRun.Status.DONE, run.error)
        return run

    def export_file(self):
        run = self.start({'source': 'export'})
        r = self.client.get(f'/api/contacts/runs/{run.pk}/download/')
        self.assertEqual(r.status_code, 200)
        data = json.loads(b''.join(r.streaming_content))
        self.assertEqual(len(data['lists']['people']['tasks']), 3)
        return run.output

    def test_export_then_import_through_the_api(self):
        f = self.export_file()
        plan = self.start({'source': 'import', 'files': {'export': f.id},
                           'options': {'people_list_id': '333333', 'orgs_list_id': '444444'}})
        self.assertEqual(plan.stats.get('CREATE'), 4)
        writes_before = len(self.ws.writes)
        r = self.client.post(f'/api/contacts/runs/{plan.pk}/apply/')
        self.assertEqual(r.status_code, 201, r.content)
        live = runner.execute_run(runner.claim(r.json()['id']))
        self.assertEqual(live.status, SyncRun.Status.DONE, live.error)
        self.assertEqual(live.ops, plan.ops)
        self.assertEqual(len(self.ws.writes) - writes_before, plan.ops)
        self.assertEqual(ImportedTask.objects.count(), 4)
        self.assertEqual(len(self.ws.lists['333333']['tasks']), 3)

    def test_import_refuses_the_live_lists(self):
        f = self.export_file()
        r = self.client.post('/api/contacts/runs/', {'source': 'import', 'files': {'export': f.id},
                                                     'options': {'people_list_id': '111111',
                                                                 'orgs_list_id': '444444'}}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('lists Contact Sync uses', r.json()['detail'])

    def test_exports_cannot_be_applied(self):
        f = self.export_file()
        run = SyncRun.objects.get(output=f)
        self.assertEqual(self.client.post(f'/api/contacts/runs/{run.pk}/apply/').status_code, 409)

    def test_upload_rejects_a_file_that_isnt_an_export(self):
        r = self.client.post('/api/contacts/uploads/', {
            'kind': 'contacts_export', 'file': SimpleUploadedFile('x.json', b'{"a": 1}')}, format='multipart')
        self.assertEqual(r.status_code, 400)
