# HEIF/HEIC and RAW Format Support

This document explains support for HEIF/HEIC and RAW camera formats in the Media Processor GUI.

## Overview

The Media Processor GUI supports viewing and processing:
- **HEIF/HEIC** formats (Apple's High Efficiency Image Format)
- **RAW camera formats** from all major camera manufacturers

## Supported Formats

### HEIF/HEIC Formats
- `.heic` - High Efficiency Image Container (Apple)
- `.heif` - High Efficiency Image Format
- `.avif` - AV1 Image File Format

### RAW Camera Formats

| Brand | Extensions |
|-------|-----------|
| Canon | `.cr2`, `.cr3` |
| Nikon | `.nef`, `.nrw` |
| Sony | `.arw`, `.srf`, `.sr2` |
| Adobe/Generic | `.dng` |
| Olympus | `.orf` |
| Panasonic | `.rw2` |
| Pentax | `.pef` |
| Fujifilm | `.raf` |
| Hasselblad | `.3fr` |
| Kodak | `.dcr`, `.k25`, `.kdc` |
| Mamiya | `.mef` |
| Leaf | `.mos` |
| Minolta | `.mrw` |
| RED | `.r3d` |
| Leica | `.rwl` |
| Samsung | `.srw` |
| Sigma | `.x3f` |

## Installation Methods

The application supports multiple methods for loading HEIF/HEIC and RAW files. You can install one or more methods - the application will try them in order until one succeeds.

### Method 1: Python Libraries (Recommended)

**Advantages:**
- Fast loading
- Pure Python (no system dependencies)
- Best integration with the GUI

**For HEIF/HEIC:**
```bash
pip3 install pillow-heif
```

**For RAW:**
```bash
pip3 install rawpy numpy
```

**Compatibility:**
- `pillow-heif`: Works on Linux, macOS, Windows
- `rawpy`: Works on Linux, macOS, Windows (requires libraw)

### Method 2: ImageMagick (Alternative)

**Advantages:**
- Supports both HEIF and RAW
- System-level tool
- Works for many formats

**Installation:**

Ubuntu/Debian:
```bash
sudo apt-get install imagemagick libraw-dev
```

macOS:
```bash
brew install imagemagick
```

**Note:** ImageMagick may need additional configuration for HEIC files. Edit `/etc/ImageMagick-6/policy.xml` (or similar) to enable HEIC support.

### Method 3: dcraw (RAW only)

**Advantages:**
- Lightweight
- Fast for RAW processing
- No complex dependencies

**Installation:**

Ubuntu/Debian:
```bash
sudo apt-get install dcraw
```

macOS:
```bash
brew install dcraw
```

**Limitations:**
- RAW formats only (no HEIF/HEIC)
- Command-line tool only

## How It Works

When you select a HEIF/HEIC or RAW file, the application tries to load it using this priority:

### For HEIF/HEIC Files:
1. **pillow-heif** (if installed)
2. **ImageMagick convert** (if installed)
3. If all fail, shows "Preview unavailable" message

### For RAW Files:
1. **rawpy** (if installed)
2. **ImageMagick convert** (if installed)
3. **dcraw** (if installed)
4. If all fail, shows "Preview unavailable" message

The first successful method is used. This ensures:
- Fast loading when Python libraries are available
- Fallback to system tools if needed
- Maximum compatibility

## Features Available

### With Preview Support
When at least one method is installed:
- ✅ File browsing and listing
- ✅ Preview thumbnails
- ✅ EXIF data viewing
- ✅ All bulk operations
- ✅ Database indexing
- ✅ Duplicate detection
- ✅ EXIF tag application

### Without Preview Support
If no methods are installed:
- ✅ File browsing and listing
- ❌ Preview thumbnails (shows "Preview unavailable")
- ✅ EXIF data viewing (via exiftool)
- ✅ All bulk operations
- ✅ Database indexing
- ✅ Duplicate detection
- ✅ EXIF tag application

**Note:** Preview is the only feature that requires special libraries. All other features work through exiftool and the parent scripts.

## Testing Your Installation

Run the prerequisite checker to see what's installed:

```bash
cd /home/ubuntu/monorepo/scripts/media_process/gui
python3 check_prerequisites.py
```

This will show:
- ✓ Installed methods
- ⚠ Missing optional methods
- Installation commands for missing methods

## Performance Notes

### HEIF/HEIC Performance
- **pillow-heif**: Fast (~0.5-1 second per image)
- **ImageMagick**: Medium (~1-2 seconds per image)

### RAW Performance
- **rawpy**: Fast (~1-2 seconds per image)
- **ImageMagick**: Medium (~2-4 seconds per image)
- **dcraw**: Fast (~1-2 seconds per image)

**Note:** Initial load of RAW files is slower than JPEG. The GUI shows a "Loading..." message during processing.

## Troubleshooting

### HEIF/HEIC Issues

**Problem:** "Preview unavailable" for HEIC files

**Solutions:**
1. Install pillow-heif:
   ```bash
   pip3 install pillow-heif
   ```

2. If using ImageMagick, check policy file:
   ```bash
   # Ubuntu/Debian
   sudo nano /etc/ImageMagick-6/policy.xml
   
   # Look for HEIC line and ensure it's not restricted:
   # <policy domain="coder" rights="read|write" pattern="HEIC" />
   ```

3. On macOS, ensure ImageMagick was built with HEIC support:
   ```bash
   brew reinstall imagemagick --with-libheif
   ```

**Problem:** pillow-heif installation fails

**Solution:**
Try installing libheif first:
```bash
# Ubuntu/Debian
sudo apt-get install libheif-dev

# macOS
brew install libheif
```

### RAW Issues

**Problem:** "Preview unavailable" for RAW files

**Solutions:**
1. Install rawpy:
   ```bash
   pip3 install rawpy numpy
   ```

2. If rawpy fails to install, check for libraw:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install libraw-dev
   
   # macOS
   brew install libraw
   ```

3. Try ImageMagick or dcraw as alternative

**Problem:** rawpy installation fails on Windows

**Solution:**
Use pre-built wheels:
```bash
pip3 install --upgrade pip
pip3 install rawpy --only-binary :all:
```

**Problem:** Specific RAW format not supported

**Solution:**
1. Check if your camera's RAW format is in the supported list
2. Try ImageMagick (supports more formats)
3. Try dcraw (supports most formats)
4. Convert RAW to DNG using Adobe DNG Converter

### General Issues

**Problem:** Preview loads very slowly

**Possible causes:**
- Large RAW files (20+ MB)
- Using ImageMagick fallback instead of Python libraries
- Slow disk I/O

**Solutions:**
- Install Python libraries (rawpy, pillow-heif) for faster loading
- Use SSD instead of network drive for better performance
- Close other applications to free up resources

**Problem:** Some RAW files work, others don't

**Possible causes:**
- Different RAW formats
- Corrupted files
- Proprietary RAW formats

**Solutions:**
- Check file with exiftool to verify it's valid
- Try opening in camera manufacturer's software
- Convert to DNG format (more standardized)

## Recommendations

### For Best Experience:
1. **Install all methods:**
   ```bash
   pip3 install pillow-heif rawpy numpy
   sudo apt-get install imagemagick dcraw  # Ubuntu
   brew install imagemagick dcraw  # macOS
   ```

2. **For photographers (many RAW files):**
   - Install rawpy for fast preview
   - Use SSD storage
   - Consider converting to DNG for better compatibility

3. **For Apple users (many HEIC files):**
   - Install pillow-heif (essential)
   - Consider converting to JPEG for broader compatibility

4. **For minimal setup:**
   - Just install pillow-heif (for HEIC)
   - Just install ImageMagick (for both HEIC and RAW)

## Converting Formats

If you need to convert HEIF/HEIC or RAW to more standard formats:

### HEIF/HEIC to JPEG:
```bash
# Using ImageMagick
convert image.heic image.jpg

# Using Python
python3 -c "from PIL import Image; import pillow_heif; pillow_heif.register_heif_opener(); Image.open('image.heic').save('image.jpg')"
```

### RAW to JPEG:
```bash
# Using ImageMagick
convert image.cr2 image.jpg

# Using dcraw + ImageMagick
dcraw -c image.cr2 | convert - image.jpg

# Using Python
python3 -c "import rawpy; import imageio; with rawpy.imread('image.cr2') as raw: imageio.imsave('image.jpg', raw.postprocess())"
```

## Batch Conversion

For batch conversion of HEIF/HEIC or RAW files, you can use the parent scripts or command-line tools:

### Convert directory of HEIC to JPG:
```bash
for f in *.heic; do convert "$f" "${f%.heic}.jpg"; done
```

### Convert directory of RAW to JPG:
```bash
for f in *.cr2; do dcraw -c "$f" | convert - "${f%.cr2}.jpg"; done
```

## Future Enhancements

Planned improvements for HEIF/HEIC and RAW support:
- Built-in batch converter
- RAW processing options (white balance, exposure)
- Side-by-side RAW+JPEG comparison
- Faster thumbnail caching
- GPU acceleration for RAW processing

## Additional Resources

### Documentation:
- pillow-heif: https://github.com/bigcat88/pillow_heif
- rawpy: https://github.com/letmaik/rawpy
- ImageMagick: https://imagemagick.org/
- dcraw: https://www.dechifro.org/dcraw/

### Camera RAW Formats:
- List of RAW formats: https://en.wikipedia.org/wiki/Raw_image_format
- Adobe DNG: https://helpx.adobe.com/camera-raw/digital-negative.html

### HEIF Specification:
- Official spec: https://nokiatech.github.io/heif/

## Support

If you encounter issues with HEIF/HEIC or RAW support:

1. Run the prerequisite checker
2. Check the console output for error messages
3. Try a different loading method
4. Verify the file is not corrupted
5. Check the file format is in the supported list

For format-specific issues, refer to the documentation of the tool being used (rawpy, pillow-heif, ImageMagick, etc.).
