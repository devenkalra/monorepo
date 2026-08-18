import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';

async function api(path, { token, method = 'GET' } = {}) {
  const headers = { Accept: 'application/json' };
  if (token) headers.Authorization = `Token ${token}`;
  const res = await fetch(`/api/audio/${path}`, {
    method,
    headers,
    credentials: 'omit',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return '';
  const total = Math.max(0, Math.round(Number(seconds)));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatBpm(value) {
  if (value == null || value === '') return '';
  const n = Number(value);
  if (Number.isNaN(n)) return '';
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, '');
}

function asList(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.results)) return data.results;
  return [];
}

const SORT_COLUMNS = [
  { key: 'has_cover', label: '', aria: 'Cover' },
  { key: 'title', label: 'Title' },
  { key: 'artist', label: 'Artist' },
  { key: 'composer', label: 'Composer' },
  { key: 'genre', label: 'Genre' },
  { key: 'year', label: 'Year' },
  { key: 'bpm', label: 'BPM' },
  { key: 'album', label: 'Album' },
  { key: 'folder', label: 'Folder' },
  { key: 'duration_seconds', label: 'Time' },
];

function sortValue(row, key) {
  if (key === 'title') return (row.title || row.filename || '').toLowerCase();
  if (key === 'folder') {
    return `${row.folder_label || ''} / ${row.parent || ''}`.toLowerCase();
  }
  if (key === 'has_cover') return row.has_cover ? 1 : 0;
  if (key === 'year' || key === 'bpm' || key === 'duration_seconds') {
    const n = Number(row[key]);
    return Number.isFinite(n) ? n : null;
  }
  return (row[key] ?? '').toString().toLowerCase();
}

function compareTracks(a, b, key, dir) {
  const av = sortValue(a, key);
  const bv = sortValue(b, key);
  const emptyA = av == null || av === '';
  const emptyB = bv == null || bv === '';
  if (emptyA && emptyB) return 0;
  if (emptyA) return 1;
  if (emptyB) return -1;
  const cmp = typeof av === 'number' && typeof bv === 'number'
    ? av - bv
    : String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: 'base' });
  return dir === 'asc' ? cmp : -cmp;
}

function SortHeader({ column, sort, onSort }) {
  const active = sort.key === column.key;
  const arrow = active ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : '';
  return (
    <th aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button
        type="button"
        className={`music-lib-sort-btn${active ? ' is-active' : ''}`}
        aria-label={column.aria || `Sort by ${column.label}`}
        onClick={() => onSort(column.key)}
      >
        {column.label}{arrow}
      </button>
    </th>
  );
}

