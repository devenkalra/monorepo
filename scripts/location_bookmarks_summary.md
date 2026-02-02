# Location Bookmarks Feature Summary

**Date:** 2026-01-28  
**Status:** ✅ **COMPLETED**

---

## Overview

Added a location bookmarks feature to `image_process.py` that allows users to save and load location presets for the `apply_exif` command. Users can quickly fill in all location fields with a single click.

---

## Features

### 1. **Save Location Bookmarks** 💾
- Save current location field values with a custom name
- Stores GPS coordinates, city, state, country, country code, and full address
- Persistent storage in JSON file

### 2. **Load Location Bookmarks** 📍
- Select bookmark from dropdown menu
- Auto-fills all location fields
- One-click location entry

### 3. **Persistent Storage**
- Bookmarks saved to `~/.image_process_bookmarks.json`
- Automatically loaded on application start
- JSON format for easy manual editing

---

## User Interface

### **New Controls in Apply EXIF:**

```
┌─────────────────────────────────────────────────────────────┐
│ Location Bookmark: [▼ Dropdown] [📍 Load] [💾 Save]        │
├─────────────────────────────────────────────────────────────┤
│ GPS Coordinates:   [28.5439554,77.198706,1183]              │
│ City:              [New Delhi]                               │
│ State:             [Delhi]                                   │
│ Country:           [India]                                   │
│ Country Code:      [IN]                                      │
│ Full Address:      [Connaught Place, New Delhi, ...]        │
└─────────────────────────────────────────────────────────────┘
```

### **Button Functions:**

- **📍 Load Button**: Loads selected bookmark into location fields
- **💾 Save Button**: Opens dialog to save current location as bookmark

---

## Bookmark File Structure

**Location:** `~/.image_process_bookmarks.json`

**Format:**
```json
{
  "Home": {
    "gps_coords": "32.7157,-97.3308,195",
    "city": "Fort Worth",
    "state": "Texas",
    "country": "USA",
    "country_code": "US",
    "coverage": "123 Main Street, Fort Worth, TX 76102, USA"
  },
  "Office": {
    "gps_coords": "28.5439554,77.198706,1183",
    "city": "New Delhi",
    "state": "Delhi",
    "country": "India",
    "country_code": "IN",
    "coverage": "Connaught Place, New Delhi, Delhi 110001, India"
  },
  "Vacation Spot": {
    "gps_coords": "37.7749,-122.4194,52",
    "city": "San Francisco",
    "state": "California",
    "country": "USA",
    "country_code": "US",
    "coverage": "Golden Gate Bridge, San Francisco, CA"
  }
}
```

---

## Workflow

### **Saving a Location Bookmark:**

1. Fill in location fields (GPS coords, city, state, country, etc.)
2. Click **💾 Save** button
3. Enter bookmark name in dialog (e.g., "Home", "Office", "Vacation Spot")
4. Click **Save**
5. Bookmark is saved and appears in dropdown
6. Success message confirms save

### **Loading a Location Bookmark:**

**Method 1: From Dropdown**
1. Click dropdown next to "Location Bookmark"
2. Select saved bookmark (e.g., "Home")
3. Click **📍 Load** button
4. All location fields auto-filled
5. Status bar shows: "✓ Loaded bookmark: Home"

**Method 2: Auto-Load on Selection**
1. Click dropdown
2. Select bookmark
3. Fields automatically populate (no need to click Load)

### **Editing a Bookmark:**

1. Load the bookmark
2. Modify any location fields
3. Click **💾 Save** button
4. Enter same bookmark name
5. Bookmark is updated (overwrites old values)

### **Deleting a Bookmark:**

*Manual method (currently):*
1. Close application
2. Edit `~/.image_process_bookmarks.json`
3. Remove bookmark entry
4. Save file
5. Restart application

---

## Use Cases

### **1. Multiple Photo Shoots at Same Locations**

**Scenario:** You regularly take photos at a few locations

```
Bookmarks:
- "Home" → Your house
- "Studio" → Photography studio
- "Park" → Favorite park
- "Downtown" → City center
```

**Workflow:**
- Select files from shoot
- Pick location from bookmark dropdown
- Click Load
- Add other tags (date, keywords, etc.)
- Execute

---

### **2. Travel Photography**

**Scenario:** Creating bookmarks as you travel

```
Day 1: Save "Eiffel Tower" bookmark
Day 2: Save "Louvre Museum" bookmark
Day 3: Save "Notre Dame" bookmark
...
```

**Later, when organizing:**
- Select photos
- Pick day's location from bookmarks
- All location metadata applied instantly

---

### **3. Event Photography**

**Scenario:** Wedding at a venue

```
Save bookmark: "Smith Wedding Venue"
- GPS: 30.2672,-97.7431,149
- Address: "Barton Creek Resort, Austin, TX"
```

**For all photos from event:**
- Load "Smith Wedding Venue" bookmark
- Consistent location metadata across hundreds of photos

---

### **4. Real Estate Photography**

**Scenario:** Multiple properties

