import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from contacts import entities, google_auth, runner
from contacts.engine import ClickUp
from contacts.engine import relations as rel
from contacts.engine.fields import STATUS_OPTIONS
from contacts.models import EntityDetailCache, EntityEdit, GoogleAccount, SyncRun

from .fakes import FakePeople
from .test_transfer import cf, field, source_workspace


def _sync_fields(prefix='p'):
    """Required + commonly written sync fields for create tests (on top of people_fields)."""
    out = [
        field(f'{prefix}-gid', 'Google ID', 'short_text'),
        field(f'{prefix}-ghash', 'Google hash', 'short_text'),
        field(f'{prefix}-glink', 'Google Link', 'url'),
        field(f'{prefix}-li', 'LinkedIn URL', 'url'),
        field(f'{prefix}-lih', 'LinkedIn hash', 'short_text'),
        field(f'{prefix}-emails', 'Emails', 'short_text'),
        field(f'{prefix}-phones', 'Phones', 'short_text'),
        field(f'{prefix}-email', 'Email', 'email'),
        field(f'{prefix}-bday', 'Birthday', 'short_text'),
        field(f'{prefix}-addr', 'Address', 'short_text'),
        field(f'{prefix}-web', 'Website', 'url'),
        field(f'{prefix}-src', 'Sources', 'labels',
              [{'id': f'{prefix}-src-g', 'label': 'Google'}, {'id': f'{prefix}-src-li', 'label': 'LinkedIn'}]),
        field(f'{prefix}-st', 'Match status', 'drop_down',
              [{'id': f'{prefix}-st-{i}', 'name': o, 'orderindex': i} for i, o in enumerate(STATUS_OPTIONS)]),
        field(f'{prefix}-dup', 'Duplicate of', 'url'),
    ]
    return out


class BuildRowOutreachTests(SimpleTestCase):
    def test_outreach_dropdown_and_options(self):
        fields = [
            field('p-out', 'Outreach', 'drop_down', [
                {'id': 'out-cold', 'name': 'Cold', 'orderindex': 0},
                {'id': 'out-warm', 'name': 'Warm', 'orderindex': 1},
            ]),
        ]
        by_id = {f['id']: f for f in fields}
        rec = {
            'id': 't1', 'name': 'Ada', 'status': 'open', 'archived': False,
            'date_updated': '0', 'url': 'https://app.clickup.com/t/t1', 'description': '',
            'custom_fields': [
                {'field_id': 'p-out', 'name': 'Outreach', 'type': 'drop_down', 'value': 1},
            ],
        }
        row = entities.build_row('people', rec, by_id)
        self.assertEqual(row['outreach'], ['Warm'])
        # Float orderindex (ClickUp sometimes returns JSON numbers as floats).
        rec['custom_fields'][0]['value'] = 0.0
        self.assertEqual(entities.build_row('people', rec, by_id)['outreach'], ['Cold'])
        self.assertEqual(entities.field_option_names(fields, 'Outreach'), ['Cold', 'Warm'])


