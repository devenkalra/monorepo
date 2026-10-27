"""ClickUp API client for the Contacts list. All writes go through the WriteGuard."""
import time
from datetime import datetime

import requests

from .fields import FIELDS, REQUIRED, SOURCE_LABEL, STATUS_OPTIONS, task_url
from .guard import ALLOWED_TASK_KEYS, check_field_changes

# ClickUp rejects numbers in these ("Value is not a valid string", FIELD_018).
TEXT_TYPES = ("short_text", "text", "url", "email", "phone")


class ClickUp:
    BASE = "https://api.clickup.com/api/v2"

    def __init__(self, token, list_id, guard, session=None):
        self.list_id = str(list_id)
        self.guard = guard
        self.s = session or requests.Session()
        self.s.headers.update({"Authorization": token, "Content-Type": "application/json"})
        self.fields = {}
        self.all_fields = []
        self._dry_n = 0

    @property
    def dry(self):
        return self.guard.dry

    def _req(self, method, path, retry_5xx=True, **kw):
        if method != "GET":
            self.guard.assert_live(f"{method} {path}")
        for attempt in range(7):
            r = self.s.request(method, self.BASE + path, timeout=30, **kw)
            if r.status_code == 429:
                reset = r.headers.get("X-RateLimit-Reset")
                wait = float(reset) - time.time() if reset else 2 ** attempt
                time.sleep(min(max(wait, 1), 65))
                continue
            if r.status_code >= 500 and retry_5xx:
                time.sleep(2 ** attempt)
                continue
            if not r.ok:
                raise RuntimeError(f"ClickUp {method} {path} -> {r.status_code}: {r.text[:300]}")
            return r.json() if r.text else {}
        raise RuntimeError(f"ClickUp {method} {path}: retries exhausted")

    # ---- reads -----------------------------------------------------------------------
    def load_fields(self):
        self.all_fields = self._req("GET", f"/list/{self.list_id}/field").get("fields", [])
        by_name = {f["name"].strip().lower(): f for f in self.all_fields}
        missing = []
        for key, name in FIELDS.items():
            f = by_name.get(name.lower())
            if f:
                self.fields[key] = f
            elif key in REQUIRED:
                missing.append(name)
        return missing

    def label_options(self, key):
        f = self.fields.get(key) or {}
        return {(o.get("label") or o.get("name") or "").strip().lower(): o
                for o in f.get("type_config", {}).get("options", [])}

    def all_tasks(self, progress=None):
        tasks, page = [], 0
        while True:
            d = self._req("GET", f"/list/{self.list_id}/task",
                          params={"page": page, "include_closed": "true", "subtasks": "true"})
            batch = d.get("tasks", [])
            tasks += batch
            if progress:
                progress(len(tasks))
            if d.get("last_page") or len(batch) < 100:
                return tasks
            page += 1

    def attachment_names(self, task_id):
        t = self._req("GET", f"/task/{task_id}")
        return {a.get("title") or "" for a in t.get("attachments", [])}

    # ---- value conversion ------------------------------------------------------------
    def prep(self, key, raw):
        """Convert a raw source value to what we store, given the field's type (None = skip)."""
        f = self.fields.get(key)
        if not f or raw in (None, ""):
            return None
        is_date = f["type"] == "date"
        if key == "birthday":
            y, m, d = raw
            if is_date:
                if not y or y < 1970:
                    return None  # ClickUp Date fields need a full date after 1970
                return int(datetime(y, m, d, 12).timestamp() * 1000)
            return f"{m:02d}-{d:02d}" + (f" ({y})" if y else "")
        if key == "connected_on":
            try:
                dt = datetime.strptime(raw.strip(), "%d %b %Y")
            except ValueError:
                return None
            return int(dt.replace(hour=12).timestamp() * 1000) if is_date else dt.strftime("%Y-%m-%d")
        return raw

    def encode(self, key, value):
        f = self.fields[key]
        if key in ("groups", "sources"):
            opts = self.label_options(key)
            return [opts[g.lower()]["id"] for g in value if g.lower() in opts]
        if f["type"] == "drop_down":
            for o in f.get("type_config", {}).get("options", []):
                if o["name"].strip().lower() == str(value).lower():
                    return o["id"]
            raise ValueError(f"Option {value!r} missing from dropdown '{f['name']}'")
        if f["type"] == "labels":
            for o in f.get("type_config", {}).get("options", []):
                if (o.get("label") or o.get("name") or "").strip().lower() == str(value).lower():
                    return [o["id"]]
            raise ValueError(f"Label {value!r} missing from labels field '{f['name']}'")
        if f["type"] in ("tasks", "list_relationship"):
            tid = str(value).rstrip("/").split("/")[-1]
            return {"add": [tid], "rem": []}
        if f["type"] == "date":
            return int(value)
        if f["type"] in TEXT_TYPES:
            return str(value)
        return value

    def decode(self, task, key):
        f = self.fields.get(key)
        if not f:
            return None
        for cf in task.get("custom_fields", []):
            if cf["id"] != f["id"]:
                continue
            v = cf.get("value")
            if v in (None, ""):
                return None
            if key in ("groups", "sources"):
                ids = v if isinstance(v, list) else [v]
                return [(o.get("label") or o.get("name") or "").strip()
                        for o in f.get("type_config", {}).get("options", []) if o["id"] in ids]
            if f["type"] == "drop_down":
                for o in f.get("type_config", {}).get("options", []):
                    if str(v) in (str(o.get("orderindex")), o["id"]):
                        return o["name"].strip().lower()
                return None
            if f["type"] == "labels":
                ids = v if isinstance(v, list) else [v]
                for o in f.get("type_config", {}).get("options", []):
                    if o["id"] in ids:
                        return (o.get("label") or o.get("name") or "").strip().lower()
                return None
            if f["type"] in ("tasks", "list_relationship"):
                items = v if isinstance(v, list) else [v]
                return task_url(items[0]["id"]) if items and isinstance(items[0], dict) else None
            return v
        return None

    # ---- guarded writes --------------------------------------------------------------
    def create(self, name, values):
        values = {k: v for k, v in values.items() if k in self.fields and v not in (None, "", [])}
        handle = self.guard.begin("create", task_id="(new)", task_name=name, after=values)
        if handle is None:
            self._dry_n += 1
            return {"id": f"dry-run-{self._dry_n}"}
        cfs = [{"id": self.fields[k]["id"], "value": self.encode(k, v)} for k, v in values.items()]
        try:
            # No retry on 5xx: the task may have been created, and a retry would duplicate it.
            task = self._req("POST", f"/list/{self.list_id}/task", retry_5xx=False,
                             json={"name": name, "custom_fields": cfs})
        except Exception as e:
            self.guard.done(handle, error=str(e))
            raise
        self.guard.done(handle)
        return task

    def set_fields(self, task_id, changes, *, before, task_name="", allow_clear=()):
        """Write field changes. `before` is the record's current values (from the index)."""
        check_field_changes(before, changes, allow_clear)
        for k, v in changes.items():
            if k not in self.fields:
                continue
            clear = v in (None, "", [])
            if clear and self.fields[k]["type"] in ("tasks", "list_relationship"):
                continue
            if before.get(k) == v:
                continue
            handle = self.guard.begin("clear" if clear else "set", task_id=task_id, task_name=task_name,
                                      field=FIELDS[k], before=before.get(k), after=None if clear else v)
            if handle is None:
                continue
            fid = self.fields[k]["id"]
            try:
                if clear:
                    self._req("DELETE", f"/task/{task_id}/field/{fid}")
                else:
                    self._req("POST", f"/task/{task_id}/field/{fid}", json={"value": self.encode(k, v)})
            except Exception as e:
                self.guard.done(handle, error=str(e))
                raise
            self.guard.done(handle)

    def update_task(self, task_id, *, task_name="", before=None, **body):
        bad = set(body) - ALLOWED_TASK_KEYS
        if bad:
            raise ValueError(f"update_task only changes {sorted(ALLOWED_TASK_KEYS)}, not {sorted(bad)}")
        op = "rename" if "name" in body else "archive"
        handle = self.guard.begin(op, task_id=task_id, task_name=task_name, before=before, after=body)
        if handle is None:
            return
        try:
            self._req("PUT", f"/task/{task_id}", json=body)
        except Exception as e:
            self.guard.done(handle, error=str(e))
            raise
        self.guard.done(handle)

    def upload(self, task_id, filename, data, mime, *, task_name=""):
        handle = self.guard.begin("attach", task_id=task_id, task_name=task_name, after=filename)
        if handle is None:
            return None
        self.guard.assert_live(f"upload {filename}")
        try:
            for attempt in range(7):
                r = requests.post(f"{self.BASE}/task/{task_id}/attachment",
                                  headers={"Authorization": self.s.headers["Authorization"]},
                                  files={"attachment": (filename, data, mime)}, timeout=60)
                if r.status_code == 429:
                    time.sleep(min(2 ** attempt, 60))
                    continue
                if not r.ok:
                    raise RuntimeError(f"ClickUp upload -> {r.status_code}: {r.text[:300]}")
                self.guard.done(handle)
                return r.json()
            raise RuntimeError("ClickUp upload: retries exhausted")
        except Exception as e:
            self.guard.done(handle, error=str(e))
            raise

    # ---- list health -----------------------------------------------------------------
    def field_report(self, missing):
        expected = [{"key": k, "name": n, "present": k in self.fields, "required": k in REQUIRED,
                     "type": (self.fields.get(k) or {}).get("type")} for k, n in FIELDS.items()]
        status_missing = []
        st = self.fields.get("status")
        if st and st["type"] in ("drop_down", "labels"):
            have = {(o.get("name") or o.get("label") or "").strip().lower()
                    for o in st.get("type_config", {}).get("options", [])}
            status_missing = [o for o in STATUS_OPTIONS if o not in have]
        sources_missing = []
        if "sources" in self.fields:
            opts = self.label_options("sources")
            sources_missing = [x for x in SOURCE_LABEL.values() if x.lower() not in opts]
        return {
            "list_id": self.list_id,
            "fields": [{"name": f["name"], "type": f["type"]} for f in self.all_fields],
            "expected": expected,
            "missing_required": missing,
            "status_missing_options": status_missing,
            "sources_missing_options": sources_missing,
            "ready": not missing and not status_missing,
        }
