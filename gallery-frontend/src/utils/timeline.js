export const DEFAULT_CLIP_DURATION = 10;
export const MIN_CLIP_DURATION = 0.2;

export function round2(n) {
  return Math.round(Number(n) * 100) / 100;
}

export function newClipId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return `clip-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function numericDuration(slide, fallback = DEFAULT_CLIP_DURATION) {
  if (slide?.duration === 'video' || slide?.duration === 'end') return fallback;
  const n = Number(slide?.duration);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

export function slideStart(slide) {
  const n = Number(slide?.start);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

export function slideChannel(slide) {
  return slide?.channel === 1 ? 1 : 0;
}

export function slideEnd(slide) {
  return slideStart(slide) + numericDuration(slide);
}

export function showDuration(slides) {
  return (slides || []).reduce((max, s) => Math.max(max, slideEnd(s)), 0);
}

export function defaultViews(duration = DEFAULT_CLIP_DURATION) {
  const d = Number(duration) || DEFAULT_CLIP_DURATION;
  return [
    {
      name: 'Start',
      time: 0,
      zoom: 1,
      zoomX: 1,
      zoomY: 1,
      x: 0.5,
      y: 0.5,
      rotation: 0,
      opacity: 1,
      pitch: 0,
      yaw: 0,
      anchorX: 0.5,
      anchorY: 0.5,
      cropLeft: 0,
      cropRight: 0,
      cropTop: 0,
      cropBottom: 0,
    },
    {
      name: 'End',
      time: d,
      zoom: 1.15,
      zoomX: 1.15,
      zoomY: 1.15,
      x: 0.5,
      y: 0.5,
      rotation: 0,
      opacity: 1,
      pitch: 0,
      yaw: 0,
      anchorX: 0.5,
      anchorY: 0.5,
      cropLeft: 0,
      cropRight: 0,
      cropTop: 0,
      cropBottom: 0,
    },
  ];
}

export function scaleViews(views, oldDur, newDur) {
  const from = oldDur > 0 ? oldDur : 1;
  const f = newDur / from;
  return (views || []).map((v) => ({
    ...v,
    time: round2(Math.max(0, (Number(v.time) || 0) * f)),
  }));
}

export function normalizeSlides(slides) {
  const list = slides || [];
  const hasStart = list.some((s) => s.start != null);
  let cursor = 0;
  return list.map((s, i) => {
    const duration = numericDuration(s);
    const start = hasStart ? slideStart(s) : cursor;
    if (!hasStart) cursor += duration;
    return {
      ...s,
      clip_id: s.clip_id || newClipId(),
      channel: slideChannel(s),
      start: round2(start),
      duration,
      views: s.views?.length ? s.views : defaultViews(duration),
    };
  });
}

export function clipsOnChannel(slides, channel, exceptIndex = -1) {
  return (slides || [])
    .map((s, i) => ({ s, i }))
    .filter(({ s, i }) => i !== exceptIndex && slideChannel(s) === channel)
    .sort((a, b) => slideStart(a.s) - slideStart(b.s) || a.i - b.i);
}

export function leftNeighborEnd(slides, channel, exceptIndex, beforeTime) {
  let end = 0;
  for (const { s } of clipsOnChannel(slides, channel, exceptIndex)) {
    if (slideStart(s) < beforeTime) end = Math.max(end, slideEnd(s));
  }
  return end;
}

export function rightNeighborStart(slides, channel, exceptIndex, afterTime) {
  let start = Infinity;
  for (const { s } of clipsOnChannel(slides, channel, exceptIndex)) {
    if (slideStart(s) >= afterTime) start = Math.min(start, slideStart(s));
  }
  return start;
}

/** Gap on a channel at dropTime. If inside a clip, snap to that clip's end. */
export function gapAt(slides, channel, dropTime, exceptIndex = -1) {
  let t = Math.max(0, dropTime);
  const clips = clipsOnChannel(slides, channel, exceptIndex);
  for (const { s } of clips) {
    const a = slideStart(s);
    const b = slideEnd(s);
    if (t >= a && t < b - 0.001) t = b;
  }
  let nextStart = Infinity;
  for (const { s } of clips) {
    const a = slideStart(s);
    if (a >= t) nextStart = Math.min(nextStart, a);
  }
  const open = nextStart - t;
  return { start: round2(t), open };
}

export function dropDuration(open) {
  if (!Number.isFinite(open) || open > DEFAULT_CLIP_DURATION) return DEFAULT_CLIP_DURATION;
  return round2(Math.max(MIN_CLIP_DURATION, open));
}

export function rippleAfter(slides, fromTime, delta, exceptIndex = -1) {
  if (!delta) return slides;
  return slides.map((s, i) => {
    if (i === exceptIndex) return s;
    if (slideStart(s) > fromTime) {
      return { ...s, start: round2(Math.max(0, slideStart(s) + delta)) };
    }
    return s;
  });
}

export function activeClips(slides, time) {
  return (slides || [])
    .map((s, i) => ({ s, i }))
    .filter(({ s }) => time >= slideStart(s) - 0.0001 && time <= slideEnd(s) + 0.0001)
    .sort((a, b) => slideChannel(a.s) - slideChannel(b.s) || a.i - b.i);
}

export function clipAt(slides, time, preferIndex) {
  const hits = activeClips(slides, time);
  if (!hits.length) return null;
  const preferred = hits.find((h) => h.i === preferIndex);
  if (preferred) return preferred;
  // Channel A (0) is the top track in the preview.
  return [...hits].sort((a, b) => slideChannel(a.s) - slideChannel(b.s))[0];
}

export const EFFECT_TYPES = [
  { type: 'fade-in', label: 'Fade in' },
  { type: 'fade-out', label: 'Fade out' },
  { type: 'blend', label: 'Blend' },
];

export const DEFAULT_EFFECT_DURATION = 1;

export function effectStart(fx) {
  const n = Number(fx?.start);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

export function effectDuration(fx) {
  const n = Number(fx?.duration);
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_EFFECT_DURATION;
}

export function effectEnd(fx) {
  return effectStart(fx) + effectDuration(fx);
}

export function newEffect(type, start, duration = DEFAULT_EFFECT_DURATION) {
  return {
    id: newClipId(),
    type,
    start: round2(Math.max(0, start)),
    duration: round2(Math.max(MIN_CLIP_DURATION, duration)),
  };
}

export function rippleEffects(effects, fromTime, delta) {
  if (!delta) return effects || [];
  return (effects || []).map((fx) => {
    if (effectStart(fx) > fromTime) {
      return { ...fx, start: round2(Math.max(0, effectStart(fx) + delta)) };
    }
    return fx;
  });
}

export function applyTimelineOpacity(slide, time, baseOpacity, effects) {
  let opacity = Number.isFinite(Number(baseOpacity)) ? Number(baseOpacity) : 1;
  const local = time - slideStart(slide);
  const dur = numericDuration(slide);
  for (const tr of slide.transitions || []) {
    const td = Math.max(0.0001, Number(tr.duration) || 1);
    if (tr.type === 'fade-in' && local < td) opacity *= local / td;
    if (tr.type === 'fade-out' && local > dur - td) opacity *= Math.max(0, (dur - local) / td);
  }
  for (const fx of effects || []) {
    const a = effectStart(fx);
    const b = effectEnd(fx);
    if (time < a - 0.0001 || time > b + 0.0001) continue;
    const u = Math.min(1, Math.max(0, (time - a) / Math.max(0.0001, effectDuration(fx))));
    const ch = slideChannel(slide);
    if (fx.type === 'fade-in') opacity *= u;
    else if (fx.type === 'fade-out') opacity *= 1 - u;
    else if (fx.type === 'blend') opacity *= ch === 0 ? 1 - u : u;
  }
  return Math.min(1, Math.max(0, opacity));
}

export function formatTime(sec) {
  const t = Math.max(0, Number(sec) || 0);
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, '0')}`;
}

export function newClipFromItem(itemId, start, duration, channel) {
  const d = dropDuration(duration);
  return {
    clip_id: newClipId(),
    item_id: itemId,
    start: round2(start),
    duration: d,
    channel,
    muted: true,
    transitions: [],
    views: defaultViews(d),
  };
}
