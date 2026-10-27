#!/usr/bin/env python3
"""
contacts_sync.py - idempotent import of Google Contacts and LinkedIn connections
into a ClickUp "Contacts" list (one task per person).

Setup
  pip install requests google-api-python-client google-auth-oauthlib phonenumbers
  export CLICKUP_TOKEN=pk_...          # ClickUp personal API token
  export CLICKUP_LIST_ID=901234567     # ID of your Contacts list
  export DEFAULT_REGION=US             # optional, for parsing phone numbers without +country
  export GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=...   # or credentials.json; OAuth client with People API enabled

Commands
  python contacts_sync.py check
  python contacts_sync.py google   [--dry-run] [--full] [--writeback]
  python contacts_sync.py linkedin Connections.csv [--dry-run]
  python contacts_sync.py merge SURVIVOR_TASK_ID LOSER_TASK_ID [--dry-run]

Recommended order: check -> google --dry-run -> google -> linkedin --dry-run -> linkedin.
Every run writes a JSON report of what it did (or would do) next to the script.
"""
import argparse
import csv
import fnmatch
import difflib
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

import phonenumbers
import requests

# --------------------------------------------------------------------------------------
# Configuration: internal key -> custom field name in your ClickUp list (case-insensitive)
# --------------------------------------------------------------------------------------
FIELDS = {
    "google_id":     "Google ID",      # Short text  - people/c123...   (idempotency key)
    "google_link":   "Google Link",    # URL         - contacts.google.com link
    "google_hash":   "Google hash",    # Short text  - change detection
    "linkedin_url":  "LinkedIn URL",   # URL         - normalized profile URL (idempotency key)
    "linkedin_hash": "LinkedIn hash",  # Short text  - change detection
    "email":         "Email",          # Email       - primary email (optional)
    "emails":        "Emails",         # Short text  - all emails, comma separated
    "phones":        "Phones",         # Short text  - all phones, comma separated (E.164 when valid)
    "company":       "Company",        # Short text
    "title":         "Title",          # Short text
    "birthday":      "Birthday",       # Text (recommended: "03-14 (1985)", sorts by month) or Date  - from Google
    "address":       "Address",        # Text        - from Google
    "website":       "Website",        # URL         - from Google
    "groups":        "Groups",         # Labels      - Google contact labels are ADDED, never removed
    "connected_on":  "Connected on",   # Date        - from LinkedIn
    "sources":       "Sources",        # Labels      - options: Google, LinkedIn (added automatically, never removed)
    "last_li_msg":   "Last LinkedIn message",  # Date - latest message with them, from messages.csv
    "whatsapp":      "WhatsApp",       # Text        - WhatsApp number, E.164 (idempotency key for WhatsApp)
    "whatsapp_hash": "WhatsApp hash",  # Text        - change detection
    "last_wa_msg":   "Last WhatsApp message",  # Date - latest WhatsApp message with them
    "status":        "Match status",   # Dropdown (or text): active / possible duplicate / deleted in google / merged
    "dup_of":        "Duplicate of",   # URL or short text - suspected duplicate task link
    "last_synced":   "Last synced",    # Date (optional)
}
EXTRA = ("birthday", "address", "website", "connected_on")  # single-valued, source-owned
SOURCE_LABEL = {"google": "Google", "linkedin": "LinkedIn", "whatsapp": "WhatsApp"}
REQUIRED = ["google_id", "google_hash", "linkedin_url", "linkedin_hash", "emails", "status", "dup_of"]

ACTIVE, REVIEW, DELETED, MERGED = "active", "possible duplicate", "deleted in google", "merged"
STATUS_OPTIONS = [ACTIVE, REVIEW, DELETED, MERGED]

KEY = {"google": "google_id", "linkedin": "linkedin_url", "whatsapp": "whatsapp"}
HASH = {"google": "google_hash", "linkedin": "linkedin_hash", "whatsapp": "whatsapp_hash"}

NAME_STRONG = 0.95        # name similarity that alone flags a possible duplicate
NAME_WITH_COMPANY = 0.85  # name similarity that flags a duplicate when the company also matches

DEFAULT_REGION = os.environ.get("DEFAULT_REGION", "US")
HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "sync_state.json"


# --------------------------------------------------------------------------------------
# Normalization helpers
# --------------------------------------------------------------------------------------
def norm_email(e):
    e = (e or "").strip().lower()
    return e if "@" in e else None


def norm_phone(p):
    """E.164 for valid numbers, else None (used for matching)."""
    if not p:
        return None
    try:
        n = phonenumbers.parse(p, DEFAULT_REGION)
        if phonenumbers.is_valid_number(n):
            return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return None


def phone_for_storage(p):
    return norm_phone(p) or (p or "").strip() or None


def norm_li(url):
    m = re.search(r"linkedin\.com/in/([^/?#\s]+)", url or "", re.I)
    return f"https://www.linkedin.com/in/{m.group(1).lower()}" if m else None


NICKNAMES = {
    "bob": "robert", "rob": "robert", "bobby": "robert", "bill": "william", "will": "william",
    "liz": "elizabeth", "beth": "elizabeth", "jim": "james", "jimmy": "james", "mike": "michael",
    "dave": "david", "dan": "daniel", "danny": "daniel", "tom": "thomas", "chris": "christopher",
    "kate": "katherine", "katie": "katherine", "cathy": "catherine", "alex": "alexander",
    "sam": "samuel", "joe": "joseph", "tony": "anthony", "nick": "nicholas", "matt": "matthew",
    "steve": "steven", "andy": "andrew", "ben": "benjamin", "jen": "jennifer", "jenny": "jennifer",
    "rick": "richard", "dick": "richard", "ed": "edward", "greg": "gregory", "pat": "patrick",
}


