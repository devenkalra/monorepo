"""LinkedIn data export (Connections.csv, messages.csv) -> ClickUp."""
import csv
import io
import re
from datetime import datetime
from pathlib import Path

from ..errors import ConfigError
from ..fields import FIELDS
from ..normalize import content_hash, norm_email, norm_li, norm_name, union
from ..sync import bump_date, upsert


def read_connections(path):
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("First Name"))
    except StopIteration:
        raise ConfigError("Couldn't find the 'First Name,...' header row in the connections CSV.")
    return list(csv.DictReader(lines[start:]))


def read_messages(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if rows and "DATE" not in rows[0]:
        raise ConfigError("messages.csv has no DATE column; is this the LinkedIn messages export?")
    return rows


def linkedin_contact(r):
    url = norm_li(r.get("URL"))
    name = f"{(r.get('First Name') or '').strip()} {(r.get('Last Name') or '').strip()}".strip() or url or "(no name)"
    if not url:
        return None, name
    c = {
        "source": "linkedin", "key": url, "name": name,
        "emails": union([norm_email(r.get("Email Address"))]), "phones": [],
        "company": (r.get("Company") or "").strip() or None,
        "title": (r.get("Position") or "").strip() or None,
        "extra": {"connected_on": (r.get("Connected On") or "").strip() or None},
    }
    c["hash"] = content_hash({**{k: c[k] for k in ("name", "emails", "company", "title")}, **c["extra"]})
    return c, name


def run_linkedin(ctx, connections_path, messages_path=None):
    rows = read_connections(connections_path)
    ctx.log("INFO", "", f"{len(rows)} LinkedIn connections to process")
    for i, r in enumerate(rows, 1):
        ctx.tick("Syncing connections", i, len(rows))
        c, name = linkedin_contact(r)
        if not c:
            ctx.log("SKIP", name, "no profile URL")
            continue
        try:
            upsert(ctx, c)
        except Exception as e:
            ctx.error(name, e)
    if messages_path:
        run_li_messages(ctx, messages_path)


def parse_msg_date(s):
    s = (s or "").replace(" UTC", "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def run_li_messages(ctx, path):
    """Set 'Last LinkedIn message' from messages.csv (latest message sent to or received from each person)."""
    if "last_li_msg" not in ctx.cu.fields:
        ctx.log("INFO", "", f"No '{FIELDS['last_li_msg']}' field on the list; skipping messages.csv.")
        return
    rows = read_messages(path)
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

    ctx.log("INFO", "", f"{len(rows)} messages read; {len(latest)} LinkedIn contacts have a latest message")
    for i, (tid, dt) in enumerate(latest.items(), 1):
        ctx.tick("Updating last-message dates", i, len(latest))
        rec = ctx.ix.by_id[tid]
        try:
            bump_date(ctx, rec, "last_li_msg", int(dt.timestamp() * 1000), "MESSAGE",
                      f"last LinkedIn message {dt:%Y-%m-%d}")
        except Exception as e:
            ctx.error(rec["name"], e)


def sniff_connections(data):
    """Row count for an uploaded connections CSV (raises ConfigError if it isn't one)."""
    lines = data.decode("utf-8-sig", errors="replace").splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("First Name"))
    except StopIteration:
        raise ConfigError("This doesn't look like LinkedIn's Connections.csv (no 'First Name' header row).")
    return sum(1 for _ in csv.DictReader(lines[start:]))


def sniff_messages(data):
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig", errors="replace"))))
    if rows and "DATE" not in rows[0]:
        raise ConfigError("This doesn't look like LinkedIn's messages.csv (no DATE column).")
    return len(rows)
