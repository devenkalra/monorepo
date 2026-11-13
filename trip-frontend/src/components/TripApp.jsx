import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { MarkdownSplitEditor } from '@bldrdojo/markdown-editor';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAuth } from '../contexts/AuthContext';
import { getLoginUrl } from '../utils/apiUrl';
import api from '../services/api';
import AppsMenu from './AppsMenu';

// Notes are typed line by line, so a single newline is a line break.
function remarkLineBreaks() {
  const walk = (node) => {
    if (!node.children) return;
    node.children = node.children.flatMap((child) => {
      if (child.type !== 'text' || !child.value.includes('\n')) {
        walk(child);
        return [child];
      }
      return child.value.split('\n').flatMap((part, i) => (
        i === 0 ? [{ type: 'text', value: part }] : [{ type: 'break' }, { type: 'text', value: part }]
      ));
    });
  };
  return walk;
}

const MD_PLUGINS = [remarkGfm, remarkLineBreaks];
const MD_LINK = { a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" /> };
const MD_INLINE = { ...MD_LINK, p: ({ children }) => <>{children}</> };

function Markdown({ children, inline = false, className }) {
  if (!children) return null;
  const Tag = inline ? 'span' : 'div';
  return (
    <Tag className={`trip-md${className ? ` ${className}` : ''}`}>
      <ReactMarkdown remarkPlugins={MD_PLUGINS} components={inline ? MD_INLINE : MD_LINK}>{children}</ReactMarkdown>
    </Tag>
  );
}

const STATUS_LABEL = { tobook: 'To book', booked: 'Booked', confirmed: 'Confirmed' };
const TRAVEL_MODES = [
  { id: 'flight', label: 'Flight' },
  { id: 'drive', label: 'Drive' },
  { id: 'walk', label: 'Walk' },
  { id: 'boat', label: 'Boat' },
];

function travelModeLabel(mode) {
  return TRAVEL_MODES.find((m) => m.id === mode)?.label || 'Travel';
}

function travelTitle(mode, from, to) {
  const name = travelModeLabel(mode);
  if (from && to) return `${name}: ${from} → ${to}`;
  if (from) return `${name} from ${from}`;
  if (to) return `${name} to ${to}`;
  return name;
}

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

function parseClockMinutes(value) {
  if (!value) return null;
  const [hours, minutes] = String(value).split(':');
  const h = Number(hours);
  const m = Number(minutes);
  if (!Number.isFinite(h) || !Number.isFinite(m)) return null;
  return h * 60 + m;
}

function formatClock(totalMinutes) {
  const day = 24 * 60;
  const n = ((Number(totalMinutes) % day) + day) % day;
  const h = Math.floor(n / 60);
  const m = Math.round(n % 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

const MINUTE_CHOICES = ['00', '15', '30', '45'];

function splitClock(value) {
  const total = parseClockMinutes(value);
  if (total == null) return { hour: '', minute: '', period: '' };
  const hour24 = Math.floor(total / 60);
  const minute = String(total % 60).padStart(2, '0');
  const period = hour24 >= 12 ? 'PM' : 'AM';
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  return { hour: String(hour12), minute, period };
}

function joinClock(hour, minute, period) {
  if (hour === '' && minute === '' && period === '') return '';
  if (hour === '' || period === '') return null;
  let hours = Number(hour);
  const mins = Number(minute === '' ? 0 : minute);
  if (!Number.isFinite(hours) || !Number.isFinite(mins) || mins < 0 || mins > 59) return null;
  if (period === 'PM' && hours < 12) hours += 12;
  if (period === 'AM' && hours === 12) hours = 0;
  return formatClock(hours * 60 + mins);
}

function TimeInput({ value, onChange }) {
  const parts = splitClock(value);
  const minuteChoices = MINUTE_CHOICES.includes(parts.minute) || parts.minute === ''
    ? MINUTE_CHOICES
    : [...MINUTE_CHOICES, parts.minute].sort((a, b) => Number(a) - Number(b));

  const emit = (nextHour, nextMinute, nextPeriod) => {
    if (nextHour === '' && nextMinute === '' && nextPeriod === '') {
      onChange('');
      return;
    }
    const joined = joinClock(nextHour, nextMinute === '' ? '00' : nextMinute, nextPeriod || 'AM');
    if (joined) onChange(joined);
  };

  return (
    <div className="trip-time">
      <select
        aria-label="Hour"
        value={parts.hour}
        onChange={(e) => emit(e.target.value, parts.minute, parts.period || 'AM')}
      >
        <option value="">Hour</option>
        {Array.from({ length: 12 }, (_, i) => i + 1).map((h) => (
          <option key={h} value={String(h)}>{h}</option>
        ))}
      </select>
      <select
        aria-label="Minutes"
        value={parts.minute || '00'}
        onChange={(e) => emit(parts.hour || '12', e.target.value, parts.period || 'AM')}
      >
        {minuteChoices.map((m) => (
          <option key={m} value={m}>{m}</option>
        ))}
      </select>
      <select
        aria-label="AM or PM"
        value={parts.period}
        onChange={(e) => emit(parts.hour || '12', parts.minute, e.target.value)}
      >
        <option value="">AM/PM</option>
        <option value="AM">AM</option>
        <option value="PM">PM</option>
      </select>
    </div>
  );
}

function endFromStartAndDuration(start, duration) {
  const startMin = parseClockMinutes(start);
  const mins = Number(duration);
  if (startMin == null || duration === '' || !Number.isFinite(mins)) return '';
  return formatClock(startMin + mins);
}

function durationFromStartAndEnd(start, end) {
  const startMin = parseClockMinutes(start);
  const endMin = parseClockMinutes(end);
  if (startMin == null || endMin == null) return '';
  let diff = endMin - startMin;
  if (diff < 0) diff += 24 * 60;
  return String(diff);
}

const popupHotkeyStack = [];

function usePopupHotkeys({ onSave, onClose, busy = false }) {
  const saveRef = useRef(onSave);
  const closeRef = useRef(onClose);
  const busyRef = useRef(busy);
  saveRef.current = onSave;
  closeRef.current = onClose;
  busyRef.current = busy;

  useEffect(() => {
    const entry = { saveRef, closeRef, busyRef };
    popupHotkeyStack.push(entry);
    const onKey = (event) => {
      if (popupHotkeyStack[popupHotkeyStack.length - 1] !== entry) return;
      if (event.isComposing) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        closeRef.current?.();
        return;
      }
      if (event.repeat) return;
      const modifier = event.metaKey || event.ctrlKey;
      const isSave = modifier && !event.altKey && (event.key === 'Enter' || event.code === 'KeyS');
      if (isSave) {
        if (busyRef.current) return;
        event.preventDefault();
        event.stopPropagation();
        saveRef.current?.();
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => {
      window.removeEventListener('keydown', onKey, true);
      const index = popupHotkeyStack.lastIndexOf(entry);
      if (index >= 0) popupHotkeyStack.splice(index, 1);
    };
  }, []);
}

function saveHotkeyLabel() {
  const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);
  const mod = mac ? '⌘' : 'Ctrl';
  return `${mod}+S or ${mod}+Enter`;
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

function StopGlyph() {
  return (
    <IconSvg width="14" height="14">
      <path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z" />
      <circle cx="12" cy="10" r="2.2" />
    </IconSvg>
  );
}

function TravelGlyph() {
  return (
    <IconSvg width="14" height="14">
      <path d="M3 14l2.2-5.2A1.5 1.5 0 0 1 6.6 8h10.8c.6 0 1.1.3 1.3.9L21 14" />
      <path d="M5 14h14v2.2a1 1 0 0 1-1 1h-1.2" />
      <circle cx="7.5" cy="17.2" r="1.6" />
      <circle cx="16.5" cy="17.2" r="1.6" />
      <path d="M8 8.2L9.1 5h5.8L16 8.2" />
    </IconSvg>
  );
}

function DayStopCounts({ stops }) {
  const items = stops || [];
  const travelCount = items.filter((s) => s.kind === 'travel').length;
  const stopCount = items.filter((s) => s.kind !== 'travel').length;
  return (
    <span className="trip-day-stats">
      <span className="trip-day-stat" title={`${stopCount} ${stopCount === 1 ? 'stop' : 'stops'}`}>
        <StopGlyph />
        {stopCount}
      </span>
      <span className="trip-day-stat" title={`${travelCount} travel`}>
        <TravelGlyph />
        {travelCount}
      </span>
    </span>
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

function AttachmentEditor({ stop, lodging, onSaved, addRef, pendingRef }) {
  const [kind, setKind] = useState(lodging ? 'picture' : 'url');
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [address, setAddress] = useState(lodging?.address || stop?.loc || '');
  const [lat, setLat] = useState('');
  const [lng, setLng] = useState('');
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const busyLock = useRef(false);

  const reset = () => {
    setTitle('');
    setUrl('');
    setAddress(lodging?.address || stop?.loc || '');
    setLat('');
    setLng('');
    setFile(null);
    setError('');
  };

  const add = async () => {
    if (busyLock.current) return false;
    busyLock.current = true;
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
      reset();
      await onSaved();
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      busyLock.current = false;
      setBusy(false);
    }
  };

  const hasPending = () => {
    if (kind === 'location') {
      return Boolean(url.trim() || lat !== '' || lng !== ''
        || (address.trim() && address.trim() !== (lodging?.address || stop?.loc || '').trim()));
    }
    return Boolean(url.trim() || ((kind === 'document' || kind === 'picture') && file));
  };

  useEffect(() => {
    if (addRef) addRef.current = add;
    if (pendingRef) pendingRef.current = hasPending;
    return () => {
      if (addRef?.current === add) addRef.current = null;
      if (pendingRef?.current === hasPending) pendingRef.current = null;
    };
  });

  return (
    <div className="trip-attach-editor">
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
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
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
      <div className="trip-attach-editor-actions">
        <button type="button" className="trip-primary" disabled={busy} onClick={add} title={saveHotkeyLabel()}>
          {busy ? 'Adding…' : `Add ${ATTACH_KINDS.find((k) => k.id === kind)?.label || 'item'}`}
        </button>
      </div>
    </div>
  );
}

function AttachmentForm({ stop, lodging, onClose, onSaved }) {
  const addRef = useRef(null);
  usePopupHotkeys({
    onClose,
    onSave: () => addRef.current?.(),
  });
  const label = lodging ? lodging.name : stop?.text;
  return (
    <div className="trip-modal-backdrop trip-modal-backdrop-stack" onClick={onClose} role="presentation">
      <div className="trip-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={lodging ? 'Add to lodging' : 'Add to stop'}>
        <h3>{lodging ? 'Add to lodging' : 'Add to stop'}</h3>
        <p className="trip-hint">{label}</p>
        <AttachmentEditor stop={stop} lodging={lodging} onSaved={onSaved} addRef={addRef} />
        <div className="trip-modal-actions">
          <button type="button" onClick={onClose} title="Esc">Close</button>
        </div>
      </div>
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
  const formRef = useRef(null);
  usePopupHotkeys({
    onClose,
    busy,
    onSave: () => formRef.current?.requestSubmit(),
  });

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
      <form ref={formRef} className="trip-modal trip-modal-wide" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
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
            <TimeInput value={checkIn} onChange={setCheckIn} />
          </label>
          <label>
            Check-out
            <TimeInput value={checkOut} onChange={setCheckOut} />
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
          <button type="button" onClick={onClose} title="Esc">Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy} title={saveHotkeyLabel()}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  );
}

function TripInfoForm({ trip, onClose, onSave }) {
  const [description, setDescription] = useState(trip.description || '');
  const [notes, setNotes] = useState(trip.notes || '');
  const [openItems, setOpenItems] = useState(trip.open_items || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const formRef = useRef(null);
  usePopupHotkeys({
    onClose,
    busy,
    onSave: () => formRef.current?.requestSubmit(),
  });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await onSave({ description, notes, open_items: openItems });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" onClick={onClose} role="presentation">
      <form ref={formRef} className="trip-modal trip-modal-scroll" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>Trip details · {trip.title}</h3>
        <div className="trip-modal-body">
          <label>
            Description
            <textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Who is going, how long, the overall shape of the trip…"
            />
          </label>
          <label>
            Notes (markdown; shown under To Dos in the report)
            <textarea
              rows={6}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="- Fill in the arrival card 3 days before landing"
            />
          </label>
          <label>
            Open items (markdown; decisions still to make)
            <textarea
              rows={5}
              value={openItems}
              onChange={(e) => setOpenItems(e.target.value)}
              placeholder="- Phuket or Khao Lak for the last 4 nights?"
            />
          </label>
        </div>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={onClose} title="Esc">Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy} title={saveHotkeyLabel()}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  );
}

function TripReport({ trip, onClose }) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');
  const [raw, setRaw] = useState(false);
  const [copied, setCopied] = useState(false);
  usePopupHotkeys({ onClose, busy: false });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.json(`/api/trips/trips/${trip.id}/report/`);
        if (!cancelled) setReport(data);
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [trip.id]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(report.markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      setError(err.message);
    }
  };

  const download = () => {
    const url = URL.createObjectURL(new Blob([report.markdown], { type: 'text/markdown' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = report.filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="trip-modal-backdrop" onClick={onClose} role="presentation">
      <div className="trip-modal trip-modal-bulk" onClick={(e) => e.stopPropagation()}>
        <h3>Report · {trip.title}</h3>
        <div className="trip-report">
          {!report && !error && <p className="trip-muted">Building report…</p>}
          {report && (raw
            ? <pre className="trip-report-raw">{report.markdown}</pre>
            : <Markdown>{report.markdown}</Markdown>)}
        </div>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={() => setRaw((v) => !v)} disabled={!report}>
            {raw ? 'Show formatted' : 'Show markdown'}
          </button>
          <button type="button" onClick={copy} disabled={!report}>{copied ? 'Copied' : 'Copy markdown'}</button>
          <button type="button" onClick={download} disabled={!report}>Download .md</button>
          <button type="button" className="trip-primary" onClick={onClose} title="Esc">Close</button>
        </div>
      </div>
    </div>
  );
}

function DayForm({ initial, onClose, onSave }) {
  const [date, setDate] = useState(initial?.date || '');
  const [title, setTitle] = useState(initial?.title || '');
  const [notes, setNotes] = useState(initial?.notes || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const formRef = useRef(null);
  usePopupHotkeys({
    onClose,
    busy,
    onSave: () => formRef.current?.requestSubmit(),
  });

  const submit = async (e) => {
    e.preventDefault();
    if (!date) {
      setError('Pick a date.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await onSave({ date, title: title.trim(), notes });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" onClick={onClose} role="presentation">
      <form ref={formRef} className="trip-modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>{initial?.id ? 'Edit day' : 'Add day'}</h3>
        <label>
          Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          Title
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Bay Area to Sequoia" />
        </label>
        <label>
          Notes
          <textarea
            rows={4}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="High-level plan for the day…"
          />
        </label>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={onClose} title="Esc">Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy} title={saveHotkeyLabel()}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  );
}

function StopForm({ days, initial, defaultDayId, defaultKind = 'activity', onClose, onSave, onAddAttachment, onRemoveAttachment }) {
  const kind = initial?.kind || defaultKind || 'activity';
  const isTravel = kind === 'travel';
  const [dayId, setDayId] = useState(initial?.day || initial?.day_id || defaultDayId || days[0]?.id || '');
  const [text, setText] = useState(initial?.text || '');
  const [description, setDescription] = useState(initial?.description || '');
  const [travelMode, setTravelMode] = useState(initial?.travel_mode || 'drive');
  const [loc, setLoc] = useState(initial?.loc || '');
  const [arriveLoc, setArriveLoc] = useState(initial?.arrive_loc || '');
  const [cat, setCat] = useState(initial?.cat || (isTravel ? 'Travel' : 'Sight'));
  const [status, setStatus] = useState(initial?.status || 'confirmed');
  const [startTime, setStartTime] = useState(initial?.start_time ? String(initial.start_time).slice(0, 5) : '');
  const [duration, setDuration] = useState(initial?.duration_minutes ?? '');
  const [endTime, setEndTime] = useState(() => (
    endFromStartAndDuration(
      initial?.start_time ? String(initial.start_time).slice(0, 5) : '',
      initial?.duration_minutes ?? '',
    )
  ));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const formRef = useRef(null);
  const attachAddRef = useRef(null);
  const attachPendingRef = useRef(null);
  usePopupHotkeys({
    onClose,
    busy,
    onSave: () => formRef.current?.requestSubmit(),
  });
  const selectedDay = days.find((d) => String(d.id) === String(dayId));
  const endsNextDay = parseClockMinutes(endTime) != null
    && parseClockMinutes(startTime) != null
    && parseClockMinutes(endTime) < parseClockMinutes(startTime);

  const changeStartTime = (value) => {
    setStartTime(value);
    if (duration !== '' && Number.isFinite(Number(duration))) {
      setEndTime(endFromStartAndDuration(value, duration));
    } else if (endTime) {
      setDuration(durationFromStartAndEnd(value, endTime));
    }
  };

  const changeDuration = (value) => {
    setDuration(value);
    setEndTime(endFromStartAndDuration(startTime, value));
  };

  const changeEndTime = (value) => {
    setEndTime(value);
    if (startTime) setDuration(durationFromStartAndEnd(startTime, value));
  };

  const submit = async (e) => {
    e.preventDefault();
    const title = text.trim() || (isTravel ? travelTitle(travelMode, loc.trim(), arriveLoc.trim()) : '');
    if (!title) {
      setError(isTravel ? 'Enter a title or departure/arrival locations.' : 'Enter an activity.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      if (attachPendingRef.current?.() && !(await attachAddRef.current?.())) return;
      await onSave({
        day_id: Number(dayId),
        kind,
        travel_mode: isTravel ? travelMode : '',
        text: title,
        description: description.trim(),
        loc: loc.trim(),
        arrive_loc: isTravel ? arriveLoc.trim() : '',
        cat: cat.trim() || (isTravel ? 'Travel' : ''),
        status,
        start_time: startTime || null,
        duration_minutes: duration === '' ? null : Number(duration),
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" onClick={onClose} role="presentation">
      <form ref={formRef} className="trip-modal trip-modal-scroll" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>{initial?.id ? (isTravel ? 'Edit travel' : 'Edit stop') : (isTravel ? 'Add travel' : 'Add stop')}</h3>
        <div className="trip-modal-body">
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
          {isTravel && (
            <label>
              Type
              <select value={travelMode} onChange={(e) => setTravelMode(e.target.value)}>
                {TRAVEL_MODES.map((m) => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
            </label>
          )}
          <label>
            {isTravel ? 'Title' : 'Activity'}
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={isTravel ? 2 : 3}
              placeholder={isTravel ? travelTitle(travelMode, loc, arriveLoc) : ''}
            />
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
          {isTravel && (
            <div className="trip-form-row-2">
              <label>
                Departure location
                <input value={loc} onChange={(e) => setLoc(e.target.value)} placeholder="Oakland" />
              </label>
              <label>
                Arrival location
                <input value={arriveLoc} onChange={(e) => setArriveLoc(e.target.value)} placeholder="Sequoia" />
              </label>
            </div>
          )}
          <div className="trip-form-row">
            <label>
              {isTravel ? 'Departure time' : 'Start time'}
              <TimeInput value={startTime} onChange={changeStartTime} />
            </label>
            <label>
              {isTravel ? 'Arrival time' : 'End time'}
              <TimeInput value={endTime} onChange={changeEndTime} />
              {endsNextDay && <span className="trip-hint">{isTravel ? 'Arrives next day' : 'Ends next day'}</span>}
            </label>
            <label>
              Duration (min)
              <input
                type="number"
                min="0"
                step="5"
                value={duration}
                onChange={(e) => changeDuration(e.target.value)}
                placeholder={isTravel ? '240' : '90'}
              />
            </label>
          </div>
          {isTravel ? (
            <div className="trip-form-row-2">
              <label>
                Category
                <input value={cat} onChange={(e) => setCat(e.target.value)} placeholder="Travel" />
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
          ) : (
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
          )}
          <section className="trip-attach-section">
            <h4>URLs, pictures, and locations</h4>
            {initial?.id ? (
              <>
                <AttachmentIcons
                  attachments={initial.attachments}
                  canEdit
                  onRemove={onRemoveAttachment}
                />
                <AttachmentEditor
                  stop={initial}
                  onSaved={onAddAttachment}
                  addRef={attachAddRef}
                  pendingRef={attachPendingRef}
                />
              </>
            ) : (
              <p className="trip-hint">Save the stop first to attach a URL, picture, or location.</p>
            )}
          </section>
        </div>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={onClose} title="Esc">Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy} title={saveHotkeyLabel()}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  );
}

function newBulkRow(kind = 'activity') {
  newBulkRow.next = (newBulkRow.next || 0) + 1;
  return {
    key: `new-${newBulkRow.next}`,
    id: null,
    kind,
    text: '',
    start_time: '',
    end_time: '',
    loc: '',
    arrive_loc: '',
    travel_mode: 'drive',
  };
}

function stopToBulkRow(stop) {
  const start = stop.start_time ? String(stop.start_time).slice(0, 5) : '';
  return {
    key: `id-${stop.id}`,
    id: stop.id,
    kind: stop.kind === 'travel' ? 'travel' : 'activity',
    text: stop.text || '',
    start_time: start,
    end_time: endFromStartAndDuration(start, stop.duration_minutes),
    loc: stop.loc || '',
    arrive_loc: stop.arrive_loc || '',
    travel_mode: stop.travel_mode || 'drive',
  };
}

function bulkRowHasContent(row) {
  return Boolean(
    row.text.trim()
    || row.loc.trim()
    || row.arrive_loc.trim()
    || row.start_time
    || row.end_time,
  );
}

const BULK_COL_COUNT = 6;

function isBulkTimeCol(col) {
  return col === 2 || col === 3;
}

function bulkCellEnabled(row, col) {
  if (!row || col < 0 || col >= BULK_COL_COUNT) return false;
  if (col === 5 && row.kind !== 'travel') return false;
  return true;
}

function stepBulkCell(rows, from, key) {
  if (!rows.length) return from;
  const dRow = key === 'ArrowUp' ? -1 : key === 'ArrowDown' ? 1 : 0;
  const dCol = key === 'ArrowLeft' ? -1 : key === 'ArrowRight' ? 1 : 0;
  const { row, col } = from;

  if (dRow) {
    let r = row + dRow;
    while (r >= 0 && r < rows.length) {
      if (bulkCellEnabled(rows[r], col)) {
        return { row: r, col, sub: isBulkTimeCol(col) ? from.sub : 0 };
      }
      if (col === 5 && bulkCellEnabled(rows[r], 4)) {
        return { row: r, col: 4, sub: 0 };
      }
      r += dRow;
    }
    return from;
  }

  let r = row;
  let c = col + dCol;
  while (r >= 0 && r < rows.length) {
    while (c >= 0 && c < BULK_COL_COUNT) {
      if (bulkCellEnabled(rows[r], c)) {
        return {
          row: r,
          col: c,
          sub: isBulkTimeCol(c) ? (dCol < 0 ? 2 : 0) : 0,
        };
      }
      c += dCol;
    }
    r += dCol;
    c = dCol > 0 ? 0 : BULK_COL_COUNT - 1;
  }
  return from;
}

function sameBulkCell(a, b) {
  return a.row === b.row && a.col === b.col;
}

function ClickEditCell({ active, editing = false, sub = 0, onActivate, onEdit, display, placeholder, children }) {
  const wrapRef = useRef(null);
  const displayRef = useRef(null);

  useEffect(() => {
    if (!active) return undefined;
    if (editing) {
      const fields = wrapRef.current?.querySelectorAll('input, select, textarea');
      if (!fields?.length) return undefined;
      const node = fields[Math.min(sub, fields.length - 1)];
      if (node) {
        node.focus();
        if (typeof node.select === 'function' && node.tagName === 'INPUT') node.select();
      }
    } else {
      displayRef.current?.focus({ preventScroll: true });
    }
    return undefined;
  }, [active, editing, sub]);

  if (!(active && editing)) {
    return (
      <button
        ref={displayRef}
        type="button"
        tabIndex={active ? 0 : -1}
        className={`trip-bulk-text${display ? '' : ' is-empty'}`}
        onClick={() => (active ? onEdit?.() : onActivate?.())}
      >
        {display || placeholder || '…'}
      </button>
    );
  }

  return (
    <div ref={wrapRef} className="trip-bulk-editor">
      {children}
    </div>
  );
}

function newTripDayRow(seed = {}) {
  newTripDayRow.next = (newTripDayRow.next || 0) + 1;
  return {
    key: seed.id ? `day-${seed.id}` : `new-day-${newTripDayRow.next}`,
    id: seed.id || null,
    date: seed.date || '',
    title: seed.title || '',
    notes: seed.notes || '',
  };
}

function dayAfter(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return '';
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

function tripDayRowHasContent(row) {
  return Boolean((row.date || '').trim() || (row.title || '').trim() || (row.notes || '').trim());
}

function BulkTripDaysEditor({ trip, days, onClose, onSaved }) {
  const [rows, setRows] = useState(() => {
    const existing = [...(days || [])]
      .sort((a, b) => String(a.date).localeCompare(String(b.date)))
      .map((d) => newTripDayRow(d));
    return existing.length
      ? [...existing, newTripDayRow(), newTripDayRow()]
      : [newTripDayRow(), newTripDayRow(), newTripDayRow()];
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const formRef = useRef(null);
  usePopupHotkeys({
    onClose,
    busy,
    onSave: () => formRef.current?.requestSubmit(),
  });

  const updateRow = (key, patch) => {
    setRows((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  };

  // The native picker opens on the input's value (today when empty), so seed an empty date with
  // the day after the nearest earlier dated row, then open the picker ourselves on that value.
  const seedDate = (e, index) => {
    if (rows[index].date) return;
    const prev = rows.slice(0, index).reverse().find((r) => r.date);
    const next = prev && dayAfter(prev.date);
    if (!next) return;
    const input = e.currentTarget;
    e.preventDefault();
    flushSync(() => updateRow(rows[index].key, { date: next }));
    input.focus();
    try {
      input.showPicker?.();
    } catch {
      // showPicker is unsupported or refused; the date is still filled in.
    }
  };

  // Arrows move between cells: Up/Down to the same column, Left/Right along the row. Inside text the
  // caret moves first; the jump happens only at the start/end (or first/last line of the notes).
  const moveWithArrows = (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    const el = e.target;
    const row = Number(el.dataset?.row);
    const col = Number(el.dataset?.col);
    if (!Number.isInteger(row) || !Number.isInteger(col)) return;
    const isText = el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && el.type !== 'date');
    const start = isText ? el.selectionStart : 0;
    const end = isText ? el.selectionEnd : 0;
    const atStart = !isText || (start === end && start === 0);
    const atEnd = !isText || (start === end && end === el.value.length);
    const multiline = el.tagName === 'TEXTAREA';
    let dRow = 0;
    let dCol = 0;
    if (e.key === 'ArrowUp' && !(multiline && el.value.slice(0, start).includes('\n'))) dRow = -1;
    else if (e.key === 'ArrowDown' && !(multiline && el.value.slice(end).includes('\n'))) dRow = 1;
    else if (e.key === 'ArrowLeft' && atStart) dCol = -1;
    else if (e.key === 'ArrowRight' && atEnd) dCol = 1;
    else return;
    const target = e.currentTarget.querySelector(`[data-row="${row + dRow}"][data-col="${col + dCol}"]`);
    if (!target) return;
    e.preventDefault();
    target.focus();
    if (target.type !== 'date' && typeof target.setSelectionRange === 'function') {
      const pos = dCol > 0 ? 0 : target.value.length;
      target.setSelectionRange(pos, pos);
    }
  };

  const save = async (e) => {
    e.preventDefault();
    const filled = rows.filter(tripDayRowHasContent);
    if (!filled.length) {
      setError('Add at least one day with a date.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const items = filled.map((row) => {
        if (!(row.date || '').trim()) {
          throw new Error('Every filled row needs a date.');
        }
        return {
          id: row.id || undefined,
          date: row.date.trim(),
          title: (row.title || '').trim(),
          notes: row.notes || '',
        };
      });
      await api.json(`/api/trips/trips/${trip.id}/bulk-days/`, {
        method: 'POST',
        body: JSON.stringify({ items }),
      });
      await onSaved();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" onClick={onClose} role="presentation">
      <form
        ref={formRef}
        className="trip-modal trip-modal-bulk"
        onClick={(e) => e.stopPropagation()}
        onSubmit={save}
      >
        <h3>Plan days · {trip.title}</h3>
        <p className="trip-muted">Edit dates, titles, and planning notes. Empty rows are ignored. Days not listed stay as they are.</p>
        <div className="trip-bulk-wrap">
          <table className="trip-bulk-table trip-bulk-days-table" onKeyDown={moveWithArrows}>
            <thead>
              <tr>
                <th style={{ width: '9rem' }}>Date</th>
                <th style={{ width: '14rem' }}>Title</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={row.key}>
                  <td>
                    <input
                      type="date"
                      data-row={index}
                      data-col={0}
                      value={row.date}
                      onClick={(e) => seedDate(e, index)}
                      onChange={(e) => updateRow(row.key, { date: e.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      data-row={index}
                      data-col={1}
                      value={row.title}
                      onChange={(e) => updateRow(row.key, { title: e.target.value })}
                      placeholder="Day title"
                    />
                  </td>
                  <td>
                    <textarea
                      rows={2}
                      data-row={index}
                      data-col={2}
                      value={row.notes}
                      onChange={(e) => updateRow(row.key, { notes: e.target.value })}
                      placeholder="High-level plan…"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={() => setRows((prev) => [...prev, newTripDayRow()])}>
            Add row
          </button>
          <button type="button" onClick={onClose} title="Esc">Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy} title={saveHotkeyLabel()}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  );
}

function BulkDayEditor({ day, onClose, onSaved }) {
  const [rows, setRows] = useState(() => {
    const existing = [...(day.stops || [])]
      .sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id))
      .map(stopToBulkRow);
    return [...existing, newBulkRow(), newBulkRow(), newBulkRow()];
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [active, setActive] = useState({ row: 0, col: 0, sub: 0 });
  const [isEditing, setIsEditing] = useState(false);
  const formRef = useRef(null);
  const isEditingRef = useRef(false);
  isEditingRef.current = isEditing;
  usePopupHotkeys({
    onClose: () => {
      if (isEditingRef.current) {
        setIsEditing(false);
        return;
      }
      onClose();
    },
    busy,
    onSave: () => formRef.current?.requestSubmit(),
  });

  const patchRow = (key, fields) => {
    setRows((prev) => prev.map((row) => (row.key === key ? { ...row, ...fields } : row)));
  };

  const changeStart = (row, start) => {
    const duration = durationFromStartAndEnd(row.start_time, row.end_time);
    patchRow(row.key, {
      start_time: start,
      end_time: duration !== '' ? endFromStartAndDuration(start, duration) : row.end_time,
    });
  };

  const selectCell = (row, col) => {
    setActive({ row, col, sub: 0 });
    setIsEditing(false);
  };

  const editCell = (row, col) => {
    setActive({ row, col, sub: 0 });
    setIsEditing(true);
  };

  const onTableKeyDown = (event) => {
    if (event.altKey || event.metaKey || event.ctrlKey || event.isComposing) return;
    const { key } = event;

    if (key === 'Enter') {
      event.preventDefault();
      event.stopPropagation();
      setIsEditing((prev) => !prev);
      return;
    }

    if (key === 'Tab') {
      const next = stepBulkCell(rows, active, event.shiftKey ? 'ArrowLeft' : 'ArrowRight');
      if (sameBulkCell(next, active)) {
        setIsEditing(false);
        if (event.shiftKey) return;
        event.preventDefault();
        event.stopPropagation();
        formRef.current?.querySelector('.trip-modal-actions button')?.focus();
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      setActive({ ...next, sub: 0 });
      setIsEditing(false);
      return;
    }

    if (key !== 'ArrowLeft' && key !== 'ArrowRight' && key !== 'ArrowUp' && key !== 'ArrowDown') return;
    if (isEditing) {
      const el = event.target;
      const td = el.closest?.('td');
      const fields = td ? [...td.querySelectorAll('input, select, textarea')] : [];
      const sub = Math.max(0, fields.indexOf(el));
      const subCount = fields.length || 1;
      if (key === 'ArrowLeft' && sub > 0) {
        event.preventDefault();
        event.stopPropagation();
        setActive((prev) => ({ ...prev, sub: sub - 1 }));
        return;
      }
      if (key === 'ArrowRight' && sub < subCount - 1) {
        event.preventDefault();
        event.stopPropagation();
        setActive((prev) => ({ ...prev, sub: sub + 1 }));
        return;
      }
      if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
        if (key === 'ArrowLeft' && !(el.selectionStart === 0 && el.selectionEnd === 0)) return;
        if (key === 'ArrowRight') {
          const len = el.value.length;
          if (!(el.selectionStart === len && el.selectionEnd === len)) return;
        }
      }
      if (el instanceof HTMLSelectElement && (key === 'ArrowUp' || key === 'ArrowDown')) return;
    }
    event.preventDefault();
    event.stopPropagation();
    setIsEditing(false);
    setActive((prev) => stepBulkCell(rows, { ...prev, sub: 0 }, key));
  };

  const removeRow = (key) => {
    const idx = rows.findIndex((item) => item.key === key);
    const next = rows.filter((item) => item.key !== key);
    setRows(next);
    setIsEditing(false);
    setActive((prev) => {
      if (!next.length) return { row: 0, col: 0, sub: 0 };
      let nextRow = prev.row;
      if (idx >= 0 && prev.row > idx) nextRow -= 1;
      if (idx >= 0 && prev.row === idx) nextRow = Math.min(prev.row, next.length - 1);
      nextRow = Math.max(0, Math.min(nextRow, next.length - 1));
      const col = bulkCellEnabled(next[nextRow], prev.col) ? prev.col : 4;
      return { row: nextRow, col, sub: 0 };
    });
  };

  const save = async (e) => {
    e.preventDefault();
    const filled = rows.filter(bulkRowHasContent);
    if (!filled.length && (day.stops || []).length) {
      if (!window.confirm(`Remove all stops from ${formatDay(day)}?`)) return;
    }
    setBusy(true);
    setError('');
    try {
      const items = filled.map((row) => {
        const isTravel = row.kind === 'travel';
        const title = row.text.trim() || (isTravel ? travelTitle(row.travel_mode, row.loc.trim(), row.arrive_loc.trim()) : '');
        if (!title) throw new Error('Each row needs a title, or travel locations.');
        const duration = durationFromStartAndEnd(row.start_time, row.end_time);
        return {
          ...(row.id ? { id: row.id } : {}),
          kind: isTravel ? 'travel' : 'activity',
          travel_mode: isTravel ? (row.travel_mode || 'drive') : '',
          text: title,
          loc: row.loc.trim(),
          arrive_loc: isTravel ? row.arrive_loc.trim() : '',
          start_time: row.start_time || null,
          duration_minutes: duration === '' ? null : Number(duration),
        };
      });
      await api.json(`/api/trips/days/${day.id}/bulk-stops/`, {
        method: 'POST',
        body: JSON.stringify({ items }),
      });
      await onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" onClick={onClose} role="presentation">
      <form ref={formRef} className="trip-modal trip-modal-bulk" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h3>Bulk edit · {formatDay(day)}</h3>
        <p className="trip-hint">Edit this day’s stops and travel in one table. Empty rows are ignored. Arrows select a cell, Enter edits, Tab moves right.</p>
        <div className="trip-bulk-wrap">
          <table className="trip-bulk-table" onKeyDownCapture={onTableKeyDown}>
            <thead>
              <tr>
                <th>Type</th>
                <th>Title</th>
                <th>Start</th>
                <th>End</th>
                <th>Location</th>
                <th>Arrival location</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const isTravel = row.kind === 'travel';
                const cellClass = (col) => (active.row === index && active.col === col ? 'is-active' : undefined);
                const cellProps = (col) => ({
                  active: active.row === index && active.col === col,
                  editing: isEditing && active.row === index && active.col === col,
                  sub: active.sub,
                  onActivate: () => selectCell(index, col),
                  onEdit: () => editCell(index, col),
                });
                return (
                  <tr key={row.key}>
                    <td className={cellClass(0)}>
                      <ClickEditCell {...cellProps(0)} display={isTravel ? 'Travel' : 'Stop'}>
                        <select
                          value={row.kind}
                          onChange={(e) => {
                            const kind = e.target.value;
                            patchRow(row.key, { kind });
                            if (kind !== 'travel' && active.row === index && active.col === 5) {
                              setActive((prev) => ({ ...prev, col: 4, sub: 0 }));
                            }
                          }}
                          aria-label="Type"
                        >
                          <option value="activity">Stop</option>
                          <option value="travel">Travel</option>
                        </select>
                      </ClickEditCell>
                    </td>
                    <td className={cellClass(1)}>
                      <ClickEditCell
                        {...cellProps(1)}
                        display={row.text}
                        placeholder={isTravel ? travelTitle(row.travel_mode, row.loc, row.arrive_loc) || 'Title' : 'Title'}
                      >
                        <input
                          value={row.text}
                          onChange={(e) => patchRow(row.key, { text: e.target.value })}
                          placeholder={isTravel ? travelTitle(row.travel_mode, row.loc, row.arrive_loc) : 'Activity'}
                        />
                      </ClickEditCell>
                    </td>
                    <td className={cellClass(2)}>
                      <ClickEditCell
                        {...cellProps(2)}
                        display={formatStopTime(row.start_time)}
                        placeholder="Start"
                      >
                        <TimeInput value={row.start_time} onChange={(v) => changeStart(row, v)} />
                      </ClickEditCell>
                    </td>
                    <td className={cellClass(3)}>
                      <ClickEditCell
                        {...cellProps(3)}
                        display={formatStopTime(row.end_time)}
                        placeholder="End"
                      >
                        <TimeInput value={row.end_time} onChange={(v) => patchRow(row.key, { end_time: v })} />
                      </ClickEditCell>
                    </td>
                    <td className={cellClass(4)}>
                      <ClickEditCell
                        {...cellProps(4)}
                        display={row.loc}
                        placeholder={isTravel ? 'Departure' : 'Location'}
                      >
                        <input
                          value={row.loc}
                          onChange={(e) => patchRow(row.key, { loc: e.target.value })}
                          placeholder={isTravel ? 'Departure' : 'Location'}
                        />
                      </ClickEditCell>
                    </td>
                    <td className={cellClass(5)}>
                      {isTravel ? (
                        <ClickEditCell
                          {...cellProps(5)}
                          display={row.arrive_loc}
                          placeholder="Arrival"
                        >
                          <input
                            value={row.arrive_loc}
                            onChange={(e) => patchRow(row.key, { arrive_loc: e.target.value })}
                            placeholder="Arrival"
                          />
                        </ClickEditCell>
                      ) : (
                        <span className="trip-bulk-na">—</span>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        tabIndex={-1}
                        onClick={() => removeRow(row.key)}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={() => setRows((prev) => [...prev, newBulkRow()])}>Add row</button>
          <button type="button" onClick={onClose} title="Esc">Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy} title={saveHotkeyLabel()}>
            {busy ? 'Saving…' : 'Save all'}
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
  const [adding, setAdding] = useState(null);
  const [addingDay, setAddingDay] = useState(false);
  const [editingDay, setEditingDay] = useState(null);
  const [currentDayId, setCurrentDayId] = useState(null);
  const [attaching, setAttaching] = useState(null);
  const [lodgingForm, setLodgingForm] = useState(null);
  const [bulkDay, setBulkDay] = useState(null);
  const [bulkTripDays, setBulkTripDays] = useState(false);
  const [editingInfo, setEditingInfo] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const [journalDrafts, setJournalDrafts] = useState({});
  const [collapsedDayIds, setCollapsedDayIds] = useState(() => new Set());

  const days = useMemo(
    () => [...(trip.days || [])].sort((a, b) => String(a.date).localeCompare(String(b.date))),
    [trip],
  );
  const currentDay = days.find((d) => d.id === currentDayId) || null;
  const expandAllDays = () => setCollapsedDayIds(new Set());
  const collapseAllDays = () => setCollapsedDayIds(new Set(days.map((d) => d.id)));
  const toggleDayCollapsed = (id) => {
    setCollapsedDayIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

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
    days.forEach((d) => d.stops.forEach((s) => {
      if (s.loc) set.add(s.loc);
      if (s.arrive_loc) set.add(s.arrive_loc);
    }));
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
        if (loc !== 'all' && item.loc !== loc && item.arrive_loc !== loc) return false;
        if (cat !== 'all' && item.cat !== cat) return false;
        if (query && !`${item.text} ${item.description || ''} ${item.loc} ${item.arrive_loc || ''} ${item.travel_mode || ''}`.toLowerCase().includes(query.toLowerCase())) return false;
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
      setEditing(null);
      setAdding(null);
    } else {
      const created = await api.json('/api/trips/stops/', { method: 'POST', body: JSON.stringify(payload) });
      setAdding(null);
      setEditing(created);
    }
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

  const exportTrip = async () => {
    setExporting(true);
    setError('');
    try {
      const res = await api.fetch(`/api/trips/trips/${trip.id}/export/`);
      if (!res.ok) throw new Error(`Export failed (HTTP ${res.status})`);
      const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '')?.[1] || 'trip-export.zip';
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement('a');
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(false);
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
        <button type="button" onClick={() => setEditingInfo(true)}>Details</button>
        <button type="button" onClick={() => setShowReport(true)}>Report</button>
        <button type="button" onClick={exportTrip} disabled={exporting} title="Download this trip with its uploaded files, to import elsewhere">
          {exporting ? 'Exporting…' : 'Export'}
        </button>
      </div>
      <Markdown className="trip-description">{trip.description}</Markdown>

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
              <button type="button" onClick={() => setBulkTripDays(true)}>
                Plan days
              </button>
              <button type="button" className="trip-primary" onClick={() => setAdding('activity')} disabled={!currentDay}>
                Add stop
              </button>
              <button type="button" onClick={() => setAdding('travel')} disabled={!currentDay}>
                Add travel
              </button>
              <button type="button" onClick={() => setBulkDay(currentDay)} disabled={!currentDay}>
                Bulk edit
              </button>
            </>
          )}
        </div>
      )}

      {error && <p className="trip-error">{error}</p>}

      {!!visibleDays.length && (
        <div className="trip-fold-bar">
          <button type="button" onClick={expandAllDays}>Expand all days</button>
          <button type="button" onClick={collapseAllDays}>Collapse all days</button>
        </div>
      )}

      {visibleDays.map((day) => {
        const collapsed = collapsedDayIds.has(day.id);
        return (
        <section
          key={day.id}
          className={`trip-day${day.id === currentDayId ? ' is-current' : ''}${collapsed ? ' is-collapsed' : ''}`}
          onClick={() => setCurrentDayId(day.id)}
        >
          <header>
            <div>
              <h3>
                <button
                  type="button"
                  className="trip-day-fold"
                  aria-expanded={!collapsed}
                  title={collapsed ? 'Expand day' : 'Collapse day'}
                  onClick={(e) => {
                    e.stopPropagation();
                    setCurrentDayId(day.id);
                    toggleDayCollapsed(day.id);
                  }}
                >
                  <span className="trip-day-chevron" aria-hidden="true">{collapsed ? '▶' : '▼'}</span>
                  {formatDay(day)}
                  <DayStopCounts stops={(days.find((d) => d.id === day.id) || day).stops} />
                </button>
              </h3>
              {collapsed ? (
                <p className="trip-lodging-line trip-lodging-collapsed">
                  {day.notes ? day.notes.split('\n')[0] : (day.lodging?.name || '\u00a0')}
                </p>
              ) : (
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
              )}
            </div>
            {!collapsed && mode === 'plan' && (
              <div className="trip-stop-actions">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setCurrentDayId(day.id);
                    setAdding('activity');
                  }}
                >
                  Add stop
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setCurrentDayId(day.id);
                    setAdding('travel');
                  }}
                >
                  Add travel
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setCurrentDayId(day.id);
                    setBulkDay(days.find((d) => d.id === day.id) || day);
                  }}
                >
                  Bulk edit
                </button>
                <button type="button" onClick={(e) => { e.stopPropagation(); setEditingDay(day); }}>Edit</button>
                <button type="button" onClick={(e) => { e.stopPropagation(); deleteDay(day); }}>Delete</button>
              </div>
            )}
            {!collapsed && mode === 'travelog' && (
              <button type="button" onClick={() => saveJournal(day)}>Save journal</button>
            )}
          </header>
          {!collapsed && mode === 'plan' && day.notes && (
            <Markdown className="trip-day-notes">{day.notes}</Markdown>
          )}
          {!collapsed && (mode === 'travelog' ? (
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
                <li key={stop.id} className={`${stop.done ? 'is-done' : ''}${stop.kind === 'travel' ? ' is-travel' : ''}`.trim()}>
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
                          {[
                            formatStopTime(stop.start_time),
                            formatStopTime(endFromStartAndDuration(stop.start_time, stop.duration_minutes)),
                            formatDuration(stop.duration_minutes),
                          ].filter(Boolean).join(' · ')}
                        </span>
                      )}
                      <Markdown inline>{stop.text}</Markdown>
                    </p>
                    <Markdown className="trip-stop-desc">{stop.description}</Markdown>
                    <div className="trip-tags">
                      {stop.kind === 'travel' && (
                        <span className="tag travel">{travelModeLabel(stop.travel_mode)}</span>
                      )}
                      <span className={`tag ${stop.status}`}>{STATUS_LABEL[stop.status] || stop.status}</span>
                      {stop.kind === 'travel' && (stop.loc || stop.arrive_loc) ? (
                        <span className="tag">{[stop.loc, stop.arrive_loc].filter(Boolean).join(' → ')}</span>
                      ) : (
                        stop.loc && <span className="tag">{stop.loc}</span>
                      )}
                      {stop.cat && <span className="tag">{stop.cat}</span>}
                    </div>
                    <AttachmentIcons attachments={stop.attachments} />
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
          ))}
        </section>
        );
      })}

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
          key={editing?.id || adding || 'new'}
          days={days}
          initial={
            editing?.id
              ? days.flatMap((d) => d.stops).find((s) => s.id === editing.id) || editing
              : editing
          }
          defaultDayId={currentDayId}
          defaultKind={editing?.kind || adding || 'activity'}
          onClose={() => { setAdding(null); setEditing(null); }}
          onSave={saveStop}
          onAddAttachment={onReload}
          onRemoveAttachment={removeAttachment}
        />
      )}
      {bulkDay && (
        <BulkDayEditor
          day={days.find((d) => d.id === bulkDay.id) || bulkDay}
          onClose={() => setBulkDay(null)}
          onSaved={async () => {
            setBulkDay(null);
            await onReload();
          }}
        />
      )}
      {editingInfo && (
        <TripInfoForm
          trip={trip}
          onClose={() => setEditingInfo(false)}
          onSave={async (body) => {
            await api.json(`/api/trips/trips/${trip.id}/`, { method: 'PATCH', body: JSON.stringify(body) });
            setEditingInfo(false);
            await onReload();
          }}
        />
      )}
      {showReport && <TripReport trip={trip} onClose={() => setShowReport(false)} />}
      {bulkTripDays && (
        <BulkTripDaysEditor
          trip={trip}
          days={days}
          onClose={() => setBulkTripDays(false)}
          onSaved={async () => {
            setBulkTripDays(false);
            await onReload();
          }}
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

  const importTrip = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      const data = await api.json('/api/trips/trips/import/', { method: 'POST', body: form });
      await loadTrips();
      if (data.trips?.length === 1) await loadSelected(data.trips[0].id);
    } catch (err) {
      setError(`Import failed: ${err.message}`);
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
              <label className={`trip-import${busy ? ' is-disabled' : ''}`} title="Import a trip exported from another server (.zip)">
                {busy ? 'Working…' : 'Import trip…'}
                <input type="file" accept=".zip,.json,application/zip,application/json" onChange={importTrip} disabled={busy} hidden />
              </label>
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
