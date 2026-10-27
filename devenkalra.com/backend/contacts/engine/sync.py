"""Matching and upsert of source contacts into the ClickUp Contacts list."""
import difflib
import time
from collections import Counter

from .errors import ProtectionViolation, SafetyStop, TooManyErrors
from .fields import (ACTIVE, DELETED, EXTRA, FIELDS, HASH, KEY, MERGED, NAME_STRONG, NAME_WITH_COMPANY, REVIEW,
                     SOURCE_LABEL, task_url)
from .normalize import norm_company, norm_email, norm_name, norm_phone, phone_for_storage, split_list, union


def now_ms():
    return int(time.time() * 1000)


class Reporter:
    """Receives progress from a run. The CLI prints; the web runner stores to the database."""

    def action(self, entry):
        pass

    def progress(self, phase, done=0, total=0):
        pass

    def check_cancel(self):
        pass


class SyncContext:
    def __init__(self, cu, ix, *, reporter=None, decisions=None, hold_review=False, no_create=False,
                 trust_names=False, rename_tasks=False, overwrite_values=True, max_errors=25):
        self.cu, self.ix = cu, ix
        self.dry = cu.dry
        self.reporter = reporter or Reporter()
        self.decisions = decisions or {}
        self.hold_review = hold_review
        self.no_create = no_create
        self.trust_names = trust_names
        self.rename_tasks = rename_tasks
        self.overwrite_values = overwrite_values
        self.max_errors = max_errors
        self.stats, self.actions = Counter(), []
        self.unknown_groups = Counter()
        self.unknown_sources = set()
        self.review_rows = []
        self.warnings = list(ix.warnings)

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
        if not self.dry and self.stats["ERROR"] > self.max_errors:
            raise TooManyErrors(f"Stopped after {self.stats['ERROR']} errors.")

    def tick(self, phase, done, total):
        self.reporter.progress(phase, done, total)
        self.reporter.check_cancel()

    def write_fields(self, rec, changes, allow_clear=()):
        self.cu.set_fields(rec["id"], changes, before=rec["v"], task_name=rec["name"], allow_clear=allow_clear)


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


def _review_row(c, match, note=""):
    return {"name": c["name"], "company": c.get("company") or "", "title": c.get("title") or "",
            "key": c["key"], "suggested_task_id": match["id"], "suggested_task_name": match["name"], "note": note}


def upsert(ctx, c):
    kf = KEY[c["source"]]
    rec = ctx.ix.get_key(kf, c["key"])
    if rec:
        return update(ctx, rec, c, "key")
    match, how = find_existing(ctx.ix, c)
    if how == "fuzzy":
        if not ctx.hold_review:
            return create(ctx, c, REVIEW, dup=match)
        if ctx.trust_names and norm_name(c["name"]) == norm_name(match["name"]) and not match["v"].get(kf):
            same_name = [r for r in ctx.ix.by_id.values() if norm_name(r["name"]) == norm_name(c["name"])]
            if len(same_name) == 1:
                return update(ctx, match, c, "name")
        d = ctx.decisions.get(c["key"])
        if d and d["decision"] == "same":
            target = ctx.ix.by_id.get(d.get("task_id") or match["id"])
            if target and not target["v"].get(kf):
                return update(ctx, target, c, "review")
            if target:
                note = (f"Marked 'same' earlier, but '{target['name']}' is already linked to "
                        f"{target['v'][kf]}. Linking would replace it, so decide again.")
            else:
                note = "Marked 'same' earlier, but that task no longer exists. Decide again."
            ctx.log("PENDING", c["name"], note, task_id=match["id"])
            ctx.review_rows.append(_review_row(c, match, note))
            return None
        if d and d["decision"] == "new":
            return create_or_skip(ctx, c)
        ctx.review_rows.append(_review_row(c, match))
        ctx.log("PENDING", c["name"], f"maybe '{match['name']}'; decide in Review", task_id=match["id"])
        return None
    if match:
        return update(ctx, match, c, how)
    return create_or_skip(ctx, c)


