"""WhatsApp contacts JSON export -> ClickUp."""
import json
import re
from datetime import datetime
from pathlib import Path

from ..errors import ConfigError
from ..fields import FIELDS
from ..normalize import content_hash, norm_phone
from ..sync import bump_date, upsert


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


def parse_export(text):
    rows = json.loads(text)
    if isinstance(rows, dict):
        rows = next((v for v in rows.values() if isinstance(v, list)), [])
    if not isinstance(rows, list):
        raise ConfigError("The WhatsApp export should be a JSON list of contacts.")
    return rows


def sniff_export(data):
    try:
        return len(parse_export(data.decode("utf-8-sig", errors="replace")))
    except ValueError as e:
        raise ConfigError(f"Not valid JSON: {e}")


def run_whatsapp(ctx, json_path, only_saved=False):
    missing = [FIELDS[k] for k in ("whatsapp", "whatsapp_hash") if k not in ctx.cu.fields]
    if missing:
        raise ConfigError(f"Add these fields to the list first (Text type): {', '.join(missing)}")
    rows = parse_export(Path(json_path).read_text(encoding="utf-8-sig"))
    ctx.log("INFO", "", f"{len(rows)} WhatsApp contacts to process")
    latest = []
    for i, r in enumerate(rows, 1):
        ctx.tick("Syncing contacts", i, len(rows))
        phone = norm_phone(r.get("phone_number") or r.get("formatted_phone"))
        name = (r.get("saved_name") or r.get("public_name") or "").strip() or phone or "(no name)"
        if not phone:
            ctx.log("SKIP", name, "no valid phone number")
            continue
        if r.get("is_blocked"):
            ctx.log("SKIP", name, "blocked")
            continue
        if only_saved and not r.get("is_my_contact", True):
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
            ctx.error(name, e)

    if "last_wa_msg" not in ctx.cu.fields:
        ctx.log("INFO", "", f"No '{FIELDS['last_wa_msg']}' field on the list; skipping last-message dates.")
        return
    for i, (rec, dt) in enumerate(latest, 1):
        ctx.tick("Updating last-message dates", i, len(latest))
        try:
            bump_date(ctx, rec, "last_wa_msg", int(dt.timestamp() * 1000), "MESSAGE",
                      f"last WhatsApp message {dt:%Y-%m-%d}")
        except Exception as e:
            ctx.error(rec["name"], e)
