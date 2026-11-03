"""Relationships between People and Orgs.

Canonical store: the **Relationship data** custom field (JSON).

Derived view: a managed block at the **top of the description** (same section markdown as the old
layout) so ClickUp task links open in the side panel.

Legacy sources still read during migration:

- Managed description sections (**Relationships** / **Organizations** / **People**)
- The **Introduced by** task-link custom field

Every relationship is recorded on both tasks, with the inverse label on the other side.
"""
import json
import re

from .fields import INTRODUCED_BY_FIELD, task_url

SECTIONS = ("Relationships", "Organizations", "People")
HEADER_RE = re.compile(r"^\s*\*\*(%s)\*\*\s*$" % "|".join(SECTIONS), re.M)
TASK_ID_RE = re.compile(r"app\.clickup\.com/t/(?:\d+/)?([A-Za-z0-9_-]+)")
_URL = r"https://app\.clickup\.com/t/[^)\s]+"
ITEM_RE = re.compile(r"^\s+[-*+]\s+\[(.+?)\]\((%s)\)\s*(?:[—–-]+\s*(.*?))?\s*$" % _URL)
LINE_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s+\[(.+?)\]\((%s)\)\s*(?:[—–-]+\s*(.*?))?\s*$" % _URL)
GROUP_RE = re.compile(r"^\s*[-*+]\s+([^\[\]]+?)\s*:?\s*$")

PEOPLE, ORGS = "people", "orgs"
DATA_FIELD = "Relationship data"
INTRODUCED_BY_LABEL = "Introduced by"

# Description block so ClickUp task links open in the side panel (custom text fields can't).
# ATX headings (###) interrupt Markdown lists and stay left-aligned — unlike ==== lines (setext /
# list continuation) or raw HTML ClickUp may show literally.
DISPLAY_BLOCK_START = "###### ==== Do Not Change Between Lines"
DISPLAY_BLOCK_END = "###### ==== End Do Not Change Between Lines"
# Any boundary line: "Do Not Change" (any heading level / ==== prefix) or legacy pure ==== / <p>====.
# Must match hand-edited forms like "#### ==== Do Not Change…" or the constants above.
_MARKER_LINE = (
    r"(?:"
    r"[^\n]*Do Not Change[^\n]*"
    r"|"
    r"(?:<p>)?={4,}[^\n]*(?:</p>)?"
    r")"
)
MANAGED_BLOCK_RE = re.compile(
    r"^\s*" + _MARKER_LINE + r"\s*\n"
    r".*?"
    r"^\s*" + _MARKER_LINE + r"\s*(?:\n|$)",
    re.M | re.S | re.I,
)
MARKER_LINE_RE = re.compile(r"^\s*" + _MARKER_LINE + r"\s*$", re.M | re.I)
# Back-compat aliases used in tests / older call sites.
EQUALS_BLOCK_RE = MANAGED_BLOCK_RE
EQUALS_LINE_RE = MARKER_LINE_RE


def label(kind):
    """WORKS_AT / works at / Works-at -> 'Works at'."""
    words = kind.strip().replace("-", "_").replace(" ", "_").lower().split("_")
    return " ".join(w for w in words if w).capitalize()


_PERSON_INVERSE = {
    "PARENT_OF": "CHILD_OF", "GRANDPARENT_OF": "GRANDCHILD_OF", "STEPPARENT_OF": "STEPCHILD_OF",
    "PARENT_IN_LAW_OF": "CHILD_IN_LAW_OF", "AUNT_OR_UNCLE_OF": "NIECE_OR_NEPHEW_OF", "GODPARENT_OF": "GODCHILD_OF",
    "MANAGER_OF": "REPORTS_TO", "MENTOR_OF": "MENTEE_OF", "ADVISOR_OF": "ADVISEE_OF", "TEACHER_OF": "STUDENT_OF",
    "INTRODUCED": "INTRODUCED_BY", "REFERRED": "REFERRED_BY", "EMPLOYER_OF": "EMPLOYEE_OF",
}
_SYMMETRIC = ["SPOUSE_OF", "SIBLING_OF", "COUSIN_OF", "FRIEND_OF", "COLLEAGUE_OF", "CLASSMATE_OF", "PARTNER_OF",
              "RELATIVE_OF", "NEIGHBOR_OF"]
