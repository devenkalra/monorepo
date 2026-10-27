"""Normalization used for matching contacts across sources."""
import hashlib
import json
import os
import re
import unicodedata

import phonenumbers

DEFAULT_REGION = os.environ.get("CONTACTS_DEFAULT_REGION") or os.environ.get("DEFAULT_REGION") or "US"


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
    if isinstance(s, (list, tuple)):
        return [str(x).strip() for x in s if str(x).strip()]
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
