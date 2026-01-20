import meilisearch, os
MEILI_URL = "https://meili.bldrdojo.com"
MEILI_API_KEY = "DKKeyDKKeyDkKeyDKKey"  # The master key you set when creating the container
INDEX_NAME = "files_catalog"

FILES_INDEX = INDEX_NAME
FOLDERS_INDEX = "catalog_folders"
client = meilisearch.Client(MEILI_URL, MEILI_API_KEY)

def update_filterable_attributes(index, attributes):
    idx = client.index(index)
    task = idx.update_filterable_attributes(attributes)
    client.wait_for_task(task.task_uid)

def update_sortable_attributes(index, attributes):
    idx = client.index(index)
    task = idx.update_sortable_attributes(attributes)
    client.wait_for_task(task.task_uid)

update_sortable_attributes(INDEX_NAME, ["id", "extension", "size", "created", "path", "name", "volume"])


update_filterable_attributes(INDEX_NAME, [
        'name',
        'extension',
        'exif.camera_make',
        'exif.camera_model',
        'exif.exposure_time',
        'exif.aperture',
        'created',
        'size',
        'path',
        'volume',
        'hash',
        'exif.width',
        'exif.height',
        'mime',
        'exif.latitude',
        'exif.longitude',
        'exif.altitude',
        'relative_path',
    ])

update_filterable_attributes(FOLDERS_INDEX, [
    "parent_dir",
    "volume",
    "dir",
    "depth",
    "name",
])

update_sortable_attributes(FOLDERS_INDEX, [
    "name",
    "file_count",
    "child_count",
    "depth",
])
    # ✅ folders index must have parent_dir filterable for Explorer

