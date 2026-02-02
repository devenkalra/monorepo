# show_exif.py - Display EXIF/Metadata Information

## Overview

`show_exif.py` is a Python script that displays EXIF and metadata information from image and video files using `exiftool`. It provides various display modes to show different types of metadata in different formats.

## Requirements

- Python 3.6+
- `exiftool` (libimage-exiftool-perl)

Install exiftool:
```bash
# Ubuntu/Debian
sudo apt-get install libimage-exiftool-perl

# macOS
brew install exiftool
```

## Basic Usage

```bash
python3 show_exif.py --file <file> [options]
```

**Note:** You can specify `--mode` multiple times to display different types of information in one execution:

```bash
python3 show_exif.py --file photo.jpg --mode common --mode gps --mode keywords
```

## Display Modes

### 1. Common Tags (default)
Shows commonly used EXIF tags including file info, dimensions, camera, dates, and exposure settings.

```bash
python3 show_exif.py --file photo.jpg --mode common
```

**Output includes:**
- FileName, FileSize, FileType, MIMEType
- ImageWidth, ImageHeight
- Make, Model, LensModel
- DateTimeOriginal, CreateDate, ModifyDate
- ISO, FNumber, ExposureTime, FocalLength
- Orientation

### 2. GPS and Location Tags
Shows GPS coordinates and location information.

```bash
python3 show_exif.py --file photo.jpg --mode gps
```

**Output includes:**
- GPS:all (latitude, longitude, altitude)
- XMP-photoshop:City, State, Country
- XMP-iptcExt:LocationShown*
- XMP-dc:Coverage

### 3. All Tags
Shows all available EXIF tags.

```bash
# Show all tags
python3 show_exif.py --file photo.jpg --mode all

# Show all tags grouped by category
python3 show_exif.py --file photo.jpg --mode all --grouped
```

With `--grouped`, tags are prefixed with their category:
- `EXIF:Make`
- `XMP-dc:Subject`
- `IPTC:Keywords`

### 4. Specific Tags
Shows only the tags you specify.

```bash
python3 show_exif.py --file photo.jpg --mode specific --tags Make Model ISO FocalLength
```

You can also use tag groups:
```bash
python3 show_exif.py --file photo.jpg --mode specific --tags GPS:all
```

### 5. JSON Output
Outputs all metadata in JSON format for parsing or further processing.

```bash
python3 show_exif.py --file photo.jpg --mode json

# With grouping
python3 show_exif.py --file photo.jpg --mode json --grouped
```

### 6. Keywords and Captions
Shows keywords, subjects, and descriptive text.

```bash
python3 show_exif.py --file photo.jpg --mode keywords
```

**Output includes:**
- Keywords, Subject
- XMP-dc:Subject
- IPTC:Keywords
- Caption-Abstract, ImageDescription
- XMP-dc:Description, XMP-dc:Title

### 7. Camera Settings
Shows detailed camera settings.

```bash
python3 show_exif.py --file photo.jpg --mode camera
```

**Output includes:**
- Make, Model, LensModel, LensInfo
- ISO, FNumber, ExposureTime, FocalLength
- FocalLengthIn35mmFormat
- WhiteBalance, Flash
- ExposureProgram, MeteringMode, ExposureCompensation

### 8. Video Metadata
Shows video-specific metadata.

```bash
python3 show_exif.py --file video.mp4 --mode video
```

**Output includes:**
- ImageWidth, ImageHeight, Duration
- VideoFrameRate, VideoCodec
- AudioChannels, AudioBitrate, AudioCodec
- CompressorName, BitDepth, ColorSpace

### 9. Thumbnail Information
Shows information about embedded thumbnails.

```bash
python3 show_exif.py --file photo.jpg --mode thumbnail
```

This displays:
- Whether a thumbnail is embedded
- Thumbnail dimensions
- Thumbnail file size

