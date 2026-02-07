# UI Layout - Media Processor GUI

This document describes the layout and components of the Media Processor GUI.

## Main Window Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Media Processor                                                   [─][□][×]│
├─────────────────────────────────────────────────────────────────────────┤
│ TOP BAR                                                                  │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Directory: [/home/user/photos                   ][Browse][Refresh] │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────┬──────────────────────────────────────────┤
│ LEFT PANEL: FILE BROWSER     │ RIGHT PANEL: PREVIEW & INFO              │
│ ┌──────────────────────────┐ │ ┌──────────────────────────────────────┐ │
│ │ Files                    │ │ │ Preview                              │ │
│ │ ┌──────────────────────┐ │ │ │ ┌──────────────────────────────────┐ │ │
│ │ │Filter: [search...  ] │ │ │ │ │                                  │ │ │
│ │ └──────────────────────┘ │ │ │ │         [Image Preview]          │ │ │
│ │ [✓]Images [✓]Videos      │ │ │ │                                  │ │ │
│ │ [ ]Other                 │ │ │ │           500x400                │ │ │
│ │ ┌──────────────────────┐ │ │ │ └──────────────────────────────────┘ │ │
│ │ │ photo1.jpg          │ │ │ └──────────────────────────────────────┘ │
│ │ │ photo2.jpg          │ │ │ ┌──────────────────────────────────────┐ │
│ │ │ vacation/img3.jpg   │ │ │ │ File Information                     │ │
│ │ │ video1.mp4          │ │ │ │ ┌──────────────────────────────────┐ │ │
│ │ │ ...                 │ │ │ │ │File: photo1.jpg                  │ │ │
│ │ │                     │ │ │ │ │Path: /home/user/photos/photo1.jpg│ │ │
│ │ │                     │ │ │ │ │Size: 2.3 MB                      │ │ │
│ │ │                     │ │ │ │ │Modified: 2024-01-15 10:30:45     │ │ │
│ │ │                     │ │ │ │ │                                  │ │ │
│ │ │                     │ │ │ │ │--- EXIF Data ---                 │ │ │
│ │ │                     │ │ │ │ │Make: Canon                       │ │ │
│ │ │                     │ │ │ │ │Model: EOS 5D Mark IV            │ │ │
│ │ │                     │ │ │ │ │DateTimeOriginal: 2024:01:15...  │ │ │
│ │ │                     │ │ │ │ │...                               │ │ │
│ │ │                     │ │ │ │ │                                  │ │ │
│ │ │                     │↕│ │ │ │                                  │↕│ │
│ │ └──────────────────────┘ │ │ └──────────────────────────────────┘ │ │
│ │ Selected: 3 files        │ │                                        │ │
│ └──────────────────────────┘ │                                        │ │
├──────────────────────────────┴──────────────────────────────────────────┤
│ BOTTOM BAR: OPERATIONS                                                  │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Bulk Operations                                                     │ │
│ │ ┌─────────────────────────────────────────────────────────────────┐ │ │
│ │ │ Database: [/home/user/media.db            ][Browse]            │ │ │
│ │ └─────────────────────────────────────────────────────────────────┘ │ │
│ │ [Index Media Files][Move Media Files][Manage Duplicates]           │ │
│ │ [Locate in Database][Apply EXIF]                                   │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────┤
│ STATUS BAR                                                              │
│ Ready                                                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### 1. Top Bar (Directory Selection)

**Location:** Top of window  
**Purpose:** Navigate to directories containing media files

**Components:**
- **Label:** "Directory:"
- **Entry Field:** Shows current directory path (read-only)
- **Browse Button:** Opens directory selection dialog
- **Refresh Button:** Reloads file list from current directory

**User Actions:**
- Click Browse to select a new directory
- Click Refresh to update file list
- Directory path updates automatically on selection

---

### 2. Left Panel (File Browser)

**Location:** Left side, below top bar  
**Purpose:** Browse, filter, and select media files

#### 2.1 Filter Section

**Components:**
- **Filter Entry:** Text field for filename search
- **Type Checkboxes:**
  - ☑ Images
  - ☑ Videos
  - ☐ Other

**User Actions:**
- Type in filter to search filenames
- Check/uncheck file types to show/hide
- Filters apply automatically

