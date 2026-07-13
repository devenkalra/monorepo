#!/usr/bin/env python3
import sqlite3
import sys

db = sys.argv[1] if len(sys.argv) > 1 else 'files.db'
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print('TABLES:', tables)
for t in tables:
    cur.execute(f'PRAGMA table_info({t})')
    cols = cur.fetchall()
    print(f'\n{t}:')
    for c in cols:
        print(' ', c)
    cur.execute(f'SELECT COUNT(*) FROM {t}')
    print('  count:', cur.fetchone()[0])

if 'files' in tables:
    cur.execute('PRAGMA table_info(files)')
    file_cols = [c[1] for c in cur.fetchall()]
    if 'volume' in file_cols:
        cur.execute('SELECT volume, COUNT(*) FROM files GROUP BY volume')
        print('\nVolumes in files:', cur.fetchall())
    path_col = 'fullpath' if 'fullpath' in file_cols else 'relpath'
    cur.execute(f'SELECT {path_col} FROM files LIMIT 5')
    print(f'\nSample {path_col}:')
    for r in cur.fetchall():
        print(' ', r[0])
    if path_col == 'fullpath':
        prefixes = {}
        cur.execute('SELECT fullpath FROM files')
        for (fp,) in cur.fetchall():
            # first 3 path segments as prefix hint
            parts = fp.replace('\\', '/').split('/')
            key = '/'.join(parts[:3]) if len(parts) >= 3 else fp
            prefixes[key] = prefixes.get(key, 0) + 1
        print('\nPath prefix counts (top 10):')
        for k, v in sorted(prefixes.items(), key=lambda x: -x[1])[:10]:
            print(f'  {k}: {v}')
        cur.execute("SELECT COUNT(*) FROM files WHERE fullpath NOT LIKE '/mnt/photo%'")
        print('\nNon /mnt/photo files:', cur.fetchone()[0])

if 'skipped_files' in tables:
    cur.execute('PRAGMA table_info(skipped_files)')
    sk_cols = [c[1] for c in cur.fetchall()]
    path_col = 'fullpath' if 'fullpath' in sk_cols else 'relpath'
    cur.execute(f'SELECT {path_col} FROM skipped_files LIMIT 3')
    print(f'\nSample skipped {path_col}:', [r[0] for r in cur.fetchall()])

if 'removed_duplicates' in tables:
    cur.execute('PRAGMA table_info(removed_duplicates)')
    rd_cols = [c[1] for c in cur.fetchall()]
    print('\nremoved_duplicates cols:', rd_cols)
    if 'original_fullpath' in rd_cols:
        cur.execute('SELECT original_fullpath, kept_fullpath FROM removed_duplicates LIMIT 3')
        print('Sample removed:', cur.fetchall())

cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='files'")
row = cur.fetchone()
if row:
    print('\nfiles CREATE:', row[0][:500])

print('\nIndexes:')
for name, sql in cur.fetchall():
    print(f'  {name}: {sql}')
