#!/usr/bin/env python3
"""location_utils.py - Shared utilities for geocoding and location metadata.

This module provides functions for geocoding place names and extracting
location metadata for use in EXIF tags and other applications.
"""

import requests
import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from typing import Dict, Optional, Tuple


def geocode_place(place_name: str, user_agent: str = "ExifLocationTool/1.0 (contact: deven@example.com)", max_retries: int = 5, timeout: int = 30) -> Optional[object]:
    """Geocode a place name to get location information.
    
    Args:
        place_name: Human-readable location (e.g., "Fort Worth, Texas, USA")
        user_agent: User agent string for Nominatim API
        max_retries: Maximum number of retry attempts (default: 5)
        timeout: Timeout in seconds for each request (default: 30)
    
    Returns:
        Location object from geopy, or None if not found
    
    Raises:
        ValueError: If place cannot be geocoded
    """
    geolocator = Nominatim(user_agent=user_agent, timeout=timeout)
    location = None
    
    for attempt in range(max_retries):
        try:
            # Add delay before each request to respect Nominatim usage policy (1 request per second)
            if attempt > 0:
                time.sleep(1.5)  # 1.5 seconds between retries
            
            # Try with exactly_one=True first (default behavior)
            location = geolocator.geocode(
                place_name, 
                addressdetails=True, 
                language='en', 
                extratags=True,
                exactly_one=True
            )
            
            # If that fails, try without exactly_one to get multiple results and take first
            if not location:
                time.sleep(1.0)  # Delay before second attempt
                locations = geolocator.geocode(
                    place_name,
                    addressdetails=True,
                    language='en',
                    extratags=True,
                    exactly_one=False,
                    limit=5
                )
                if locations and len(locations) > 0:
                    location = locations[0]
            
            # If we got a location, break out of retry loop
            if location:
                break
                
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            print(f"Geocoding attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                # Wait before retrying (exponential backoff, but capped)
                wait_time = min((attempt + 1) * 2.0, 10.0)  # Cap at 10 seconds
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                raise ValueError(f"Geocoding service error after {max_retries} attempts: {e}")
        except Exception as e:
            raise ValueError(f"Error geocoding place: {e}")
    
    if not location:
        raise ValueError(f"Could not geocode place: {place_name}")
    
    return location


def extract_address_components(location: object) -> Dict[str, str]:
    """Extract address components from a geocoded location.
    
    Args:
        location: Location object from geopy
    
    Returns:
        Dictionary with city, state, country, country_code
    """
    address = location.raw.get('address', {}) if isinstance(location.raw, dict) else {}
    namedetails = location.raw.get('namedetails', {}) if isinstance(location.raw, dict) else {}
    
    return {
        'city': address.get('city') or address.get('town') or namedetails.get('city') or "",
        'state': address.get('state') or namedetails.get('state') or "",
        'country': address.get('country') or namedetails.get('country') or "",
        'country_code': address.get('country_code', "").upper()
    }


def get_elevation(latitude: float, longitude: float, timeout: int = 5) -> float:
    """Get elevation for coordinates using open-elevation.com API.
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        timeout: Request timeout in seconds
    
    Returns:
        Elevation in meters, or 0.0 if not available
    """
    try:
        resp = requests.get(
            "https://api.open-elevation.com/api/v1/lookup",
            params={"locations": f"{latitude},{longitude}"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get('results')
            if results and isinstance(results, list):
                elevation = results[0].get('elevation')
                if elevation is not None:
                    return float(elevation)
    except Exception:
        # Silently ignore failures
        pass
    
    return 0.0


def extract_altitude(location: object) -> float:
    """Extract altitude from location object or fetch from elevation API.
    
    Args:
        location: Location object from geopy
    
    Returns:
        Altitude in meters
    """
    altitude = None
    extratags = location.raw.get('extratags', {}) if isinstance(location.raw, dict) else {}
    
    # Try to get elevation from Nominatim extratags
    if extratags is not None:
        if 'ele' in extratags:
            altitude = extratags['ele']
        elif 'elevation' in extratags:
            altitude = extratags['elevation']
    
    # Convert to float
    try:
        altitude = float(altitude)
    except (TypeError, ValueError):
        altitude = 0.0
    
    # If altitude is still 0, fallback to open-elevation.com API
    if altitude == 0.0:
        altitude = get_elevation(location.latitude, location.longitude)
    
    return altitude


def get_location_metadata(place_name: str, date_str: str = "", offset_str: str = "") -> Dict[str, any]:
    """Get complete location metadata for a place name.
    
    Args:
        place_name: Human-readable location
        date_str: Optional date/time in "YYYY:MM:DD HH:MM:SS" format
        offset_str: Optional UTC offset like "+05:30" or "-06:00"
    
    Returns:
        Dictionary with location metadata including GPS coordinates,
        address components, and optional date/time information
    
    Raises:
        ValueError: If place cannot be geocoded
    """
    # Geocode the place
    location = geocode_place(place_name)
    
    # Extract address components
    address = extract_address_components(location)
    
    # Get altitude
    altitude = extract_altitude(location)
    
    # Build metadata dictionary
    metadata = {}
    
    # Add optional date/time tags if supplied
    if date_str:
        metadata["DateTimeOriginal"] = date_str
        metadata["CreateDate"] = date_str
    if offset_str:
        metadata["OffsetTimeOriginal"] = offset_str
        metadata["OffsetTimeDigitized"] = offset_str
    
    # Add GPS and location tags
    metadata.update({
        "GPSLatitude": abs(location.latitude),
        "GPSLatitudeRef": "N" if location.latitude >= 0 else "S",
        "GPSLongitude": abs(location.longitude),
        "GPSLongitudeRef": "E" if location.longitude >= 0 else "W",
        "GPSAltitude": altitude,
        # Photoshop XMP tags
        "XMP-photoshop:City": address['city'],
        "XMP-photoshop:State": address['state'],
        "XMP-photoshop:Country": address['country'],
        # IPTC Extension tags
        "XMP-iptcExt:LocationShownCity": address['city'],
        "XMP-iptcExt:LocationShownProvinceState": address['state'],
        "XMP-iptcExt:LocationShownCountryName": address['country'],
        "XMP-iptcExt:LocationShownCountryCode": address['country_code'],
        # Coverage tag
        "XMP-dc:Coverage": place_name,
    })
    
    return metadata


def get_location_metadata_from_params(
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    altitude: Optional[float] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = None,
    country_code: Optional[str] = None,
    coverage: Optional[str] = None,
    date_str: str = "",
    offset_str: str = ""
) -> Dict[str, any]:
    """Create location metadata from manual parameters.
    
    Args:
        latitude: Latitude coordinate (-90 to 90)
        longitude: Longitude coordinate (-180 to 180)
        altitude: Altitude in meters
        city: City name
        state: State/province name
        country: Country name
        country_code: Country code (e.g., "US")
        coverage: Human-readable location description
        date_str: Optional date/time in "YYYY:MM:DD HH:MM:SS" format
        offset_str: Optional UTC offset like "+05:30" or "-06:00"
    
    Returns:
        Dictionary with location metadata
    """
    metadata = {}
    
    # Add optional date/time tags if supplied
    if date_str:
        metadata["DateTimeOriginal"] = date_str
        metadata["CreateDate"] = date_str
    if offset_str:
        metadata["OffsetTimeOriginal"] = offset_str
        metadata["OffsetTimeDigitized"] = offset_str
    
    # Add GPS coordinates if provided
    if latitude is not None:
        metadata["GPSLatitude"] = abs(latitude)
        metadata["GPSLatitudeRef"] = "N" if latitude >= 0 else "S"
    
    if longitude is not None:
        metadata["GPSLongitude"] = abs(longitude)
        metadata["GPSLongitudeRef"] = "E" if longitude >= 0 else "W"
    
    if altitude is not None:
        metadata["GPSAltitude"] = altitude
    
    # Add location text fields if provided
    if city:
        metadata["XMP-photoshop:City"] = city
        metadata["XMP-iptcExt:LocationShownCity"] = city
    
    if state:
        metadata["XMP-photoshop:State"] = state
        metadata["XMP-iptcExt:LocationShownProvinceState"] = state
    
    if country:
        metadata["XMP-photoshop:Country"] = country
        metadata["XMP-iptcExt:LocationShownCountryName"] = country
    
    if country_code:
        metadata["XMP-iptcExt:LocationShownCountryCode"] = country_code.upper()
    
    if coverage:
        metadata["XMP-dc:Coverage"] = coverage
    
    return metadata


def format_coordinates(latitude: float, longitude: float) -> Tuple[str, str]:
    """Format GPS coordinates for display.
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
    
    Returns:
        Tuple of (formatted_latitude, formatted_longitude)
    """
    lat_dir = "N" if latitude >= 0 else "S"
    lon_dir = "E" if longitude >= 0 else "W"
    
    lat_str = f"{abs(latitude):.6f}° {lat_dir}"
    lon_str = f"{abs(longitude):.6f}° {lon_dir}"
    
    return lat_str, lon_str
