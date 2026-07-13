#!/usr/bin/env python3
"""
Comprehensive test suite for index_media.py

Tests all functions, parameter combinations, and edge cases for 100% code coverage.
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from datetime import datetime

_scripts = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_scripts, 'media_process'))
sys.path.insert(0, _scripts)

import index_media
from media_utils import create_database_schema, set_volume


class TestIndexMediaHelpers(unittest.TestCase):
    """Test helper functions in index_media.py"""
    
    def test_should_skip_path_literal(self):
        """Test literal pattern matching for skip paths"""
        # Literal string matching
        self.assertTrue(index_media.should_skip_path("/path/to/thumb.jpg", ["thumb"], literal=True))
        self.assertTrue(index_media.should_skip_path("/path/to/thumbnail/file.jpg", ["thumbnail"], literal=True))
        self.assertFalse(index_media.should_skip_path("/path/to/photo.jpg", ["thumb"], literal=True))
        
        # Multiple patterns
        self.assertTrue(index_media.should_skip_path("/path/@eaDir/file.jpg", ["@eaDir", ".DS_Store"], literal=True))
        self.assertTrue(index_media.should_skip_path("/path/.DS_Store", ["@eaDir", ".DS_Store"], literal=True))
        
        # Empty patterns
        self.assertFalse(index_media.should_skip_path("/path/to/file.jpg", [], literal=True))
    
    def test_should_skip_path_regex(self):
        """Test regex pattern matching for skip paths"""
        # Regex matching
        self.assertTrue(index_media.should_skip_path("/path/to/thumb_001.jpg", [r"thumb_\d+"], literal=False))
        self.assertTrue(index_media.should_skip_path("/path/to/file.bak", [r"\.bak$"], literal=False))
        self.assertFalse(index_media.should_skip_path("/path/to/photo.jpg", [r"\.bak$"], literal=False))
        
        # Case sensitivity
        self.assertTrue(index_media.should_skip_path("/path/THUMB/file.jpg", [r"(?i)thumb"], literal=False))
        
        # Invalid regex (should handle gracefully)
        self.assertFalse(index_media.should_skip_path("/path/to/file.jpg", [r"[invalid("], literal=False))
    
    def test_matches_include_pattern_literal(self):
        """Test literal pattern matching for include paths"""
        # Literal string matching
        self.assertTrue(index_media.matches_include_pattern("/path/to/photo.jpg", [".jpg"], literal=True))
        self.assertTrue(index_media.matches_include_pattern("/path/2024/photo.jpg", ["2024"], literal=True))
        self.assertFalse(index_media.matches_include_pattern("/path/to/photo.png", [".jpg"], literal=True))
        
        # Multiple patterns (OR logic)
        self.assertTrue(index_media.matches_include_pattern("/path/to/photo.jpg", [".jpg", ".png"], literal=True))
        self.assertTrue(index_media.matches_include_pattern("/path/to/photo.png", [".jpg", ".png"], literal=True))
        
        # Empty patterns (match all)
        self.assertTrue(index_media.matches_include_pattern("/path/to/file.jpg", [], literal=True))
    
    def test_matches_include_pattern_regex(self):
        """Test regex pattern matching for include paths"""
        # Regex matching
        self.assertTrue(index_media.matches_include_pattern("/path/to/photo.jpg", [r"\.(jpg|png)$"], literal=False))
        self.assertTrue(index_media.matches_include_pattern("/path/2024/photo.jpg", [r"202[0-9]"], literal=False))
        self.assertFalse(index_media.matches_include_pattern("/path/to/photo.gif", [r"\.(jpg|png)$"], literal=False))
        
        # Path separator matching
        self.assertTrue(index_media.matches_include_pattern("/path/to/photo.jpg", [r"[/\\]photo\.jpg$"], literal=False))

        # Substring match anywhere in Windows path
        self.assertTrue(index_media.matches_include_pattern(
            r"p:\2026\01\07 Christchurch\IMG_3313.JPG", ["3313"], literal=False
        ))
        
        # Invalid regex (should handle gracefully)
        self.assertFalse(index_media.matches_include_pattern("/path/to/file.jpg", [r"[invalid("], literal=False))


class TestIndexMediaDatabase(unittest.TestCase):
    """Test database operations in index_media.py"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.conn = sqlite3.connect(self.db_path)
        create_database_schema(self.conn)
        set_volume(self.conn, 'testvol', '/volume1/test', self.temp_dir)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.temp_dir)

    def test_check_file_exists_relpath(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO files (relpath, volume, name, size, file_hash, mime_type, extension, modified_date, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("photos/photo.jpg", "testvol", "photo.jpg", 1000, "abc123", "image/jpeg", ".jpg", "2024-01-01T12:00:00", "2024-01-01T12:00:00"))
        self.conn.commit()

        file_info = {"relpath": "photos/photo.jpg", "volume": "testvol"}
        self.assertTrue(index_media.check_file_exists(file_info, ["relpath"], self.conn))
        self.assertFalse(index_media.check_file_exists({"relpath": "other.jpg", "volume": "testvol"}, ["relpath"], self.conn))

    def test_check_file_exists_volume(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO files (relpath, volume, name, size, file_hash, mime_type, extension, modified_date, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("photos/photo.jpg", "testvol", "photo.jpg", 1000, "abc123", "image/jpeg", ".jpg", "2024-01-01T12:00:00", "2024-01-01T12:00:00"))
        self.conn.commit()

        file_info = {"relpath": "photos/photo.jpg", "volume": "testvol"}
        self.assertTrue(index_media.check_file_exists(file_info, ["volume"], self.conn))
        self.assertFalse(index_media.check_file_exists({**file_info, "volume": "othervol"}, ["volume"], self.conn))

    def test_check_file_exists_hash(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO files (relpath, volume, name, size, file_hash, mime_type, extension, modified_date, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("photos/photo.jpg", "testvol", "photo.jpg", 1000, "abc123", "image/jpeg", ".jpg", "2024-01-01T12:00:00", "2024-01-01T12:00:00"))
        self.conn.commit()

        self.assertTrue(index_media.check_file_exists({"file_hash": "abc123", "volume": "testvol"}, ["hash"], self.conn))
        self.assertFalse(index_media.check_file_exists({"file_hash": "xyz789", "volume": "testvol"}, ["hash"], self.conn))

    def test_check_file_exists_multiple_criteria(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO files (relpath, volume, name, size, file_hash, mime_type, extension, modified_date, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("photos/photo.jpg", "testvol", "photo.jpg", 1000, "abc123", "image/jpeg", ".jpg", "2024-01-01T12:00:00", "2024-01-01T12:00:00"))
        self.conn.commit()

        file_info = {
            "relpath": "photos/photo.jpg",
            "volume": "testvol",
            "size": 1000,
            "file_hash": "abc123",
        }
        self.assertTrue(index_media.check_file_exists(file_info, ["relpath", "size", "hash"], self.conn))
        self.assertFalse(index_media.check_file_exists({**file_info, "size": 2000}, ["relpath", "size", "hash"], self.conn))

    def test_record_skipped_file(self):
        timestamp = datetime.now().isoformat()
        skipped_path = os.path.join(self.temp_dir, "skip.jpg")
        open(skipped_path, 'wb').close()
        index_media.record_skipped_file(skipped_path, "unsupported_file_type", "TestVol", self.temp_dir, timestamp, self.conn)

        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM skipped_files WHERE skip_reason = ?", ("unsupported_file_type",))
        result = cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[2], "skip.jpg")
        self.assertEqual(result[4], "testvol")


class TestIndexMediaFileProcessing(unittest.TestCase):
    """Test file processing in index_media.py"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.conn = sqlite3.connect(self.db_path)
        create_database_schema(self.conn)
        set_volume(self.conn, 'testvol', '/volume1/test', self.temp_dir)

        self.test_image = os.path.join(self.temp_dir, "test_photo.jpg")
        with open(self.test_image, 'wb') as f:
            f.write(b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00')
            f.write(b'\x00' * 100)
            f.write(b'\xFF\xD9')

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.temp_dir)

    def test_process_file_new_image(self):
        timestamp = datetime.now().isoformat()
        success, skip_reason, was_update = index_media.process_file(
            self.test_image, "TestVol", self.temp_dir, timestamp, ["relpath"], 0, False, self.conn
        )

        self.assertTrue(success)
        self.assertIsNone(skip_reason)
        self.assertFalse(was_update)

        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM files WHERE relpath = ?", ("test_photo.jpg",))
        result = cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[2], "test_photo.jpg")
        self.assertEqual(result[1], "testvol")

    def test_process_file_update_existing(self):
        cursor = self.conn.cursor()
        old_hash = "old_hash_value"
        cursor.execute("""
            INSERT INTO files (relpath, volume, name, size, file_hash, mime_type, extension, modified_date, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("test_photo.jpg", "testvol", "test_photo.jpg", 1000, old_hash, "image/jpeg", ".jpg", "2024-01-01T12:00:00", "2024-01-01T12:00:00"))
        self.conn.commit()

        timestamp = datetime.now().isoformat()
        success, skip_reason, was_update = index_media.process_file(
            self.test_image, "TestVol", self.temp_dir, timestamp, ["size"], 0, False, self.conn
        )

        self.assertTrue(success)
        self.assertIsNone(skip_reason)
        self.assertTrue(was_update)

        cursor.execute("SELECT file_hash FROM files WHERE relpath = ?", ("test_photo.jpg",))
        new_hash = cursor.fetchone()[0]
        self.assertNotEqual(new_hash, old_hash)

    def test_process_file_dry_run(self):
        timestamp = datetime.now().isoformat()
        success, skip_reason, was_update = index_media.process_file(
            self.test_image, "TestVol", self.temp_dir, timestamp, ["relpath"], 1, True, self.conn
        )

        self.assertTrue(success)
        self.assertIsNone(skip_reason)

        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM files WHERE relpath = ?", ("test_photo.jpg",))
        self.assertIsNone(cursor.fetchone())

    def test_process_file_already_exists(self):
        timestamp1 = datetime.now().isoformat()
        success1, _, _ = index_media.process_file(
            self.test_image, "TestVol", self.temp_dir, timestamp1, ["relpath"], 0, False, self.conn
        )
        self.assertTrue(success1)

        timestamp2 = datetime.now().isoformat()
        success2, skip_reason, was_update = index_media.process_file(
            self.test_image, "TestVol", self.temp_dir, timestamp2, ["relpath"], 0, False, self.conn
        )

        self.assertFalse(success2)
        self.assertIsNotNone(skip_reason)
        self.assertIn("already_indexed", skip_reason)
        self.assertFalse(was_update)

    def test_dry_run_records_already_indexed_skip_reason(self):
        """Dry-run scan should record process_file skip reasons in skipped_files."""
        scan_dir = os.path.join(self.temp_dir, "2026", "01", "07 Christchurch")
        os.makedirs(scan_dir)
        img_3313 = os.path.join(scan_dir, "IMG_3313.jpg")
        shutil.copy(self.test_image, img_3313)

        timestamp1 = datetime.now().isoformat()
        index_media.process_file(
            img_3313, "TestVol", self.temp_dir, timestamp1, ["relpath", "volume"], 0, False, self.conn
        )

        timestamp2 = datetime.now().isoformat()
        added, updated, skipped = index_media.scan_directory(
            self.temp_dir, os.path.join("2026", "01", "07 Christchurch"), "TestVol",
            [], ["3313"], None, ["relpath", "volume"], 0, True, False, timestamp2, self.conn,
        )

        self.assertEqual(added, 0)
        self.assertEqual(updated, 0)
        self.assertEqual(skipped, 1)

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT skip_reason FROM skipped_files WHERE run_timestamp = ?",
            (timestamp2,),
        )
        reasons = [row[0] for row in cursor.fetchall()]
        self.assertEqual(len(reasons), 1)
        self.assertIn("already_indexed", reasons[0])

    def test_process_file_unknown_type(self):
        unknown_path = os.path.join(self.temp_dir, "archive.zip")
        with open(unknown_path, 'wb') as f:
            f.write(b'PK\x03\x04')

        timestamp = datetime.now().isoformat()
        success, skip_reason, was_update = index_media.process_file(
            unknown_path, "TestVol", self.temp_dir, timestamp, ["relpath"], 0, False, self.conn
        )

        self.assertTrue(success)
        self.assertIsNone(skip_reason)
        self.assertFalse(was_update)

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT mime_type, file_hash, extension FROM files WHERE relpath = ?",
            ("archive.zip",),
        )
        mime_type, file_hash, extension = cursor.fetchone()
        self.assertIn('zip', mime_type)
        self.assertIsNotNone(file_hash)
        self.assertEqual(extension, ".zip")
        cursor.execute(
            "SELECT COUNT(*) FROM thumbnails WHERE file_id = (SELECT id FROM files WHERE relpath = ?)",
            ("archive.zip",),
        )
        self.assertEqual(cursor.fetchone()[0], 0)

    def test_process_file_unrecognized_extension_uses_unknown_mime(self):
        unknown_path = os.path.join(self.temp_dir, "data.xyz123")
        with open(unknown_path, 'wb') as f:
            f.write(b'binary')

        timestamp = datetime.now().isoformat()
        success, skip_reason, _ = index_media.process_file(
            unknown_path, "TestVol", self.temp_dir, timestamp, ["relpath"], 0, False, self.conn
        )

        self.assertTrue(success)
        self.assertIsNone(skip_reason)
        cursor = self.conn.cursor()
        cursor.execute("SELECT mime_type FROM files WHERE relpath = ?", ("data.xyz123",))
        self.assertEqual(cursor.fetchone()[0], "UNKNOWN")

    def test_process_file_document_and_email(self):
        doc_path = os.path.join(self.temp_dir, "notes.txt")
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write("hello document")

        eml_path = os.path.join(self.temp_dir, "mail.eml")
        with open(eml_path, 'w', encoding='utf-8') as f:
            f.write("From: a@example.com\nTo: b@example.com\nSubject: Hi\n\nBody\n")

        timestamp = datetime.now().isoformat()
        self.assertTrue(index_media.process_file(doc_path, "TestVol", self.temp_dir, timestamp, ["relpath"], 0, False, self.conn)[0])
        self.assertTrue(index_media.process_file(eml_path, "TestVol", self.temp_dir, timestamp, ["relpath"], 0, False, self.conn)[0])

        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM document_metadata")
        self.assertEqual(cursor.fetchone()[0], 1)
        cursor.execute("SELECT COUNT(*) FROM email_metadata")
        self.assertEqual(cursor.fetchone()[0], 1)

    def test_process_file_nonexistent(self):
        timestamp = datetime.now().isoformat()
        success, skip_reason, was_update = index_media.process_file(
            "/nonexistent/file.jpg", "TestVol", self.temp_dir, timestamp, ["relpath"], 0, False, self.conn
        )

        self.assertFalse(success)
        self.assertIsNotNone(skip_reason)


class TestIndexMediaScanDirectory(unittest.TestCase):
    """Test directory scanning in index_media.py"""
    
    def setUp(self):
        """Create test directory structure"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.conn = sqlite3.connect(self.db_path)
        create_database_schema(self.conn)
        
        # Create directory structure
        self.photo_dir = os.path.join(self.temp_dir, "photos")
        self.sub_dir1 = os.path.join(self.photo_dir, "2024")
        self.sub_dir2 = os.path.join(self.photo_dir, "2023")
        self.thumb_dir = os.path.join(self.photo_dir, "thumbnails")
        
        os.makedirs(self.sub_dir1)
        os.makedirs(self.sub_dir2)
        os.makedirs(self.thumb_dir)
        
        # Create test files
        self.create_test_image(os.path.join(self.sub_dir1, "photo1.jpg"))
        self.create_test_image(os.path.join(self.sub_dir1, "photo2.jpg"))
        self.create_test_image(os.path.join(self.sub_dir2, "photo3.jpg"))
        self.create_test_image(os.path.join(self.thumb_dir, "thumb1.jpg"))
        
        # Create non-image file
        with open(os.path.join(self.sub_dir1, "readme.txt"), 'w') as f:
            f.write("test")
    
    def tearDown(self):
        """Clean up"""
        self.conn.close()
        shutil.rmtree(self.temp_dir)
    
    def create_test_image(self, path):
        """Create a minimal valid JPEG"""
        with open(path, 'wb') as f:
            f.write(b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00')
            f.write(b'\x00' * 100)
            f.write(b'\xFF\xD9')
    
    @patch('index_media.process_file')
    def test_scan_directory_all_files(self, mock_process):
        """Test scanning all files without filters"""
        mock_process.return_value = (True, None, False)
        
        timestamp = datetime.now().isoformat()
        added, updated, skipped = index_media.scan_directory(
            self.photo_dir, "", "TestVol", [], [], None, ["relpath"], 0, False, False, timestamp, self.conn
        )
        
        # Should process 5 files total (4 images + 1 text file)
        self.assertEqual(mock_process.call_count, 5)
    
    @patch('index_media.process_file')
    def test_scan_directory_with_include_pattern(self, mock_process):
        """Test scanning with include pattern"""
        mock_process.return_value = (True, None, False)
        
        timestamp = datetime.now().isoformat()
        added, updated, skipped = index_media.scan_directory(
            self.photo_dir, "", "TestVol", [], ["2024"], None, ["relpath"], 0, False, False, timestamp, self.conn
        )
        
        # Should process only files in 2024 directory (2 images + 1 text file)
        self.assertEqual(mock_process.call_count, 3)
    
    @patch('index_media.process_file')
    def test_scan_directory_with_skip_pattern(self, mock_process):
        """Test scanning with skip pattern"""
        mock_process.return_value = (True, None, False)
        
        timestamp = datetime.now().isoformat()
        added, updated, skipped = index_media.scan_directory(
            self.photo_dir, "", "TestVol", ["thumbnails"], [], None, ["relpath"], 0, False, False, timestamp, self.conn
        )
        
        # Should skip thumbnails directory (3 images in 2024+2023 + 1 text file)
        self.assertEqual(mock_process.call_count, 4)
    
    @patch('index_media.process_file')
    def test_scan_directory_with_max_depth(self, mock_process):
        """Test scanning with max depth limit"""
        mock_process.return_value = (True, None, False)
        
        timestamp = datetime.now().isoformat()
        added, updated, skipped = index_media.scan_directory(
            self.photo_dir, "", "TestVol", [], [], 0, ["relpath"], 0, False, False, timestamp, self.conn
        )
        
        # Should not recurse into subdirectories
        self.assertEqual(mock_process.call_count, 0)
    
    @patch('index_media.process_file')
    def test_scan_directory_with_limit(self, mock_process):
        """Test scanning with file limit"""
        mock_process.return_value = (True, None, False)
        
        timestamp = datetime.now().isoformat()
        added, updated, skipped = index_media.scan_directory(
            self.photo_dir, "", "TestVol", [], [], None, ["relpath"], 0, False, False, timestamp, self.conn, limit=2
        )
        
        # Should process only 2 files
        self.assertEqual(mock_process.call_count, 2)
    
    def test_scan_directory_nonexistent(self):
        """Test scanning non-existent directory"""
        timestamp = datetime.now().isoformat()
        added, updated, skipped = index_media.scan_directory(
            "/nonexistent", "", "TestVol", [], [], None, ["relpath"], 0, False, False, timestamp, self.conn
        )
        
        self.assertEqual(added, 0)
        self.assertEqual(updated, 0)
        self.assertEqual(skipped, 0)


class TestIndexMediaCommandLine(unittest.TestCase):
    """Test command-line argument parsing"""

    def test_argparse_required_arguments(self):
        with self.assertRaises(SystemExit):
            with patch('sys.argv', ['index_media.py']):
                index_media.main()

    @patch('index_media.scan_directory')
    @patch('index_media.get_volume')
    @patch('index_media.create_database_schema')
    def test_argparse_minimal_arguments(self, mock_schema, mock_get_volume, mock_scan):
        mock_scan.return_value = (0, 0, 0)
        test_dir = tempfile.mkdtemp()
        mock_get_volume.return_value = {
            'name': 'test',
            'src_root': '/volume1/test',
            'mount_path': test_dir,
            'updated_at': '2026-01-01',
        }
        try:
            with patch('sys.argv', ['index_media.py', '--volume', 'Test', '--db-path', os.path.join(test_dir, 'db.sqlite')]):
                index_media.main()
        finally:
            shutil.rmtree(test_dir)

    @patch('index_media.scan_directory')
    @patch('index_media.get_volume')
    @patch('index_media.create_database_schema')
    def test_argparse_all_arguments(self, mock_schema, mock_get_volume, mock_scan):
        mock_scan.return_value = (1, 2, 3)
        test_dir = tempfile.mkdtemp()
        db_path = os.path.join(test_dir, "test.db")
        mock_get_volume.return_value = {
            'name': 'test',
            'src_root': '/volume1/test',
            'mount_path': test_dir,
            'updated_at': '2026-01-01',
        }

        try:
            with patch('sys.argv', [
                'index_media.py',
                '--volume', 'Test',
                '--db-path', db_path,
                '--include-pattern', '.jpg',
                '--include-pattern', '.png',
                '--skip-pattern', 'thumb',
                '--literal-patterns',
                '--max-depth', '2',
                '--check-existing', 'relpath',
                '--check-existing', 'hash',
                '--verbose', '2',
                '--dry-run',
                '--limit', '10'
            ]):
                index_media.main()
        finally:
            shutil.rmtree(test_dir)


if __name__ == '__main__':
    unittest.main(verbosity=2)
