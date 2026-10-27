"""Write guard: the single gate every ClickUp (and Google) write goes through.

Layers, in order:
  1. Dry runs count the write and stop there; nothing is sent.
  2. Live writes require the server-wide switch (CONTACTS_CLICKUP_WRITES_ENABLED).
  3. A live run may not exceed its write budget (derived from the dry-run plan it applies).
  4. Field changes may only add information: no clearing values, no dropping emails/phones/labels,
     no replacing an existing source key, no un-merging, no moving last-message dates backwards.
  5. Every live write is journaled (before/after) before it is sent.
"""
from .errors import DryRunViolation, ProtectionViolation, WriteBudgetExceeded, WritesDisabled
from .fields import FIELDS, KEY_FIELDS, LABEL_FIELDS, LIST_FIELDS, MERGED, MONOTONIC_DATE_FIELDS
from .normalize import norm_email, norm_li, norm_phone, split_list

ALLOWED_TASK_KEYS = {"name", "archived"}


def _empty(v):
    return v is None or v == "" or v == [] or v == ()


def _norm_key(field, v):
    v = str(v or "").strip()
    if field == "linkedin_url":
        return norm_li(v) or v.lower()
    if field == "whatsapp":
        return norm_phone(v) or v
    return v


def _norm_items(field, v):
    if field == "emails":
        return {norm_email(x) or x.lower() for x in split_list(v)}
    if field == "phones":
        return {norm_phone(x) or x for x in split_list(v)}
    return {str(x).strip().lower() for x in (v or [])}


def _as_ms(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def check_field_changes(before, changes, allow_clear=()):
    """Raise ProtectionViolation if `changes` would remove or replace existing ClickUp data."""
    for key, new in changes.items():
        if key not in FIELDS:
            raise ProtectionViolation(f"Refusing to write unknown field {key!r}")
        old = before.get(key)
        if _empty(new):
            if not _empty(old) and key not in allow_clear:
                raise ProtectionViolation(f"Refusing to clear {FIELDS[key]} (currently {old!r})")
            continue
        if _empty(old):
            continue
        if key in KEY_FIELDS and _norm_key(key, old) != _norm_key(key, new):
            raise ProtectionViolation(f"Refusing to replace {FIELDS[key]} {old!r} with {new!r}")
        if key in LIST_FIELDS + LABEL_FIELDS:
            lost = _norm_items(key, old) - _norm_items(key, new)
            if lost:
                raise ProtectionViolation(f"Refusing to drop {FIELDS[key]}: {', '.join(sorted(lost))}")
        if key == "status" and str(old).lower() == MERGED and str(new).lower() != MERGED:
            raise ProtectionViolation("Refusing to change the status of a merged contact")
        if key in MONOTONIC_DATE_FIELDS:
            o, n = _as_ms(old), _as_ms(new)
            if o is not None and n is not None and n < o:
                raise ProtectionViolation(f"Refusing to move {FIELDS[key]} backwards")


class WriteGuard:
    def __init__(self, *, dry, writes_enabled=False, max_ops=None, journal=None):
        self.dry = dry
        self.writes_enabled = writes_enabled
        self.max_ops = max_ops
        self.ops = 0
        self._journal = journal

    def begin(self, op, *, task_id, task_name="", field="", before=None, after=None):
        """Count one write. Returns None for dry runs (caller must not send), else a journal handle."""
        self.ops += 1
        if self.dry:
            return None
        if not self.writes_enabled:
            raise WritesDisabled("Live ClickUp writes are disabled (CONTACTS_CLICKUP_WRITES_ENABLED).")
        if self.max_ops is None:
            raise WriteBudgetExceeded("Live runs need a write budget.")
        if self.ops > self.max_ops:
            raise WriteBudgetExceeded(
                f"Stopped after {self.max_ops} writes: this run is doing more than its dry-run plan allowed.")
        if str(task_id).startswith("dry-run"):
            raise DryRunViolation(f"Refusing to write to placeholder task {task_id}")
        if self._journal:
            return self._journal.record(op=op, task_id=str(task_id), task_name=task_name, field=field,
                                        before=before, after=after)
        return True

    def done(self, handle, error=None):
        if self._journal and handle is not None and handle is not True:
            self._journal.finish(handle, error)

    def assert_live(self, what):
        """Last line of defence inside the HTTP layer."""
        if self.dry:
            raise DryRunViolation(f"Dry run attempted a write: {what}")
        if not self.writes_enabled:
            raise WritesDisabled(f"Live writes are disabled: {what}")
