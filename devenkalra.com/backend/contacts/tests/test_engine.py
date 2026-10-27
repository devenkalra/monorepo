import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from contacts.engine import WriteGuard, open_list, run_sync
from contacts.engine.errors import (DryRunViolation, ProtectionViolation, SafetyStop, WriteBudgetExceeded,
                                    WritesDisabled)
from contacts.engine.guard import check_field_changes

from .fakes import FakeClickUp, FakePeople, make_task

CSV_HEADER = "Notes:\nsome preamble\n\nFirst Name,Last Name,URL,Email Address,Company,Position,Connected On\n"


def linkedin_csv(rows):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    f.write(CSV_HEADER + "".join(",".join(r) + "\n" for r in rows))
    f.close()
    return Path(f.name)


def existing_contacts():
    return [
        make_task("t1", "Alice Smith", emails="alice@example.com, not an email", **{"status": "st-0"}),
        make_task("t2", "Bob Jones", linkedin_url="https://www.linkedin.com/in/bobj", status="st-0",
                  company="OldCo", sources=["src-LinkedIn"]),
        make_task("t3", "Merged Person", status="st-3", google_id="people/c3"),
    ]


ROWS = [
    ("Alice", "Smith", "https://www.linkedin.com/in/alice", "alice@example.com", "Acme", "CTO", "01 Feb 2020"),
    ("Bob", "Jones", "https://www.linkedin.com/in/bobj", "", "NewCo", "VP", "03 Mar 2019"),
    ("Carol", "New", "https://www.linkedin.com/in/carol", "", "Initech", "Eng", "04 Apr 2021"),
]


def run(source="linkedin", *, dry=True, writes_enabled=False, max_ops=None, tasks=None, files=None, **kw):
    fake = FakeClickUp(tasks if tasks is not None else existing_contacts())
    guard = WriteGuard(dry=dry, writes_enabled=writes_enabled, max_ops=max_ops)
    cu, missing = open_list("tok", "L1", guard, session=fake)
    assert not missing
    ctx, result = run_sync(source=source, cu=cu, files=files or {"connections": linkedin_csv(ROWS)}, **kw)
    return fake, guard, ctx, result


class DryRunTests(SimpleTestCase):
    def test_dry_run_sends_no_writes_but_counts_them(self):
        fake, guard, ctx, _ = run()
        self.assertEqual(fake.writes, [])
        self.assertGreater(guard.ops, 0)
        self.assertEqual(ctx.stats["LINK(email)"], 1)
        self.assertEqual(ctx.stats["UPDATE"], 1)
        self.assertEqual(ctx.stats["CREATE"], 1)

    def test_http_layer_refuses_writes_in_dry_mode(self):
        fake = FakeClickUp(existing_contacts())
        cu, _ = open_list("tok", "L1", WriteGuard(dry=True), session=fake)
        with self.assertRaises(DryRunViolation):
            cu._req("POST", "/task/t1/field/f-title", json={"value": "x"})
        self.assertEqual(fake.writes, [])


class LiveRunTests(SimpleTestCase):
    def test_live_run_needs_writes_enabled(self):
        with self.assertRaises(WritesDisabled):
            run(dry=False, writes_enabled=False, max_ops=100)

    def test_live_run_stops_at_budget(self):
        with self.assertRaises(WriteBudgetExceeded):
            run(dry=False, writes_enabled=True, max_ops=3)

    def test_live_run_matches_its_plan(self):
        _, plan_guard, _, _ = run()
        fake, guard, ctx, _ = run(dry=False, writes_enabled=True, max_ops=plan_guard.ops)
        self.assertEqual(guard.ops, plan_guard.ops)
        self.assertEqual(len(fake.writes), guard.ops)
        alice = {cf["id"]: cf["value"] for cf in fake.tasks["t1"]["custom_fields"]}
        self.assertEqual(alice["f-linkedin_url"], "https://www.linkedin.com/in/alice")
        self.assertIn("not an email", alice["f-emails"])

    def test_fill_blanks_only_keeps_existing_values(self):
        _, plan, _, _ = run(options={"overwrite_values": False})
        fake, _, _, _ = run(dry=False, writes_enabled=True, max_ops=plan.ops, options={"overwrite_values": False})
        bob = {cf["id"]: cf["value"] for cf in fake.tasks["t2"]["custom_fields"]}
        self.assertEqual(bob["f-company"], "OldCo")
        self.assertEqual(bob["f-title"], "VP")


