import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { MarkdownSplitEditor } from '@bldrdojo/markdown-editor';
import { useAuth } from '../contexts/AuthContext';
import { getLoginUrl } from '../utils/apiUrl';
import api from '../services/api';
import AppsMenu from './AppsMenu';

const STATUS_LABEL = { tobook: 'To book', booked: 'Booked', confirmed: 'Confirmed' };

function asList(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

function formatStopTime(value) {
  if (!value) return '';
  const [hours, minutes] = String(value).split(':');
  if (hours == null || minutes == null) return String(value);
  const d = new Date();
  d.setHours(Number(hours), Number(minutes), 0, 0);
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

function formatDuration(minutes) {
  if (minutes == null || minutes === '') return '';
  const n = Number(minutes);
  if (!Number.isFinite(n) || n <= 0) return '';
  const h = Math.floor(n / 60);
  const m = n % 60;
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

const ATTACH_KINDS = [
  { id: 'document', label: 'Document' },
  { id: 'url', label: 'URL' },
  { id: 'picture', label: 'Picture' },
  { id: 'location', label: 'Location' },
];

function IconSvg({ children, ...props }) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      {children}
    </svg>
  );
}

function AttachmentGlyph({ kind, variant }) {
  if (kind === 'document') {
    return (
      <IconSvg>
        <path d="M7 3.5h7l4 4V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1z" />
        <path d="M14 3.5V8h4" />
        <path d="M8.5 13h7M8.5 16.5h5" />
      </IconSvg>
    );
  }
  if (kind === 'picture') {
    return (
      <IconSvg>
        <rect x="4" y="5" width="16" height="14" rx="1.5" />
        <circle cx="9" cy="10" r="1.4" />
        <path d="M4 16l5-4 4 3 3-2 4 3" />
      </IconSvg>
    );
  }
  if (kind === 'location' && variant === 'osm') {
    return (
      <IconSvg>
        <path d="M4 7l5.5-2 5 2L20.5 5v12l-6 2-5-2L4 19V7z" />
        <path d="M9.5 5v12M14.5 7v12" />
      </IconSvg>
    );
  }
  if (kind === 'location') {
    return (
      <IconSvg>
        <path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z" />
        <circle cx="12" cy="10" r="2.2" />
      </IconSvg>
    );
  }
  return (
    <IconSvg>
      <path d="M10 13a5 5 0 0 0 7.07 0l2.12-2.12a5 5 0 0 0-7.07-7.07L10.7 5.2" />
      <path d="M14 11a5 5 0 0 0-7.07 0L4.8 13.12a5 5 0 0 0 7.07 7.07L13.3 18.8" />
    </IconSvg>
  );
}

function attachmentHref(item, map = 'google') {
  if (item.kind === 'location') {
    return map === 'osm' ? item.osm_url : item.url;
  }
  return item.file_url || item.url;
}

function AttachmentIcons({ attachments, onAdd, onRemove, canEdit }) {
  if (!attachments?.length && !canEdit) return null;
  return (
    <div className="trip-attach-icons" onClick={(e) => e.stopPropagation()}>
      {(attachments || []).map((item) => {
        const href = attachmentHref(item);
        const label = item.title || ATTACH_KINDS.find((k) => k.id === item.kind)?.label || item.kind;
        return (
          <span key={item.id} className="trip-attach-item">
            {href ? (
              <a
                className="trip-attach-icon"
                href={href}
                target="_blank"
                rel="noreferrer"
                title={label}
                aria-label={label}
              >
                <AttachmentGlyph kind={item.kind} />
              </a>
            ) : (
              <span className="trip-attach-icon" title={label}><AttachmentGlyph kind={item.kind} /></span>
            )}
            {item.kind === 'location' && item.osm_url && (
              <a
                className="trip-attach-icon"
                href={item.osm_url}
                target="_blank"
                rel="noreferrer"
                title={`${label} on OpenStreetMap`}
                aria-label={`${label} on OpenStreetMap`}
              >
                <AttachmentGlyph kind="location" variant="osm" />
              </a>
            )}
            {canEdit && onRemove && (
              <button
                type="button"
                className="trip-attach-remove"
                onClick={() => onRemove(item)}
                aria-label={`Remove ${label}`}
                title="Remove"
              >
                ×
              </button>
            )}
          </span>
        );
      })}
      {canEdit && onAdd && (
        <button type="button" className="trip-attach-add" onClick={onAdd} title="Add document, URL, picture, or location">
          +
        </button>
      )}
    </div>
  );
}

function AttachmentForm({ stop, lodging, onClose, onSaved }) {
  const [kind, setKind] = useState(lodging ? 'picture' : 'document');
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [address, setAddress] = useState(lodging?.address || stop?.loc || '');
  const [lat, setLat] = useState('');
  const [lng, setLng] = useState('');
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const label = lodging ? lodging.name : stop?.text;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const payload = {
        kind,
        title: title.trim(),
        ...(lodging ? { lodging_id: lodging.id } : { stop_id: stop.id }),
      };
      if (kind === 'url') {
        payload.url = url.trim();
      } else if (kind === 'location') {
        payload.address = address.trim();
        payload.url = url.trim();
        payload.lat = lat === '' ? null : Number(lat);
        payload.lng = lng === '' ? null : Number(lng);
      } else if (file) {
        const form = new FormData();
        form.append('file', file);
        form.append('add_to_gallery', 'false');
        const uploaded = await api.json('/api/gallery/upload/', { method: 'POST', body: form });
        payload.asset_id = uploaded.user_media_id;
        payload.url = uploaded.url;
        if (!payload.title) payload.title = uploaded.filename || file.name;
      } else if (url.trim()) {
        payload.url = url.trim();
      }
      await api.json('/api/trips/attachments/', { method: 'POST', body: JSON.stringify(payload) });
      await onSaved();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" onClick={onClose} role="presentation">
      <form className="trip-modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>{lodging ? 'Add to lodging' : 'Add to stop'}</h3>
        <p className="trip-hint">{label}</p>
        <div className="trip-kind-tabs">
          {ATTACH_KINDS.map((k) => (
            <button
              key={k.id}
              type="button"
              className={kind === k.id ? 'is-active' : ''}
              onClick={() => setKind(k.id)}
            >
              <AttachmentGlyph kind={k.id} />
              {k.label}
            </button>
          ))}
        </div>
        <label>
          Label
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={kind === 'document' ? 'Booking confirmation' : ''} />
        </label>
        {kind === 'location' && (
          <>
            <label>
              Address or place
              <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="The Inn at Death Valley" />
            </label>
            <label>
              Map URL (optional)
              <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://maps.google.com/..." />
            </label>
            <div className="trip-form-row">
              <label>
                Latitude
                <input value={lat} onChange={(e) => setLat(e.target.value)} placeholder="36.457" />
              </label>
              <label>
                Longitude
                <input value={lng} onChange={(e) => setLng(e.target.value)} placeholder="-116.867" />
              </label>
            </div>
            <p className="trip-hint">Icons will open Google Maps and OpenStreetMap.</p>
          </>
        )}
        {kind === 'url' && (
          <label>
            URL
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" required />
          </label>
        )}
        {(kind === 'document' || kind === 'picture') && (
          <>
            <label>
              File
              <input
                type="file"
                accept={kind === 'picture' ? 'image/*' : '.pdf,.doc,.docx,.txt,image/*,.png,.jpg'}
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            <label>
              Or URL
              <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
            </label>
          </>
        )}
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy}>
            {busy ? 'Saving…' : 'Add'}
          </button>
        </div>
      </form>
    </div>
  );
}

