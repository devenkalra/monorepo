import React, { useCallback, useEffect, useRef } from 'react';
import { mediaSrc } from './Carousel';
import { applyKenBurnsTransform, clamp01 } from '../utils/kenBurns';

/**
 * Interactive Ken Burns preview for one keyframe.
 * Same transform model as playback: focus stays centered; zoom/pan stay in sync.
 */
export default function KeyframeStage({ item, view, viewIndex = 0, onChange, fillHeight = false }) {
  const stageRef = useRef(null);
  const mediaRef = useRef(null);
  const naturalRef = useRef({ width: 0, height: 0 });
  const dragRef = useRef(null);
  const viewRef = useRef(view);

  useEffect(() => {
    viewRef.current = view;
  }, [view]);

  const paint = useCallback(() => {
    if (!mediaRef.current || !stageRef.current || !naturalRef.current.width) return;
    applyKenBurnsTransform(mediaRef.current, stageRef.current, viewRef.current || {}, naturalRef.current);
  }, []);

  useEffect(() => {
    paint();
  }, [view, paint, fillHeight]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(() => paint());
    ro.observe(stage);
    return () => ro.disconnect();
  }, [paint]);

  const onMediaReady = (el) => {
    if (!el) return;
    mediaRef.current = el;
    const w = el.naturalWidth || el.videoWidth || 0;
    const h = el.naturalHeight || el.videoHeight || 0;
    if (w && h) {
      naturalRef.current = { width: w, height: h };
      paint();
    }
  };

  const onPointerDown = (e) => {
    if (!onChange) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { id: e.pointerId, lastX: e.clientX, lastY: e.clientY };
  };

  const onPointerMove = (e) => {
    const drag = dragRef.current;
    if (!drag || drag.id !== e.pointerId || !stageRef.current || !onChange) return;
    const rect = stageRef.current.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const cur = viewRef.current || {};
    const curZoom = Math.max(Number(cur.zoom) || 1, 0.2);
    // Pan in focus-space: dragging right reveals content to the left (focus x decreases).
    // Divide by zoom so pan speed matches visible scale (same feel as FolderBrowser).
    const dx = (e.clientX - drag.lastX) / rect.width / curZoom;
    const dy = (e.clientY - drag.lastY) / rect.height / curZoom;
    drag.lastX = e.clientX;
    drag.lastY = e.clientY;
    onChange({
      x: round4(clamp01((Number(cur.x) ?? 0.5) - dx)),
      y: round4(clamp01((Number(cur.y) ?? 0.5) - dy)),
    });
  };

  const endDrag = (e) => {
    if (dragRef.current?.id === e.pointerId) dragRef.current = null;
  };

  const onWheel = useCallback(
    (e) => {
      if (!onChange) return;
      e.preventDefault();
      const cur = viewRef.current || {};
      const curZoom = Number(cur.zoom) || 1;
      const factor = e.deltaY > 0 ? 0.92 : 1.08;
      onChange({ zoom: round4(Math.min(8, Math.max(0.2, curZoom * factor))) });
    },
    [onChange]
  );

  useEffect(() => {
    const node = stageRef.current;
    if (!node) return undefined;
    node.addEventListener('wheel', onWheel, { passive: false });
    return () => node.removeEventListener('wheel', onWheel);
  }, [onWheel]);

  if (!item) {
    return (
      <div className="flex aspect-video items-center justify-center rounded-lg bg-black text-white/50">
        Pick a media item
      </div>
    );
  }

  const src = mediaSrc(item);
  const zoom = Number(view?.zoom) || 1;
  const x = clamp01(view?.x ?? 0.5);
  const y = clamp01(view?.y ?? 0.5);

  return (
    <div className={`flex min-h-0 flex-col ${fillHeight ? 'h-full' : ''}`}>
      <div
        ref={stageRef}
        className={`relative cursor-grab overflow-hidden rounded-lg bg-black active:cursor-grabbing ${
          fillHeight ? 'min-h-0 flex-1' : 'aspect-video'
        }`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        {item.media_type === 'video' ? (
          <video
            key={src}
            ref={onMediaReady}
            src={src}
            muted
            playsInline
            className="pointer-events-none block select-none"
            draggable={false}
            onLoadedMetadata={(e) => onMediaReady(e.currentTarget)}
          />
        ) : (
          <img
            key={src}
            ref={onMediaReady}
            src={src}
            alt=""
            className="pointer-events-none block select-none"
            draggable={false}
            onLoad={(e) => onMediaReady(e.currentTarget)}
          />
        )}
        <div
          className="pointer-events-none absolute left-1/2 top-1/2 h-6 w-6 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-emerald-400/90 shadow"
        >
          <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-emerald-400/80" />
          <div className="absolute top-1/2 left-0 h-px w-full -translate-y-1/2 bg-emerald-400/80" />
        </div>
        <div className="pointer-events-none absolute left-2 top-2 rounded bg-black/60 px-2 py-0.5 text-[11px] text-white">
          {(view?.name || '').trim() || `Keyframe ${viewIndex + 1}`} · zoom {zoom.toFixed(2)} · focus{' '}
          {x.toFixed(2)}, {y.toFixed(2)}
        </div>
      </div>
      {!fillHeight ? (
        <p className="mt-2 text-xs text-stone-500">
          Zoom 1 = full image. Drag to pan · scroll to zoom (0.2–8).
        </p>
      ) : null}
    </div>
  );
}

function round4(n) {
  return Math.round(n * 10000) / 10000;
}
