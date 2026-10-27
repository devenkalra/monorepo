"""Export the People and Orgs lists to one JSON file, and import such a file into empty lists.

The export keeps each task's name, status, tags, priority, dates, description and custom field values,
plus the links between tasks: the managed description sections (**Relationships**, **Organizations**,
**People**) and task-link custom fields such as "Introduced by". Import creates the tasks in other lists
and rewrites those links to the new task IDs.

Import only writes into lists that are empty, or that hold only tasks it created itself on an earlier,
interrupted attempt, so it can never change a list that's in use.
"""
import re
from collections import Counter
from datetime import datetime, timezone

from .clickup import TEXT_TYPES
from .errors import ConfigError, SafetyStop, TooManyErrors
from .fields import task_url
from .relations import split
from .sync import Reporter

FORMAT, VERSION = "clickup-contacts-export", 1
LISTS = {"people": "People", "orgs": "Orgs"}

TASK_URL_RE = re.compile(r"https://app\.clickup\.com/t/(?:\d+/)?([A-Za-z0-9_-]+)")

LINK_TYPES = ("tasks", "list_relationship")
NUMBER_TYPES = ("number", "currency", "emoji", "rating")
VALUE_TYPES = TEXT_TYPES + NUMBER_TYPES + ("date", "checkbox", "drop_down", "labels")
PRIORITY = {"urgent": 1, "high": 2, "normal": 3, "low": 4}
MAX_ERRORS = 25


class TransferLog:
    """Collects actions for one export/import, in the shape the runner stores for sync runs."""

    def __init__(self, reporter=None, dry=True):
        self.reporter = reporter or Reporter()
        self.dry = dry
        self.stats, self.actions, self.warnings = Counter(), [], []
        self.unknown_groups, self.unknown_sources = Counter(), set()

    def log(self, action, name, detail="", task_id=None):
        entry = {"action": action, "name": name, "detail": detail}
        if task_id and not str(task_id).startswith("dry-run"):
            entry["task_id"] = str(task_id)
        self.stats[action] += 1
        self.actions.append(entry)
        self.reporter.action(entry)

    def warn(self, message):
        self.warnings.append(message)
        self.log("WARN", "", message)

    def error(self, name, exc):
        if isinstance(exc, SafetyStop):
            raise exc
        self.log("ERROR", name, str(exc)[:300])
        if not self.dry and self.stats["ERROR"] > MAX_ERRORS:
            raise TooManyErrors(f"Stopped after {self.stats['ERROR']} errors.")

    def tick(self, phase, done=0, total=0):
        self.reporter.progress(phase, done, total)
        self.reporter.check_cancel()


# ---- reading ----------------------------------------------------------------------------
def read_list(cu, log, label):
    info = cu._req("GET", f"/list/{cu.list_id}")
    fields = cu._req("GET", f"/list/{cu.list_id}/field").get("fields", [])
    tasks, seen = [], set()
    for archived in ("false", "true"):
        page = 0
        while True:
            d = cu._req("GET", f"/list/{cu.list_id}/task", params={
                "page": page, "archived": archived, "include_closed": "true", "subtasks": "true",
                "include_markdown_description": "true"})
            batch = d.get("tasks", [])
            tasks += [t for t in batch if t["id"] not in seen]
            seen.update(t["id"] for t in batch)
            log.tick(f"Reading {label}", len(tasks), 0)
            if d.get("last_page") or len(batch) < 100:
                break
            page += 1
    return info, fields, tasks


def task_record(t):
    values = [{"field_id": cf["id"], "name": cf.get("name", ""), "type": cf.get("type", ""), "value": cf["value"]}
              for cf in t.get("custom_fields", []) if cf.get("value") not in (None, "", [])]
    return {
        "id": t["id"],
        "name": t.get("name") or "",
        "status": (t.get("status") or {}).get("status"),
        "tags": [g["name"] for g in t.get("tags", []) if g.get("name")],
        "priority": ((t.get("priority") or {}).get("priority") or None),
        "due_date": t.get("due_date"),
        "start_date": t.get("start_date"),
        "parent": t.get("parent"),
        "archived": bool(t.get("archived")),
        "date_created": t.get("date_created"),
        "date_updated": t.get("date_updated"),
        "url": t.get("url") or task_url(t["id"]),
        "description": t.get("markdown_description") or t.get("description") or "",
        "custom_fields": values,
    }


