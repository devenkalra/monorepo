"""Convert a natural-language mail request into a Gmail search query.

Rule-based (no LLM) so listing mail stays fast and deterministic.
Optional UI qualifiers (start/end date, days, keyword) are merged in.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

# Filler phrases stripped before parsing.
_FILLER_RE = re.compile(
    r"\b("
    r"find|get|show|list|search|fetch|pull|"
    r"emails?|mails?|messages?|"
    r"please|for\s+me"
    r")\b",
    re.IGNORECASE,
)

_INBOX_RE = re.compile(r"\bin\s+inbox\b|\binbox\b", re.IGNORECASE)
_LAST_DAY_RE = re.compile(
    r"\b(?:last|past|previous)\s+day\b|\btoday\b|\blast\s+24\s*hours?\b",
    re.IGNORECASE,
)
_LAST_N_DAYS_RE = re.compile(
    r"\b(?:last|past|previous)\s+(\d+)\s+days?\b", re.IGNORECASE
)
_LAST_N_HOURS_RE = re.compile(
    r"\b(?:last|past|previous)\s+(\d+)\s+hours?\b", re.IGNORECASE
)
# Negative lookahead avoids "from the last day" (time window, not sender).
_FROM_BLOCK_RE = re.compile(
    r"\bfrom\s+(?!the\s+(?:last|past|previous)\b)(?!today\b)"
    r"(.+?)(?=\s+\bin\b|\s+\blast\b|\s+\bpast\b|\s+\btoday\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_SPLIT_SENDERS_RE = re.compile(r"\s*(?:,|;|\band\b|&)\s*", re.IGNORECASE)
_TIME_CLAUSE_RE = re.compile(
    r"\b(?:newer_than|older_than|after|before):\S+",
    re.IGNORECASE,
)


def _quote_from_term(name: str) -> str:
    name = name.strip().strip("\"'")
    if not name:
        return ""
    # Bare domain / single token — from:token works; multi-word needs quotes.
    if re.fullmatch(r"[\w.\-+@]+", name):
        return f"from:{name}"
    return f'from:"{name}"'


def _extract_senders(text: str) -> list[str]:
    match = _FROM_BLOCK_RE.search(text)
    if not match:
        return []
    block = match.group(1).strip()
    # Drop trailing junk like "emails" if still present.
    block = re.sub(r"\b(emails?|mails?|messages?)\b", "", block, flags=re.I).strip()
    parts = [p.strip(" \"'") for p in _SPLIT_SENDERS_RE.split(block) if p.strip()]
    return [p for p in parts if p]


def _parse_date(value: str | date | datetime | None) -> str | None:
    """Return Gmail ``YYYY/MM/DD`` or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().strftime("%Y/%m/%d")
    if isinstance(value, date):
        return value.strftime("%Y/%m/%d")
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().strftime("%Y/%m/%d")
        except ValueError:
            continue
    raise ValueError(f"Invalid date: {text!r} (use YYYY-MM-DD)")


def _quote_keyword(keyword: str) -> str:
    kw = keyword.strip()
    if not kw:
        return ""
    if (kw.startswith('"') and kw.endswith('"')) or " " not in kw:
        return kw
    return f'"{kw}"'


def _strip_time_clauses(query: str) -> str:
    return re.sub(r"\s+", " ", _TIME_CLAUSE_RE.sub(" ", query)).strip()


