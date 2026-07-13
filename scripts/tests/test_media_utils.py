#!/usr/bin/env python3
"""
Unit tests for media_utils.py

Tests the shared utility functions including:
- Database schema creation
- File hash calculation
- MIME type detection
- Image file detection
- Video file detection
"""

import unittest
import tempfile
import os
import sys
import sqlite3
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_utils import (
    create_database_schema,
    calculate_file_hash,
    get_mime_type,
    get_indexable_file_type,
    insert_thumbnail,
    is_image_file,
    is_video_file,
    is_audio_file,
    is_document_file,
    is_email_file,
    classify_file_type,
    catalog_mime_type,
    UNKNOWN_MIME_TYPE,
    normalize_date_filter,
    normalize_volume_name,
    set_volume,
    to_storage_relpath,
    clean_mount_path,
    normalize_path,
)


class TestMediaUtils(unittest.TestCase):
    """Test suite for media_utils.py"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create temporary directory
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, 'test.db')
        
        # Create test files
        self.test_file = os.path.join(self.test_dir, 'test.txt')
        with open(self.test_file, 'wb') as f:
            f.write(b'Test content for hashing')
    
    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.test_dir)
    
    def test_create_database_schema(self):
        """Test database schema creation"""
        conn = sqlite3.connect(self.db_path)
        create_database_schema(conn)
        
        cursor = conn.cursor()
        
        # Check that tables were created
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' 
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = [
            'volumes',
            'files',
            'image_metadata',
            'video_metadata',
            'audio_metadata',
            'document_metadata',
            'email_metadata',
            'thumbnails',
            'skipped_files',
        ]
        
        for table in expected_tables:
            self.assertIn(table, tables)
        
        conn.close()
    
    def test_database_schema_indexes(self):
        """Test that database indexes are created"""
        conn = sqlite3.connect(self.db_path)
        create_database_schema(conn)
        
        cursor = conn.cursor()
        
        # Check that indexes were created
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' 
            ORDER BY name
        """)
        indexes = [row[0] for row in cursor.fetchall()]
        
        # Should have indexes on volume, extension, hash, etc.
        self.assertGreater(len(indexes), 0)
        
        conn.close()

    def test_clean_mount_path_strips_shell_quotes(self):
        self.assertEqual(clean_mount_path('d:\\"'), 'd:\\')
        self.assertEqual(clean_mount_path('"d:\\"'), 'd:\\')
        self.assertEqual(clean_mount_path('d:'), f'd:{os.sep}')

    def test_thumbnails_created_at_column(self):
        """New and migrated databases include thumbnails.created_at."""
        conn = sqlite3.connect(self.db_path)
        create_database_schema(conn)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(thumbnails)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        self.assertIn('created_at', columns)
        conn.close()

    def test_insert_thumbnail_sets_created_at(self):
        """insert_thumbnail stores created_at as ISO timestamp."""
        conn = sqlite3.connect(self.db_path)
        try:
            create_database_schema(conn)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO files (volume, relpath, name, modified_date, size, indexed_date)
                VALUES ('photo', 'test.jpg', 'test.jpg', '2024-01-01', 100, '2024-01-01')
            """)
            file_id = cursor.lastrowid
            created_at = '2026-07-03T12:00:00'
            insert_thumbnail(conn, file_id, b'jpeg-bytes', 200, 150, created_at=created_at)
            conn.commit()
            cursor.execute(
                "SELECT created_at FROM thumbnails WHERE file_id = ?",
                (file_id,),
            )
            self.assertEqual(cursor.fetchone()[0], created_at)
        finally:
            conn.close()
    
    def test_calculate_file_hash(self):
        """Test file hash calculation"""
        file_hash = calculate_file_hash(self.test_file)
        
        self.assertIsNotNone(file_hash)
        self.assertEqual(len(file_hash), 64)  # SHA256 is 64 hex chars
        self.assertTrue(all(c in '0123456789abcdef' for c in file_hash))
    
    def test_calculate_file_hash_consistency(self):
        """Test that hash calculation is consistent"""
        hash1 = calculate_file_hash(self.test_file)
        hash2 = calculate_file_hash(self.test_file)
        
        self.assertEqual(hash1, hash2)
    
    def test_calculate_file_hash_different_files(self):
        """Test that different files produce different hashes"""
        test_file2 = os.path.join(self.test_dir, 'test2.txt')
        with open(test_file2, 'wb') as f:
            f.write(b'Different content')
        
        hash1 = calculate_file_hash(self.test_file)
        hash2 = calculate_file_hash(test_file2)
        
        self.assertNotEqual(hash1, hash2)
    
    def test_calculate_file_hash_nonexistent(self):
        """Test hash calculation for non-existent file"""
        nonexistent = os.path.join(self.test_dir, 'nonexistent.txt')
        
        file_hash = calculate_file_hash(nonexistent)
        
        # Should return None or handle gracefully
        self.assertIsNone(file_hash)
    
    def test_calculate_file_hash_empty_file(self):
        """Test hash calculation for empty file"""
        empty_file = os.path.join(self.test_dir, 'empty.txt')
        with open(empty_file, 'wb') as f:
            pass  # Create empty file
        
        file_hash = calculate_file_hash(empty_file)
        
        self.assertIsNotNone(file_hash)
        self.assertEqual(len(file_hash), 64)
    
    def test_calculate_file_hash_large_file(self):
        """Test hash calculation for large file"""
        large_file = os.path.join(self.test_dir, 'large.bin')
        
        # Create a 1MB file
        with open(large_file, 'wb') as f:
            f.write(b'X' * (1024 * 1024))
        
        file_hash = calculate_file_hash(large_file)
        
        self.assertIsNotNone(file_hash)
        self.assertEqual(len(file_hash), 64)
    
    def test_get_mime_type_jpg(self):
        """Test MIME type detection for JPEG"""
        mime_type = get_mime_type('test.jpg')
        self.assertEqual(mime_type, 'image/jpeg')
    
    def test_get_mime_type_png(self):
        """Test MIME type detection for PNG"""
        mime_type = get_mime_type('test.png')
        self.assertEqual(mime_type, 'image/png')
    
    def test_get_mime_type_mp4(self):
        """Test MIME type detection for MP4"""
        mime_type = get_mime_type('test.mp4')
        self.assertIn('video', mime_type.lower())
    
    def test_get_mime_type_unknown(self):
        """Test MIME type detection for unknown extension"""
        mime_type = get_mime_type('test.xyz')
        self.assertIsNotNone(mime_type)
    
    def test_is_image_file_jpeg(self):
        """Test image detection for JPEG"""
        self.assertTrue(is_image_file('image/jpeg', '.jpg'))
    
    def test_is_image_file_png(self):
        """Test image detection for PNG"""
        self.assertTrue(is_image_file('image/png', '.png'))
    
    def test_is_image_file_raw_cr2(self):
        """Test image detection for CR2 (Canon RAW)"""
        self.assertTrue(is_image_file('application/octet-stream', '.cr2'))
    
    def test_is_image_file_raw_nef(self):
        """Test image detection for NEF (Nikon RAW)"""
        self.assertTrue(is_image_file('application/octet-stream', '.nef'))
    
    def test_is_image_file_raw_arw(self):
        """Test image detection for ARW (Sony RAW)"""
        self.assertTrue(is_image_file('application/octet-stream', '.arw'))
    
    def test_is_image_file_not_image(self):
        """Test image detection for non-image file"""
        self.assertFalse(is_image_file('text/plain', '.txt'))
    
    def test_is_image_file_video(self):
        """Test image detection for video file"""
        self.assertFalse(is_image_file('video/mp4', '.mp4'))
    
    def test_is_video_file_mp4(self):
        """Test video detection for MP4"""
        self.assertTrue(is_video_file('video/mp4'))
    
    def test_is_video_file_mov(self):
        """Test video detection for MOV"""
        self.assertTrue(is_video_file('video/quicktime'))
    
    def test_is_video_file_avi(self):
        """Test video detection for AVI"""
        self.assertTrue(is_video_file('video/x-msvideo'))
    
    def test_is_video_file_not_video(self):
        """Test video detection for non-video file"""
        self.assertFalse(is_video_file('image/jpeg'))
    
    def test_is_video_file_text(self):
        """Test video detection for text file"""
        self.assertFalse(is_video_file('text/plain'))
    
    def test_database_schema_idempotent(self):
        """Test that schema creation is idempotent"""
        conn = sqlite3.connect(self.db_path)
        
        # Create schema twice
        create_database_schema(conn)
        create_database_schema(conn)
        
        # Should not raise an error
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        self.assertGreater(len(tables), 0)
        
        conn.close()
    
    def test_raw_format_detection(self):
        """Test detection of various RAW formats"""
        raw_formats = [
            '.cr2', '.cr3', '.nef', '.arw', '.dng', '.orf', '.rw2',
            '.pef', '.srw', '.raf', '.raw', '.rwl', '.mrw', '.erf',
            '.3fr', '.dcr', '.kdc', '.mef', '.mos', '.nrw', '.ptx',
            '.r3d', '.x3f', '.iiq'
        ]
        
        for ext in raw_formats:
            with self.subTest(ext=ext):
                self.assertTrue(
                    is_image_file('application/octet-stream', ext),
                    f"Failed to detect {ext} as image"
                )


class TestVolumeHelpers(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, 'test.db')
        self.conn = sqlite3.connect(self.db_path)
        create_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.test_dir)

    def test_normalize_volume_name(self):
        self.assertEqual(normalize_volume_name('Photo'), 'photo')
        self.assertEqual(normalize_volume_name(' PHOTO '), 'photo')

    def test_set_and_get_volume(self):
        from media_utils import get_volume
        set_volume(self.conn, 'Photo', '/volume1/photo', '/mnt/photo')
        vol = get_volume(self.conn, 'PHOTO')
        self.assertIsNotNone(vol)
        self.assertEqual(vol['name'], 'photo')
        self.assertEqual(vol['src_root'], '/volume1/photo')

    def test_to_storage_relpath(self):
        root = os.path.join(self.test_dir, 'mount')
        os.makedirs(root, exist_ok=True)
        filepath = os.path.join(root, '2024', 'a.jpg')
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        open(filepath, 'wb').close()
        self.assertEqual(to_storage_relpath(filepath, root), '2024/a.jpg')


class TestFileTypeDetection(unittest.TestCase):
    def test_indexable_types(self):
        self.assertEqual(get_indexable_file_type('image/jpeg', '.jpg'), 'image')
        self.assertEqual(get_indexable_file_type('video/mp4', '.mp4'), 'video')
        self.assertEqual(get_indexable_file_type('audio/mpeg', '.mp3'), 'audio')
        self.assertEqual(get_indexable_file_type('application/pdf', '.pdf'), 'document')
        self.assertEqual(get_indexable_file_type('message/rfc822', '.eml'), 'email')
        self.assertIsNone(get_indexable_file_type('application/zip', '.zip'))

    def test_classify_and_catalog_unknown_types(self):
        self.assertEqual(classify_file_type('application/zip', '.zip'), 'unknown')
        self.assertIn('zip', catalog_mime_type('application/zip', '.zip'))
        self.assertEqual(catalog_mime_type('application/octet-stream', '.xyz'), UNKNOWN_MIME_TYPE)
        self.assertEqual(catalog_mime_type('image/jpeg', '.jpg'), 'image/jpeg')
        self.assertEqual(classify_file_type('image/jpeg', '.jpg'), 'image')

    def test_audio_document_email_helpers(self):
        self.assertTrue(is_audio_file('audio/mpeg', '.mp3'))
        self.assertTrue(is_document_file('application/pdf', '.pdf'))
        self.assertTrue(is_email_file('message/rfc822', '.eml'))
    
    def test_mime_type_case_insensitive(self):
        """Test that MIME type detection is case insensitive"""
        mime1 = get_mime_type('TEST.JPG')
        mime2 = get_mime_type('test.jpg')
        
        self.assertEqual(mime1, mime2)

    def test_normalize_date_filter_formats(self):
        cases = [
            ('20260101', '20260101'),
            ('2026-01-30', '20260130'),
            ('2026/01/09', '20260109'),
            ('2024-06-02T10:00:00', '20240602'),
            ('2026:01:09 14:30:00', '20260109'),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_date_filter(raw), expected)

    def test_normalize_date_filter_invalid(self):
        with self.assertRaises(ValueError):
            normalize_date_filter('2026')


if __name__ == '__main__':
    unittest.main()