def relationships(lists):
    where = {t["id"]: (key, t["name"]) for key, lst in lists.items() for t in lst["tasks"]}
    out = []
    for key, lst in lists.items():
        for t in lst["tasks"]:
            links = [(f"section:{ln['section']}", ln["label"], ln["target_id"], ln["name"], ln["note"])
                     for ln in split(t["description"])[1] if ln["target_id"]]
            for cf in t["custom_fields"]:
                if cf["type"] in LINK_TYPES:
                    links += [(f"field:{cf['name']}", cf["name"], item["id"], item.get("name", ""), "")
                              for item in cf["value"] if isinstance(item, dict) and item.get("id")]
            for via, label, to, name, note in links:
                to_list, to_name = where.get(to, (None, name))
                out.append({"from_id": t["id"], "from_name": t["name"], "from_list": key, "via": via,
                            "label": label, "to_id": to, "to_name": to_name, "to_list": to_list, "note": note})
    return out


def export_lists(sources, reporter=None):
    """sources: {"people": ClickUp, "orgs": ClickUp}. Read-only. Returns (data, log)."""
    log = TransferLog(reporter)
    data = {"format": FORMAT, "version": VERSION, "exported_at": datetime.now(timezone.utc).isoformat(), "lists": {}}
    for key, cu in sources.items():
        info, fields, tasks = read_list(cu, log, LISTS[key])
        data["lists"][key] = {
            "id": str(cu.list_id), "name": info.get("name", ""), "space_id": (info.get("space") or {}).get("id"),
            "statuses": [{k: s.get(k) for k in ("status", "type", "color", "orderindex")}
                         for s in info.get("statuses", [])],
            "fields": fields,
            "tasks": [task_record(t) for t in tasks],
        }
        archived = sum(t["archived"] for t in data["lists"][key]["tasks"])
        log.log("EXPORT", info.get("name") or LISTS[key],
                f"{len(tasks)} tasks ({archived} archived), {len(fields)} custom fields")
    data["relationships"] = relationships(data["lists"])
    for r in data["relationships"]:
        log.log("RELATION", r["from_name"], f"{r['label']} → {r['to_name'] or r['to_id']}"
                + ("" if r["to_list"] else " (outside the export)"), task_id=r["from_id"])
    return data, log


def check_export(data):
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ConfigError("This isn't a contacts export file.")
    if data.get("version") != VERSION:
        raise ConfigError(f"Unsupported export version {data.get('version')!r}.")
    if not isinstance(data.get("lists"), dict) or not set(data["lists"]) <= set(LISTS) or not data["lists"]:
        raise ConfigError("The export has no People or Orgs list.")
    return sum(len(lst.get("tasks", [])) for lst in data["lists"].values())


# ---- importing --------------------------------------------------------------------------
def _send(cu, op, method, path, body, *, task_id, task_name, field="", after=None, retry_5xx=True):
    handle = cu.guard.begin(op, task_id=task_id, task_name=task_name, field=field, after=after)
    if handle is None:
        return None
    try:
        resp = cu._req(method, path, retry_5xx=retry_5xx, json=body)
    except Exception as e:
        cu.guard.done(handle, error=str(e))
        raise
    cu.guard.done(handle)
    return resp


def _options(field):
    """Option keys as a task stores them (id, and orderindex for dropdowns) -> lowercase option name."""
    out = {}
    for o in field.get("type_config", {}).get("options", []):
        name = (o.get("name") or o.get("label") or "").strip().lower()
        out[o["id"]] = name
        if o.get("orderindex") is not None:
            out[str(o["orderindex"])] = name
    return out


def _compatible(a, b):
    return a == b or (a in TEXT_TYPES and b in TEXT_TYPES)


