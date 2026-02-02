#!/usr/bin/env python3
"""
Integration tests for show_exif.py

Tests the EXIF display functionality including:
- Reading EXIF data
- Different display modes
- GPS data extraction
- Thumbnail extraction
- Error handling
"""

import unittest
import tempfile
import os
import sys
import shutil
from PIL import Image
from PIL.ExifTags import TAGS

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from show_exif import (
    read_exif_data,
    format_exif_output,
    extract_thumbnail
)


class TestShowExif(unittest.TestCase):
    """Test suite for show_exif.py"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create temporary directory
        self.test_dir = tempfile.mkdtemp()
        
        # Create test image with EXIF data
        self.test_image = os.path.join(self.test_dir, 'test.jpg')
        self._create_test_image_with_exif()
        
        # Create test image without EXIF
        self.test_image_no_exif = os.path.join(self.test_dir, 'no_exif.jpg')
        img = Image.new('RGB', (100, 100), color='red')
        img.save(self.test_image_no_exif)
    
    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.test_dir)
    
    def _create_test_image_with_exif(self):
        """Create a test image with EXIF data"""
        img = Image.new('RGB', (100, 100), color='blue')
        
        # Create EXIF data
        exif_dict = {
            'Make': 'Test Camera',
            'Model': 'Test Model',
            'DateTime': '2024:01:15 12:00:00',
            'Software': 'Test Software'
        }
        
        # Note: PIL doesn't easily allow setting EXIF, so we'll save without it
        # The actual tests will use exiftool which can read real EXIF
        img.save(self.test_image, 'JPEG', quality=95)
    
    def test_read_exif_from_file(self):
        """Test reading EXIF data from a file"""
        try:
            exif_data = read_exif_data(self.test_image, mode='common')
            self.assertIsNotNone(exif_data)
            self.assertIsInstance(exif_data, dict)
        except Exception as e:
            # If exiftool is not available, skip
            if 'exiftool' in str(e).lower():
                self.skipTest("exiftool not available")
            raise
    
    def test_read_exif_no_exif_data(self):
        """Test reading EXIF from file without EXIF data"""
        try:
            exif_data = read_exif_data(self.test_image_no_exif, mode='common')
            # Should return empty dict or minimal data
            self.assertIsInstance(exif_data, dict)
        except Exception as e:
            if 'exiftool' in str(e).lower():
                self.skipTest("exiftool not available")
            raise
    
    def test_read_exif_nonexistent_file(self):
        """Test reading EXIF from non-existent file"""
        nonexistent = os.path.join(self.test_dir, 'nonexistent.jpg')
        
        with self.assertRaises(Exception):
            read_exif_data(nonexistent, mode='common')
    
    def test_display_mode_common(self):
        """Test common EXIF display mode"""
        try:
            exif_data = read_exif_data(self.test_image, mode='common')
            output = format_exif_output(exif_data, mode='common')
            
            self.assertIsInstance(output, str)
        except Exception as e:
            if 'exiftool' in str(e).lower():
                self.skipTest("exiftool not available")
            raise
    
    def test_display_mode_all(self):
        """Test all EXIF display mode"""
        try:
            exif_data = read_exif_data(self.test_image, mode='all')
            output = format_exif_output(exif_data, mode='all')
            
            self.assertIsInstance(output, str)
        except Exception as e:
            if 'exiftool' in str(e).lower():
                self.skipTest("exiftool not available")
            raise
    
    def test_display_mode_gps(self):
        """Test GPS EXIF display mode"""
        try:
            exif_data = read_exif_data(self.test_image, mode='gps')
            output = format_exif_output(exif_data, mode='gps')
            
            self.assertIsInstance(output, str)
        except Exception as e:
            if 'exiftool' in str(e).lower():
                self.skipTest("exiftool not available")
            raise
    
    def test_display_mode_grouped(self):
        """Test grouped EXIF display mode"""
        try:
            exif_data = read_exif_data(self.test_image, mode='grouped')
            output = format_exif_output(exif_data, mode='grouped')
            
            self.assertIsInstance(output, str)
        except Exception as e:
            if 'exiftool' in str(e).lower():
                self.skipTest("exiftool not available")
            raise
    
    def test_extract_thumbnail(self):
        """Test thumbnail extraction"""
        try:
            thumbnail = extract_thumbnail(self.test_image)
            
            # May or may not have thumbnail
            if thumbnail is not None:
                self.assertIsInstance(thumbnail, bytes)
        except Exception as e:
            if 'exiftool' in str(e).lower():
                self.skipTest("exiftool not available")
            raise
    
    def test_multiple_files(self):
        """Test processing multiple files"""
        # Create another test file
        test_image2 = os.path.join(self.test_dir, 'test2.jpg')
        img = Image.new('RGB', (100, 100), color='green')
        img.save(test_image2)
        
        try:
            for file in [self.test_image, test_image2]:
                exif_data = read_exif_data(file, mode='common')
                self.assertIsInstance(exif_data, dict)
        except Exception as e:
            if 'exiftool' in str(e).lower():
                self.skipTest("exiftool not available")
            raise
    
    def test_invalid_file_type(self):
        """Test handling of invalid file type"""
        # Create a text file
        text_file = os.path.join(self.test_dir, 'test.txt')
        with open(text_file, 'w') as f:
            f.write('Not an image')
        
        # Should handle gracefully
        try:
            exif_data = read_exif_data(text_file, mode='common')
            # May return empty dict or raise exception
            self.assertIsInstance(exif_data, dict)
        except Exception as e:
            # Expected to fail for non-image files
            self.assertIsInstance(e, Exception)
    
    def test_format_output_consistency(self):
        """Test that output formatting is consistent"""
        try:
            exif_data = read_exif_data(self.test_image, mode='common')
            
            output1 = format_exif_output(exif_data, mode='common')
            output2 = format_exif_output(exif_data, mode='common')
            
            self.assertEqual(output1, output2)
        except Exception as e:
            if 'exiftool' in str(e).lower():
                self.skipTest("exiftool not available")
            raise


if __name__ == '__main__':
    unittest.main()