class ProtectionTests(SimpleTestCase):
    def test_refuses_clearing_a_value(self):
        with self.assertRaises(ProtectionViolation):
            check_field_changes({"company": "Acme"}, {"company": None})

    def test_allows_clearing_when_explicitly_allowed(self):
        check_field_changes({"dup_of": "https://app.clickup.com/t/x"}, {"dup_of": None}, allow_clear=("dup_of",))

    def test_refuses_dropping_an_email(self):
        with self.assertRaises(ProtectionViolation):
            check_field_changes({"emails": "a@x.com, b@x.com"}, {"emails": "a@x.com"})

    def test_reformatting_emails_is_not_a_loss(self):
        check_field_changes({"emails": "A@X.com"}, {"emails": "a@x.com, c@x.com"})

    def test_refuses_dropping_a_label(self):
        with self.assertRaises(ProtectionViolation):
            check_field_changes({"groups": ["Family", "Work"]}, {"groups": ["Family"]})

    def test_refuses_replacing_a_source_key(self):
        with self.assertRaises(ProtectionViolation):
            check_field_changes({"linkedin_url": "https://www.linkedin.com/in/a"},
                                {"linkedin_url": "https://www.linkedin.com/in/b"})

    def test_refuses_unmerging(self):
        with self.assertRaises(ProtectionViolation):
            check_field_changes({"status": "merged"}, {"status": "active"})

    def test_refuses_moving_last_message_backwards(self):
        with self.assertRaises(ProtectionViolation):
            check_field_changes({"last_li_msg": "2000"}, {"last_li_msg": 1000})

    def test_safety_stops_are_not_swallowed_per_contact(self):
        self.assertTrue(issubclass(ProtectionViolation, SafetyStop))


class ReviewTests(SimpleTestCase):
    def test_fuzzy_name_match_waits_for_review(self):
        rows = [("Alicia", "Smith", "https://www.linkedin.com/in/alicia", "", "", "", "")]
        tasks = [make_task("t9", "Smith Alicia", status="st-0")]
        fake, _, ctx, _ = run(tasks=tasks, files={"connections": linkedin_csv(rows)})
        self.assertEqual(ctx.stats["PENDING"], 1)
        self.assertEqual(ctx.review_rows[0]["suggested_task_id"], "t9")

    def test_same_decision_links_the_chosen_task(self):
        rows = [("Alicia", "Smith", "https://www.linkedin.com/in/alicia", "", "", "", "")]
        tasks = [make_task("t9", "Alicia Smyth", status="st-0")]
        tasks = [make_task("t9", "Smith Alicia", status="st-0")]
        decisions = {"https://www.linkedin.com/in/alicia": {"decision": "same", "task_id": "t9"}}
        _, plan, _, _ = run(tasks=tasks, files={"connections": linkedin_csv(rows)}, decisions=decisions)
        fake, _, ctx, _ = run(dry=False, writes_enabled=True, max_ops=plan.ops, tasks=tasks,
                              files={"connections": linkedin_csv(rows)}, decisions=decisions)
        self.assertEqual(ctx.stats["LINK(review)"], 1)
        self.assertEqual(len(fake.tasks), 1)

    def test_same_decision_never_relinks_an_already_linked_task(self):
        rows = [("Bob", "Jones", "https://www.linkedin.com/in/bob2", "", "", "", "")]
        decisions = {"https://www.linkedin.com/in/bob2": {"decision": "same", "task_id": "t2"}}
        fake, _, ctx, _ = run(dry=False, writes_enabled=True, max_ops=50,
                              files={"connections": linkedin_csv(rows)}, decisions=decisions)
        self.assertEqual(fake.writes, [])
        self.assertEqual(ctx.stats["PENDING"], 1)


def person(rid, name, email=None):
    p = {"resourceName": rid, "etag": "e", "names": [{"displayName": name}], "metadata": {}}
    if email:
        p["emailAddresses"] = [{"value": email}]
    return p


