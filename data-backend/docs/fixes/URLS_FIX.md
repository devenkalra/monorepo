# URLs Display Fix

## Issue
URLs were being displayed as JSON strings in the UI instead of as individual clickable elements.

## Root Cause
The entity data coming from the API needed to be normalized to ensure `urls`, `photos`, and `attachments` are always arrays, even if they come in different formats.

## Solution

### Frontend Fix (`EntityDetail.jsx`)
Added normalization logic when the entity is received:

```javascript
useEffect(() => {
    if (entity && isVisible) {
        // Ensure urls, photos, and attachments are arrays
        const normalizedEntity = {
            ...entity,
            urls: Array.isArray(entity.urls) ? entity.urls : (entity.urls ? [] : []),
            photos: Array.isArray(entity.photos) ? entity.photos : (entity.photos ? [] : []),
            attachments: Array.isArray(entity.attachments) ? entity.attachments : (entity.attachments ? [] : [])
        };
        
        // Store entity for display during animations
        displayEntityRef.current = normalizedEntity;
        setEditedEntity(normalizedEntity);
        // ... rest of the code
    }
}, [entity, isVisible, initialViewMode]);
```

### Backend Configuration (`people/sync.py`)
Added `displayedAttributes` configuration to MeiliSearch to ensure all fields are returned:

```python
# Define displayed attributes (what gets returned in search results)
self.helper.client.index(self.index_name).update_displayed_attributes([
    'id', 'type', 'display', 'description', 'tags', 'urls', 'photos', 'attachments',
    'locations', 'user_id', 'first_name', 'last_name', 'emails', 'phones',
    'profession', 'gender', 'dob', 'date', 'address1', 'address2', 'postal_code',
    'city', 'state', 'country', 'year', 'language', 'name', 'kind'
])
```

## URLs Display Features

### Detail View
- URLs displayed in a responsive grid (2-4 columns)
- Each URL is a clickable link opening in a new tab
- Caption displayed if available, otherwise shows the URL
- Long text is shortened with "..." and full text shown on hover

### Edit View
- URLs displayed in a row layout with controls
- Each URL has an editable caption field
- Delete button to remove URLs
- Add URL button with input field
- Can press Enter to add a URL quickly

## Testing

### Verify URLs are returned from API:
```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/search/?q=Manish"
```

Expected response includes:
```json
{
  "display": "Manish Jain (IIT GN)",
  "urls": [
    {
      "caption": "IITGN",
      "url": "https://iitgn.ac.in/faculty/cl/manish"
    }
  ]
}
```

### Verify in UI:
1. Search for "Manish" in the UI
2. Click on "Manish Jain (IIT GN)"
3. Scroll to the URLs section
4. Should see a clickable link with caption "IITGN"

## Browser Cache
If URLs still appear as JSON strings after the fix:
1. Hard refresh the browser (Ctrl+Shift+R or Cmd+Shift+R)
2. Clear browser cache
3. Restart the frontend dev server if needed

## Files Modified
- `/home/ubuntu/monorepo/data-backend/frontend/src/components/EntityDetail.jsx`
- `/home/ubuntu/monorepo/data-backend/people/sync.py`
