import gzip
import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from contacts import runner
from contacts.engine import open_list as real_open_list
from contacts.models import ChangeLog, ReviewItem, SyncRun

from .fakes import FakeClickUp, make_task
from .test_engine import CSV_HEADER, ROWS, existing_contacts

CSV = (CSV_HEADER + "".join(",".join(r) + "\n" for r in ROWS)).encode()


class ContactsApiTests(TestCase):
    def setUp(self):
        self.data_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.data_dir, ignore_errors=True)
        self.settings_ctx = override_settings(CONTACTS_DATA_DIR=self.data_dir, CONTACTS_CLICKUP_TOKEN='tok',
                                              CONTACTS_CLICKUP_LIST_ID='L1', CONTACTS_CLICKUP_WRITES_ENABLED=False)
        self.settings_ctx.enable()
        self.addCleanup(self.settings_ctx.disable)
        admin = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=admin).key}')
        self.fake = FakeClickUp(existing_contacts())
        patcher = mock.patch.object(runner, 'open_list',
                                    lambda token, list_id, guard: real_open_list(token, list_id, guard,
                                                                                 session=self.fake))
        patcher.start()
        self.addCleanup(patcher.stop)

    def upload(self):
        r = self.client.post('/api/contacts/uploads/', {
            'kind': 'linkedin_connections', 'file': SimpleUploadedFile('Connections.csv', CSV)}, format='multipart')
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def preview(self):
        f = self.upload()
        r = self.client.post('/api/contacts/runs/', {'source': 'linkedin', 'files': {'connections': f['id']}},
                             format='json')
        self.assertEqual(r.status_code, 201, r.content)
        run = runner.execute_run(runner.claim(r.json()['id']))
        self.assertEqual(run.status, SyncRun.Status.DONE, run.error)
        return run

    def test_requires_superuser(self):
        self.assertEqual(APIClient().get('/api/contacts/status/').status_code, 401)

    def test_upload_rejects_the_wrong_file(self):
        r = self.client.post('/api/contacts/uploads/', {
            'kind': 'linkedin_connections', 'file': SimpleUploadedFile('x.csv', b'a,b\n1,2\n')}, format='multipart')
        self.assertEqual(r.status_code, 400)

    def test_preview_writes_nothing(self):
        run = self.preview()
        self.assertEqual(self.fake.writes, [])
        self.assertGreater(run.ops, 0)
        self.assertEqual(ChangeLog.objects.count(), 0)

    def test_live_runs_cannot_be_created_directly(self):
        f = self.upload()
        r = self.client.post('/api/contacts/runs/', {'source': 'linkedin', 'mode': 'live',
                                                     'files': {'connections': f['id']}}, format='json')
        self.assertEqual(SyncRun.objects.get(pk=r.json()['id']).mode, SyncRun.Mode.DRY)

    def test_apply_refused_while_writes_are_disabled(self):
        run = self.preview()
        r = self.client.post(f'/api/contacts/runs/{run.pk}/apply/')
        self.assertEqual(r.status_code, 409)
        self.assertIn('disabled', r.json()['detail'])

    def test_apply_journals_every_write_and_snapshots_first(self):
        plan = self.preview()
        with override_settings(CONTACTS_CLICKUP_WRITES_ENABLED=True):
            r = self.client.post(f'/api/contacts/runs/{plan.pk}/apply/')
            self.assertEqual(r.status_code, 201, r.content)
            live = SyncRun.objects.get(pk=r.json()['id'])
            self.assertEqual(live.max_ops, runner.plan_budget(plan.ops))
            live = runner.execute_run(runner.claim(live.pk))
        self.assertEqual(live.status, SyncRun.Status.DONE, live.error)
        self.assertEqual(live.ops, plan.ops)
        self.assertEqual(ChangeLog.objects.filter(run=live, ok=True).count(), len(self.fake.writes))
        with gzip.open(self.data_dir / live.snapshot_path, 'rt') as fh:
            snap = json.load(fh)
        self.assertEqual({c['id'] for c in snap['contacts']}, {'t1', 't2', 't3'})

    def test_a_preview_can_only_be_applied_once(self):
        plan = self.preview()
        with override_settings(CONTACTS_CLICKUP_WRITES_ENABLED=True):
            self.assertEqual(self.client.post(f'/api/contacts/runs/{plan.pk}/apply/').status_code, 201)
            self.assertEqual(self.client.post(f'/api/contacts/runs/{plan.pk}/apply/').status_code, 409)

    def test_apply_refused_after_review_decisions_change(self):
        self.fake.tasks['t9'] = make_task('t9', 'New Carol', status='st-0')
        plan = self.preview()
        item = ReviewItem.objects.get(source='linkedin')
        self.client.post(f'/api/contacts/reviews/{item.pk}/decide/', {'decision': 'new'}, format='json')
        with override_settings(CONTACTS_CLICKUP_WRITES_ENABLED=True):
            r = self.client.post(f'/api/contacts/runs/{plan.pk}/apply/')
        self.assertEqual(r.status_code, 409)
        self.assertIn('Review decisions changed', r.json()['detail'])

    def test_live_run_stops_when_it_exceeds_its_budget(self):
        plan = self.preview()
        with override_settings(CONTACTS_CLICKUP_WRITES_ENABLED=True):
            live = runner.create_live_from_plan(plan)
            SyncRun.objects.filter(pk=live.pk).update(max_ops=2)
            live = runner.execute_run(runner.claim(live.pk))
        self.assertEqual(live.status, SyncRun.Status.STOPPED)
        self.assertEqual(len(self.fake.writes), 2)

    def test_only_one_run_executes_at_a_time(self):
        a = SyncRun.objects.create(source='linkedin')
        b = SyncRun.objects.create(source='linkedin')
        self.assertEqual(runner.claim().pk, a.pk)
        self.assertIsNone(runner.claim())
        self.assertIsNone(runner.claim(b.pk))

    def test_page_setup_never_overwrites_an_existing_page(self):
        from core.models import Page
        from contacts.pages import PAGE_SLUG, ensure_contact_sync_page
        Page.objects.create(slug=PAGE_SLUG, title='My title', content='mine', roles_with_access='superuser')
        page, created, _, _ = ensure_contact_sync_page()
        self.assertFalse(created)
        self.assertEqual((page.title, page.content), ('My title', 'mine'))

    def test_oauth_callback_rejects_unknown_state(self):
        r = APIClient().get('/api/contacts/oauth/callback/', {'state': 'forged', 'code': 'x'})
        self.assertEqual(r.status_code, 400)

    def test_merge_preview_and_apply(self):
        self.fake.tasks['t4'] = make_task('t4', 'Alice Smith', status='st-1', linkedin_url='https://www.linkedin.com/in/alice2')
        bad = self.client.post('/api/contacts/runs/', {'source': 'merge', 'options': {'survivor': 't1', 'loser': 't1'}},
                               format='json')
        self.assertEqual(bad.status_code, 400)
        r = self.client.post('/api/contacts/runs/', {'source': 'merge', 'options': {'survivor': 't1', 'loser': 't4'}},
                             format='json')
        self.assertEqual(r.status_code, 201, r.content)
        plan = runner.execute_run(runner.claim(r.json()['id']))
        self.assertEqual(plan.stats.get('MERGE'), 1, plan.error)
        self.assertEqual(self.fake.writes, [])
        with override_settings(CONTACTS_CLICKUP_WRITES_ENABLED=True):
            r = self.client.post(f'/api/contacts/runs/{plan.pk}/apply/')
            self.assertEqual(r.status_code, 201, r.content)
            live = runner.execute_run(runner.claim(r.json()['id']))
        self.assertEqual(live.status, SyncRun.Status.DONE, live.error)
        self.assertTrue(self.fake.tasks['t4']['archived'])
