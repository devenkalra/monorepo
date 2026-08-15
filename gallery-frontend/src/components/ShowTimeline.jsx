import React, { useEffect, useMemo, useRef, useState } from 'react';
import { thumbSrc } from './Carousel';
import {
  DEFAULT_CLIP_DURATION,
  DEFAULT_EFFECT_DURATION,
  EFFECT_TYPES,
  MIN_CLIP_DURATION,
  dropDuration,
  effectDuration,
  effectEnd,
  effectStart,
  formatTime,
  gapAt,
  leftNeighborEnd,
  newClipFromItem,
  newEffect,
  numericDuration,
  rightNeighborStart,
  rippleAfter,
  rippleEffects,
  round2,
  scaleViews,
  slideChannel,
  slideStart,
  showDuration,
} from '../utils/timeline';

const CHANNELS = [
  { id: 0, label: 'A' },
  { id: 1, label: 'B' },
];

const FX_COLORS = {
  'fade-in': 'bg-sky-500/80 border-sky-700',
  'fade-out': 'bg-amber-500/80 border-amber-700',
  blend: 'bg-violet-500/80 border-violet-700',
  'blend-reverse': 'bg-fuchsia-500/80 border-fuchsia-700',
};

function ticks(total, pxPerSec) {
  const step = pxPerSec >= 56 ? 1 : pxPerSec >= 28 ? 2 : 5;
  const out = [];
  for (let t = 0; t <= total + 0.001; t += step) out.push(t);
  return out;
}

function readItemId(dt) {
  const custom = dt.getData('application/x-gallery-item');
  if (custom) return custom;
  const plain = dt.getData('text/plain') || '';
  if (plain.startsWith('gallery-item:')) return plain.slice('gallery-item:'.length);
  return '';
}

function readEffectType(dt) {
  return dt.getData('application/x-gallery-effect') || '';
}

