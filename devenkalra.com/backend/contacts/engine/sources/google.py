"""Google Contacts (People API) -> ClickUp."""
import fnmatch
import hashlib
import re
import time

import requests

from ..errors import SafetyStop
from ..normalize import content_hash, norm_email, phone_for_storage, union
from ..sync import mark_deleted, upsert

PERSON_FIELDS = ("names,emailAddresses,phoneNumbers,organizations,externalIds,metadata,"
                 "birthdays,addresses,urls,memberships,photos")

# A full sync marks Google-linked contacts that Google no longer returns as deleted. If more than
# this share (or count) is missing, something is wrong with the fetch, not the address book.
DELETE_SWEEP_MAX_SHARE = 0.02
DELETE_SWEEP_MIN_LIMIT = 10
BATCH_GET_MAX = 200


def ignored(name, patterns):
    return any(fnmatch.fnmatchcase(name.lower(), p.lower()) for p in patterns)


def load_groups(svc, ignore_patterns):
    """contactGroups/xyz -> label name for user-created labels, minus ignored ones."""
    names, skipped, page = {}, [], None
    while True:
        r = svc.contactGroups().list(pageSize=1000, pageToken=page).execute()
        for g in r.get("contactGroups", []):
            if g.get("groupType") == "USER_CONTACT_GROUP":
                nm = g.get("formattedName") or g["name"]
                if ignored(nm, ignore_patterns):
                    skipped.append(nm)
                else:
                    names[g["resourceName"]] = nm
        page = r.get("nextPageToken")
        if not page:
            return names, sorted(skipped)


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


def fetch_people(svc, resource_names):
    """Fetch specific contacts by resourceName; ones Google no longer has are left out."""
    people = []
    for i in range(0, len(resource_names), BATCH_GET_MAX):
        resp = svc.people().getBatchGet(resourceNames=resource_names[i:i + BATCH_GET_MAX],
                                        personFields=PERSON_FIELDS).execute()
        people += [r["person"] for r in resp.get("responses", []) if r.get("person")]
    return people


def google_contact(p, group_names):
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
    c["groups"] = sorted({group_names[m["contactGroupMembership"]["contactGroupResourceName"]]
                          for m in p.get("memberships", [])
                          if m.get("contactGroupMembership", {}).get("contactGroupResourceName") in group_names})
    c["hash"] = content_hash({**{k: c[k] for k in ("name", "emails", "phones", "company", "title", "groups")},
                              **c["extra"], "photo": c["photo_url"]})
    return c


def sync_photo(ctx, rec, c):
    """Attach the Google photo as photo-<hash>.jpg unless that exact photo is already attached."""
    url = c.get("photo_url")
    if not url or not rec:
        return
    if ctx.dry:
        ctx.cu.upload(rec["id"], "(google photo)", None, None, task_name=rec["name"])
        ctx.log("PHOTO", rec["name"], "would attach Google photo", task_id=rec["id"])
        return
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    ext = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(mime, "jpg")
    fname = f"photo-{hashlib.sha1(r.content).hexdigest()[:10]}.{ext}"
    if fname in ctx.cu.attachment_names(rec["id"]):
        return
    ctx.cu.upload(rec["id"], fname, r.content, mime, task_name=rec["name"])
    ctx.log("PHOTO", rec["name"], fname, task_id=rec["id"])


def writeback(ctx, svc, person, rec):
    """Store the ClickUp task id on the Google contact (externalIds, type 'clickup')."""
    task_id = rec["id"]
    ext = person.get("externalIds", [])
    if any(e.get("type") == "clickup" and e.get("value") == task_id for e in ext):
        return
    handle = ctx.cu.guard.begin("google_writeback", task_id=task_id, task_name=rec["name"],
                                field="Google externalIds", before=ext, after=task_id)
    if handle is None:
        return
    kept = [{"type": e.get("type"), "value": e.get("value")} for e in ext if e.get("type") != "clickup"]
    try:
        svc.people().updateContact(resourceName=person["resourceName"], updatePersonFields="externalIds",
                                   body={"etag": person["etag"], "externalIds": kept + [
                                       {"type": "clickup", "value": task_id}]}).execute()
    except Exception as e:
        ctx.cu.guard.done(handle, error=str(e))
        raise
    ctx.cu.guard.done(handle)
    time.sleep(0.7)  # stay under People API write quota


