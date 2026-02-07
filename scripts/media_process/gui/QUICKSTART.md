# Quick Start Guide - Media Processor GUI

Get started with the Media Processor GUI in 5 minutes!

## Prerequisites Check

Before starting, ensure you have:
- ✅ Python 3 installed: `python3 --version`
- ✅ Tkinter installed: `python3 -c "import tkinter"`
- ✅ Pillow installed: `pip3 install Pillow`
- ✅ ExifTool installed: `exiftool -ver`

**Optional (for HEIC/HEIF and RAW formats):**
- ⚙️ pillow-heif: `pip3 install pillow-heif`
- ⚙️ rawpy: `pip3 install rawpy numpy`

## Step 1: Launch the Application

```bash
cd /home/ubuntu/monorepo/scripts/media_process/gui
./run_media_processor.sh
```

Or run directly:
```bash
python3 media_processor_app.py
```

## Step 2: Browse to Your Media Directory

1. Click the **"Browse..."** button at the top
2. Navigate to a directory containing images or videos
3. Click **"Select Folder"**
4. Files will load automatically

**Tip:** Use a test directory with a few files for your first try!

## Step 3: Configure Your Database

1. Find the "Database:" field in the bottom panel
2. Click **"Browse..."** next to it
3. Either:
   - Select an existing `.db` file, OR
   - Type a new filename like `my_media.db` to create one

**Tip:** The database stores metadata about your files for quick searching and duplicate detection.

## Step 4: Select Files

1. Click on a file in the left panel to select it
2. The preview and info will appear on the right
3. To select multiple files:
   - Hold **Ctrl** (or **Cmd** on Mac) and click files
   - Or hold **Shift** and click to select a range

## Step 5: Try an Operation (Dry Run)

Let's try indexing files with dry-run mode:

1. Select some image files
2. Click **"Index Media Files"** at the bottom
3. In the dialog:
   - Set Volume name (e.g., "TestLibrary")
   - ✅ Check "Dry run (preview only)"
   - Click **"Start"**
4. Watch the output panel to see what would happen

**No changes were made** because we used dry-run mode!

## Common First Tasks

### Task 1: Index Your Media Library

**Purpose:** Add files to the database with metadata

1. Select files or browse to directory
2. Click **"Index Media Files"**
3. Set volume name: `"MyPhotos"`
4. Uncheck dry-run (only after testing!)
5. Click **"Start"**

**Result:** Files are added to database with:
- File paths and metadata
- EXIF data (for images)
- Video metadata (for videos)
- Thumbnails

### Task 2: Find and Remove Duplicates

**Purpose:** Identify and move duplicate files

1. Specify your database
2. Click **"Manage Duplicates"**
3. Set destination: `/path/to/duplicates`
4. Choose action: **Move** or **Copy**
5. ✅ Check "Dry run" first
6. Click **"Start"**

**Result:** Duplicate files are identified by content hash and moved/copied to the destination.

### Task 3: Add Location Data to Photos

**Purpose:** Add GPS and location metadata to images

1. Select image files
2. Click **"Apply EXIF"**
3. Enter place: `"New York, NY, USA"`
4. Add keywords: `"vacation, 2024, summer"`
5. ✅ Check "Dry run" first
6. Click **"Start"**

**Result:** Images get GPS coordinates and location metadata from the place name.

### Task 4: Organize Files by Moving Them

**Purpose:** Move files to new location and update database

1. Select files to move
2. Click **"Move Media Files"**
3. Set destination: `/path/to/organized/photos`
4. Set volume: `"OrganizedLibrary"`
5. ✅ Check "Dry run" first
6. Click **"Start"**

**Result:** Files are moved and database is updated with new paths.

## Tips for Success

### 1. Always Test with Dry Run First
- Every operation has a "Dry run" checkbox
- Enable it to see what will happen WITHOUT making changes
- Review the output carefully
- Run again without dry-run when ready

### 2. Back Up Your Database
Before major operations:
```bash
cp my_media.db my_media.db.backup
```

### 3. Start Small
- Test with a small directory first (10-20 files)
- Once comfortable, scale up to larger collections
- Use filters to work with subsets

### 4. Use Filters Effectively
- Type in filter box to search filenames
- Uncheck file types you don't want to see
- Click "Refresh" after changing filters

### 5. Check File Info Before Operations
- Select a single file to see its info
- Review EXIF data in the info panel
- Verify file details match your expectations

## Common Workflows

### Workflow 1: Import New Photos
1. Browse to import directory
2. Filter to show only images
3. Select all images (Ctrl+A in listbox)
4. Index Media Files → Set volume → Run
5. Apply EXIF → Add location/keywords → Run
6. Move Media Files → Organize into library → Run

### Workflow 2: Clean Up Duplicates
1. Manage Duplicates → Set source directory
2. Set destination for dupes
3. Enable "Media files only"
4. Run with dry-run first
5. Review output
6. Run without dry-run

### Workflow 3: Update Existing Files
1. Browse to directory with indexed files
2. Select files to update
3. Apply EXIF → Add new tags/location
4. Enable "Update database" checkbox
5. Run operation

## Keyboard Shortcuts

File List:
- **Ctrl+A**: Select all (platform-specific)
- **Ctrl+Click**: Add/remove from selection
- **Shift+Click**: Select range
- **Up/Down**: Navigate files

## Troubleshooting Quick Fixes

**Problem:** No files appear in list
- **Fix:** Check filters (Images/Videos/Other checkboxes)
- **Fix:** Click "Refresh" button
- **Fix:** Verify directory has media files

**Problem:** Preview shows "Preview error"
- **Fix:** Check Pillow is installed: `pip3 install Pillow`
- **Fix:** Verify file format is supported

**Problem:** EXIF data not showing
- **Fix:** Check exiftool is installed: `exiftool -ver`
- **Fix:** File may not have EXIF data

**Problem:** Operation button does nothing
- **Fix:** Check files are selected
- **Fix:** Verify database path is set (if required)

**Problem:** Operation fails
- **Fix:** Check output panel for error messages
- **Fix:** Verify parent scripts exist: `ls ../*.py`
- **Fix:** Check file permissions

## Next Steps

Now that you've completed the quick start:

1. ✅ Explored the interface
2. ✅ Tried operations with dry-run
3. ✅ Understand the basic workflow

Continue with:
- Read [README.md](README.md) for detailed feature documentation
- Review [INSTALL.md](INSTALL.md) for advanced setup
- Check parent script documentation for operation details
- Start organizing your real media collection!

## Getting Help

If you encounter issues:
1. Check the output panel in operation dialogs
2. Review the [README.md](README.md) troubleshooting section
3. Verify all prerequisites are installed
4. Test with a small sample directory first

## Safe Practices

Before processing important files:
- ✅ Back up your data
- ✅ Back up your database
- ✅ Test with dry-run mode
- ✅ Start with a small sample
- ✅ Verify results before scaling up

---

**Ready to process your media? Launch the app and start exploring!** 🎉
