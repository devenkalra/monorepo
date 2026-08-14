import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../services/api';

function slugify(s) {
  return (s || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 80) || 'gallery';
}

export default function GalleryList() {
  const navigate = useNavigate();
  const [galleries, setGalleries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [title, setTitle] = useState('');
  const [creating, setCreating] = useState(false);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.json('/api/gallery/galleries/');
      setGalleries(Array.isArray(data) ? data : data.results || []);
    } catch (e) {
      setError(e.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const create = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    setCreating(true);
    try {
      const g = await api.json('/api/gallery/galleries/', {
        method: 'POST',
        body: JSON.stringify({
          title: title.trim(),
          slug: slugify(title),
          access_mode: 'public',
        }),
      });
      setTitle('');
      navigate(`/g/${g.id}`);
    } catch (err) {
      setError(err.message || 'Create failed');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-stone-900">Galleries</h1>
          <p className="text-sm text-stone-500">Create and manage photo &amp; video galleries</p>
        </div>
        <form onSubmit={create} className="flex gap-2">
          <input
            className="rounded-lg border border-stone-300 px-3 py-2 text-sm"
            placeholder="New gallery title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <button
            type="submit"
            disabled={creating}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Create
          </button>
        </form>
      </div>
      {error ? <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      {loading ? (
        <p className="text-stone-500">Loading…</p>
      ) : galleries.length === 0 ? (
        <p className="text-stone-500">No galleries yet.</p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {galleries.map((g) => (
            <li key={g.id}>
              <Link
                to={`/g/${g.id}`}
                className="block overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm transition hover:border-emerald-300"
              >
                <div className="aspect-[4/3] bg-stone-100">
                  {g.cover?.thumbnail_url || g.cover?.url ? (
                    <img
                      src={g.cover.thumbnail_url || g.cover.url}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-stone-400">No cover</div>
                  )}
                </div>
                <div className="p-3">
                  <div className="font-medium text-stone-900">{g.title}</div>
                  <div className="mt-0.5 text-xs text-stone-500">
                    {g.item_count ?? 0} items · {g.access_mode}
                    {g.public_path ? (
                      <span className="ml-1 text-emerald-700">{g.public_path}</span>
                    ) : null}
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
