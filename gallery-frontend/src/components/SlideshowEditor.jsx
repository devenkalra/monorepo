import React, { useEffect, useMemo, useRef, useState } from 'react';
import api from '../services/api';
import { thumbSrc } from './Carousel';
import { sampleView, viewZoomX, viewZoomY } from '../utils/kenBurns';
import ShowTimeline, { EffectPalette } from './ShowTimeline';
import TimelineStage from './TimelineStage';
import JsonDebugPanel from './JsonDebugPanel';
import {
  clipAt,
  effectDuration,
  effectStart,
  formatTime,
  newClipId,
  newEffect,
  normalizeSlides,
  numericDuration,
  round2,
  slideEnd,
  slideStart,
  showDuration,
} from '../utils/timeline';

function slugify(s) {
  return (s || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 80) || 'show';
}

function uniqueSlug(base, existing, currentId) {
  const taken = new Set(
    (existing || [])
      .filter((s) => s.id !== currentId)
      .map((s) => (s.slug || '').toLowerCase())
  );
  let slug = slugify(base);
  if (!taken.has(slug)) return slug;
  let n = 2;
  while (taken.has(`${slug}-${n}`)) n += 1;
  return `${slug}-${n}`;
}

function slideResolves(slide, itemsById) {
  if (!slide) return false;
  if (slide.url) return true;
  return Boolean(slide.item_id && itemsById[slide.item_id]);
}

function viewParams(view) {
  if (!view) return {};
  const zoomX = viewZoomX(view);
  const zoomY = viewZoomY(view);
  return {
    name: view.name || '',
    zoom: zoomX,
    zoomX,
    zoomY,
    x: view.x,
    y: view.y,
    rotation: view.rotation,
    opacity: view.opacity,
    pitch: view.pitch ?? 0,
    yaw: view.yaw ?? 0,
    anchorX: view.anchorX ?? view.x ?? 0.5,
    anchorY: view.anchorY ?? view.y ?? 0.5,
    cropLeft: view.cropLeft ?? 0,
    cropRight: view.cropRight ?? 0,
    cropTop: view.cropTop ?? 0,
    cropBottom: view.cropBottom ?? 0,
  };
}

const numInputCls = 'min-w-0 rounded border border-stone-300 px-1 py-0.5 text-xs';

function CompactNum({ className = 'w-12', value, step = 0.01, min, max, onChange }) {
  return (
    <input
      type="number"
      className={`${numInputCls} ${className}`}
      value={Number.isFinite(Number(value)) ? value : 0}
      step={step}
      min={min}
      max={max}
      onChange={(e) => onChange(Number(e.target.value))}
    />
  );
}

function SliderRow({ label, value, min, max, step, onChange }) {
  return (
    <div className="flex items-center gap-1 text-[11px] text-stone-600">
      <span className="w-11 shrink-0">{label}</span>
      <input
        type="range"
        className="min-w-0 flex-1 accent-emerald-700"
        min={min}
        max={max}
        step={step}
        value={value ?? 0}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <CompactNum value={value} step={step} min={min} max={max} onChange={onChange} />
    </div>
  );
}

function PanelToggle({ title, open, onToggle, children }) {
  return (
    <div className="rounded border border-stone-200">
      <button
        type="button"
        className="flex w-full items-center justify-between px-1.5 py-1 text-[11px] font-medium uppercase tracking-wide text-stone-600 hover:bg-stone-50"
        onClick={onToggle}
      >
        <span>{title}</span>
        <span className={`text-[10px] text-stone-400 ${open ? 'rotate-90' : ''} inline-block`}>▸</span>
      </button>
      {open ? <div className="space-y-1.5 border-t border-stone-100 px-1.5 py-1.5">{children}</div> : null}
    </div>
  );
}

function initialConfig(show, items) {
  const itemsById = Object.fromEntries((items || []).map((i) => [i.id, i]));
  const base = {
    version: 1,
    loop: true,
    defaults: { duration: 10, transition: 1 },
    ...(show?.config || {}),
  };
  const raw = (base.slides || []).filter((s) => slideResolves(s, itemsById));
  return { ...base, slides: normalizeSlides(raw), effects: Array.isArray(base.effects) ? base.effects : [] };
}