class RelationsTests(SimpleTestCase):
    def test_render_round_trips_and_keeps_notes(self):
        md = ("Met at a conference.\n\n**Relationships**\n*   Spouse of\n"
              "    *   [Reeta Sharma](https://app.clickup.com/t/reeta)\n\n**Organizations**\n"
              "*   Works at [Google](https://app.clickup.com/t/google) — Staff SWE")
        notes, lines, unparsed = rel.parse(md)
        self.assertEqual(notes, "Met at a conference.")
        self.assertEqual(unparsed, [])
        self.assertEqual(rel.split(rel.render(notes, lines)), (notes, lines))

    def test_text_the_parser_does_not_understand_is_reported(self):
        md = "**Relationships**\n- Spouse of\n    - [A](https://app.clickup.com/t/a)\n- just a remark\nfree text"
        self.assertEqual(rel.parse(md)[2], ["- just a remark", "free text"])

    def test_inverse_labels(self):
        self.assertEqual(rel.inverse("Parent of", "people", "people"), "Child of")
        self.assertEqual(rel.inverse("Spouse of", "people", "people"), "Spouse of")
        self.assertEqual(rel.inverse("Works at", "people", "orgs"), "Employs")
        self.assertEqual(rel.inverse("Has alumnus", "orgs", "people"), "Studied at")
        self.assertEqual(rel.inverse("Plays chess with", "people", "people"), "Plays chess with")

    def test_upsert_and_remove_one_line(self):
        md = "Notes\n\n**People**\n- Employs\n    - [Hakan](https://app.clickup.com/t/hakan) — SWE"
        md2, changed = rel.upsert_line(md, "People", "Employs", "hakan", "Hakan Ancin", "Staff SWE")
        self.assertTrue(changed)
        self.assertIn("[Hakan Ancin](https://app.clickup.com/t/hakan) — Staff SWE", md2)
        md3, changed = rel.upsert_line(md2, "People", "Employs", "hakan", "Hakan Ancin", None, remove=True)
        self.assertTrue(changed)
        self.assertEqual(md3, "Notes")

    def test_relationship_data_json_round_trip_and_merge(self):
        lines = [
            {'label': 'Spouse of', 'target_id': 'reeta', 'note': '', 'name': 'Reeta'},
            {'label': 'Works at', 'target_id': 'google', 'note': 'SWE', 'name': 'Google'},
        ]
        raw = rel.encode_data(lines)
        self.assertEqual(rel.decode_data(raw), [
            {'label': 'Spouse of', 'target_id': 'reeta', 'note': '', 'name': ''},
            {'label': 'Works at', 'target_id': 'google', 'note': 'SWE', 'name': ''},
        ])
        merged, unparsed, structured = rel.load_lines(
            '**Relationships**\n- Friend of\n    - [X](https://app.clickup.com/t/x)',
            raw,
            [{'id': 'hakan', 'name': 'Hakan'}],
        )
        self.assertTrue(structured)
        self.assertEqual(unparsed, [])
        keys = {rel.key(ln) for ln in merged}
        self.assertEqual(keys, {('reeta', 'spouse of'), ('google', 'works at'), ('hakan', 'introduced by')})

    def test_encode_display_matches_legacy_sections(self):
        lines = [
            {'section': 'Relationships', 'label': 'Spouse of', 'target_id': 'reeta',
             'name': 'Reeta Sharma', 'note': ''},
            {'section': 'Organizations', 'label': 'Works at', 'target_id': 'google',
             'name': 'Google', 'note': 'Staff SWE'},
        ]
        text = rel.encode_display(lines)
        self.assertIn('**Relationships**', text)
        self.assertIn('[Reeta Sharma](https://app.clickup.com/t/reeta)', text)
        self.assertIn('**Organizations**', text)
        self.assertIn('[Google](https://app.clickup.com/t/google) — Staff SWE', text)
        self.assertEqual(rel.encode_display([]), '')
        # render() is notes + display body
        self.assertEqual(rel.render('Met at a conference.', lines),
                         'Met at a conference.\n\n' + text)
        # Managed description block: relationships on top, notes below.
        composed = rel.compose_description(lines, 'Met at a conference.')
        self.assertTrue(composed.startswith(rel.DISPLAY_BLOCK_START + '\n'))
        # ### headings interrupt lists and stay left-aligned; no blank line / HTML before the end.
        self.assertIn(f'\n{rel.DISPLAY_BLOCK_END}\n\nMet at a conference.', composed)
        self.assertNotIn(f'\n\n{rel.DISPLAY_BLOCK_END}', composed)
        start_at = len(rel.DISPLAY_BLOCK_START)
        end_at = composed.index(rel.DISPLAY_BLOCK_END, start_at + 1)
        inside = composed[start_at:end_at]
        self.assertIn('**Relationships**', inside)
        self.assertIn('**Organizations**', inside)
        self.assertEqual(rel.notes_text(composed), 'Met at a conference.')
        self.assertEqual(rel.compose_description([], 'Just notes.'), 'Just notes.')
        # Legacy ==== / heading-level variants are stripped — including stacked boundaries.
        stale = ("==== Do Not Change Between Lines ====\n**Relationships**\n- X\n"
                 "<p>==== Do Not Change Between Lines ====</p>\n\nKeep my notes.")
        self.assertEqual(rel.strip_managed_blocks(stale), 'Keep my notes.')
        stacked = (
            "#### ==== Do Not Change Between Lines\n**People**\n- Employs\n"
            "    - [A](https://app.clickup.com/t/a)\n"
            "#### ==== End Do Not Change Between Lines\n"
            f"{rel.DISPLAY_BLOCK_START}\n**People**\n- Employs\n"
            "    - [B](https://app.clickup.com/t/b)\n"
            f"{rel.DISPLAY_BLOCK_END}\n\nSchool notes."
        )
        cleaned = rel.compose_description_over(stacked, lines)
        self.assertEqual(len(rel.MARKER_LINE_RE.findall(cleaned)), 2)
        self.assertEqual(cleaned.count('Do Not Change'), 2)  # one start + one end only
        self.assertEqual(rel.notes_text(cleaned), 'School notes.')
        self.assertEqual(rel.compose_description_over(cleaned, lines), cleaned)  # idempotent
        with_legacy = "Keep my notes.\n\n**Relationships**\n- Spouse of\n    - [X](https://app.clickup.com/t/x)"
        refreshed = rel.compose_description_over(with_legacy, lines)
        self.assertEqual(rel.notes_text(refreshed), 'Keep my notes.')
        self.assertTrue(refreshed.startswith(rel.DISPLAY_BLOCK_START))
        self.assertEqual(refreshed.count('**Relationships**'), 1)