_ORG_SIDE = {
    "WORKS_AT": "EMPLOYS", "WORKED_AT": "EMPLOYED", "INTERNED_AT": "HOSTED_INTERN", "CONSULTS_FOR": "CLIENT_OF",
    "STUDIES_AT": "HAS_STUDENT", "STUDIED_AT": "HAS_ALUMNUS", "TEACHES_AT": "HAS_FACULTY", "TAUGHT_AT": "HAD_FACULTY",
    "BELONGS_TO": "HAS_MEMBER", "MEMBER_OF": "HAS_MEMBER", "WAS_MEMBER_OF": "HAD_MEMBER", "FOUNDED": "FOUNDED_BY",
    "CO_FOUNDED": "CO_FOUNDED_BY", "LEADS": "LED_BY", "ADVISES": "ADVISED_BY", "INVESTED_IN": "BACKED_BY",
    "ON_BOARD_OF": "HAS_BOARD_MEMBER", "VOLUNTEERS_AT": "HAS_VOLUNTEER", "CUSTOMER_OF": "SERVES",
}

PERSON_INVERSE = {}
for _a, _b in _PERSON_INVERSE.items():
    PERSON_INVERSE[label(_a).lower()], PERSON_INVERSE[label(_b).lower()] = label(_b), label(_a)
ORG_FROM_PERSON = {label(a).lower(): label(b) for a, b in _ORG_SIDE.items()}
PERSON_FROM_ORG = {}
for _a, _b in _ORG_SIDE.items():
    PERSON_FROM_ORG.setdefault(label(_b).lower(), label(_a))

SUGGESTIONS = {
    (PEOPLE, PEOPLE): sorted({label(x) for x in [*_PERSON_INVERSE, *_PERSON_INVERSE.values(), *_SYMMETRIC]}),
    (PEOPLE, ORGS): sorted({label(x) for x in _ORG_SIDE}),
    (ORGS, PEOPLE): sorted({label(x) for x in _ORG_SIDE.values()}),
}


def section_for(own_kind, other_kind):
    """The section on `own` that holds a link to `other`, or None if that pairing isn't supported."""
    return {(PEOPLE, PEOPLE): "Relationships", (PEOPLE, ORGS): "Organizations",
            (ORGS, PEOPLE): "People"}.get((own_kind, other_kind))


def inverse(lab, own_kind, other_kind):
    """The label the other task shows for this relationship. Unknown types read the same both ways."""
    key = lab.strip().lower()
    if own_kind == PEOPLE and other_kind == PEOPLE:
        return PERSON_INVERSE.get(key, lab.strip())
    if own_kind == PEOPLE:
        return ORG_FROM_PERSON.get(key, lab.strip())
    return PERSON_FROM_ORG.get(key, lab.strip())


def task_id(url):
    m = TASK_ID_RE.search(url or "")
    return m.group(1) if m else None


def parse(md):
    """Description -> (notes, [{section, label, name, target_id, note}], unparsed lines).

    Unparsed lines are text inside the managed sections that isn't a relationship; rewriting the
    description would drop them, so callers must not rewrite a description that has any.
    """
    md = md or ""
    heads = list(HEADER_RE.finditer(md))
    if not heads:
        return md.rstrip(), [], []
    lines, unparsed = [], []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(md)
        group, group_items = None, 0
        for ln in md[h.end():end].splitlines() + [None]:
            mi = ln is not None and ITEM_RE.match(ln)
            if mi and group:
                lines.append({"section": h.group(1), "label": group, "name": mi.group(1).strip(),
                              "target_id": task_id(mi.group(2)), "note": (mi.group(3) or "").strip()})
                group_items += 1
                continue
            if ln is not None and not ln.strip():
                continue
            if group and not group_items:
                unparsed.append(f"- {group}")
            group, group_items = None, 0
            if ln is None:
                break
            mm = LINE_RE.match(ln)
            if mm:
                lines.append({"section": h.group(1), "label": mm.group(1).strip(), "name": mm.group(2).strip(),
                              "target_id": task_id(mm.group(3)), "note": (mm.group(4) or "").strip()})
                continue
            mg = GROUP_RE.match(ln)
            if mg:
                group = mg.group(1).strip()
            else:
                unparsed.append(ln.strip())
    return md[:heads[0].start()].rstrip(), lines, unparsed


