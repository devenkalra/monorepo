import React, { useEffect, useState } from 'react';
import api from '../services/api';
import { getLoginUrl, getSignupUrl } from '../utils/apiUrl';
import Carousel, { thumbSrc } from './Carousel';
import SlideshowPlayer from './SlideshowPlayer';

export default function PublicGallery({ username, slug }) {
  const [gallery, setGallery] = useState(null);
  const [error, setError] = useState('');
  const [password, setPassword] = useState('');
  const [carouselIdx, setCarouselIdx] = useState(null);
  const [playingShow, setPlayingShow] = useState(null);

  const path = `/${username}/gallery/${slug}`;

  const load = async () => {
    setError('');
    try {
      const data = await api.json(`/api/gallery/public/${encodeURIComponent(username)}/${encodeURIComponent(slug)}/`);
      setGallery(data);
    } catch (e) {
      setError(e.message || 'Failed to load');
    }
  };

  useEffect(() => {
    load();
  }, [username, slug]);

  const unlock = async (e) => {
    e.preventDefault();
    try {
      const data = await api.json(
        `/api/gallery/public/${encodeURIComponent(username)}/${encodeURIComponent(slug)}/unlock/`,
        { method: 'POST', body: JSON.stringify({ password }) }
      );
      setGallery(data);
    } catch (err) {
      setError(err.message || 'Unlock failed');
    }
  };

  if (!gallery && !error) {
    return <div className="p-8 text-center text-stone-500">Loading…</div>;
  }

  const perms = gallery?.permissions || {};

  if (perms.needs_login || perms.needs_signup) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <h1 className="text-xl font-semibold text-stone-900">{gallery?.title || 'Private gallery'}</h1>
        <p className="mt-2 text-stone-600">
          This gallery is invite-only. Log in with your invited email, or create an account if you were invited and
          do not have one yet.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <a href={getLoginUrl(path)} className="inline-block rounded-lg bg-emerald-700 px-4 py-2 text-white">
            Log in
          </a>
          <a href={getSignupUrl(path)} className="inline-block rounded-lg border border-stone-300 px-4 py-2">
            Sign up
          </a>
        </div>
      </div>
    );
  }

  if (perms.needs_share_password) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <h1 className="text-xl font-semibold text-center">{gallery?.title || 'Private gallery'}</h1>
        <p className="mt-2 text-center text-sm text-stone-600">Enter the share password you were given.</p>
        <form onSubmit={unlock} className="mt-6 space-y-3">
          <input
            type="password"
            className="w-full rounded-lg border px-3 py-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Share password"
            required
          />
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <button type="submit" className="w-full rounded-lg bg-emerald-700 py-2 text-white">
            Unlock
          </button>
        </form>
      </div>
    );
  }

  if (!perms.can_view) {
    return (
      <div className="p-8 text-center text-red-600">{error || 'You do not have access to this gallery.'}</div>
    );
  }

  const items = gallery.items || [];

  return (
    <div className="min-h-screen bg-gradient-to-b from-stone-50 to-stone-100">
      <header className="border-b border-stone-200/80 bg-white/80 px-4 py-6 backdrop-blur">
        <div className="mx-auto max-w-5xl">
          <h1 className="text-3xl font-semibold tracking-tight text-stone-900">{gallery.title}</h1>
          {gallery.description ? <p className="mt-2 max-w-2xl text-stone-600">{gallery.description}</p> : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-lg bg-stone-900 px-3 py-1.5 text-sm text-white"
              onClick={() => setCarouselIdx(0)}
              disabled={!items.length}
            >
              Open carousel
            </button>
            {(gallery.shows || []).map((s) => (
              <button
                key={s.id}
                type="button"
                className="rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-sm"
                onClick={() => setPlayingShow(s)}
              >
                Play {s.title || s.slug}
              </button>
            ))}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
          {items.map((item, idx) => (
            <button
              key={item.id}
              type="button"
              className="overflow-hidden rounded-lg bg-white shadow-sm ring-1 ring-stone-200"
              onClick={() => setCarouselIdx(idx)}
            >
              <img src={thumbSrc(item)} alt={item.title || ''} className="aspect-square w-full object-cover" />
              {(item.title || item.caption) && (
                <div className="truncate px-2 py-1.5 text-left text-xs text-stone-600">
                  {item.title || item.caption}
                </div>
              )}
            </button>
          ))}
        </div>
      </main>
      {carouselIdx != null ? (
        <div className="fixed inset-0 z-40 bg-black/60 p-4">
          <Carousel items={items} startIndex={carouselIdx} onClose={() => setCarouselIdx(null)} />
        </div>
      ) : null}
      {playingShow ? (
        <SlideshowPlayer config={playingShow.config} items={items} onClose={() => setPlayingShow(null)} />
      ) : null}
    </div>
  );
}