@override_settings(CONTACTS_CLICKUP_TOKEN='tok', CONTACTS_CLICKUP_LIST_ID='P1', CONTACTS_CLICKUP_ORGS_LIST_ID='O1',
                   CONTACTS_CLICKUP_WRITES_ENABLED=True)
class EntityApiTests(TestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=admin).key}')
        ws = source_workspace()
        ws.lists['P1']['fields'].append(field('p-gid', 'Google ID', 'short_text'))
        ws.lists['P1']['fields'].append(field('p-title', 'Title', 'short_text'))
        ws.lists['P1']['tasks']['hakan']['custom_fields'].append(cf('p-gid', 'people/c1'))
        self.ws = ws
        patcher = mock.patch.object(entities, 'ClickUp',
                                    lambda token, list_id, guard: ClickUp(token, list_id, guard, session=ws))
        patcher.start()
        self.addCleanup(patcher.stop)

    def detail(self, tid):
        r = self.client.get(f'/api/contacts/entities/{tid}/')
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def save(self, tid, body, status=200):
        d = self.detail(tid)
        r = self.client.put(f'/api/contacts/entities/{tid}/', dict(body, date_updated=d['date_updated']),
                            format='json')
        self.assertEqual(r.status_code, status, r.content)
        return r.json()

    def md(self, list_id, tid):
        return self.ws.lists[list_id]['tasks'][tid]['markdown_description']

    def test_refresh_fills_the_list(self):
        self.assertFalse(self.client.get('/api/contacts/entities/').json()['loaded'])
        r = self.client.post('/api/contacts/entities/')
        self.assertEqual(r.status_code, 200, r.content)
        rows = {e['id']: e for e in r.json()['entities']}
        self.assertEqual(set(rows), {'hakan', 'reeta', 'old', 'google'})
        self.assertEqual(rows['hakan']['company'], 'Google')
        self.assertEqual(rows['hakan']['groups'], ['Google', 'Caltech'])
        self.assertEqual(rows['hakan']['relationships'], 2)
        self.assertEqual(rows['google']['list'], 'orgs')
        self.assertTrue(rows['old']['archived'])
        self.assertEqual(self.ws.writes, [])

    def test_detail_locks_sync_fields(self):
        d = self.detail('hakan')
        specs = {s['name']: s for s in d['fields']}
        self.assertTrue(specs['Google ID']['locked'])
        self.assertTrue(specs['Last synced']['locked'])
        self.assertIn('Google', specs['Company']['locked'])
        self.assertIn('Relationships', specs['Introduced by']['locked'])
        self.assertIn('Relationships', specs['Relationship data']['locked'])
        self.assertIsNone(specs['Contact Relationship']['locked'])
        self.assertTrue(specs['Groups']['hint'])
        self.assertEqual(specs['Contact Relationship']['value'], 'p-work')
        self.assertIsNone(self.detail('reeta')['fields'][0]['locked'])  # Company: reeta isn't linked to Google
        self.assertEqual({(r['label'], r['name'], r['target_list']) for r in d['relationships']},
                         {('Spouse of', 'Reeta Sharma', 'people'), ('Works at', 'Google', 'orgs')})
        reeta = {(r['label'], r['name'], r['target_list']) for r in self.detail('reeta')['relationships']}
        self.assertIn(('Introduced by', 'Hakan Ancin', 'people'), reeta)

    def _rdata(self, list_id, tid):
        values = {c['id']: c['value'] for c in self.ws.lists[list_id]['tasks'][tid]['custom_fields']}
        fid = 'p-rdata' if list_id == 'P1' else 'o-rdata'
        raw = values.get(fid) or '[]'
        return {(x['type'], x['id'], x.get('note') or '') for x in json.loads(raw)}

    def test_save_edits_fields_and_both_sides_of_relationships(self):
        self.client.post('/api/contacts/entities/')
        out = self.save('reeta', {
            'name': 'Reeta Ancin',
            'notes': 'Lives in Palo Alto.',
            'fields': {'p-co': 'Stanford', 'p-rel': 'p-pers', 'p-grp': ['p-g2']},
            'relationships': [
                {'label': 'Spouse of', 'target_id': 'hakan', 'note': ''},
                {'label': 'Works at', 'target_id': 'google', 'note': 'PM'},
            ],
        })
        self.assertTrue(out['changed'])
        reeta = self.ws.lists['P1']['tasks']['reeta']
        self.assertEqual(reeta['name'], 'Reeta Ancin')
        values = {c['id']: c['value'] for c in reeta['custom_fields']}
        self.assertEqual((values['p-co'], values['p-rel'], values['p-grp']), ('Stanford', 'p-pers', ['p-g2']))
        reeta_md = self.md('P1', 'reeta')
        self.assertTrue(reeta_md.startswith(rel.DISPLAY_BLOCK_START))
        self.assertIn(rel.DISPLAY_BLOCK_END, reeta_md)
        self.assertIn('**Organizations**', reeta_md)
        self.assertEqual(rel.notes_text(reeta_md), 'Lives in Palo Alto.')
        self.assertEqual(self._rdata('P1', 'reeta'),
                         {('Spouse of', 'hakan', ''), ('Works at', 'google', 'PM')})
        # Google already employed Hakan; adding Reeta keeps both edges.
        self.assertEqual(self._rdata('O1', 'google'),
                         {('Employs', 'hakan', 'Staff SWE'), ('Employs', 'reeta', 'PM')})
        self.assertEqual(self._rdata('P1', 'hakan'),
                         {('Spouse of', 'reeta', ''), ('Works at', 'google', 'Staff SWE')})
        hakan_md = self.md('P1', 'hakan')
        self.assertTrue(hakan_md.startswith(rel.DISPLAY_BLOCK_START))
        self.assertEqual(rel.notes_text(hakan_md), 'Met at a conference.')
        self.assertIn('[Hakan Ancin](https://app.clickup.com/t/hakan)', reeta_md)
        self.assertIn('[Google](https://app.clickup.com/t/google) — PM', reeta_md)
        self.assertIn('[Reeta Ancin](https://app.clickup.com/t/reeta)', self.md('O1', 'google'))
        # Introduced by was folded away when relationships were saved.
        self.assertNotIn('p-intro', values)
        rows = {r['id']: r for r in out['rows']}
        self.assertEqual(rows['reeta']['name'], 'Reeta Ancin')
        self.assertEqual(rows['reeta']['company'], 'Stanford')
        edit = EntityEdit.objects.get()
        self.assertTrue(edit.ok)
        self.assertTrue(all(c['ok'] for c in edit.changes))

    def test_removing_a_relationship_removes_the_other_side(self):
        self.save('hakan', {'relationships': [{'label': 'Spouse of', 'target_id': 'reeta', 'note': ''}]})
        self.assertEqual(self._rdata('P1', 'hakan'), {('Spouse of', 'reeta', '')})
        self.assertNotIn(('Employs', 'hakan', 'Staff SWE'), self._rdata('O1', 'google'))
        # Unchanged Spouse edge isn't rewritten on Reeta; legacy description still lists it.
        self.assertTrue(any(r['label'] == 'Spouse of' and r['target_id'] == 'hakan'
                            for r in self.detail('reeta')['relationships']))

    def test_saving_nothing_writes_nothing(self):
        out = self.save('hakan', {'name': 'Hakan Ancin', 'fields': {'p-co': 'Google'}})
        self.assertFalse(out['changed'])
        self.assertEqual(self.ws.writes, [])
        self.assertFalse(EntityEdit.objects.exists())

    def test_refuses_locked_fields(self):
        out = self.save('hakan', {'fields': {'p-co': 'Microsoft', 'p-seen': '1'}}, status=400)
        self.assertIn('Company', out['detail'])
        self.assertIn('Last synced', out['detail'])
        self.assertEqual(self.ws.writes, [])

    def test_refuses_a_task_changed_since_it_was_opened(self):
        r = self.client.put('/api/contacts/entities/hakan/', {'date_updated': '1', 'name': 'X'}, format='json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.ws.writes, [])

    def test_refuses_an_org_linked_to_an_org(self):
        self.ws.put('O1', {'id': 'alphabet', 'name': 'Alphabet'})
        out = self.save('google', {'relationships': [{'label': 'Part of', 'target_id': 'alphabet'}]}, status=400)
        self.assertIn('only be linked to people', out['detail'])

    def test_unparsed_description_still_allows_relationship_field_edits(self):
        self.ws.lists['P1']['tasks']['reeta']['markdown_description'] += '\nhandwritten remark'
        # Relationship data field is present, so relationships stay editable; notes are blocked.
        self.assertTrue(self.detail('reeta')['relationships_editable'])
        out = self.save('reeta', {'notes': 'New notes only'}, status=400)
        self.assertIn('notes can only be changed in ClickUp', out['detail'])
        self.save('reeta', {'relationships': [{'label': 'Spouse of', 'target_id': 'hakan', 'note': ''}]})
        self.assertEqual(self._rdata('P1', 'reeta'), {('Spouse of', 'hakan', '')})

    def test_refuses_while_writes_are_disabled_or_a_live_run_is_active(self):
        with override_settings(CONTACTS_CLICKUP_WRITES_ENABLED=False):
            self.save('hakan', {'name': 'X'}, status=409)
        SyncRun.objects.create(source='google', mode=SyncRun.Mode.LIVE, status=SyncRun.Status.RUNNING)
        self.save('hakan', {'name': 'X'}, status=409)
        self.assertEqual(self.ws.writes, [])

    def test_an_edit_makes_older_previews_stale(self):
        plan = SyncRun.objects.create(source='google', mode=SyncRun.Mode.DRY, status=SyncRun.Status.DONE, ops=3,
                                      started_at=timezone.now(), finished_at=timezone.now())
        self.save('hakan', {'name': 'Hakan A.'})
        self.assertIn('edited in People & Orgs', runner.apply_refusal(plan))

    def test_detail_is_cached_until_invalidated(self):
        first = self.detail('hakan')
        self.assertEqual(first['name'], 'Hakan Ancin')
        self.assertEqual(EntityDetailCache.objects.filter(task_id='hakan').count(), 1)

        self.ws.lists['P1']['tasks']['hakan']['name'] = 'Changed In ClickUp'
        cached = self.detail('hakan')
        self.assertEqual(cached['name'], 'Hakan Ancin')  # still the cached payload

        r = self.client.get('/api/contacts/entities/hakan/?refresh=1')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['name'], 'Changed In ClickUp')
        self.assertEqual(EntityDetailCache.objects.get(task_id='hakan').payload['name'], 'Changed In ClickUp')

    def test_save_and_list_refresh_invalidate_detail_cache(self):
        self.detail('hakan')
        self.detail('reeta')
        self.assertEqual(EntityDetailCache.objects.filter(task_id__in=['hakan', 'reeta']).count(), 2)

        self.save('hakan', {'name': 'Hakan A.'})
        # Save rebuilt hakan's cache from live ClickUp; reeta was a relationship target and was cleared.
        self.assertEqual(EntityDetailCache.objects.get(task_id='hakan').payload['name'], 'Hakan A.')
        self.assertFalse(EntityDetailCache.objects.filter(task_id='reeta').exists())

        self.detail('reeta')
        self.client.post('/api/contacts/entities/')
        self.assertFalse(EntityDetailCache.objects.exists())

    def bulk(self, body, status=200):
        r = self.client.post('/api/contacts/entities/bulk/', body, format='json')
        self.assertEqual(r.status_code, status, r.content)
        return r.json()

    def test_bulk_add_groups_merges_and_skips_existing(self):
        out = self.bulk({'op': 'add_groups', 'ids': ['reeta', 'hakan', 'google'], 'groups': ['Google']})
        self.assertEqual(out['ok'], 1)
        self.assertEqual(out['skipped'], 1)
        self.assertEqual(out['failed'], 1)
        by_id = {r['id']: r for r in out['results']}
        self.assertTrue(by_id['reeta']['changed'])
        self.assertFalse(by_id['hakan']['changed'])
        self.assertIn('organization', by_id['google']['error'])
        values = {c['id']: c['value'] for c in self.ws.lists['P1']['tasks']['reeta']['custom_fields']}
        self.assertEqual(values.get('p-grp'), ['p-g1'])
        rows = {r['id']: r for r in out['rows']}
        self.assertEqual(rows['reeta']['groups'], ['Google'])

    def test_bulk_add_relationship_appends_missing_edges(self):
        out = self.bulk({
            'op': 'add_relationship',
            'ids': ['reeta', 'hakan'],
            'label': 'Works at',
            'target_id': 'google',
            'note': 'PM',
        })
        self.assertEqual(out['ok'], 1)
        self.assertEqual(out['skipped'], 1)
        self.assertEqual(out['failed'], 0)
        by_id = {r['id']: r for r in out['results']}
        self.assertTrue(by_id['reeta']['changed'])
        self.assertFalse(by_id['hakan']['changed'])
        self.assertEqual(self._rdata('P1', 'reeta'),
                         {('Spouse of', 'hakan', ''), ('Works at', 'google', 'PM'),
                          ('Introduced by', 'hakan', '')})
        self.assertIn(('Employs', 'reeta', 'PM'), self._rdata('O1', 'google'))
    def test_bulk_refuses_empty_or_unknown_op(self):
        self.assertIn('Select at least one', self.bulk({'op': 'add_groups', 'ids': [], 'groups': ['Google']},
                                                       status=400)['detail'])
        self.assertIn('Unknown bulk op', self.bulk({'op': 'delete', 'ids': ['hakan']}, status=400)['detail'])


