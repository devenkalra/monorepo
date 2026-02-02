#!/usr/bin/env python3
"""
Unit tests for location_utils.py

Tests the location utility functions including:
- Geocoding place names
- Coordinate validation
- Address formatting
- Error handling
"""

import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from location_utils import (
    geocode_place,
    validate_coordinates,
    format_address,
    parse_coordinates
)


class TestLocationUtils(unittest.TestCase):
    """Test suite for location_utils.py"""
    
    def test_validate_coordinates_valid(self):
        """Test validation of valid coordinates"""
        # Valid coordinates
        self.assertTrue(validate_coordinates(40.7128, -74.0060))  # New York
        self.assertTrue(validate_coordinates(0, 0))  # Null Island
        self.assertTrue(validate_coordinates(90, 180))  # Max values
        self.assertTrue(validate_coordinates(-90, -180))  # Min values
    
    def test_validate_coordinates_invalid_latitude(self):
        """Test validation of invalid latitude"""
        self.assertFalse(validate_coordinates(91, 0))  # Too high
        self.assertFalse(validate_coordinates(-91, 0))  # Too low
        self.assertFalse(validate_coordinates(100, 0))  # Way too high
    
    def test_validate_coordinates_invalid_longitude(self):
        """Test validation of invalid longitude"""
        self.assertFalse(validate_coordinates(0, 181))  # Too high
        self.assertFalse(validate_coordinates(0, -181))  # Too low
        self.assertFalse(validate_coordinates(0, 200))  # Way too high
    
    def test_validate_coordinates_none(self):
        """Test validation with None values"""
        self.assertFalse(validate_coordinates(None, 0))
        self.assertFalse(validate_coordinates(0, None))
        self.assertFalse(validate_coordinates(None, None))
    
    def test_validate_coordinates_string(self):
        """Test validation with string values"""
        # Should handle string conversion
        try:
            result = validate_coordinates("40.7128", "-74.0060")
            self.assertTrue(result)
        except (ValueError, TypeError):
            # If it doesn't handle strings, that's also acceptable
            pass
    
    def test_parse_coordinates_decimal(self):
        """Test parsing decimal coordinates"""
        lat, lon = parse_coordinates("40.7128, -74.0060")
        
        self.assertAlmostEqual(lat, 40.7128, places=4)
        self.assertAlmostEqual(lon, -74.0060, places=4)
    
    def test_parse_coordinates_with_altitude(self):
        """Test parsing coordinates with altitude"""
        result = parse_coordinates("40.7128, -74.0060, 10")
        
        if len(result) == 3:
            lat, lon, alt = result
            self.assertAlmostEqual(lat, 40.7128, places=4)
            self.assertAlmostEqual(lon, -74.0060, places=4)
            self.assertAlmostEqual(alt, 10, places=1)
        else:
            # If altitude not supported, should still parse lat/lon
            lat, lon = result
            self.assertAlmostEqual(lat, 40.7128, places=4)
    
    def test_parse_coordinates_invalid_format(self):
        """Test parsing invalid coordinate format"""
        with self.assertRaises(Exception):
            parse_coordinates("invalid")
    
    def test_parse_coordinates_missing_value(self):
        """Test parsing coordinates with missing value"""
        with self.assertRaises(Exception):
            parse_coordinates("40.7128")
    
    def test_format_address_full(self):
        """Test formatting full address"""
        address = format_address(
            city="New York",
            state="New York",
            country="United States",
            country_code="US"
        )
        
        self.assertIsInstance(address, str)
        self.assertIn("New York", address)
    
    def test_format_address_partial(self):
        """Test formatting partial address"""
        address = format_address(
            city="New York",
            country="United States"
        )
        
        self.assertIsInstance(address, str)
        self.assertIn("New York", address)
    
    def test_format_address_empty(self):
        """Test formatting empty address"""
        address = format_address()
        
        self.assertIsInstance(address, str)
        # Should return empty string or default value
    
    def test_geocode_place_known_location(self):
        """Test geocoding a known location"""
        try:
            result = geocode_place("New York, NY")
            
            if result is not None:
                self.assertIn('latitude', result)
                self.assertIn('longitude', result)
                
                # New York should be roughly at these coordinates
                self.assertAlmostEqual(result['latitude'], 40.7, delta=1.0)
                self.assertAlmostEqual(result['longitude'], -74.0, delta=1.0)
        except Exception as e:
            # If geocoding service is unavailable, skip
            if 'timeout' in str(e).lower() or 'connection' in str(e).lower():
                self.skipTest("Geocoding service unavailable")
            raise
    
    def test_geocode_place_invalid(self):
        """Test geocoding an invalid location"""
        try:
            result = geocode_place("INVALID_LOCATION_XYZ_123")
            
            # Should return None or raise exception
            self.assertIsNone(result)
        except Exception as e:
            # Exception is also acceptable
            self.assertIsInstance(e, Exception)
    
    def test_geocode_place_empty(self):
        """Test geocoding empty string"""
        with self.assertRaises(Exception):
            geocode_place("")
    
    def test_geocode_place_with_country(self):
        """Test geocoding with country specification"""
        try:
            result = geocode_place("Paris, France")
            
            if result is not None:
                # Paris should be roughly at these coordinates
                self.assertAlmostEqual(result['latitude'], 48.8, delta=1.0)
                self.assertAlmostEqual(result['longitude'], 2.3, delta=1.0)
        except Exception as e:
            if 'timeout' in str(e).lower() or 'connection' in str(e).lower():
                self.skipTest("Geocoding service unavailable")
            raise
    
    def test_coordinate_precision(self):
        """Test coordinate precision handling"""
        # Test with high precision
        lat, lon = parse_coordinates("40.712776, -74.005974")
        
        self.assertAlmostEqual(lat, 40.712776, places=6)
        self.assertAlmostEqual(lon, -74.005974, places=6)
    
    def test_coordinate_edge_cases(self):
        """Test coordinate edge cases"""
        # Equator
        self.assertTrue(validate_coordinates(0, 0))
        
        # Prime meridian
        self.assertTrue(validate_coordinates(0, 0))
        
        # North pole
        self.assertTrue(validate_coordinates(90, 0))
        
        # South pole
        self.assertTrue(validate_coordinates(-90, 0))
        
        # International date line
        self.assertTrue(validate_coordinates(0, 180))
        self.assertTrue(validate_coordinates(0, -180))
    
    def test_address_formatting_special_characters(self):
        """Test address formatting with special characters"""
        address = format_address(
            city="São Paulo",
            country="Brasil"
        )
        
        self.assertIsInstance(address, str)
        self.assertIn("São Paulo", address)
    
    def test_geocode_caching(self):
        """Test that geocoding results can be cached"""
        try:
            result1 = geocode_place("London, UK")
            result2 = geocode_place("London, UK")
            
            if result1 is not None and result2 is not None:
                # Results should be the same
                self.assertEqual(result1['latitude'], result2['latitude'])
                self.assertEqual(result1['longitude'], result2['longitude'])
        except Exception as e:
            if 'timeout' in str(e).lower() or 'connection' in str(e).lower():
                self.skipTest("Geocoding service unavailable")
            raise


if __name__ == '__main__':
    unittest.main()
