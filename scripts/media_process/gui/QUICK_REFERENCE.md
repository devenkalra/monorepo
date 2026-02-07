# Quick Reference Card

## Launch
```bash
cd /home/ubuntu/monorepo/scripts/media_process/gui
./run_media_processor.sh
```

## Main Controls

| Control | Location | Purpose |
|---------|----------|---------|
| **Browse** | Top bar | Select directory |
| **Refresh** | Top bar | Reload file list |
| **Filter** | Left panel | Search filenames |
| **☑ Images/Videos/Other** | Left panel | Filter file types |
| **EXIF Display** | Right panel | Filter EXIF data |
| **Database** | Bottom panel | Select database file |
| **Volume Filter** | Bottom panel | Filter by volume |
| **Save Settings** | Status bar | Save preferences |

## EXIF Display Modes

| Mode | Shows |
|------|-------|
| **All** | Complete metadata |
| **Common** | Essential info (default) |
| **GPS/Location** | GPS and location data |
| **Camera** | Camera settings |
| **Keywords** | Keywords and captions |
| **Video** | Video metadata |

## Database Status Colors

| Color | Meaning |
|-------|---------|
| 🟢 Green ✓ | Indexed / In correct volume |
| 🔴 Red ✗ | Not in database |
| 🟠 Orange ✗ | In database but wrong volume |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **Click** | Select file |
| **Ctrl+Click** | Add/remove from selection |
| **Shift+Click** | Select range |
| **Tab** | Navigate controls |

## Common Workflows

### Quick Preview
1. Launch app
2. Select file
3. **Instant preview** if indexed

### Verify Volume
1. Set volume filter
2. Browse files
3. Check colors:
   - 🟢 = Correct
   - 🟠 = Wrong volume
   - 🔴 = Not indexed

### Review Camera Settings
1. Select file
2. Change EXIF to "Camera"
3. See shooting parameters

### Find Unindexed Files
1. Select all files
2. Check multi-file stats
3. See "Not in database: X"

### Index New Files
1. Select files
2. Click "Index Media Files"
3. Set volume name
4. Enable dry-run (test)
5. Click "Start"

## File Types Supported

**Images:** JPEG, PNG, GIF, BMP, TIFF  
**HEIF:** .heic, .heif, .avif  
**RAW:** CR2, NEF, ARW, DNG, ORF, etc. (30+ formats)  
**Video:** MP4, MOV, AVI, MKV, etc.

## Performance Tips

✅ Files in database = instant preview  
✅ Use Common EXIF filter for speed  
✅ Filter files before selecting all  
✅ Enable dry-run before batch ops  

## Configuration

**File:** `media_processor_config.yaml`  
**Auto-saved:** Click "Save Settings"  
**Auto-loaded:** On startup

**Saved:**
- Directory
- Database path
- Volume filter
- EXIF filter
- File filters
- Window size

## Troubleshooting

**No preview:**
- Check file format supported
- Install pillow-heif (HEIC)
- Install rawpy (RAW)

**No EXIF:**
- Install exiftool
- Select different EXIF filter

**Slow preview:**
- Index file to database
- Use database cache

**Not in database:**
- Red ✗ indicator
- Use "Index Media Files"

## Quick Commands

**Check prerequisites:**
```bash
./check_prerequisites.py
```

**Install HEIC support:**
```bash
pip3 install pillow-heif
```

**Install RAW support:**
```bash
pip3 install rawpy numpy
```

## Documentation

| Doc | Purpose |
|-----|---------|
| **QUICKSTART.md** | 5-min setup |
| **README.md** | Complete guide |
| **INDEX.md** | Find docs |
| **VERSION_1.2_SUMMARY.md** | Latest features |

## Support

1. Check documentation
2. Run `check_prerequisites.py`
3. Review operation output
4. Check status bar messages

---

**Version:** 1.2.0  
**Docs:** See INDEX.md