class _Target:
    """What we know about one target list: its field mapping, statuses and the tasks already there."""

    def __init__(self, key, cu, src, log):
        self.key, self.cu, self.src = key, cu, src
        info, fields, tasks = read_list(cu, log, f"target {LISTS[key]} list")
        self.name = info.get("name") or cu.list_id
        self.task_ids = {t["id"] for t in tasks}
        self.statuses = {s["status"].lower(): s["status"] for s in info.get("statuses", [])}
        by_name = {}
        for f in fields:
            by_name.setdefault(f["name"].strip().lower(), []).append(f)
        self.fields, self.dropped = {}, {}
        used = Counter(cf["field_id"] for t in src["tasks"] for cf in t["custom_fields"])
        for f in src["fields"]:
            if not used[f["id"]]:
                continue
            match = next((g for g in by_name.get(f["name"].strip().lower(), []) if _compatible(f["type"], g["type"])),
                         None)
            if f["type"] not in VALUE_TYPES + LINK_TYPES:
                self.dropped[f["name"]] = f"its type ({f['type']}) isn't imported"
            elif not match:
                self.dropped[f["name"]] = "the target list has no field with that name and type"
            else:
                tgt_opts = {v: k for k, v in _options(match).items() if not k.isdigit()}
                src_opts = _options(f)
                self.fields[f["id"]] = (f, match, {k: tgt_opts[v] for k, v in src_opts.items() if v in tgt_opts},
                                        sorted({v for v in src_opts.values() if v not in tgt_opts}))
        self.used = used

    def encode(self, cf):
        """Source value -> value to send, or None to skip (link fields are set after all tasks exist)."""
        m = self.fields.get(cf["field_id"])
        if not m:
            return None
        src, tgt, opts, _ = m
        v, t = cf["value"], tgt["type"]
        if t in LINK_TYPES:
            return None
        if t in TEXT_TYPES:
            return str(v)
        if t in NUMBER_TYPES:
            n = float(v)
            return int(n) if n.is_integer() else n
        if t == "date":
            return int(float(v))
        if t == "checkbox":
            return v in (True, "true", 1, "1")
        if t == "drop_down":
            return opts.get(str(v))
        if t == "labels":
            ids = [opts[x] for x in (v if isinstance(v, list) else [v]) if x in opts]
            return ids or None
        return None


def _rewrite(md, id_map):
    """Point task links at the imported copies. Returns (text, links rewritten, links left alone)."""
    hits = Counter()

    def sub(m):
        new = id_map.get(m.group(1))
        hits["mapped" if new else "outside"] += 1
        return task_url(new) if new else m.group(0)

    return TASK_URL_RE.sub(sub, md or ""), hits["mapped"], hits["outside"]


