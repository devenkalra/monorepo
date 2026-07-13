#!/usr/bin/env python3
"""Tests for backup_media_db.py"""

import json
import os
import sqlite3
import sys
import tarfile
import tempfile
import unittest
import shutil
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backup_media_db as backup
from media_utils import create_database_schema, insert_thumbnail


class TestBackupMediaDb(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / 'source.db'
        self.backup_dir = Path(self.temp_dir) / 'backups'

        conn = sqlite3.connect(str(self.db_path))
        create_database_schema(conn)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO files (volume, relpath, name, modified_date, size, indexed_date)
            VALUES ('photo', 'a.jpg', 'a.jpg', '2024-01-01', 10, '2024-01-01')
        """)
        file_id = cursor.lastrowid
        insert_thumbnail(conn, file_id, b'old-thumb', 10, 10, created_at='2020-01-01T00:00:00')
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_metadata_backup_strips_thumbnails(self):
        rc = backup.main([
            '--db-path', str(self.db_path),
            '--backup-dir', str(self.backup_dir),
            '--metadata-only', '-v', '0',
        ])
        self.assertEqual(rc, 0)
        archives = list(self.backup_dir.glob('metadata_backup_*.tar.gz'))
        self.assertEqual(len(archives), 1)

        with tempfile.TemporaryDirectory() as tmp:
            extracted = backup.extract_tar_gz(archives[0], Path(tmp))
            conn = sqlite3.connect(str(extracted))
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            conn.close()
            self.assertIn('files', tables)
            self.assertNotIn('thumbnails', tables)

    def test_full_thumbnail_backup_and_restore(self):
        rc = backup.main([
            '--db-path', str(self.db_path),
            '--backup-dir', str(self.backup_dir),
            '--thumbnails-only', '--mode', 'full', '-v', '0',
        ])
        self.assertEqual(rc, 0)
        archives = list(self.backup_dir.glob('thumbnail_full_*.tar.gz'))
        self.assertEqual(len(archives), 1)

        target_db = Path(self.temp_dir) / 'restored.db'
        shutil.copy2(self.db_path, target_db)
        conn = sqlite3.connect(str(target_db))
        conn.execute('DELETE FROM thumbnails')
        conn.commit()
        conn.close()

        rc = backup.main([
            'restore',
            '--db-path', str(target_db),
            '--thumbnail-archive', str(archives[0]),
            '-v', '0',
        ])
        self.assertEqual(rc, 0)

        conn = sqlite3.connect(str(target_db))
        count = conn.execute('SELECT COUNT(*) FROM thumbnails').fetchone()[0]
        blob = conn.execute('SELECT thumbnail_data FROM thumbnails').fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)
        self.assertEqual(blob, b'old-thumb')

    def test_incremental_skips_old_thumbnails(self):
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO files (volume, relpath, name, modified_date, size, indexed_date)
            VALUES ('photo', 'b.jpg', 'b.jpg', '2024-01-01', 10, '2024-01-01')
        """)
        new_id = cursor.lastrowid
        insert_thumbnail(conn, new_id, b'new-thumb', 10, 10, created_at='2099-01-01T00:00:00')
        conn.commit()
        conn.close()

        rc = backup.main([
            '--db-path', str(self.db_path),
            '--backup-dir', str(self.backup_dir),
            '--thumbnails-only',
            '--since', '2090-01-01T00:00:00',
            '--no-include-missing-created-at',
            '-v', '0',
        ])
        self.assertEqual(rc, 0)
        archives = list(self.backup_dir.glob('thumbnail_patch_*.tar.gz'))
        self.assertEqual(len(archives), 1)

        with tempfile.TemporaryDirectory() as tmp:
            patch_db = backup.extract_tar_gz(archives[0], Path(tmp))
            conn = sqlite3.connect(str(patch_db))
            rows = conn.execute('SELECT thumbnail_data FROM thumbnails').fetchall()
            conn.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], b'new-thumb')

    def test_state_file_written(self):
        backup.main([
            '--db-path', str(self.db_path),
            '--backup-dir', str(self.backup_dir),
            '-v', '0',
        ])
        state_path = self.backup_dir / backup.STATE_FILENAME
        self.assertTrue(state_path.exists())
        state = json.loads(state_path.read_text(encoding='utf-8'))
        self.assertEqual(state['source_db'], str(self.db_path.resolve()))
        self.assertIn('last_metadata_backup', state)


if __name__ == '__main__':
    unittest.main()
