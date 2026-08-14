import React, { useEffect, useMemo, useRef, useState } from 'react';
import TimelineStage from './TimelineStage';
import { formatTime, normalizeSlides, round2, showDuration } from '../utils/timeline';

function resolveSlideMedia(slide, itemsById, itemsByFile) {
  if (slide.url) return true;
  if (slide.item_id && itemsById[slide.item_id]) return true;
  if (slide.file && itemsByFile[slide.file]) return true;
  return false;
}

export default function SlideshowPlayer({
  config,
  items = [],
  onClose,
  embedded = false,
  startAt = 0,
}) {
  const itemsById = useMemo(
    () => Object.fromEntries((items || []).map((it) => [it.id, it])),
    [items]
  );
  const itemsByFile = useMemo(() => {
    const file = {};
    for (const it of items || []) {
      if (it.filename) file[it.filename] = it;
    }
    return file;
  }, [items]);

  const slides = useMemo(() => {
    const raw = config?.slides?.length
      ? config.slides
      : items.map((it) => ({
          item_id: it.id,
          duration: it.media_type === 'video' ? 'video' : config?.defaults?.duration ?? 10,
        }));
    return normalizeSlides(raw.filter((s) => resolveSlideMedia(s, itemsById, itemsByFile)));
  }, [config, items, itemsById, itemsByFile]);

  const end = Math.max(0.1, showDuration(slides));
  const [time, setTime] = useState(() => Math.min(startAt, end));
  const [playing, setPlaying] = useState(true);
  const timeRef = useRef(time);
  const playingRef = useRef(true);

  timeRef.current = time;
  playingRef.current = playing;

  useEffect(() => {
    if (!playing) return undefined;
    let last = performance.now();
    let raf = 0;
    const tick = (now) => {
      const dt = (now - last) / 1000;
      last = now;
      let next = timeRef.current + dt;
      if (next >= end) {
        if (config?.loop === false) {
          setTime(end);
          setPlaying(false);
          return;
        }
        next = 0;
      }
      setTime(round2(next));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, end, config?.loop]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === ' ') {
        e.preventDefault();
        setPlaying((p) => !p);
      } else if (e.key === 'Escape') {
        onClose?.();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!slides.length) {
    return (
      <div
        className={
          embedded
            ? 'relative flex h-full items-center justify-center bg-black text-white'
            : 'fixed inset-0 z-50 flex items-center justify-center bg-black text-white'
        }
      >
        No slides
        <button type="button" className="ml-4 underline" onClick={onClose}>
          Close
        </button>
      </div>
    );
  }

  return (
    <div
      className={
        embedded
          ? 'relative flex h-full min-h-0 w-full flex-col overflow-hidden rounded-lg bg-black text-white'
          : 'fixed inset-0 z-50 flex flex-col bg-black text-white'
      }
    >
      <div className="flex items-center justify-between px-4 py-2 text-sm text-white/70">
        <span>
          {formatTime(time)} / {formatTime(end)}
          {!playing ? ' · paused' : ''}
        </span>
        <div className="flex gap-2">
          <button type="button" className="rounded px-2 py-1 hover:bg-white/10" onClick={() => setPlaying((p) => !p)}>
            {playing ? 'Pause' : 'Play'}
          </button>
          <button
            type="button"
            className="rounded px-2 py-1 hover:bg-white/10"
            onClick={() => {
              setTime(startAt || 0);
              setPlaying(true);
            }}
          >
            Replay
          </button>
          <button type="button" className="rounded px-2 py-1 hover:bg-white/10" onClick={onClose}>
            {embedded ? 'Stop' : 'Close'}
          </button>
        </div>
      </div>
      <TimelineStage
        className="min-h-0 flex-1"
        slides={slides}
        itemsById={itemsById}
        time={time}
        effects={config?.effects || []}
      />
    </div>
  );
}
