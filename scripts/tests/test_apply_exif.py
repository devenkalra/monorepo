# tests/test_apply_exif.py

import unittest
from unittest.mock import patch, MagicMock, call
import tempfile
import os
import subprocess
import json

# Import functions to test
from apply_exif import (
    create_exif_metadata, 
    _normalize_keywords, 
    build_exiftool_cmd,
    get_existing_keywords,
    run_exiftool
)


def mock_location_factory(address, namedetails=None, extratags=None, latitude=0.0, longitude=0.0):
    """Create a mock location object mimicking geopy's Nominatim response."""
    mock_loc = MagicMock()
    mock_loc.latitude = latitude
    mock_loc.longitude = longitude
    raw = {
        "address": address,
    }
    if namedetails:
        raw["nameddetails"] = namedetails
    if extratags:
        raw["extratags"] = extratags
    mock_loc.raw = raw
    return mock_loc


class TestCreateExifMetadata(unittest.TestCase):
    @patch("apply_exif.Nominatim")
    def test_new_delhi(self, mock_nominatim):
        address = {
            "city": "New Delhi",
            "state": "Delhi",
            "country": "India",
            "country_code": "in",
        }
        mock_nominatim.return_value.geocode.return_value = mock_location_factory(address, latitude=28.6139, longitude=77.2090)
        tags = create_exif_metadata("New Delhi, India", "2026:01:01 12:00:00", "+05:30")
        self.assertEqual(tags["XMP-photoshop:City"], "New Delhi")
        self.assertEqual(tags["XMP-photoshop:State"], "Delhi")
        self.assertEqual(tags["XMP-photoshop:Country"], "India")
        self.assertEqual(tags["XMP-iptcExt:LocationShownCountryCode"], "IN")

    @patch("apply_exif.Nominatim")
    def test_fort_worth(self, mock_nominatim):
        address = {
            "city": "Fort Worth",
            "state": "Texas",
            "country": "United States",
            "country_code": "us",
        }
        mock_nominatim.return_value.geocode.return_value = mock_location_factory(address, latitude=32.7555, longitude=-97.3308)
        tags = create_exif_metadata("Fort Worth, Texas, USA", "2026:01:01 12:00:00", "-06:00")
        self.assertEqual(tags["XMP-photoshop:City"], "Fort Worth")
        self.assertEqual(tags["XMP-photoshop:State"], "Texas")
        self.assertEqual(tags["XMP-photoshop:Country"], "United States")
        self.assertEqual(tags["XMP-iptcExt:LocationShownCountryCode"], "US")

    @patch("apply_exif.Nominatim")
    def test_queenstown(self, mock_nominatim):
        address = {
            "city": "Queenstown",
            "state": "Otago",
            "country": "New Zealand",
            "country_code": "nz",
        }
        mock_nominatim.return_value.geocode.return_value = mock_location_factory(address, latitude=-45.0312, longitude=168.6626)
        tags = create_exif_metadata("Queenstown, New Zealand", "2026:01:01 12:00:00", "+12:00")
        self.assertEqual(tags["XMP-photoshop:City"], "Queenstown")
        self.assertEqual(tags["XMP-photoshop:State"], "Otago")
        self.assertEqual(tags["XMP-photoshop:Country"], "New Zealand")
        self.assertEqual(tags["XMP-iptcExt:LocationShownCountryCode"], "NZ")

    @patch("apply_exif.Nominatim")
    def test_kathmandu(self, mock_nominatim):
        address = {
            "city": "Kathmandu",
            "state": "Bagmati",
            "country": "Nepal",
            "country_code": "np",
        }
        mock_nominatim.return_value.geocode.return_value = mock_location_factory(address, latitude=27.7172, longitude=85.3240)
        tags = create_exif_metadata("Kathmandu, Nepal", "2026:01:01 12:00:00", "+05:45")
        self.assertEqual(tags["XMP-photoshop:City"], "Kathmandu")
        self.assertEqual(tags["XMP-photoshop:State"], "Bagmati")
        self.assertEqual(tags["XMP-photoshop:Country"], "Nepal")
        self.assertEqual(tags["XMP-iptcExt:LocationShownCountryCode"], "NP")