def split(md):
    """Description -> (notes, relationship lines)."""
    notes, lines, _ = parse(md)
    return notes, lines


def render(notes, lines):
    """Legacy description layout (migration / export fallback). Prefer encode_data for new writes."""
    parts = [notes.rstrip()] if notes and notes.strip() else []
    body = encode_display(lines)
    if body:
        parts.append(body)
    return "\n\n".join(parts)


def encode_display(lines):
    """Markdown relationship sections for the managed description block (no free-form notes)."""
    parts = []
    for section in SECTIONS:
        groups = {}
        for ln in lines or []:
            if ln.get("section") == section:
                groups.setdefault(ln["label"].lower(), [ln["label"], []])[1].append(ln)
        if not groups:
            continue
        out = []
        for key in sorted(groups):
            lab, items = groups[key]
            out.append(f"- {lab}")
            for ln in sorted(items, key=lambda x: (x.get("name") or "").lower()):
                name = ln.get("name") or ln.get("target_id") or ""
                out.append(f"    - [{name}]({task_url(ln['target_id'])})"
                           + (f" — {ln['note']}" if ln.get("note") else ""))
        parts.append(f"**{section}**\n" + "\n".join(out))
    return "\n\n".join(parts)


def strip_managed_blocks(md):
    """Remove managed relationship blocks (### markers and legacy ==== / <p> variants)."""
    text = md or ""
    while True:
        new, n = MANAGED_BLOCK_RE.subn("", text, count=1)
        if not n:
            break
        text = new
    text = MARKER_LINE_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


# Back-compat name.
strip_equals_blocks = strip_managed_blocks


def split_display_block(md):
    """Compatibility helper: strip managed blocks. Returns (None, remainder)."""
    return None, strip_managed_blocks(md)


def _display_block(body):
    """Wrap display markdown between ### markers (headings stay left-aligned after lists)."""
    return f"{DISPLAY_BLOCK_START}\n{body}\n{DISPLAY_BLOCK_END}"


def _notes_after_managed(description):
    """User notes below managed content: drop managed markers and legacy **Relationships** sections.

    Parseable relationship lines are omitted (they live inside the managed block via encode_display).
    Unparsed lines from those sections are kept so handwritten text is not destroyed.
    """
    rest = strip_managed_blocks(description or "")
    notes, _legacy, unparsed = parse(rest)
    parts = []
    if notes and notes.strip():
        parts.append(notes.rstrip())
    if unparsed:
        parts.append("\n".join(unparsed))
    return "\n\n".join(parts).rstrip()


def compose_description(lines, notes):
    """Managed relationship block at the top (when any edges), then user notes.

    Section headings (**Relationships** / **Organizations** / **People**) stay inside the markers.
    """
    notes = _notes_after_managed(notes or "")
    body = encode_display(lines)
    if not body:
        return notes
    block = _display_block(body)
    return f"{block}\n\n{notes}" if notes else block


def compose_description_over(description, lines):
    """Replace the managed block in a full description (idempotent; never stacks markers)."""
    notes = _notes_after_managed(description or "")
    return compose_description(lines, notes)


def key(ln):
    return (str(ln["target_id"]), ln["label"].strip().lower())


def upsert_line(md, section, lab, target_id, name, note, remove=False):
    """Add, update or remove one relationship line in a description. Returns (new description, changed)."""
    notes, lines = split(md)
    match = [ln for ln in lines if ln["section"] == section and key(ln) == (target_id, lab.strip().lower())]
    rest = [ln for ln in lines if ln not in match]
    if not remove:
        rest.append({"section": section, "label": lab.strip(), "name": name, "target_id": target_id,
                     "note": note if note is not None else (match[0]["note"] if match else "")})
    new = render(notes, rest)
    return new, new != render(notes, lines)


# ---- Relationship data (JSON) ------------------------------------------------------------
def encode_data(lines):
    """Canonical JSON for the Relationship data field."""
    items = []
    for ln in sorted(lines, key=lambda x: (x["label"].lower(), str(x["target_id"]))):
        tid = str(ln.get("target_id") or "").strip()
        lab = " ".join(str(ln.get("label") or "").split())
        if not tid or not lab:
            continue
        row = {"type": lab, "id": tid}
        note = " ".join(str(ln.get("note") or "").split())
        if note:
            row["note"] = note
        items.append(row)
    return json.dumps(items, ensure_ascii=False, separators=(",", ":"))


