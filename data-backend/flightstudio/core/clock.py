"""Local time of day on a path: parse only, no simulator."""

from __future__ import annotations

import re

_TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::\d{2})?$")


def parse_time_of_day(value: str | None) -> tuple[int, int] | None:
    """Hour and minute in 24-hour local time, or None to leave the sim clock.

    Seconds, if present, are ignored: the sim's clock events are minute-resolution.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _TIME.fullmatch(text)
    if not match:
        raise ValueError(f"Time of day must be HH:MM, not {value!r}.")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError(f"Time of day must be HH:MM, not {value!r}.")
    return hour, minute
