# Apply EXIF Quick Reference

## Basic Usage

```bash
python3 apply_exif.py --files photo.jpg --latitude 32.7157 --longitude -97.3308
```

## Verbosity Levels

| Level | Flag | Description |
|-------|------|-------------|
| **0** | `--verbose 0` | Quiet (default) - basic messages only |
| **1** | `--verbose 1` | Verbose - detailed progress |
| **2** | `--verbose 2` | Debug - step-by-step trace |
| **3** | `--verbose 3` | Trace - full subprocess output |

## Common Use Cases

### Apply GPS coordinates
```bash
python3 apply_exif.py \
  --files photo.jpg \
  --latitude 32.7157 \
  --longitude -97.3308 \
  --altitude 200
```

### Geocode from place name
```bash
python3 apply_exif.py \
  --files photo.jpg \
  --place "Fort Worth, Texas, USA"
```

### Apply location details manually
```bash
python3 apply_exif.py \
  --files photo.jpg \
  --city "Fort Worth" \
  --state "Texas" \
  --country "USA" \
  --country-code "US"
```

### Add date/time
```bash
python3 apply_exif.py \
  --files photo.jpg \
  --date "2024:03:15 14:30:00" \
  --offset "-06:00"
```

### Add keywords
```bash
python3 apply_exif.py \
  --files photo.jpg \
  --add-keyword "family" \
  --add-keyword "vacation"
```

### Update database after EXIF changes
```bash
python3 apply_exif.py \
  --files photo.jpg \
  --latitude 32.7157 \
  --longitude -97.3308 \
  --db-path ~/media_index.db \
  --reprocess-db
```

### Debug mode (see what's happening)
```bash
python3 apply_exif.py --verbose 2 \
  --files photo.jpg \
  --latitude 32.7157 \
  --longitude -97.3308 \
  --db-path ~/media_index.db \
  --reprocess-db
```

### Dry run (test without writing)
```bash
python3 apply_exif.py --dry-run \
  --files photo.jpg \
  --place "Fort Worth, Texas, USA"
```

## All Options

```
--files FILE              Image file to process (can be repeated)
--pattern GLOB            Glob pattern to select files
--dry-run                 Show what would be done without writing

Location (Geocoding):
--place "Location"        Geocode place name to GPS coordinates

Location (Manual):
--latitude LAT            GPS latitude (-90 to 90)
--longitude LON           GPS longitude (-180 to 180)
--altitude ALT            GPS altitude in meters
--city CITY               City name
--state STATE             State/province
--country COUNTRY         Country name
--country-code CODE       Country code (e.g., "US")
--coverage TEXT           Full address (stored in XMP-dc:Coverage)

Date/Time:
--date "YYYY:MM:DD HH:MM:SS"  Date/time
--offset "+HH:MM"        UTC offset (e.g., "-06:00")

Keywords:
--add-keyword WORD        Add keyword (can be repeated)
--remove-keyword WORD     Remove keyword (can be repeated)

Other:
--caption TEXT            Caption text
--limit N                 Process only first N files

Database:
--db-path PATH            Media database path
--reprocess-db            Reprocess files in database after update

Debugging:
--verbose {0,1,2,3}       Verbosity level (0=quiet, 3=trace)
```

## Examples with Database Reprocessing

### Single file with GPS and database update
```bash
python3 apply_exif.py \
  --files /mnt/photo/2024/vacation/IMG_1234.jpg \
  --latitude 32.7157 \
  --longitude -97.3308 \
  --city "Fort Worth" \
  --db-path ~/media_index.db \
  --reprocess-db \
  --verbose 1
```

### Multiple files with place lookup
```bash
python3 apply_exif.py \
  --files photo1.jpg \
  --files photo2.jpg \
  --files photo3.jpg \
  --place "Fort Worth, Texas, USA" \
  --date "2024:03:15 14:30:00" \
  --db-path ~/media_index.db \
  --reprocess-db
```

### Test with debug output
```bash
python3 apply_exif.py --verbose 2 \
  --files /mnt/photo/test.jpg \
  --latitude 32.7157 \
  --longitude -97.3308 \
  --db-path ~/media_index.db \
  --reprocess-db \
  --limit 1
```

## Troubleshooting

### Check if EXIF is being written
```bash
# Run with debug
python3 apply_exif.py --verbose 2 --files photo.jpg --city "Fort Worth"

# Verify with exiftool
exiftool -City photo.jpg
```

### Check if file is in database
```bash
python3 locate_in_db.py --files photo.jpg --db-path ~/media_index.db
```

### Test database reprocessing
```bash
# With full trace
python3 apply_exif.py --verbose 3 \
  --files photo.jpg \
  --city "Fort Worth" \
  --db-path ~/media_index.db \
  --reprocess-db
```
