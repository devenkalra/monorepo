# Bug Fix: Selection and Preview Disappearing on Filter Change

## Issue
When changing the EXIF filter dropdown or volume filter, the following problems occurred:
1. The file selection highlight in the listbox would disappear
2. The preview image would disappear
3. The EXIF information would disappear

## Root Cause Analysis
Through systematic debugging, we discovered:
1. When the EXIF filter dropdown value changes, it triggers the `on_exif_filter_change` handler via `StringVar.trace`
2. The handler updates the info text widget successfully
3. **However**, after the handler completes, a spurious `on_file_select` event fires with an empty selection `()`
4. This empty selection event clears the preview and info, making everything disappear

The problem is a race condition where the combobox widget takes focus when its value changes, causing the listbox to lose its selection and fire a selection-changed event.

## Solution
The fix uses `after_idle()` to schedule selection restoration after all pending events have been processed:

### Implementation in `on_exif_filter_change()`

```python
def on_exif_filter_change(self):
    """Handle EXIF filter change - refresh info if file is selected."""
    # Guard against early initialization calls
    if not hasattr(self, 'selected_files') or not hasattr(self, 'file_listbox'):
        return
    
    # Prevent recursive calls
    if self._updating_filter:
        return
    
    # Skip if no files selected
    if not self.selected_files:
        return
    
    # Save current listbox selection indices
    current_selection = list(self.file_listbox.curselection())
    
    # If there was a selection, update info and schedule selection restore
    if current_selection:
        self._updating_filter = True
        try:
            # Update the info panel directly
            if len(self.selected_files) == 1:
                self.show_file_info(self.selected_files[0])
            
            # Use after_idle to restore selection after all events have processed
            self.root.after_idle(lambda: self._restore_selection(current_selection))
        finally:
            self._updating_filter = False

def _restore_selection(self, indices):
    """Restore listbox selection after filter change."""
    if not self.file_listbox.curselection():
        for idx in indices:
            self.file_listbox.selection_set(idx)
        
        # Manually trigger the selection event to redisplay preview/info
        self.file_listbox.event_generate('<<ListboxSelect>>')
```

## How It Works

1. **Update the info panel** with the new filter immediately
2. **Schedule selection restoration** using `after_idle()` - this runs after all pending events
3. When restoration runs:
   - Check if selection was lost (it usually is)
   - Restore the selection by calling `selection_set()` for each index
   - Trigger `<<ListboxSelect>>` event to redisplay everything

The key insight: By using `after_idle()`, we let the spurious empty selection event happen, then we restore the selection afterwards.

## Key Benefits

1. **Event Order Management**: `after_idle()` ensures our restoration happens after all other events
2. **Recursive Call Prevention**: `_updating_filter` flag prevents infinite loops
3. **Minimal Changes**: Only updates what needs updating (info text), then restores selection
4. **Robust**: Works even if Tkinter's event ordering changes

## Testing
To verify the fix:
1. Select a file to see its preview and info
2. Change the EXIF filter dropdown
3. Verify that:
   - The file remains highlighted in the listbox
   - The preview image remains visible
   - The info panel updates with the new EXIF filter
4. Try changing the volume filter and verify the same behavior

## Technical Notes
- `after_idle()` is a Tkinter method that schedules a callback to run when the event loop is idle
- The `_updating_filter` flag is essential to prevent recursive calls if the restoration triggers another filter change
- `event_generate('<<ListboxSelect>>')` manually fires the selection event, ensuring `on_file_select` runs and restores the preview/info display