def apply_search_qualifiers(
    query: str,
    *,
    start_date: str | date | datetime | None = None,
    end_date: str | date | datetime | None = None,
    days: int | str | None = None,
    keyword: str | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Merge UI qualifiers into an existing Gmail query string."""
    notes = list(notes or [])
    clauses: list[str] = []
    base = (query or "").strip()

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    days_n: int | None = None
    if days is not None and str(days).strip() != "":
        try:
            days_n = int(days)
        except (TypeError, ValueError) as exc:
            raise ValueError("days must be an integer") from exc
        if days_n < 1:
            raise ValueError("days must be >= 1")

    has_time_qualifier = bool(start or end or days_n)
    if has_time_qualifier and base:
        stripped = _strip_time_clauses(base)
        if stripped != base:
            notes.append("qualifier dates override NL time window")
        base = stripped

    if base:
        clauses.append(base)

    if days_n is not None:
        clauses.append(f"newer_than:{days_n}d")
        notes.append(f"qualifier days -> newer_than:{days_n}d")
    if start:
        clauses.append(f"after:{start}")
        notes.append(f"qualifier start -> after:{start}")
    if end:
        clauses.append(f"before:{end}")
        notes.append(f"qualifier end -> before:{end}")

    kw = _quote_keyword(keyword or "")
    if kw:
        clauses.append(kw)
        notes.append("qualifier keyword")

    if not clauses:
        clauses.append("in:inbox")
        notes.append("default in:inbox")

    return {"query": " ".join(clauses), "notes": notes}


def nl_to_gmail_query(
    prompt: str,
    *,
    start_date: str | date | datetime | None = None,
    end_date: str | date | datetime | None = None,
    days: int | str | None = None,
    keyword: str | None = None,
) -> dict[str, Any]:
    """Return ``{query, notes}`` from a natural-language prompt + qualifiers.

    If the prompt already looks like a raw Gmail query (starts with ``q:`` or
    contains Gmail operators as the whole string), it is used mostly as-is.
    Qualifiers are always merged afterward.
    """
    raw = (prompt or "").strip()
    notes: list[str] = []
    query = ""

    if not raw:
        notes.append("empty prompt")
    elif raw.lower().startswith("q:"):
        query = raw[2:].strip()
        notes.append("raw q: query")
    elif re.search(
        r"\b(in:|from:|to:|subject:|newer_than:|older_than:|after:|before:|label:)\S",
        raw,
        re.I,
    ) and not re.search(r"\b(find|get|show|list)\b", raw, re.I):
        query = raw
        notes.append("passed through as Gmail operators")
    else:
        text = raw
        clauses: list[str] = []

        if _INBOX_RE.search(text):
            clauses.append("in:inbox")
            notes.append("in:inbox")
            text = _INBOX_RE.sub(" ", text)

        hours = _LAST_N_HOURS_RE.search(text)
        day_match = _LAST_N_DAYS_RE.search(text)
        if hours:
            n = max(1, int(hours.group(1)))
            clauses.append(f"newer_than:{n}h")
            notes.append(f"newer_than:{n}h")
            text = _LAST_N_HOURS_RE.sub(" ", text)
        elif day_match:
            n = max(1, int(day_match.group(1)))
            clauses.append(f"newer_than:{n}d")
            notes.append(f"newer_than:{n}d")
            text = _LAST_N_DAYS_RE.sub(" ", text)
        elif _LAST_DAY_RE.search(text):
            clauses.append("newer_than:1d")
            notes.append("newer_than:1d")
            text = _LAST_DAY_RE.sub(" ", text)

        senders = _extract_senders(raw)
        if senders:
            from_parts = [_quote_from_term(s) for s in senders]
            from_parts = [p for p in from_parts if p]
            if from_parts:
                if len(from_parts) == 1:
                    clauses.append(from_parts[0])
                else:
                    clauses.append("(" + " OR ".join(from_parts) + ")")
                notes.append(f"{len(from_parts)} from: term(s)")
            text = _FROM_BLOCK_RE.sub(" ", text)

        # Leftover free text → subject/body search terms (AND).
        leftover = _FILLER_RE.sub(" ", text)
        leftover = re.sub(r"\s+", " ", leftover).strip(" ,.;")
        stop = {
            "and",
            "or",
            "from",
            "the",
            "a",
            "an",
            "to",
            "of",
            "in",
            "on",
            "for",
            "with",
            "me",
        }
        if leftover and len(leftover) > 1:
            tokens = [
                t
                for t in re.split(r"\s+", leftover)
                if t and t.lower() not in stop
            ]
            # Only use free text when we did not already resolve structured clauses
            # from/senders/time — avoids leftovers like "from the" after "last day".
            if tokens and not senders and len(clauses) <= 1:
                clauses.append(" ".join(tokens))
                notes.append("free-text terms")

        if not clauses:
            clauses.append("in:inbox")
            notes.append("default in:inbox")

        query = " ".join(clauses)

    return apply_search_qualifiers(
        query,
        start_date=start_date,
        end_date=end_date,
        days=days,
        keyword=keyword,
        notes=notes,
    )