@override_settings(CONTACTS_CLICKUP_TOKEN='tok', CONTACTS_CLICKUP_LIST_ID='P1', CONTACTS_CLICKUP_ORGS_LIST_ID='O1',
                   CONTACTS_CLICKUP_WRITES_ENABLED=True)
class MigrateRelationshipsTests(TestCase):
    def test_plan_folds_description_and_introduced_by(self):
        from contacts.migrate_relationships import plan
        ws = source_workspace()
        people = list(ws.lists['P1']['tasks'].values())
        orgs = list(ws.lists['O1']['tasks'].values())
        fields = {'people': ws.lists['P1']['fields'], 'orgs': ws.lists['O1']['fields']}
        rows = plan({'people': people, 'orgs': orgs}, fields)
        reeta = rows['reeta']
        self.assertTrue(reeta['changed'])
        self.assertTrue(reeta['clear_intro'])
        self.assertTrue(reeta['strip_desc'] or reeta['unparsed'] == [])
        payload = {(x['type'], x['id']) for x in json.loads(reeta['payload'])}
        self.assertIn(('Introduced by', 'hakan'), payload)
        self.assertIn(('Spouse of', 'hakan'), payload)
        # Inverse of Introduced by lands on Hakan.
        hakan = {(x['type'], x['id']) for x in json.loads(rows['hakan']['payload'])}
        self.assertIn(('Introduced', 'reeta'), hakan)


