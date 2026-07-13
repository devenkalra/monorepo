# ==============================================================================
# CONFIGURATION
# ==============================================================================
$SQLiteExe   = "C:\path\to\sqlite3.exe"             # Path to your sqlite3 binary
$SourceDB    = "C:\path\to\catalog.db"              # Your active live catalog file
$BackupDir   = "D:\backups\catalog_differential"    # Where you want to save backups

# Generate dynamic timestamps for naming files uniquely
$Timestamp   = Get-Date -Format "yyyyMMdd_HHmmss"
$DateToday   = Get-Date -Format "yyyy-MM-dd"

# Ensure target directories exist cleanly
if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir -Force }

# Change context location to backup directory to streamline compression execution
Push-Location $BackupDir

Write-Host "Starting Split-Differential SQLite backup cycle at $(Get-Date)..." -ForegroundColor Cyan

# ==============================================================================
# STEP 1: EXSTRUCT & BACKUP METADATA (TEXT ONLY)
# ==============================================================================
Write-Host "Staging transaction-consistent online copy via VACUUM INTO..." -ForegroundColor Yellow
$TempMetaDB = "temp_metadata_$Timestamp.db"

# Safely copy the database online without corrupting live file pages
& $SQLiteExe $SourceDB "VACUUM INTO '$TempMetaDB';"

Write-Host "Stripping heavy image rows out of the metadata baseline database..." -ForegroundColor Yellow
# Purge the heavy visual rows to leave behind a lightweight plain-text catalog structure
& $SQLiteExe $TempMetaDB "DROP TABLE thumbnails;"

Write-Host "Compressing metadata into a secure tarball..." -ForegroundColor Yellow
$MetaTarName = "metadata_backup_$Timestamp.tar.gz"
# Native Windows tar bypasses standard .NET 2GB stream thresholds smoothly
tar -czf $MetaTarName $TempMetaDB
Remove-Item $TempMetaDB -ErrorAction SilentlyContinue

# ==============================================================================
# STEP 2: DAILY INCREMENTAL THUMBNAIL PATCH (BLOB ASSETS)
# ==============================================================================
Write-Host "Compiling daily incremental image BLOB patch file..." -ForegroundColor Yellow
$TempPatchDB = "temp_patch_$Timestamp.db"

# Query string isolates new entries utilizing your indexed created_at timestamp
# This clones only rows created in the last 24 hours directly into an independent file layout
$SQLPatchQuery = @"
ATTACH DATABASE '$TempPatchDB' AS patch;
CREATE TABLE patch.thumbnails AS 
SELECT id, file_id, thumbnail_data, thumbnail_width, thumbnail_height, created_at 
FROM thumbnails 
WHERE created_at >= datetime('now', '-1 day');
"@

& $SQLiteExe $SourceDB $SQLPatchQuery

# Check if any new thumbnails were actually extracted by evaluating file footprint sizes
if ((Get-Item $TempPatchDB).Length -gt 16384) { # Standard empty SQLite file baseline is ~16KB
    Write-Host "New thumbnails discovered! Packing incremental patch..." -ForegroundColor Green
    $PatchTarName = "thumbnail_patch_$DateToday.tar.gz"
    tar -czf $PatchTarName $TempPatchDB
} else {
    Write-Host "No new thumbnails generated in the last 24 hours. Skipping patch file generation." -ForegroundColor Gray
}

Remove-Item $TempPatchDB -ErrorAction SilentlyContinue

Pop-Location
Write-Host "Backup strategy successfully processed!" -ForegroundColor Green