export function MusicLibraryApp() {
  const { token, isAuthenticated, user, openSocialLoginModal } = useAuth();
  const [tracks, setTracks] = useState([]);
  const [meta, setMeta] = useState({
    folders: [], artists: [], composers: [], genres: [], albums: [], years: [], parents: [], track_count: 0,
  });
  const [q, setQ] = useState('');
  const [qDebounced, setQDebounced] = useState('');
  const [artist, setArtist] = useState('');
  const [composer, setComposer] = useState('');
  const [genre, setGenre] = useState('');
  const [album, setAlbum] = useState('');
  const [year, setYear] = useState('');
  const [parent, setParent] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [indexMsg, setIndexMsg] = useState('');
  const [currentId, setCurrentId] = useState(null);
  const [sort, setSort] = useState({ key: 'title', dir: 'asc' });
  const audioRef = useRef(null);

  const load = useCallback(async () => {
    if (!token) return;
    setBusy(true);
    setError('');
    try {
      const params = new URLSearchParams();
      params.set('page_size', '500');
      if (qDebounced.trim()) params.set('q', qDebounced.trim());
      if (artist) params.set('artist', artist);
      if (composer) params.set('composer', composer);
      if (genre) params.set('genre', genre);
      if (album) params.set('album', album);
      if (year) params.set('year', year);
      if (parent) params.set('parent', parent);
      const [list, info] = await Promise.all([
        api(`tracks/?${params.toString()}`, { token }),
        api('meta/', { token }),
      ]);
      setTracks(asList(list));
      setMeta(info);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, [token, qDebounced, artist, composer, genre, album, year, parent]);

  useEffect(() => {
    const timer = setTimeout(() => setQDebounced(q), 250);
    return () => clearTimeout(timer);
  }, [q]);

  useEffect(() => {
    load();
  }, [load]);

  const sortedTracks = useMemo(
    () => [...tracks].sort((a, b) => compareTracks(a, b, sort.key, sort.dir)),
    [tracks, sort],
  );

  const current = useMemo(
    () => sortedTracks.find((row) => row.id === currentId) || null,
    [sortedTracks, currentId],
  );

  const toggleSort = (key) => {
    setSort((prev) => (
      prev.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: 'asc' }
    ));
  };

  const playAt = (index) => {
    const row = sortedTracks[index];
    if (!row) return;
    setCurrentId(row.id);
  };

  const playNext = () => {
    const idx = sortedTracks.findIndex((row) => row.id === currentId);
    if (idx >= 0 && idx < sortedTracks.length - 1) playAt(idx + 1);
  };

  const playPrev = () => {
    const idx = sortedTracks.findIndex((row) => row.id === currentId);
    if (idx > 0) playAt(idx - 1);
  };

  const reindex = async () => {
    setIndexMsg('');
    try {
      const counts = await api('reindex/', { token, method: 'POST' });
      setIndexMsg(
        `Indexed ${counts.scanned} files (${counts.upserted} updated, ${counts.covers || 0} covers, ${counts.removed} removed).`,
      );
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="music-lib">
        <p className="music-lib-hint">Sign in to browse and play the library.</p>
        <button type="button" className="editorial-button" onClick={() => openSocialLoginModal()}>
          Sign in
        </button>
      </div>
    );
  }

  return (
    <div className="music-lib">
      <div className="music-lib-toolbar">
        <label className="music-lib-search">
          <span>Search</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Title, artist, composer, genre"
          />
        </label>
        <label>
          <span>Folder</span>
          <select value={parent} onChange={(e) => setParent(e.target.value)}>
            <option value="">All folders</option>
            {(meta.parents || []).map((row) => {
              const name = typeof row === 'string' ? row : row.name;
              const count = typeof row === 'string' ? null : row.track_count;
              return (
                <option key={name} value={name}>
                  {count != null ? `${name} (${count})` : name}
                </option>
              );
            })}
          </select>
        </label>
        <label>
          <span>Artist</span>
          <select value={artist} onChange={(e) => setArtist(e.target.value)}>
            <option value="">All artists</option>
            {(meta.artists || []).map((row) => (
              <option key={row} value={row}>{row}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Composer</span>
          <select value={composer} onChange={(e) => setComposer(e.target.value)}>
            <option value="">All composers</option>
            {(meta.composers || []).map((row) => (
              <option key={row} value={row}>{row}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Genre</span>
          <select value={genre} onChange={(e) => setGenre(e.target.value)}>
            <option value="">All genres</option>
            {(meta.genres || []).map((row) => (
              <option key={row} value={row}>{row}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Year</span>
          <select value={year} onChange={(e) => setYear(e.target.value)}>
            <option value="">All years</option>
            {(meta.years || []).map((row) => (
              <option key={row} value={row}>{row}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Album</span>
          <select value={album} onChange={(e) => setAlbum(e.target.value)}>
            <option value="">All albums</option>
            {(meta.albums || []).map((row) => (
              <option key={row} value={row}>{row}</option>
            ))}
          </select>
        </label>
        {user?.role === 'superuser' && (
          <button type="button" className="editorial-button" onClick={reindex} disabled={busy}>
            Refresh index
          </button>
        )}
      </div>
      {indexMsg && <p className="music-lib-hint">{indexMsg}</p>}
      {error && <p className="music-lib-error">{error}</p>}
      <p className="music-lib-hint">
        {busy ? 'Loading…' : `${sortedTracks.length} track${sortedTracks.length === 1 ? '' : 's'}`}
        {meta.folders?.length === 0 ? ' — no NAS folders configured yet.' : ''}
      </p>
      <div className="music-lib-table-wrap">
        <table className="music-lib-table">
          <thead>
            <tr>
              {SORT_COLUMNS.map((column) => (
                <SortHeader key={column.key} column={column} sort={sort} onSort={toggleSort} />
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedTracks.map((row, index) => (
              <tr
                key={row.id}
                className={row.id === currentId ? 'is-playing' : ''}
                onClick={() => playAt(index)}
              >
                <td className="music-lib-cover-cell">
                  {row.has_cover && row.cover_url ? (
                    <img src={row.cover_url} alt="" />
                  ) : (
                    <span className="music-lib-cover-empty" aria-hidden="true" />
                  )}
                </td>
                <td>{row.title || row.filename}</td>
                <td>{row.artist}</td>
                <td>{row.composer}</td>
                <td>{row.genre}</td>
                <td>{row.year || ''}</td>
                <td>{formatBpm(row.bpm)}</td>
                <td>{row.album}</td>
                <td>{row.folder_label}{row.parent ? ` / ${row.parent}` : ''}</td>
                <td>{formatDuration(row.duration_seconds)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="music-lib-player">
        <div className="music-lib-now">
          {current ? (
            <>
              {current.has_cover && current.cover_url ? (
                <img className="music-lib-now-cover" src={current.cover_url} alt="" />
              ) : null}
              <div>
              <strong>{current.title || current.filename}</strong>
              <span>
                {[current.artist, current.composer, current.genre, current.year, formatBpm(current.bpm) && `${formatBpm(current.bpm)} BPM`]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
              </div>
            </>
          ) : (
            <span>Select a track to play</span>
          )}
        </div>
        <div className="music-lib-controls">
          <button type="button" onClick={playPrev} disabled={!current}>Prev</button>
          <audio
            ref={audioRef}
            src={current?.stream_url || ''}
            controls
            autoPlay={Boolean(current)}
            onEnded={playNext}
          />
          <button type="button" onClick={playNext} disabled={!current}>Next</button>
        </div>
      </div>
    </div>
  );
}
