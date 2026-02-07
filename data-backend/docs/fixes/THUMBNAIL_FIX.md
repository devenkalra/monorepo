# Attachment Thumbnail Generation Fix

## Issue
Attachment thumbnails were not being generated when files were uploaded during entity save.

## Root Cause
The required Python packages for image processing were missing from the backend:
- `Pillow` - Required for image thumbnail generation
- `pdf2image` - Required for PDF thumbnail generation
- `poppler-utils` - System package required by pdf2image

## Solution

### 1. Added Python Packages to requirements.txt
```
# Image processing and thumbnails
Pillow>=10.0.0
pdf2image>=1.16.0
```

### 2. Installed System Dependencies
Installed `poppler-utils` in the backend container for PDF processing.

### 3. Backend Code Already Correct
The `save_file_deduplicated()` function in `/people/utils.py` already had the correct logic:
- Generates thumbnails for images (`.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.webp`)
- Generates thumbnails and previews for PDFs
- Returns `thumbnail_url` and `preview_url` in the response

### 4. Frontend Code Already Correct
The `EntityDetail.jsx` component already properly handles the upload response:
- Checks for `uploadResult.thumbnail_url` and `uploadResult.preview_url`
- Stores them in the attachment data
- Displays thumbnails in the UI

## How It Works Now

1. **Image Upload**:
   - File is uploaded to `/api/upload/`
   - Backend generates a 256x256 thumbnail using Pillow
   - Response includes `url` and `thumbnail_url`
   - Frontend stores both URLs in the attachment data

2. **PDF Upload**:
   - File is uploaded to `/api/upload/`
   - Backend converts first page to image using pdf2image
   - Generates both a full-size preview and 256x256 thumbnail
   - Response includes `url`, `thumbnail_url`, and `preview_url`
   - Frontend stores all URLs in the attachment data

3. **Other Files**:
   - File is uploaded and stored
   - No thumbnail generated
   - Only `url` is returned and stored

## Testing
After the fix:
1. Upload an image as an attachment → Thumbnail should be generated
2. Upload a PDF as an attachment → Thumbnail and preview should be generated
3. Upload other file types → No thumbnail (expected behavior)

## Files Modified
- `/home/ubuntu/monorepo/data-backend/requirements.txt` - Added Pillow and pdf2image
- Backend container - Installed poppler-utils system package
