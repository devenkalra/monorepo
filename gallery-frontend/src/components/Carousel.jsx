import React, { useCallback, useEffect, useState } from 'react';

function mediaSrc(item) {
  return item?.display_url || item?.external_url || item?.url || '';
}

function thumbSrc(item) {
  return item?.thumbnail_url || mediaSrc(item);
}

export default function Carousel({
  items = [],
  startIndex = 0,
  onClose,
  fullscreen = false,
  onFullscreenChange,
}) {
  const [index, setIndex] = useState(startIndex);
  const [fs, setFs] = useState(fullscreen);
  const item = items[index];

  const go = useCallback(
    (delta) => {
      if (!items.length) return;
      setIndex((i) => (i + delta + items.length) % items.length);
    },
    [items.length]
  );

  useEffect(() => {
    setIndex(Math.min(Math.max(0, startIndex), Math.max(0, items.length - 1)));
  }, [startIndex, items.length]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'ArrowRight' || e.key === 'l') {
        e.preventDefault();
        go(1);
      } else if (e.key === 'ArrowLeft' || e.key === 'h' || e.key === 'j') {
        e.preventDefault();
        go(-1);
      } else if (e.key === 'Escape') {
        if (fs) {
          setFs(false);
          onFullscreenChange?.(false);
        } else {
          onClose?.();
        }
      } else if (e.key === 'f') {
        const next = !fs;
        setFs(next);
        onFullscreenChange?.(next);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go, fs, onClose, onFullscreenChange]);

  if (!item) {
    return (
      <div className="rounded-lg border border-stone-200 bg-stone-50 p-8 text-center text-stone-500">
        No media
      </div>
    );
  }

  const src = mediaSrc(item);
  const shell = (
    <div
      className={`${
        fs ? 'fixed inset-0 z-50 bg-black' : 'relative rounded-lg border border-stone-200 bg-stone-900'
      } flex flex-col`}
    >
      <div className="flex items-center justify-between gap-2 px-3 py-2 text-sm text-white/90">
        <div className="min-w-0 truncate">
          <span className="font-medium">{item.title || item.filename || 'Untitled'}</span>
          {item.caption ? <span className="ml-2 text-white/60">{item.caption}</span> : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-white/50">
            {index + 1}/{items.length}
          </span>
          <button
            type="button"
            className="rounded px-2 py-1 hover:bg-white/10"
            onClick={() => {
              const next = !fs;
              setFs(next);
              onFullscreenChange?.(next);
            }}
            title="Fullscreen (f)"
          >
            {fs ? 'Exit' : 'Full'}
          </button>
          {onClose ? (
            <button type="button" className="rounded px-2 py-1 hover:bg-white/10" onClick={onClose}>
              Close
            </button>
          ) : null}
        </div>
      </div>
      <div className="relative flex min-h-0 flex-1 items-center justify-center px-10 py-4">
        <button
          type="button"
          className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-white/10 px-3 py-2 text-white hover:bg-white/20"
          onClick={() => go(-1)}
          aria-label="Previous"
        >
          ‹
        </button>
        {item.media_type === 'video' ? (
          <video key={src} src={src} controls className="max-h-[80vh] max-w-full" poster={thumbSrc(item)} />
        ) : (
          <img key={src} src={src} alt={item.title || ''} className="max-h-[80vh] max-w-full object-contain" />
        )}
        <button
          type="button"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-white/10 px-3 py-2 text-white hover:bg-white/20"
          onClick={() => go(1)}
          aria-label="Next"
        >
          ›
        </button>
      </div>
      <div className="px-3 pb-2 text-center text-xs text-white/40">
        ← → or h/l navigate · f fullscreen · Esc close
      </div>
    </div>
  );

  return shell;
}

export { mediaSrc, thumbSrc };
