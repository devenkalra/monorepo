from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from people.models import Person
from people.vcf import person_fields_from_vcf


User = get_user_model()

SAMPLE_VCF = """BEGIN:VCARD
VERSION:3.0
FN:Ada Lovelace
N:Lovelace;Ada;;;
EMAIL:ada@example.com
TEL;TYPE=CELL:+1-555-0100
TITLE:Mathematician
ORG:Analytical Engines
BDAY:1815-12-10
GENDER:F
NOTE:First programmer
URL:https://example.com/ada
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Alan Turing
N:Turing;Alan;;;
EMAIL:alan@example.com
TEL:+1-555-0101
NOTE:Pioneer of
  computing
END:VCARD
"""


class VcfParseTests(TestCase):
    def test_parses_name_email_phone_and_note(self):
        people = person_fields_from_vcf(SAMPLE_VCF)
        self.assertEqual(len(people), 2)
        ada = people[0]
        self.assertEqual(ada['first_name'], 'Ada')
        self.assertEqual(ada['last_name'], 'Lovelace')
        self.assertEqual(ada['display'], 'Ada Lovelace')
        self.assertEqual(ada['emails'], ['ada@example.com'])
        self.assertEqual(ada['phones'], ['+1-555-0100'])
        self.assertEqual(ada['profession'], 'Mathematician')
        self.assertEqual(ada['description'], 'First programmer')
        self.assertEqual(ada['gender'], 'Female')
        self.assertEqual(ada['dob'].isoformat(), '1815-12-10')
        self.assertEqual(ada['urls'][0]['url'], 'https://example.com/ada')
        self.assertEqual(ada['tags'], ['imported/vcf'])

    def test_unfolds_continued_lines(self):
        alan = person_fields_from_vcf(SAMPLE_VCF)[1]
        self.assertEqual(alan['emails'], ['alan@example.com'])
        self.assertEqual(alan['last_name'], 'Turing')
        self.assertEqual(alan['description'], 'Pioneer of computing')

    def test_skips_empty_cards(self):
        people = person_fields_from_vcf('BEGIN:VCARD\nVERSION:3.0\nEND:VCARD\n')
        self.assertEqual(people, [])


class VcfImportApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='vcfuser',
            email='vcf@example.com',
            password='testpass123',
        )
        self.client.force_authenticate(user=self.user)

    def test_import_vcf_creates_people(self):
        upload = SimpleUploadedFile('contacts.vcf', SAMPLE_VCF.encode('utf-8'), content_type='text/vcard')
        response = self.client.post('/api/people/import_file/', {'file': upload}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['created'], 2)
        self.assertEqual(Person.objects.filter(user=self.user).count(), 2)
        ada = Person.objects.get(user=self.user, first_name='Ada')
        self.assertEqual(ada.last_name, 'Lovelace')
        self.assertEqual(ada.emails, ['ada@example.com'])
        self.assertEqual(ada.tags, ['imported/vcf'])

    def test_import_rejects_missing_file(self):
        response = self.client.post('/api/people/import_file/', {}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_import_rejects_wrong_extension(self):
        upload = SimpleUploadedFile('contacts.json', b'{}', content_type='application/json')
        response = self.client.post('/api/people/import_file/', {'file': upload}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
