"""In-memory stand-ins for the ClickUp HTTP API and the Google People API."""
import itertools

from contacts.engine.clickup import TEXT_TYPES
from contacts.engine.fields import FIELDS, STATUS_OPTIONS

TYPES = {"status": "drop_down", "groups": "labels", "sources": "labels", "connected_on": "date",
         "last_li_msg": "date", "google_link": "url",
         "website": "url", "linkedin_url": "url", "email": "email"}


def make_fields(groups=("Family", "Work")):
    fields = []
    for key, name in FIELDS.items():
        f = {"id": f"f-{key}", "name": name, "type": TYPES.get(key, "short_text"), "type_config": {}}
        if key == "status":
            f["type_config"]["options"] = [{"id": f"st-{i}", "name": o, "orderindex": i}
                                           for i, o in enumerate(STATUS_OPTIONS)]
        if key == "sources":
            f["type_config"]["options"] = [{"id": f"src-{s}", "label": s} for s in ("Google", "LinkedIn", "WhatsApp")]
        if key == "groups":
            f["type_config"]["options"] = [{"id": f"grp-{g}", "label": g} for g in groups]
        fields.append(f)
    return fields


def make_task(tid, name, **values):
    """values: internal key -> raw ClickUp value (labels as option ids, dropdown as option id)."""
    return {"id": tid, "name": name, "archived": False,
            "custom_fields": [{"id": f"f-{k}", "value": v} for k, v in values.items()]}


class Resp:
    def __init__(self, data=None, status=200):
        self._data = data if data is not None else {}
        self.status_code = status
        self.ok = status < 400
        self.text = "x"
        self.headers = {}

    def json(self):
        return self._data


class FakeClickUp:
    """A requests.Session replacement. `writes` lists every non-GET call."""

    def __init__(self, tasks=(), fields=None):
        self.headers = {}
        self.fields = fields or make_fields()
        self.tasks = {t["id"]: t for t in tasks}
        self.calls, self.writes = [], []
        self._ids = itertools.count(1)

    def _bad_text(self, fid, value):
        f = next((f for f in self.fields if f["id"] == fid), None)
        return f and f["type"] in TEXT_TYPES and not isinstance(value, str)

    def request(self, method, url, timeout=None, params=None, json=None):
        path = url.split("/api/v2", 1)[1]
        self.calls.append((method, path, json))
        if method != "GET":
            self.writes.append((method, path, json))
        values = ([(path.split("/")[4], json["value"])] if method == "POST" and "/field/" in path else
                  [(cf["id"], cf["value"]) for cf in (json or {}).get("custom_fields", [])])
        if any(self._bad_text(fid, v) for fid, v in values):
            return Resp({"err": "Value is not a valid string", "ECODE": "FIELD_018"}, status=400)
        if method == "GET" and path.endswith("/field"):
            return Resp({"fields": self.fields})
        if method == "GET" and path.startswith("/list/") and path.endswith("/task"):
            return Resp({"tasks": list(self.tasks.values()), "last_page": True})
        if method == "GET" and path.startswith("/task/"):
            return Resp({"attachments": []})
        if method == "POST" and path.startswith("/list/"):
            tid = f"new{next(self._ids)}"
            self.tasks[tid] = {"id": tid, "name": json["name"], "custom_fields": json["custom_fields"]}
            return Resp({"id": tid})
        if path.startswith("/task/") and "/field/" in path:
            tid, fid = path.split("/")[2], path.split("/")[4]
            cfs = [cf for cf in self.tasks[tid]["custom_fields"] if cf["id"] != fid]
            if method == "POST":
                cfs.append({"id": fid, "value": json["value"]})
            self.tasks[tid]["custom_fields"] = cfs
            return Resp({})
        if method == "PUT" and path.startswith("/task/"):
            self.tasks[path.split("/")[2]].update(json)
            return Resp({})
        return Resp({"err": "unexpected"}, status=404)


class _Exec:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class FakePeople:
    """Minimal People API: contactGroups().list(), people().connections().list() and people().getBatchGet()."""

    def __init__(self, people, groups=(), others=()):
        self._people, self._groups = people, list(groups)
        self._all = {p["resourceName"]: p for p in [*people, *others]}
        self.updates = []
        self.batch_gets = []

    def contactGroups(self):
        return self

    def people(self):
        return self

    def connections(self):
        return self

    def list(self, **kw):
        if "resourceName" in kw:
            return _Exec({"connections": self._people, "nextSyncToken": "tok-2"})
        return _Exec({"contactGroups": self._groups})

    def getBatchGet(self, resourceNames, **kw):
        self.batch_gets.append(list(resourceNames))
        return _Exec({"responses": [{"requestedResourceName": r, "person": self._all.get(r)} for r in resourceNames]})

    def updateContact(self, **kw):
        self.updates.append(kw)
        return _Exec({})
