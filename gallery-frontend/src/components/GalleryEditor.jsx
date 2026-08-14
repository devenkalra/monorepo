import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import api from '../services/api';
import Carousel, { thumbSrc } from './Carousel';
import MediaPicker from './MediaPicker';
import SlideshowEditor from './SlideshowEditor';
import SlideshowPlayer from './SlideshowPlayer';

export default function GalleryEditor() {
  const { id } = useParams();
  const [gallery, setGallery] = useState(null);
  const [error, setError] = useState('');
  const [picker, setPicker] = useState(false);
  const [carouselIdx, setCarouselIdx] = useState(null);
  const [showEditor, setShowEditor] = useState(null);
  const [playingShow, setPlayingShow] = useState(null);
  const [entityId, setEntityId] = useState('');
  const [shareForm, setShareForm] = useState({ email: '', password: '', role: 'view' });
  const [dragId, setDragId] = useState(null);

  const load = useCallback(async () => {
    try {
      const data = await api.json(`/api/gallery/galleries/${id}/`);
      setGallery(data);
      setEntityId(data.source_entity || '');
    } catch (e) {
      setError(e.message || 'Failed to load');
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const patch = async (body) => {
    const data = await api.json(`/api/gallery/galleries/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
    setGallery((g) => ({ ...g, ...data }));
    await load();
  };

  const addItem = async (payload) => {
    await api.json('/api/gallery/items/', {
      method: 'POST',
      body: JSON.stringify({ gallery: id, ...payload }),
    });
    setPicker(false);
    await load();
  };

  const onUploadedItem = async () => {
    await load();
  };

  const refreshEntity = async () => {
    if (!entityId) return;
    await api.json(`/api/gallery/galleries/${id}/refresh-from-entity/`, {
      method: 'POST',
      body: JSON.stringify({ entity_id: entityId }),
    });
    await load();
  };

  const onDrop = async (targetId) => {
    if (!dragId || dragId === targetId || !gallery?.items) return;
    const ids = gallery.items.map((i) => i.id);
    const from = ids.indexOf(dragId);
    const to = ids.indexOf(targetId);
    if (from < 0 || to < 0) return;
    ids.splice(from, 1);
    ids.splice(to, 0, dragId);
    await api.json(`/api/gallery/galleries/${id}/reorder/`, {
      method: 'POST',
      body: JSON.stringify({ item_ids: ids }),
    });
    setDragId(null);
    await load();
  };

  const addShare = async (e) => {
    e.preventDefault();
    await api.json('/api/gallery/shares/', {
      method: 'POST',
      body: JSON.stringify({ gallery: id, ...shareForm }),
    });
    setShareForm({ email: '', password: '', role: 'view' });
    await load();
  };

  if (error) {
    return <div className="p-6 text-red-600">{error}</div>;
  }
  if (!gallery) {
    return <div className="p-6 text-stone-500">Loading…</div>;
  }

  const canEdit = gallery.permissions?.can_edit || gallery.permissions?.is_owner;
  const items = gallery.items || [];

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="mb-4">
        <Link to="/" className="text-sm text-emerald-700 hover:underline">
          ← All galleries
        </Link>
      </div>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          {canEdit ? (
            <input
              className="w-full border-0 border-b border-transparent text-2xl font-semibold text-stone-900 focus:border-emerald-500 focus:outline-none"
              value={gallery.title}
              onChange={(e) => setGallery({ ...gallery, title: e.target.value })}
              onBlur={() => patch({ title: gallery.title })}
            />
          ) : (
            <h1 className="text-2xl font-semibold">{gallery.title}</h1>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-stone-500">
            <span>
              Public URL:{' '}
              <a className="text-emerald-700" href={gallery.public_path} target="_blank" rel="noreferrer">
                {gallery.public_path}
              </a>
            </span>
            {canEdit ? (
              <label className="flex items-center gap-1">
                slug
                <input
                  className="rounded border px-2 py-0.5"
                  value={gallery.slug}
                  onChange={(e) => setGallery({ ...gallery, slug: e.target.value })}
                  onBlur={() => patch({ slug: gallery.slug })}
                />
              </label>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-lg border px-3 py-1.5 text-sm"
            onClick={() => setCarouselIdx(0)}
            disabled={!items.length}
          >
            Carousel
          </button>
          {canEdit ? (
            <button type="button" className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm text-white" onClick={() => setPicker(true)}>
              Add media
            </button>
          ) : null}
        </div>
      </div>

      {canEdit ? (
        <section className="mb-6 grid gap-4 rounded-xl border border-stone-200 bg-white p-4 sm:grid-cols-2">
          <label className="text-sm">
            Access
            <select
              className="mt-1 w-full rounded border px-2 py-1.5"
              value={gallery.access_mode}
              onChange={(e) => patch({ access_mode: e.target.value })}
            >
              <option value="public">Public</option>
              <option value="restricted">Restricted</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm pt-6">
            <input
              type="checkbox"
              checked={!!gallery.allow_download}
              onChange={(e) => patch({ allow_download: e.target.checked })}
            />
            Allow download
          </label>
          <label className="text-sm sm:col-span-2">
            Description
            <textarea
              className="mt-1 w-full rounded border px-2 py-1.5"
              rows={2}
              value={gallery.description || ''}
              onChange={(e) => setGallery({ ...gallery, description: e.target.value })}
              onBlur={() => patch({ description: gallery.description })}
            />
          </label>
          <div className="sm:col-span-2 flex flex-wrap items-end gap-2">
            <label className="text-sm flex-1">
              Source entity id (refresh photos)
              <input
                className="mt-1 w-full rounded border px-2 py-1.5 font-mono text-xs"
                value={entityId}
                onChange={(e) => setEntityId(e.target.value)}
                placeholder="UUID of person/entity"
              />
            </label>
            <button type="button" className="rounded border px-3 py-1.5 text-sm" onClick={refreshEntity}>
              Refresh from entity
            </button>
          </div>
          <div className="sm:col-span-2 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded border px-3 py-1.5 text-sm"
              onClick={() =>
                api.json(`/api/gallery/galleries/${id}/sort_items/`, {
                  method: 'POST',
                  body: JSON.stringify({ by: 'title', direction: 'asc' }),
                }).then(load)
              }
            >
              Sort by title
            </button>
            <button
              type="button"
              className="rounded border px-3 py-1.5 text-sm"
              onClick={() =>
                api.json(`/api/gallery/galleries/${id}/sort_items/`, {
                  method: 'POST',
                  body: JSON.stringify({ by: 'created_at', direction: 'asc' }),
                }).then(load)
              }
            >
              Sort by date
            </button>
          </div>
        </section>
      ) : null}

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-stone-500">Grid</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
          {items.map((item, idx) => (
            <div
              key={item.id}
              draggable={canEdit}
              onDragStart={() => setDragId(item.id)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => onDrop(item.id)}
              className="group relative overflow-hidden rounded-lg border border-stone-200 bg-stone-50"
            >
              <button type="button" className="block w-full" onClick={() => setCarouselIdx(idx)}>
                <img src={thumbSrc(item)} alt="" className="aspect-square w-full object-cover" />
              </button>
              <div className="p-2">
                {canEdit ? (
                  <input
                    className="w-full border-0 bg-transparent text-xs font-medium focus:outline-none"
                    value={item.title}
                    placeholder="Title"
                    onChange={(e) => {
                      const title = e.target.value;
                      setGallery({
                        ...gallery,
                        items: items.map((it) => (it.id === item.id ? { ...it, title } : it)),
                      });
                    }}
                    onBlur={() =>
                      api.json(`/api/gallery/items/${item.id}/`, {
                        method: 'PATCH',
                        body: JSON.stringify({ title: item.title }),
                      })
                    }
                  />
                ) : (
                  <div className="truncate text-xs font-medium">{item.title || item.filename}</div>
                )}
                {canEdit ? (
                  <div className="mt-1 flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="text-[10px] text-emerald-700"
                      onClick={() =>
                        patch({
                          cover: {
                            url: item.display_url || item.url || item.external_url,
                            thumbnail_url: item.thumbnail_url || item.url || item.external_url,
                          },
                        })
                      }
                    >
                      Set cover
                    </button>
                    <button
                      type="button"
                      className="text-[10px] text-red-600"
                      onClick={async () => {
                        if (!window.confirm('Remove this item from the gallery?')) return;
                        await api.json(`/api/gallery/items/${item.id}/`, { method: 'DELETE' });
                        await load();
                      }}
                    >
                      Remove
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium uppercase tracking-wide text-stone-500">Shows</h2>
          {canEdit ? (
            <button type="button" className="text-sm text-emerald-700" onClick={() => setShowEditor({})}>
              New show
            </button>
          ) : null}
        </div>
        <ul className="space-y-2">
          {(gallery.shows || []).map((s) => (
            <li key={s.id} className="flex items-center justify-between rounded-lg border bg-white px-3 py-2 text-sm">
              <span>
                {s.title || s.slug}
              </span>
              <div className="flex gap-2">
                <button type="button" className="text-emerald-700" onClick={() => setPlayingShow(s)}>
                  Play
                </button>
                {canEdit ? (
                  <button type="button" className="text-stone-600" onClick={() => setShowEditor(s)}>
                    Edit
                  </button>
                ) : null}
              </div>
            </li>
          ))}
          {!gallery.shows?.length ? <li className="text-sm text-stone-400">No scripted shows yet</li> : null}
        </ul>
      </section>

      {canEdit && gallery.access_mode === 'restricted' ? (
        <section className="mb-8 rounded-xl border bg-white p-4">
          <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-stone-500">Shares</h2>
          <ul className="mb-4 space-y-1 text-sm">
            {(gallery.shares || []).map((s) => (
              <li key={s.id} className="flex justify-between gap-2">
                <span>
                  {s.email} · {s.role} {s.active ? '' : '(inactive)'}
                </span>
                <button
                  type="button"
                  className="text-red-600"
                  onClick={() => api.json(`/api/gallery/shares/${s.id}/`, { method: 'DELETE' }).then(load)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
          <form onSubmit={addShare} className="flex flex-wrap gap-2">
            <input
              className="rounded border px-2 py-1.5 text-sm"
              placeholder="email"
              value={shareForm.email}
              onChange={(e) => setShareForm({ ...shareForm, email: e.target.value })}
              required
            />
            <input
              className="rounded border px-2 py-1.5 text-sm"
              placeholder="share password"
              type="password"
              value={shareForm.password}
              onChange={(e) => setShareForm({ ...shareForm, password: e.target.value })}
              required
            />
            <select
              className="rounded border px-2 py-1.5 text-sm"
              value={shareForm.role}
              onChange={(e) => setShareForm({ ...shareForm, role: e.target.value })}
            >
              <option value="view">View</option>
              <option value="add_photos">Add photos</option>
              <option value="edit">Edit</option>
            </select>
            <button type="submit" className="rounded bg-stone-800 px-3 py-1.5 text-sm text-white">
              Invite
            </button>
          </form>
        </section>
      ) : null}

      {carouselIdx != null ? (
        <div className="fixed inset-0 z-40 bg-black/50 p-4 md:p-8">
          <Carousel items={items} startIndex={carouselIdx} onClose={() => setCarouselIdx(null)} />
        </div>
      ) : null}
      {picker ? (
        <MediaPicker
          galleryId={id}
          onPick={addItem}
          onUploaded={async () => {
            await onUploadedItem();
          }}
          onClose={() => {
            setPicker(false);
            load();
          }}
        />
      ) : null}
      {showEditor ? (
        <SlideshowEditor
          gallery={gallery}
          show={showEditor.id ? showEditor : null}
          onSaved={() => {
            setShowEditor(null);
            load();
          }}
          onClose={() => setShowEditor(null)}
        />
      ) : null}
      {playingShow ? (
        <SlideshowPlayer
          config={playingShow.config}
          items={items}
          onClose={() => setPlayingShow(null)}
        />
      ) : null}
    </div>
  );
}