def decode_data(raw):
    """Parse Relationship data JSON -> list of {label, target_id, note, name?}."""
    if raw in (None, "", []):
        return []
    if isinstance(raw, list):
        data = raw
    else:
        text = str(raw).strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        tid = str(item.get("id") or item.get("target_id") or "").strip()
        lab = " ".join(str(item.get("type") or item.get("label") or "").split())
        if not tid or not lab:
            continue
        out.append({
            "label": lab, "target_id": tid,
            "note": " ".join(str(item.get("note") or "").split()),
            "name": " ".join(str(item.get("name") or "").split()),
        })
    return out


def introduced_by_lines(items):
    """ClickUp tasks-field value -> relationship lines labeled Introduced by."""
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        tid = str(item.get("id") or "").strip()
        if not tid:
            continue
        out.append({
            "label": INTRODUCED_BY_LABEL, "target_id": tid,
            "name": " ".join(str(item.get("name") or "").split()), "note": "",
        })
    return out


def merge_lines(*groups):
    """Union relationship lines by (target_id, label); first occurrence wins for name/note."""
    out, seen = [], set()
    for group in groups:
        for ln in group or []:
            k = key(ln)
            if not ln.get("target_id") or k in seen:
                continue
            seen.add(k)
            out.append(dict(ln))
    return out


def attach_sections(lines, own_kind, target_kind_of):
    """Fill section / drop edges that aren't allowed for this list pairing."""
    out = []
    for ln in lines:
        tkind = ln.get("target_list") or target_kind_of(ln["target_id"])
        section = section_for(own_kind, tkind) if tkind else ln.get("section")
        if not section and tkind:
            continue
        out.append(dict(ln, section=section or ln.get("section") or "Relationships",
                        target_list=tkind))
    return out


def field_value(task_or_cfs, field_name, fields=None):
    """Raw custom field value by display name from a ClickUp task or task_record custom_fields list."""
    name = field_name.strip().lower()
    if fields is not None:
        fid = next((f["id"] for f in fields if f["name"].strip().lower() == name), None)
        if not fid:
            return None
        cfs = task_or_cfs.get("custom_fields", []) if isinstance(task_or_cfs, dict) else task_or_cfs
        for cf in cfs:
            if cf.get("id") == fid:
                return cf.get("value")
        return None
    # task_record style: custom_fields carry name
    cfs = task_or_cfs.get("custom_fields", []) if isinstance(task_or_cfs, dict) else task_or_cfs
    for cf in cfs:
        if (cf.get("name") or "").strip().lower() == name:
            return cf.get("value")
        # entities/task live form uses id-only; callers should pass fields=
    return None


def load_lines(description, relationship_data_raw, introduced_by_raw=None):
    """Merge structured field, legacy description sections, and Introduced by into one line list.

    Prefers Relationship data when it is non-empty; otherwise uses description sections.
    Introduced by links are always unioned in. The managed display block is ignored for parsing.
    """
    structured = decode_data(relationship_data_raw)
    rest = strip_managed_blocks(description or "")
    _notes, desc_lines, unparsed = parse(rest)
    primary = structured if structured else desc_lines
    intro = introduced_by_lines(introduced_by_raw)
    return merge_lines(primary, intro), unparsed, bool(structured)


def notes_text(description, *, structured=False):
    """User notes below the managed display block (and above any legacy relationship sections)."""
    rest = strip_managed_blocks(description or "")
    notes, _, _ = parse(rest)
    return notes


def upsert_data(raw, lab, target_id, name, note, remove=False):
    """Add/update/remove one edge in Relationship data JSON. Returns (new_json, changed)."""
    lines = decode_data(raw)
    match = [ln for ln in lines if key(ln) == (str(target_id), lab.strip().lower())]
    rest = [ln for ln in lines if ln not in match]
    if not remove:
        rest.append({
            "label": lab.strip(), "target_id": str(target_id),
            "name": name or (match[0].get("name") if match else ""),
            "note": note if note is not None else (match[0].get("note") if match else ""),
        })
    new = encode_data(rest)
    return new, new != encode_data(lines)
