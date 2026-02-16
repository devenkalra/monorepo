# Show Location Feature

## Overview
The "Show Location" feature allows you to view the GPS location of photos on a map. When a photo contains GPS coordinates in its EXIF data, you can click the "Show Location" button to open the location in your web browser.

## How to Use

### Basic Usage
1. **Select a single file** in the file list
2. Look at the EXIF Display controls (top of the File Information panel)
3. If the file has GPS data, the **"Show Location"** button will be enabled
4. Click **"Show Location"** to open the location on a map

### What Happens
- A dialog shows the GPS coordinates (latitude/longitude)
- If available, shows the location name (City, State, Country)
- Opens the location in your default web browser using OpenStreetMap
- Provides Google Maps URL as alternative

## Button States

### Enabled (Clickable)
The button is enabled when:
- A single file is selected
- The file contains GPS coordinates in EXIF data
- GPS data includes both latitude and longitude

### Disabled (Grayed Out)
The button is disabled when:
- No file is selected
- Multiple files are selected
- The selected file has no GPS data
- The selected file is not an image with EXIF data

## Supported GPS Formats

The feature can parse various GPS coordinate formats:
- Decimal degrees: `37.7749`
- Degrees, minutes, seconds: `37 deg 46' 29.99" N`
- Mixed formats from different cameras
- **Properly handles hemisphere references**:
  - **N** (North): Positive latitude
  - **S** (South): Negative latitude
  - **E** (East): Positive longitude
  - **W** (West): Negative longitude

## Map Services

### Primary: OpenStreetMap
- Free and open-source
- No API key required
- Shows location with marker at zoom level 15
- URL format: `https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=15`

### Alternative: Google Maps
- Also provided in the dialog
- Can be copied and pasted if preferred
- URL format: `https://www.google.com/maps?q={lat},{lon}`

## Example Output

### With Location Name
```
GPS Coordinates:
Latitude: 37.774929
Longitude: -122.419416
Location: San Francisco, California, USA

Opening in web browser...
```

### Without Location Name
```
GPS Coordinates:
Latitude: 37.774929
Longitude: -122.419416

Opening in web browser...
```

### No GPS Data
```
No GPS coordinates found in:
photo.jpg
```

## Location Information

The feature attempts to extract location information from EXIF tags:
- **City**: From `City` or `XMP-photoshop:City` tags
- **State**: From `State` or `XMP-photoshop:State` tags  
- **Country**: From `Country` or `XMP-photoshop:Country` tags

This information is displayed in the dialog and helps identify the location.

## Requirements

### System Requirements
- **exiftool**: Must be installed for GPS extraction
  ```bash
  # Ubuntu/Debian
  sudo apt-get install libimage-exiftool-perl
  
  # macOS
  brew install exiftool
  ```

### Python Requirements
- Standard library only (no additional packages needed)
- Uses `subprocess` to call exiftool
- Uses `webbrowser` to open URLs
- Uses `json` to parse exiftool output

### Browser Requirements
- Any modern web browser
- Must be set as system default browser
- Internet connection required to view maps

## Technical Details

### GPS Data Extraction
1. Calls `exiftool` with GPS-specific flags:
   - `-GPSLatitude`
   - `-GPSLongitude`
   - `-GPSLatitudeRef` (N/S)
   - `-GPSLongitudeRef` (E/W)
   - `-City`, `-State`, `-Country`

2. Parses JSON output from exiftool

3. Converts coordinates to decimal degrees if needed

4. **Applies hemisphere reference correctly**:
   - South (S): Negates latitude value
   - West (W): Negates longitude value
   - North (N): Keeps latitude positive
   - East (E): Keeps longitude positive
   
   This ensures coordinates are in the standard decimal format where:
   - Negative latitude = Southern hemisphere
   - Negative longitude = Western hemisphere

### Coordinate Parsing
The coordinate parsing handles both string and numeric formats:

**For string coordinates** (e.g., "37 deg 46' 29.99\""):
- Parses degrees, minutes, seconds format
- Converts to decimal degrees
- Applies hemisphere reference

**For numeric coordinates** (e.g., 37.7749):
- Uses value directly
- **Still applies hemisphere reference** (critical for accuracy)
- Negates if South or West

This dual handling ensures coordinates are correct regardless of how exiftool returns them.

### URL Generation
- OpenStreetMap: Uses `mlat`/`mlon` parameters with zoom
- Google Maps: Uses simple `q` parameter with lat,lon
- Coordinates formatted to 6 decimal places for precision

## Use Cases

