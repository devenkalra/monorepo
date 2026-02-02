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
    is_image_file,
    is_video_file
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
            'files',
            'image_metadata',
            'video_metadata',
            'thumbnails',
            'skipped_files'
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
    
    def test_mime_type_case_insensitive(self):
        """Test that MIME type detection is case insensitive"""
        mime1 = get_mime_type('TEST.JPG')
        mime2 = get_mime_type('test.jpg')
        
        self.assertEqual(mime1, mime2)


if __name__ == '__main__':
    unittest.main()
