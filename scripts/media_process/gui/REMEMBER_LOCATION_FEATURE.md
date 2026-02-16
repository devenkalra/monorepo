# Remember Location Feature

## Overview
The Remember Location feature allows you to save GPS coordinates and location information from one photo and reuse it when applying EXIF data to other photos. This is useful when you have multiple photos from the same location but only some have GPS data.

## How It Works

### 1. Remember Location from a Photo
When viewing a photo with GPS data:
1. Select a file with GPS coordinates
2. Click the **"Remember Location"** button (next to "Show Location")
3. The application stores all location data:
   - GPS coordinates (latitude, longitude, altitude)
   - Location details (city, state, country, country code, coverage)

### 2. Apply Remembered Location to Other Photos
When applying EXIF data:
1. Select one or more files
2. Click **"Apply EXIF"**
3. The dialog opens with remembered location data pre-populated
4. Modify values if needed or click **"Clear GPS"** to start fresh
5. Click **"Start"** to apply the location data

## Features

### Remember Location Button
- **Location**: Next to "Show Location" button in the file information panel
- **Enabled when**: Single file selected with GPS data
- **Action**: Stores complete location data in memory

### Location Data Stored
The feature remembers:
- **Latitude**: Decimal degrees (e.g., 37.774929)
- **Longitude**: Decimal degrees (e.g., -122.419416)
- **Altitude**: Meters above sea level
- **City**: City name
- **State**: State/province name
- **Country**: Country name
- **Country Code**: ISO country code
- **Coverage**: Geographic coverage area

### Apply EXIF Dialog Integration
The Apply EXIF dialog now includes:

#### GPS Coordinates Section
- Latitude field (pre-populated from remembered location)
- Longitude field (pre-populated from remembered location)
- Altitude field (pre-populated from remembered location)
- **Clear GPS button**: Clears all GPS and location fields

#### Location Details Section
- City field
- State field
- Country field
- Country Code field
- Coverage field

All fields are pre-populated with remembered location data if available.

#### Dialog Buttons
- **Start**: Apply EXIF data to selected files
- **Remember**: Save current field values as remembered location
- **Close**: Close the dialog

The **Remember** button allows you to update the remembered location from within the Apply EXIF dialog, useful when you've manually entered or modified location data.

## Use Cases

### Case 1: Group Photos at Same Location
**Scenario**: You took 20 photos at a landmark, but only one has GPS data.

**Steps**:
1. Select the photo with GPS data
2. Click "Remember Location"
3. Select all 19 other photos
4. Click "Apply EXIF"
5. GPS fields are pre-filled
6. Click "Start" to apply to all photos

### Case 2: Indoor Photos
**Scenario**: Indoor photos don't have GPS, but you know the location.

**Steps**:
1. Find any outdoor photo from the same location with GPS
2. Click "Remember Location"
3. Select indoor photos
4. Click "Apply EXIF"
5. Location is pre-filled
6. Apply to indoor photos

### Case 3: Scanned Photos
**Scenario**: Old scanned photos need location data added.

**Steps**:
1. Find a recent photo from the same location
2. Click "Remember Location"
3. Select scanned photos
4. Click "Apply EXIF"
5. Modify location details if needed (old vs new city names)
6. Apply location data

### Case 4: Manual Location Entry
**Scenario**: You want to add GPS data manually.

**Steps**:
1. Select photos
2. Click "Apply EXIF"
3. Click "Clear GPS" to clear any remembered data
4. Enter GPS coordinates manually
5. Enter location details
6. Click "Remember" to save for future use
7. Apply to photos

### Case 5: Modify and Remember
**Scenario**: Remembered location needs slight adjustment.

**Steps**:
1. Open "Apply EXIF" dialog
2. Fields are pre-populated with remembered location
3. Modify city name or adjust coordinates
4. Click "Remember" to update remembered location
5. Click "Start" to apply to current files
6. Next time you open Apply EXIF, modified values are used

## Workflow Examples

### Example 1: Tourist Photos
```
1. At Eiffel Tower, take photo → GPS recorded
2. Select that photo, click "Remember Location"
3. Take 50 more photos nearby
4. Select all photos without GPS
5. Click "Apply EXIF" → GPS pre-filled
6. Click "Start" to apply
7. All photos now have correct location
```

### Example 1b: Manual Entry and Remember
```
1. Select photos needing location
2. Click "Apply EXIF"
3. Click "Clear GPS"
4. Manually enter coordinates: 48.858844, 2.294351
5. Enter city: Paris, country: France
6. Click "Remember" to save for future use
7. Click "Start" to apply to current photos
8. Next batch automatically has Paris location
```

### Example 2: Event Photography
```
1. Arrive at venue, take test shot with GPS
2. Remember Location
3. Shoot event (200 photos, some without GPS)
4. After event, select photos missing GPS
5. Apply EXIF → venue location pre-filled
6. All event photos tagged with venue location
```

### Example 3: Historical Photos
```
1. Visit historical location today
2. Take reference photo with GPS
3. Remember Location
4. Select old photos from that location
5. Apply EXIF → GPS coordinates pre-filled
6. Adjust date/time, keep location
7. Historical photos now have accurate location
```

## Clear GPS Button