def run_google(ctx, svc, *, sync_token=None, full=False, photos=False, do_writeback=False, ignore_patterns=(),
               revisit=()):
    """Returns the next sync token to store, or None if it must not advance.

    `revisit`: contacts decided in Review. An incremental sync only returns contacts changed since
    the last run, so decided ones that aren't linked to a task yet are fetched explicitly.
    """
    from googleapiclient.errors import HttpError

    ctx.tick("Reading Google labels", 0, 0)
    group_names, skipped = load_groups(svc, ignore_patterns)
    if skipped:
        ctx.log("INFO", "", f"Ignoring {len(skipped)} Google label(s): {', '.join(skipped)}")

    token = None if full else sync_token
    ctx.tick("Reading Google contacts", 0, 0)
    try:
        people, next_token = fetch_google(svc, token)
    except HttpError as e:
        if token and (e.resp.status == 410 or b"SYNC_TOKEN" in (e.content or b"")):
            ctx.log("INFO", "", "Google sync token expired; running a full sync.")
            token = None
            people, next_token = fetch_google(svc, None)
        else:
            raise
    is_full = token is None
    returned = {p["resourceName"] for p in people}
    reviewed = [rid for rid in revisit
                if rid.startswith("people/") and rid not in returned and not ctx.ix.get_key("google_id", rid)]
    if reviewed:
        people += fetch_people(svc, reviewed)
        ctx.log("INFO", "", f"Re-reading {len(reviewed)} Google contact(s) decided in Review")
    ctx.log("INFO", "", f"{'Full' if is_full else 'Incremental'} sync: {len(people)} Google contacts to process")

    seen = set()
    total = len(people)
    for i, p in enumerate(people, 1):
        ctx.tick("Syncing contacts", i, total)
        seen.add(p["resourceName"])
        if p.get("metadata", {}).get("deleted"):
            try:
                mark_deleted(ctx, p["resourceName"])
            except Exception as e:
                ctx.error(p["resourceName"], e)
            continue
        c = google_contact(p, group_names)
        try:
            n_before = len(ctx.actions)
            rec = upsert(ctx, c)
            changed = any(a["action"] != "UNCHANGED" for a in ctx.actions[n_before:])
            if c.get("photo_url") and (changed or photos):
                try:
                    sync_photo(ctx, rec, c)
                except SafetyStop:
                    raise
                except Exception as e:
                    ctx.log("ERROR", c["name"], f"photo: {str(e)[:180]}")
            if do_writeback and rec:
                writeback(ctx, svc, p, rec)
        except Exception as e:
            ctx.error(c["name"], e)

    if is_full and people:
        missing = [rid for rid in list(ctx.ix.by_key["google_id"]) if rid not in seen]
        limit = max(DELETE_SWEEP_MIN_LIMIT, int(len(ctx.ix.by_key["google_id"]) * DELETE_SWEEP_MAX_SHARE))
        if len(missing) > limit:
            ctx.warn(f"{len(missing)} Google-linked contacts weren't returned by Google. That's more than the "
                     f"safety limit of {limit}, so none were marked deleted. Check Google Contacts.")
        else:
            for rid in missing:
                try:
                    mark_deleted(ctx, rid)
                except Exception as e:
                    ctx.error(rid, e)

    if ctx.dry or ctx.stats["ERROR"]:
        if ctx.stats["ERROR"] and not ctx.dry:
            ctx.warn("Errors occurred, so the Google sync token was not advanced; the next run retries them.")
        return None
    return next_token