#### 2.2 File List

**Components:**
- **Listbox:** Scrollable list of files (relative paths)
- **Scrollbar:** Vertical scrollbar for navigation
- **Selection Label:** Shows count of selected files

**User Actions:**
- Click to select single file
- Ctrl+Click to add/remove from selection
- Shift+Click to select range
- Scroll to view more files

**Display Format:**
- Shows relative paths from current directory
- Files from subdirectories show path prefix
- Example: `vacation/photos/img001.jpg`

---

### 3. Right Panel (Preview & Info)

**Location:** Right side, below top bar  
**Purpose:** Display preview and metadata for selected files

#### 3.1 Preview Area

**Location:** Top half of right panel  
**Size:** Approximately 500x400 pixels  
**Purpose:** Show image preview

**Display States:**
- **No Selection:** "No file selected" (gray background)
- **Single Image:** Thumbnail preview (proportionally scaled)
- **Single Video:** "Video file (Preview not available)"
- **Single Other:** "No preview available"
- **Multiple Files:** "N files selected"
- **Error:** "Preview error: [message]"

#### 3.2 Information Area

**Location:** Bottom half of right panel  
**Purpose:** Display file details and EXIF data

**Components:**
- **Scrollable Text Area:** Shows file information
- **Vertical Scrollbar:** For long metadata

**Display Content:**

**Single File:**
```
File: photo1.jpg
Path: /full/path/to/photo1.jpg
Size: 2.3 MB
Modified: 2024-01-15 10:30:45

--- EXIF Data ---
Make: Canon
Model: EOS 5D Mark IV
DateTimeOriginal: 2024:01:15 10:30:45
FNumber: 2.8
ISO: 400
FocalLength: 50mm
GPSLatitude: 40.7128 N
GPSLongitude: 74.0060 W
...
```

**Multiple Files:**
```
Selected 5 files

Images: 3
Videos: 1
Other: 1

Total size: 15.7 MB
```

---

### 4. Bottom Bar (Operations)

**Location:** Bottom of window, above status bar  
**Purpose:** Configure database and execute bulk operations

#### 4.1 Database Configuration

**Components:**
- **Label:** "Database:"
- **Entry Field:** Path to database file
- **Browse Button:** Opens file dialog

**User Actions:**
- Click Browse to select .db file
- Type path directly
- Path persists during session

#### 4.2 Operation Buttons

**Layout:** Single row of buttons

**Buttons:**
1. **Index Media Files**
   - Add files to database with metadata
   - Requires: Files selected, database specified

2. **Move Media Files**
   - Move files and update database
   - Requires: Files selected, database specified

3. **Manage Duplicates**
   - Find and organize duplicate files
   - Requires: Database specified

4. **Locate in Database**
   - Find files in database
   - Requires: Files selected, database specified

5. **Apply EXIF**
   - Add/update EXIF metadata
   - Requires: Files selected

---

### 5. Status Bar

**Location:** Bottom of window  
**Purpose:** Show current application status

**Display Messages:**
- "Ready" - Idle state
- "Loading files..." - During directory scan
- "Loaded N files" - After successful load
- "Error loading files" - On error

---

## Operation Dialogs

All operation dialogs follow a similar layout:

```
┌─────────────────────────────────────────┐
│ [Operation Name]              [─][×]    │
├─────────────────────────────────────────┤
│ Info Section                            │
│ • Files: N file(s)                      │
│ • Database: /path/to/db                 │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ Options                             │ │
│ │ ┌─────────────────────────────────┐ │ │
│ │ │ [Operation-specific options]    │ │ │
│ │ └─────────────────────────────────┘ │ │
│ │ [ ] Dry run (preview only)          │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ Output                              │ │
│ │ ┌─────────────────────────────────┐ │ │
│ │ │ Running: command...             │ │ │
│ │ │ Processing file 1...            │ │ │
│ │ │ Processing file 2...            │ │ │
│ │ │ ...                             │ │ │
│ │ │ ✓ Operation completed           │↕│ │
│ │ └─────────────────────────────────┘ │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ [Start] [Close]                         │
└─────────────────────────────────────────┘
```

### Dialog Sections

