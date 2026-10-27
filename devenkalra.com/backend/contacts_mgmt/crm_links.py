"""
crm_links.py - shared helpers for create_relation.py and link_org.py.

Descriptions hold managed sections at the end, each starting with a bold heading:
    **Relationships**   (person <-> person, written by create_relation.py)
    **Organizations**   (on a person, written by link_org.py)
    **People**          (on an org, written by link_org.py)
Each line looks like:  - Works at [Google](https://app.clickup.com/t/86abc) — VP Eng, 2015-2019
Text above the first managed heading is yours and is never changed.
"""
import difflib
import json
import re
import sys
import time
import unicodedata

from pathlib import Path

import requests

CACHE_DIR = Path(__file__).resolve().parent

API = "https://api.clickup.com/api/v2"
SECTIONS = ["Relationships", "Organizations", "People"]
HEADER_RE = re.compile(r"^\s*\*\*(%s)\*\*\s*$" % "|".join(SECTIONS), re.M)
LINE_RE = re.compile(r"^\s*[-*]\s+(.+?)\s+\[(.+?)\]\((https://app\.clickup\.com/t/[^)\s]+)\)\s*(?:[—–-]+\s*(.*?))?\s*$")
ITEM_RE = re.compile(r"^\s+[-*+]\s+\[(.+?)\]\((https://app\.clickup\.com/t/[^)\s]+)\)\s*(?:[—–-]+\s*(.*?))?\s*$")
GROUP_RE = re.compile(r"^\s*[-*+]\s+([^\[\]]+?)\s*:?\s*$")
ID_RE = r"(?=.*\d)[a-z0-9]{6,12}"


class ClickUp:
    def __init__(self, token, dry):
        self.dry = dry
        self.s = requests.Session()
        self.s.headers.update({"Authorization": token, "Content-Type": "application/json"})
        self._tasks = {}

    def req(self, method, path, **kw):
        for attempt in range(7):
            r = self.s.request(method, API + path, timeout=30, **kw)
            if r.status_code == 429:
                reset = r.headers.get("X-RateLimit-Reset")
                time.sleep(min(max(float(reset) - time.time() if reset else 2 ** attempt, 1), 65))
                continue
            if r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            if not r.ok:
                raise RuntimeError(f"ClickUp {method} {path} -> {r.status_code}: {r.text[:300]}")
            return r.json() if r.text else {}
        raise RuntimeError(f"ClickUp {method} {path}: retries exhausted")

    def list_id(self, ref):
        """Accept a numeric list ID, a list URL, or a view ID like '2kyddzem-1154'."""
        ref = str(ref).strip()
        m = re.search(r"/li/(\d+)", ref)
        if m:
            return m.group(1)
        if ref.isdigit():
            return ref
        m = re.search(r"([0-9a-z]+-\d+)", ref)
        if m:
            view = self.req("GET", f"/view/{m.group(1)}").get("view", {})
            parent = view.get("parent", {})
            if str(parent.get("type")) == "6":
                return str(parent["id"])
            sys.exit(f"View {m.group(1)} doesn't belong to a single list (parent type {parent.get('type')}).")
        sys.exit(f"Can't read a list ID from '{ref}'.")

    def all_tasks(self, list_id, fresh=False):
        """[{id, name}] for the list. Served from a local cache unless fresh=True."""
        cache = CACHE_DIR / f".names_{list_id}.json"
        if not fresh and list_id not in self._tasks and cache.exists():
            try:
                self._tasks[list_id] = json.loads(cache.read_text(encoding="utf-8"))
                self._cached = getattr(self, "_cached", set()) | {list_id}
            except ValueError:
                pass
        if fresh and list_id in getattr(self, "_cached", set()):
            self._tasks.pop(list_id, None)
            self._cached.discard(list_id)
        if list_id not in self._tasks:
            print("Refreshing the name list from ClickUp (one-time, can take a minute)...", flush=True)
            out, page = [], 0
            while True:
                d = self.req("GET", f"/list/{list_id}/task",
                             params={"page": page, "include_closed": "true", "subtasks": "true"})
                out += d.get("tasks", [])
                if d.get("last_page") or len(d.get("tasks", [])) < 100:
                    break
                page += 1
            self._tasks[list_id] = [{"id": t["id"], "name": t["name"]} for t in out if not t.get("archived")]
            try:
                cache.write_text(json.dumps(self._tasks[list_id]), encoding="utf-8")
            except OSError:
                pass
        return self._tasks[list_id]

    def remember(self, list_id, tid, name):
        """Add a newly created task to the cache."""
        if list_id in self._tasks and not self.dry:
            self._tasks[list_id].append({"id": tid, "name": name})
            try:
                (CACHE_DIR / f".names_{list_id}.json").write_text(json.dumps(self._tasks[list_id]), encoding="utf-8")
            except OSError:
                pass

    def is_cached(self, list_id):
        return list_id in getattr(self, "_cached", set())

    def task(self, tid):
        return self.req("GET", f"/task/{tid}", params={"include_markdown_description": "true"})

    def create_task(self, list_id, name):
        if self.dry:
            return {"id": "dry-run-new", "name": name}
        return self.req("POST", f"/list/{list_id}/task", json={"name": name})


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).lower().split())


def task_url(tid):
    return f"https://app.clickup.com/t/{tid}"


