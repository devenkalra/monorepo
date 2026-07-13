#!/usr/bin/env python3
"""Integration tests for locate_in_db.py"""

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime

_scripts = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_scripts, 'media_process'))
sys.path.insert(0, _scripts)

from locate_in_db import find_by_hash
from media_utils import calculate_file_hash, create_database_schema, set_volume


class TestLocateInDb(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, 'test.db')
        self.conn = sqlite3.connect(self.db_path)
        create_database_schema(self.conn)
        set_volume(self.conn, 'volume1', '/volume1/photo', self.test_dir)

        self.test_file1 = os.path.join(self.test_dir, 'test1.jpg')
        self.test_file2 = os.path.join(self.test_dir, 'test2.jpg')
        self.test_file3 = os.path.join(self.test_dir, 'test3.jpg')

        with open(self.test_file1, 'wb') as f:
            f.write(b'Test image 1 content')
        with open(self.test_file2, 'wb') as f:
            f.write(b'Test image 1 content')
        with open(self.test_file3, 'wb') as f:
            f.write(b'Test image 3 unique content')

        self.hash1 = calculate_file_hash(self.test_file1)
        self.hash3 = calculate_file_hash(self.test_file3)
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO files (volume, relpath, name, modified_date, size, file_hash, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('volume1', 'path/test1.jpg', 'test1.jpg', now, 20, self.hash1, now))
        cursor.execute("""
            INSERT INTO files (volume, relpath, name, modified_date, size, file_hash, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('volume1', 'path/test2.jpg', 'test2.jpg', now, 20, self.hash1, now))
        cursor.execute("""
            INSERT INTO files (volume, relpath, name, modified_date, size, file_hash, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('volume1', 'path/test3.jpg', 'test3.jpg', now, 28, self.hash3, now))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.test_dir)

    def test_find_duplicate_hash(self):
        matches = find_by_hash(self.conn, self.hash1)
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0]['relpath'], 'path/test1.jpg')
        self.assertIn('fullpath', matches[0])

    def test_find_unique_hash(self):
        matches = find_by_hash(self.conn, self.hash3)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['relpath'], 'path/test3.jpg')

    def test_find_missing_hash(self):
        matches = find_by_hash(self.conn, '0' * 64)
        self.assertEqual(matches, [])


if __name__ == '__main__':
    unittest.main()
