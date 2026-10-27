from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from contacts import entities, runner
from contacts.engine import ClickUp
from contacts.engine import relations as rel
from contacts.models import EntityEdit, SyncRun

from .test_transfer import cf, field, source_workspace


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
        self.assertTrue(specs['Introduced by']['locked'])
        self.assertIsNone(specs['Contact Relationship']['locked'])
        self.assertTrue(specs['Groups']['hint'])
        self.assertEqual(specs['Contact Relationship']['value'], 'p-work')
        self.assertIsNone(self.detail('reeta')['fields'][0]['locked'])  # Company: reeta isn't linked to Google
        self.assertEqual({(r['label'], r['name'], r['target_list']) for r in d['relationships']},
                         {('Spouse of', 'Reeta Sharma', 'people'), ('Works at', 'Google', 'orgs')})

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
        self.assertTrue(self.md('P1', 'reeta').startswith('Lives in Palo Alto.'))
        self.assertIn('[Google](https://app.clickup.com/t/google) — PM', self.md('P1', 'reeta'))
        self.assertIn('[Reeta Ancin](https://app.clickup.com/t/reeta) — PM', self.md('O1', 'google'))
        self.assertIn('- Employs', self.md('O1', 'google'))
        self.assertIn('[Reeta Ancin](https://app.clickup.com/t/reeta)', self.md('P1', 'hakan'))
        self.assertTrue(self.md('P1', 'hakan').startswith('Met at a conference.'))
        rows = {r['id']: r for r in out['rows']}
        self.assertEqual(rows['reeta']['name'], 'Reeta Ancin')
        self.assertEqual(rows['reeta']['company'], 'Stanford')
        edit = EntityEdit.objects.get()
        self.assertTrue(edit.ok)
        self.assertTrue(all(c['ok'] for c in edit.changes))

    def test_removing_a_relationship_removes_the_other_side(self):
        self.save('hakan', {'relationships': [{'label': 'Spouse of', 'target_id': 'reeta', 'note': ''}]})
        self.assertNotIn('/t/google', self.md('P1', 'hakan'))
        self.assertNotIn('/t/hakan', self.md('O1', 'google'))
        self.assertIn('/t/reeta', self.md('P1', 'hakan'))

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

    def test_refuses_relationship_edits_when_the_description_has_unknown_text(self):
        self.ws.lists['P1']['tasks']['reeta']['markdown_description'] += '\nhandwritten remark'
        out = self.save('reeta', {'relationships': []}, status=400)
        self.assertIn('only be changed in ClickUp', out['detail'])
        self.assertFalse(self.detail('reeta')['relationships_editable'])

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