def label(kind):
    """WORKS_AT -> 'Works at'."""
    words = kind.strip().replace("-", "_").replace(" ", "_").lower().split("_")
    return " ".join(w for w in words if w).capitalize()


def parse_type(t, inverse):
    t = t.strip().upper().replace("-", "_").replace(" ", "_")
    if "/" in t:
        fwd, inv = (x.strip("_") for x in t.split("/", 1))
    else:
        fwd, inv = t, inverse.get(t, t)
    if not fwd or not inv:
        sys.exit(f"Can't read relationship type '{t}'.")
    return label(fwd), label(inv)


def is_ref(x):
    return bool(re.search(r"app\.clickup\.com/t/", x) or re.fullmatch(ID_RE, x))


def resolve(cu, who, list_id, what="contact", create=False):
    """Name, task ID or task URL -> (id, name). Optionally create the task if no name matches."""
    m = re.search(r"app\.clickup\.com/t/(?:\d+/)?([A-Za-z0-9_-]+)", who)
    if m or re.fullmatch(ID_RE, who):
        t = cu.task(m.group(1) if m else who)
        return t["id"], t["name"]
    tasks = cu.all_tasks(list_id)
    exact = [t for t in tasks if norm(t["name"]) == norm(who)]
    if len(exact) == 1 and cu.is_cached(list_id):
        try:  # confirm the cached entry still exists, is live and has that name
            t = cu.task(exact[0]["id"])
            if norm(t["name"]) == norm(who) and not t.get("archived"):
                return t["id"], t["name"]
        except RuntimeError:
            pass
    if cu.is_cached(list_id):
        tasks = cu.all_tasks(list_id, fresh=True)
        exact = [t for t in tasks if norm(t["name"]) == norm(who)]
    if len(exact) == 1:
        return exact[0]["id"], exact[0]["name"]
    if len(exact) > 1:
        print(f"'{who}' matches {len(exact)} {what}s. Re-run with the task ID or URL instead:")
        for t in exact:
            print(f"  {t['id']}  {t['name']}  {task_url(t['id'])}")
        sys.exit(1)
    if create:
        t = cu.create_task(list_id, who.strip())
        cu.remember(list_id, t["id"], who.strip())
        print(f"{'[dry] ' if cu.dry else ''}Created {what} '{who.strip()}' {task_url(t['id'])}")
        return t["id"], who.strip()
    names = {t["name"]: t for t in tasks}
    close = difflib.get_close_matches(who, list(names), n=5, cutoff=0.6)
    print(f"No {what} named '{who}'." + (" Did you mean:" if close else ""))
    for n in close:
        print(f"  {names[n]['id']}  {n}")
    if what == "org":
        print("Add --create to create it in the Orgs list.")
    sys.exit(1)


def split_sections(md):
    """-> (head, {section: [(label, name, url, note)]}) with sections in SECTIONS order."""
    md = md or ""
    heads = list(HEADER_RE.finditer(md))
    if not heads:
        return md.rstrip(), {}
    head = md[:heads[0].start()].rstrip()
    secs = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(md)
        group = None
        for ln in md[h.end():end].splitlines():
            mi = ITEM_RE.match(ln)            # grouped item:   "    - [Name](url) — note"
            if mi and group:
                secs.setdefault(h.group(1), []).append(
                    (group, mi.group(1).strip(), mi.group(2).strip(), (mi.group(3) or "").strip()))
                continue
            mm = LINE_RE.match(ln)            # old flat line:  "- Label [Name](url) — note"
            if mm:
                secs.setdefault(h.group(1), []).append(
                    (mm.group(1).strip(), mm.group(2).strip(), mm.group(3).strip(), (mm.group(4) or "").strip()))
                continue
            mg = GROUP_RE.match(ln)           # group heading:  "- Label"
            if mg:
                group = mg.group(1).strip()
    return head, secs


def render(head, secs):
    parts = [head] if head else []
    for name in SECTIONS:
        lines = secs.get(name)
        if not lines:
            continue
        groups = {}
        for lab, n, u, note in lines:
            key = lab.lower()
            groups.setdefault(key, [lab, []])[1].append((n, u, note))
        out = []
        for key in sorted(groups):
            lab, items = groups[key]
            out.append(f"- {lab}")
            for n, u, note in sorted(items, key=lambda x: norm(x[0])):
                out.append(f"    - [{n}]({u})" + (f" — {note}" if note else ""))
        parts.append(f"**{name}**\n" + "\n".join(out))
    return "\n\n".join(parts)


def upsert_line(cu, me_id, section, lab, other_id, other_name, note=None, remove=False):
    """Add/update/remove one line in a section of a task's description. Returns (task name, changed)."""
    t = cu.task(me_id)
    head, secs = split_sections(t.get("markdown_description") or t.get("description") or "")
    lines = secs.get(section, [])
    same = lambda l: l[0].lower() == lab.lower() and l[2].rstrip("/").endswith(other_id)
    old = next((l for l in lines if same(l)), None)
    new = [l for l in lines if not same(l)]
    if not remove:
        keep_note = note if note is not None else (old[3] if old else "")
        new.append((lab, other_name, task_url(other_id), keep_note))
        new.sort(key=lambda l: (l[0].lower(), l[1].lower()))
    if new == lines:
        return t["name"], False
    secs[section] = new
    if not cu.dry:
        cu.req("PUT", f"/task/{me_id}", json={"markdown_content": render(head, secs)})
    return t["name"], True