def import_lists(data, targets, *, reporter=None, id_map=None, on_mapped=None):
    """Create the exported tasks in `targets` ({"people": ClickUp, "orgs": ClickUp}, one shared guard).

    `id_map` (exported id -> created id) holds tasks created by an earlier attempt at the same import;
    `on_mapped(key, old, new)` is called right after each live create so an interrupted run can resume.
    """
    check_export(data)
    missing = set(data["lists"]) - set(targets)
    if missing:
        raise ConfigError(f"Choose a target list for: {', '.join(LISTS[k] for k in sorted(missing))}.")
    if len({cu.list_id for cu in targets.values()}) < len(targets):
        raise ConfigError("People and Orgs need different target lists.")
    dry = next(iter(targets.values())).dry
    log = TransferLog(reporter, dry=dry)
    id_map = dict(id_map or {})
    mine = set(id_map.values())

    tgts = {}
    for key, src in data["lists"].items():
        cu = targets[key]
        if str(cu.list_id) == str(src["id"]):
            raise SafetyStop(f"The target {LISTS[key]} list is the list this export came from.")
        t = _Target(key, cu, src, log)
        foreign = t.task_ids - mine
        if foreign:
            raise SafetyStop(f"The target {LISTS[key]} list '{t.name}' already has {len(foreign)} task(s). Import "
                             "only writes into empty lists: create a new list with the same custom fields and "
                             "use that.")
        for name, why in t.dropped.items():
            log.warn(f"{LISTS[key]}: '{name}' won't be imported because {why}.")
        for f, tgt, _, lost in t.fields.values():
            if lost:
                log.warn(f"{LISTS[key]}: field '{tgt['name']}' is missing option(s) {', '.join(lost)}; "
                         "those values will be left out.")
        lost_status = sorted({x["status"] for x in src["tasks"] if x["status"] and x["status"].lower() not in t.statuses})
        if lost_status:
            log.warn(f"{LISTS[key]}: the target list has no status {', '.join(lost_status)}; "
                     "those tasks get the list's default status.")
        tgts[key] = t

    # Pass 1: create every task (parents first) with its values and any description without task links.
    ordered = [(key, x) for key, src in data["lists"].items() for x in src["tasks"]]
    ordered.sort(key=lambda kx: bool(kx[1]["parent"]))
    exported = {x["id"] for _, x in ordered}
    dry_n = 0
    for i, (key, x) in enumerate(ordered, 1):
        log.tick("Creating tasks", i, len(ordered))
        t = tgts[key]
        if x["id"] in id_map:
            log.log("SKIP", x["name"], "already created by an earlier attempt", task_id=id_map[x["id"]])
            continue
        body = {"name": x["name"]}
        if x["status"] and x["status"].lower() in t.statuses:
            body["status"] = t.statuses[x["status"].lower()]
        if x["tags"]:
            body["tags"] = x["tags"]
        if PRIORITY.get(x["priority"] or ""):
            body["priority"] = PRIORITY[x["priority"]]
        for k in ("due_date", "start_date"):
            if x.get(k):
                body[k] = int(x[k])
        if x["parent"] and id_map.get(x["parent"]):
            body["parent"] = id_map[x["parent"]]
        if x["description"] and not any(m.group(1) in exported for m in TASK_URL_RE.finditer(x["description"])):
            body["markdown_content"] = x["description"]
        cfs = [(cf, t.encode(cf)) for cf in x["custom_fields"]]
        body["custom_fields"] = [{"id": t.fields[cf["field_id"]][1]["id"], "value": v} for cf, v in cfs
                                 if v is not None]
        try:
            new_id = _create(t.cu, body, x["name"], log)
        except Exception as e:  # noqa: BLE001 - one bad task shouldn't stop the import
            log.error(x["name"], e)
            continue
        if new_id is None:
            dry_n += 1
            new_id = f"dry-run-{dry_n}"
        elif on_mapped:
            on_mapped(key, x["id"], new_id)
        id_map[x["id"]] = new_id
        log.log("CREATE", x["name"], f"{LISTS[key]} · {len(body['custom_fields'])} field values", task_id=new_id)

    # Pass 2: now that every task exists, rewrite links between them, then archive what was archived.
    outside = 0
    for i, (key, x) in enumerate(ordered, 1):
        log.tick("Linking tasks", i, len(ordered))
        t, new_id = tgts[key], id_map.get(x["id"])
        if not new_id:
            continue
        try:
            md, mapped, out = _rewrite(x["description"], id_map)
            outside += out
            if mapped:
                _send(t.cu, "describe", "PUT", f"/task/{new_id}", {"markdown_content": md},
                      task_id=new_id, task_name=x["name"], field="Description", after=f"{mapped} task link(s)")
                log.log("LINK", x["name"], f"description: {mapped} link(s) to imported tasks", task_id=new_id)
            for cf in x["custom_fields"]:
                m = t.fields.get(cf["field_id"])
                if not m or m[1]["type"] not in LINK_TYPES:
                    continue
                items = [it["id"] for it in cf["value"] if isinstance(it, dict) and it.get("id")]
                ids = [id_map[it] for it in items if it in id_map]
                outside += len(items) - len(ids)
                if ids:
                    _send(t.cu, "link", "POST", f"/task/{new_id}/field/{m[1]['id']}",
                          {"value": {"add": ids, "rem": []}}, task_id=new_id, task_name=x["name"],
                          field=m[1]["name"], after=ids)
                    log.log("LINK", x["name"], f"{m[1]['name']}: {len(ids)} task(s)", task_id=new_id)
            if x["archived"]:
                _send(t.cu, "archive", "PUT", f"/task/{new_id}", {"archived": True},
                      task_id=new_id, task_name=x["name"], after={"archived": True})
                log.log("ARCHIVE", x["name"], "archived, as in the export", task_id=new_id)
        except Exception as e:  # noqa: BLE001
            log.error(x["name"], e)
    if outside:
        log.warn(f"{outside} link(s) point to tasks that aren't in the export; they were left pointing at "
                 "the original tasks.")
    return log, id_map


def _create(cu, body, name, log):
    """Create a task. If ClickUp rejects a custom field value, create it without values and set them one
    by one, so a single bad value costs that value rather than the whole task."""
    path = f"/list/{cu.list_id}/task"
    try:
        task = _send(cu, "create", "POST", path, body, task_id="(new)", task_name=name, after=body,
                     retry_5xx=False)
    except RuntimeError as e:
        if " -> 400:" not in str(e) or not body.get("custom_fields"):
            raise
        log.log("WARN", name, f"ClickUp rejected the task's field values ({str(e)[:160]}); setting them one by one")
        bare = {k: v for k, v in body.items() if k != "custom_fields"}
        task = _send(cu, "create", "POST", path, bare, task_id="(new)", task_name=name, after=bare,
                     retry_5xx=False)
        for cf in body["custom_fields"]:
            try:
                _send(cu, "set", "POST", f"/task/{task['id']}/field/{cf['id']}", {"value": cf["value"]},
                      task_id=task["id"], task_name=name, field=cf["id"], after=cf["value"])
            except Exception as fe:  # noqa: BLE001
                log.error(name, fe)
    return task["id"] if task else None