### 10. Extract Thumbnails
Extract and save embedded thumbnails to files.

```bash
# Extract to temporary directory
python3 show_exif.py --file photo.jpg --extract-thumbnails

# Extract to specific directory
python3 show_exif.py --file *.jpg --extract-thumbnails --thumbnail-dir ./thumbnails

# Combine with metadata display
python3 show_exif.py --file photo.jpg --mode common --extract-thumbnails
```

This will:
- Extract thumbnails from all specified files
- Save them with prefix `thumb_` + original filename
- Display extraction status for each file
- Show thumbnail dimensions
- Attempt to open the output directory in file manager

## Options

### Multiple Files
Specify multiple files using repeated `--file` arguments:

```bash
python3 show_exif.py --file photo1.jpg --file photo2.jpg --file video.mp4 --mode common
```

### Hide Filenames
Show only values without tag names or filenames:

```bash
python3 show_exif.py --file photo.jpg --mode common --no-filenames
```

### Grouped Output
Group tags by their category (EXIF, XMP, IPTC, etc.):

```bash
python3 show_exif.py --file photo.jpg --mode all --grouped
```

## Examples

### Example 1: Quick check of photo details
```bash
python3 show_exif.py --file IMG_1234.jpg --mode common
```

Output:
```
======== IMG_1234.jpg
FileName                        : IMG_1234.jpg
FileSize                        : 3.2 MB
FileType                        : JPEG
MIMEType                        : image/jpeg
ImageWidth                      : 4032
ImageHeight                     : 3024
Make                            : Apple
Model                           : iPhone 12 Pro
DateTimeOriginal                : 2024:08:15 14:30:22
ISO                             : 100
FNumber                         : 1.8
ExposureTime                    : 1/120
FocalLength                     : 4.2 mm
LensModel                       : iPhone 12 Pro back dual wide camera 4.2mm f/1.6
```

### Example 2: Check GPS location
```bash
python3 show_exif.py --file vacation_photo.jpg --mode gps
```

Output:
```
======== vacation_photo.jpg
GPSLatitude                     : 25.7617 N
GPSLongitude                    : 80.1918 W
GPSAltitude                     : 5 m
City                            : Miami
State                           : Florida
Country                         : USA
Coverage                        : Miami Beach, Florida
```

### Example 3: Export all metadata as JSON
```bash
python3 show_exif.py --file photo.jpg --mode json > metadata.json
```

### Example 4: Check specific tags for multiple photos
```bash
python3 show_exif.py --file *.jpg --mode specific --tags Make Model ISO ExposureTime
```

### Example 5: Compare video metadata
```bash
python3 show_exif.py --file video1.mp4 --file video2.mov --mode video
```

### Example 6: Show all tags with category grouping
```bash
python3 show_exif.py --file photo.jpg --mode all --grouped
```

Output:
```
======== photo.jpg
[EXIF]          Make                            : Canon
[EXIF]          Model                           : Canon EOS 5D Mark IV
[XMP]           Subject                         : vacation, beach, sunset
[XMP-dc]        Description                     : Beautiful sunset at the beach
[IPTC]          Keywords                        : vacation, beach, sunset
[GPS]           GPSLatitude                     : 25.7617 N
```

### Example 8: Show multiple modes at once
```bash
python3 show_exif.py --file photo.jpg --mode common --mode gps --mode keywords
```

This will display common tags, GPS information, and keywords all in one output, separated by dividers.

### Example 9: Show and extract thumbnails
```bash
# Just show thumbnail info
python3 show_exif.py --file photo.jpg --mode thumbnail

# Extract thumbnails to temp directory
python3 show_exif.py --file *.jpg --extract-thumbnails

# Extract thumbnails to specific directory
python3 show_exif.py --file photo1.jpg --file photo2.jpg --extract-thumbnails --thumbnail-dir ~/extracted_thumbs
```