def create_or_skip(ctx, c):
    if ctx.no_create:
        ctx.log("SKIP", c["name"], "no matching contact (creating new contacts is off)")
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
        ctx.log("REVIEW", c["name"], f"possible duplicate of '{dup['name']}'", task_id=dup["id"])
    else:
        ctx.log("CREATE", c["name"], c["key"], task_id=task["id"])
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
        ctx.log("UNCHANGED", rec["name"], task_id=rec["id"])
        return rec

    ch = {}
    if how != "key":
        ch[kf] = c["key"]
    if c.get("link") and v.get("google_link") != c["link"]:
        ch["google_link"] = c["link"]

    # Entries that don't parse as emails are kept as typed rather than dropped.
    emails = union([norm_email(e) or e for e in split_list(v.get("emails"))], c["emails"])
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
        if new and (not v.get(f) or (ctx.overwrite_values and owner and v.get(f) != new)):
            ch[f] = new

    for k, val in extra.items():
        if val is None or str(v.get(k)) == str(val):
            continue
        if v.get(k) not in (None, "") and not ctx.overwrite_values:
            continue
        ch[k] = val
    if new_groups:
        ch["groups"] = (v.get("groups") or []) + new_groups
    if new_sources:
        ch["sources"] = (v.get("sources") or []) + new_sources

    ch[hf] = c["hash"]
    ch["last_synced"] = now_ms()
    if v.get("status") in (None, DELETED):
        ch["status"] = ACTIVE

    rename = ctx.rename_tasks and src == "google" and c["name"] and c["name"] != rec["name"]
    if rename:
        ctx.cu.update_task(rec["id"], task_name=rec["name"], before=rec["name"], name=c["name"])
    ctx.write_fields(rec, ch)

    old_name = rec["name"]
    if rename:
        rec["name"] = c["name"]
    v.update(ch)
    ctx.ix.add(rec)
    label = "UPDATE" if how == "key" else f"LINK({how})"
    detail = ", ".join(FIELDS[k] for k in ch if k not in ("last_synced", hf))
    if rename:
        detail = f"renamed from '{old_name}'; " + detail
    ctx.log(label, rec["name"], detail, task_id=rec["id"])
    return rec


def mark_deleted(ctx, rid):
    rec = ctx.ix.get_key("google_id", rid)
    if not rec or rec["v"].get("status") in (DELETED, MERGED):
        return
    ctx.write_fields(rec, {"status": DELETED})
    rec["v"]["status"] = DELETED
    ctx.log("DELETED", rec["name"], f"{rid} no longer in Google", task_id=rec["id"])


def bump_date(ctx, rec, key, ms, action, detail):
    """Set a last-message date only if it moves forward."""
    cur = rec["v"].get(key)
    try:
        if cur and int(float(cur)) >= ms:
            return
    except ValueError:
        pass
    ctx.write_fields(rec, {key: ms})
    rec["v"][key] = str(ms)
    ctx.log(action, rec["name"], detail, task_id=rec["id"])


def merge(ctx, survivor_id, loser_id):
    """Fold the loser task into the survivor, mark the loser merged and archive it."""
    s, l = ctx.ix.by_id.get(survivor_id), ctx.ix.by_id.get(loser_id)
    if not s or not l or survivor_id == loser_id:
        raise ProtectionViolation("Both task IDs must be different active tasks in the list.")
    sv, lv = s["v"], l["v"]
    if MERGED in (sv.get("status"), lv.get("status")):
        raise ProtectionViolation("One of these tasks is already merged.")
    # The loser's Google contact is gone, so its Google ID is dead and must not block or be copied.
    dead_google = lv.get("status") == DELETED
    for kf in KEY.values():
        if kf == "google_id" and dead_google:
            continue
        if sv.get(kf) and lv.get(kf) and sv[kf] != lv[kf]:
            raise ProtectionViolation(
                f"Both tasks have different {FIELDS[kf]} values. Merge them in the source first "
                f"(e.g. merge the two Google contacts), then re-run the import.")
    ch = {}
    for lk in ("groups", "sources"):
        merged = union(sv.get(lk) or [], lv.get(lk) or [])
        if merged != (sv.get(lk) or []):
            ch[lk] = merged
    copied = ("google_id", "google_link", "google_hash", "linkedin_url", "linkedin_hash", "whatsapp",
              "whatsapp_hash", "email", "company", "title") + EXTRA
    for k in copied:
        if dead_google and k.startswith("google_"):
            continue
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
    allow_clear = ()
    if sv.get("dup_of"):
        ch["dup_of"] = None
        allow_clear = ("dup_of",)

    ctx.write_fields(s, ch, allow_clear=allow_clear)
    sv.update(ch)
    ctx.write_fields(l, {"status": MERGED, "dup_of": task_url(s["id"])})
    lv.update({"status": MERGED, "dup_of": task_url(s["id"])})
    try:
        ctx.cu.update_task(l["id"], task_name=l["name"], before={"archived": False}, archived=True)
        archived = True
    except SafetyStop:
        raise
    except RuntimeError as e:
        archived = False
        ctx.warn(f"Couldn't archive the merged task automatically ({e}). Archive it in ClickUp.")
    ctx.log("MERGE", s["name"], f"absorbed '{l['name']}' {task_url(l['id'])}"
            + ("" if archived or ctx.dry else " (not archived)"), task_id=s["id"])
