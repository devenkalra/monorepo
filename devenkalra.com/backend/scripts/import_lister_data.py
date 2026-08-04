"""
Import vacation_list + asset_manager data from a lister SQLite DB.

Safe for production: only writes vacation_list_* and asset_manager_* tables
(and copies files under MEDIA_ROOT/ass_photos/). Does not replace db.sqlite3
and does not touch core/blog/notes/auth/analytics.

Usage (inside devenkalra container):

  python scripts/import_lister_data.py \\
      --source /app/_import/lister.sqlite3 \\
      --media-source /app/_import/lister_media \\
      --clear

Prefer the host wrapper for prod:

  ./scripts/sync_devenkalra_lister_data.sh --source ... --media ...
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction

from vacation_list.models import VacCategory, VacTag, VacItem, VacList, VacListItem
from asset_manager.models import (
    AssetCategory, AssetTag, AssetArea, AssetItem, AssetPhoto,
)


def fetchall(conn, sql, params=()):
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def clear_target():
    print('Clearing existing vacation_list / asset_manager rows…')
    AssetPhoto.objects.all().delete()
    AssetItem.objects.all().delete()
    AssetArea.objects.all().delete()
    AssetTag.objects.all().delete()
    AssetCategory.objects.all().delete()
    VacListItem.objects.all().delete()
    VacList.objects.all().delete()
    VacItem.objects.all().delete()
    VacTag.objects.all().delete()
    VacCategory.objects.all().delete()


def reset_sqlite_sequences(table_names):
    if connection.vendor != 'sqlite':
        return
    with connection.cursor() as cursor:
        for table in table_names:
            cursor.execute(f'SELECT MAX(id) FROM {table}')
            max_id = cursor.fetchone()[0]
            cursor.execute('DELETE FROM sqlite_sequence WHERE name=%s', [table])
            if max_id is not None:
                cursor.execute(
                    'INSERT INTO sqlite_sequence(name, seq) VALUES (%s, %s)',
                    [table, max_id],
                )


def copy_media_file(rel_path: str, media_source: Path, media_root: Path) -> str | None:
    if not rel_path:
        return None
    rel = rel_path.replace('\\', '/').lstrip('/')
    src = media_source / rel
    if not src.is_file():
        # try basename under ass_photos/
        src = media_source / 'ass_photos' / Path(rel).name
    if not src.is_file():
        print(f'  WARN missing media: {rel_path}')
        return None
    dest = media_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(src, dest)
    return rel


def import_vacation(conn):
    print('Importing vacation_list…')
    cats = fetchall(conn, 'SELECT * FROM listmanager_category ORDER BY id')
    VacCategory.objects.bulk_create([
        VacCategory(
            id=r['id'],
            name=r['name'] or '',
            created_at=r['created_at'],
            modified_on=r['modified_on'],
        )
        for r in cats
    ])
    print(f'  VacCategory: {len(cats)}')

    tags = fetchall(conn, 'SELECT * FROM listmanager_tag ORDER BY id')
    VacTag.objects.bulk_create([
        VacTag(
            id=r['id'],
            name=r['name'] or '',
            created_at=r['created_at'],
            modified_on=r['modified_on'],
        )
        for r in tags
    ])
    print(f'  VacTag: {len(tags)}')

    items = fetchall(conn, 'SELECT * FROM listmanager_item ORDER BY id')
    VacItem.objects.bulk_create([
        VacItem(
            id=r['id'],
            name=r['name'] or '',
            name_group=r['name_group'] or '',
            description=r['description'],
            category_id=r['category_id'],
            created_at=r['created_at'],
            modified_on=r['modified_on'],
        )
        for r in items
    ])
    print(f'  VacItem: {len(items)}')

    Through = VacItem.tags.through
    m2m = fetchall(conn, 'SELECT item_id, tag_id FROM listmanager_item_tags')
    Through.objects.bulk_create([
        Through(vacitem_id=r['item_id'], vactag_id=r['tag_id'])
        for r in m2m
    ], ignore_conflicts=True)
    print(f'  VacItem↔VacTag: {len(m2m)}')

    lists = fetchall(conn, 'SELECT * FROM listmanager_list ORDER BY id')
    VacList.objects.bulk_create([
        VacList(
            id=r['id'],
            name=r['name'] or '',
            created_at=r['created_at'],
            modified_on=r['modified_on'],
        )
        for r in lists
    ])
    print(f'  VacList: {len(lists)}')

    ListThrough = VacList.initial_tags.through
    init_tags = fetchall(conn, 'SELECT list_id, tag_id FROM listmanager_list_initial_tags')
    ListThrough.objects.bulk_create([
        ListThrough(vaclist_id=r['list_id'], vactag_id=r['tag_id'])
        for r in init_tags
    ], ignore_conflicts=True)
    print(f'  VacList.initial_tags: {len(init_tags)}')

    list_items = fetchall(conn, 'SELECT * FROM listmanager_listitem ORDER BY id')
    # Deduplicate by (item_id, in_list_id) keeping first id
    seen = set()
    objs = []
    skipped = 0
    for r in list_items:
        key = (r['item_id'], r['in_list_id'])
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        objs.append(VacListItem(
            id=r['id'],
            item_id=r['item_id'],
            in_list_id=r['in_list_id'],
            need=bool(r['need']),
            done=bool(r['done']),
            created_at=r['created_at'],
            modified_on=r['modified_on'],
        ))
    VacListItem.objects.bulk_create(objs)
    print(f'  VacListItem: {len(objs)} (skipped {skipped} duplicate item/list pairs)')


def import_assets(conn, media_source: Path, media_root: Path):
    print('Importing asset_manager…')
    cats = fetchall(conn, 'SELECT * FROM listmanager_assetcategory ORDER BY id')
    AssetCategory.objects.bulk_create([
        AssetCategory(
            id=r['id'],
            name=r['name'] or '',
            description=r['description'] or '',
            created_at=r['created_at'],
            modified_at=r['modified_at'],
        )
        for r in cats
    ])
    print(f'  AssetCategory: {len(cats)}')

    tags = fetchall(conn, 'SELECT * FROM listmanager_assettag ORDER BY id')
    AssetTag.objects.bulk_create([
        AssetTag(
            id=r['id'],
            name=r['name'] or '',
            created_at=r['created_at'],
            modified_at=r['modified_at'],
        )
        for r in tags
    ])
    print(f'  AssetTag: {len(tags)}')

    areas = fetchall(conn, 'SELECT * FROM listmanager_assarea ORDER BY id')
    # Pass 1: create without parents
    AssetArea.objects.bulk_create([
        AssetArea(
            id=r['id'],
            name=r['name'] or '',
            description=r['description'] or '',
            locator_code=r['locator_code'],
            locator_type=r['locator_type'] or '',
            category_id=r['category_id'],
            parent_area_id=None,
            created_at=r['created_at'],
            modified_at=r['modified_at'],
        )
        for r in areas
    ])
    # Pass 2: set parents
    for r in areas:
        if r['parent_area_id']:
            AssetArea.objects.filter(pk=r['id']).update(parent_area_id=r['parent_area_id'])
    print(f'  AssetArea: {len(areas)}')

    AreaThrough = AssetArea.tags.through
    area_tags = fetchall(conn, 'SELECT assarea_id, assettag_id FROM listmanager_assarea_tags')
    AreaThrough.objects.bulk_create([
        AreaThrough(assetarea_id=r['assarea_id'], assettag_id=r['assettag_id'])
        for r in area_tags
    ], ignore_conflicts=True)

    # Lister boxes become nested AssetAreas (containership via parent_area only).
    boxes = fetchall(conn, 'SELECT * FROM listmanager_assbox ORDER BY id')
    box_to_area = {}
    next_area_id = max([r['id'] for r in areas], default=0) + 1
    remaining = list(boxes)
    converted_boxes = []
    while remaining:
        still = []
        progress = False
        for r in remaining:
            parent_box_id = r['parent_box_id']
            area_id = r['area_id']
            if parent_box_id and area_id:
                print(f'  WARN box {r["id"]} had both parent_box and area; keeping parent_box')
                area_id = None
            if parent_box_id and parent_box_id not in box_to_area:
                still.append(r)
                continue
            parent_area_id = box_to_area[parent_box_id] if parent_box_id else area_id
            new_id = next_area_id
            next_area_id += 1
            converted_boxes.append(AssetArea(
                id=new_id,
                name=r['name'] or '',
                description=r['description'] or '',
                locator_code=r['locator_code'],
                locator_type=r['locator_type'] or '',
                category_id=r['category_id'],
                parent_area_id=parent_area_id,
                created_at=r['created_at'],
                modified_at=r['modified_at'],
            ))
            box_to_area[r['id']] = new_id
            progress = True
        if not progress:
            for r in still:
                new_id = next_area_id
                next_area_id += 1
                converted_boxes.append(AssetArea(
                    id=new_id,
                    name=r['name'] or '',
                    description=r['description'] or '',
                    locator_code=r['locator_code'],
                    locator_type=r['locator_type'] or '',
                    category_id=r['category_id'],
                    parent_area_id=r['area_id'],
                    created_at=r['created_at'],
                    modified_at=r['modified_at'],
                ))
                box_to_area[r['id']] = new_id
            break
        remaining = still
    AssetArea.objects.bulk_create(converted_boxes)
    print(f'  AssetArea from boxes: {len(converted_boxes)}')

    box_tags = fetchall(conn, 'SELECT assbox_id, assettag_id FROM listmanager_assbox_tags')
    AreaThrough.objects.bulk_create([
        AreaThrough(assetarea_id=box_to_area[r['assbox_id']], assettag_id=r['assettag_id'])
        for r in box_tags
        if r['assbox_id'] in box_to_area
    ], ignore_conflicts=True)

    items = fetchall(conn, 'SELECT * FROM listmanager_assitem ORDER BY id')
    asset_items = []
    for r in items:
        box_id = r['box_id']
        area_id = r['area_id']
        if box_id:
            area_id = box_to_area.get(box_id)
            if area_id is None:
                print(f'  WARN item {r["id"]}: unknown box_id={box_id}; leaving unlocated')
        asset_items.append(AssetItem(
            id=r['id'],
            name=r['name'] or '',
            description=r['description'] or '',
            locator_code=r['locator_code'],
            locator_type=r['locator_type'] or '',
            category_id=r['category_id'],
            area_id=area_id,
            created_at=r['created_at'],
            modified_at=r['modified_at'],
        ))
    AssetItem.objects.bulk_create(asset_items)
    print(f'  AssetItem: {len(asset_items)}')

    ItemThrough = AssetItem.tags.through
    item_tags = fetchall(conn, 'SELECT assitem_id, assettag_id FROM listmanager_assitem_tags')
    ItemThrough.objects.bulk_create([
        ItemThrough(assetitem_id=r['assitem_id'], assettag_id=r['assettag_id'])
        for r in item_tags
    ], ignore_conflicts=True)

    # Remap Photo GFK content types (lister boxes → AssetArea ids via box_to_area)
    src_cts = {
        row['model']: row['id']
        for row in fetchall(
            conn,
            "SELECT id, model FROM django_content_type WHERE app_label='listmanager'",
        )
    }
    area_ct_id = ContentType.objects.get_for_model(AssetArea).id
    item_ct_id = ContentType.objects.get_for_model(AssetItem).id
    model_map = {
        'assarea': area_ct_id,
        'assbox': area_ct_id,
        'assitem': item_ct_id,
    }
    src_id_to_dest_ct = {
        src_cts[model]: dest_ct
        for model, dest_ct in model_map.items()
        if model in src_cts
    }
    box_src_ct = src_cts.get('assbox')

    photos = fetchall(conn, 'SELECT * FROM listmanager_photo ORDER BY id')
    photo_objs = []
    for r in photos:
        dest_ct = src_id_to_dest_ct.get(r['content_type_id'])
        if not dest_ct:
            print(f'  WARN skip photo {r["id"]}: unknown content_type_id={r["content_type_id"]}')
            continue
        object_id = r['object_id']
        if box_src_ct is not None and r['content_type_id'] == box_src_ct:
            object_id = box_to_area.get(object_id)
            if object_id is None:
                print(f'  WARN skip photo {r["id"]}: unknown box object_id={r["object_id"]}')
                continue
        rel = copy_media_file(r['image'], media_source, media_root)
        if not rel:
            continue
        photo_objs.append(AssetPhoto(
            id=r['id'],
            image=rel,
            description=r['description'] or '',
            content_type_id=dest_ct,
            object_id=object_id,
            created_at=r['created_at'],
            modified_at=r['modified_at'],
        ))
    AssetPhoto.objects.bulk_create(photo_objs)
    print(f'  AssetPhoto: {len(photo_objs)} / {len(photos)}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--source',
        type=Path,
        default=BASE_DIR / '_import' / 'lister.sqlite3',
        help='Path to lister db.sqlite3',
    )
    parser.add_argument(
        '--media-source',
        type=Path,
        default=BASE_DIR / '_import' / 'lister_media',
        help='Directory containing ass_photos/ (lister MEDIA_ROOT)',
    )
    parser.add_argument(
        '--clear',
        action='store_true',
        help='Delete existing vacation_list/asset_manager rows before import',
    )
    args = parser.parse_args()

    if not args.source.is_file():
        raise SystemExit(f'Source DB not found: {args.source}')

    from django.conf import settings
    media_root = Path(settings.MEDIA_ROOT)

    conn = sqlite3.connect(str(args.source))
    conn.row_factory = sqlite3.Row

    with transaction.atomic():
        if args.clear:
            clear_target()
        import_vacation(conn)
        import_assets(conn, args.media_source, media_root)

    reset_sqlite_sequences([
        'vacation_list_vaccategory',
        'vacation_list_vactag',
        'vacation_list_vacitem',
        'vacation_list_vaclist',
        'vacation_list_vaclistitem',
        'asset_manager_assetcategory',
        'asset_manager_assettag',
        'asset_manager_assetarea',
        'asset_manager_assetitem',
        'asset_manager_assetphoto',
    ])

    print('Done.')
    print(
        'Counts:',
        VacCategory.objects.count(), 'cats,',
        VacItem.objects.count(), 'vac items,',
        VacListItem.objects.count(), 'list items,',
        AssetItem.objects.count(), 'asset items,',
        AssetPhoto.objects.count(), 'photos',
    )


if __name__ == '__main__':
    main()