class GoogleTests(SimpleTestCase):
    def google_tasks(self, n):
        return [make_task(f"g{i}", f"Person {i}", google_id=f"people/c{i}", status="st-0") for i in range(n)]

    def test_full_sync_refuses_a_mass_deletion(self):
        svc = FakePeople([person("people/c0", "Person 0")])
        _, _, ctx, _ = run("google", tasks=self.google_tasks(30), google_service=svc, options={"full": True})
        self.assertEqual(ctx.stats["DELETED"], 0)
        self.assertTrue(any("safety limit" in w for w in ctx.warnings))

    def test_full_sync_marks_a_few_missing_contacts_deleted(self):
        svc = FakePeople([person(f"people/c{i}", f"Person {i}") for i in range(28)])
        _, _, ctx, _ = run("google", tasks=self.google_tasks(30), google_service=svc, options={"full": True})
        self.assertEqual(ctx.stats["DELETED"], 2)

    def test_tasks_are_not_renamed_unless_asked(self):
        svc = FakePeople([person("people/c0", "Renamed In Google")])
        tasks = self.google_tasks(1)
        _, plan, _, _ = run("google", tasks=tasks, google_service=svc)
        fake, _, _, _ = run("google", dry=False, writes_enabled=True, max_ops=plan.ops, tasks=tasks,
                            google_service=svc)
        self.assertEqual(fake.tasks["g0"]["name"], "Person 0")
        self.assertFalse(any(m == "PUT" for m, _, _ in fake.writes))

    def test_lookalike_waits_for_review_instead_of_creating(self):
        svc = FakePeople([person("people/c9", "Smith Alicia")])
        tasks = [make_task("t9", "Alicia Smith", status="st-0")]
        fake, _, ctx, _ = run("google", dry=False, writes_enabled=True, max_ops=50, tasks=tasks, google_service=svc)
        self.assertEqual(ctx.stats["PENDING"], 1)
        self.assertEqual(ctx.stats["REVIEW"], 0)
        self.assertEqual(fake.writes, [])
        self.assertEqual(ctx.review_rows[0]["key"], "people/c9")

    def test_incremental_sync_rereads_decided_contacts(self):
        svc = FakePeople([], others=[person("people/c9", "Smith Alicia")])
        tasks = [make_task("t9", "Alicia Smith", status="st-0")]
        decisions = {"people/c9": {"decision": "same", "task_id": "t9"}}
        _, plan, _, _ = run("google", tasks=tasks, google_service=svc, sync_token="tok-1", decisions=decisions)
        fake, _, ctx, _ = run("google", dry=False, writes_enabled=True, max_ops=plan.ops, tasks=tasks,
                              google_service=svc, sync_token="tok-1", decisions=decisions)
        self.assertEqual(ctx.stats["LINK(review)"], 1)
        alicia = {cf["id"]: cf["value"] for cf in fake.tasks["t9"]["custom_fields"]}
        self.assertEqual(alicia["f-google_id"], "people/c9")

    def test_linked_decisions_are_not_reread(self):
        svc = FakePeople([], others=[person("people/c0", "Person 0")])
        run("google", tasks=self.google_tasks(1), google_service=svc, sync_token="tok-1",
            decisions={"people/c0": {"decision": "same", "task_id": "g0"}})
        self.assertEqual(svc.batch_gets, [])

    def test_dry_run_does_not_advance_the_sync_token(self):
        svc = FakePeople([person("people/c0", "Person 0")])
        _, _, _, result = run("google", tasks=self.google_tasks(1), google_service=svc)
        self.assertIsNone(result["next_sync_token"])


class MergeTests(SimpleTestCase):
    def tasks(self, loser_status):
        return [
            make_task("keep", "Nidhi Kalra", status="st-1", google_id="people/c17", emails="nk@example.com",
                      dup_of="https://app.clickup.com/t/gone"),
            make_task("gone", "Nidhi Kalra", status=loser_status, google_id="people/c999",
                      google_hash="oldhash", linkedin_url="https://www.linkedin.com/in/nidhi",
                      company="Oracle", sources=["src-LinkedIn"]),
        ]

    def test_absorbs_a_task_whose_google_contact_was_deleted(self):
        fake, _, ctx, _ = run("merge", dry=False, writes_enabled=True, max_ops=50, tasks=self.tasks("st-2"),
                              options={"survivor": "keep", "loser": "gone"})
        self.assertEqual(ctx.stats["MERGE"], 1)
        keep = {cf["id"]: cf["value"] for cf in fake.tasks["keep"]["custom_fields"]}
        self.assertEqual(keep["f-linkedin_url"], "https://www.linkedin.com/in/nidhi")
        self.assertEqual(keep["f-company"], "Oracle")
        self.assertEqual(keep["f-google_id"], "people/c17")
        self.assertNotEqual(keep.get("f-google_hash"), "oldhash")
        self.assertTrue(fake.tasks["gone"]["archived"])

    def test_refuses_two_live_google_contacts(self):
        with self.assertRaises(ProtectionViolation):
            run("merge", dry=True, tasks=self.tasks("st-0"), options={"survivor": "keep", "loser": "gone"})
