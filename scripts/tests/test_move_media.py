#!/usr/bin/env python3
"""Integration tests for move_media.py"""

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock

_scripts = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_scripts, 'media_process'))
sys.path.insert(0, _scripts)

from move_media import update_or_insert_file, check_database_record, check_destination_file
from media_utils import create_database_schema, calculate_file_hash, set_volume, lookup_file_by_abs_path, to_storage_relpath


class TestMoveMedia(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.test_dir, 'source')
        self.dest_dir = os.path.join(self.test_dir, 'destination')
        self.db_path = os.path.join(self.test_dir, 'test.db')
        os.makedirs(self.source_dir)
        os.makedirs(self.dest_dir)

        self.conn = sqlite3.connect(self.db_path)
        create_database_schema(self.conn)
        set_volume(self.conn, 'testvolume', '/volume1/test', self.test_dir)

        self.test_file = os.path.join(self.source_dir, 'photo.jpg')
        with open(self.test_file, 'wb') as f:
            f.write(b'test image')

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.test_dir)

    def test_update_or_insert_inserts_new_file(self):
        dest_file = os.path.join(self.dest_dir, 'photo.jpg')
        shutil.copy2(self.test_file, dest_file)
        action, file_id = update_or_insert_file(
            self.conn, self.test_file, dest_file, 'TestVolume', verbose=0, dry_run=False,
        )
        self.assertEqual(action, 'inserted')
        record = lookup_file_by_abs_path(self.conn, dest_file)
        self.assertIsNotNone(record)
        self.assertEqual(record['relpath'], to_storage_relpath(dest_file, self.test_dir))

    def test_update_or_insert_updates_existing_file(self):
        now = datetime.now().isoformat()
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO files (volume, relpath, name, modified_date, size, file_hash, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('testvolume', 'source/photo.jpg', 'photo.jpg', now, 10, calculate_file_hash(self.test_file), now))
        self.conn.commit()

        dest_file = os.path.join(self.dest_dir, 'photo.jpg')
        shutil.copy2(self.test_file, dest_file)
        action, file_id = update_or_insert_file(
            self.conn, self.test_file, dest_file, 'TestVolume', verbose=0, dry_run=False,
        )
        self.assertEqual(action, 'updated')
        record = lookup_file_by_abs_path(self.conn, dest_file)
        self.assertIsNotNone(record)

    def test_check_database_record_by_relpath(self):
        now = datetime.now().isoformat()
        file_hash = calculate_file_hash(self.test_file)
        dest_file = os.path.join(self.dest_dir, 'photo.jpg')
        shutil.copy2(self.test_file, dest_file)
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO files (volume, relpath, name, modified_date, size, file_hash, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('testvolume', 'destination/photo.jpg', 'photo.jpg', now, 10, file_hash, now))
        self.conn.commit()

        exists, file_id, match_type = check_database_record(
            self.conn, dest_file, file_hash, 'TestVolume', verbose=0,
        )
        self.assertTrue(exists)
        self.assertEqual(match_type, 'exact_match')

    def test_check_destination_file(self):
        dest_file = os.path.join(self.dest_dir, 'photo.jpg')
        shutil.copy2(self.test_file, dest_file)
        source_hash = calculate_file_hash(self.test_file)
        should_skip, reason = check_destination_file(dest_file, source_hash, verbose=0)
        self.assertTrue(should_skip)


if __name__ == '__main__':
    unittest.main()