export default function SlideshowEditor({ gallery, show, onSaved, onClose }) {
  const [savedShow, setSavedShow] = useState(show || null);
  const [title, setTitle] = useState(show?.title || 'Show');
  const [slug, setSlug] = useState(
    show?.slug || uniqueSlug(show?.title || 'show', gallery.shows || [], show?.id)
  );
  const [config, setConfig] = useState(() => initialConfig(show, gallery.items || []));
  const [selected, setSelected] = useState(config.slides.length ? 0 : -1);
  const [selectedView, setSelectedView] = useState(0);
  const [selectedEffect, setSelectedEffect] = useState(-1);
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(null);
  const [pxPerSec, setPxPerSec] = useState(40);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const playBounds = useRef({ start: 0, end: 0 });
  const playheadRef = useRef(0);
  const selectedViewRef = useRef(0);
  const clipboardRef = useRef(null);
  const slidesRef = useRef([]);
  const [hasClipboard, setHasClipboard] = useState(false);
  const [transformOpen, setTransformOpen] = useState(true);
  const [cropOpen, setCropOpen] = useState(false);
  const [zoomSync, setZoomSync] = useState(true);
  const [jsonOpen, setJsonOpen] = useState(false);

  const itemsById = useMemo(
    () => Object.fromEntries((gallery.items || []).map((i) => [i.id, i])),
    [gallery.items]
  );
  const slides = config.slides || [];
  const effects = config.effects || [];
  const slide = selected >= 0 ? slides[selected] : null;
  const views = slide?.views || [];
  const view = views[selectedView] || views[0];
  const showEnd = showDuration(slides);

  playheadRef.current = playhead;
  selectedViewRef.current = selectedView;
  slidesRef.current = slides;

  const setSlides = (next) => {
    setConfig((c) => ({ ...c, slides: next }));
  };

  const setEffects = (next) => {
    setConfig((c) => ({ ...c, effects: next }));
  };

  const updateSlide = (index, patch) => {
    setConfig((c) => {
      const list = [...c.slides];
      if (!list[index]) return c;
      list[index] = { ...list[index], ...patch };
      return { ...c, slides: list };
    });
  };

  const updateView = (patch) => {
    if (selected < 0 || !slide) return;
    const nextViews = [...(slide.views || [])];
    if (!nextViews[selectedView]) return;
    nextViews[selectedView] = { ...nextViews[selectedView], ...patch };
    updateSlide(selected, { views: nextViews });
  };

  const setZoomX = (n) => {
    const z = Math.max(0.2, n);
    if (zoomSync) updateView({ zoom: z, zoomX: z, zoomY: z });
    else updateView({ zoom: z, zoomX: z });
  };

  const setZoomY = (n) => {
    const z = Math.max(0.2, n);
    if (zoomSync) updateView({ zoom: z, zoomX: z, zoomY: z });
    else updateView({ zoomY: z });
  };

  const setCrop = (side, n) => {
    const opp = { cropLeft: 'cropRight', cropRight: 'cropLeft', cropTop: 'cropBottom', cropBottom: 'cropTop' }[side];
    const other = Number(view?.[opp]) || 0;
    updateView({ [side]: Math.max(0, Math.min(Number(n) || 0, 0.95, 0.98 - other)) });
  };

  const selectClip = (index, viewIndex) => {
    setSelected(index);
    setSelectedEffect(-1);
    if (typeof viewIndex === 'number') setSelectedView(viewIndex);
    setPlaying(null);
  };

  const selectEffect = (index) => {
    setSelectedEffect(index);
    setSelected(-1);
    setPlaying(null);
  };

  const onPlayhead = (t) => {
    setPlayhead(t);
    if (playing) setPlaying(null);
    if (selectedEffect >= 0) return;
    const hit = clipAt(slides, t, selected);
    if (hit && (selected < 0 || t < slideStart(slide) || t > slideEnd(slide))) {
      setSelected(hit.i);
    }
  };

  const addOrSelectKeyframe = (localTime) => {
    if (selected < 0 || !slide) return;
    const dur = numericDuration(slide);
    const t = round2(Math.min(dur, Math.max(0, localTime)));
    const existing = (slide.views || []).findIndex(
      (v) => Math.abs((Number(v.time) || 0) - t) < 0.12
    );
    if (existing >= 0) {
      setSelectedView(existing);
      return;
    }
    const sampled = sampleView(slide.views, t, dur, 'linear');
    const kf = {
      ...viewParams(sampled),
      name: '',
      time: t,
    };
    const nextViews = [...(slide.views || []), kf].sort(
      (a, b) => (Number(a.time) || 0) - (Number(b.time) || 0)
    );
    updateSlide(selected, { views: nextViews });
    setSelectedView(nextViews.findIndex((v) => v === kf));
  };

  const moveSelectedKeyframe = (localTime) => {
    if (selected < 0) return;
    const vi = selectedViewRef.current;
    setConfig((c) => {
      const list = [...c.slides];
      const s = list[selected];
      if (!s || !s.views?.[vi]) return c;
      const dur = numericDuration(s);
      const t = round2(Math.min(dur, Math.max(0, localTime)));
      const views = [...s.views];
      views[vi] = { ...views[vi], time: t };
      list[selected] = { ...s, views };
      return { ...c, slides: list };
    });
    const s = slides[selected];
    if (s) setPlayhead(round2(slideStart(s) + round2(Math.min(numericDuration(s), Math.max(0, localTime)))));
  };

  const commitKeyframeOrder = () => {
    if (selected < 0) return;
    const s = slidesRef.current[selected];
    if (!s?.views?.length) return;
    const vi = selectedViewRef.current;
    const kf = s.views[vi];
    const views = [...s.views].sort((a, b) => (Number(a.time) || 0) - (Number(b.time) || 0));
    updateSlide(selected, { views });
    const idx = kf ? views.indexOf(kf) : vi;
    if (idx >= 0) {
      selectedViewRef.current = idx;
      setSelectedView(idx);
    }
  };

  const copyKeyframe = () => {
    if (!view) return;
    clipboardRef.current = viewParams(view);
    setHasClipboard(true);
  };

  const pasteKeyframe = () => {
    const src = clipboardRef.current;
    if (!src || selected < 0 || !slide) return;
    const dur = numericDuration(slide);
    let t = round2(Math.min(dur, Math.max(0, playhead - slideStart(slide))));
    const used = new Set((slide.views || []).map((v) => round2(Number(v.time) || 0)));
    while (used.has(t) && t < dur) t = round2(t + 0.05);
    if (used.has(t)) {
      t = round2(Math.max(0, t - 0.05));
      while (used.has(t) && t > 0) t = round2(t - 0.05);
    }
    const kf = {
      ...src,
      name: src.name ? `${String(src.name).replace(/ copy$/, '')} copy` : '',
      time: t,
    };
    const nextViews = [...(slide.views || []), kf].sort(
      (a, b) => (Number(a.time) || 0) - (Number(b.time) || 0)
    );
    updateSlide(selected, { views: nextViews });
    setSelectedView(nextViews.findIndex((v) => v === kf));
    setPlayhead(round2(slideStart(slide) + t));
  };

  const removeKeyframe = () => {
    if (!slide || views.length <= 1) return;
    const next = views.filter((_, i) => i !== selectedView);
    updateSlide(selected, { views: next });
    setSelectedView(Math.max(0, selectedView - 1));
  };

  const removeClip = () => {
    if (selected < 0) return;
    const next = slides.filter((_, i) => i !== selected);
    setSlides(next);
    setSelected(next.length ? Math.min(selected, next.length - 1) : -1);
    setSelectedView(0);
  };

  const removeEffect = () => {
    if (selectedEffect < 0) return;
    const next = effects.filter((_, i) => i !== selectedEffect);
    setEffects(next);
    setSelectedEffect(next.length ? Math.min(selectedEffect, next.length - 1) : -1);
  };

  const startPlay = (mode) => {
    if (mode === 'slide') {
      if (!slide) return;
      const start = slideStart(slide);
      const end = slideEnd(slide);
      playBounds.current = { start, end };
      setPlayhead(start);
      setPlaying('slide');
      return;
    }
    const end = Math.max(playhead, showEnd);
    playBounds.current = { start: playhead, end };
    setPlaying('show');
  };

  useEffect(() => {
    if (!playing) return undefined;
    let last = performance.now();
    let raf = 0;
    const tick = (now) => {
      const dt = (now - last) / 1000;
      last = now;
      const { end } = playBounds.current;
      const next = playheadRef.current + dt;
      if (next >= end) {
        setPlayhead(end);
        setPlaying(null);
        return;
      }
      setPlayhead(round2(next));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  useEffect(() => {
    if (selectedView >= views.length) setSelectedView(Math.max(0, views.length - 1));
  }, [views.length, selectedView]);

  useEffect(() => {
    if (!view) return;
    if (Math.abs(viewZoomX(view) - viewZoomY(view)) > 0.001) setZoomSync(false);
  }, [selected, selectedView]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === ' ') {
        e.preventDefault();
        if (playing) {
          setPlaying(null);
        } else {
          playBounds.current = { start: playhead, end: Math.max(playhead + 0.05, showEnd) };
          setPlaying('show');
        }
      } else if ((e.key === 'c' || e.key === 'C') && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        copyKeyframe();
      } else if ((e.key === 'v' || e.key === 'V') && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        pasteKeyframe();
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (selectedEffect >= 0) {
          e.preventDefault();
          removeEffect();
        } else if (selected >= 0) {
          e.preventDefault();
          if (e.shiftKey) removeKeyframe();
          else removeClip();
        }
      } else if (e.key === 'Escape') {
        if (playing) setPlaying(null);
        else if (jsonOpen) setJsonOpen(false);
        else onClose?.();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const nextSlug = uniqueSlug(slug || title || 'show', gallery.shows || [], savedShow?.id);
      if (nextSlug !== slug) setSlug(nextSlug);
      const kept = (config.slides || [])
        .filter((s) => slideResolves(s, itemsById))
        .map((s) => ({ ...s, clip_id: s.clip_id || newClipId() }))
        .sort((a, b) => slideStart(a) - slideStart(b) || (a.channel || 0) - (b.channel || 0));
      const nextConfig = { ...config, slides: kept, effects: config.effects || [] };
      setConfig(nextConfig);
      const body = {
        gallery: gallery.id,
        title,
        slug: nextSlug,
        config: nextConfig,
      };
      const data = savedShow?.id
        ? await api.json(`/api/gallery/shows/${savedShow.id}/`, { method: 'PATCH', body: JSON.stringify(body) })
        : await api.json('/api/gallery/shows/', { method: 'POST', body: JSON.stringify(body) });
      setSavedShow(data);
      onSaved?.(data);
    } catch (e) {
      setError(e.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const onMediaDragStart = (e, item) => {
    e.dataTransfer.setData('application/x-gallery-item', item.id);
    e.dataTransfer.setData('text/plain', `gallery-item:${item.id}`);
    e.dataTransfer.effectAllowed = 'copy';
  };

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-stone-100">
      <header className="flex flex-wrap items-center gap-3 border-b border-stone-200 bg-white px-4 py-2">
        <h2 className="text-lg font-semibold text-stone-900">Slideshow editor</h2>
        <input
          className="rounded border border-stone-300 px-2 py-1 text-sm"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title"
        />
        <input
          className="w-36 rounded border border-stone-300 px-2 py-1 text-sm"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          placeholder="slug"
        />
        <label className="flex items-center gap-1 text-sm text-stone-600">
          <input
            type="checkbox"
            checked={!!config.loop}
            onChange={(e) => setConfig((c) => ({ ...c, loop: e.target.checked }))}
          />
          Loop
        </label>
        <span className="text-xs text-stone-500">{formatTime(playhead)}</span>
        <div className="ml-auto flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
            disabled={!slide}
            onClick={() => startPlay('slide')}
          >
            Preview slide
          </button>
          <button type="button" className="rounded border px-3 py-1.5 text-sm" onClick={() => startPlay('show')}>
            {playing === 'show' ? 'Playing…' : 'Play from marker'}
          </button>
          {playing ? (
            <button type="button" className="rounded border px-3 py-1.5 text-sm" onClick={() => setPlaying(null)}>
              Stop
            </button>
          ) : null}
          <button
            type="button"
            className="rounded border px-3 py-1.5 text-sm"
            onClick={() => setJsonOpen((o) => !o)}
          >
            {jsonOpen ? 'Hide JSON' : 'Show JSON'}
          </button>
          <button
            type="button"
            className="rounded bg-emerald-700 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            disabled={saving}
            onClick={save}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="rounded border px-3 py-1.5 text-sm" onClick={onClose}>
            Close
          </button>
        </div>
      </header>
      {error ? <div className="bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div> : null}

      <div className="grid min-h-0 flex-1 grid-rows-[minmax(180px,38%)_1fr]">
        <div className="grid min-h-0 grid-cols-1 md:grid-cols-[300px_1fr]">
          <aside className="min-h-0 overflow-auto border-r border-stone-200 bg-white p-2">
            {selectedEffect >= 0 && effects[selectedEffect] ? null : (
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="text-xs font-medium uppercase tracking-wide text-stone-500">Keyframe</div>
                <button
                  type="button"
                  title="Add keyframe at playhead"
                  disabled={!slide}
                  className="inline-flex items-center gap-1 rounded border border-emerald-600 px-1.5 py-0.5 text-emerald-800 disabled:opacity-40"
                  onClick={() => addOrSelectKeyframe(Math.max(0, playhead - slideStart(slide || { start: 0 })))}
                >
                  <span className="inline-block h-2.5 w-2.5 rotate-45 border border-emerald-700 bg-emerald-400" />
                  <span className="text-[11px] font-medium">Add</span>
                </button>
              </div>
            )}
            {selectedEffect >= 0 && effects[selectedEffect] ? (
              <div className="space-y-2 text-sm">
                <div className="text-xs font-medium uppercase tracking-wide text-stone-500">Effect</div>
                <div className="capitalize text-stone-800">
                  {(effects[selectedEffect].type || 'effect').replace('-', ' ')}
                </div>
                <div className="text-xs text-stone-500">
                  {formatTime(effectStart(effects[selectedEffect]))}–
                  {formatTime(effectStart(effects[selectedEffect]) + effectDuration(effects[selectedEffect]))}
                </div>
                <button
                  type="button"
                  className="rounded border px-2 py-1 text-xs text-red-700"
                  onClick={removeEffect}
                >
                  Delete effect
                </button>
                <p className="text-[11px] text-stone-400">Delete or Backspace removes the selected effect.</p>
              </div>
            ) : slide && view ? (
              <div className="space-y-1.5 text-sm">
                <div className="text-[11px] text-stone-500">
                  Clip {formatTime(slideStart(slide))}–{formatTime(slideEnd(slide))} ·{' '}
                  {slide.channel === 1 ? 'B' : 'A'}
                </div>
                <label className="block text-[11px] text-stone-600">
                  Name
                  <input
                    className={`${numInputCls} mt-0.5 w-full`}
                    value={view.name || ''}
                    onChange={(e) => updateView({ name: e.target.value })}
                  />
                </label>
                <div className="flex items-center gap-2 text-[11px] text-stone-600">
                  <span className="w-9 shrink-0">Time</span>
                  <CompactNum
                    className="w-14 flex-1"
                    step={0.1}
                    min={0}
                    value={view.time ?? 0}
                    onChange={(n) => {
                      updateView({ time: n });
                      setPlayhead(round2(slideStart(slide) + n));
                    }}
                  />
                  <span className="w-12 shrink-0">Opacity</span>
                  <CompactNum
                    className="w-14 flex-1"
                    step={0.01}
                    min={0}
                    max={1}
                    value={view.opacity ?? 1}
                    onChange={(n) => updateView({ opacity: n })}
                  />
                </div>
                <PanelToggle title="Transform" open={transformOpen} onToggle={() => setTransformOpen((o) => !o)}>
                  <div className="flex items-center gap-1 text-[11px] text-stone-600">
                    <span className="w-11 shrink-0">Zoom</span>
                    <CompactNum
                      className="min-w-0 flex-1"
                      step={0.01}
                      min={0.2}
                      max={8}
                      value={viewZoomX(view)}
                      onChange={setZoomX}
                    />
                    <button
                      type="button"
                      title={zoomSync ? 'X/Y zoom linked' : 'X/Y zoom independent'}
                      className={`shrink-0 rounded border px-1 py-0.5 text-[10px] font-semibold ${
                        zoomSync
                          ? 'border-emerald-600 bg-emerald-50 text-emerald-800'
                          : 'border-stone-300 text-stone-500'
                      }`}
                      onClick={() => {
                        const next = !zoomSync;
                        setZoomSync(next);
                        if (next) {
                          const z = viewZoomX(view);
                          updateView({ zoom: z, zoomX: z, zoomY: z });
                        }
                      }}
                    >
                      ⟷
                    </button>
                    <CompactNum
                      className="min-w-0 flex-1"
                      step={0.01}
                      min={0.2}
                      max={8}
                      value={viewZoomY(view)}
                      onChange={setZoomY}
                    />
                  </div>
                  <div className="flex items-center gap-1 text-[11px] text-stone-600">
                    <span className="w-11 shrink-0">Pos</span>
                    <CompactNum
                      className="min-w-0 flex-1"
                      value={view.x ?? 0.5}
                      onChange={(n) => updateView({ x: n })}
                    />
                    <CompactNum
                      className="min-w-0 flex-1"
                      value={view.y ?? 0.5}
                      onChange={(n) => updateView({ y: n })}
                    />
                  </div>
                  <SliderRow
                    label="Angle"
                    min={-180}
                    max={180}
                    step={0.1}
                    value={view.rotation ?? 0}
                    onChange={(n) => updateView({ rotation: n })}
                  />
                  <div className="flex items-center gap-1 text-[11px] text-stone-600">
                    <span className="w-11 shrink-0">Anchor</span>
                    <CompactNum
                      className="min-w-0 flex-1"
                      value={view.anchorX ?? view.x ?? 0.5}
                      onChange={(n) => updateView({ anchorX: n })}
                    />
                    <CompactNum
                      className="min-w-0 flex-1"
                      value={view.anchorY ?? view.y ?? 0.5}
                      onChange={(n) => updateView({ anchorY: n })}
                    />
                  </div>
                  <SliderRow
                    label="Pitch"
                    min={-90}
                    max={90}
                    step={0.1}
                    value={view.pitch ?? 0}
                    onChange={(n) => updateView({ pitch: n })}
                  />
                  <SliderRow
                    label="Yaw"
                    min={-90}
                    max={90}
                    step={0.1}
                    value={view.yaw ?? 0}
                    onChange={(n) => updateView({ yaw: n })}
                  />
                </PanelToggle>
                <PanelToggle title="Crop" open={cropOpen} onToggle={() => setCropOpen((o) => !o)}>
                  <SliderRow
                    label="Left"
                    min={0}
                    max={0.95}
                    step={0.01}
                    value={view.cropLeft ?? 0}
                    onChange={(n) => setCrop('cropLeft', n)}
                  />
                  <SliderRow
                    label="Right"
                    min={0}
                    max={0.95}
                    step={0.01}
                    value={view.cropRight ?? 0}
                    onChange={(n) => setCrop('cropRight', n)}
                  />
                  <SliderRow
                    label="Top"
                    min={0}
                    max={0.95}
                    step={0.01}
                    value={view.cropTop ?? 0}
                    onChange={(n) => setCrop('cropTop', n)}
                  />
                  <SliderRow
                    label="Bottom"
                    min={0}
                    max={0.95}
                    step={0.01}
                    value={view.cropBottom ?? 0}
                    onChange={(n) => setCrop('cropBottom', n)}
                  />
                </PanelToggle>
                <div className="flex flex-wrap gap-1 pt-0.5">
                  <button
                    type="button"
                    className="rounded border px-1.5 py-0.5 text-[11px]"
                    disabled={!view}
                    onClick={copyKeyframe}
                  >
                    Copy
                  </button>
                  <button
                    type="button"
                    className="rounded border px-1.5 py-0.5 text-[11px] disabled:opacity-40"
                    disabled={!hasClipboard || !slide}
                    onClick={pasteKeyframe}
                  >
                    Paste
                  </button>
                  <button
                    type="button"
                    className="rounded border px-1.5 py-0.5 text-[11px] text-red-700 disabled:opacity-40"
                    disabled={views.length <= 1}
                    onClick={removeKeyframe}
                  >
                    Del kf
                  </button>
                  <button
                    type="button"
                    className="rounded border px-1.5 py-0.5 text-[11px] text-red-700"
                    onClick={removeClip}
                  >
                    Del clip
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-sm text-stone-500">
                Drag media onto a channel, then Add a keyframe at the playhead.
              </p>
            )}
          </aside>
          <div className="relative min-h-0 bg-black">
            <TimelineStage
              className="h-full w-full"
              slides={slides}
              itemsById={itemsById}
              time={playhead}
              selectedIndex={selected}
              selectedView={view}
              effects={effects}
              onViewChange={playing ? undefined : updateView}
            />
            {playing ? (
              <div className="pointer-events-none absolute right-2 top-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">
                {playing === 'slide' ? 'Slide build' : 'Show'} · {formatTime(playhead)}
              </div>
            ) : null}
          </div>
        </div>

        <div className="flex min-h-0 flex-col">
          <div className="flex items-center gap-2 border-t border-stone-200 bg-white px-3 py-1 text-xs text-stone-600">
            <span>Timeline</span>
            <button type="button" className="rounded border px-1.5" onClick={() => setPxPerSec((p) => Math.max(16, p - 8))}>
              −
            </button>
            <span>{pxPerSec} px/s</span>
            <button type="button" className="rounded border px-1.5" onClick={() => setPxPerSec((p) => Math.min(120, p + 8))}>
              +
            </button>
            <span className="text-stone-400">Drop onto A or B · FX bar for fades</span>
            <EffectPalette
              onAddAtPlayhead={(type) => {
                const fx = newEffect(type, playhead, 1);
                const next = [...effects, fx];
                setEffects(next);
                selectEffect(next.length - 1);
              }}
            />
            {selectedEffect >= 0 ? (
              <button
                type="button"
                className="rounded border px-1.5 py-0.5 text-[11px] text-red-700"
                onClick={removeEffect}
              >
                Delete FX
              </button>
            ) : null}
          </div>
          <ShowTimeline
            slides={slides}
            effects={effects}
            itemsById={itemsById}
            selectedIndex={selected}
            selectedViewIndex={selectedView}
            selectedEffectIndex={selectedEffect}
            playhead={playhead}
            pxPerSec={pxPerSec}
            onChangeSlides={setSlides}
            onChangeEffects={setEffects}
            onSelect={selectClip}
            onSelectEffect={selectEffect}
            onPlayhead={onPlayhead}
            onMoveKeyframe={moveSelectedKeyframe}
            onMoveKeyframeEnd={commitKeyframeOrder}
          />
          <div className="shrink-0 border-t border-stone-200 bg-white">
            <div className="px-3 py-1 text-[10px] font-medium uppercase tracking-wide text-stone-500">
              Media — drag onto a channel
            </div>
            <div className="flex gap-2 overflow-x-auto px-3 pb-2">
              {(gallery.items || []).map((it) => (
                <button
                  key={it.id}
                  type="button"
                  draggable
                  onDragStart={(e) => onMediaDragStart(e, it)}
                  className="w-20 shrink-0 rounded border border-stone-200 bg-stone-50 p-1 text-left hover:border-emerald-400"
                  title={it.title || it.filename}
                >
                  <img src={thumbSrc(it)} alt="" className="h-12 w-full rounded object-cover bg-stone-200" />
                  <div className="mt-0.5 truncate text-[10px] text-stone-600">
                    {it.title || it.filename || 'item'}
                  </div>
                </button>
              ))}
              {!gallery.items?.length ? (
                <span className="pb-2 text-xs text-stone-400">Add images to the gallery first</span>
              ) : null}
            </div>
          </div>
        </div>
      </div>
      {jsonOpen ? (
        <JsonDebugPanel title="Show JSON" data={config} onClose={() => setJsonOpen(false)} />
      ) : null}
    </div>
  );
}
