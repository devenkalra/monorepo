#!/usr/bin/env python3
"""
link_org.py - connect a person (Contacts list) to an organization (Orgs list), on BOTH records.

  python link_org.py "Hakan Ancin" WORKS_AT "Google" --note "Staff SWE, since 2019"
      Hakan:   **Organizations**  - Works at [Google](...) — Staff SWE, since 2019
      Google:  **People**         - Employs [Hakan Ancin](...) — Staff SWE, since 2019
  python link_org.py "Reeta Sharma" STUDIED_AT "Caltech" --note "BS '05"
  python link_org.py "Mei Lin" BELONGS_TO "Shoreline Flying Club" --create   (creates the org if missing)
  python link_org.py "Mei Lin" COACHES/COACHED_BY "Palo Alto Robotics"        (new type, with org-side label)
  python link_org.py "Hakan Ancin" WORKS_AT "Google" --remove
  python link_org.py --types

Any TYPE works (WORKS_AT -> "Works at"). Known types get an org-side label automatically;
unknown ones show the same label on the org unless you give TYPE/ORG_SIDE.
Re-running updates the note (if given) and otherwise changes nothing.

Env: CLICKUP_TOKEN, CLICKUP_LIST_ID (Contacts), CLICKUP_ORGS_LIST_ID (Orgs: list ID, list URL or view ID).
"""
import argparse
import os
import sys

import crm_links as cl

DEFAULT_ORGS = "2kyddzem-1154"  # Orgs view ID; resolved to its list at runtime

# person-side TYPE -> org-side TYPE
ORG_SIDE = {
    "WORKS_AT": "EMPLOYS",
    "WORKED_AT": "EMPLOYED",
    "INTERNED_AT": "HOSTED_INTERN",
    "CONSULTS_FOR": "CLIENT_OF",
    "STUDIES_AT": "HAS_STUDENT",
    "STUDIED_AT": "HAS_ALUMNUS",
    "TEACHES_AT": "HAS_FACULTY",
    "TAUGHT_AT": "HAD_FACULTY",
    "BELONGS_TO": "HAS_MEMBER",
    "MEMBER_OF": "HAS_MEMBER",
    "WAS_MEMBER_OF": "HAD_MEMBER",
    "FOUNDED": "FOUNDED_BY",
    "CO_FOUNDED": "CO_FOUNDED_BY",
    "LEADS": "LED_BY",
    "ADVISES": "ADVISED_BY",
    "INVESTED_IN": "BACKED_BY",
    "ON_BOARD_OF": "HAS_BOARD_MEMBER",
    "VOLUNTEERS_AT": "HAS_VOLUNTEER",
    "CUSTOMER_OF": "SERVES",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=__import__("argparse").RawDescriptionHelpFormatter)
    ap.add_argument("person", nargs="?")
    ap.add_argument("type", nargs="?", help="e.g. WORKS_AT, STUDIED_AT, BELONGS_TO, or NEWTYPE/ORG_SIDE")
    ap.add_argument("org", nargs="?")
    ap.add_argument("--note", help='extra detail shown on both lines, e.g. "VP Eng, 2015-2019"')
    ap.add_argument("--create", action="store_true", help="create the org in the Orgs list if it doesn't exist")
    ap.add_argument("--remove", action="store_true", help="remove the link from both records")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--types", action="store_true", help="list types with a built-in org-side label")
    args = ap.parse_args()

    if args.types or not (args.person and args.type and args.org):
        print("Any TYPE works (WORKS_AT -> 'Works at'). Built-in org-side labels:")
        for k, v in ORG_SIDE.items():
            print(f"  {k:<16} person: '{cl.label(k)} <org>'   org: '{cl.label(v)} <person>'")
        print("For a new type, give the org-side label too:  PERSON COACHES/COACHED_BY ORG")
        return

    lab_p, lab_o = cl.parse_type(args.type, ORG_SIDE)
    token, contacts = os.environ.get("CLICKUP_TOKEN"), os.environ.get("CLICKUP_LIST_ID")
    if not token or not contacts:
        sys.exit("Set CLICKUP_TOKEN and CLICKUP_LIST_ID.")
    cu = cl.ClickUp(token, args.dry_run)
    orgs = cu.list_id(os.environ.get("CLICKUP_ORGS_LIST_ID") or DEFAULT_ORGS)

    p_id, p_name = cl.resolve(cu, args.person, contacts, "contact")
    o_id, o_name = cl.resolve(cu, args.org, orgs, "org", create=args.create and not args.remove)

    tag = "[dry] " if args.dry_run else ""
    sides = ((p_id, "Organizations", lab_p, o_id, o_name), (o_id, "People", lab_o, p_id, p_name))
    for me, section, lab, other, other_name in sides:
        if me == "dry-run-new":
            print(f"{tag}(new org) '{lab} {other_name}' would be added")
            continue
        name, changed = cl.upsert_line(cu, me, section, lab, other, other_name, args.note, args.remove)
        action = ("removed" if args.remove else "added/updated") if changed else "already up to date"
        print(f"{tag}{name}: '{lab} {other_name}' {action}")


if __name__ == "__main__":
    main()
