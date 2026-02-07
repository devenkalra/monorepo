# Configuration System

The Media Processor GUI now saves your settings automatically.

## Configuration File

**Location:** `media_processor_config.yaml` (in the same directory as the app)

**Auto-created:** The file is created when you click "Save Settings"

## Saved Settings

The following settings are saved:
- Current directory path
- Database path
- File type filters (Images/Videos/Other checkboxes)
- Window size and position

## Usage

### Saving Settings
1. Configure your preferences (directory, database, filters, window size)
2. Click the **"Save Settings"** button in the bottom-right corner
3. Settings are saved to `media_processor_config.yaml`

### Loading Settings
Settings are automatically loaded when the application starts.

### Manual Editing
You can manually edit `media_processor_config.yaml` if needed.

See `media_processor_config.yaml.example` for the format.

## Example Config

```yaml
current_directory: /home/user/Pictures
database_path: /home/user/media.db
show_images: true
show_videos: true
show_other: false
window_geometry: 1200x800+100+100
```

## Notes

- The config file is in `.gitignore` (won't be committed to git)
- Invalid paths are ignored on load
- Missing config file is not an error (uses defaults)
- Config is loaded after UI setup