```
Bookmarks:
- "123 Oak Street" → Property 1
- "456 Pine Avenue" → Property 2
- "789 Maple Drive" → Property 3
```

**For each property shoot:**
- Select property photos
- Load corresponding bookmark
- Perfect location metadata for MLS

---

## Implementation Details

### **New Parameter Type: `bookmark_dropdown`**

Added to `PARAM_DEFS`:

```python
'location_bookmark': {
    'label': 'Location Bookmark',
    'type': 'bookmark_dropdown',  # Special type
    'flag': '',  # No command flag (UI only)
    'help': 'Select saved location bookmark',
    'default': ''
}
```

### **UI Components:**

```python
# Dropdown with bookmark names
bookmark_names = [''] + list(self.location_bookmarks.keys())
combobox = ttk.Combobox(frame, textvariable=var, values=bookmark_names, width=30)
combobox.bind('<<ComboboxSelected>>', lambda e: self.load_location_bookmark())

# Load button (📍)
load_btn = ttk.Button(frame, text="📍 Load", command=self.load_location_bookmark, width=8)

# Save button (💾)
save_btn = ttk.Button(frame, text="💾 Save", command=self.save_location_bookmark, width=8)
```

### **Bookmark Storage Methods:**

```python
def load_bookmarks(self):
    """Load location bookmarks from file."""
    # Loads from ~/.image_process_bookmarks.json
    # Returns dict of bookmarks
    
def save_bookmarks(self):
    """Save location bookmarks to file."""
    # Saves to ~/.image_process_bookmarks.json
    # JSON format with indentation
```

### **Bookmark Operations:**

```python
def save_location_bookmark(self):
    """Save current location fields as a bookmark."""
    # Opens dialog to get bookmark name
    # Collects current values from location fields
    # Saves to bookmarks dict
    # Updates dropdown values
    # Persists to file

def load_location_bookmark(self):
    """Load a location bookmark and populate location fields."""
    # Gets selected bookmark name
    # Retrieves bookmark data
    # Populates all location fields
    # Updates command preview
    # Shows status message
```

---

## Save Dialog

When clicking **💾 Save**, a dialog appears:

```
┌─────────────────────────────────────────────┐
│          Save Location Bookmark             │
├─────────────────────────────────────────────┤
│                                             │
│  Bookmark Name:                             │
│  ┌─────────────────────────────────────┐   │
│  │ [Enter name here...]                 │   │
│  └─────────────────────────────────────┘   │
│                                             │
│          [Save]  [Cancel]                   │
│                                             │
└─────────────────────────────────────────────┘
```

**Features:**
- Centered on screen
- Modal dialog (blocks main window)
- Enter key submits
- Escape key cancels
- Validation: name required
- Validation: at least one location field must have data
- Overwrites if name already exists

---

## Location Fields Saved

The following fields are saved in bookmarks:

| Field | Parameter | Example |
|-------|-----------|---------|
| GPS Coordinates | `gps_coords` | `28.5439554,77.198706,1183` |
| City | `city` | `New Delhi` |
| State | `state` | `Delhi` |
| Country | `country` | `India` |
| Country Code | `country_code` | `IN` |
| Full Address | `coverage` | `Connaught Place, New Delhi...` |

**Note:** Only non-empty fields are saved

---

## Command Line Impact

**Important:** The bookmark dropdown is **UI-only** and does **not** generate command-line flags.

**Before bookmark load:**
```bash
python3 apply_exif.py --file photo.jpg
```

**After loading "Home" bookmark:**
```bash
python3 apply_exif.py --file photo.jpg \
  --latitude 32.7157 \
  --longitude -97.3308 \
  --altitude 195 \
  --city "Fort Worth" \
  --state Texas \
  --country USA \
  --country-code US \
  --coverage "123 Main Street, Fort Worth, TX 76102, USA"
```

The bookmark loads values into the location fields, which then generate their respective command flags.

---

## Integration with Existing Features

### **Works With:**

✅ **Place Geocoding** - Can use both bookmarks and `--place` lookup  
✅ **Manual GPS Entry** - Bookmark provides GPS, can edit after loading  
✅ **Config Save/Load** - Bookmarks separate from config files  
✅ **Command Preview** - Updates in real-time when bookmark loaded  
✅ **All Scripts** - Only appears for `apply_exif` command  

### **Priority:**

1. **User Manual Entry** (highest priority)
   - Type directly in fields
   - Overrides bookmark values

2. **Bookmark Load**
   - Fills in fields
   - Can be edited after loading

3. **Place Geocoding**
   - Can use instead of bookmarks
   - Automatically fills fields from lookup

---

## Benefits

### **For Users:**
- ⚡ **Fast** - One click vs filling 6 fields
- 🎯 **Accurate** - No typos, consistent data
- 📍 **Reusable** - Save once, use forever
- 🗂️ **Organized** - All locations in one place
- ✏️ **Editable** - Load, modify, re-save

### **For Workflow:**
- Same location for multiple photo batches
- Consistent location metadata across projects
- Quick switching between common locations
- Backup/share bookmarks file between machines

---