### Photo Location Verification
Check where a photo was taken:
1. Select the photo
2. Click "Show Location"
3. Verify the location on the map

### Travel Photo Organization
Organize photos by location:
1. Browse through photos
2. Check locations using Show Location
3. Group photos by geographic area

### Geotagging Validation
Verify GPS data accuracy:
1. Select a photo you know the location of
2. Click Show Location
3. Confirm the map shows the correct location

### Location-Based Searching
Find photos from specific locations:
1. Use EXIF filter "GPS/Location"
2. Check GPS coordinates in info panel
3. Use Show Location to visualize on map

## Troubleshooting

### Button Always Disabled

**Problem**: Show Location button is always grayed out

**Possible Causes**:
1. Selected files don't have GPS data
2. exiftool not installed
3. GPS data in non-standard format

**Solutions**:
1. Check if file has GPS data:
   ```bash
   exiftool -GPS:all photo.jpg
   ```

2. Install exiftool if missing

3. Try different EXIF filter to see raw GPS data

### Browser Doesn't Open

**Problem**: Dialog appears but browser doesn't open

**Possible Causes**:
1. No default browser set
2. Browser not in system PATH
3. Permission issues

**Solutions**:
1. Set default browser in system settings
2. Manually copy URL from error dialog
3. Check system permissions

### Wrong Location Shown

**Problem**: Map shows incorrect location

**Possible Causes**:
1. GPS data is incorrect in the file
2. Coordinate parsing error
3. Reference (N/S/E/W) applied incorrectly

**Solutions**:
1. Check raw GPS data using exiftool
2. Verify coordinates manually
3. Report issue with coordinate format

### "No GPS Data" for Photos with Location

**Problem**: You know the photo has location but button says no GPS

**Possible Causes**:
1. Location stored in non-standard tags
2. GPS data in proprietary format
3. exiftool can't read the format

**Solutions**:
1. Check all EXIF data with filter "All"
2. Look for location in other tags
3. Try re-geotagging the photo

## Privacy Considerations

### GPS Data Exposure
- GPS coordinates reveal exact photo locations
- Be cautious when sharing photos with GPS data
- Consider removing GPS data before sharing

### Removing GPS Data
To remove GPS data from photos:
```bash
exiftool -gps:all= photo.jpg
```

Or use the Apply EXIF feature to selectively update metadata.

## Future Enhancements

Potential improvements:
- Show multiple photos on a single map
- Display photo thumbnail on map marker
- Export GPS data to GPX/KML format
- Batch location viewer for selected files
- Offline map support
- Custom map service selection
- Location-based photo filtering

## Integration with Other Features

### EXIF Filter
- Use "GPS/Location" filter to see all GPS data
- Shows raw coordinates and location tags
- Complements Show Location visualization

### Apply EXIF
- Can add/update GPS coordinates
- Can add location names (City, State, Country)
- Works together with Show Location for verification

### Database
- GPS data is indexed in database
- Can query photos by location
- Enables location-based searches

## Examples

### Example 1: Vacation Photo
```
File: IMG_1234.JPG
GPS Coordinates:
Latitude: 48.858844
Longitude: 2.294351
Location: Paris, Île-de-France, France

Opens map showing the Eiffel Tower area
```

### Example 2: Hiking Photo
```
File: mountain.jpg
GPS Coordinates:
Latitude: 46.520833
Longitude: 8.055833

Opens map showing Swiss Alps location
```

### Example 3: Southern Hemisphere
```
File: sydney.jpg
GPS Coordinates:
Latitude: -33.865143
Longitude: 151.209900
Location: Sydney, New South Wales, Australia

Opens map showing Sydney Opera House area
(Note: Negative latitude indicates Southern hemisphere)
```

### Example 4: Western Hemisphere
```
File: newyork.jpg
GPS Coordinates:
Latitude: 40.748817
Longitude: -73.985428
Location: New York, New York, USA

Opens map showing Empire State Building area
(Note: Negative longitude indicates Western hemisphere)
```

### Example 5: No GPS
```
File: scan_001.jpg
No GPS coordinates found in:
scan_001.jpg

(Scanned photos typically don't have GPS data)
```

## Tips

1. **Check GPS Before Sharing**: Use Show Location to verify what location data your photos contain before sharing them online

2. **Organize by Location**: Use Show Location while browsing to mentally organize photos by geographic regions

3. **Verify Geotagging**: After adding GPS data with Apply EXIF, use Show Location to verify accuracy

4. **Travel Documentation**: Create a visual travel log by checking locations of photos from a trip

5. **Location Scouting**: Find interesting photo locations by checking GPS data from others' photos (with permission)
