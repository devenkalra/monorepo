# Photo and Attachment Caption Feature

## Overview
Added caption functionality for both photos and attachments in the EntityDetail component. Users can now add descriptive captions to their media files, which are displayed in the UI and stored with the entity data.

## Features

### Photos
- **Detail View**: 
  - Displayed in a responsive grid layout (3-6 columns depending on screen size)
  - Each photo shown as a square thumbnail with `object-cover` (centered and cropped)
  - Caption or filename displayed underneath, truncated to fit
  - Hovering shows the full caption/filename
  - Clicking opens the full-size image in lightbox
  - Consistent styling with attachments for a unified look
  
- **Edit View**:
  - Displayed in a 2-column grid with larger thumbnails
  - Each photo has:
    - Delete button (top-right)
    - Reorder buttons (top-left, up/down arrows)
    - Caption input field below
  - Placeholder shows the filename
  - Caption is saved with the photo metadata

### Attachments
- **Detail View**:
  - Displayed in a responsive grid layout (3-6 columns depending on screen size)
  - Each attachment shown as a card with:
    - Thumbnail (if available) or file icon placeholder
    - Label (caption or filename) shown underneath, truncated to fit
    - Hovering over the label shows the full text
    - Clicking the thumbnail opens the preview in lightbox
    - Clicking the label downloads the file
  - Space-efficient grid layout for viewing multiple attachments
  
- **Edit View**:
  - Displayed in a vertical list layout with full controls
  - Each attachment has:
    - Reorder buttons (up/down arrows)
    - Thumbnail preview (if available)
    - Filename link
    - Caption input field below
    - Delete button
  - Placeholder shows the filename for existing attachments
  - Caption is saved with the attachment metadata

## Data Structure

### Photo Object
```javascript
{
  url: string,              // Required: URL to the photo
  thumbnail_url: string,    // Optional: URL to thumbnail
  filename: string,         // Required: Original filename
  caption: string          // Optional: User-provided caption
}
```

### Attachment Object
```javascript
{
  url: string,              // Required: URL to the attachment
  filename: string,         // Required: Original filename
  caption: string,         // Optional: User-provided caption
  thumbnail_url: string,    // Optional: URL to thumbnail (for images/PDFs)
  preview_url: string      // Optional: URL to preview (for PDFs)
}
```

## Implementation Details

### Caption Storage
- Captions are stored as properties on the photo/attachment objects
- Old format (string URLs) is automatically converted to object format when a caption is added
- Empty captions are stored as empty strings

### Caption Display Logic
- **Photos**: `displayCaption = photoCaption || photoFilename`
- **Attachments**: `displayName = attachmentCaption || filename`

### User Experience
1. **Adding Captions to New Media**:
   - Upload photos/attachments
   - Type caption in the input field below each item
   - Save the entity

2. **Editing Existing Captions**:
   - Click Edit button
   - Modify caption in the input field
   - Save changes

3. **Viewing Captions**:
   - Photos: Hover over the image to see the caption (or filename if no caption)
   - Attachments with thumbnails: Label shown under thumbnail, hover to see full text
   - Attachments without thumbnails: Caption displayed as the link text

## Backward Compatibility
- Old entities with string-format photos/attachments continue to work
- String format is automatically converted to object format when captions are added
- If no caption is provided, the filename is used (maintaining original behavior)

## Files Modified
- `/home/ubuntu/monorepo/data-backend/frontend/src/components/EntityDetail.jsx`
  - Added caption input fields for photos (existing and new)
  - Added caption input fields for attachments (existing and new)
  - Updated display logic to show captions on hover for photos
  - Updated display logic to show captions instead of filenames for attachments
  - Updated upload handlers to include caption data