### Purpose
Allows you to clear all GPS and location fields to:
- Start with a clean slate
- Remove remembered location data
- Enter completely new location information

### What It Clears
- Latitude
- Longitude
- Altitude
- City
- State
- Country
- Country Code
- Coverage

### When to Use
- You want to enter location manually
- Remembered location is not relevant
- You want to remove GPS data from photos
- Testing different locations

## Data Persistence

### Session Memory
- Location data is remembered for the current session
- Survives dialog opens/closes
- Lost when application closes

### Not Saved to Config
- Remembered location is NOT saved to configuration file
- Intentionally session-only for privacy
- Must remember location each session

## Privacy Considerations

### Why Session-Only?
Location data can be sensitive:
- Reveals home/work locations
- Shows travel patterns
- May contain personal information

By keeping it session-only:
- No persistent storage of locations
- User must explicitly remember each session
- Reduces privacy risks

### Clearing Data
To clear remembered location:
1. Close and restart the application, OR
2. Remember a different location (overwrites previous)

## Technical Details

### Data Structure
```python
remembered_location = {
    'latitude': float,      # Decimal degrees
    'longitude': float,     # Decimal degrees
    'altitude': float,      # Meters
    'city': str,           # City name
    'state': str,          # State/province
    'country': str,        # Country name
    'country_code': str,   # ISO code
    'coverage': str        # Coverage area
}
```

### Extraction Method
Uses `get_full_location_data()` which:
1. Calls exiftool with GPS and location tags
2. Parses JSON output
3. Applies hemisphere references (S/W = negative)
4. Extracts altitude if available
5. Collects all location metadata

### Pre-population
When Apply EXIF dialog opens:
- Checks if remembered_location exists
- Pre-fills all fields with remembered values
- Empty fields if no remembered data
- User can modify any field

## Button States

### Remember Location Button

**Enabled** when:
- Single file selected
- File has GPS coordinates
- GPS data successfully extracted

**Disabled** when:
- No file selected
- Multiple files selected
- File has no GPS data
- GPS extraction fails

## Integration with Other Features

### Show Location
- Both buttons work with same GPS data
- Remember Location stores more data than Show Location displays
- Can use Show Location to verify before remembering

### Apply EXIF
- Remembered data pre-populates Apply EXIF dialog
- Can be modified before applying
- Can be cleared with Clear GPS button

### Database
- Applied location data is stored in database
- Can query photos by location later
- Enables location-based searches

## Limitations

### Session-Only Storage
- Not saved between sessions
- Must remember location each time you start app
- Intentional for privacy

### Single Location
- Can only remember one location at a time
- Remembering new location overwrites previous
- No location history or favorites

### No Validation
- Does not validate GPS coordinates
- Does not check if location names match coordinates
- User responsible for accuracy

## Future Enhancements

Potential improvements:
- Save favorite locations to config (opt-in)
- Location history (last 5-10 locations)
- Location presets/templates
- Reverse geocoding (coordinates → location names)
- Location name validation
- Map preview in Apply EXIF dialog
- Batch remember from multiple photos

## Tips

1. **Verify First**: Use "Show Location" to verify GPS data before remembering

2. **One Good Photo**: You only need one photo with good GPS data to tag many others

3. **Outdoor Reference**: Take an outdoor photo first to get GPS for indoor photos

4. **Check Accuracy**: After applying, use "Show Location" on result to verify

5. **Clear When Needed**: Use "Clear GPS" when switching to a different location

6. **Manual Entry**: You can manually enter GPS coordinates if you know them

7. **Altitude Optional**: Altitude is optional, leave blank if unknown

8. **Location Details**: City/State/Country help organize photos, even without GPS

## Troubleshooting

### Button Not Enabled
**Problem**: Remember Location button is grayed out

**Solutions**:
- Ensure single file is selected
- Check file has GPS data (use EXIF filter "GPS/Location")
- Verify exiftool is installed

### Fields Not Pre-populated
**Problem**: Apply EXIF dialog shows empty fields

**Solutions**:
- Check if you remembered location this session
- Remember location again
- Verify source photo had complete data

### Wrong Location Remembered
**Problem**: Applied wrong location to photos

**Solutions**:
- Remember correct location
- Use "Clear GPS" in Apply EXIF
- Re-apply with correct data

### Can't Clear Location
**Problem**: Want to forget remembered location

**Solutions**:
- Click "Clear GPS" in Apply EXIF dialog
- Remember a different location (overwrites)
- Restart application (clears memory)

## Examples

### Example Output: Remember Location
```
Location data remembered:

GPS: 48.858844, 2.294351
Altitude: 35.0 m
Location: Paris, Île-de-France, France
Country Code: FR
```

### Example: Apply EXIF Dialog
```
GPS Coordinates:
  Latitude: 48.858844
  Longitude: 2.294351
  Altitude (m): 35.0
  
Location Details:
  City: Paris
  State: Île-de-France
  Country: France
  Country Code: FR
  Coverage: 
```

### Example: After Clear GPS
```
GPS Coordinates:
  Latitude: [empty]
  Longitude: [empty]
  Altitude (m): [empty]
  
Location Details:
  City: [empty]
  State: [empty]
  Country: [empty]
  Country Code: [empty]
  Coverage: [empty]
```