function formatDay(day) {
  const d = day.date ? new Date(`${day.date}T00:00:00`) : null;
  const dateLabel = d
    ? d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
    : '';
  return [dateLabel, day.title].filter(Boolean).join(' — ');
}

function lodgingLabel(lodging) {
  if (!lodging) return '';
  return [lodging.name, lodging.confirmation && `conf ${lodging.confirmation}`].filter(Boolean).join(' · ');
}

function LodgingForm({ trip, days, initial, defaultDayIds, onClose, onSaved, onAddAttachment, onRemoveAttachment }) {
  const [name, setName] = useState(initial?.name || '');
  const [address, setAddress] = useState(initial?.address || '');
  const [phone, setPhone] = useState(initial?.phone || '');
  const [url, setUrl] = useState(initial?.url || '');
  const [confirmation, setConfirmation] = useState(initial?.confirmation || '');
  const [notes, setNotes] = useState(initial?.notes || '');
  const [checkIn, setCheckIn] = useState(initial?.check_in_time ? String(initial.check_in_time).slice(0, 5) : '');
  const [checkOut, setCheckOut] = useState(initial?.check_out_time ? String(initial.check_out_time).slice(0, 5) : '');
  const [dayIds, setDayIds] = useState(() => {
    if (initial?.assigned_day_ids?.length) return initial.assigned_day_ids.map(Number);
    return (defaultDayIds || []).map(Number);
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const toggleDay = (id) => {
    setDayIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Enter a hotel or lodging name.');
      return;
    }
    setBusy(true);
    setError('');
    const payload = {
      trip_id: trip.id,
      name: name.trim(),
      address: address.trim(),
      phone: phone.trim(),
      url: url.trim(),
      confirmation: confirmation.trim(),
      notes: notes.trim(),
      check_in_time: checkIn || null,
      check_out_time: checkOut || null,
      day_ids: dayIds,
    };
    try {
      if (initial?.id) {
        await api.json(`/api/trips/lodgings/${initial.id}/`, { method: 'PATCH', body: JSON.stringify(payload) });
      } else {
        await api.json('/api/trips/lodgings/', { method: 'POST', body: JSON.stringify(payload) });
      }
      await onSaved();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!initial?.id || !window.confirm('Delete this lodging? Days using it will be unset.')) return;
    setBusy(true);
    try {
      await api.json(`/api/trips/lodgings/${initial.id}/`, { method: 'DELETE' });
      await onSaved();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" onClick={onClose} role="presentation">
      <form className="trip-modal trip-modal-wide" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>{initial?.id ? 'Edit lodging' : 'Add lodging'}</h3>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="The Inn at Death Valley" />
        </label>
        <label>
          Address
          <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Furnace Creek, CA" />
        </label>
        <div className="trip-form-row">
          <label>
            Confirmation
            <input value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
          </label>
          <label>
            Phone
            <input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
        </div>
        <label>
          Website
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
        </label>
        <div className="trip-form-row">
          <label>
            Check-in
            <input type="time" value={checkIn} onChange={(e) => setCheckIn(e.target.value)} />
          </label>
          <label>
            Check-out
            <input type="time" value={checkOut} onChange={(e) => setCheckOut(e.target.value)} />
          </label>
        </div>
        <label>
          Notes
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} placeholder="Room type, parking, late arrival…" />
        </label>
        {initial?.id && (
          <div>
            <p className="trip-hint">Photos, documents, links, and map pins</p>
            <AttachmentIcons
              attachments={initial.attachments}
              canEdit
              onAdd={() => onAddAttachment?.(initial)}
              onRemove={onRemoveAttachment}
            />
          </div>
        )}
        <fieldset className="trip-day-picks">
          <legend>Nights at this lodging</legend>
          {days.map((d) => (
            <label key={d.id} className="trip-check">
              <input
                type="checkbox"
                checked={dayIds.includes(d.id)}
                onChange={() => toggleDay(d.id)}
              />
              {formatDay(d)}
            </label>
          ))}
        </fieldset>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          {initial?.id && (
            <button type="button" onClick={remove} disabled={busy}>Delete</button>
          )}
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  );
}

function DayForm({ initial, onClose, onSave }) {
  const [date, setDate] = useState(initial?.date || '');
  const [title, setTitle] = useState(initial?.title || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    if (!date) {
      setError('Pick a date.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await onSave({ date, title: title.trim() });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" onClick={onClose} role="presentation">
      <form className="trip-modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>{initial?.id ? 'Edit day' : 'Add day'}</h3>
        <label>
          Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          Title
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Bay Area to Sequoia" />
        </label>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  );
}

function StopForm({ days, initial, defaultDayId, onClose, onSave }) {
  const [dayId, setDayId] = useState(initial?.day || initial?.day_id || defaultDayId || days[0]?.id || '');
  const [text, setText] = useState(initial?.text || '');
  const [description, setDescription] = useState(initial?.description || '');
  const [loc, setLoc] = useState(initial?.loc || '');
  const [cat, setCat] = useState(initial?.cat || 'Sight');
  const [status, setStatus] = useState(initial?.status || 'confirmed');
  const [startTime, setStartTime] = useState(initial?.start_time ? String(initial.start_time).slice(0, 5) : '');
  const [duration, setDuration] = useState(initial?.duration_minutes ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const selectedDay = days.find((d) => String(d.id) === String(dayId));

  const submit = async (e) => {
    e.preventDefault();
    if (!text.trim()) {
      setError('Enter an activity.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await onSave({
        day_id: Number(dayId),
        text: text.trim(),
        description: description.trim(),
        loc: loc.trim(),
        cat: cat.trim(),
        status,
        start_time: startTime || null,
        duration_minutes: duration === '' ? null : Number(duration),
      });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" onClick={onClose} role="presentation">
      <form className="trip-modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>{initial?.id ? 'Edit stop' : 'Add stop'}</h3>
        <label>
          Day
          <select value={dayId} onChange={(e) => setDayId(e.target.value)}>
            {days.map((d) => (
              <option key={d.id} value={d.id}>{formatDay(d)}</option>
            ))}
          </select>
        </label>
        {!initial?.id && selectedDay && (
          <p className="trip-hint">Goes at the end of {formatDay(selectedDay)}.</p>
        )}
        <label>
          Activity
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} />
        </label>
        <label>
          Description
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Notes, booking details, what to bring…"
          />
        </label>
        <div className="trip-form-row">
          <label>
            Start time
            <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
          </label>
          <label>
            Duration (min)
            <input
              type="number"
              min="0"
              step="5"
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              placeholder="90"
            />
          </label>
        </div>
        <div className="trip-form-row">
          <label>
            Location
            <input value={loc} onChange={(e) => setLoc(e.target.value)} placeholder="Death Valley" />
          </label>
          <label>
            Category
            <input value={cat} onChange={(e) => setCat(e.target.value)} placeholder="Sight" />
          </label>
          <label>
            Status
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {Object.entries(STATUS_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </label>
        </div>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  );
}

function TripDetail({ trip, lists, galleries, onBack, onReload }) {
  const [mode, setMode] = useState('plan');
  const [query, setQuery] = useState('');
  const [loc, setLoc] = useState('all');
  const [cat, setCat] = useState('all');
  const [status, setStatus] = useState('all');
  const [editing, setEditing] = useState(null);
  const [adding, setAdding] = useState(false);
  const [addingDay, setAddingDay] = useState(false);
  const [editingDay, setEditingDay] = useState(null);
  const [currentDayId, setCurrentDayId] = useState(null);
  const [attaching, setAttaching] = useState(null);
  const [lodgingForm, setLodgingForm] = useState(null);
  const [error, setError] = useState('');
  const [journalDrafts, setJournalDrafts] = useState({});

  const days = useMemo(
    () => [...(trip.days || [])].sort((a, b) => String(a.date).localeCompare(String(b.date))),
    [trip],
  );
  const currentDay = days.find((d) => d.id === currentDayId) || null;

  useEffect(() => {
    if (!days.length) {
      if (currentDayId != null) setCurrentDayId(null);
      return;
    }
    if (currentDayId != null && days.some((d) => d.id === currentDayId)) return;
    const today = new Date().toISOString().slice(0, 10);
    const todayDay = days.find((d) => d.date === today);
    setCurrentDayId((todayDay || days[0]).id);
  }, [days, currentDayId]);
  const locations = useMemo(() => {
    const set = new Set();
    days.forEach((d) => d.stops.forEach((s) => s.loc && set.add(s.loc)));
    return [...set].sort();
  }, [days]);
  const categories = useMemo(() => {
    const set = new Set();
    days.forEach((d) => d.stops.forEach((s) => s.cat && set.add(s.cat)));
    return [...set].sort();
  }, [days]);

  const visibleDays = useMemo(() => {
    return days.map((day) => ({
      ...day,
      stops: [...day.stops].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id)).filter((item) => {
        if (status === 'hide-done' && item.done) return false;
        if (status !== 'all' && status !== 'hide-done' && item.status !== status) return false;
        if (loc !== 'all' && item.loc !== loc) return false;
        if (cat !== 'all' && item.cat !== cat) return false;
        if (query && !`${item.text} ${item.description || ''} ${item.loc}`.toLowerCase().includes(query.toLowerCase())) return false;
        return true;
      }),
    })).filter((d) => mode === 'travelog' || d.stops.length > 0 || !query);
  }, [days, query, loc, cat, status, mode]);

  const saveDay = async (payload) => {
    if (editingDay?.id) {
      await api.json(`/api/trips/days/${editingDay.id}/`, { method: 'PATCH', body: JSON.stringify(payload) });
    } else {
      const created = await api.json('/api/trips/days/', {
        method: 'POST',
        body: JSON.stringify({ ...payload, trip_id: trip.id }),
      });
      if (created?.id) setCurrentDayId(created.id);
    }
    setAddingDay(false);
    setEditingDay(null);
    await onReload();
  };

  const assignLodging = async (day, lodgingId) => {
    await api.json(`/api/trips/days/${day.id}/`, {
      method: 'PATCH',
      body: JSON.stringify({ lodging_id: lodgingId }),
    });
    await onReload();
  };

  const deleteDay = async (day) => {
    if (!window.confirm(`Delete ${formatDay(day)} and its stops?`)) return;
    await api.json(`/api/trips/days/${day.id}/`, { method: 'DELETE' });
    await onReload();
  };

  const saveStop = async (payload) => {
    if (payload.day_id) setCurrentDayId(payload.day_id);
    if (editing?.id) {
      await api.json(`/api/trips/stops/${editing.id}/`, { method: 'PATCH', body: JSON.stringify(payload) });
    } else {
      await api.json('/api/trips/stops/', { method: 'POST', body: JSON.stringify(payload) });
    }
    setEditing(null);
    setAdding(false);
    await onReload();
  };

  const removeAttachment = async (item) => {
    if (!window.confirm('Remove this attachment?')) return;
    await api.json(`/api/trips/attachments/${item.id}/`, { method: 'DELETE' });
    await onReload();
  };

  const moveStop = async (stop, direction) => {
    await api.json(`/api/trips/stops/${stop.id}/move/`, {
      method: 'POST',
      body: JSON.stringify({ direction }),
    });
    await onReload();
  };

  const toggleDone = async (stop) => {
    await api.json(`/api/trips/stops/${stop.id}/`, {
      method: 'PATCH',
      body: JSON.stringify({ done: !stop.done }),
    });
    await onReload();
  };

  const deleteStop = async (stop) => {
    if (!window.confirm('Delete this stop?')) return;
    await api.json(`/api/trips/stops/${stop.id}/`, { method: 'DELETE' });
    await onReload();
  };

  const patchTrip = async (body) => {
    try {
      await api.json(`/api/trips/trips/${trip.id}/`, { method: 'PATCH', body: JSON.stringify(body) });
      await onReload();
    } catch (err) {
      setError(err.message);
    }
  };

  const saveJournal = async (day) => {
    const journal = journalDrafts[day.id] ?? day.journal ?? '';
    await api.json(`/api/trips/days/${day.id}/`, {
      method: 'PATCH',
      body: JSON.stringify({ journal }),
    });
    await onReload();
  };

  const uploadDayPhoto = async (day, file) => {
    const form = new FormData();
    form.append('file', file);
    form.append('add_to_gallery', 'false');
    const uploaded = await api.json('/api/gallery/upload/', { method: 'POST', body: form });
    const umId = uploaded.user_media_id;
    if (!umId) throw new Error('Upload succeeded but no library id was returned.');
    await api.json('/api/trips/media/', {
      method: 'POST',
      body: JSON.stringify({ asset_id: umId, day_id: day.id, trip_id: trip.id }),
    });
    await onReload();
  };

  return (
    <div className="trip-detail">
      <div className="trip-detail-bar">
        <button type="button" onClick={onBack}>All trips</button>
        <h2>{trip.title}</h2>
        <div className="trip-modes">
          {['plan', 'track', 'travelog'].map((m) => (
            <button
              key={m}
              type="button"
              className={mode === m ? 'is-active' : ''}
              onClick={() => setMode(m)}
            >
              {m[0].toUpperCase() + m.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="trip-links">
        <label>
          Packing list
          <select
            value={trip.packing_list || ''}
            onChange={(e) => patchTrip({ packing_list_id: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">None</option>
            {lists.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
        </label>
        <label>
          Gallery
          <select
            value={trip.gallery || ''}
            onChange={(e) => patchTrip({ gallery_id: e.target.value || null })}
          >
            <option value="">None</option>
            {galleries.map((g) => (
              <option key={g.id} value={g.id}>{g.title}</option>
            ))}
          </select>
        </label>
        {trip.packing_list && (
          <a href="/app/vacation/" className="trip-ext-link">Open packing list</a>
        )}
        {trip.gallery && (
          <a href="/app/gallery/" className="trip-ext-link">Open gallery</a>
        )}
      </div>

      {mode !== 'travelog' && (
        <div className="trip-filters">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search stops…" />
          <select value={loc} onChange={(e) => setLoc(e.target.value)}>
            <option value="all">All locations</option>
            {locations.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <select value={cat} onChange={(e) => setCat(e.target.value)}>
            <option value="all">All categories</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <div className="trip-status-tabs">
            {['all', 'tobook', 'booked', 'confirmed', 'hide-done'].map((s) => (
              <button
                key={s}
                type="button"
                className={status === s ? 'is-active' : ''}
                onClick={() => setStatus(s)}
              >
                {s === 'hide-done' ? 'Hide done' : s === 'all' ? 'All' : STATUS_LABEL[s]}
              </button>
            ))}
          </div>
          <label>
            Current day
            <select
              value={currentDayId || ''}
              onChange={(e) => setCurrentDayId(e.target.value ? Number(e.target.value) : null)}
            >
              {days.map((d) => (
                <option key={d.id} value={d.id}>{formatDay(d)}</option>
              ))}
            </select>
          </label>
          {mode === 'plan' && (
            <>
              <button type="button" onClick={() => setAddingDay(true)}>Add day</button>
              <button type="button" className="trip-primary" onClick={() => setAdding(true)} disabled={!currentDay}>
                Add stop
              </button>
            </>
          )}
        </div>
      )}

      {error && <p className="trip-error">{error}</p>}

      {visibleDays.map((day) => (
        <section
          key={day.id}
          className={`trip-day${day.id === currentDayId ? ' is-current' : ''}`}
          onClick={() => setCurrentDayId(day.id)}
        >
          <header>
            <div>
              <h3>{formatDay(day)}</h3>
              <div className="trip-lodging-line">
                {day.lodging ? (
                  <>
                    <span>Stay: {lodgingLabel(day.lodging)}</span>
                    {day.lodging.maps_url && (
                      <a href={day.lodging.maps_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>Map</a>
                    )}
                    {day.lodging.url && (
                      <a href={day.lodging.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>Site</a>
                    )}
                    <AttachmentIcons
                      attachments={
                        (trip.lodgings || []).find((l) => l.id === day.lodging.id)?.attachments
                        || day.lodging.attachments
                      }
                      canEdit={mode === 'plan'}
                      onAdd={() => setAttaching({ lodging: (trip.lodgings || []).find((l) => l.id === day.lodging.id) || day.lodging })}
                      onRemove={removeAttachment}
                    />
                    {mode === 'plan' && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          const full = (trip.lodgings || []).find((l) => l.id === day.lodging.id) || day.lodging;
                          setLodgingForm({ lodging: full, dayIds: [day.id] });
                        }}
                      >
                        Edit stay
                      </button>
                    )}
                  </>
                ) : (
                  <span className="trip-lodging-empty">No lodging</span>
                )}
                {mode === 'plan' && (
                  <select
                    value={day.lodging_id || ''}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => {
                      e.stopPropagation();
                      const value = e.target.value;
                      if (value === '__new__') {
                        setLodgingForm({ lodging: null, dayIds: [day.id] });
                        return;
                      }
                      assignLodging(day, value ? Number(value) : null).catch((err) => setError(err.message));
                    }}
                  >
                    <option value="">No lodging</option>
                    {(trip.lodgings || []).map((l) => (
                      <option key={l.id} value={l.id}>{l.name}</option>
                    ))}
                    <option value="__new__">New lodging…</option>
                  </select>
                )}
              </div>
            </div>
            {mode === 'plan' && (
              <div className="trip-stop-actions">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setCurrentDayId(day.id);
                    setAdding(true);
                  }}
                >
                  Add stop
                </button>
                <button type="button" onClick={(e) => { e.stopPropagation(); setEditingDay(day); }}>Edit</button>
                <button type="button" onClick={(e) => { e.stopPropagation(); deleteDay(day); }}>Delete</button>
              </div>
            )}
            {mode === 'travelog' && (
              <button type="button" onClick={() => saveJournal(day)}>Save journal</button>
            )}
          </header>
          {mode === 'travelog' ? (
            <div className="trip-journal">
              <MarkdownSplitEditor
                value={journalDrafts[day.id] ?? day.journal ?? ''}
                onChange={(v) => setJournalDrafts((prev) => ({ ...prev, [day.id]: v }))}
                placeholder="What happened today…"
              />
              <label className="trip-upload">
                Add photo
                <input
                  type="file"
                  accept="image/*,video/*"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) uploadDayPhoto(day, file).catch((err) => setError(err.message));
                    e.target.value = '';
                  }}
                />
              </label>
              <div className="trip-photos">
                {(day.media || []).map((m) => (
                  <img key={m.id} src={m.thumbnail_url || m.url} alt={m.caption || m.filename} />
                ))}
              </div>
            </div>
          ) : (
            <ul>
              {day.stops.map((stop, index) => (
                <li key={stop.id} className={stop.done ? 'is-done' : ''}>
                  <input
                    type="checkbox"
                    checked={!!stop.done}
                    onChange={() => toggleDone(stop)}
                    aria-label={`Done: ${stop.text}`}
                  />
                  <div>
                    <p>
                      {(stop.start_time || stop.duration_minutes != null) && (
                        <span className="trip-stop-time">
                          {[formatStopTime(stop.start_time), formatDuration(stop.duration_minutes)].filter(Boolean).join(' · ')}
                        </span>
                      )}
                      {stop.text}
                    </p>
                    {stop.description && <p className="trip-stop-desc">{stop.description}</p>}
                    <div className="trip-tags">
                      <span className={`tag ${stop.status}`}>{STATUS_LABEL[stop.status] || stop.status}</span>
                      {stop.loc && <span className="tag">{stop.loc}</span>}
                      {stop.cat && <span className="tag">{stop.cat}</span>}
                    </div>
                    <AttachmentIcons
                      attachments={stop.attachments}
                      canEdit={mode === 'plan'}
                      onAdd={() => setAttaching({ stop })}
                      onRemove={removeAttachment}
                    />
                  </div>
                  {mode === 'plan' && (
                    <div className="trip-stop-actions">
                      <button
                        type="button"
                        disabled={index === 0}
                        onClick={(e) => { e.stopPropagation(); moveStop(stop, 'up'); }}
                      >
                        Up
                      </button>
                      <button
                        type="button"
                        disabled={index === day.stops.length - 1}
                        onClick={(e) => { e.stopPropagation(); moveStop(stop, 'down'); }}
                      >
                        Down
                      </button>
                      <button type="button" onClick={(e) => { e.stopPropagation(); setEditing(stop); }}>Edit</button>
                      <button type="button" onClick={(e) => { e.stopPropagation(); deleteStop(stop); }}>Delete</button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}

      {mode === 'plan' && !days.length && (
        <p className="trip-empty">No days yet. Add a day, then add stops.</p>
      )}

      {(addingDay || editingDay) && (
        <DayForm
          initial={editingDay}
          onClose={() => { setAddingDay(false); setEditingDay(null); }}
          onSave={saveDay}
        />
      )}
      {(adding || editing) && (
        <StopForm
          days={days}
          initial={editing}
          defaultDayId={currentDayId}
          onClose={() => { setAdding(false); setEditing(null); }}
          onSave={saveStop}
        />
      )}
      {lodgingForm && (
        <LodgingForm
          trip={trip}
          days={days}
          initial={
            lodgingForm.lodging?.id
              ? (trip.lodgings || []).find((l) => l.id === lodgingForm.lodging.id) || lodgingForm.lodging
              : lodgingForm.lodging
          }
          defaultDayIds={lodgingForm.dayIds}
          onClose={() => setLodgingForm(null)}
          onAddAttachment={(lodging) => setAttaching({ lodging })}
          onRemoveAttachment={removeAttachment}
          onSaved={async () => {
            setLodgingForm(null);
            await onReload();
          }}
        />
      )}
      {attaching && (
        <AttachmentForm
          stop={attaching.stop}
          lodging={attaching.lodging}
          onClose={() => setAttaching(null)}
          onSaved={async () => {
            setAttaching(null);
            await onReload();
          }}
        />
      )}
    </div>
  );
}

export default function TripApp() {
  const { user, loading, logout, isAuthenticated } = useAuth();
  const [trips, setTrips] = useState([]);
  const [selected, setSelected] = useState(null);
  const [lists, setLists] = useState([]);
  const [galleries, setGalleries] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState('');

  const loadTrips = useCallback(async () => {
    const data = await api.json('/api/trips/trips/');
    setTrips(asList(data));
  }, []);

  const loadSelected = useCallback(async (id) => {
    const data = await api.json(`/api/trips/trips/${id}/`);
    setSelected(data);
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    Promise.all([
      loadTrips(),
      api.json('/api/vacation/lists/').then((d) => setLists(asList(d))).catch(() => setLists([])),
      api.json('/api/gallery/galleries/').then((d) => setGalleries(asList(d))).catch(() => setGalleries([])),
    ]).catch((err) => setError(err.message));
  }, [isAuthenticated, loadTrips]);

  if (loading) return <div className="p-8 text-center text-stone-500">Loading…</div>;
  if (!user) {
    window.location.replace(getLoginUrl('/app/trips/'));
    return null;
  }

  const createTrip = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    try {
      const created = await api.json('/api/trips/trips/', {
        method: 'POST',
        body: JSON.stringify({ title: title.trim() }),
      });
      setTitle('');
      await loadTrips();
      await loadSelected(created.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const seedDeathValley = async () => {
    setBusy(true);
    try {
      const data = await api.json('/api/trips/trips/seed-death-valley/', { method: 'POST', body: '{}' });
      await loadTrips();
      await loadSelected(data.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f7f6f2] text-[#202426]">
      <header className="sticky top-0 z-20 border-b border-stone-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
          <AppsMenu current="trips" />
          <span className="text-sm font-semibold text-stone-800">Trips</span>
          <div className="ml-auto flex items-center gap-3 text-sm text-stone-600">
            <span className="hidden sm:inline">{user.displayname || user.email}</span>
            <button type="button" className="hover:text-stone-900" onClick={logout}>Log out</button>
          </div>
        </div>
      </header>
      <main className="trip-app mx-auto max-w-5xl px-4 py-6">
        {error && <p className="trip-error">{error}</p>}
        {selected ? (
          <TripDetail
            trip={selected}
            lists={lists}
            galleries={galleries}
            onBack={() => setSelected(null)}
            onReload={() => loadSelected(selected.id)}
          />
        ) : (
          <div>
            <div className="trip-list-actions">
              <form onSubmit={createTrip} className="trip-create">
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="New trip title"
                />
                <button type="submit" className="trip-primary" disabled={busy}>Create</button>
              </form>
              <button type="button" onClick={seedDeathValley} disabled={busy}>
                Add Sierra & Death Valley 2026
              </button>
            </div>
            <ul className="trip-list">
              {trips.map((t) => (
                <li key={t.id}>
                  <button type="button" onClick={() => loadSelected(t.id)}>
                    <strong>{t.title}</strong>
                    <span>
                      {[t.start_date, t.end_date].filter(Boolean).join(' – ') || 'No dates'}
                      {t.day_count != null ? ` · ${t.day_count} days` : ''}
                    </span>
                  </button>
                </li>
              ))}
              {trips.length === 0 && (
                <li className="trip-empty">No trips yet. Seed Death Valley or create a blank one.</li>
              )}
            </ul>
          </div>
        )}
      </main>
    </div>
  );
}
