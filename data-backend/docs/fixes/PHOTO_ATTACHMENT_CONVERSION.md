# Photo and Attachment Conversion

## Overview
Updated the Neo4j conversion script to properly map photos and attachments from Neo4j format to Django format with all required fields including captions, filenames, URLs, and thumbnail URLs.

## Photo Conversion

### Input Format (Neo4j)
```json
[{
  "label": "Deven Passport 2032.jpg",
  "name": "photo",
  "value": "/c1e/604/c1e604699fa74c3a73395a4a5e89eb8efe5da6cfc0a9e58ae39cea87857282a7.jpg"
}]
```

### Output Format (Django)
```json
[{
  "caption": "Deven Passport 2032.jpg",
  "filename": "c1e604699fa74c3a73395a4a5e89eb8efe5da6cfc0a9e58ae39cea87857282a7.jpg",
  "url": "/media/c1e/604/c1e604699fa74c3a73395a4a5e89eb8efe5da6cfc0a9e58ae39cea87857282a7.jpg",
  "thumbnail_url": "/media/c1e/604/c1e604699fa74c3a73395a4a5e89eb8efe5da6cfc0a9e58ae39cea87857282a7_thumb.jpg"
}]
```

### Field Mappings
| Neo4j Field | Django Field | Transformation |
|-------------|--------------|----------------|
| `label` | `caption` | Direct copy |
| `value` (basename) | `filename` | Extract last part of path |
| `value` | `url` | Prefix with `/media` |
| `value` (modified) | `thumbnail_url` | Prefix with `/media`, add `_thumb` before extension |

## Attachment Conversion

### Input Format (Neo4j)
```json
[{
  "label": "Vinoba - Introduction.pdf",
  "name": "attachment",
  "value": "/1f0/541/1f05414c757508e2fd759d41c2e2e1d67ce32f8f1974512d99d80e9b36931391.pdf",
  "copy": false
}]
```

### Output Format (Django)
```json
[{
  "caption": "Vinoba - Introduction.pdf",
  "filename": "1f05414c757508e2fd759d41c2e2e1d67ce32f8f1974512d99d80e9b36931391.pdf",
  "url": "/media/1f0/541/1f05414c757508e2fd759d41c2e2e1d67ce32f8f1974512d99d80e9b36931391.pdf",
  "preview_url": "/media/1f0/541/1f05414c757508e2fd759d41c2e2e1d67ce32f8f1974512d99d80e9b36931391_preview.jpg",
  "thumbnail_url": "/media/1f0/541/1f05414c757508e2fd759d41c2e2e1d67ce32f8f1974512d99d80e9b36931391_thumb.jpg"
}]
```

### Field Mappings
| Neo4j Field | Django Field | Transformation |
|-------------|--------------|----------------|
| `label` | `caption` | Direct copy |
| `value` (basename) | `filename` | Extract last part of path |
| `value` | `url` | Prefix with `/media` |
| `value` (modified) | `preview_url` | Prefix with `/media`, replace extension with `_preview.jpg` |
| `value` (modified) | `thumbnail_url` | Prefix with `/media`, replace extension with `_thumb.jpg` |

## Implementation Details

### Helper Functions

#### `convert_photos(photos_data)`
- Parses Neo4j photo JSON array
- Extracts filename from value path
- Creates thumbnail filename by adding `_thumb` before extension
- Maintains directory structure
- Returns list of photo objects with all required fields

#### `convert_attachments(attachments_data)`
- Parses Neo4j attachment JSON array
- Extracts filename from value path
- Creates preview filename: `{basename}_preview.jpg`
- Creates thumbnail filename: `{basename}_thumb.jpg`
- Maintains directory structure
- Returns list of attachment objects with all required fields

### Path Processing

#### Directory Structure Preservation
Neo4j stores files in a content-addressable structure:
```
/abc/def/abcdef1234567890...xyz.ext
```

This structure is preserved in all generated URLs:
- Original: `/abc/def/abcdef1234567890...xyz.ext`
- Thumbnail: `/abc/def/abcdef1234567890...xyz_thumb.ext`
- Preview: `/abc/def/abcdef1234567890...xyz_preview.jpg`

#### Media URL Prefix
All paths are prefixed with `/media` to match Django's media serving configuration:
- Neo4j: `/abc/def/file.jpg`
- Django: `/media/abc/def/file.jpg`

## Conversion Statistics

From the latest conversion of `full_graph.json`:
- **Total entities**: 1,842
- **Entities with photos**: ~200+ (estimated)
- **Entities with attachments**: 35

## Backward Compatibility

The conversion functions handle both:
1. **New format**: Objects with `label`, `name`, `value` fields
2. **Old format**: Simple URL strings

If old format is detected, it's passed through unchanged.

## Testing

### Verify Photo Conversion
```bash
cat full_import.json | jq '[.people[], .notes[]] | map(select(.photos and (.photos | length) > 0)) | .[0].photos[0]'
```

Expected output:
```json
{
  "caption": "...",
  "filename": "...",
  "url": "/media/...",
  "thumbnail_url": "/media/...thumb..."
}
```

### Verify Attachment Conversion
```bash
cat full_import.json | jq '[.people[], .notes[]] | map(select(.attachments and (.attachments | length) > 0)) | .[0].attachments[0]'
```

Expected output:
```json
{
  "caption": "...",
  "filename": "...",
  "url": "/media/...",
  "preview_url": "/media/..._preview.jpg",
  "thumbnail_url": "/media/..._thumb.jpg"
}
```

## Files Modified
- `/home/ubuntu/monorepo/data-backend/convert_neo4j_test.py`
  - Added `convert_photos()` function
  - Added `convert_attachments()` function
  - Updated `common_data` to use conversion functions

## Next Steps

After importing the data:
1. Verify photos display correctly in the UI
2. Verify photo captions appear on hover
3. Verify attachments display with thumbnails (for PDFs/images)
4. Verify attachment captions appear as link text
5. Check that clicking thumbnails opens previews in lightbox
