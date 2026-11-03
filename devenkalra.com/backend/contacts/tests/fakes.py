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
        if method == "GET" and path.startswith("/list/") and path.count("/") == 2:
            # GET /list/{id}
            return Resp({"id": path.split("/")[2], "name": "People", "statuses": [{"status": "to do"}]})
        if method == "GET" and path.startswith("/list/") and path.endswith("/task"):
            return Resp({"tasks": list(self.tasks.values()), "last_page": True})
        if method == "GET" and "/attachment" in path:
            return Resp({"attachments": []})
        if method == "GET" and path.startswith("/task/"):
            tid = path.split("/")[2]
            t = self.tasks.get(tid)
            if not t:
                return Resp({"err": "not found"}, status=404)
            return Resp({
                **t,
                "list": {"id": "P1"},
                "status": t.get("status") if isinstance(t.get("status"), dict) else {"status": "to do"},
                "date_updated": str(t.get("date_updated") or "1"),
                "url": t.get("url") or f"https://app.clickup.com/t/{tid}",
                "archived": bool(t.get("archived")),
                "markdown_description": t.get("markdown_description") or t.get("description") or "",
            })
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
    """Minimal People API: list, getBatchGet, createContact, updateContact, search, groups."""

    def __init__(self, people, groups=(), others=()):
        self._people, self._groups = people, list(groups)
        self._all = {p["resourceName"]: p for p in [*people, *others]}
        self.updates = []
        self.creates = []
        self.batch_gets = []
        self.member_mods = []
        self._ids = itertools.count(1)

    def contactGroups(self):
        return self

    def members(self):
        return self

    def people(self):
        return self

    def connections(self):
        return self

    def list(self, **kw):
        if "resourceName" in kw:
            page = kw.get("pageSize") or 1000
            token = kw.get("pageToken")
            start = int(token) if token and str(token).isdigit() else 0
            chunk = self._people[start:start + page]
            nxt = str(start + page) if start + page < len(self._people) else None
            out = {"connections": chunk, "nextSyncToken": "tok-2"}
            if nxt:
                out["nextPageToken"] = nxt
            return _Exec(out)
        return _Exec({"contactGroups": self._groups})

    def create(self, body=None, **kw):
        name = body["contactGroup"]["name"]
        group = {"resourceName": f"contactGroups/{name.lower()}", "groupType": "USER_CONTACT_GROUP",
                 "name": f"contactGroups/{name.lower()}", "formattedName": name}
        self._groups.append(group)
        return _Exec(group)

    def get(self, resourceName, **kw):
        members = []
        for p in self._all.values():
            for m in p.get("memberships") or []:
                rn = (m.get("contactGroupMembership") or {}).get("contactGroupResourceName")
                if rn == resourceName:
                    members.append(p["resourceName"])
                    break
        return _Exec({"resourceName": resourceName, "memberResourceNames": members[: kw.get("maxMembers", 2000)]})

    def modify(self, resourceName=None, body=None, **kw):
        body = body or {}
        self.member_mods.append({"resourceName": resourceName, **body})
        for rid in body.get("resourceNamesToAdd") or []:
            person = self._all.get(rid)
            if not person:
                continue
            mems = list(person.get("memberships") or [])
            if not any((m.get("contactGroupMembership") or {}).get("contactGroupResourceName") == resourceName
                       for m in mems):
                mems.append({"contactGroupMembership": {"contactGroupResourceName": resourceName}})
                person["memberships"] = mems
        for rid in body.get("resourceNamesToRemove") or []:
            person = self._all.get(rid)
            if not person:
                continue
            person["memberships"] = [
                m for m in person.get("memberships") or []
                if (m.get("contactGroupMembership") or {}).get("contactGroupResourceName") != resourceName
            ]
        return _Exec({})

    def searchContacts(self, query="", readMask=None, pageSize=50, **kw):
        q = (query or "").lower()
        hits = []
        for p in self._people:
            blob = " ".join([
                ((p.get("names") or [{}])[0]).get("displayName") or "",
                " ".join(e.get("value") or "" for e in p.get("emailAddresses") or []),
            ]).lower()
            if q in blob:
                hits.append({"person": p})
        return _Exec({"results": hits[:pageSize]})

    def getBatchGet(self, resourceNames, **kw):
        self.batch_gets.append(list(resourceNames))
        return _Exec({"responses": [{"requestedResourceName": r, "person": self._all.get(r)} for r in resourceNames]})

    def createContact(self, body=None, personFields=None, **kw):
        body = body or {}
        self.creates.append(body)
        rid = f"people/new{next(self._ids)}"
        names = list(body.get("names") or [])
        if names and not names[0].get("displayName"):
            n = names[0]
            names = [{**n, "displayName": " ".join(filter(None, [n.get("givenName"), n.get("familyName")]))}]
        person = {
            "resourceName": rid, "etag": f"etag-{rid}",
            "names": names,
            "emailAddresses": list(body.get("emailAddresses") or []),
            "phoneNumbers": list(body.get("phoneNumbers") or []),
            "organizations": list(body.get("organizations") or []),
            "birthdays": list(body.get("birthdays") or []),
            "addresses": list(body.get("addresses") or []),
            "urls": list(body.get("urls") or []),
            "memberships": list(body.get("memberships") or []),
            "externalIds": [], "photos": [], "metadata": {},
        }
        self._all[rid] = person
        self._people.append(person)
        return _Exec(person)

    def updateContact(self, **kw):
        self.updates.append(kw)
        person = self._all.get(kw.get("resourceName"))
        if person and "body" in kw:
            person["etag"] = person.get("etag", "") + "-u"
            body = kw["body"]
            for key in ("externalIds", "emailAddresses", "phoneNumbers", "addresses", "names", "memberships"):
                if key in body:
                    person[key] = body[key]
        return _Exec(person or {})
