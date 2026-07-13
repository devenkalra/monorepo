# Media Index Test Data

This folder provides sample files for manually testing `index_media.py` and `manage_volumes.py`.

## Setup

From the `scripts/` directory:

```bash
# 1. Create a fresh database and register the test volume
python manage_volumes.py --db-path test_data/media_index/test.db set TestVol \
  --src-root /volume1/test \
  --mount "$(pwd)/test_data/media_index"

# 2. Index everything under the test volume
python index_media.py --volume TestVol --db-path test_data/media_index/test.db -v 2

# 3. Inspect results
sqlite3 test_data/media_index/test.db "SELECT volume, relpath, mime_type FROM files;"

# 4. View saved thumbnails
python show_thumbnails.py --db-path test_data/media_index/test.db \
  --file test_data/media_index/images/sample.jpg --output-dir test_data/media_index/thumbs_out --open
```

On Windows PowerShell, use the full path for `--mount`, for example:

```powershell
python manage_volumes.py --db-path test_data/media_index/test.db set TestVol `
  --src-root /volume1/test `
  --mount "C:\code\monorepo\scripts\test_data\media_index"
```

## Included sample files

| Path | Type | Purpose |
|------|------|---------|
| `images/sample.jpg` | Image | JPEG indexing + EXIF/thumbnail path |
| `documents/sample.txt` | Text document | Text preview + text thumbnail |
| `documents/sample.pdf` | PDF | Page count + PDF thumbnail (needs `pdftoppm` or `mutool`) |
| `email/sample.eml` | Email | Header/body metadata + text thumbnail |

## Files you should add locally for full coverage

These binary formats are not checked into git. Copy any small sample files into the paths below before running a full test pass.

| Path | Type | Notes |
|------|------|-------|
| `video/sample.mp4` | Video | Any short H.264 clip; needs `ffprobe` + `ffmpeg` |
| `audio/sample.mp3` | Audio | Any short MP3; needs `ffprobe` |
| `documents/sample.docx` | Office Word | Thumbnail needs LibreOffice (`soffice`) |
| `documents/sample.xlsx` | Office Excel | Metadata via exiftool |
| `documents/sample.pptx` | Office PowerPoint | Thumbnail needs LibreOffice |
| `images/sample.cr2` | RAW image | Optional; tests RAW preview extraction |

## Expected database tables per file type

| Type | Base `files` row | Metadata table | Thumbnail |
|------|------------------|----------------|-----------|
| Image | yes | `image_metadata` | JPEG from Pillow/exiftool |
| Video | yes | `video_metadata` | ffmpeg frame |
| Audio | yes | `audio_metadata` | text-style placeholder |
| PDF / txt / Office | yes | `document_metadata` | first page or text render |
| `.eml` | yes | `email_metadata` | subject/sender text render |

## Optional system tools

| Tool | Used for |
|------|----------|
| `exiftool` | **Required** for images and Office metadata |
| `ffprobe` / `ffmpeg` | Video and audio metadata/thumbnails |
| `pdfinfo` | PDF page count |
| `pdftoppm` or `mutool` | PDF first-page thumbnails |
| `soffice` (LibreOffice) | Office document thumbnails |

Without optional tools, indexing still succeeds; thumbnails or some metadata fields may be omitted.