## Example Bookmarks for Common Scenarios

### **Home Office:**
```json
{
  "Home Office": {
    "gps_coords": "32.7157,-97.3308,195",
    "city": "Fort Worth",
    "state": "Texas",
    "country": "USA",
    "country_code": "US",
    "coverage": "123 Main Street, Fort Worth, TX 76102, USA"
  }
}
```

### **Famous Landmarks:**
```json
{
  "Eiffel Tower": {
    "gps_coords": "48.8584,2.2945,324",
    "city": "Paris",
    "country": "France",
    "country_code": "FR",
    "coverage": "Eiffel Tower, Champ de Mars, 75007 Paris, France"
  },
  "Statue of Liberty": {
    "gps_coords": "40.6892,-74.0445,93",
    "city": "New York",
    "state": "New York",
    "country": "USA",
    "country_code": "US",
    "coverage": "Liberty Island, New York, NY 10004, USA"
  }
}
```

### **Wedding Venues:**
```json
{
  "Smith Wedding - Main Hall": {
    "gps_coords": "30.2672,-97.7431,149",
    "coverage": "Barton Creek Resort, 8212 Barton Club Dr, Austin, TX 78735"
  },
  "Smith Wedding - Garden": {
    "gps_coords": "30.2675,-97.7428,145",
    "coverage": "Barton Creek Resort Garden, Austin, TX 78735"
  }
}
```

---

## Technical Details

### **File Location:**
```
~/.image_process_bookmarks.json
```

**Full path examples:**
- Linux: `/home/username/.image_process_bookmarks.json`
- macOS: `/Users/username/.image_process_bookmarks.json`
- Windows: `C:\Users\username\.image_process_bookmarks.json`

### **File Permissions:**
- User read/write only
- JSON format with 2-space indentation
- Created automatically on first save
- Loaded automatically on app start

### **Error Handling:**
- Missing file: Creates new empty bookmarks
- Invalid JSON: Shows error, uses empty bookmarks
- Save failure: Shows error dialog
- Load failure: Shows warning message

---

## Keyboard Shortcuts

### **In Save Dialog:**
- **Enter** - Save bookmark
- **Escape** - Cancel dialog

### **In Main UI:**
- *No shortcuts yet (future enhancement)*

---

## Future Enhancements (Optional)

Potential improvements:

1. **Delete Button**
   - Delete bookmark from UI
   - No manual file editing needed

2. **Rename Button**
   - Rename existing bookmarks
   - Preserve all data

3. **Import/Export**
   - Share bookmarks with others
   - Backup to different location

4. **Bookmark Categories**
   - Organize by project, location type, etc.
   - Nested dropdowns

5. **Recent Bookmarks**
   - Quick access to most used
   - History tracking

6. **Search/Filter**
   - Find bookmarks quickly
   - Filter by field values

7. **Keyboard Shortcuts**
   - Ctrl+B - Open bookmark dropdown
   - Ctrl+S - Save bookmark
   - Quick number keys (1-9) for top bookmarks

---

## Files Modified

**`/home/ubuntu/monorepo/scripts/image_process.py`**

### Changes:
1. Added `location_bookmark` parameter definition
2. Added `bookmark_dropdown` parameter type
3. Added bookmark UI controls (dropdown, Load, Save buttons)
4. Added `load_bookmarks()` method
5. Added `save_bookmarks()` method
6. Added `save_location_bookmark()` method with dialog
7. Added `load_location_bookmark()` method
8. Added bookmark file path to `__init__`
9. Updated `save_current_values()` to handle bookmarks
10. Updated `restore_saved_values()` to handle bookmarks
11. Updated `build_command()` to skip bookmark dropdown

**Lines added:** ~150  
**No breaking changes**

---

## Testing

### Test 1: Save Bookmark
```
✓ Fill in location fields
✓ Click Save button
✓ Dialog appears
✓ Enter name
✓ Click Save
✓ Bookmark appears in dropdown
✓ File created/updated
✓ Success message shown
```

### Test 2: Load Bookmark
```
✓ Select bookmark from dropdown
✓ Fields auto-populated
✓ GPS coords parsed correctly
✓ All text fields filled
✓ Command preview updated
✓ Status message shown
```

### Test 3: Edit Bookmark
```
✓ Load existing bookmark
✓ Modify fields
✓ Save with same name
✓ Bookmark updated
✓ New values saved to file
```

### Test 4: Multiple Bookmarks
```
✓ Create 3+ bookmarks
✓ All appear in dropdown
✓ Can switch between them
✓ Each loads correct data
```

### Test 5: Persistence
```
✓ Save bookmarks
✓ Close application
✓ Reopen application
✓ Bookmarks still available
✓ All data intact
```

---

## Conclusion

✅ **Location bookmarks feature complete**  
✅ **Save and load location presets**  
✅ **Persistent JSON storage**  
✅ **User-friendly dialog interface**  
✅ **One-click location entry**  
✅ **Seamless integration with existing features**  
✅ **No breaking changes**  

Users can now save frequently-used locations and apply them to photos with a single click! 🎉