class TestNormalizeKeywords(unittest.TestCase):
    """Test the _normalize_keywords function."""
    
    def test_normalize_string_single(self):
        """Test normalizing a single keyword as string."""
        result = _normalize_keywords("vacation")
        self.assertEqual(result, ["vacation"])
    
    def test_normalize_string_comma_separated(self):
        """Test normalizing comma-separated keywords."""
        result = _normalize_keywords("vacation, beach, sunset")
        self.assertEqual(result, ["beach", "sunset", "vacation"])
    
    def test_normalize_string_with_whitespace(self):
        """Test normalizing keywords with extra whitespace."""
        result = _normalize_keywords("  vacation ,  beach  , sunset  ")
        self.assertEqual(result, ["beach", "sunset", "vacation"])
    
    def test_normalize_string_with_duplicates(self):
        """Test that duplicates are removed."""
        result = _normalize_keywords("vacation, beach, vacation, sunset, beach")
        self.assertEqual(result, ["beach", "sunset", "vacation"])
    
    def test_normalize_list(self):
        """Test normalizing a list of keywords."""
        result = _normalize_keywords(["vacation", "beach", "sunset"])
        self.assertEqual(result, ["beach", "sunset", "vacation"])
    
    def test_normalize_list_with_duplicates(self):
        """Test that duplicates are removed from lists."""
        result = _normalize_keywords(["vacation", "beach", "vacation", "sunset"])
        self.assertEqual(result, ["beach", "sunset", "vacation"])
    
    def test_normalize_list_with_whitespace(self):
        """Test normalizing list with whitespace."""
        result = _normalize_keywords(["  vacation  ", "beach", "  sunset"])
        self.assertEqual(result, ["beach", "sunset", "vacation"])
    
    def test_normalize_empty_string(self):
        """Test normalizing empty string."""
        result = _normalize_keywords("")
        self.assertEqual(result, [])
    
    def test_normalize_empty_list(self):
        """Test normalizing empty list."""
        result = _normalize_keywords([])
        self.assertEqual(result, [])
    
    def test_normalize_none(self):
        """Test normalizing None."""
        result = _normalize_keywords(None)
        self.assertEqual(result, [])


class TestBuildExiftoolCmd(unittest.TestCase):
    """Test the build_exiftool_cmd function."""
    
    def test_single_regular_tag(self):
        """Test building command with a single regular tag."""
        tags = {"Caption-Abstract": "My caption"}
        cmd = build_exiftool_cmd(["image.jpg"], tags, dry_run=False)
        
        self.assertIn("exiftool", cmd)
        self.assertIn("-Caption-Abstract=My caption", cmd)
        self.assertIn("-overwrite_original", cmd)
        self.assertIn("image.jpg", cmd)
    
    def test_single_keyword(self):
        """Test building command with a single keyword."""
        tags = {"XMP-dc:Subject": ["vacation"]}
        cmd = build_exiftool_cmd(["image.jpg"], tags, dry_run=False)
        
        self.assertIn("exiftool", cmd)
        self.assertIn("-sep", cmd)
        self.assertIn("-XMP-dc:Subject=vacation", cmd)
        self.assertIn("-overwrite_original", cmd)
        self.assertIn("image.jpg", cmd)
    
    def test_multiple_keywords(self):
        """Test building command with multiple keywords."""
        tags = {"XMP-dc:Subject": ["vacation", "beach", "sunset"]}
        cmd = build_exiftool_cmd(["image.jpg"], tags, dry_run=False)
        
        self.assertIn("exiftool", cmd)
        self.assertIn("-sep", cmd)
        # Check that all keywords are in the joined value
        joined_value = None
        for i, arg in enumerate(cmd):
            if arg.startswith("-XMP-dc:Subject="):
                joined_value = arg.split("=", 1)[1]
                break
        
        self.assertIsNotNone(joined_value)
        self.assertIn("vacation", joined_value)
        self.assertIn("beach", joined_value)
        self.assertIn("sunset", joined_value)
    
    def test_empty_keyword_list(self):
        """Test building command with empty keyword list."""
        tags = {"XMP-dc:Subject": []}
        cmd = build_exiftool_cmd(["image.jpg"], tags, dry_run=False)
        
        self.assertIn("exiftool", cmd)
        self.assertIn("-XMP-dc:Subject=", cmd)
        self.assertIn("-overwrite_original", cmd)
    
    def test_mixed_tags(self):
        """Test building command with both list and regular tags."""
        tags = {
            "XMP-dc:Subject": ["vacation", "beach"],
            "Caption-Abstract": "My vacation",
            "IPTC:Keywords": ["vacation", "beach"]
        }
        cmd = build_exiftool_cmd(["image.jpg"], tags, dry_run=False)
        
        self.assertIn("exiftool", cmd)
        self.assertIn("-Caption-Abstract=My vacation", cmd)
        # Should have -sep for list tags
        self.assertIn("-sep", cmd)
        self.assertIn("-overwrite_original", cmd)
    
    def test_dry_run_mode(self):
        """Test that dry run mode doesn't include -overwrite_original."""
        tags = {"Caption-Abstract": "My caption"}
        cmd = build_exiftool_cmd(["image.jpg"], tags, dry_run=True)
        
        self.assertIn("exiftool", cmd)
        self.assertNotIn("-overwrite_original", cmd)
    
    def test_multiple_files(self):
        """Test building command with multiple files."""
        tags = {"Caption-Abstract": "My caption"}
        cmd = build_exiftool_cmd(["image1.jpg", "image2.jpg"], tags, dry_run=False)
        
        self.assertIn("image1.jpg", cmd)
        self.assertIn("image2.jpg", cmd)


