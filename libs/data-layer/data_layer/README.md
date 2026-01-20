Design
======
Django api server to server file catalog

# Models

# Urls

## Query a file

```
List all files (Paginated) 
    GET /api/files/

Search for a file by name (Fuzzy) 
    GET /api/files/?search=holiday_photo (Finds "holiday_photo.jpg" or files in "/backup/holiday_photos/")

Find all duplicates (by Hash) 
    GET /api/files/?hash=a1b2c3d4e5...

Filter by Volume 
    GET /api/files/?volume=External_HDD

Find largest files (Sort by Size Descending) 
    GET /api/files/?ordering=-size
```

## Execute a general command
```
/api/files/command=<command>

E.g
/api/files/command=catalog /mnt/photo SYN_PHOTO start_dir="cat test"
```