def norm_name(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    toks = [NICKNAMES.get(t, t) for t in re.sub(r"[^a-z\s]", " ", s).split() if len(t) > 1]
    return " ".join(sorted(toks))  # sorted: tolerant of first/last order swaps


COMPANY_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|gmbh|plc)\b\.?")


def norm_company(s):
    s = COMPANY_SUFFIX.sub("", (s or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def split_list(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def union(*lists):
    out = []
    for lst in lists:
        for x in lst:
            if x and x not in out:
                out.append(x)
    return out


def content_hash(d):
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def now_ms():
    return int(time.time() * 1000)


def task_url(tid):
    return f"https://app.clickup.com/t/{tid}"


def load_state():
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# --------------------------------------------------------------------------------------
# ClickUp API
# --------------------------------------------------------------------------------------
class ClickUp:
    BASE = "https://api.clickup.com/api/v2"

    def __init__(self, token, list_id, dry_run):
        self.list_id, self.dry = list_id, dry_run
        self.s = requests.Session()
        self.s.headers.update({"Authorization": token, "Content-Type": "application/json"})
        self.fields = {}
        self.all_fields = []

    def _req(self, method, path, **kw):
        for attempt in range(7):
            r = self.s.request(method, self.BASE + path, timeout=30, **kw)
            if r.status_code == 429:
                reset = r.headers.get("X-RateLimit-Reset")
                wait = float(reset) - time.time() if reset else 2 ** attempt
                time.sleep(min(max(wait, 1), 65))
                continue
            if r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            if not r.ok:
                raise RuntimeError(f"ClickUp {method} {path} -> {r.status_code}: {r.text[:300]}")
            return r.json() if r.text else {}
        raise RuntimeError(f"ClickUp {method} {path}: retries exhausted")

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
                    return None  # ClickUp Date fields need a full date after 1970; use a Text field instead
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

    def all_tasks(self):
        tasks, page = [], 0
        while True:
            d = self._req("GET", f"/list/{self.list_id}/task",
                          params={"page": page, "include_closed": "true", "subtasks": "true"})
            batch = d.get("tasks", [])
            tasks += batch
            if d.get("last_page") or len(batch) < 100:
                return tasks
            page += 1

    def create(self, name, values):
        if self.dry:
            self._n = getattr(self, "_n", 0) + 1
            return {"id": f"dry-run-{self._n}"}
        cfs = [{"id": self.fields[k]["id"], "value": self.encode(k, v)}
               for k, v in values.items() if k in self.fields and v not in (None, "")]
        return self._req("POST", f"/list/{self.list_id}/task", json={"name": name, "custom_fields": cfs})

    def set_fields(self, task_id, changes):
        if self.dry:
            return
        for k, v in changes.items():
            if k not in self.fields:
                continue
            fid = self.fields[k]["id"]
            if v in (None, ""):
                if self.fields[k]["type"] in ("tasks", "list_relationship"):
                    continue
                self._req("DELETE", f"/task/{task_id}/field/{fid}")
            else:
                self._req("POST", f"/task/{task_id}/field/{fid}", json={"value": self.encode(k, v)})

    def attachment_names(self, task_id):
        t = self._req("GET", f"/task/{task_id}")
        return {a.get("title") or "" for a in t.get("attachments", [])}

    def upload(self, task_id, filename, data, mime):
        for attempt in range(7):
            r = requests.post(f"{self.BASE}/task/{task_id}/attachment",
                              headers={"Authorization": self.s.headers["Authorization"]},
                              files={"attachment": (filename, data, mime)}, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(min(2 ** attempt, 60))
                continue
            if not r.ok:
                raise RuntimeError(f"ClickUp upload -> {r.status_code}: {r.text[:300]}")
            return r.json()
        raise RuntimeError("ClickUp upload: retries exhausted")

    def update_task(self, task_id, **body):
        if not self.dry:
            self._req("PUT", f"/task/{task_id}", json=body)


# --------------------------------------------------------------------------------------
# Local index of existing ClickUp contacts
# --------------------------------------------------------------------------------------
class Index:
    def __init__(self):
        self.by_id = {}
        self.by_key = {"google_id": {}, "linkedin_url": {}, "whatsapp": {}}
        self.by_email, self.by_phone, self.by_token = {}, {}, {}

    def add(self, rec):
        tid, v = rec["id"], rec["v"]
        self.by_id[tid] = rec
        for kf, m in self.by_key.items():
            k = v.get(kf)
            if kf == "linkedin_url" and k:
                k = norm_li(k) or k
            if kf == "whatsapp" and k:
                k = norm_phone(k) or k
            if not k:
                continue
            other = m.get(k)
            if other and other != tid:
                print(f"WARN: {FIELDS[kf]} {k} is on two tasks: {task_url(other)} and {task_url(tid)}")
            else:
                m[k] = tid
        for e in split_list(v.get("emails")) + [v.get("email") or ""]:
            if norm_email(e):
                self.by_email.setdefault(norm_email(e), set()).add(tid)
        for p in split_list(v.get("phones")):
            if norm_phone(p):
                self.by_phone.setdefault(norm_phone(p), set()).add(tid)
        for t in norm_name(rec["name"]).split():
            self.by_token.setdefault(t, set()).add(tid)

    def get_key(self, kf, k):
        tid = self.by_key[kf].get(k)
        return self.by_id.get(tid) if tid else None


def build_index(cu):
    ix = Index()
    for t in cu.all_tasks():
        if t.get("archived"):
            continue
        ix.add({"id": t["id"], "name": t.get("name", ""), "v": {k: cu.decode(t, k) for k in FIELDS}})
    return ix


# --------------------------------------------------------------------------------------
# Matching and upsert
# --------------------------------------------------------------------------------------
class Ctx:
    def __init__(self, cu, ix, dry):
        self.cu, self.ix, self.dry = cu, ix, dry
        self.stats, self.actions = Counter(), []
        self.unknown_groups = Counter()
        self.unknown_sources = set()
        self.hold_review, self.decisions, self.review_rows = False, {}, []
        self.review_file, self.review_source = None, None
        self.no_create = False
        self.trust_names = False

    def log(self, action, name, detail=""):
        self.stats[action] += 1
        self.actions.append({"action": action, "name": name, "detail": detail})
        if action != "UNCHANGED":
            print(f"{'[dry] ' if self.dry else ''}{action:<10} {name}  {detail}")


def find_existing(ix, c):
    """Exact email/phone -> auto-link; similar name -> review candidate."""
    kf = KEY[c["source"]]

    def free(tid):  # task not already linked to a different record from this source
        return not ix.by_id[tid]["v"].get(kf)

    for e in c["emails"]:
        hits = [t for t in ix.by_email.get(e, ()) if free(t)]
        if hits:
            return ix.by_id[hits[0]], ("email" if len(hits) == 1 else "fuzzy")
    for p in c["phones"]:
        hits = [t for t in ix.by_phone.get(norm_phone(p), ()) if free(t)] if norm_phone(p) else []
        if hits:
            return ix.by_id[hits[0]], ("phone" if len(hits) == 1 else "fuzzy")

    target = norm_name(c["name"])
    if not target:
        return None, None
    comp = norm_company(c.get("company"))
    cand = set().union(*(ix.by_token.get(t, set()) for t in target.split()))
    best, best_score = None, 0.0
    for tid in cand:
        r = ix.by_id[tid]
        sim = difflib.SequenceMatcher(None, target, norm_name(r["name"])).ratio()
        rc = norm_company(r["v"].get("company"))
        same_co = bool(comp and rc and (comp in rc or rc in comp))
        if sim >= NAME_STRONG or (sim >= NAME_WITH_COMPANY and same_co):
            score = sim + (0.1 if same_co else 0)
            if score > best_score:
                best, best_score = r, score
    return (best, "fuzzy") if best else (None, None)


def upsert(ctx, c):
    rec = ctx.ix.get_key(KEY[c["source"]], c["key"])
    if rec:
        return update(ctx, rec, c, "key")
    match, how = find_existing(ctx.ix, c)
    if how == "fuzzy":
        if not ctx.hold_review:
            return create(ctx, c, REVIEW, dup=match)
        if ctx.trust_names and norm_name(c["name"]) == norm_name(match["name"]):
            same_name = [r for r in ctx.ix.by_id.values() if norm_name(r["name"]) == norm_name(c["name"])]
            if len(same_name) == 1:
                return update(ctx, match, c, "name")
        d = ctx.decisions.get(c["key"])
        if d and d["decision"] == "same":
            rec = ctx.ix.by_id.get(cs_task_id(d.get("suggested_task_url")) or match["id"])
            if rec:
                return update(ctx, rec, c, "review")
        if d and d["decision"] == "new":
            return create_or_skip(ctx, c)
        ctx.review_rows.append({"decision": "", "name": c["name"], "company": c.get("company") or "",
                                "title": c.get("title") or "", "key": c["key"],
                                "suggested_task_name": match["name"], "suggested_task_url": task_url(match["id"])})
        ctx.log("PENDING", c["name"], f"maybe '{match['name']}'; decide in {ctx.review_file.name}")
        return None
    if match:
        return update(ctx, match, c, how)
    return create_or_skip(ctx, c)


def create_or_skip(ctx, c):
    if ctx.no_create:
        ctx.log("SKIP", c["name"], "no matching contact (--no-create)")
        return None
    return create(ctx, c, ACTIVE)


def wanted_groups(ctx, c):
    """Source groups that exist as options on the ClickUp Groups field; remember the rest."""
    if "groups" not in ctx.cu.fields:
        return []
    opts = ctx.cu.label_options("groups")
    out = []
    for g in c.get("groups", []):
        o = opts.get(g.lower())
        if o:
            out.append((o.get("label") or o.get("name")).strip())
        else:
            ctx.unknown_groups[g] += 1
    return out


def source_label(ctx, c):
    opts = ctx.cu.label_options("sources")
    o = opts.get(SOURCE_LABEL[c["source"]].lower())
    if "sources" in ctx.cu.fields and not o:
        ctx.unknown_sources.add(SOURCE_LABEL[c["source"]])
    return [(o.get("label") or o.get("name")).strip()] if o else []


def create(ctx, c, status, dup=None):
    vals = {
        KEY[c["source"]]: c["key"], HASH[c["source"]]: c["hash"],
        "emails": ", ".join(c["emails"]), "phones": ", ".join(c["phones"]),
        "email": c["emails"][0] if c["emails"] else None,
        "company": c.get("company"), "title": c.get("title"),
        "status": status, "last_synced": now_ms(),
        "google_link": c.get("link"),
        "dup_of": task_url(dup["id"]) if dup else None,
    }
    for k in EXTRA:
        vals[k] = ctx.cu.prep(k, c.get("extra", {}).get(k))
    vals["groups"] = wanted_groups(ctx, c) or None
    vals["sources"] = source_label(ctx, c) or None
    task = ctx.cu.create(c["name"], vals)
    rec = {"id": task["id"], "name": c["name"], "v": {k: vals.get(k) for k in FIELDS}}
    ctx.ix.add(rec)
    if dup:
        ctx.log("REVIEW", c["name"], f"possible duplicate of '{dup['name']}' {task_url(dup['id'])}")
    else:
        ctx.log("CREATE", c["name"], c["key"])
    return rec


def update(ctx, rec, c, how):
    v, src = rec["v"], c["source"]
    kf, hf = KEY[src], HASH[src]
    extra = {k: ctx.cu.prep(k, c.get("extra", {}).get(k)) for k in EXTRA}
    new_sources = [x for x in source_label(ctx, c)
                   if x.lower() not in {y.lower() for y in (v.get("sources") or [])}]
    new_groups = [g for g in wanted_groups(ctx, c)
                  if g.lower() not in {x.lower() for x in (v.get("groups") or [])}]
    backfill = ((c["emails"] and "emails" in ctx.cu.fields and not v.get("emails")) or
                (c["phones"] and "phones" in ctx.cu.fields and not v.get("phones")) or
                any(val is not None and v.get(k) in (None, "") for k, val in extra.items()) or
                bool(new_groups) or bool(new_sources))
    if how == "key" and v.get(hf) == c["hash"] and v.get("status") not in (DELETED, None) and not backfill:
        ctx.log("UNCHANGED", rec["name"])
        return rec

    ch = {}
    if how != "key":
        ch[kf] = c["key"]
    if c.get("link") and v.get("google_link") != c["link"]:
        ch["google_link"] = c["link"]

    emails = union([norm_email(e) for e in split_list(v.get("emails"))], c["emails"])
    if ", ".join(emails) != (v.get("emails") or ""):
        ch["emails"] = ", ".join(emails)
    if "email" in ctx.cu.fields and not v.get("email") and emails:
        ch["email"] = emails[0]
    phones = union([phone_for_storage(p) for p in split_list(v.get("phones"))], c["phones"])
    if ", ".join(phones) != (v.get("phones") or ""):
        ch["phones"] = ", ".join(phones)

    # Company/title: LinkedIn wins; Google only fills blanks once LinkedIn is linked.
    for f in ("company", "title"):
        new = c.get(f)
        owner = src == "linkedin" or not (v.get("linkedin_url") or ch.get("linkedin_url"))
        if new and (not v.get(f) or (owner and v.get(f) != new)):
            ch[f] = new

    for k, val in extra.items():
        if val is not None and str(v.get(k)) != str(val):
            ch[k] = val
    if new_groups:
        ch["groups"] = (v.get("groups") or []) + new_groups
    if new_sources:
        ch["sources"] = (v.get("sources") or []) + new_sources

    ch[hf] = c["hash"]
    ch["last_synced"] = now_ms()
    if v.get("status") in (None, DELETED):
        ch["status"] = ACTIVE

    rename = src == "google" and c["name"] and c["name"] != rec["name"]
    if rename:
        ctx.cu.update_task(rec["id"], name=c["name"])
    ctx.cu.set_fields(rec["id"], ch)

    old_name = rec["name"]
    if rename:
        rec["name"] = c["name"]
    v.update(ch)
    ctx.ix.add(rec)
    label = "UPDATE" if how == "key" else f"LINK({how})"
    detail = ", ".join(FIELDS[k] for k in ch if k not in ("last_synced", hf))
    if rename:
        detail = f"renamed from '{old_name}'; " + detail
    ctx.log(label, rec["name"], detail)
    return rec


# --------------------------------------------------------------------------------------
# Google Contacts
# --------------------------------------------------------------------------------------
PERSON_FIELDS = ("names,emailAddresses,phoneNumbers,organizations,externalIds,metadata,"
                 "birthdays,addresses,urls,memberships,photos")
IGNORE_FILE = HERE / "ignore_labels.txt"
REVIEW_COLS = ["decision", "name", "company", "title", "key", "suggested_task_name", "suggested_task_url"]


def review_file(source):
    return HERE / f"{source}_review.csv"


def norm_key(source, k):
    if source == "linkedin":
        return norm_li(k) or (k or "")
    if source == "whatsapp":
        return norm_phone(k) or (k or "")
    return k or ""


def cs_task_id(url):
    m = re.search(r"/t/([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else None


def load_decisions(ctx, source):
    ctx.hold_review, ctx.review_file, ctx.review_source = True, review_file(source), source
    ctx.review_rows = []
    if not ctx.review_file.exists():
        return {}
    with open(ctx.review_file, encoding="utf-8-sig", newline="") as fh:
        out = {}
        for r in csv.DictReader(fh):
            r["decision"] = (r.get("decision") or "").strip().lower()
            if r["decision"] in ("s", "y", "yes", "same", "merge", "link"):
                r["decision"] = "same"
            elif r["decision"] in ("n", "no", "new", "different", "create"):
                r["decision"] = "new"
            r["key"] = norm_key(source, r.get("key") or r.get("linkedin_url"))  # older files used linkedin_url
            r["name"] = r.get("name") or r.get("linkedin_name") or ""
            out[r["key"]] = r
        return out


def finish_review(ctx):
    save_review(ctx)
    if ctx.review_rows:
        print(f"\n{len(ctx.review_rows)} possible matches need a decision. Open {ctx.review_file.name}, put 'same' or"
              f" 'new' in the decision column, save, and run the import again. Undecided rows are left alone.")


def save_review(ctx):
    """Rewrite the review file: undecided rows first, then already-decided rows for reference."""
    pending_keys = {r["key"] for r in ctx.review_rows}
    decided = [r for k, r in ctx.decisions.items() if r["decision"] in ("same", "new") and k not in pending_keys]
    rows = ctx.review_rows + decided
    if not rows:
        return
    def write(path):
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=REVIEW_COLS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    while True:
        try:
            write(ctx.review_file)
            return
        except PermissionError:
            print(f"\nCan't write {ctx.review_file.name}; it's probably open in Excel.")
            if sys.stdin.isatty():
                ans = input("Close it and press Enter to retry (or type s + Enter to save a copy instead): ")
                if ans.strip().lower() != "s":
                    continue
            alt = ctx.review_file.with_name(f"{ctx.review_file.stem}_{datetime.now():%Y%m%d-%H%M%S}.csv")
            write(alt)
            print(f"Saved the review list to {alt.name} instead. Copy your decisions into "
                  f"{ctx.review_file.name} (or rename the file) before the next run.")
            return


def load_ignore(extra=()):
    """Label patterns to skip entirely (case-insensitive, * and ? wildcards), from ignore_labels.txt + CLI."""
    pats = list(extra or [])
    if IGNORE_FILE.exists():
        for ln in IGNORE_FILE.read_text(encoding="utf-8").splitlines():
            ln = ln.split("#", 1)[0].strip()
            if ln:
                pats.append(ln)
    return [p.lower() for p in pats]


def ignored(name, pats):
    return any(fnmatch.fnmatchcase(name.lower(), p) for p in pats)


GROUP_NAMES = {}  # contactGroups/xyz -> label name (user-created labels only)


def google_service(writeback):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    scope = "contacts" if writeback else "contacts.readonly"
    scopes = [f"https://www.googleapis.com/auth/{scope}"]
    token_file = HERE / f"token_{'rw' if writeback else 'ro'}.json"
    creds = Credentials.from_authorized_user_file(str(token_file), scopes) if token_file.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            secrets = HERE / "credentials.json"
            cid, csec = os.environ.get("GOOGLE_CLIENT_ID"), os.environ.get("GOOGLE_CLIENT_SECRET")
            if secrets.exists():
                flow = InstalledAppFlow.from_client_secrets_file(str(secrets), scopes)
            elif cid and csec:
                flow = InstalledAppFlow.from_client_config({"installed": {
                    "client_id": cid, "client_secret": csec,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost:8765/"],
                }}, scopes)
            else:
                sys.exit("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, or put credentials.json next to the script.")
            creds = flow.run_local_server(port=int(os.environ.get("GOOGLE_OAUTH_PORT", "8765")))
        token_file.write_text(creds.to_json())
    return build("people", "v1", credentials=creds, cache_discovery=False)


def fetch_google(svc, sync_token):
    people, page = [], None
    while True:
        kw = dict(resourceName="people/me", pageSize=1000, personFields=PERSON_FIELDS, requestSyncToken=True)
        if sync_token:
            kw["syncToken"] = sync_token
        if page:
            kw["pageToken"] = page
        resp = svc.people().connections().list(**kw).execute()
        people += resp.get("connections", [])
        page = resp.get("nextPageToken")
        if not page:
            return people, resp.get("nextSyncToken")


def google_contact(p):
    rid = p["resourceName"]
    emails = union([norm_email(e.get("value")) for e in p.get("emailAddresses", [])])
    phones = union([phone_for_storage(x.get("canonicalForm") or x.get("value")) for x in p.get("phoneNumbers", [])])
    org = (p.get("organizations") or [{}])[0]
    display = ((p.get("names") or [{}])[0].get("displayName") or "").strip()
    name = display or (emails[0] if emails else "") or (phones[0] if phones else "") or org.get("name") or "(no name)"
    c = {
        "source": "google", "key": rid, "name": name, "emails": emails, "phones": phones,
        "company": (org.get("name") or "").strip() or None, "title": (org.get("title") or "").strip() or None,
        "link": f"https://contacts.google.com/person/{rid.split('/')[-1]}",
    }
    bday = None
    for b in p.get("birthdays", []):
        d = b.get("date") or {}
        if d.get("month") and d.get("day"):
            bday = (d.get("year"), d["month"], d["day"])
            if b.get("metadata", {}).get("primary"):
                break
    addrs = p.get("addresses", [])
    addr = next((a for a in addrs if a.get("metadata", {}).get("primary")), addrs[0] if addrs else {})
    address = " ".join((addr.get("formattedValue") or "").split()) or None
    urls = p.get("urls", [])
    website = next((u.get("value") for u in urls if "linkedin.com" not in (u.get("value") or "")), None)
    if website and not re.match(r"https?://", website):
        website = "https://" + website
    c["extra"] = {"birthday": bday, "address": address, "website": website}
    photo = next((ph for ph in p.get("photos", []) if not ph.get("default") and ph.get("metadata", {}).get("primary")),
                 next((ph for ph in p.get("photos", []) if not ph.get("default")), None))
    c["photo_url"] = re.sub(r"=s\d+(-c)?$", "=s512", photo["url"]) if photo and photo.get("url") else None
    c["groups"] = sorted({GROUP_NAMES[m["contactGroupMembership"]["contactGroupResourceName"]]
                          for m in p.get("memberships", [])
                          if m.get("contactGroupMembership", {}).get("contactGroupResourceName") in GROUP_NAMES})
    c["hash"] = content_hash({**{k: c[k] for k in ("name", "emails", "phones", "company", "title", "groups")},
                              **c["extra"], "photo": c["photo_url"]})
    return c


def sync_photo(ctx, rec, c):
    """Attach the Google photo as photo-<hash>.jpg unless that exact photo is already attached."""
    url = c.get("photo_url")
    if not url or not rec or str(rec["id"]).startswith("dry-run"):
        return
    if ctx.dry:
        ctx.log("PHOTO", rec["name"], "would attach Google photo")
        return
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    ext = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(mime, "jpg")
    fname = f"photo-{hashlib.sha1(r.content).hexdigest()[:10]}.{ext}"
    if fname in ctx.cu.attachment_names(rec["id"]):
        return
    ctx.cu.upload(rec["id"], fname, r.content, mime)
    ctx.log("PHOTO", rec["name"], fname)


def mark_deleted(ctx, rid):
    rec = ctx.ix.get_key("google_id", rid)
    if not rec or rec["v"].get("status") in (DELETED, MERGED):
        return
    ctx.cu.set_fields(rec["id"], {"status": DELETED})
    rec["v"]["status"] = DELETED
    ctx.log("DELETED", rec["name"], f"{rid} no longer in Google")


def writeback(svc, person, task_id):
    """Store the ClickUp task id on the Google contact (externalIds, type 'clickup')."""
    ext = person.get("externalIds", [])
    if any(e.get("type") == "clickup" and e.get("value") == task_id for e in ext):
        return
    ext = [{"type": e.get("type"), "value": e.get("value")} for e in ext if e.get("type") != "clickup"]
    ext.append({"type": "clickup", "value": task_id})
    svc.people().updateContact(resourceName=person["resourceName"], updatePersonFields="externalIds",
                               body={"etag": person["etag"], "externalIds": ext}).execute()
    time.sleep(0.7)  # stay under People API write quota


def cmd_google(ctx, args):
    from googleapiclient.errors import HttpError

    svc = google_service(args.writeback)
    pats = load_ignore(args.ignore_label)
    skipped = []
    page = None
    while True:
        r = svc.contactGroups().list(pageSize=1000, pageToken=page).execute()
        for g in r.get("contactGroups", []):
            if g.get("groupType") == "USER_CONTACT_GROUP":
                nm = g.get("formattedName") or g["name"]
                if ignored(nm, pats):
                    skipped.append(nm)
                else:
                    GROUP_NAMES[g["resourceName"]] = nm
        page = r.get("nextPageToken")
        if not page:
            break
    if skipped:
        print(f"Ignoring {len(skipped)} Google label(s): {', '.join(sorted(skipped))}")
    state = load_state()
    token = None if args.full else state.get("google_sync_token")
    try:
        people, next_token = fetch_google(svc, token)
    except HttpError as e:
        if token and (e.resp.status == 410 or b"SYNC_TOKEN" in (e.content or b"")):
            print("Google sync token expired; running a full sync.")
            token = None
            people, next_token = fetch_google(svc, None)
        else:
            raise
    full = token is None
    print(f"{'Full' if full else 'Incremental'} sync: {len(people)} Google contacts to process")

    seen = set()
    for p in people:
        seen.add(p["resourceName"])
        if p.get("metadata", {}).get("deleted"):
            mark_deleted(ctx, p["resourceName"])
            continue
        c = google_contact(p)
        try:
            rec = upsert(ctx, c)
            changed = ctx.actions and ctx.actions[-1]["action"] not in ("UNCHANGED",)
            if c.get("photo_url") and (changed or args.photos):
                try:
                    sync_photo(ctx, rec, c)
                except Exception as e:
                    ctx.log("ERROR", c["name"], f"photo: {str(e)[:180]}")
            if args.writeback and not ctx.dry and rec:
                writeback(svc, p, rec["id"])
        except Exception as e:  # keep going; report at the end
            ctx.log("ERROR", c["name"], str(e)[:200])

    if full and people:
        for rid in list(ctx.ix.by_key["google_id"]):
            if rid not in seen:
                mark_deleted(ctx, rid)

    if next_token and not ctx.dry and not ctx.stats["ERROR"]:
        state["google_sync_token"] = next_token
        save_state(state)
    elif ctx.stats["ERROR"]:
        print("Errors occurred, so the sync token was not advanced; the next run will retry these contacts.")


# --------------------------------------------------------------------------------------
# LinkedIn (Connections.csv from "Get a copy of your data")
# --------------------------------------------------------------------------------------
def read_linkedin(path):
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("First Name"))
    except StopIteration:
        sys.exit("Couldn't find the 'First Name,...' header row in the CSV.")
    return list(csv.DictReader(lines[start:]))


def cmd_linkedin(ctx, args):
    ctx.decisions = load_decisions(ctx, "linkedin")
    rows = read_linkedin(args.csv)
    print(f"{len(rows)} LinkedIn connections to process")
    for r in rows:
        url = norm_li(r.get("URL"))
        if not url:
            ctx.log("SKIP", f"{r.get('First Name', '')} {r.get('Last Name', '')}".strip(), "no profile URL")
            continue
        name = f"{(r.get('First Name') or '').strip()} {(r.get('Last Name') or '').strip()}".strip() or url
        c = {
            "source": "linkedin", "key": url, "name": name,
            "emails": union([norm_email(r.get("Email Address"))]), "phones": [],
            "company": (r.get("Company") or "").strip() or None,
            "title": (r.get("Position") or "").strip() or None,
            "extra": {"connected_on": (r.get("Connected On") or "").strip() or None},
        }
        c["hash"] = content_hash({**{k: c[k] for k in ("name", "emails", "company", "title")}, **c["extra"]})
        try:
            upsert(ctx, c)
        except Exception as e:
            ctx.log("ERROR", name, str(e)[:200])

    finish_review(ctx)

    msgs = args.messages or (Path(args.csv).parent / "messages.csv")
    if args.messages or Path(msgs).exists():
        cmd_li_messages(ctx, msgs)
    else:
        print("No messages.csv next to the connections file; skipping 'Last LinkedIn message'.")


def parse_msg_date(s):
    s = (s or "").replace(" UTC", "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def cmd_li_messages(ctx, path):
    """Set 'Last LinkedIn message' from messages.csv (latest message sent to or received from each person)."""
    if "last_li_msg" not in ctx.cu.fields:
        print(f"No '{FIELDS['last_li_msg']}' field on the list; skipping messages.csv.")
        return
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    # Contacts linked to LinkedIn, by URL and by (unique) normalized name as a fallback
    by_name, dup_names = {}, set()
    for url, tid in ctx.ix.by_key["linkedin_url"].items():
        n = norm_name(ctx.ix.by_id[tid]["name"])
        if n in by_name and by_name[n] != tid:
            dup_names.add(n)
        by_name[n] = tid
    latest = {}

    def bump(tid, dt):
        if tid and (tid not in latest or dt > latest[tid]):
            latest[tid] = dt

    for r in rows:
        dt = parse_msg_date(r.get("DATE"))
        if not dt:
            continue
        urls = re.findall(r"https?://[^\s,;]*linkedin\.com/in/[^\s,;]+",
                          f"{r.get('SENDER PROFILE URL', '')} {r.get('RECIPIENT PROFILE URLS', '')}")
        hit = False
        for u in urls:
            tid = ctx.ix.by_key["linkedin_url"].get(norm_li(u) or "")
            if tid:
                bump(tid, dt)
                hit = True
        if not hit:  # message URLs are sometimes opaque IDs; fall back to an unambiguous name match
            for nm in [r.get("FROM", "")] + re.split(r"[,;]", r.get("TO", "")):
                n = norm_name(nm)
                if n and n in by_name and n not in dup_names:
                    bump(by_name[n], dt)

    print(f"{len(rows)} messages read; {len(latest)} LinkedIn contacts have a latest message")
    for tid, dt in latest.items():
        rec = ctx.ix.by_id[tid]
        ms = int(dt.timestamp() * 1000)
        cur = rec["v"].get("last_li_msg")
        try:
            if cur and int(float(cur)) >= ms:
                continue
        except ValueError:
            pass
        try:
            ctx.cu.set_fields(tid, {"last_li_msg": ms})
            rec["v"]["last_li_msg"] = str(ms)
            ctx.log("MESSAGE", rec["name"], f"last LinkedIn message {dt:%Y-%m-%d}")
        except Exception as e:
            ctx.log("ERROR", rec["name"], str(e)[:200])


# --------------------------------------------------------------------------------------
# WhatsApp (JSON export from WA Extractor-style tools)
# --------------------------------------------------------------------------------------
def parse_wa_date(s):
    """'Wed Dec 31 2025 06:30:54 GMT-0800 (Pacific Standard Time)' or ISO -> datetime (aware) or None."""
    s = (s or "").strip()
    if not s:
        return None
    m = re.match(r"\w{3} (\w{3} \d{1,2} \d{4} \d{2}:\d{2}:\d{2}) GMT([+-]\d{4})", s)
    try:
        if m:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%b %d %Y %H:%M:%S %z")
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def cmd_whatsapp(ctx, args):
    missing = [FIELDS[k] for k in ("whatsapp", "whatsapp_hash") if k not in ctx.cu.fields]
    if missing:
        sys.exit(f"Add these fields to the list first (Text type): {', '.join(missing)}")
    ctx.decisions = load_decisions(ctx, "whatsapp")
    ctx.no_create, ctx.trust_names = args.no_create, args.trust_exact_names
    rows = json.loads(Path(args.json).read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = next((v for v in rows.values() if isinstance(v, list)), [])
    print(f"{len(rows)} WhatsApp contacts to process")
    latest = []
    for r in rows:
        phone = norm_phone(r.get("phone_number") or r.get("formatted_phone"))
        name = (r.get("saved_name") or r.get("public_name") or "").strip() or phone or "(no name)"
        if not phone:
            ctx.log("SKIP", name, "no valid phone number")
            continue
        if r.get("is_blocked"):
            ctx.log("SKIP", name, "blocked")
            continue
        if args.only_saved and not r.get("is_my_contact", True):
            ctx.log("SKIP", name, "not in your address book")
            continue
        c = {"source": "whatsapp", "key": phone, "name": name, "emails": [], "phones": [phone]}
        c["hash"] = content_hash({"name": name, "phone": phone})
        try:
            rec = upsert(ctx, c)
            dt = parse_wa_date(r.get("last_msg_date"))
            if rec and dt:
                latest.append((rec, dt))
        except Exception as e:
            ctx.log("ERROR", name, str(e)[:200])
    finish_review(ctx)

    if "last_wa_msg" not in ctx.cu.fields:
        print(f"No '{FIELDS['last_wa_msg']}' field on the list; skipping last-message dates.")
        return
    for rec, dt in latest:
        ms = int(dt.timestamp() * 1000)
        cur = rec["v"].get("last_wa_msg")
        try:
            if cur and int(float(cur)) >= ms:
                continue
        except ValueError:
            pass
        try:
            ctx.cu.set_fields(rec["id"], {"last_wa_msg": ms})
            rec["v"]["last_wa_msg"] = str(ms)
            ctx.log("MESSAGE", rec["name"], f"last WhatsApp message {dt:%Y-%m-%d}")
        except Exception as e:
            ctx.log("ERROR", rec["name"], str(e)[:200])


# --------------------------------------------------------------------------------------
# Merge two ClickUp contacts that are the same person
# --------------------------------------------------------------------------------------
def cmd_merge(ctx, args):
    s, l = ctx.ix.by_id.get(args.survivor), ctx.ix.by_id.get(args.loser)
    if not s or not l:
        sys.exit("Both task IDs must be active tasks in the list.")
    sv, lv = s["v"], l["v"]
    for kf in ("google_id", "linkedin_url", "whatsapp"):
        if sv.get(kf) and lv.get(kf) and sv[kf] != lv[kf]:
            sys.exit(f"Both tasks have different {FIELDS[kf]} values. Merge them in the source first "
                     f"(e.g. merge the two Google contacts), then re-run the import.")
    ch = {}
    for lk in ("groups", "sources"):
        merged = union(sv.get(lk) or [], lv.get(lk) or [])
        if merged != (sv.get(lk) or []):
            ch[lk] = merged
    for k in ("google_id", "google_link", "google_hash", "linkedin_url", "linkedin_hash", "whatsapp", "whatsapp_hash",
              "email", "company", "title") + EXTRA:
        if not sv.get(k) and lv.get(k):
            ch[k] = lv[k]
    emails = union(split_list(sv.get("emails")), split_list(lv.get("emails")))
    phones = union(split_list(sv.get("phones")), split_list(lv.get("phones")))
    if ", ".join(emails) != (sv.get("emails") or ""):
        ch["emails"] = ", ".join(emails)
    if ", ".join(phones) != (sv.get("phones") or ""):
        ch["phones"] = ", ".join(phones)
    if sv.get("status") != ACTIVE:
        ch["status"] = ACTIVE
    if sv.get("dup_of"):
        ch["dup_of"] = None

    ctx.cu.set_fields(s["id"], ch)
    ctx.cu.set_fields(l["id"], {"status": MERGED, "dup_of": task_url(s["id"])})
    try:
        ctx.cu.update_task(l["id"], archived=True)
        archived = True
    except RuntimeError as e:
        archived = False
        print(f"Couldn't archive the merged task automatically ({e}). Archive it in ClickUp.")
    ctx.log("MERGE", s["name"], f"absorbed '{l['name']}' {task_url(l['id'])}"
            + ("" if archived or ctx.dry else " (not archived)"))


# --------------------------------------------------------------------------------------
def cmd_check(cu, missing):
    print(f"Custom fields on list {cu.list_id}:")
    for f in cu.all_fields:
        print(f"  {f['name']:<20} {f['type']}")
    for key, name in FIELDS.items():
        mark = "ok " if key in cu.fields else ("MISSING (required)" if key in REQUIRED else "missing (optional)")
        print(f"  [{mark}] {name}")
    st = cu.fields.get("status")
    if st and st["type"] in ("drop_down", "labels"):
        have = {(o.get("name") or o.get("label") or "").strip().lower()
                for o in st.get("type_config", {}).get("options", [])}
        lacking = [o for o in STATUS_OPTIONS if o not in have]
        if lacking:
            print(f"  Dropdown '{st['name']}' needs these options: {', '.join(lacking)}")
            missing = missing + ["status options"]
    if "sources" in cu.fields:
        lacking = [x for x in SOURCE_LABEL.values() if x.lower() not in cu.label_options("sources")]
        if lacking:
            print(f"  Labels field '{FIELDS['sources']}' needs these options: {', '.join(lacking)}")
    print("Ready." if not missing else "Fix the items above, then run check again.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    g = sub.add_parser("google")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--full", action="store_true", help="ignore the sync token; also sweeps for deletions")
    g.add_argument("--writeback", action="store_true", help="store the ClickUp task id on each Google contact")
    g.add_argument("--photos", action="store_true", help="check photos on every contact, not just changed ones")
    g.add_argument("--ignore-label", action="append", default=[], metavar="PATTERN",
                   help='skip a Google label (repeatable, wildcards ok); permanent ones go in ignore_labels.txt')
    g.add_argument("--ignore-missing-labels", action="store_true",
                   help="don't report Google labels / sources that have no matching ClickUp option")
    li = sub.add_parser("linkedin")
    li.add_argument("csv")
    li.add_argument("--messages", help="path to messages.csv (default: next to the connections CSV)")
    li.add_argument("--ignore-missing-labels", action="store_true",
                    help="don't report sources that have no matching ClickUp option")
    li.add_argument("--dry-run", action="store_true")
    wa = sub.add_parser("whatsapp")
    wa.add_argument("json", help="WhatsApp contacts JSON export")
    wa.add_argument("--no-create", action="store_true",
                    help="only enrich existing contacts; don't create WhatsApp-only people")
    wa.add_argument("--only-saved", action="store_true", help="skip numbers not saved in your address book")
    wa.add_argument("--trust-exact-names", action="store_true",
                    help="auto-link when the name matches exactly one existing contact (no review)")
    wa.add_argument("--ignore-missing-labels", action="store_true",
                    help="don't report sources that have no matching ClickUp option")
    wa.add_argument("--dry-run", action="store_true")
    m = sub.add_parser("merge")
    m.add_argument("survivor")
    m.add_argument("loser")
    m.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token, list_id = os.environ.get("CLICKUP_TOKEN"), os.environ.get("CLICKUP_LIST_ID")
    if not token or not list_id:
        sys.exit("Set CLICKUP_TOKEN and CLICKUP_LIST_ID.")
    dry = getattr(args, "dry_run", False)
    cu = ClickUp(token, list_id, dry)
    missing = cu.load_fields()
    if args.cmd == "check":
        return cmd_check(cu, missing)
    if missing:
        sys.exit(f"Missing required custom fields: {', '.join(missing)}. Run `check`.")

    ctx = Ctx(cu, build_index(cu), dry)
    print(f"Indexed {len(ctx.ix.by_id)} existing ClickUp contacts")
    for k in ("emails", "phones", "company", "title"):
        if k not in cu.fields:
            print(f"NOTE: no '{FIELDS[k]}' field on the list, so {k} won't be synced.")
    {"google": cmd_google, "linkedin": cmd_linkedin, "whatsapp": cmd_whatsapp,
     "merge": cmd_merge}[args.cmd](ctx, args)

    if getattr(args, "ignore_missing_labels", False):
        ctx.unknown_sources.clear()
        ctx.unknown_groups.clear()
    if ctx.unknown_sources:
        print(f"\nAdd these options to the '{FIELDS['sources']}' field: {', '.join(sorted(ctx.unknown_sources))}")
    if ctx.unknown_groups:
        print("\nGoogle labels with no matching option in the ClickUp 'Groups' field (add them, then re-run):")
        for g, n in ctx.unknown_groups.most_common():
            print(f"  {g}  ({n} contacts)")
    print("\nSummary:", ", ".join(f"{k.lower()}={v}" for k, v in sorted(ctx.stats.items())) or "nothing to do")
    report = HERE / f"sync_report_{args.cmd}{'_dry' if dry else ''}_{datetime.now():%Y%m%d-%H%M%S}.json"
    report.write_text(json.dumps({"stats": ctx.stats, "actions": ctx.actions}, indent=2))
    print(f"Report: {report.name}")


if __name__ == "__main__":
    main()
