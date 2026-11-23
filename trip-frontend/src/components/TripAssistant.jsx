import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../services/api';

const KIND_LABEL = { stop: 'Stop', event: 'Event', lodging: 'Lodging' };
const KIND_GLYPH = { stop: '●', event: '◆', lodging: '⌂' };
const POLL_MS = 2500;

const STARTERS = [
  { label: 'Hotels', prompt: 'Recommend places to stay for these nights' },
  { label: 'Things to do', prompt: 'Suggest things to do' },
  { label: 'Dinner', prompt: 'Suggest good places for dinner' },
  { label: 'Rainy day', prompt: 'Suggest rainy-day options' },
  { label: 'Fill free time', prompt: 'Fill the free time in the schedule with nearby activities' },
];

function clock(hhmm) {
  if (!hhmm) return '';
  const [h, m] = String(hhmm).split(':').map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}

function minutes(n) {
  if (!n) return '';
  const h = Math.floor(n / 60);
  const m = n % 60;
  return [h && `${h}h`, m && `${m}m`].filter(Boolean).join(' ');
}

function subtitle(s, dayLabel, days) {
  const d = s.data;
  const parts = [KIND_LABEL[s.kind]];
  if (s.kind === 'lodging') {
    const nights = (d.day_ids || []).length;
    if (nights) parts.push(`${nights} night${nights === 1 ? '' : 's'}`);
  } else {
    const day = days.find((x) => x.id === d.day_id);
    if (day) parts.push(dayLabel(day));
    if (d.start_time) parts.push(clock(d.start_time));
    if (d.duration_minutes) parts.push(minutes(d.duration_minutes));
  }
  if (d.price_hint) parts.push(d.price_hint);
  return parts.join(' · ');
}

