import React, { useEffect, useMemo, useRef, useState } from 'react';
import api from '../services/api';
import { thumbSrc } from './Carousel';

const STYLES = [
  { id: 'kenburns', label: 'Ken Burns' },
  { id: 'punchy', label: 'Punchy' },
  { id: 'documentary', label: 'Documentary' },
  { id: 'cinematic', label: 'Cinematic' },
];

const STEPS = ['queued', 'analyzing', 'planning', 'compiling', 'ready'];

function statusLabel(status) {
  if (status === 'failed') return 'Failed';
  if (status === 'ready') return 'Ready';
  if (status === 'planning') return 'Planning shot list';
  if (status === 'analyzing') return 'Analyzing images';
  if (status === 'compiling') return 'Compiling show';
  return 'Queued';
}

function formatTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString();
}

export default function GenerateShowModal({ gallery, onGenerated, onClose }) {
  const items = useMemo(
    () => (gallery.items || []).filter((it) => !it.media_type || it.media_type === 'image'),
    [gallery.items]
  );
  const [picked, setPicked] = useState([]);
  const [title, setTitle] = useState('Show');
  const [style, setStyle] = useState('kenburns');
  const [seconds, setSeconds] = useState(45);
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [dragIndex, setDragIndex] = useState(null);
  const [job, setJob] = useState(null);
  const logRef = useRef(null);

  const pickedSet = useMemo(() => new Set(picked), [picked]);
  const available = items.filter((it) => !pickedSet.has(it.id));
  const jobId = job?.id;
  const running = Boolean(jobId && !['ready', 'failed'].includes(job?.status));

  const add = (id) => setPicked((p) => [...p, id]);
  const remove = (index) => setPicked((p) => p.filter((_, i) => i !== index));
  const move = (from, to) => {
    if (from === to || to < 0 || to >= picked.length) return;
    setPicked((p) => {
      const next = [...p];
      const [row] = next.splice(from, 1);
      next.splice(to, 0, row);
      return next;
    });
  };

  useEffect(() => {
    if (!jobId || ['ready', 'failed'].includes(job?.status)) return undefined;
    let stop = false;
    let timer;
    const tick = async () => {
      try {
        const next = await api.json(`/api/gallery/show-jobs/${jobId}/`);
        if (stop) return;
        setJob(next);
        if (next.status === 'failed') {
          setError(next.error || 'Generate failed');
          setBusy(false);
          return;
        }
        if (next.status === 'ready') {
          setBusy(false);
          return;
        }
      } catch (err) {
        if (!stop) setError(err.message || 'Status check failed');
      }
      if (!stop) timer = setTimeout(tick, 700);
    };
    timer = setTimeout(tick, 700);
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [jobId, job?.status]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [job?.log?.length]);

  const submit = async (e) => {
    e.preventDefault();
    if (!picked.length) {
      setError('Select images and put them in play order.');
      return;
    }
    setBusy(true);
    setError('');
    setJob(null);
    try {
      const data = await api.json('/api/gallery/shows/generate/', {
        method: 'POST',
        body: JSON.stringify({
          gallery: gallery.id,
          item_ids: picked,
          title,
          style,
          target_seconds: Number(seconds),
          prompt,
        }),
      });
      setJob(data);
    } catch (err) {
      setError(err.message || 'Generate failed');
      setBusy(false);
    }
  };

  const copyLog = async () => {
    const lines = (job?.log || []).map((row) => {
      const extra = row.data ? ` ${JSON.stringify(row.data)}` : '';
      return `${row.t || ''} [${row.step}] ${row.message}${extra}`;
    });
    const text = lines.join('\n');
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      setError('Could not copy log');
    }
  };

  const byId = useMemo(
    () => Object.fromEntries(items.map((it) => [it.id, it])),
    [items]
  );

  const stepIndex = STEPS.indexOf(job?.status === 'failed' ? 'compiling' : job?.status);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <form
        onSubmit={submit}
        className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl bg-white shadow-lg"
      >
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="text-lg font-semibold">Generate show</h2>
          <button type="button" className="text-sm text-stone-500" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-0 overflow-hidden lg:grid-cols-2">
          <div className="flex min-h-0 flex-col overflow-hidden border-b lg:border-b-0 lg:border-r">
            <div className="min-h-0 flex-1 overflow-auto p-3">
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">
                Gallery images — click to add
              </div>
              <div className="grid grid-cols-3 gap-2">
                {available.map((it) => (
                  <button
                    key={it.id}
                    type="button"
                    disabled={running}
                    className="overflow-hidden rounded border border-stone-200 text-left hover:border-emerald-500 disabled:opacity-50"
                    onClick={() => add(it.id)}
                  >
                    <img src={thumbSrc(it)} alt="" className="aspect-square w-full object-cover" />
                    <div className="truncate px-1 py-0.5 text-[10px] text-stone-600">
                      {it.title || it.filename || 'Image'}
                    </div>
                  </button>
                ))}
                {!available.length ? (
                  <p className="col-span-3 text-sm text-stone-400">All images are in the sequence.</p>
                ) : null}
              </div>
              <div className="mb-2 mt-4 text-xs font-medium uppercase tracking-wide text-stone-500">
                Play order ({picked.length})
              </div>
              <ul className="space-y-1">
                {picked.map((id, index) => {
                  const it = byId[id];
                  return (
                    <li
                      key={`${id}-${index}`}
                      draggable={!running}
                      onDragStart={() => setDragIndex(index)}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => {
                        if (dragIndex == null) return;
                        move(dragIndex, index);
                        setDragIndex(null);
                      }}
                      className="flex items-center gap-2 rounded border border-stone-200 bg-stone-50 px-1 py-1"
                    >
                      <span className="w-5 text-center text-[10px] text-stone-400">{index + 1}</span>
                      <img src={it ? thumbSrc(it) : ''} alt="" className="h-10 w-10 rounded object-cover" />
                      <span className="min-w-0 flex-1 truncate text-xs">
                        {it?.title || it?.filename || id}
                      </span>
                      <button type="button" disabled={running} className="text-[10px] text-stone-500" onClick={() => move(index, index - 1)}>
                        Up
                      </button>
                      <button type="button" disabled={running} className="text-[10px] text-stone-500" onClick={() => move(index, index + 1)}>
                        Down
                      </button>
                      <button type="button" disabled={running} className="text-[10px] text-red-600" onClick={() => remove(index)}>
                        Remove
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
            <div className="grid grid-cols-2 gap-2 border-t p-3 text-sm">
              <label className="col-span-2">
                Title
                <input
                  className="mt-0.5 w-full rounded border px-2 py-1"
                  value={title}
                  disabled={running}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label className="col-span-2">
                Shot list prompt
                <textarea
                  className="mt-0.5 w-full rounded border px-2 py-1 text-sm"
                  rows={2}
                  placeholder="e.g. open on the group, skip shots without faces"
                  value={prompt}
                  disabled={running}
                  onChange={(e) => setPrompt(e.target.value)}
                />
              </label>
              <label>
                Style
                <select
                  className="mt-0.5 w-full rounded border px-2 py-1"
                  value={style}
                  disabled={running}
                  onChange={(e) => setStyle(e.target.value)}
                >
                  {STYLES.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Length (s)
                <input
                  type="number"
                  min={8}
                  max={180}
                  className="mt-0.5 w-full rounded border px-2 py-1"
                  value={seconds}
                  disabled={running}
                  onChange={(e) => setSeconds(e.target.value)}
                />
              </label>
            </div>
          </div>
          <div className="flex min-h-0 flex-col bg-stone-950 p-3 text-stone-100">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div>
                <div className="text-xs font-medium uppercase tracking-wide text-stone-400">Status</div>
                <div className={`text-sm font-semibold ${job?.status === 'failed' ? 'text-red-400' : 'text-emerald-300'}`}>
                  {job ? statusLabel(job.status) : 'Idle'}
                </div>
              </div>
              {job?.log?.length ? (
                <button type="button" className="text-[11px] text-stone-400 underline" onClick={copyLog}>
                  Copy log
                </button>
              ) : null}
            </div>
            <ol className="mb-3 flex flex-wrap gap-1 text-[10px] uppercase tracking-wide">
              {STEPS.map((step, i) => {
                const active = job?.status === step;
                const done = stepIndex > i || job?.status === 'ready';
                const failed = job?.status === 'failed' && i >= Math.max(stepIndex, 0);
                return (
                  <li
                    key={step}
                    className={`rounded px-1.5 py-0.5 ${
                      failed ? 'bg-red-900 text-red-200' : active ? 'bg-emerald-700 text-white' : done ? 'bg-stone-700 text-stone-200' : 'bg-stone-900 text-stone-500'
                    }`}
                  >
                    {step}
                  </li>
                );
              })}
            </ol>
            <div
              ref={logRef}
              className="min-h-[12rem] flex-1 overflow-auto rounded border border-stone-800 bg-black/40 p-2 font-mono text-[11px] leading-5"
            >
              {(job?.log || []).map((row, i) => (
                <div key={`${row.t}-${i}`} className={row.level === 'error' ? 'text-red-400' : row.level === 'warn' ? 'text-amber-300' : 'text-stone-300'}>
                  <span className="text-stone-500">{formatTime(row.t)} </span>
                  <span className="text-stone-400">[{row.step}] </span>
                  {row.message}
                  {row.data?.preview ? (
                    <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-stone-500">
                      {row.data.preview}
                    </pre>
                  ) : null}
                </div>
              ))}
              {!job ? (
                <div className="text-stone-500">Generate to watch analyze → LocalAI plan → compile.</div>
              ) : null}
            </div>
          </div>
        </div>
        {error ? <div className="bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div> : null}
        <div className="flex justify-end gap-2 border-t px-4 py-3">
          <button type="button" className="rounded border px-3 py-1.5 text-sm" onClick={onClose}>
            {running ? 'Hide' : 'Cancel'}
          </button>
          {job?.status === 'ready' && job.show ? (
            <button
              type="button"
              className="rounded bg-emerald-700 px-3 py-1.5 text-sm text-white"
              onClick={() => onGenerated?.({ ...job.show, warnings: job.warnings, plan: job.plan })}
            >
              Open show
            </button>
          ) : (
            <button
              type="submit"
              disabled={busy || running || !picked.length}
              className="rounded bg-emerald-700 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              {running || busy ? 'Generating…' : 'Generate'}
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
