import React, { useCallback, useEffect, useRef } from 'react';
import { mediaSrc } from './Carousel';
import { applyKenBurnsTransform, clamp01, sampleView, viewZoomX, viewZoomY } from '../utils/kenBurns';
import { applyTimelineOpacity, numericDuration, slideStart } from '../utils/timeline';

function round4(n) {
  return Math.round(n * 10000) / 10000;
}

function ClipLayer({ item, view, stageRef }) {
  const mediaRef = useRef(null);
  const naturalRef = useRef({ width: 0, height: 0 });
  const viewRef = useRef(view);

  useEffect(() => {
    viewRef.current = view;
  }, [view]);

  const paint = useCallback(() => {
    if (!mediaRef.current || !stageRef.current || !naturalRef.current.width) return;
    applyKenBurnsTransform(mediaRef.current, stageRef.current, viewRef.current || {}, naturalRef.current);
  }, [stageRef]);

  useEffect(() => {
    paint();
  }, [view, paint]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(() => paint());
    ro.observe(stage);
    return () => ro.disconnect();
  }, [paint, stageRef]);

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

  if (!item) return null;
  const src = mediaSrc(item);

  return item.media_type === 'video' ? (
    <video
      key={src}
      ref={onMediaReady}
      src={src}
      muted
      playsInline
      className="pointer-events-none"
      draggable={false}
      onLoadedMetadata={(e) => onMediaReady(e.currentTarget)}
    />
  ) : (
    <img
      key={src}
      ref={onMediaReady}
      src={src}
      alt=""
      className="pointer-events-none"
      draggable={false}
      onLoad={(e) => onMediaReady(e.currentTarget)}
    />
  );
}

/**
 * Composite preview of every clip active at `time`.
 * Pan/zoom edits the selected keyframe when playhead is on it.
 */
export default function TimelineStage({
  slides = [],
  itemsById,
  time = 0,
  selectedIndex = -1,
  selectedView,
  onViewChange,
  effects = [],
  className = '',
}) {
  const stageRef = useRef(null);
  const dragRef = useRef(null);
  const viewRef = useRef(selectedView);
  const active = (slides || [])
    .map((s, i) => ({ s, i }))
    .filter(({ s }) => time >= slideStart(s) - 0.0001 && time <= slideStart(s) + numericDuration(s) + 0.0001)
    .sort((a, b) => (b.s.channel === 1 ? 1 : 0) - (a.s.channel === 1 ? 1 : 0));

  const selected = selectedIndex >= 0 ? slides[selectedIndex] : null;
  const localTime = selected ? time - slideStart(selected) : 0;
  const kfTime = Number(selectedView?.time) || 0;
  const interactive =
    Boolean(onViewChange && selected && selectedView) && Math.abs(localTime - kfTime) <= 0.12;

  useEffect(() => {
    viewRef.current = selectedView;
  }, [selectedView]);

  const onPointerDown = (e) => {
    if (!interactive || !onViewChange) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { id: e.pointerId, lastX: e.clientX, lastY: e.clientY };
  };

  const onPointerMove = (e) => {
    const drag = dragRef.current;
    if (!drag || drag.id !== e.pointerId || !stageRef.current || !onViewChange) return;
    const rect = stageRef.current.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const cur = viewRef.current || {};
    const curZoomX = viewZoomX(cur);
    const curZoomY = viewZoomY(cur);
    const dx = (e.clientX - drag.lastX) / rect.width / curZoomX;
    const dy = (e.clientY - drag.lastY) / rect.height / curZoomY;
    drag.lastX = e.clientX;
    drag.lastY = e.clientY;
    onViewChange({
      x: round4(clamp01((Number(cur.x) ?? 0.5) - dx)),
      y: round4(clamp01((Number(cur.y) ?? 0.5) - dy)),
    });
  };

  const endDrag = (e) => {
    if (dragRef.current?.id === e.pointerId) dragRef.current = null;
  };

  const onWheel = useCallback(
    (e) => {
      if (!interactive || !onViewChange) return;
      e.preventDefault();
      const cur = viewRef.current || {};
      const factor = e.deltaY > 0 ? 0.92 : 1.08;
      const zoomX = round4(Math.min(8, Math.max(0.2, viewZoomX(cur) * factor)));
      const zoomY = round4(Math.min(8, Math.max(0.2, viewZoomY(cur) * factor)));
      onViewChange({ zoom: zoomX, zoomX, zoomY });
    },
    [interactive, onViewChange]
  );

  useEffect(() => {
    const node = stageRef.current;
    if (!node) return undefined;
    node.addEventListener('wheel', onWheel, { passive: false });
    return () => node.removeEventListener('wheel', onWheel);
  }, [onWheel]);

  return (
    <div
      ref={stageRef}
      className={`relative overflow-hidden bg-black ${interactive ? 'cursor-grab active:cursor-grabbing' : ''} ${className}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
    >
      {active.length ? (
        active.map(({ s, i }) => {
          const sampled = sampleView(s.views, time - slideStart(s), numericDuration(s), 'linear');
          const view = {
            ...sampled,
            opacity: applyTimelineOpacity(s, time, sampled.opacity, effects),
          };
          return (
            <ClipLayer
              key={s.clip_id || i}
              item={itemsById[s.item_id]}
              view={view}
              stageRef={stageRef}
            />
          );
        })
      ) : (
        <div className="flex h-full items-center justify-center text-sm text-white/40">
          No clip at playhead
        </div>
      )}
      {interactive ? (
        <div className="pointer-events-none absolute left-1/2 top-1/2 h-6 w-6 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-emerald-400/90">
          <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-emerald-400/80" />
          <div className="absolute top-1/2 left-0 h-px w-full -translate-y-1/2 bg-emerald-400/80" />
        </div>
      ) : null}
    </div>
  );
}