class TestKeywordMerging(unittest.TestCase):
    """Test the keyword merging logic (set operations)."""
    
    def test_add_keyword_to_empty(self):
        """Test adding keyword to empty set."""
        existing = set()
        to_add = {"vacation"}
        result = existing.union(to_add)
        self.assertEqual(result, {"vacation"})
    
    def test_add_keyword_to_existing(self):
        """Test adding keyword to existing keywords."""
        existing = {"beach", "sunset"}
        to_add = {"vacation"}
        result = existing.union(to_add)
        self.assertEqual(result, {"beach", "sunset", "vacation"})
    
    def test_add_duplicate_keyword(self):
        """Test that adding duplicate keyword doesn't create duplicate."""
        existing = {"beach", "sunset", "vacation"}
        to_add = {"vacation"}
        result = existing.union(to_add)
        self.assertEqual(result, {"beach", "sunset", "vacation"})
        self.assertEqual(len(result), 3)  # Still only 3 keywords
    
    def test_add_multiple_keywords(self):
        """Test adding multiple keywords at once."""
        existing = {"beach"}
        to_add = {"vacation", "sunset"}
        result = existing.union(to_add)
        self.assertEqual(result, {"beach", "sunset", "vacation"})
    
    def test_add_multiple_with_duplicates(self):
        """Test adding multiple keywords where some already exist."""
        existing = {"beach", "sunset"}
        to_add = {"vacation", "beach", "mountains"}
        result = existing.union(to_add)
        self.assertEqual(result, {"beach", "mountains", "sunset", "vacation"})
        self.assertEqual(len(result), 4)  # No duplicates
    
    def test_remove_keyword(self):
        """Test removing a keyword."""
        existing = {"beach", "sunset", "vacation"}
        to_remove = {"sunset"}
        result = existing.difference(to_remove)
        self.assertEqual(result, {"beach", "vacation"})
    
    def test_remove_nonexistent_keyword(self):
        """Test removing a keyword that doesn't exist."""
        existing = {"beach", "sunset"}
        to_remove = {"vacation"}
        result = existing.difference(to_remove)
        self.assertEqual(result, {"beach", "sunset"})
    
    def test_add_and_remove(self):
        """Test adding and removing keywords in one operation."""
        existing = {"beach", "sunset", "old"}
        to_add = {"vacation", "mountains"}
        to_remove = {"old"}
        result = existing.union(to_add).difference(to_remove)
        self.assertEqual(result, {"beach", "mountains", "sunset", "vacation"})
    
    def test_complex_scenario(self):
        """Test complex scenario: existing keywords, add some (including duplicates), remove some."""
        # File has: First, Second, Third
        existing = {"First", "Second", "Third"}
        # User wants to add: First (duplicate), Fourth
        to_add = {"First", "Fourth"}
        # User wants to remove: Second
        to_remove = {"Second"}
        
        result = existing.union(to_add).difference(to_remove)
        # Should have: First, Third, Fourth (Second removed, First not duplicated)
        self.assertEqual(result, {"First", "Third", "Fourth"})
        self.assertEqual(len(result), 3)