class SyncRelationshipDisplayTests(SimpleTestCase):
    def test_plan_wipes_description_and_rebuilds_from_relationship_data(self):
        from contacts.sync_relationship_display import plan
        ws = source_workspace()
        ws.lists['P1']['tasks']['hakan']['custom_fields'].append(cf(
            'p-rdata',
            rel.encode_data([
                {'label': 'Spouse of', 'target_id': 'reeta', 'note': ''},
                {'label': 'Works at', 'target_id': 'google', 'note': 'Staff SWE'},
            ]),
            'Relationship data', 'text'))
        people = list(ws.lists['P1']['tasks'].values())
        orgs = list(ws.lists['O1']['tasks'].values())
        fields = {'people': ws.lists['P1']['fields'], 'orgs': ws.lists['O1']['fields']}
        rows = plan({'people': people, 'orgs': orgs}, fields)
        hakan = rows['hakan']
        self.assertTrue(hakan['changed'])
        self.assertEqual(hakan['edge_count'], 2)
        self.assertTrue(hakan['description'].startswith(rel.DISPLAY_BLOCK_START))
        self.assertIn('**Relationships**', hakan['description'])
        self.assertIn('[Reeta Sharma](https://app.clickup.com/t/reeta)', hakan['description'])
        self.assertIn('**Organizations**', hakan['description'])
        self.assertIn('[Google](https://app.clickup.com/t/google) — Staff SWE', hakan['description'])
        # Sync clears free-form notes; description is the managed block only.
        self.assertEqual(rel.notes_text(hakan['description']), '')
        self.assertTrue(hakan['description'].endswith(rel.DISPLAY_BLOCK_END))
        ws.lists['P1']['tasks']['hakan']['markdown_description'] = hakan['description']
        people = list(ws.lists['P1']['tasks'].values())
        rows2 = plan({'people': people, 'orgs': orgs}, fields)
        self.assertFalse(rows2['hakan']['changed'])


