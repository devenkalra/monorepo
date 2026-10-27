"""Relationships stored in task descriptions, as written by the old create_relation.py / link_org.py.

A description ends with managed sections, each a bold heading followed by grouped lines:

    **Relationships**          person <-> person
    **Organizations**          on a person, links to orgs
    **People**                 on an org, links to people

    - Works at
        - [Google](https://app.clickup.com/t/86abc) — Staff SWE

Text above the first managed heading is the user's notes. Every relationship is recorded on both tasks,
with the inverse label on the other side.
"""
import re

from .fields import task_url

SECTIONS = ("Relationships", "Organizations", "People")
HEADER_RE = re.compile(r"^\s*\*\*(%s)\*\*\s*$" % "|".join(SECTIONS), re.M)
TASK_ID_RE = re.compile(r"app\.clickup\.com/t/(?:\d+/)?([A-Za-z0-9_-]+)")
_URL = r"https://app\.clickup\.com/t/[^)\s]+"
ITEM_RE = re.compile(r"^\s+[-*+]\s+\[(.+?)\]\((%s)\)\s*(?:[—–-]+\s*(.*?))?\s*$" % _URL)
LINE_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s+\[(.+?)\]\((%s)\)\s*(?:[—–-]+\s*(.*?))?\s*$" % _URL)
GROUP_RE = re.compile(r"^\s*[-*+]\s+([^\[\]]+?)\s*:?\s*$")

PEOPLE, ORGS = "people", "orgs"


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
    """Inverse of split, in the grouped layout the old scripts write."""
    parts = [notes.rstrip()] if notes and notes.strip() else []
    for section in SECTIONS:
        groups = {}
        for ln in lines:
            if ln["section"] == section:
                groups.setdefault(ln["label"].lower(), [ln["label"], []])[1].append(ln)
        if not groups:
            continue
        out = []
        for key in sorted(groups):
            lab, items = groups[key]
            out.append(f"- {lab}")
            for ln in sorted(items, key=lambda x: x["name"].lower()):
                out.append(f"    - [{ln['name']}]({task_url(ln['target_id'])})" + (f" — {ln['note']}" if ln["note"] else ""))
        parts.append(f"**{section}**\n" + "\n".join(out))
    return "\n\n".join(parts)


def key(ln):
    return (ln["target_id"], ln["label"].strip().lower())


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
