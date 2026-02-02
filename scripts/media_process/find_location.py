#!/usr/bin/env python3
"""find_location.py - Find and display location information for a place name.

This script geocodes a place name and displays the location metadata that
would be added to EXIF tags by apply_exif.py. Useful for verifying location
information before applying it to images.
"""

import argparse
import json
import sys
from typing import Dict

try:
    from location_utils import (
        geocode_place,
        extract_address_components,
        extract_altitude,
        format_coordinates,
        get_location_metadata
    )
except ImportError:
    print("Error: location_utils module not found", file=sys.stderr)
    print("Make sure location_utils.py is in the same directory", file=sys.stderr)
    sys.exit(1)


def display_location_info(place_name: str, verbose: bool = False, json_output: bool = False):
    """Display location information for a place name.
    
    Args:
        place_name: Human-readable location to geocode
        verbose: If True, show detailed information
        json_output: If True, output as JSON
    """
    try:
        # Geocode the place
        print("PN:" + place_name)
        location = geocode_place(place_name)
        
        # Extract components
        address = extract_address_components(location)
        altitude = extract_altitude(location)
        
        # Format coordinates
        lat_str, lon_str = format_coordinates(location.latitude, location.longitude)
        
        if json_output:
            # Output as JSON
            output = {
                'place_name': place_name,
                'latitude': location.latitude,
                'longitude': location.longitude,
                'altitude': altitude,
                'city': address['city'],
                'state': address['state'],
                'country': address['country'],
                'country_code': address['country_code'],
                'display_name': location.address if hasattr(location, 'address') else place_name
            }
            print(json.dumps(output, indent=2))
        else:
            # Human-readable output
            print("=" * 70)
            print(f"Location Information: {place_name}")
            print("=" * 70)
            print()
            
            print("GEOCODING RESULT:")
            if hasattr(location, 'address'):
                print(f"  Full Address: {location.address}")
            print()
            
            print("GPS COORDINATES:")
            print(f"  Latitude:  {lat_str} ({location.latitude})")
            print(f"  Longitude: {lon_str} ({location.longitude})")
            print(f"  Altitude:  {altitude:.1f} meters")
            print()
            
            print("ADDRESS COMPONENTS:")
            print(f"  City:         {address['city'] or '(not found)'}")
            print(f"  State:        {address['state'] or '(not found)'}")
            print(f"  Country:      {address['country'] or '(not found)'}")
            print(f"  Country Code: {address['country_code'] or '(not found)'}")
            print()
            
            if verbose:
                print("EXIF TAGS THAT WOULD BE APPLIED:")
                print(f"  GPSLatitude:  {abs(location.latitude)}")
                print(f"  GPSLatitudeRef:  {'N' if location.latitude >= 0 else 'S'}")
                print(f"  GPSLongitude:  {abs(location.longitude)}")
                print(f"  GPSLongitudeRef:  {'E' if location.longitude >= 0 else 'W'}")
                print(f"  GPSAltitude:  {altitude}")
                print(f"  XMP-photoshop:City:  {address['city']}")
                print(f"  XMP-photoshop:State:  {address['state']}")
                print(f"  XMP-photoshop:Country:  {address['country']}")
                print(f"  XMP-iptcExt:LocationShownCity:  {address['city']}")
                print(f"  XMP-iptcExt:LocationShownProvinceState:  {address['state']}")
                print(f"  XMP-iptcExt:LocationShownCountryName:  {address['country']}")
                print(f"  XMP-iptcExt:LocationShownCountryCode:  {address['country_code']}")
                print(f"  XMP-dc:Coverage:  {place_name}")
                print()
            
            print("=" * 70)
            print("✓ Location found successfully")
            print()
            print("To apply this location to images, use:")
            print(f'  python3 apply_exif.py --place "{place_name}" --files <images>')
            print("=" * 70)
    
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Find and display location information for a place name",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Find location for a city
  python3 find_location.py "Fort Worth, Texas, USA"
  
  # Show detailed EXIF tag information
  python3 find_location.py "Paris, France" --verbose
  
  # Output as JSON
  python3 find_location.py "Tokyo, Japan" --json
  
  # Find location for a specific address
  python3 find_location.py "1600 Pennsylvania Avenue, Washington, DC"
  
  # Find location for a landmark
  python3 find_location.py "Eiffel Tower, Paris"
        """
    )
    
    parser.add_argument("place", help="Place name to geocode (e.g., 'Fort Worth, Texas, USA')")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Show detailed EXIF tag information")
    parser.add_argument("--json", action="store_true",
                       help="Output as JSON")
    
    args = parser.parse_args()
    
    display_location_info(args.place, verbose=args.verbose, json_output=args.json)


if __name__ == "__main__":
    main()
