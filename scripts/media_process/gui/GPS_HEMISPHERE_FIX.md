# GPS Hemisphere Reference Fix

## Issue
GPS coordinates need to be negated based on hemisphere references (S for South, W for West) before being sent to map services.

## Fix Applied

### Problem
The original implementation only applied hemisphere references when coordinates were in string format (DMS). When exiftool returned coordinates as decimal numbers, the hemisphere reference was not being applied, leading to incorrect map locations.

### Solution
Updated `get_gps_coordinates()` method to handle both cases:

1. **String coordinates** (e.g., "37 deg 46' 29.99\" N"):
   - Parse DMS format
   - Apply reference in `_parse_gps_coordinate()`

2. **Numeric coordinates** (e.g., 37.7749):
   - Use value directly
   - **Apply reference explicitly**:
     ```python
     if lat_ref == 'S':
         lat = -lat
     if lon_ref == 'W':
         lon = -lon
     ```

## Code Changes

### Before
```python
# Convert to decimal if needed
if isinstance(lat, str):
    lat = self._parse_gps_coordinate(lat, exif.get('GPSLatitudeRef', 'N'))
if isinstance(lon, str):
    lon = self._parse_gps_coordinate(lon, exif.get('GPSLongitudeRef', 'E'))
```

### After
```python
lat_ref = exif.get('GPSLatitudeRef', 'N')
lon_ref = exif.get('GPSLongitudeRef', 'E')

# Convert to decimal if needed, always applying reference
if isinstance(lat, str):
    lat = self._parse_gps_coordinate(lat, lat_ref)
else:
    # Already a number, but still need to apply reference
    lat = float(lat)
    if lat_ref == 'S':
        lat = -lat

if isinstance(lon, str):
    lon = self._parse_gps_coordinate(lon, lon_ref)
else:
    # Already a number, but still need to apply reference
    lon = float(lon)
    if lon_ref == 'W':
        lon = -lon
```

## Hemisphere Reference Rules

### Latitude
- **N (North)**: Positive values (0° to +90°)
- **S (South)**: Negative values (0° to -90°)

### Longitude
- **E (East)**: Positive values (0° to +180°)
- **W (West)**: Negative values (0° to -180°)

## Test Cases

### Test 1: Northern Hemisphere, Eastern Hemisphere
```
Input:  Lat=48.8584, LatRef=N, Lon=2.2945, LonRef=E
Output: Lat=48.8584, Lon=2.2945
Result: Paris, France (correct)
```

### Test 2: Northern Hemisphere, Western Hemisphere
```
Input:  Lat=40.7489, LatRef=N, Lon=73.9854, LonRef=W
Output: Lat=40.7489, Lon=-73.9854
Result: New York, USA (correct)
```

### Test 3: Southern Hemisphere, Eastern Hemisphere
```
Input:  Lat=33.8651, LatRef=S, Lon=151.2099, LonRef=E
Output: Lat=-33.8651, Lon=151.2099
Result: Sydney, Australia (correct)
```

### Test 4: Southern Hemisphere, Western Hemisphere
```
Input:  Lat=22.9068, LatRef=S, Lon=43.1729, LonRef=W
Output: Lat=-22.9068, Lon=-43.1729
Result: Rio de Janeiro, Brazil (correct)
```

## Impact

### Before Fix
- Photos from Southern hemisphere would show in Northern hemisphere
- Photos from Western hemisphere would show in Eastern hemisphere
- Example: Sydney photo would show in Northern Australia instead of Sydney

### After Fix
- All coordinates correctly positioned on map
- Hemisphere references properly applied
- Maps show accurate locations worldwide

## Verification

To verify the fix works:

1. **Test with Northern/Eastern photo** (e.g., Paris):
   - Should show positive lat, positive lon
   - Map should show correct location

2. **Test with Northern/Western photo** (e.g., New York):
   - Should show positive lat, negative lon
   - Map should show correct location

3. **Test with Southern/Eastern photo** (e.g., Sydney):
   - Should show negative lat, positive lon
   - Map should show correct location

4. **Test with Southern/Western photo** (e.g., Rio):
   - Should show negative lat, negative lon
   - Map should show correct location

## Related Files

- `media_processor_app.py`: Main implementation
- `SHOW_LOCATION_FEATURE.md`: Feature documentation
- `IMPLEMENTATION_SUMMARY.md`: Overall summary

## Technical Notes

### Why This Matters
Map services (OpenStreetMap, Google Maps) use the standard geographic coordinate system where:
- Negative latitude = South of equator
- Negative longitude = West of prime meridian

Without proper negation, locations would be mirrored across the equator and/or prime meridian.

### exiftool Behavior
exiftool can return GPS coordinates in two formats:
1. **String with reference**: "37 deg 46' 29.99\" N"
2. **Numeric with separate reference**: Lat=37.7749, LatRef=N

Both formats need the reference applied, which is why we handle both cases.