1. **Title Bar:** Operation name
2. **Info Section:** Summary of inputs
3. **Options Section:** Operation-specific configuration
4. **Output Section:** Real-time command output
5. **Button Bar:** Start and Close buttons

### Example: Index Media Dialog

```
┌─────────────────────────────────────────┐
│ Index Media Files             [─][×]    │
├─────────────────────────────────────────┤
│ Indexing 5 file(s)                      │
│ Database: /home/user/media.db           │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ Options                             │ │
│ │ Volume: [MediaLibrary            ]  │ │
│ │ [✓] Dry run (preview only)          │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ Output                              │ │
│ │ ┌─────────────────────────────────┐ │ │
│ │ │ [Output appears here after      │ │ │
│ │ │  clicking Start]                │ │ │
│ │ │                                 │↕│ │
│ │ └─────────────────────────────────┘ │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ [Start] [Close]                         │
└─────────────────────────────────────────┘
```

### Example: Apply EXIF Dialog

```
┌─────────────────────────────────────────┐
│ Apply EXIF Tags               [─][×]    │
├─────────────────────────────────────────┤
│ Applying EXIF to 3 file(s)              │
│ Database: /home/user/media.db           │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ Options                             │ │
│ │ Place: [New York, NY, USA        ]  │ │
│ │ Add Keywords: [vacation, summer  ]  │ │
│ │              (comma-separated)      │ │
│ │ Caption: [Summer vacation 2024   ]  │ │
│ │ [✓] Update database after EXIF      │ │
│ │ [ ] Dry run (preview only)          │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ Output                              │ │
│ │ ┌─────────────────────────────────┐ │ │
│ │ │ Running: python3 apply_exif.py  │ │ │
│ │ │ Processing: photo1.jpg          │ │ │
│ │ │   ✓ EXIF tags written           │ │ │
│ │ │   ✓ Database updated            │ │ │
│ │ │ Processing: photo2.jpg          │ │ │
│ │ │   ✓ EXIF tags written           │ │ │
│ │ │   ✓ Database updated            │↕│ │
│ │ └─────────────────────────────────┘ │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ [Start] [Close]                         │
└─────────────────────────────────────────┘
```

---

## Color Scheme

The application uses the default tkinter/ttk theme which adapts to system theme:

**Light Theme:**
- Background: Light gray (#f0f0f0)
- Text: Black
- Selected: Blue highlight
- Borders: Gray

**Dark Theme** (if system supports):
- Background: Dark gray
- Text: White
- Selected: Blue highlight
- Borders: Dark borders

---

## Sizing & Responsiveness

### Main Window
- **Default Size:** 1200x800 pixels
- **Minimum Size:** 800x600 pixels (recommended)
- **Resizable:** Yes, all panels resize proportionally

### Panel Proportions
- **Left Panel Width:** ~40% of window
- **Right Panel Width:** ~60% of window
- **Preview Area Height:** ~40% of right panel
- **Info Area Height:** ~60% of right panel

### Dialog Windows
- **Standard Size:** 700x500 pixels
- **Resizable:** Yes
- **Modal:** Yes (blocks main window)

---

## Accessibility Features

### Keyboard Navigation
- Tab between controls
- Arrow keys in listbox
- Enter to activate buttons
- Space to toggle checkboxes

### Screen Reader Support
- All controls have labels
- Status updates in status bar
- Operation results in output text

### Visual Indicators
- Selected files highlighted
- Active controls have focus ring
- Status messages in status bar
- Operation progress in dialogs

---

## Platform Differences

### Windows
- Uses native Windows theme
- Title bar follows Windows style
- File paths use backslashes

### macOS
- Uses native macOS theme
- Title bar in window content area
- File paths use forward slashes

### Linux
- Uses GTK or Qt theme (based on system)
- Varies by desktop environment
- File paths use forward slashes

---

## UI Interaction Flow

### Typical User Flow

1. **Launch** → Main window appears
2. **Browse** → Select directory
3. **Filter** → Narrow down files
4. **Select** → Choose files to process
5. **Configure** → Set database path
6. **Execute** → Click operation button
7. **Options** → Configure in dialog
8. **Preview** → Check with dry-run
9. **Run** → Execute operation
10. **Review** → Check output
11. **Close** → Return to main window

---

This layout ensures a clean, intuitive interface for managing and processing media files efficiently.