class TestIntegrationWithExiftool(unittest.TestCase):
    """Integration tests that create actual image files and run exiftool."""
    
    @classmethod
    def setUpClass(cls):
        """Check if exiftool is available."""
        try:
            subprocess.run(["exiftool", "-ver"], capture_output=True, check=True)
            cls.exiftool_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            cls.exiftool_available = False
    
    def setUp(self):
        """Create a temporary image file for each test."""
        if not self.exiftool_available:
            self.skipTest("exiftool not available")
        
        # Create a temporary directory
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a JPEG file instead of PNG (simpler and more compatible with IPTC)
        self.test_image = os.path.join(self.temp_dir, "test_image.jpg")
        
        # Minimal valid JPEG (1x1 white pixel)
        # This is a properly formatted JPEG with correct markers
        jpeg_data = (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c'
            b'\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c'
            b'\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08'
            b'\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xc4\x00\x14'
            b'\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\x00\xff\xd9'
        )
        with open(self.test_image, 'wb') as f:
            f.write(jpeg_data)
    
    def tearDown(self):
        """Clean up temporary files."""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            # Remove all files in temp directory
            for filename in os.listdir(self.temp_dir):
                filepath = os.path.join(self.temp_dir, filename)
                try:
                    os.remove(filepath)
                except Exception:
                    pass
            # Remove the directory
            try:
                os.rmdir(self.temp_dir)
            except Exception:
                pass
    
    def get_keywords_from_file(self, filepath):
        """Helper to read keywords from a file using exiftool."""
        cmd = ["exiftool", "-G", "-json", "-XMP-dc:Subject", "-IPTC:Keywords", filepath]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        if data and isinstance(data, list) and data[0]:
            file_tags = data[0]
            subjects = (file_tags.get("XMP-dc:Subject") or 
                       file_tags.get("XMP:Subject") or 
                       file_tags.get("Subject", []))
            iptc_keywords = (file_tags.get("IPTC:Keywords") or 
                            file_tags.get("Keywords", []))
            return {
                "XMP-dc:Subject": subjects if isinstance(subjects, list) else [subjects] if subjects else [],
                "IPTC:Keywords": iptc_keywords if isinstance(iptc_keywords, list) else [iptc_keywords] if iptc_keywords else []
            }
        return {"XMP-dc:Subject": [], "IPTC:Keywords": []}
    
    def test_add_single_keyword_to_empty_file(self):
        """Test adding a single keyword to a file with no keywords."""
        # Add keyword
        tags = {
            "XMP-dc:Subject": ["vacation"],
            "IPTC:Keywords": ["vacation"]
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify
        keywords = self.get_keywords_from_file(self.test_image)
        self.assertEqual(keywords["XMP-dc:Subject"], ["vacation"])
        self.assertEqual(keywords["IPTC:Keywords"], ["vacation"])
    
    def test_add_multiple_keywords(self):
        """Test adding multiple keywords at once."""
        tags = {
            "XMP-dc:Subject": ["vacation", "beach", "sunset"],
            "IPTC:Keywords": ["vacation", "beach", "sunset"]
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify
        keywords = self.get_keywords_from_file(self.test_image)
        self.assertEqual(sorted(keywords["XMP-dc:Subject"]), ["beach", "sunset", "vacation"])
        self.assertEqual(sorted(keywords["IPTC:Keywords"]), ["beach", "sunset", "vacation"])
    
    def test_add_keyword_twice_no_duplicate(self):
        """Test that adding the same keyword twice doesn't create duplicates."""
        # First, add "vacation"
        tags = {
            "XMP-dc:Subject": ["vacation"],
            "IPTC:Keywords": ["vacation"]
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Read existing keywords
        existing = get_existing_keywords(self.test_image)
        
        # Merge with the same keyword (simulating --add-keyword vacation again)
        current_subjects = set(existing.get("XMP-dc:Subject", []))
        keywords_to_add = {"vacation"}
        updated_subjects = current_subjects.union(keywords_to_add)
        
        # Write back
        tags = {
            "XMP-dc:Subject": sorted(list(updated_subjects)),
            "IPTC:Keywords": sorted(list(updated_subjects))
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify - should still have only one "vacation"
        keywords = self.get_keywords_from_file(self.test_image)
        self.assertEqual(keywords["XMP-dc:Subject"], ["vacation"])
        self.assertEqual(keywords["IPTC:Keywords"], ["vacation"])
        # Explicitly check count
        self.assertEqual(len(keywords["XMP-dc:Subject"]), 1)
    
    def test_add_new_keyword_to_existing(self):
        """Test adding a new keyword to existing keywords."""
        # First, add "vacation"
        tags = {
            "XMP-dc:Subject": ["vacation"],
            "IPTC:Keywords": ["vacation"]
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Read existing keywords
        existing = get_existing_keywords(self.test_image)
        
        # Add "beach"
        current_subjects = set(existing.get("XMP-dc:Subject", []))
        keywords_to_add = {"beach"}
        updated_subjects = current_subjects.union(keywords_to_add)
        
        # Write back
        tags = {
            "XMP-dc:Subject": sorted(list(updated_subjects)),
            "IPTC:Keywords": sorted(list(updated_subjects))
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify - should have both keywords
        keywords = self.get_keywords_from_file(self.test_image)
        self.assertEqual(sorted(keywords["XMP-dc:Subject"]), ["beach", "vacation"])
        self.assertEqual(sorted(keywords["IPTC:Keywords"]), ["beach", "vacation"])
    
    def test_add_multiple_keywords_with_existing_overlap(self):
        """Test adding multiple keywords where some already exist."""
        # First, add "vacation" and "beach"
        tags = {
            "XMP-dc:Subject": ["vacation", "beach"],
            "IPTC:Keywords": ["vacation", "beach"]
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Read existing keywords
        existing = get_existing_keywords(self.test_image)
        
        # Try to add "beach" (duplicate) and "sunset" (new)
        current_subjects = set(existing.get("XMP-dc:Subject", []))
        keywords_to_add = {"beach", "sunset"}
        updated_subjects = current_subjects.union(keywords_to_add)
        
        # Write back
        tags = {
            "XMP-dc:Subject": sorted(list(updated_subjects)),
            "IPTC:Keywords": sorted(list(updated_subjects))
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify - should have all three, no duplicates
        keywords = self.get_keywords_from_file(self.test_image)
        self.assertEqual(sorted(keywords["XMP-dc:Subject"]), ["beach", "sunset", "vacation"])
        self.assertEqual(sorted(keywords["IPTC:Keywords"]), ["beach", "sunset", "vacation"])
        self.assertEqual(len(keywords["XMP-dc:Subject"]), 3)
    
    def test_remove_keyword(self):
        """Test removing a keyword from existing keywords."""
        # First, add multiple keywords
        tags = {
            "XMP-dc:Subject": ["vacation", "beach", "sunset"],
            "IPTC:Keywords": ["vacation", "beach", "sunset"]
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Read existing keywords
        existing = get_existing_keywords(self.test_image)
        
        # Remove "beach"
        current_subjects = set(existing.get("XMP-dc:Subject", []))
        keywords_to_remove = {"beach"}
        updated_subjects = current_subjects.difference(keywords_to_remove)
        
        # Write back
        tags = {
            "XMP-dc:Subject": sorted(list(updated_subjects)),
            "IPTC:Keywords": sorted(list(updated_subjects))
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify - should have only vacation and sunset
        keywords = self.get_keywords_from_file(self.test_image)
        self.assertEqual(sorted(keywords["XMP-dc:Subject"]), ["sunset", "vacation"])
        self.assertEqual(sorted(keywords["IPTC:Keywords"]), ["sunset", "vacation"])
    
    def test_clear_all_keywords(self):
        """Test clearing all keywords."""
        # First, add keywords
        tags = {
            "XMP-dc:Subject": ["vacation", "beach"],
            "IPTC:Keywords": ["vacation", "beach"]
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Clear keywords
        tags = {
            "XMP-dc:Subject": [],
            "IPTC:Keywords": []
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify - should have no keywords
        keywords = self.get_keywords_from_file(self.test_image)
        self.assertEqual(keywords["XMP-dc:Subject"], [])
        self.assertEqual(keywords["IPTC:Keywords"], [])
    
    def test_get_existing_keywords_function(self):
        """Test the get_existing_keywords function directly."""
        # Add keywords using exiftool directly
        tags = {
            "XMP-dc:Subject": ["vacation", "beach"],
            "IPTC:Keywords": ["vacation", "beach"]
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Use get_existing_keywords function
        keywords = get_existing_keywords(self.test_image)
        
        # Verify
        self.assertEqual(sorted(keywords["XMP-dc:Subject"]), ["beach", "vacation"])
        self.assertEqual(sorted(keywords["IPTC:Keywords"]), ["beach", "vacation"])
    
    def test_complex_workflow(self):
        """Test a complex workflow: add, add duplicate, add new, remove."""
        # Step 1: Add "First"
        tags = {"XMP-dc:Subject": ["First"], "IPTC:Keywords": ["First"]}
        run_exiftool([self.test_image], tags, dry_run=False)
        keywords = self.get_keywords_from_file(self.test_image)
        self.assertEqual(keywords["XMP-dc:Subject"], ["First"])
        
        # Step 2: Add "First" again (should not duplicate)
        existing = get_existing_keywords(self.test_image)
        updated = sorted(list(set(existing["XMP-dc:Subject"]).union({"First"})))
        tags = {"XMP-dc:Subject": updated, "IPTC:Keywords": updated}
        run_exiftool([self.test_image], tags, dry_run=False)
        keywords = self.get_keywords_from_file(self.test_image)
        self.assertEqual(keywords["XMP-dc:Subject"], ["First"])
        self.assertEqual(len(keywords["XMP-dc:Subject"]), 1)
        
        # Step 3: Add "Second"
        existing = get_existing_keywords(self.test_image)
        updated = sorted(list(set(existing["XMP-dc:Subject"]).union({"Second"})))
        tags = {"XMP-dc:Subject": updated, "IPTC:Keywords": updated}
        run_exiftool([self.test_image], tags, dry_run=False)
        keywords = self.get_keywords_from_file(self.test_image)
        self.assertEqual(sorted(keywords["XMP-dc:Subject"]), ["First", "Second"])
        
        # Step 4: Add "Third" and "First" (First should not duplicate)
        existing = get_existing_keywords(self.test_image)
        updated = sorted(list(set(existing["XMP-dc:Subject"]).union({"Third", "First"})))
        tags = {"XMP-dc:Subject": updated, "IPTC:Keywords": updated}
        run_exiftool([self.test_image], tags, dry_run=False)
        keywords = self.get_keywords_from_file(self.test_image)
        self.assertEqual(sorted(keywords["XMP-dc:Subject"]), ["First", "Second", "Third"])
        self.assertEqual(len(keywords["XMP-dc:Subject"]), 3)
        
        # Step 5: Remove "Second"
        existing = get_existing_keywords(self.test_image)
        updated = sorted(list(set(existing["XMP-dc:Subject"]).difference({"Second"})))
        tags = {"XMP-dc:Subject": updated, "IPTC:Keywords": updated}
        run_exiftool([self.test_image], tags, dry_run=False)
        keywords = self.get_keywords_from_file(self.test_image)
        self.assertEqual(sorted(keywords["XMP-dc:Subject"]), ["First", "Third"])


class TestIntegrationLocationAndMetadata(unittest.TestCase):
    """Integration tests for location, caption, date, and offset functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Check if exiftool is available."""
        try:
            subprocess.run(["exiftool", "-ver"], capture_output=True, check=True)
            cls.exiftool_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            cls.exiftool_available = False
    
    def setUp(self):
        """Create a temporary image file for each test."""
        if not self.exiftool_available:
            self.skipTest("exiftool not available")
        
        # Create a temporary directory
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a JPEG file
        self.test_image = os.path.join(self.temp_dir, "test_image.jpg")
        
        # Minimal valid JPEG (1x1 white pixel)
        jpeg_data = (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c'
            b'\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c'
            b'\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08'
            b'\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xc4\x00\x14'
            b'\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\x00\xff\xd9'
        )
        with open(self.test_image, 'wb') as f:
            f.write(jpeg_data)
    
    def tearDown(self):
        """Clean up temporary files."""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            # Remove all files in temp directory
            for filename in os.listdir(self.temp_dir):
                filepath = os.path.join(self.temp_dir, filename)
                try:
                    os.remove(filepath)
                except Exception:
                    pass
            # Remove the directory
            try:
                os.rmdir(self.temp_dir)
            except Exception:
                pass
    
    def get_metadata_from_file(self, filepath, *tags):
        """Helper to read specific metadata tags from a file using exiftool."""
        tag_args = []
        for tag in tags:
            tag_args.extend([f"-{tag}"])
        
        cmd = ["exiftool", "-G", "-json"] + tag_args + [filepath]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        if data and isinstance(data, list) and data[0]:
            return data[0]
        return {}
    
    def test_add_caption(self):
        """Test adding a caption to an image."""
        tags = {"Caption-Abstract": "My vacation photo"}
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify
        metadata = self.get_metadata_from_file(self.test_image, "Caption-Abstract")
        # Caption-Abstract might be returned with different group prefixes
        caption = (metadata.get("IPTC:Caption-Abstract") or 
                  metadata.get("Caption-Abstract") or
                  metadata.get("XMP:Description"))
        self.assertEqual(caption, "My vacation photo")
    
    def test_add_date_and_offset(self):
        """Test adding date/time and timezone offset."""
        tags = {
            "DateTimeOriginal": "2026:01:15 14:30:00",
            "CreateDate": "2026:01:15 14:30:00",
            "OffsetTimeOriginal": "+05:30",
            "OffsetTimeDigitized": "+05:30"
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify
        metadata = self.get_metadata_from_file(
            self.test_image, 
            "DateTimeOriginal", 
            "CreateDate",
            "OffsetTimeOriginal",
            "OffsetTimeDigitized"
        )
        
        # Check date/time
        date_original = (metadata.get("EXIF:DateTimeOriginal") or 
                        metadata.get("DateTimeOriginal"))
        create_date = (metadata.get("EXIF:CreateDate") or 
                      metadata.get("CreateDate"))
        
        self.assertEqual(date_original, "2026:01:15 14:30:00")
        self.assertEqual(create_date, "2026:01:15 14:30:00")
        
        # Check offsets
        offset_original = (metadata.get("EXIF:OffsetTimeOriginal") or 
                          metadata.get("OffsetTimeOriginal"))
        offset_digitized = (metadata.get("EXIF:OffsetTimeDigitized") or 
                           metadata.get("OffsetTimeDigitized"))
        
        self.assertEqual(offset_original, "+05:30")
        self.assertEqual(offset_digitized, "+05:30")
    
    def test_add_gps_coordinates(self):
        """Test adding GPS coordinates."""
        tags = {
            "GPSLatitude": 28.6139,
            "GPSLatitudeRef": "N",
            "GPSLongitude": 77.2090,
            "GPSLongitudeRef": "E",
            "GPSAltitude": 216
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify
        metadata = self.get_metadata_from_file(
            self.test_image,
            "GPSLatitude",
            "GPSLatitudeRef",
            "GPSLongitude",
            "GPSLongitudeRef",
            "GPSAltitude"
        )
        
        # GPS coordinates are returned with EXIF: prefix
        gps_lat = (metadata.get("EXIF:GPSLatitude") or 
                  metadata.get("GPS:GPSLatitude") or 
                  metadata.get("GPSLatitude"))
        gps_lat_ref = (metadata.get("EXIF:GPSLatitudeRef") or 
                      metadata.get("GPS:GPSLatitudeRef") or 
                      metadata.get("GPSLatitudeRef"))
        gps_lon = (metadata.get("EXIF:GPSLongitude") or 
                  metadata.get("GPS:GPSLongitude") or 
                  metadata.get("GPSLongitude"))
        gps_lon_ref = (metadata.get("EXIF:GPSLongitudeRef") or 
                      metadata.get("GPS:GPSLongitudeRef") or 
                      metadata.get("GPSLongitudeRef"))
        gps_alt = (metadata.get("EXIF:GPSAltitude") or 
                  metadata.get("GPS:GPSAltitude") or 
                  metadata.get("GPSAltitude"))
        
        self.assertIsNotNone(gps_lat)
        # exiftool returns "North" or "N" depending on version
        self.assertIn(gps_lat_ref, ["N", "North"])
        self.assertIsNotNone(gps_lon)
        self.assertIn(gps_lon_ref, ["E", "East"])
        self.assertIsNotNone(gps_alt)
    
    def test_add_location_tags(self):
        """Test adding location metadata tags."""
        tags = {
            "XMP-photoshop:City": "New Delhi",
            "XMP-photoshop:State": "Delhi",
            "XMP-photoshop:Country": "India",
            "XMP-iptcExt:LocationShownCity": "New Delhi",
            "XMP-iptcExt:LocationShownProvinceState": "Delhi",
            "XMP-iptcExt:LocationShownCountryName": "India",
            "XMP-iptcExt:LocationShownCountryCode": "IN",
            "XMP-dc:Coverage": "New Delhi, India"
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify
        metadata = self.get_metadata_from_file(
            self.test_image,
            "XMP-photoshop:City",
            "XMP-photoshop:State",
            "XMP-photoshop:Country",
            "XMP-iptcExt:LocationShownCity",
            "XMP-iptcExt:LocationShownCountryCode",
            "XMP-dc:Coverage"
        )
        
        # Check Photoshop tags
        city = (metadata.get("XMP-photoshop:City") or 
               metadata.get("XMP:City"))
        state = (metadata.get("XMP-photoshop:State") or 
                metadata.get("XMP:State"))
        country = (metadata.get("XMP-photoshop:Country") or 
                  metadata.get("XMP:Country"))
        
        self.assertEqual(city, "New Delhi")
        self.assertEqual(state, "Delhi")
        self.assertEqual(country, "India")
        
        # Check IPTC Extension tags
        location_city = (metadata.get("XMP-iptcExt:LocationShownCity") or 
                        metadata.get("XMP:LocationShownCity"))
        country_code = (metadata.get("XMP-iptcExt:LocationShownCountryCode") or 
                       metadata.get("XMP:LocationShownCountryCode"))
        
        self.assertEqual(location_city, "New Delhi")
        self.assertEqual(country_code, "IN")
        
        # Check Coverage
        coverage = (metadata.get("XMP-dc:Coverage") or 
                   metadata.get("XMP:Coverage"))
        self.assertEqual(coverage, "New Delhi, India")
    
    def test_combined_metadata(self):
        """Test adding multiple types of metadata together."""
        tags = {
            "Caption-Abstract": "Vacation in New Delhi",
            "DateTimeOriginal": "2026:01:15 14:30:00",
            "OffsetTimeOriginal": "+05:30",
            "GPSLatitude": 28.6139,
            "GPSLatitudeRef": "N",
            "GPSLongitude": 77.2090,
            "GPSLongitudeRef": "E",
            "XMP-photoshop:City": "New Delhi",
            "XMP-photoshop:Country": "India",
            "XMP-dc:Subject": ["vacation", "travel", "india"],
            "IPTC:Keywords": ["vacation", "travel", "india"]
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify caption
        metadata = self.get_metadata_from_file(self.test_image, "Caption-Abstract")
        caption = (metadata.get("IPTC:Caption-Abstract") or 
                  metadata.get("Caption-Abstract"))
        self.assertEqual(caption, "Vacation in New Delhi")
        
        # Verify date
        metadata = self.get_metadata_from_file(self.test_image, "DateTimeOriginal")
        date = (metadata.get("EXIF:DateTimeOriginal") or 
               metadata.get("DateTimeOriginal"))
        self.assertEqual(date, "2026:01:15 14:30:00")
        
        # Verify GPS
        metadata = self.get_metadata_from_file(self.test_image, "GPSLatitudeRef")
        gps_ref = (metadata.get("EXIF:GPSLatitudeRef") or 
                  metadata.get("GPS:GPSLatitudeRef") or 
                  metadata.get("GPSLatitudeRef"))
        self.assertIn(gps_ref, ["N", "North"])
        
        # Verify location
        metadata = self.get_metadata_from_file(self.test_image, "XMP-photoshop:City")
        city = (metadata.get("XMP-photoshop:City") or 
               metadata.get("XMP:City"))
        self.assertEqual(city, "New Delhi")
        
        # Verify keywords
        metadata = self.get_metadata_from_file(self.test_image, "XMP-dc:Subject")
        subjects = (metadata.get("XMP-dc:Subject") or 
                   metadata.get("XMP:Subject") or 
                   metadata.get("Subject", []))
        if isinstance(subjects, str):
            subjects = [subjects]
        self.assertEqual(sorted(subjects), ["india", "travel", "vacation"])
    
    def test_update_existing_metadata(self):
        """Test updating existing metadata without losing other fields."""
        # First, add some metadata
        tags = {
            "Caption-Abstract": "Original caption",
            "DateTimeOriginal": "2026:01:01 12:00:00",
            "XMP-dc:Subject": ["original"],
            "IPTC:Keywords": ["original"]
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Now update just the caption
        tags = {"Caption-Abstract": "Updated caption"}
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify caption is updated
        metadata = self.get_metadata_from_file(self.test_image, "Caption-Abstract")
        caption = (metadata.get("IPTC:Caption-Abstract") or 
                  metadata.get("Caption-Abstract"))
        self.assertEqual(caption, "Updated caption")
        
        # Verify date is still there
        metadata = self.get_metadata_from_file(self.test_image, "DateTimeOriginal")
        date = (metadata.get("EXIF:DateTimeOriginal") or 
               metadata.get("DateTimeOriginal"))
        self.assertEqual(date, "2026:01:01 12:00:00")
        
        # Verify keywords are still there
        metadata = self.get_metadata_from_file(self.test_image, "XMP-dc:Subject")
        subjects = (metadata.get("XMP-dc:Subject") or 
                   metadata.get("XMP:Subject") or 
                   metadata.get("Subject", []))
        if isinstance(subjects, str):
            subjects = [subjects]
        self.assertEqual(subjects, ["original"])
    
    def test_negative_gps_coordinates(self):
        """Test adding GPS coordinates in southern and western hemispheres."""
        tags = {
            "GPSLatitude": 45.0312,  # Absolute value
            "GPSLatitudeRef": "S",   # Southern hemisphere
            "GPSLongitude": 168.6626,  # Absolute value
            "GPSLongitudeRef": "E",    # Eastern hemisphere
            "GPSAltitude": 310
        }
        run_exiftool([self.test_image], tags, dry_run=False)
        
        # Verify
        metadata = self.get_metadata_from_file(
            self.test_image,
            "GPSLatitudeRef",
            "GPSLongitudeRef"
        )
        
        gps_lat_ref = (metadata.get("EXIF:GPSLatitudeRef") or 
                      metadata.get("GPS:GPSLatitudeRef") or 
                      metadata.get("GPSLatitudeRef"))
        gps_lon_ref = (metadata.get("EXIF:GPSLongitudeRef") or 
                      metadata.get("GPS:GPSLongitudeRef") or 
                      metadata.get("GPSLongitudeRef"))
        
        self.assertIn(gps_lat_ref, ["S", "South"])
        self.assertIn(gps_lon_ref, ["E", "East"])
    
    def test_different_timezone_offsets(self):
        """Test adding different timezone offsets."""
        test_cases = [
            ("+00:00", "UTC"),
            ("-05:00", "EST"),
            ("+05:30", "IST"),
            ("+09:00", "JST"),
            ("-08:00", "PST")
        ]
        
        for offset, timezone_name in test_cases:
            with self.subTest(timezone=timezone_name, offset=offset):
                tags = {
                    "DateTimeOriginal": "2026:01:15 12:00:00",
                    "OffsetTimeOriginal": offset
                }
                run_exiftool([self.test_image], tags, dry_run=False)
                
                # Verify
                metadata = self.get_metadata_from_file(
                    self.test_image,
                    "OffsetTimeOriginal"
                )
                
                offset_value = (metadata.get("EXIF:OffsetTimeOriginal") or 
                              metadata.get("OffsetTimeOriginal"))
                self.assertEqual(offset_value, offset)


if __name__ == "__main__":
    unittest.main()
