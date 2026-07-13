#!/usr/bin/env python3
"""Tests for search_media.py"""

import io
import os
import sqlite3
import sys
import tempfile
import unittest
import unittest.mock
import shutil
from contextlib import redirect_stdout

_scripts = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _scripts)

from media_utils import create_database_schema, set_volume
import search_media

# (after, before) date filter value pairs in different user formats
DATE_RANGE_FORMATS = [
    ('20240601', '20240630'),
    ('2024-06-01', '2024-06-30'),
    ('2024/06/01', '2024/06/30'),
]

DATE_TAKEN_RANGE_FORMATS = [
    ('20260101', '20260130'),
    ('2026-01-01', '2026-01-30'),
    ('2026/01/01', '2026/01/30'),
]


class TestSearchMedia(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.mount = os.path.join(self.temp_dir, 'mount')
        os.makedirs(self.mount)
        self.conn = sqlite3.connect(self.db_path)
        create_database_schema(self.conn)
        set_volume(self.conn, 'testvol', '/volume1/test', self.mount)

        test_file = os.path.join(self.mount, 'vacation', 'beach.jpg')
        os.makedirs(os.path.dirname(test_file), exist_ok=True)
        with open(test_file, 'wb') as f:
            f.write(b'jpeg')

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO files (volume, relpath, name, created_date, modified_date, size, file_hash,
                               mime_type, extension, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('testvol', 'vacation/beach.jpg', 'beach.jpg',
              '2024-06-01T08:00:00', '2024-06-01T12:00:00',
              4, 'abc', 'image/jpeg', '.jpg', '2024-06-02T10:00:00'))
        file_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO image_metadata (file_id, width, height, city, keywords)
            VALUES (?, 100, 80, 'Fort Worth', 'vacation, beach')
        """, (file_id,))
        cursor.execute("""
            INSERT INTO thumbnails (file_id, thumbnail_data, thumbnail_width, thumbnail_height, created_at)
            VALUES (?, ?, 10, 10, ?)
        """, (file_id, b'thumb', '2024-06-02T10:00:00'))
        self.conn.commit()
        self.conn.close()
        self.file_id = file_id
        self.test_file = test_file

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_lookup_by_id(self):
        rc = search_media.main(['--db-path', self.db_path, '--id', str(self.file_id)])
        self.assertEqual(rc, 0)

    def test_search_by_name(self):
        rc = search_media.main(['--db-path', self.db_path, '--name', 'beach'])
        self.assertEqual(rc, 0)

    def test_search_metadata(self):
        rc = search_media.main([
            '--db-path', self.db_path, '--metadata', 'Fort Worth',
            '--show', 'metadata', '--json',
        ])
        self.assertEqual(rc, 0)

    def test_lookup_by_path(self):
        rc = search_media.main(['--db-path', self.db_path, '--path', self.test_file, '--json'])
        self.assertEqual(rc, 0)

    def test_count_only(self):
        rc = search_media.main(['--db-path', self.db_path, '--name', 'beach', '--count-only'])
        self.assertEqual(rc, 0)

    def test_pagination_start(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for i, name in enumerate(['aaa.jpg', 'bbb.jpg', 'ccc.jpg'], start=1):
            cursor.execute("""
                INSERT INTO files (volume, relpath, name, modified_date, size, file_hash,
                                   mime_type, extension, indexed_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ('testvol', f'pics/{name}', name, '2024-06-01T12:00:00',
                  4, f'hash{i}', 'image/jpeg', '.jpg', f'2024-06-0{i}T10:00:00'))
        conn.commit()
        conn.close()

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = search_media.main([
                '--db-path', self.db_path, '--relpath-pattern', 'pics/%',
                '--order-by', 'f.indexed_date ASC', '--start', '1', '--limit', '1',
            ])
        self.assertEqual(rc, 0)
        self.assertIn('bbb.jpg', buf.getvalue())
        self.assertNotIn('aaa.jpg', buf.getvalue())

    def test_show_full(self):
        with unittest.mock.patch.object(search_media, 'open_path') as mock_open:
            rc = search_media.main([
                '--db-path', self.db_path, '--path', self.test_file, '--show', 'full',
            ])
        self.assertEqual(rc, 0)
        mock_open.assert_called_once()

    def test_show_full_max_five(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        paths = []
        for i in range(7):
            name = f'pic{i}.jpg'
            rel = f'open/{name}'
            abs_path = os.path.join(self.mount, rel.replace('/', os.sep))
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, 'wb') as f:
                f.write(b'x')
            paths.append(abs_path)
            cursor.execute("""
                INSERT INTO files (volume, relpath, name, modified_date, size, file_hash,
                                   mime_type, extension, indexed_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ('testvol', rel, name, '2024-06-01T12:00:00',
                  1, f'h{i}', 'image/jpeg', '.jpg', f'2024-06-01T10:00:0{i}'))
        conn.commit()
        conn.close()

        with unittest.mock.patch.object(search_media, 'open_path') as mock_open:
            rc = search_media.main([
                '--db-path', self.db_path, '--relpath-pattern', 'open/%',
                '--show', 'full', '--limit', '10',
            ])
        self.assertEqual(rc, 0)
        self.assertEqual(mock_open.call_count, search_media.MAX_OPEN_FILES)

    def _run_search(self, extra_args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = search_media.main(['--db-path', self.db_path, *extra_args])
        return rc, buf.getvalue()

    def test_date_taken_range_formats(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE image_metadata SET date_taken = '2026:01:09 14:30:00' WHERE file_id = ?
        """, (self.file_id,))
        conn.commit()
        conn.close()

        for after_fmt, before_fmt in DATE_TAKEN_RANGE_FORMATS:
            with self.subTest(after=after_fmt, before=before_fmt):
                rc, _ = self._run_search([
                    '--date-taken-after', after_fmt,
                    '--date-taken-before', before_fmt,
                    '--limit', '1',
                ])
                self.assertEqual(rc, 0)

        for after_fmt, before_fmt in DATE_TAKEN_RANGE_FORMATS:
            with self.subTest(exclude_after=after_fmt, exclude_before=before_fmt):
                rc, _ = self._run_search([
                    '--date-taken-after', '20260110',
                    '--date-taken-before', before_fmt,
                    '--limit', '1',
                ])
                self.assertEqual(rc, 1)

    def test_indexed_date_range_formats(self):
        for after_fmt, before_fmt in DATE_RANGE_FORMATS:
            with self.subTest(after=after_fmt, before=before_fmt):
                rc, out = self._run_search([
                    '--indexed-after', after_fmt,
                    '--indexed-before', before_fmt,
                    '--limit', '1',
                ])
                self.assertEqual(rc, 0)
                self.assertIn('beach.jpg', out)

    def test_modified_date_range_formats(self):
        for after_fmt, before_fmt in DATE_RANGE_FORMATS:
            with self.subTest(after=after_fmt, before=before_fmt):
                rc, out = self._run_search([
                    '--modified-after', after_fmt,
                    '--modified-before', before_fmt,
                    '--limit', '1',
                ])
                self.assertEqual(rc, 0)
                self.assertIn('beach.jpg', out)

    def test_created_date_range_formats(self):
        for after_fmt, before_fmt in DATE_RANGE_FORMATS:
            with self.subTest(after=after_fmt, before=before_fmt):
                rc, out = self._run_search([
                    '--created-after', after_fmt,
                    '--created-before', before_fmt,
                    '--limit', '1',
                ])
                self.assertEqual(rc, 0)
                self.assertIn('beach.jpg', out)

    def test_date_filters_exclude_out_of_range(self):
        cases = [
            ('--indexed-after', '20240701', '--indexed-before', '20240731'),
            ('--modified-after', '20240701', '--modified-before', '20240731'),
            ('--created-after', '20240701', '--created-before', '20240731'),
            ('--date-taken-after', '20260101', '--date-taken-before', '20260105'),
        ]
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE image_metadata SET date_taken = '2026:01:09 14:30:00' WHERE file_id = ?",
            (self.file_id,),
        )
        conn.commit()
        conn.close()

        for after_arg, after_val, before_arg, before_val in cases:
            with self.subTest(filter=f'{after_arg}/{before_arg}'):
                rc, _ = self._run_search([
                    after_arg, after_val, before_arg, before_val, '--limit', '1',
                ])
                self.assertEqual(rc, 1)

    def test_date_taken_range(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE image_metadata SET date_taken = '2026:01:09 14:30:00' WHERE file_id = ?
        """, (self.file_id,))
        conn.commit()
        conn.close()

        rc, _ = self._run_search([
            '--date-taken-after', '20260101',
            '--date-taken-before', '20260130', '--limit', '1',
        ])
        self.assertEqual(rc, 0)

        rc, _ = self._run_search([
            '--date-taken-after', '20260110',
            '--date-taken-before', '20260130', '--limit', '1',
        ])
        self.assertEqual(rc, 1)

    def test_show_comma_separated(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf), unittest.mock.patch.object(search_media.webbrowser, 'open', return_value=True):
            rc = search_media.main([
                '--db-path', self.db_path, '--id', str(self.file_id),
                '--show', 'basic,thumbnail', '--no-save',
            ])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn('Thumb', out)
        self.assertIn('yes', out)
        self.assertIn('Thumbnail grid', out)

    def test_thumbnail_list_only(self):
        with unittest.mock.patch.object(search_media.webbrowser, 'open', return_value=True):
            rc = search_media.main([
                '--db-path', self.db_path, '--id', str(self.file_id),
                '--show', 'basic,thumbnail', '--no-save',
            ])
        self.assertEqual(rc, 0)


if __name__ == '__main__':
    unittest.main()
