import base64
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from contacts import mail_merge
from contacts.models import EntityCache, GoogleAccount, MailCampaign, MailCampaignRecipient


@override_settings(CONTACTS_WORKER_ENABLED=False)
class MailMergeTests(TestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser('admin', 'a@example.com', 'x')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=admin).key}')
        GoogleAccount.objects.create(
            email='me@example.com', refresh_token='rt',
            scopes=('https://www.googleapis.com/auth/contacts '
                    'https://www.googleapis.com/auth/gmail.compose '
                    'https://www.googleapis.com/auth/gmail.send openid email'),
        )
        self._send_as = mock.patch(
            'contacts.mail_merge.list_send_as',
            return_value=[{
                'email': 'me@example.com', 'name': 'Me',
                'is_primary': True, 'is_default': True, 'verification_status': 'accepted',
            }],
        )
        self._send_as.start()
        self.addCleanup(self._send_as.stop)
        for tid, name, emails in (
            ('ada', 'Ada Lovelace', 'ada@example.com'),
            ('bob', 'Bob Jones', 'bob@example.com, bob2@example.com'),
            ('noemail', 'No Mail', ''),
            ('org1', 'Acme', 'ops@acme.com'),
        ):
            EntityCache.objects.create(task_id=tid, list_key='people' if tid != 'org1' else 'orgs', row={
                'id': tid, 'list': 'people' if tid != 'org1' else 'orgs', 'name': name,
                'emails': emails, 'email': '', 'company': 'Analytical', 'title': '',
                'groups': [], 'outreach': ['Diwali'], 'match': 'active', 'archived': False,
                'google_id': '', 'phones': '',
                'psalutation': 'Ada' if tid == 'ada' else '',
                'fsalutation': 'Lovelace' if tid == 'ada' else '',
            })

    def test_render_tokens(self):
        self.assertEqual(
            mail_merge.render('Hi {{ first_name }} at {{company}}', {'first_name': 'Ada', 'company': 'X'}),
            'Hi Ada at X',
        )
        self.assertEqual(mail_merge.render('{{missing}}', {}), '')
        # Gmail sometimes wraps token pieces in tags.
        self.assertEqual(
            mail_merge.render('Hi {{<span>first_name</span>}}', {'first_name': 'Ada'}),
            'Hi Ada',
        )
        self.assertEqual(
            mail_merge.render('<b>{{first_name}}</b>', {'first_name': 'A<B>'}, escape_html=True),
            '<b>A&lt;B&gt;</b>',
        )
        data = mail_merge._merge_data(
            {'name': 'Ada Lovelace', 'emails': 'a@x.com', 'psalutation': 'Ada', 'fsalutation': 'Lovelace',
             'company': '', 'title': '', 'phones': '', 'groups': [], 'outreach': []},
            'Ada',
        )
        self.assertEqual(data['PSalutation'], 'Ada')
        self.assertEqual(data['FSalutation'], 'Lovelace')
        self.assertEqual(
            mail_merge.render('Dear {{PSalutation}} {{FSalutation}}', data),
            'Dear Ada Lovelace',
        )
        # Gmail drafts often use single braces.
        self.assertEqual(
            mail_merge.render('Dear {PSalutation},', data),
            'Dear Ada,',
        )
        self.assertEqual(
            mail_merge.render('keep {unknown} and {PSalutation}', data),
            'keep {unknown} and Ada',
        )

    def test_load_draft_template(self):
        html_body = base64.urlsafe_b64encode(
            b'<p>Hello {{first_name}}</p>').decode().rstrip('=')
        pdf_b64 = base64.urlsafe_b64encode(b'%PDF-1.4 fake').decode().rstrip('=')

        class FakeAttachments:
            def get(self, **kwargs):
                return FakeExec({'data': pdf_b64, 'size': 12})

        class FakeMessages:
            def attachments(self):
                return FakeAttachments()

        class FakeDrafts:
            def list(self, **kwargs):
                return FakeExec({'drafts': [{'id': 'd1'}]})

            def get(self, **kwargs):
                return FakeExec({
                    'id': 'd1',
                    'message': {
                        'id': 'msg1',
                        'snippet': 'Hello',
                        'payload': {
                            'headers': [{'name': 'Subject', 'value': 'Hi {{first_name}}'}],
                            'mimeType': 'multipart/mixed',
                            'parts': [
                                {
                                    'mimeType': 'text/html',
                                    'body': {'data': html_body},
                                },
                                {
                                    'filename': 'flyer.pdf',
                                    'mimeType': 'application/pdf',
                                    'body': {'attachmentId': 'att1', 'size': 12},
                                    'headers': [{
                                        'name': 'Content-Disposition',
                                        'value': 'attachment; filename="flyer.pdf"',
                                    }],
                                },
                            ],
                        },
                    },
                })

        class FakeExec:
            def __init__(self, data):
                self._data = data

            def execute(self):
                return self._data

        class FakeUsers:
            def drafts(self):
                return FakeDrafts()

            def messages(self):
                return FakeMessages()

        class FakeService:
            def users(self):
                return FakeUsers()

        with mock.patch('contacts.google_auth.gmail_service', return_value=FakeService()):
            tpl = mail_merge.load_draft_template('d1')
            drafts = mail_merge.list_gmail_drafts()
            out = mail_merge.create_campaign(
                ids=['ada'],
                gmail_draft_id='d1',
                name='From draft',
            )
        self.assertEqual(tpl['subject'], 'Hi {{first_name}}')
        self.assertIn('{{first_name}}', tpl['html'])
        self.assertTrue(tpl['has_html'])
        self.assertEqual(tpl['attachment_names'], ['flyer.pdf'])
        self.assertEqual(drafts[0]['id'], 'd1')
        self.assertTrue(drafts[0]['has_attachments'])
        camp = MailCampaign.objects.get(pk=out['id'])
        self.assertEqual(camp.source_draft_id, 'd1')
        self.assertTrue(camp.body_html_template)
        self.assertEqual(len(camp.attachments), 1)
        self.assertEqual(camp.attachments[0]['filename'], 'flyer.pdf')
        self.assertIn('Ada', out['preview'][0]['body_html'])
        self.assertEqual(out['attachment_names'], ['flyer.pdf'])

        raw = mail_merge._mime_raw(
            'ada@example.com', 'Hi', 'plain', '<p>x</p>', 'me@example.com',
            attachments=camp.attachments,
        )
        decoded = base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4))
        self.assertIn(b'flyer.pdf', decoded)
        # Attachment payload is base64-transfer-encoded inside the MIME message.
        self.assertIn(base64.b64encode(b'%PDF-1.4 fake'), decoded)

    def test_create_skips_and_freezes_audience(self):
        out = mail_merge.create_campaign(
            ids=['ada', 'bob', 'noemail', 'org1', 'ada'],
            subject_template='Hi {{first_name}}',
            body_template='Hello {{name}}',
            name='Test',
            user='tester',
        )
        self.assertEqual(out['counts']['total'], 2)
        reasons = {s['reason'] for s in out['skipped_on_create']}
        self.assertTrue(any('no email' in r for r in reasons))
        self.assertTrue(any('not a person' in r for r in reasons))
        self.assertTrue(any('duplicate' in r for r in reasons))
        camp = MailCampaign.objects.get(pk=out['id'])
        self.assertEqual(camp.status, MailCampaign.Status.READY)
        emails = set(camp.recipients.values_list('email', flat=True))
        self.assertEqual(emails, {'ada@example.com', 'bob@example.com'})

    def test_throttle_and_resume(self):
        out = mail_merge.create_campaign(
            ids=['ada', 'bob'],
            subject_template='S',
            body_template='B {{first_name}}',
            daily_limit=1,
            per_minute=10,
        )
        camp_id = out['id']
        mail_merge.start_campaign(camp_id)

        class FakeExec:
            def __init__(self, data):
                self._data = data

            def execute(self):
                return self._data

        class FakeDrafts:
            def __init__(self):
                self.n = 0

            def create(self, **kwargs):
                self.n += 1
                return FakeExec({'id': f'draft-{self.n}'})

        class FakeUsers:
            def __init__(self):
                self._drafts = FakeDrafts()

            def drafts(self):
                return self._drafts

        class FakeService:
            def __init__(self):
                self._users = FakeUsers()

            def users(self):
                return self._users

        svc = FakeService()
        with mock.patch('contacts.google_auth.gmail_service', return_value=svc):
            n = mail_merge.tick_campaign(MailCampaign.objects.get(pk=camp_id))
        self.assertEqual(n, 1)
        camp = MailCampaign.objects.get(pk=camp_id)
        self.assertEqual(camp.status, MailCampaign.Status.WAITING_QUOTA)
        self.assertEqual(camp.recipients.filter(status='drafted').count(), 1)
        self.assertEqual(camp.recipients.filter(status='pending').count(), 1)

        # Simulate next day by moving sent_at to yesterday, then resume.
        MailCampaignRecipient.objects.filter(campaign=camp, status='drafted').update(
            sent_at=timezone.now() - timedelta(days=1))
        camp.status = MailCampaign.Status.WAITING_QUOTA
        camp.save(update_fields=['status'])
        with mock.patch('contacts.google_auth.gmail_service', return_value=svc):
            n = mail_merge.tick_campaign(MailCampaign.objects.get(pk=camp_id))
        self.assertEqual(n, 1)
        camp = MailCampaign.objects.get(pk=camp_id)
        self.assertEqual(camp.status, MailCampaign.Status.COMPLETED)
        self.assertEqual(camp.recipients.filter(status='drafted').count(), 2)

    def test_api_create_and_start(self):
        r = self.client.post('/api/contacts/mail-campaigns/', {
            'ids': ['ada'],
            'subject_template': 'Hi {{first_name}}',
            'body_template': 'Body',
            'delivery': 'draft',
            'daily_limit': 50,
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        cid = r.json()['id']
        r2 = self.client.post(f'/api/contacts/mail-campaigns/{cid}/action/', {'action': 'start'}, format='json')
        self.assertEqual(r2.status_code, 200, r2.content)
        self.assertEqual(r2.json()['status'], 'running')