### Example 10: Show metadata and extract thumbnails
```bash
python3 show_exif.py --file vacation_photo.jpg --mode common --mode gps --extract-thumbnails --thumbnail-dir ./thumbs
```

This will show common EXIF tags, GPS information, AND extract the thumbnail to the `./thumbs` directory.

### Example 7: Extract only values (for scripting)
```bash
# Get ISO value
python3 show_exif.py --file photo.jpg --mode specific --tags ISO --no-filenames

# Get dimensions
python3 show_exif.py --file photo.jpg --mode specific --tags ImageWidth ImageHeight --no-filenames
```

## Integration with command_runner.py

Use the provided `show_exif.yaml` configuration file:

```bash
python3 command_runner.py show_exif.yaml
```

This provides a GUI interface with:
- File selection (supports multiple files)
- Display mode dropdown
- Group by category checkbox
- Specific tags input
- Hide filenames option
- Command preview
- Execute button with output display

## Supported File Types

### Images
- JPEG (.jpg, .jpeg)
- PNG (.png)
- TIFF (.tif, .tiff)
- RAW formats: CR2, CR3, NEF, ARW, RW2, ORF, DNG, RAF, etc.
- HEIC (.heic, .heif)
- GIF (.gif)
- BMP (.bmp)

### Videos
- MP4 (.mp4)
- MOV (.mov)
- AVI (.avi)
- MKV (.mkv)
- MPG (.mpg, .mpeg)
- WMV (.wmv)
- FLV (.flv)

## Tips

1. **Finding tag names**: Use `--mode all --grouped` to see all available tags and their group names.

2. **Batch processing**: Use shell wildcards or multiple `--file` arguments to process many files at once.

3. **Scripting**: Use `--no-filenames` and `--mode specific` to extract specific values for scripts.

4. **JSON export**: Use `--mode json` to export metadata for further processing with tools like `jq`.

5. **Location verification**: Use `--mode gps` to verify location tags before or after running `apply_exif.py`.

6. **Camera comparison**: Use `--mode camera` to compare settings across multiple photos.

## Common Tag Names

Here are some commonly used tag names for `--mode specific`:

**File Info:**
- FileName, FileSize, FileType, MIMEType

**Dimensions:**
- ImageWidth, ImageHeight, Orientation

**Camera:**
- Make, Model, LensModel, LensInfo, SerialNumber

**Exposure:**
- ISO, FNumber, ExposureTime, FocalLength, FocalLengthIn35mmFormat
- WhiteBalance, Flash, ExposureProgram, MeteringMode

**Dates:**
- DateTimeOriginal, CreateDate, ModifyDate, FileModifyDate

**GPS:**
- GPSLatitude, GPSLongitude, GPSAltitude
- GPSLatitudeRef, GPSLongitudeRef

**Location:**
- XMP-photoshop:City, XMP-photoshop:State, XMP-photoshop:Country
- XMP-dc:Coverage

**Keywords:**
- Keywords, Subject, XMP-dc:Subject, IPTC:Keywords

**Description:**
- ImageDescription, Caption-Abstract, XMP-dc:Description, XMP-dc:Title

**Video:**
- Duration, VideoFrameRate, VideoCodec, AudioChannels, AudioBitrate

## Troubleshooting

**"exiftool not found"**
- Install exiftool: `sudo apt-get install libimage-exiftool-perl`

**"File not found"**
- Check the file path is correct
- Use absolute paths if relative paths don't work

**No output for certain tags**
- The file may not have those tags
- Use `--mode all` to see what tags are available
- Try `--grouped` to see tag group names

**Unexpected output format**
- Use `--no-filenames` for cleaner output
- Use `--mode json` for structured data

## See Also

- `apply_exif.py` - Apply EXIF tags to files
- `locate_in_db.py` - Find files in database and show metadata
- `index_media.py` - Index media files with metadata extraction
- `command_runner.py` - GUI for running scripts
