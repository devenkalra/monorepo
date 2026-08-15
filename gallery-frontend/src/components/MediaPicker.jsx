import React, { useEffect, useRef, useState } from 'react';
import api from '../services/api';

const TABS = [
  { id: 'upload', label: 'Upload' },
  { id: 'library', label: 'My files' },
  { id: 'entities', label: 'By entity' },
  { id: 'url', label: 'Web URL' },
];

const STORAGE_KEY = 'gallery.mediaPicker';

function readStored() {
  try {
    const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    const tab = TABS.some((t) => t.id === data.tab) ? data.tab : 'upload';
    return {
      tab,
      q: typeof data.q === 'string' ? data.q : '',
      external: typeof data.external === 'string' ? data.external : '',
    };
  } catch {
    return { tab: 'upload', q: '', external: '' };
  }
}

function toPickPayload(r) {
  return {
    url: r.url?.startsWith('http') ? '' : r.url,
    external_url: r.url?.startsWith('http') ? r.url : '',
    thumbnail_url: r.thumbnail_url,
    filename: r.filename,
    caption: r.caption || '',
    title: r.caption || r.filename || '',
    media_type: r.media_type,
    source_photo_key: r.source_photo_key || r.url,
  };
}

export default function MediaPicker({ galleryId, onPick, onUploaded, onClose }) {
  const [tab, setTab] = useState(() => readStored().tab);
  const [q, setQ] = useState(() => readStored().q);
  const [results, setResults] = useState([]);
  const [external, setExternal] = useState(() => readStored().external);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState('');
  const fileRef = useRef(null);

  const load = async (source) => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (q) params.set('q', q);
      params.set('source', source);
      if (galleryId) params.set('gallery', galleryId);
      const data = await api.json(`/api/gallery/media-browser/?${params}`);
      setResults(data.results || []);
    } catch (e) {
      setResults([]);
      setError(e.message || 'Failed to load media');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ tab, q, external }));
    } catch {
      /* private mode / quota */
    }
  }, [tab, q, external]);

  useEffect(() => {
    // My files = everything keyed to the user (uploads, gallery items, entity photos)
    if (tab === 'library') load('all');
    if (tab === 'entities') load('entities');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, galleryId]);

  const uploadFiles = async (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setUploading(true);
    setError('');
    let ok = 0;
    try {
      for (let i = 0; i < files.length; i += 1) {
        const file = files[i];
        setProgress(`Uploading ${i + 1}/${files.length}: ${file.name}`);
        const body = new FormData();
        body.append('file', file);
        if (galleryId) {
          body.append('gallery', galleryId);
          body.append('add_to_gallery', 'true');
        }
        const data = await api.json('/api/gallery/upload/', { method: 'POST', body });
        ok += 1;
        if (data.item && onUploaded) {
          onUploaded(data.item);
        } else if (onPick) {
          onPick({
            url: data.url,
            external_url: '',
            thumbnail_url: data.thumbnail_url,
            filename: data.filename,
            media_type: data.media_type,
            title: data.filename,
            caption: '',
            source_photo_key: data.url,
          });
        }
      }
      setProgress(`Uploaded ${ok} file${ok === 1 ? '' : 's'}`);
      if (tab === 'library') load('all');
    } catch (e) {
      setError(e.message || 'Upload failed');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h3 className="font-semibold">Add media</h3>
          <button type="button" onClick={onClose} className="text-stone-500 hover:text-stone-800">
            ✕
          </button>
        </div>

        <div className="flex gap-1 border-b px-2 pt-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`rounded-t px-3 py-2 text-sm ${
                tab === t.id
                  ? 'bg-stone-100 font-medium text-stone-900'
                  : 'text-stone-500 hover:text-stone-800'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {error ? <div className="bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div> : null}
        {progress ? <div className="bg-emerald-50 px-4 py-2 text-sm text-emerald-800">{progress}</div> : null}

        {tab === 'upload' ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
            <input
              ref={fileRef}
              type="file"
              accept="image/*,video/*,.mp4,.webm,.mov,.jpg,.jpeg,.png,.gif,.webp"
              multiple
              className="hidden"
              onChange={(e) => uploadFiles(e.target.files)}
            />
            <button
              type="button"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
              className="rounded-xl border-2 border-dashed border-stone-300 px-8 py-10 text-center hover:border-emerald-500 hover:bg-emerald-50/50 disabled:opacity-50"
            >
              <div className="text-base font-medium text-stone-800">
                {uploading ? 'Uploading…' : 'Choose photos or videos'}
              </div>
              <div className="mt-1 text-sm text-stone-500">
                Files are stored under /media/ in the gallery owner&apos;s library
              </div>
            </button>
            <p className="text-xs text-stone-400">You can select multiple files</p>
          </div>
        ) : null}

        {tab === 'url' ? (
          <div className="flex flex-col gap-3 p-4">
            <input
              className="w-full rounded border border-stone-300 px-3 py-2 text-sm"
              placeholder="https://… image or video URL"
              value={external}
              onChange={(e) => setExternal(e.target.value)}
            />
            <button
              type="button"
              className="self-start rounded bg-stone-800 px-4 py-2 text-sm text-white"
              onClick={() => {
                if (!external.trim()) return;
                onPick?.({
                  external_url: external.trim(),
                  url: '',
                  media_type: /\.(mp4|webm|mov)(\?|$)/i.test(external) ? 'video' : 'image',
                  title: '',
                  caption: '',
                });
              }}
            >
              Add URL
            </button>
          </div>
        ) : null}

        {(tab === 'library' || tab === 'entities') && (
          <>
            <div className="flex gap-2 border-b px-4 py-3">
              <input
                className="flex-1 rounded border border-stone-300 px-3 py-1.5 text-sm"
                placeholder={tab === 'library' ? 'Search all my media…' : 'Search entity photos…'}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && load(tab === 'library' ? 'all' : 'entities')}
              />
              <button
                type="button"
                className="rounded bg-stone-800 px-3 py-1.5 text-sm text-white"
                onClick={() => load(tab === 'library' ? 'all' : 'entities')}
              >
                Search
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-3">
              {loading ? (
                <p className="text-sm text-stone-500">Loading…</p>
              ) : results.length === 0 ? (
                <p className="text-sm text-stone-500">
                  {tab === 'library'
                    ? 'No media found for your account yet.'
                    : 'No entity photos found.'}
                </p>
              ) : (
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                  {results.map((r) => (
                    <button
                      key={`${r.source}-${r.url}`}
                      type="button"
                      className="overflow-hidden rounded border border-stone-200 text-left hover:border-emerald-400"
                      onClick={() => onPick?.(toPickPayload(r))}
                    >
                      {r.media_type === 'video' ? (
                        <div className="relative aspect-square bg-stone-900">
                          <img
                            src={r.thumbnail_url || r.url}
                            alt=""
                            className="h-full w-full object-cover opacity-90"
                          />
                          <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 text-[10px] text-white">
                            video
                          </span>
                        </div>
                      ) : (
                        <img
                          src={r.thumbnail_url || r.url}
                          alt=""
                          className="aspect-square w-full object-cover"
                        />
                      )}
                      <div className="truncate px-1 py-0.5 text-[10px] text-stone-500">
                        {r.entity_display || r.filename || r.source}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
