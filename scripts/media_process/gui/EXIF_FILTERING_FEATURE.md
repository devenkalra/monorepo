# EXIF Filtering Feature

## Overview

Added EXIF data filtering to show specific subsets of metadata, similar to the show_exif.py script functionality.

## Feature Description

**Location:** File Information panel (right side), top control bar

**Purpose:** Filter EXIF display to show only relevant metadata categories

**Usage:** Select filter from dropdown to update EXIF display

## Filter Modes

### 1. All (Default)
Shows all EXIF data from the file, excluding only:
- SourceFile
- ExifTool version info
- Most File-related fields (except FileName, FileSize, FileType, MIMEType)

**Use Cases:**
- Complete metadata inspection
- Finding specific tags
- Debugging

### 2. Common
Shows frequently used EXIF tags:
- **File Info:** FileName, FileSize, FileType, MIMEType
- **Image:** ImageWidth, ImageHeight, Orientation
- **Camera:** Make, Model
- **Dates:** DateTimeOriginal, CreateDate, ModifyDate
- **Settings:** ISO, FNumber, ExposureTime, FocalLength
- **Lens:** LensModel

**Use Cases:**
- Quick overview
- Most relevant information
- Standard photo details

### 3. GPS/Location
Shows location-related tags:
- **GPS:** All GPS tags (latitude, longitude, altitude, etc.)
- **Location:** City, State, Country
- **XMP Location:** LocationShown fields
- **Coverage:** XMP-dc:Coverage (place name)

**Use Cases:**
- Verify location data
- Check GPS coordinates
- Review geocoded information

### 4. Camera
Shows camera settings and technical details:
- **Camera:** Make, Model
- **Lens:** LensModel, LensInfo
- **Exposure:** ISO, FNumber, ExposureTime
- **Focal Length:** FocalLength, FocalLengthIn35mmFormat
- **Settings:** WhiteBalance, Flash, ExposureProgram
- **Metering:** MeteringMode, ExposureCompensation

**Use Cases:**
- Review camera settings
- Compare shooting parameters
- Technical analysis

### 5. Keywords
Shows keywords, captions, and descriptive metadata:
- **Keywords:** Keywords, Subject, XMP-dc:Subject
- **IPTC:** IPTC:Keywords
- **Captions:** Caption-Abstract, ImageDescription
- **Descriptions:** XMP-dc:Description, XMP-dc:Title

**Use Cases:**
- Review tags and keywords
- Check captions
- Manage metadata

### 6. Video
Shows video-specific metadata:
- **Dimensions:** ImageWidth, ImageHeight
- **Timing:** Duration, VideoFrameRate
- **Video:** VideoCodec, CompressorName
- **Audio:** AudioChannels, AudioBitrate, AudioCodec
- **Color:** BitDepth, ColorSpace

**Use Cases:**
- Video file analysis
- Codec information
- Technical specs

## User Interface

### Control Location
```
File Information Panel
┌─────────────────────────────────────┐
│ EXIF Display: [Common ▼]            │
├─────────────────────────────────────┤
│ File: photo.jpg                     │
│ Path: /path/to/photo.jpg            │
│ ...                                 │
│                                     │
│ --- Common EXIF Data ---            │
│ Make: Canon                         │
│ Model: EOS 5D Mark IV               │
│ ...                                 │
└─────────────────────────────────────┘
```

### Dropdown Options
```
EXIF Display: [dropdown]
  - All
  - Common          ← Default
  - GPS/Location
  - Camera
  - Keywords
  - Video
```

### Section Headers
Headers change based on filter mode:
- **All:** "--- EXIF Data ---"
- **Common:** "--- EXIF Data ---"
- **GPS/Location:** "--- GPS/Location Data ---"
- **Camera:** "--- Camera Settings ---"
- **Keywords:** "--- Keywords & Captions ---"
- **Video:** "--- Video Metadata ---"

### Empty Results
If no data for selected filter:
```
--- GPS/Location Data ---
No gps/location data found
```

## Implementation

### Methods

**get_exif_data(file_path, filter_mode="All")**
- Builds exiftool command based on filter mode
- Requests specific tags for each mode
- Returns filtered dictionary

**on_exif_filter_change()**
- Triggered when dropdown selection changes
- Refreshes file info with new filter
- Only affects single file display