function SuggestionCard({ suggestion, days, dayLabel, fallbackDayId, onApply, onEdit, onDismiss }) {
  const s = suggestion;
  const d = s.data;
  const [open, setOpen] = useState(false);
  const [dayId, setDayId] = useState(String(d.day_id || fallbackDayId || days[0]?.id || ''));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const run = async (fn) => {
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (s.status === 'dismissed') return null;
  const added = s.status === 'added';
  const isLodging = s.kind === 'lodging';
  const fields = isLodging ? {} : { day_id: Number(dayId) };

  return (
    <li className={`trip-ai-card is-${s.kind}${added ? ' is-added' : ''}`}>
      <button type="button" className="trip-ai-card-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className={`trip-ai-glyph is-${s.kind}`} aria-hidden="true">{KIND_GLYPH[s.kind]}</span>
        <span className="trip-ai-card-text">
          <span className="trip-ai-card-title">{d.name}</span>
          <span className="trip-ai-card-sub">{subtitle(s, dayLabel, days)}</span>
        </span>
        {d.already_planned && !added && <span className="trip-ai-badge">In trip</span>}
        {added && <span className="trip-ai-badge is-added">Added</span>}
      </button>
      {d.why && <p className="trip-ai-why">{d.why}</p>}
      {open && (
        <div className="trip-ai-more">
          {d.description && <p>{d.description}</p>}
          {d.address && <p className="trip-muted">{d.address}</p>}
          {d.url && <p><a href={d.url} target="_blank" rel="noreferrer">{d.url}</a></p>}
          {isLodging && (d.day_ids || []).length > 0 && (
            <p className="trip-muted">
              Nights: {d.day_ids.map((id) => days.find((x) => x.id === id)).filter(Boolean).map(dayLabel).join(', ')}
            </p>
          )}
          <p className="trip-ai-unverified">AI suggestion: check hours, prices and availability before booking.</p>
        </div>
      )}
      {!added && (
        <div className="trip-ai-actions">
          {!isLodging && days.length > 0 && (
            <select value={dayId} onChange={(e) => setDayId(e.target.value)} aria-label="Day" disabled={busy}>
              {days.map((day) => <option key={day.id} value={day.id}>{dayLabel(day)}</option>)}
            </select>
          )}
          {(isLodging || days.length > 0) && (
            <button type="button" className="trip-primary" disabled={busy || (!isLodging && !dayId)} onClick={() => run(() => onApply(s, fields))}>
              Add
            </button>
          )}
          {!isLodging && (
            <button
              type="button"
              className={days.length === 0 ? 'trip-primary' : ''}
              disabled={busy}
              title="Save to the unscheduled Ideas pool"
              onClick={() => {
                const chosen = days.find((x) => String(x.id) === String(dayId));
                run(() => onApply(s, { to_ideas: true, leg_id: chosen?.leg || null }));
              }}
            >
              + Idea
            </button>
          )}
          <button type="button" disabled={busy} onClick={() => onEdit(s, isLodging ? null : (dayId ? Number(dayId) : null))}>Edit &amp; add</button>
          <button type="button" className="trip-ai-dismiss" disabled={busy} onClick={() => run(() => onDismiss(s))} aria-label={`Dismiss ${d.name}`}>
            Dismiss
          </button>
          {s.maps_url && (
            <a className="trip-ai-map" href={s.maps_url} target="_blank" rel="noreferrer" aria-label={`Open ${d.name} in Google Maps`}>
              Map ↗
            </a>
          )}
        </div>
      )}
      {added && s.maps_url && (
        <div className="trip-ai-actions">
          <a className="trip-ai-map" href={s.maps_url} target="_blank" rel="noreferrer">Map ↗</a>
        </div>
      )}
      {error && <p className="trip-error">{error}</p>}
    </li>
  );
}

function Batch({ batch, days, dayLabel, currentDayId, onApply, onEdit, onDismiss, onRetry, onDelete }) {
  const scopeDay = days.find((d) => d.id === batch.day_id);
  const dismissed = batch.suggestions.filter((s) => s.status === 'dismissed').length;
  return (
    <section className="trip-ai-batch">
      <header className="trip-ai-batch-head">
        <div>
          <p className="trip-ai-prompt">{batch.prompt}</p>
          <p className="trip-muted">{scopeDay ? dayLabel(scopeDay) : 'Whole trip'}</p>
        </div>
        <button type="button" className="trip-ai-icon" onClick={() => onDelete(batch)} aria-label="Remove this request" title="Remove">×</button>
      </header>
      {batch.status === 'running' && (
        <p className="trip-ai-thinking"><span className="trip-ai-spinner" aria-hidden="true" /> Thinking… this can take up to a minute.</p>
      )}
      {batch.status === 'failed' && (
        <div className="trip-ai-failed">
          <p className="trip-error">{batch.error || 'The assistant failed.'}</p>
          <button type="button" onClick={() => onRetry(batch)}>Try again</button>
        </div>
      )}
      {batch.status === 'done' && (
        <ul className="trip-ai-cards">
          {batch.suggestions.map((s) => (
            <SuggestionCard
              key={s.id}
              suggestion={s}
              days={days}
              dayLabel={dayLabel}
              fallbackDayId={batch.day_id || currentDayId}
              onApply={onApply}
              onEdit={onEdit}
              onDismiss={onDismiss}
            />
          ))}
        </ul>
      )}
      {dismissed > 0 && <p className="trip-muted trip-ai-dismissed">{dismissed} dismissed</p>}
    </section>
  );
}

/**
 * Side drawer where the user asks for recommendations and adds them to the trip.
 * `onEdit(suggestion, dayId, markAdded)` lets the parent open its own stop/lodging form;
 * the parent calls `markAdded(updatedSuggestion)` after applying it.
 */
export default function TripAssistant({ trip, days, dayLabel, currentDayId, onApplied, onEdit, onClose }) {
  const [batches, setBatches] = useState([]);
  const [prompt, setPrompt] = useState('');
  const [scope, setScope] = useState(currentDayId ? String(currentDayId) : 'trip');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    api.json(`/api/trips/assistant/?trip=${trip.id}`)
      .then((rows) => { if (!cancelled) setBatches(rows || []); })
      .catch((err) => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [trip.id]);

  useEffect(() => {
    document.body.classList.add('trip-ai-open');
    return () => document.body.classList.remove('trip-ai-open');
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape' && !document.querySelector('.trip-modal-backdrop')) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const runningIds = batches.filter((b) => b.status === 'running').map((b) => b.id).join(',');
  useEffect(() => {
    if (!runningIds) return undefined;
    const timer = setInterval(async () => {
      const updates = await Promise.all(
        runningIds.split(',').map((id) => api.json(`/api/trips/assistant/${id}/`).catch(() => null)),
      );
      setBatches((prev) => prev.map((b) => updates.find((u) => u && u.id === b.id) || b));
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [runningIds]);

  const updateSuggestion = useCallback((updated) => {
    setBatches((prev) => prev.map((b) => ({
      ...b,
      suggestions: b.suggestions.map((s) => (s.id === updated.id ? updated : s)),
    })));
  }, []);

  const ask = async (text, dayId) => {
    if (!text.trim()) return;
    setBusy(true);
    setError('');
    try {
      const batch = await api.json('/api/trips/assistant/', {
        method: 'POST',
        body: JSON.stringify({ trip_id: trip.id, day_id: dayId, prompt: text.trim() }),
      });
      setBatches((prev) => [batch, ...prev]);
      setPrompt('');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const submit = (e) => {
    e.preventDefault();
    if (busy) return;
    ask(prompt, scope === 'trip' ? null : Number(scope));
  };

  const apply = async (s, fields) => {
    const updated = await api.json(`/api/trips/suggestions/${s.id}/apply/`, {
      method: 'POST',
      body: JSON.stringify({ fields }),
    });
    updateSuggestion(updated);
    await onApplied();
  };

  const dismiss = async (s) => {
    updateSuggestion(await api.json(`/api/trips/suggestions/${s.id}/dismiss/`, { method: 'POST' }));
  };

  const remove = async (batch) => {
    await api.json(`/api/trips/assistant/${batch.id}/`, { method: 'DELETE' });
    setBatches((prev) => prev.filter((b) => b.id !== batch.id));
  };

  return (
    <aside className="trip-ai-drawer" aria-label="Trip assistant">
      <header className="trip-ai-head">
        <h3>Trip assistant</h3>
        <button type="button" className="trip-ai-icon" onClick={onClose} aria-label="Close assistant">×</button>
      </header>
      <form className="trip-ai-ask" onSubmit={submit}>
        <select value={scope} onChange={(e) => setScope(e.target.value)} aria-label="Ask about">
          <option value="trip">Whole trip</option>
          {days.map((d) => <option key={d.id} value={d.id}>{dayLabel(d)}</option>)}
        </select>
        <textarea
          ref={inputRef}
          rows={3}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key !== 'Enter' || e.nativeEvent.isComposing) return;
            if (e.ctrlKey || e.metaKey) {
              e.preventDefault();
              const el = e.currentTarget;
              const { selectionStart: start, selectionEnd: end } = el;
              setPrompt(`${prompt.slice(0, start)}\n${prompt.slice(end)}`);
              requestAnimationFrame(() => el.setSelectionRange(start + 1, start + 1));
            } else if (!e.shiftKey) {
              submit(e);
            }
          }}
          placeholder="e.g. Family-friendly hotels near the lake, or what to do on a free afternoon"
          aria-label="Ask the assistant"
        />
        <div className="trip-ai-starters">
          {STARTERS.map((s) => (
            <button
              key={s.label}
              type="button"
              onClick={() => {
                setPrompt(s.prompt);
                inputRef.current?.focus();
              }}
            >
              {s.label}
            </button>
          ))}
        </div>
        <div className="trip-ai-submit">
          <span className="trip-muted">Enter to ask · Ctrl+Enter for a new line</span>
          <button type="submit" className="trip-primary" disabled={busy || !prompt.trim()}>
            {busy ? 'Asking…' : 'Ask'}
          </button>
        </div>
        {error && <p className="trip-error">{error}</p>}
      </form>
      <div className="trip-ai-results">
        {loading && <p className="trip-muted">Loading…</p>}
        {!loading && !batches.length && (
          <p className="trip-muted">Ask for hotels, things to do, or events. Results can be added straight to a day.</p>
        )}
        {batches.map((b) => (
          <Batch
            key={b.id}
            batch={b}
            days={days}
            dayLabel={dayLabel}
            currentDayId={currentDayId}
            onApply={apply}
            onEdit={(s, dayId) => onEdit(s, dayId, updateSuggestion)}
            onDismiss={dismiss}
            onRetry={(batch) => ask(batch.prompt, batch.day_id)}
            onDelete={remove}
          />
        ))}
      </div>
    </aside>
  );
}
