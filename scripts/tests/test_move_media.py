#!/usr/bin/env python3
"""
Integration tests for move_media.py

Tests the file moving functionality including:
- Moving files to destination
- Database updates
- Hash calculation and verification
- Duplicate detection
- Dry-run mode
- Error handling
- Audit logging
"""

import unittest
import tempfile
import os
import sys
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from move_media import (
    move_files,
    check_duplicate_in_db,
    check_file_exists_at_destination
)
from media_utils import create_database_schema, calculate_file_hash


class TestMoveMedia(unittest.TestCase):
    """Test suite for move_media.py"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create temporary directories
        self.test_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.test_dir, 'source')
        self.dest_dir = os.path.join(self.test_dir, 'destination')
        self.db_path = os.path.join(self.test_dir, 'test.db')
        self.audit_log = os.path.join(self.test_dir, 'audit.log')
        
        os.makedirs(self.source_dir)
        os.makedirs(self.dest_dir)
        
        # Create test database
        self.conn = sqlite3.connect(self.db_path)
        create_database_schema(self.conn)
        
        # Create test files
        self.test_file1 = os.path.join(self.source_dir, 'test1.jpg')
        self.test_file2 = os.path.join(self.source_dir, 'test2.jpg')
        
        with open(self.test_file1, 'wb') as f:
            f.write(b'Test image 1 content')
        
        with open(self.test_file2, 'wb') as f:
            f.write(b'Test image 2 content')
    
    def tearDown(self):
        """Clean up test fixtures"""
        self.conn.close()
        shutil.rmtree(self.test_dir)
    
    def test_move_single_file(self):
        """Test moving a single file"""
        result = move_files(
            files=[self.test_file1],
            destination=self.dest_dir,
            volume='TestVolume',
            db_path=self.db_path,
            dry_run=False,
            verbose=0,
            audit_log=self.audit_log
        )
        
        self.assertEqual(result['moved'], 1)
        self.assertEqual(result['skipped'], 0)
        self.assertEqual(result['errors'], 0)
        
        # Verify file was moved
        dest_file = os.path.join(self.dest_dir, 'test1.jpg')
        self.assertTrue(os.path.exists(dest_file))
        self.assertFalse(os.path.exists(self.test_file1))
        
        # Verify database entry
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM files WHERE name = 'test1.jpg'")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], 'TestVolume')  # volume
    
    def test_move_multiple_files(self):
        """Test moving multiple files"""
        result = move_files(
            files=[self.test_file1, self.test_file2],
            destination=self.dest_dir,
            volume='TestVolume',
            db_path=self.db_path,
            dry_run=False,
            verbose=0,
            audit_log=self.audit_log
        )
        
        self.assertEqual(result['moved'], 2)
        self.assertEqual(result['skipped'], 0)
        self.assertEqual(result['errors'], 0)
        
        # Verify both files were moved
        self.assertTrue(os.path.exists(os.path.join(self.dest_dir, 'test1.jpg')))
        self.assertTrue(os.path.exists(os.path.join(self.dest_dir, 'test2.jpg')))
    
    def test_dry_run_mode(self):
        """Test dry-run mode doesn't actually move files"""
        result = move_files(
            files=[self.test_file1],
            destination=self.dest_dir,
            volume='TestVolume',
            db_path=self.db_path,
            dry_run=True,
            verbose=0,
            audit_log=self.audit_log
        )
        
        # File should still exist at source
        self.assertTrue(os.path.exists(self.test_file1))
        
        # File should not exist at destination
        dest_file = os.path.join(self.dest_dir, 'test1.jpg')
        self.assertFalse(os.path.exists(dest_file))
        
        # Database should not be updated
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM files")
        count = cursor.fetchone()[0]
        self.assertEqual(count, 0)
    
    def test_duplicate_detection_same_hash(self):
        """Test duplicate detection when file with same hash exists"""
        # First, move the file
        move_files(
            files=[self.test_file1],
            destination=self.dest_dir,
            volume='TestVolume',
            db_path=self.db_path,
            dry_run=False,
            verbose=0,
            audit_log=self.audit_log
        )
        
        # Create another file with same content
        test_file_dup = os.path.join(self.source_dir, 'test1_dup.jpg')
        with open(test_file_dup, 'wb') as f:
            f.write(b'Test image 1 content')
        
        # Try to move duplicate
        result = move_files(
            files=[test_file_dup],
            destination=self.dest_dir,
            volume='TestVolume',
            db_path=self.db_path,
            dry_run=False,
            verbose=0,
            audit_log=self.audit_log
        )
        
        # Should be skipped as duplicate
        self.assertEqual(result['skipped'], 1)
    
    def test_file_already_at_destination(self):
        """Test handling when file already exists at destination"""
        # Manually copy file to destination
        dest_file = os.path.join(self.dest_dir, 'test1.jpg')
        shutil.copy2(self.test_file1, dest_file)
        
        # Try to move the file
        result = move_files(
            files=[self.test_file1],
            destination=self.dest_dir,
            volume='TestVolume',
            db_path=self.db_path,
            dry_run=False,
            verbose=0,
            audit_log=self.audit_log
        )
        
        # Should handle gracefully
        self.assertGreaterEqual(result['skipped'] + result['moved'], 1)
    
    def test_hash_calculation(self):
        """Test file hash calculation"""
        file_hash = calculate_file_hash(self.test_file1)
        self.assertIsNotNone(file_hash)
        self.assertEqual(len(file_hash), 64)  # SHA256 is 64 hex chars
        
        # Same file should produce same hash
        file_hash2 = calculate_file_hash(self.test_file1)
        self.assertEqual(file_hash, file_hash2)
    
    def test_check_duplicate_in_db(self):
        """Test duplicate checking in database"""
        # Add a file to database
        cursor = self.conn.cursor()
        test_hash = 'abc123'
        cursor.execute("""
            INSERT INTO files (volume, fullpath, name, modified_date, size, file_hash, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('TestVolume', '/path/to/file.jpg', 'file.jpg', 
              datetime.now().isoformat(), 1000, test_hash, datetime.now().isoformat()))
        self.conn.commit()
        
        # Check for duplicate
        is_dup, existing_path = check_duplicate_in_db(self.conn, test_hash)
        self.assertTrue(is_dup)
        self.assertEqual(existing_path, '/path/to/file.jpg')
        
        # Check for non-existent hash
        is_dup, existing_path = check_duplicate_in_db(self.conn, 'nonexistent')
        self.assertFalse(is_dup)
        self.assertIsNone(existing_path)
    
    def test_check_file_exists_at_destination(self):
        """Test checking if file exists at destination"""
        # Create a file at destination
        dest_file = os.path.join(self.dest_dir, 'existing.jpg')
        with open(dest_file, 'wb') as f:
            f.write(b'Existing file')
        
        dest_hash = calculate_file_hash(dest_file)
        
        # Check for existing file
        exists, matches = check_file_exists_at_destination(
            dest_file, dest_hash
        )
        self.assertTrue(exists)
        self.assertTrue(matches)
        
        # Check for non-existent file
        non_existent = os.path.join(self.dest_dir, 'nonexistent.jpg')
        exists, matches = check_file_exists_at_destination(
            non_existent, 'somehash'
        )
        self.assertFalse(exists)
        self.assertFalse(matches)
    
    def test_limit_parameter(self):
        """Test limiting number of files processed"""
        # Create more test files
        test_file3 = os.path.join(self.source_dir, 'test3.jpg')
        with open(test_file3, 'wb') as f:
            f.write(b'Test image 3')
        
        result = move_files(
            files=[self.test_file1, self.test_file2, test_file3],
            destination=self.dest_dir,
            volume='TestVolume',
            db_path=self.db_path,
            dry_run=False,
            verbose=0,
            limit=2,
            audit_log=self.audit_log
        )
        
        # Should only process 2 files
        self.assertEqual(result['moved'], 2)
    
    def test_nonexistent_source_file(self):
        """Test handling of non-existent source file"""
        nonexistent = os.path.join(self.source_dir, 'nonexistent.jpg')
        
        result = move_files(
            files=[nonexistent],
            destination=self.dest_dir,
            volume='TestVolume',
            db_path=self.db_path,
            dry_run=False,
            verbose=0,
            audit_log=self.audit_log
        )
        
        # Should record as error or skip
        self.assertGreaterEqual(result['errors'] + result['skipped'], 1)
    
    def test_database_update_on_move(self):
        """Test that database is properly updated when file is moved"""
        result = move_files(
            files=[self.test_file1],
            destination=self.dest_dir,
            volume='TestVolume',
            db_path=self.db_path,
            dry_run=False,
            verbose=0,
            audit_log=self.audit_log
        )
        
        # Check database entry
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT volume, fullpath, name, size, file_hash 
            FROM files WHERE name = 'test1.jpg'
        """)
        row = cursor.fetchone()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 'TestVolume')
        self.assertIn('test1.jpg', row[1])
        self.assertEqual(row[2], 'test1.jpg')
        self.assertGreater(row[3], 0)  # size
        self.assertIsNotNone(row[4])  # hash
    
    def test_audit_log_creation(self):
        """Test that audit log is created"""
        result = move_files(
            files=[self.test_file1],
            destination=self.dest_dir,
            volume='TestVolume',
            db_path=self.db_path,
            dry_run=False,
            verbose=0,
            audit_log=self.audit_log
        )
        
        # Check audit log exists and has content
        self.assertTrue(os.path.exists(self.audit_log))
        
        with open(self.audit_log, 'r') as f:
            content = f.read()
            self.assertIn('test1.jpg', content)
    
    def test_verbose_output(self):
        """Test verbose output levels"""
        # Just verify it doesn't crash with different verbosity levels
        for verbose_level in [0, 1, 2, 3]:
            result = move_files(
                files=[self.test_file1],
                destination=self.dest_dir,
                volume='TestVolume',
                db_path=self.db_path,
                dry_run=True,
                verbose=verbose_level,
                audit_log=self.audit_log
            )
            self.assertIsNotNone(result)


if __name__ == '__main__':
    unittest.main()