export default function ShowTimeline({
  slides,
  effects = [],
  itemsById,
  selectedIndex,
  selectedViewIndex,
  selectedEffectIndex = -1,
  playhead,
  pxPerSec,
  onChangeSlides,
  onChangeEffects,
  onSelect,
  onSelectEffect,
  onPlayhead,
  onMoveKeyframe,
  onMoveKeyframeEnd,
}) {
  const scrollRef = useRef(null);
  const contentRef = useRef(null);
  const [ghost, setGhost] = useState(null);
  const [fxGhost, setFxGhost] = useState(null);
  const [binDrag, setBinDrag] = useState(false);
  const dragRef = useRef(null);

  const total = Math.max(20, Math.max(showDuration(slides), ...effects.map(effectEnd), 0) + DEFAULT_CLIP_DURATION);
  const width = Math.max(640, total * pxPerSec);
  const selected = selectedIndex >= 0 ? slides[selectedIndex] : null;

  const timeFromClientX = (clientX) => {
    const el = contentRef.current;
    if (!el) return 0;
    return Math.max(0, (clientX - el.getBoundingClientRect().left) / pxPerSec);
  };

  useEffect(() => {
    const onEnter = (e) => {
      const types = [...(e.dataTransfer?.types || [])];
      if (types.includes('application/x-gallery-item') || types.includes('application/x-gallery-effect')) {
        setBinDrag(true);
      }
    };
    const clear = () => {
      setBinDrag(false);
      setGhost(null);
      setFxGhost(null);
    };
    window.addEventListener('dragenter', onEnter);
    window.addEventListener('dragend', clear);
    window.addEventListener('drop', clear);
    return () => {
      window.removeEventListener('dragenter', onEnter);
      window.removeEventListener('dragend', clear);
      window.removeEventListener('drop', clear);
    };
  }, []);

  const onRulerPointer = (e) => {
    const pointerId = e.pointerId;
    const onMove = (ev) => {
      if (ev.pointerId !== pointerId) return;
      onPlayhead(round2(timeFromClientX(ev.clientX)));
    };
    const onUp = (ev) => {
      if (ev.pointerId !== pointerId) return;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    onPlayhead(round2(timeFromClientX(e.clientX)));
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const beginKfDrag = (e, vi) => {
    e.preventDefault();
    e.stopPropagation();
    onSelect(selectedIndex, vi);
    onPlayhead(round2(slideStart(selected) + (Number(selected.views?.[vi]?.time) || 0)));
    const pointerId = e.pointerId;
    const clipStart = slideStart(selected);
    const clipDur = numericDuration(selected);
    const onMove = (ev) => {
      if (ev.pointerId !== pointerId) return;
      const local = round2(Math.min(clipDur, Math.max(0, timeFromClientX(ev.clientX) - clipStart)));
      onMoveKeyframe?.(local);
    };
    const onUp = (ev) => {
      if (ev.pointerId !== pointerId) return;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      onMoveKeyframeEnd?.();
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const beginClipDrag = (e, index, mode) => {
    e.preventDefault();
    e.stopPropagation();
    const slide = slides[index];
    const pointerId = e.pointerId;
    dragRef.current = {
      kind: 'clip',
      id: pointerId,
      mode,
      index,
      startX: e.clientX,
      origStart: slideStart(slide),
      origDur: numericDuration(slide),
      origChannel: slideChannel(slide),
      origSlides: slides,
      origEffects: effects,
    };
    onSelect(index);
    const onMove = (ev) => {
      if (ev.pointerId !== pointerId) return;
      onItemPointerMove(ev);
    };
    const onUp = (ev) => {
      if (ev.pointerId !== pointerId) return;
      dragRef.current = null;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const beginFxDrag = (e, index, mode) => {
    e.preventDefault();
    e.stopPropagation();
    const fx = effects[index];
    const pointerId = e.pointerId;
    dragRef.current = {
      kind: 'fx',
      id: pointerId,
      mode,
      index,
      startX: e.clientX,
      origStart: effectStart(fx),
      origDur: effectDuration(fx),
      origEffects: effects,
    };
    onSelectEffect?.(index);
    const onMove = (ev) => {
      if (ev.pointerId !== pointerId) return;
      onItemPointerMove(ev);
    };
    const onUp = (ev) => {
      if (ev.pointerId !== pointerId) return;
      dragRef.current = null;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const onItemPointerMove = (e) => {
    const drag = dragRef.current;
    if (!drag || drag.id !== e.pointerId) return;
    const dx = (e.clientX - drag.startX) / pxPerSec;

    if (drag.kind === 'fx') {
      const next = drag.origEffects.map((fx) => ({ ...fx }));
      const cur = next[drag.index];
      if (drag.mode === 'move') {
        next[drag.index] = { ...cur, start: round2(Math.max(0, drag.origStart + dx)) };
      } else if (drag.mode === 'right') {
        next[drag.index] = { ...cur, duration: round2(Math.max(MIN_CLIP_DURATION, drag.origDur + dx)) };
      } else if (drag.mode === 'left') {
        const end = drag.origStart + drag.origDur;
        const start = round2(Math.max(0, Math.min(end - MIN_CLIP_DURATION, drag.origStart + dx)));
        next[drag.index] = { ...cur, start, duration: round2(end - start) };
      }
      onChangeEffects(next);
      onPlayhead(effectStart(next[drag.index]));
      return;
    }

    const body = scrollRef.current;
    let channel = drag.origChannel;
    if (body && drag.mode === 'move') {
      body.querySelectorAll('[data-channel]').forEach((node) => {
        const r = node.getBoundingClientRect();
        if (e.clientY >= r.top && e.clientY <= r.bottom) channel = Number(node.dataset.channel);
      });
    }

    let next = drag.origSlides.map((s) => ({ ...s }));
    let nextFx = drag.origEffects.map((fx) => ({ ...fx }));
    const i = drag.index;
    const clip = next[i];

    if (drag.mode === 'move') {
      const proposed = round2(drag.origStart + dx);
      if (channel !== drag.origChannel) {
        const dur = drag.origDur;
        let start = Math.max(0, proposed);
        start = Math.max(start, leftNeighborEnd(next, channel, i, start + 0.0001));
        const right = rightNeighborStart(next, channel, i, start);
        if (Number.isFinite(right)) start = Math.min(start, Math.max(0, right - dur));
        next[i] = { ...clip, start: round2(start), channel };
      } else if (proposed >= drag.origStart) {
        const delta = proposed - drag.origStart;
        next = rippleAfter(next, drag.origStart, delta, i);
        nextFx = rippleEffects(nextFx, drag.origStart, delta);
        next[i] = { ...next[i], start: round2(proposed), channel };
      } else {
        const dur = drag.origDur;
        let start = Math.max(0, proposed);
        start = Math.max(start, leftNeighborEnd(next, channel, i, drag.origStart));
        const right = rightNeighborStart(next, channel, i, drag.origStart);
        if (Number.isFinite(right)) start = Math.min(start, right - dur);
        next[i] = { ...clip, start: round2(Math.max(0, start)), channel };
      }
    } else if (drag.mode === 'right') {
      const dur = round2(Math.max(MIN_CLIP_DURATION, drag.origDur + dx));
      const start = drag.origStart;
      const right = rightNeighborStart(next, slideChannel(clip), i, start + 0.0001);
      if (Number.isFinite(right) && start + dur > right) {
        const overlap = start + dur - right;
        next = rippleAfter(next, right - 0.0001, overlap, i);
        nextFx = rippleEffects(nextFx, right - 0.0001, overlap);
      }
      next[i] = {
        ...next[i],
        duration: dur,
        views: scaleViews(next[i].views, drag.origDur, dur),
      };
    } else if (drag.mode === 'left') {
      const end = drag.origStart + drag.origDur;
      let start = round2(drag.origStart + dx);
      start = Math.max(start, leftNeighborEnd(next, slideChannel(clip), i, drag.origStart));
      start = Math.min(start, end - MIN_CLIP_DURATION);
      start = Math.max(0, start);
      const dur = round2(end - start);
      next[i] = {
        ...next[i],
        start,
        duration: dur,
        views: scaleViews(next[i].views, drag.origDur, dur),
      };
    }

    onChangeSlides(next);
    onChangeEffects(nextFx);
    if (drag.mode === 'move' || drag.mode === 'left') onPlayhead(slideStart(next[i]));
  };

  const onTrackDragOver = (e, channel) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    if (readEffectType(e.dataTransfer)) return;
    const t = timeFromClientX(e.clientX);
    const gap = gapAt(slides, channel, t);
    setGhost({ channel, start: gap.start, duration: dropDuration(gap.open) });
  };

  const onTrackDrop = (e, channel) => {
    e.preventDefault();
    setGhost(null);
    const itemId = readItemId(e.dataTransfer);
    if (!itemId) return;
    const t = timeFromClientX(e.clientX);
    const gap = gapAt(slides, channel, t);
    if (gap.open < MIN_CLIP_DURATION) return;
    const clip = newClipFromItem(itemId, gap.start, gap.open, channel);
    const next = [...slides, clip];
    onChangeSlides(next);
    onSelect(next.length - 1);
    onPlayhead(clip.start);
  };

  const onFxDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    const t = timeFromClientX(e.clientX);
    setFxGhost({ start: t, duration: DEFAULT_EFFECT_DURATION });
  };

  const onFxDrop = (e) => {
    e.preventDefault();
    setFxGhost(null);
    const type = readEffectType(e.dataTransfer);
    if (!type) return;
    const t = timeFromClientX(e.clientX);
    const fx = newEffect(type, t, DEFAULT_EFFECT_DURATION);
    const next = [...effects, fx];
    onChangeEffects(next);
    onSelectEffect?.(next.length - 1);
    onPlayhead(fx.start);
  };

  const markerLeft = playhead * pxPerSec;
  const rulerMarks = useMemo(() => ticks(total, pxPerSec), [total, pxPerSec]);

  return (
    <div className="flex min-h-0 flex-col border-t border-stone-200 bg-stone-50">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto">
        <div ref={contentRef} style={{ width }} className="relative min-w-full">
          <div
            className="sticky top-0 z-10 h-8 cursor-ew-resize border-b border-stone-300 bg-white"
            onPointerDown={onRulerPointer}
            title="Drag to move the playhead"
          >
            {rulerMarks.map((t) => (
              <div
                key={t}
                className="absolute top-0 h-full border-l border-stone-200"
                style={{ left: t * pxPerSec }}
              >
                <span className="pointer-events-none absolute left-1 top-1 text-[10px] text-stone-500">
                  {formatTime(t)}
                </span>
              </div>
            ))}
            {selected
              ? (selected.views || []).map((v, vi) => {
                  const left = (slideStart(selected) + (Number(v.time) || 0)) * pxPerSec;
                  return (
                    <button
                      key={vi}
                      type="button"
                      className={`absolute top-1 z-20 h-3 w-3 -translate-x-1/2 rotate-45 cursor-ew-resize border ${
                        vi === selectedViewIndex
                          ? 'border-emerald-800 bg-emerald-500'
                          : 'border-emerald-700 bg-emerald-300'
                      }`}
                      style={{ left }}
                      title={`${v.name || `Keyframe ${vi + 1}`} — drag to move`}
                      onPointerDown={(e) => beginKfDrag(e, vi)}
                    />
                  );
                })
              : null}
            <div
              className="pointer-events-none absolute top-0 z-30 h-full w-px bg-rose-500"
              style={{ left: markerLeft }}
            />
          </div>

          {CHANNELS.map((ch) => (
            <div
              key={ch.id}
              data-channel={ch.id}
              className="relative h-20 border-b border-stone-200 bg-stone-100"
              onDragOver={(e) => onTrackDragOver(e, ch.id)}
              onDrop={(e) => onTrackDrop(e, ch.id)}
            >
              <div
                className="absolute inset-0 z-[1]"
                onDragOver={(e) => onTrackDragOver(e, ch.id)}
                onDrop={(e) => onTrackDrop(e, ch.id)}
              />
              <div className="pointer-events-none absolute left-0 top-0 z-10 bg-stone-200/90 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-stone-600">
                {ch.label}
              </div>
              {ghost && ghost.channel === ch.id ? (
                <div
                  className="pointer-events-none absolute top-1.5 z-[2] h-[68px] rounded border border-dashed border-emerald-500 bg-emerald-200/40"
                  style={{
                    left: ghost.start * pxPerSec,
                    width: Math.max(8, ghost.duration * pxPerSec),
                  }}
                />
              ) : null}
              {slides.map((s, i) => {
                if (slideChannel(s) !== ch.id) return null;
                const item = itemsById[s.item_id];
                const left = slideStart(s) * pxPerSec;
                const w = Math.max(8, numericDuration(s) * pxPerSec);
                const thumb = item ? thumbSrc(item) : '';
                const selectedClip = i === selectedIndex;
                return (
                  <div
                    key={s.clip_id || i}
                    className={`absolute top-1.5 h-[68px] overflow-hidden rounded border shadow-sm ${
                      binDrag ? 'pointer-events-none z-[2]' : selectedClip ? 'z-20' : 'z-10'
                    } ${selectedClip ? 'border-emerald-600 ring-2 ring-emerald-400' : 'border-stone-400'}`}
                    style={{
                      left,
                      width: w,
                      backgroundImage: thumb ? `url(${thumb})` : undefined,
                      backgroundRepeat: 'repeat-x',
                      backgroundSize: 'auto 100%',
                      backgroundColor: '#d6d3d1',
                    }}
                    onPointerDown={(e) => beginClipDrag(e, i, 'move')}
                  >
                    <div
                      className="absolute inset-y-0 left-0 z-10 w-1.5 cursor-ew-resize bg-black/30 hover:bg-emerald-500"
                      onPointerDown={(e) => beginClipDrag(e, i, 'left')}
                    />
                    <div
                      className="absolute inset-y-0 right-0 z-10 w-1.5 cursor-ew-resize bg-black/30 hover:bg-emerald-500"
                      onPointerDown={(e) => beginClipDrag(e, i, 'right')}
                    />
                    <div className="pointer-events-none absolute inset-x-0 bottom-0 truncate bg-black/55 px-1.5 py-0.5 text-[10px] text-white">
                      {item?.title || item?.filename || 'Clip'} · {numericDuration(s).toFixed(1)}s
                    </div>
                  </div>
                );
              })}
            </div>
          ))}

          <div
            className="relative h-14 border-b border-stone-200 bg-stone-50"
            onDragOver={onFxDragOver}
            onDrop={onFxDrop}
          >
            <div className="pointer-events-none absolute left-0 top-0 z-10 bg-stone-200/90 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-stone-600">
              FX
            </div>
            {fxGhost ? (
              <div
                className="pointer-events-none absolute top-1.5 h-10 rounded border border-dashed border-violet-500 bg-violet-200/50"
                style={{
                  left: fxGhost.start * pxPerSec,
                  width: Math.max(8, fxGhost.duration * pxPerSec),
                }}
              />
            ) : null}
            {effects.map((fx, i) => (
              <div
                key={fx.id || i}
                className={`absolute top-1.5 h-10 overflow-hidden rounded border text-[10px] font-medium text-white ${
                  FX_COLORS[fx.type] || 'bg-stone-500 border-stone-700'
                } ${selectedEffectIndex === i ? 'ring-2 ring-emerald-400' : ''}`}
                style={{
                  left: effectStart(fx) * pxPerSec,
                  width: Math.max(8, effectDuration(fx) * pxPerSec),
                }}
                onPointerDown={(e) => beginFxDrag(e, i, 'move')}
              >
                <div
                  className="absolute inset-y-0 left-0 z-10 w-1.5 cursor-ew-resize bg-black/30"
                  onPointerDown={(e) => beginFxDrag(e, i, 'left')}
                />
                <div
                  className="absolute inset-y-0 right-0 z-10 w-1.5 cursor-ew-resize bg-black/30"
                  onPointerDown={(e) => beginFxDrag(e, i, 'right')}
                />
                <div className="pointer-events-none px-2 py-2 capitalize">{fx.type.replace('-', ' ')}</div>
              </div>
            ))}
          </div>

          <div
            className="pointer-events-none absolute bottom-0 top-8 z-30 w-px bg-rose-500"
            style={{ left: markerLeft }}
          />
        </div>
      </div>
    </div>
  );
}

export function EffectPalette({ onAddAtPlayhead }) {
  return (
    <div className="flex items-center gap-2">
      {EFFECT_TYPES.map((fx) => (
        <button
          key={fx.type}
          type="button"
          draggable
          onDragStart={(e) => {
            e.dataTransfer.setData('application/x-gallery-effect', fx.type);
            e.dataTransfer.effectAllowed = 'copy';
          }}
          onClick={() => onAddAtPlayhead?.(fx.type)}
          className={`rounded border px-2 py-1 text-[11px] font-medium text-white ${
            FX_COLORS[fx.type] || 'bg-stone-500'
          }`}
          title={`Click to add at playhead, or drag onto the FX bar`}
        >
          {fx.label}
        </button>
      ))}
    </div>
  );
}