@override_settings(CONTACTS_CLICKUP_TOKEN='tok', CONTACTS_CLICKUP_LIST_ID='P1', CONTACTS_CLICKUP_ORGS_LIST_ID='O1',
                   CONTACTS_CLICKUP_WRITES_ENABLED=True)
class EntityCreateTests(TestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=admin).key}')
        GoogleAccount.objects.create(email='me@example.com', refresh_token='rt',
                                     scopes='https://www.googleapis.com/auth/contacts openid email')
        self.ws = source_workspace()
        self.ws.lists['P1']['fields'] += _sync_fields()
        self.ws.lists['P1']['fields'].append(field('p-title', 'Title', 'short_text'))
        self.people = FakePeople([], groups=[
            {'resourceName': 'contactGroups/fam', 'groupType': 'USER_CONTACT_GROUP', 'name': 'contactGroups/fam',
             'formattedName': 'Caltech'},
        ])
        patcher = mock.patch.object(entities, 'ClickUp',
                                    lambda token, list_id, guard: ClickUp(token, list_id, guard, session=self.ws))
        patcher.start()
        self.addCleanup(patcher.stop)
        gpatch = mock.patch.object(google_auth, 'people_service', return_value=self.people)
        gpatch.start()
        self.addCleanup(gpatch.stop)
        sleep_patch = mock.patch('contacts.engine.sources.google.time.sleep', return_value=None)
        sleep_patch.start()
        self.addCleanup(sleep_patch.stop)

    def create(self, body, status=201):
        r = self.client.post('/api/contacts/entities/create/', body, format='json')
        self.assertEqual(r.status_code, status, r.content)
        return r.json()

    def test_creates_google_then_clickup_person(self):
        self.client.post('/api/contacts/entities/')  # load cache for duplicate check
        out = self.create({
            'first_name': 'Ada',
            'last_name': 'Lovelace',
            'emails': 'ada@example.com',
            'phones': '+1 650 555 0100',
            'company': 'Analytical Engines',
            'title': 'Mathematician',
            'birthday': '1815-12-10',
            'address': 'London',
            'website': 'example.com',
            'groups': ['Caltech', 'MissingLabel'],
        })
        self.assertEqual(len(self.people.creates), 1)
        body = self.people.creates[0]
        self.assertEqual(body['names'][0], {'givenName': 'Ada', 'familyName': 'Lovelace'})
        self.assertEqual(body['emailAddresses'][0]['value'], 'ada@example.com')
        self.assertEqual(body['organizations'][0]['name'], 'Analytical Engines')
        self.assertEqual(body['birthdays'][0]['date'], {'year': 1815, 'month': 12, 'day': 10})
        self.assertEqual(body['memberships'][0]['contactGroupMembership']['contactGroupResourceName'],
                         'contactGroups/fam')
        tid = out['entity']['id']
        self.assertTrue(tid.startswith('n'))
        task = self.ws.lists['P1']['tasks'][tid]
        self.assertEqual(task['name'], 'Ada Lovelace')
        values = {c['id']: c['value'] for c in task['custom_fields']}
        self.assertEqual(values['p-gid'], out['google_id'])
        self.assertEqual(values['p-emails'], 'ada@example.com')
        self.assertEqual(values['p-co'], 'Analytical Engines')
        self.assertEqual(values['p-src'], ['p-src-g'])
        self.assertEqual(values['p-st'], 'p-st-0')  # active
        self.assertTrue(any(u.get('updatePersonFields') == 'externalIds' for u in self.people.updates))
        self.assertIn('MissingLabel', ' '.join(out['warnings']))
        self.assertEqual(out['rows'][0]['id'], tid)
        edit = EntityEdit.objects.get()
        self.assertTrue(edit.ok)
        self.assertEqual(edit.task_id, tid)

    def test_refuses_without_write_access_or_identity(self):
        GoogleAccount.objects.all().update(scopes='https://www.googleapis.com/auth/contacts.readonly')
        self.assertIn('write access', self.create({'first_name': 'X'}, status=400)['detail'])
        GoogleAccount.objects.all().delete()
        self.assertIn('Connect Google', self.create({'first_name': 'X'}, status=400)['detail'])
        self.assertEqual(self.people.creates, [])

    def test_refuses_overlapping_email_in_cache(self):
        self.ws.lists['P1']['tasks']['hakan']['custom_fields'].append(
            cf('p-emails', 'hakan@google.com', 'Emails', 'short_text'))
        self.client.post('/api/contacts/entities/')
        out = self.create({'first_name': 'Other', 'emails': 'hakan@google.com'}, status=409)
        self.assertIn('Hakan Ancin', out['detail'])
        self.assertEqual(self.people.creates, [])

    def test_refuses_empty_and_bad_birthday(self):
        self.assertIn('first or last name, email or phone', self.create({}, status=400)['detail'])
        self.assertIn('Birthday', self.create({'first_name': 'X', 'birthday': 'nope'}, status=400)['detail'])

    def test_create_makes_older_previews_stale(self):
        plan = SyncRun.objects.create(source='google', mode=SyncRun.Mode.DRY, status=SyncRun.Status.DONE, ops=1,
                                      started_at=timezone.now(), finished_at=timezone.now())
        self.create({'first_name': 'New', 'last_name': 'Person', 'emails': 'new@example.com'})
        self.assertIn('edited in People & Orgs', runner.apply_refusal(plan))
