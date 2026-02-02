#!/usr/bin/env python3
"""
Integration tests for locate_in_db.py

Tests the file location functionality including:
- Finding files by hash
- Grouping duplicates
- Metadata display
- JSON output
- Error handling
"""

import unittest
import tempfile
import os
import sys
import sqlite3
import shutil
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from locate_in_db import (
    locate_files,
    format_output,
    format_json_output
)
from media_utils import create_database_schema, calculate_file_hash


class TestLocateInDb(unittest.TestCase):
    """Test suite for locate_in_db.py"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create temporary directories
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, 'test.db')
        
        # Create test database
        self.conn = sqlite3.connect(self.db_path)
        create_database_schema(self.conn)
        
        # Create test files
        self.test_file1 = os.path.join(self.test_dir, 'test1.jpg')
        self.test_file2 = os.path.join(self.test_dir, 'test2.jpg')
        self.test_file3 = os.path.join(self.test_dir, 'test3.jpg')
        
        with open(self.test_file1, 'wb') as f:
            f.write(b'Test image 1 content')
        
        with open(self.test_file2, 'wb') as f:
            f.write(b'Test image 1 content')  # Same content as file1
        
        with open(self.test_file3, 'wb') as f:
            f.write(b'Test image 3 unique content')
        
        # Calculate hashes
        self.hash1 = calculate_file_hash(self.test_file1)
        self.hash2 = calculate_file_hash(self.test_file2)
        self.hash3 = calculate_file_hash(self.test_file3)
        
        # Add files to database
        cursor = self.conn.cursor()
        
        # File 1 and 2 have same hash (duplicates)
        cursor.execute("""
            INSERT INTO files (volume, fullpath, name, modified_date, size, file_hash, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('Volume1', '/path/to/test1.jpg', 'test1.jpg', 
              datetime.now().isoformat(), 20, self.hash1, datetime.now().isoformat()))
        
        cursor.execute("""
            INSERT INTO files (volume, fullpath, name, modified_date, size, file_hash, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('Volume2', '/path/to/test2.jpg', 'test2.jpg', 
              datetime.now().isoformat(), 20, self.hash2, datetime.now().isoformat()))
        
        # File 3 is unique
        cursor.execute("""
            INSERT INTO files (volume, fullpath, name, modified_date, size, file_hash, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('Volume1', '/path/to/test3.jpg', 'test3.jpg', 
              datetime.now().isoformat(), 28, self.hash3, datetime.now().isoformat()))
        
        self.conn.commit()
    
    def tearDown(self):
        """Clean up test fixtures"""
        self.conn.close()
        shutil.rmtree(self.test_dir)
    
    def test_locate_single_file_found(self):
        """Test locating a single file that exists in database"""
        results = locate_files(
            files=[self.test_file1],
            db_path=self.db_path,
            metadata=False
        )
        
        self.assertEqual(len(results), 1)
        self.assertIn(self.test_file1, results)
        
        file_info = results[self.test_file1]
        self.assertEqual(file_info['status'], 'found')
        self.assertGreater(len(file_info['locations']), 0)
    
    def test_locate_file_not_found(self):
        """Test locating a file that doesn't exist in database"""
        nonexistent = os.path.join(self.test_dir, 'nonexistent.jpg')
        with open(nonexistent, 'wb') as f:
            f.write(b'Nonexistent file content')
        
        results = locate_files(
            files=[nonexistent],
            db_path=self.db_path,
            metadata=False
        )
        
        self.assertEqual(len(results), 1)
        self.assertIn(nonexistent, results)
        
        file_info = results[nonexistent]
        self.assertEqual(file_info['status'], 'not_found')
        self.assertEqual(len(file_info['locations']), 0)
    
    def test_locate_duplicate_files(self):
        """Test locating files that have duplicates"""
        results = locate_files(
            files=[self.test_file1],
            db_path=self.db_path,
            metadata=False
        )
        
        file_info = results[self.test_file1]
        
        # Should find 2 locations (test1.jpg and test2.jpg have same hash)
        self.assertEqual(len(file_info['locations']), 2)
        self.assertTrue(file_info['is_duplicate'])
    
    def test_locate_unique_file(self):
        """Test locating a file with no duplicates"""
        results = locate_files(
            files=[self.test_file3],
            db_path=self.db_path,
            metadata=False
        )
        
        file_info = results[self.test_file3]
        
        # Should find 1 location
        self.assertEqual(len(file_info['locations']), 1)
        self.assertFalse(file_info['is_duplicate'])
    
    def test_locate_multiple_files(self):
        """Test locating multiple files at once"""
        results = locate_files(
            files=[self.test_file1, self.test_file3],
            db_path=self.db_path,
            metadata=False
        )
        
        self.assertEqual(len(results), 2)
        self.assertIn(self.test_file1, results)
        self.assertIn(self.test_file3, results)
    
    def test_metadata_option(self):
        """Test metadata display option"""
        results = locate_files(
            files=[self.test_file1],
            db_path=self.db_path,
            metadata=True
        )
        
        file_info = results[self.test_file1]
        
        # With metadata, locations should include detailed info
        self.assertGreater(len(file_info['locations']), 0)
        
        location = file_info['locations'][0]
        self.assertIn('volume', location)
        self.assertIn('size', location)
        self.assertIn('path', location)
    
    def test_format_output_text(self):
        """Test text output formatting"""
        results = locate_files(
            files=[self.test_file1, self.test_file3],
            db_path=self.db_path,
            metadata=False
        )
        
        output = format_output(results, metadata=False)
        
        self.assertIsInstance(output, str)
        self.assertIn('test1.jpg', output)
        self.assertIn('test3.jpg', output)
    
    def test_format_output_json(self):
        """Test JSON output formatting"""
        results = locate_files(
            files=[self.test_file1],
            db_path=self.db_path,
            metadata=False
        )
        
        json_output = format_json_output(results)
        
        # Verify it's valid JSON
        parsed = json.loads(json_output)
        self.assertIsInstance(parsed, dict)
        self.assertIn('results', parsed)
    
    def test_hash_calculation_consistency(self):
        """Test that hash calculation is consistent"""
        hash1 = calculate_file_hash(self.test_file1)
        hash2 = calculate_file_hash(self.test_file1)
        
        self.assertEqual(hash1, hash2)
    
    def test_nonexistent_database(self):
        """Test handling of non-existent database"""
        nonexistent_db = os.path.join(self.test_dir, 'nonexistent.db')
        
        # Should handle gracefully
        try:
            results = locate_files(
                files=[self.test_file1],
                db_path=nonexistent_db,
                metadata=False
            )
            # If it doesn't raise an exception, check results
            self.assertIsNotNone(results)
        except Exception as e:
            # If it raises an exception, it should be a reasonable one
            self.assertIn('database', str(e).lower())
    
    def test_empty_file_list(self):
        """Test handling of empty file list"""
        results = locate_files(
            files=[],
            db_path=self.db_path,
            metadata=False
        )
        
        self.assertEqual(len(results), 0)
    
    def test_file_grouping(self):
        """Test that files are properly grouped by status"""
        # Create a file not in database
        nonexistent = os.path.join(self.test_dir, 'new.jpg')
        with open(nonexistent, 'wb') as f:
            f.write(b'New content')
        
        results = locate_files(
            files=[self.test_file1, self.test_file3, nonexistent],
            db_path=self.db_path,
            metadata=False
        )
        
        # Count by status
        found_count = sum(1 for r in results.values() if r['status'] == 'found')
        not_found_count = sum(1 for r in results.values() if r['status'] == 'not_found')
        
        self.assertEqual(found_count, 2)  # test1 and test3
        self.assertEqual(not_found_count, 1)  # nonexistent


if __name__ == '__main__':
    unittest.main()
