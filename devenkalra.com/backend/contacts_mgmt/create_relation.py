#!/usr/bin/env python3
"""
create_relation.py - record a relationship between two contacts on BOTH ClickUp records,
as linked lines in a "Relationships" section at the end of each task description.

  python create_relation.py "Hakan Ancin" SPOUSE_OF "Reeta Sharma"
  python create_relation.py "Raj Kalra" PARENT_OF "Anya Kalra"          (Anya gets "Child of Raj")
  python create_relation.py "Mei Lin" COACHED/COACHED_BY "Sam Park"     (new one-way type + inverse)
  python create_relation.py "Mei Lin" ROOMMATE_OF "Sam Park" --note "Stanford, 2003"
  python create_relation.py "Hakan Ancin" SPOUSE_OF "Reeta Sharma" --remove
  python create_relation.py --types

Any TYPE works (SPOUSE_OF -> "Spouse of"); types not in INVERSE are the same both ways.
Uses CLICKUP_TOKEN and CLICKUP_LIST_ID. Shares section handling with link_org.py (crm_links.py).
"""
import argparse
import os
import sys

import crm_links as cl

INVERSE = {
    "PARENT_OF": "CHILD_OF",
    "GRANDPARENT_OF": "GRANDCHILD_OF",
    "STEPPARENT_OF": "STEPCHILD_OF",
    "PARENT_IN_LAW_OF": "CHILD_IN_LAW_OF",
    "AUNT_OR_UNCLE_OF": "NIECE_OR_NEPHEW_OF",
    "GODPARENT_OF": "GODCHILD_OF",
    "MANAGER_OF": "REPORTS_TO",
    "MENTOR_OF": "MENTEE_OF",
    "ADVISOR_OF": "ADVISEE_OF",
    "TEACHER_OF": "STUDENT_OF",
    "INTRODUCED": "INTRODUCED_BY",
    "REFERRED": "REFERRED_BY",
    "EMPLOYER_OF": "EMPLOYEE_OF",
}
INVERSE.update({v: k for k, v in list(INVERSE.items())})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", nargs="?")
    ap.add_argument("type", nargs="?", help="e.g. SPOUSE_OF, PARENT_OF, or NEWTYPE/ITS_INVERSE")
    ap.add_argument("b", nargs="?")
    ap.add_argument("--note", help="extra detail shown on both lines")
    ap.add_argument("--remove", action="store_true", help="remove the relationship from both records")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--types", action="store_true", help="list the one-way types that have a built-in inverse")
    args = ap.parse_args()

    if args.types or not (args.a and args.type and args.b):
        print("Any TYPE works (SPOUSE_OF -> 'Spouse of'); types not listed here are the same both ways.")
        print("One-way types with a built-in inverse:")
        for k in sorted(INVERSE):
            print(f"  {k:<20} <-> {INVERSE[k]}")
        print("For a new one-way type, give its inverse:  A COACHED/COACHED_BY B")
        return

    lab_a, lab_b = cl.parse_type(args.type, INVERSE)
    token, contacts = os.environ.get("CLICKUP_TOKEN"), os.environ.get("CLICKUP_LIST_ID")
    if not token or not contacts:
        sys.exit("Set CLICKUP_TOKEN and CLICKUP_LIST_ID.")
    cu = cl.ClickUp(token, args.dry_run)
    a_id, a_name = cl.resolve(cu, args.a, contacts)
    b_id, b_name = cl.resolve(cu, args.b, contacts)
    if a_id == b_id:
        sys.exit("Both names resolve to the same contact.")

    tag = "[dry] " if args.dry_run else ""
    for me, other, other_name, lab in ((a_id, b_id, b_name, lab_a), (b_id, a_id, a_name, lab_b)):
        name, changed = cl.upsert_line(cu, me, "Relationships", lab, other, other_name, args.note, args.remove)
        action = ("removed" if args.remove else "added/updated") if changed else "already up to date"
        print(f"{tag}{name}: '{lab} {other_name}' {action}")


if __name__ == "__main__":
    main()
