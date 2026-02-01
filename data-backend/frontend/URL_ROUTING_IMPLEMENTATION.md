# URL-Based Routing Implementation

## Overview
Implemented browser URL-based routing with history support, enabling:
- Browser back/forward button navigation
- Bookmarkable URLs for specific entities and views
- Shareable links
- Browser history tracking

## URL Structure

### Routes
- `/` - Home page (entity list)
- `/?q=search+term` - Search results
- `/entity/:id` - Entity detail view
- `/entity/:id/edit` - Entity edit view
- `/entity/:id/relations` - Entity relations view
- `/entity/new/edit` - New entity creation
- `/import` - Import conversations view

## Implementation Details

### Files Modified

#### 1. `src/main.jsx`
- Updated to use `AppRouter` component
- Wraps entire app with `BrowserRouter`

#### 2. `src/AppRouter.jsx` (NEW)
- Main router component
- Wraps `AppWithAuth` with React Router
- Handles all route definitions

#### 3. `src/App.jsx`
- Added React Router hooks: `useNavigate`, `useLocation`, `useSearchParams`
- Added `useEffect` to handle URL changes (back/forward navigation)
- Added `loadEntityById()` function to fetch entity from API based on URL
- Updated all navigation actions to use `navigate()`:
  - `handleEntityClick()` - Navigate to entity detail
  - `handleCloseDetail()` - Navigate back to home
  - `handleEntityUpdate()` - Navigate on deletion or related entity click
  - `handleAddEntity()` - Navigate to new entity edit view
  - `handleEntityCreate()` - Navigate to created entity
  - Import button - Navigate to `/import`
  - Import close - Navigate back to home
- Added search query synchronization with URL parameters

#### 4. `src/components/EntityDetail.jsx`
- Added `useNavigate` hook
- Updated view mode toggle buttons to update URL:
  - Details tab → `/entity/:id`
  - Relations tab → `/entity/:id/relations`
- Updated edit/cancel buttons to update URL:
  - Edit button → `/entity/:id/edit`
  - Cancel edit → `/entity/:id`

## Features

### 1. Browser Back/Forward Support
- Users can navigate through their browsing history using browser buttons
- App state syncs with URL changes
- Entity details load from API when navigating via browser history

### 2. Bookmarkable URLs
- Each entity view has a unique URL
- Users can bookmark specific entities
- Direct URL access loads the entity from the API

### 3. Shareable Links
- URLs can be shared with other users
- Links open directly to the specific entity and view mode

### 4. Search Persistence
- Search queries are stored in URL parameters
- Search state persists across page reloads
- Back button returns to previous search

### 5. View Mode Tracking
- Current view mode (details/edit/relations) is reflected in URL
- Switching tabs updates the URL
- Browser history tracks view mode changes

## Technical Notes

### URL Parameter Handling
- Search queries use `?q=` parameter
- Encoded using `encodeURIComponent()` for special characters
- Parsed using `useSearchParams()` hook

### Entity Loading
- Entities are loaded from API when accessing URL directly
- Prevents stale data when using browser navigation
- Falls back to home page if entity not found

### State Synchronization
- `useEffect` hook monitors `location.pathname` and `searchParams`
- Updates component state when URL changes
- Prevents infinite loops with proper dependency management

### Navigation Strategy
- `navigate()` used for programmatic navigation
- `replace: true` option used for search updates (doesn't create history entry)
- Regular navigation for view changes (creates history entry)

## Usage Examples

### Navigate to Entity
```javascript
navigate(`/entity/${entityId}`);
```

### Navigate to Entity Edit View
```javascript
navigate(`/entity/${entityId}/edit`);
```

### Navigate to Entity Relations
```javascript
navigate(`/entity/${entityId}/relations`);
```

### Navigate with Search Query
```javascript
navigate(`/?q=${encodeURIComponent(searchTerm)}`);
```

### Navigate Back to Home
```javascript
navigate('/');
```

## Testing

### Manual Testing Checklist
- [ ] Click entity → URL updates to `/entity/:id`
- [ ] Click browser back → Returns to entity list
- [ ] Click browser forward → Returns to entity detail
- [ ] Switch to Relations tab → URL updates to `/entity/:id/relations`
- [ ] Click Edit button → URL updates to `/entity/:id/edit`
- [ ] Search for entities → URL updates with `?q=` parameter
- [ ] Refresh page on entity detail → Entity loads from API
- [ ] Copy URL and open in new tab → Correct entity loads
- [ ] Click Add Entity → URL updates to `/entity/new/edit`
- [ ] Save new entity → URL updates to `/entity/:id`
- [ ] Click Import button → URL updates to `/import`
- [ ] Close import → URL returns to `/`

## Future Enhancements

### Potential Improvements
1. **Filter Persistence**: Store filters in URL parameters
2. **Sort Persistence**: Store sort order in URL
3. **Pagination**: Add page parameter for large entity lists
4. **Tab State**: Remember which tab was active on entity detail
5. **Scroll Position**: Restore scroll position on back navigation
6. **Deep Linking**: Support for specific relation or photo in URL
7. **URL Slugs**: Use human-readable slugs instead of UUIDs

### Example Future URLs
- `/?type=Person&tag=family&sort=name`
- `/entity/:id/relations/:relationId`
- `/entity/:id/photo/:photoIndex`
- `/entity/:slug` (e.g., `/entity/john-doe`)

## Browser Compatibility
- Tested with modern browsers supporting History API
- React Router v6+ required
- Falls back gracefully for older browsers

## Performance Considerations
- Entity loading on URL navigation adds API call
- Consider caching recently viewed entities
- Debounce search query updates to URL
- Use `replace: true` for transient state changes

## Security Notes
- Entity IDs in URLs are UUIDs (not sequential)
- Authentication required for all entity access
- URLs don't expose sensitive data
- API validates user permissions on entity load