### ExifTool Commands

**Common:**
```bash
exiftool -json -FileName -FileSize -FileType -ImageWidth ... file.jpg
```

**GPS/Location:**
```bash
exiftool -json -a -GPS:all -XMP-photoshop:City ... file.jpg
```

**Camera:**
```bash
exiftool -json -Make -Model -ISO -FNumber ... file.jpg
```

**Keywords:**
```bash
exiftool -json -a -Keywords -Subject -Caption-Abstract ... file.jpg
```

**Video:**
```bash
exiftool -json -ImageWidth -Duration -VideoCodec ... file.mp4
```

**All:**
```bash
exiftool -json -a file.jpg
```

## Configuration

EXIF filter preference is saved in config:

```yaml
exif_filter: Common
```

Automatically loaded on startup.

## Use Cases

### 1. Quick Photo Review (Common)
- Select "Common" filter
- See essential info immediately
- Fast scanning of multiple photos

### 2. Verify GPS Data (GPS/Location)
- Select "GPS/Location" filter
- Check coordinates
- Verify location metadata
- Useful before/after geocoding

### 3. Compare Camera Settings (Camera)
- Select "Camera" filter
- Review shooting parameters
- Compare settings between shots
- Technical analysis

### 4. Manage Keywords (Keywords)
- Select "Keywords" filter
- Review existing tags
- Check captions
- Plan metadata updates

### 5. Video Analysis (Video)
- Select "Video" filter
- Check codec info
- Verify audio settings
- Technical specs review

### 6. Complete Inspection (All)
- Select "All" filter
- Search for specific tags
- Complete metadata review
- Debugging issues

## Performance

- **Filter Change:** Instant (just dropdown selection)
- **Data Load:** 0.5-2s (exiftool execution)
- **Same as Before:** No performance penalty
- **Benefit:** Less data to display = easier to read

## Benefits

1. **Focused Display:** Only relevant data shown
2. **Faster Scanning:** Less clutter, easier to read
3. **Workflow Specific:** Choose mode for task
4. **Saved Preference:** Remember favorite filter
5. **Real-time Update:** Change filter anytime
6. **Compatible:** Works with all file formats

## Comparison with show_exif.py

Implements similar filtering as show_exif.py:
- ✅ Common tags
- ✅ GPS/Location tags
- ✅ Camera settings
- ✅ Keywords/captions
- ✅ Video metadata
- ✅ All tags mode
- ❌ JSON output (not needed in GUI)
- ❌ Grouped output (GUI handles layout)
- ❌ Thumbnail extraction (separate feature)

## Examples

### Example 1: Photo with GPS
**Filter: GPS/Location**
```
--- GPS/Location Data ---
GPSLatitude: 40.7128
GPSLongitude: -74.0060
GPSAltitude: 10.5
City: New York
State: New York
Country: USA
```

### Example 2: Photo Settings
**Filter: Camera**
```
--- Camera Settings ---
Make: Canon
Model: EOS 5D Mark IV
LensModel: EF 24-70mm f/2.8L
ISO: 400
FNumber: 2.8
ExposureTime: 1/500
FocalLength: 50mm
```

### Example 3: Video File
**Filter: Video**
```
--- Video Metadata ---
ImageWidth: 1920
ImageHeight: 1080
Duration: 120.5s
VideoFrameRate: 30
VideoCodec: H.264
AudioChannels: 2
AudioBitrate: 192 kbps
```

### Example 4: Keywords
**Filter: Keywords**
```
--- Keywords & Captions ---
Subject: vacation, beach, sunset
Keywords: vacation, beach, sunset
Caption-Abstract: Beautiful sunset at the beach
```

## Testing Checklist

- [x] Dropdown displays all options
- [x] Selection changes filter
- [x] "All" shows all tags
- [x] "Common" shows basic tags
- [x] "GPS/Location" shows GPS data
- [x] "Camera" shows camera settings
- [x] "Keywords" shows keywords/captions
- [x] "Video" shows video metadata
- [x] Empty data shows message
- [x] Section headers update
- [x] Config saves preference
- [x] Config loads on startup
- [x] Works with all file types
- [x] Real-time updates

## Future Enhancements

Potential additions:
- Custom filter presets
- Tag search/highlighting
- Export filtered data
- Batch metadata comparison
- Side-by-side comparison mode
