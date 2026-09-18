from django.test import SimpleTestCase

from productions.transfer import TransferError, parse_import_document


class TransferParseTests(SimpleTestCase):
    def test_accepts_envelope_array_and_bare_object(self):
        self.assertEqual(len(parse_import_document({'productions': [{'title': 'A'}]})), 1)
        self.assertEqual(len(parse_import_document([{'title': 'A'}, {'title': 'B'}])), 2)
        self.assertEqual(parse_import_document({'title': 'A', 'scenes': []})[0]['title'], 'A')

    def test_rejects_empty_and_unknown_shapes(self):
        with self.assertRaises(TransferError):
            parse_import_document({'productions': []})
        with self.assertRaises(TransferError):
            parse_import_document({'hello': 'world'})
        with self.assertRaises(TransferError):
            parse_import_document('nope')
