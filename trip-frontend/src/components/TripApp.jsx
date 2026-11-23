import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { MarkdownSplitEditor } from '@bldrdojo/markdown-editor';
import {
  dayDiff, epochToZoned, loadCityIndex, localZone, searchCities, zoneAbbr, zoneCity, zonedToEpoch,
} from '@bldrdojo/timezones';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAuth } from '../contexts/AuthContext';
import { getLoginUrl } from '../utils/apiUrl';
import api from '../services/api';
import AppsMenu from './AppsMenu';
import TripAssistant from './TripAssistant';
import TripCalendar, { continuingStops, formatMinutes, overlappingStopIds } from './TripCalendar';
import {
  buildCommentIndex,
  CommentCountButton,
  CommentsDrawer,
  ShareTripModal,
} from './TripCollaboration';
import { IdeasRail, IdeasWorkspace, PrepWorkspace, RouteWorkspace } from './TripWorkspaces';

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

const STATUS_LABEL = {
  option: 'Option',
  no_booking: 'No booking needed',
  tobook: 'To book',
  booked: 'Booked',
  confirmed: 'Confirmed',
};
const STATUS_KEYS = ['option', 'no_booking', 'tobook', 'booked', 'confirmed'];
const TRAVEL_MODES = [
  { id: 'flight', label: 'Flight' },
  { id: 'drive', label: 'Drive' },
  { id: 'walk', label: 'Walk' },
  { id: 'boat', label: 'Boat' },
];

// Outline icons drawn on a 24×24 grid (shapes follow the Lucide icon set).
const ICON_PATHS = {
  edit: ['M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z', 'm15 5 4 4'],
  trash: ['M3 6h18', 'M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6', 'M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2', 'M10 11v6', 'M14 11v6'],
  up: ['m5 12 7-7 7 7', 'M12 19V5'],
  down: ['M12 5v14', 'm19 12-7 7-7-7'],
  stop: ['M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0', 'M12 7v6', 'M9 10h6'],
  travel: ['M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2', 'M9 17h6', 'M5 17a2 2 0 1 0 4 0a2 2 0 1 0-4 0', 'M15 17a2 2 0 1 0 4 0a2 2 0 1 0-4 0'],
  event: ['M8 2v4', 'M16 2v4', 'M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z', 'M3 10h18', 'M12 14v4', 'M10 16h4'],
  todo: ['m9 11 3 3L22 4', 'M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11'],
  table: ['M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z', 'M3 9h18', 'M3 15h18', 'M9 3v18'],
  list: ['M8 6h13', 'M8 12h13', 'M8 18h13', 'M3 6h.01', 'M3 12h.01', 'M3 18h.01'],
  dayAdd: ['M8 2v4', 'M16 2v4', 'M21 13V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h8', 'M3 10h18', 'M16 19h6', 'M19 16v6'],
  save: ['M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z', 'M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7', 'M7 3v4a1 1 0 0 0 1 1h7'],
  info: ['M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20', 'M12 16v-4', 'M12 8h.01'],
  docs: ['M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z', 'M14 2v4a2 2 0 0 0 2 2h4', 'M10 9H8', 'M16 13H8', 'M16 17H8'],
  report: ['M9 2h6a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z', 'M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2', 'M12 11h4', 'M12 16h4', 'M8 11h.01', 'M8 16h.01'],
  ai: ['M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z'],
  download: ['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'm7 10 5 5 5-5', 'M12 15V3'],
  expandAll: ['m7 6 5 5 5-5', 'm7 13 5 5 5-5'],
  collapseAll: ['m17 11-5-5-5 5', 'm17 18-5-5-5 5'],
  comment: ['M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'],
  share: ['M18 5a3 3 0 1 0 0 6 3 3 0 1 0 0-6z', 'M6 12a3 3 0 1 0 0 6 3 3 0 1 0 0-6z', 'M18 19a3 3 0 1 0 0 6 3 3 0 1 0 0-6z', 'm8.59 13.51 6.83 3.98', 'm15.41 6.51-6.82 3.98'],
};

function Icon({ name, size = 16 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {ICON_PATHS[name].map((d) => <path key={d} d={d} />)}
    </svg>
  );
}

/** Square icon-only button; `label` is the tooltip and the accessible name. */
function IconButton({ icon, label, onClick, className = '', badge, stop = true, ...rest }) {
  return (
    <button
      type="button"
      className={`trip-icon-btn ${className}`}
      title={label}
      aria-label={badge ? `${label} (${badge})` : label}
      onClick={(e) => {
        if (stop) e.stopPropagation();
        onClick?.(e);
      }}
      {...rest}
    >
      <Icon name={icon} />
      {badge ? <span className="trip-icon-badge">{badge}</span> : null}
    </button>
  );
}

const KIND_NOUN = { activity: 'stop', travel: 'travel', event: 'event' };
const KIND_LABEL = { activity: 'Stop', travel: 'Travel', event: 'Event' };

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

const DEFAULT_CURRENCY = 'USD';
const DEFAULT_CURRENCY_SYMBOL = '$';
const CURRENCY_SYMBOLS = { $: '', '€': 'EUR', '£': 'GBP', '¥': 'JPY', '฿': 'THB', '₹': 'INR' };

/** "120", "$120", "THB 1,500", "1500 thb", "฿1500" -> { price: '1500', currency: 'THB' }; null when unreadable. */
function parsePrice(text) {
  const value = String(text || '').trim();
  if (!value) return { price: null, currency: '' };
  const m = value.match(/^([A-Za-z]{3})?\s*([$€£¥฿₹])?\s*(-?[\d,]*\.?\d+)\s*([A-Za-z]{3})?$/);
  if (!m || (m[1] && m[4])) return null;
  const amount = Number(m[3].replace(/,/g, ''));
  if (!Number.isFinite(amount)) return null;
  let currency = (m[1] || m[4] || '').toUpperCase() || CURRENCY_SYMBOLS[m[2] || '$'];
  if (currency === DEFAULT_CURRENCY) currency = '';
  return { price: amount.toFixed(2), currency };
}

function formatPrice(price, currency) {
  if (price == null || price === '') return '';
  const n = Number(price);
  const text = n.toLocaleString('en-US', { minimumFractionDigits: Number.isInteger(n) ? 0 : 2, maximumFractionDigits: 2 });
  return currency ? `${currency} ${text}` : `${DEFAULT_CURRENCY_SYMBOL}${text}`;
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
  const minuteListId = useId();
  const [minuteDraft, setMinuteDraft] = useState(null);

  const typeMinute = (text) => {
    const digits = text.replace(/\D/g, '').slice(0, 2);
    setMinuteDraft(digits);
    const n = Number(digits);
    if (digits !== '' && n <= 59) emit(parts.hour || '12', String(n).padStart(2, '0'), parts.period || 'AM');
  };

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
      <input
        aria-label="Minutes"
        className="trip-time-minutes"
        inputMode="numeric"
        maxLength={2}
        list={minuteListId}
        placeholder={parts.minute || '00'}
        value={minuteDraft ?? (parts.minute || '00')}
        onChange={(e) => typeMinute(e.target.value)}
        onFocus={() => setMinuteDraft('')}
        onBlur={() => setMinuteDraft(null)}
      />
      <datalist id={minuteListId}>
        {MINUTE_CHOICES.map((m) => <option key={m} value={m} />)}
      </datalist>
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

function addDays(date, n) {
  const d = new Date(`${date}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Arrival { time, offset } for leaving `start` on `date` in `fromZone`, `duration` minutes later, in `toZone`. */
function zonedEnd(date, start, duration, fromZone, toZone) {
  const mins = Number(duration);
  if (!start || duration === '' || duration == null || !Number.isFinite(mins)) return null;
  if (!date || !fromZone || !toZone) {
    const total = parseClockMinutes(start) + mins;
    return { time: formatClock(total), offset: Math.floor(total / 1440) };
  }
  const end = epochToZoned(zonedToEpoch(date, start, fromZone) + mins * 60000, toZone);
  return { time: end.time, offset: dayDiff(date, end.date) };
}

/** Minutes from `start` in `fromZone` to the next `end` in `toZone` (which may fall on the day before). */
function zonedDuration(date, start, end, fromZone, toZone) {
  if (!date || !fromZone || !toZone || fromZone === toZone) return durationFromStartAndEnd(start, end);
  if (!start || !end) return '';
  const dep = zonedToEpoch(date, start, fromZone);
  const gaps = [-1, 0, 1, 2]
    .map((n) => Math.round((zonedToEpoch(addDays(date, n), end, toZone) - dep) / 60000))
    .filter((m) => m >= 0);
  return gaps.length ? String(Math.min(...gaps)) : '';
}

function dayOffsetLabel(offset) {
  return offset ? ` (${offset > 0 ? '+' : '−'}${Math.abs(offset)})` : '';
}

function zoneLabel(zone, date) {
  if (!zone) return '';
  const when = date ? zonedToEpoch(date, '12:00', zone) : Date.now();
  return `${zoneAbbr(zone, when)} · ${zone === 'UTC' ? 'UTC' : zoneCity(zone)}`;
}

/**
 * Which zone each day and item is in. The zone runs through the trip in itinerary order: it starts
 * at the trip's zone, a day may set its own, and travel switches it to the arrival zone for
 * everything after. An item's own zone overrides only that item. Mirrors trips/zones.py.
 */
function resolveTripZones(trip, days) {
  const tripZone = trip?.timezone || localZone();
  let zone = tripZone;
  const dayInfo = {};
  const stopInfo = {};
  for (const day of [...days].sort((a, b) => String(a.date).localeCompare(String(b.date)))) {
    const inherited = zone;
    if (day.timezone) zone = day.timezone;
    const start = zone;
    const zones = [zone];
    let overnight = false;
    const stops = [...(day.stops || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id));
    for (const stop of stops) {
      const own = stop.timezone || zone;
      const info = { inherited: zone, zone: own, arriveZone: own, arrive: null, afterOvernight: overnight };
      if (stop.kind === 'travel') {
        info.arriveZone = stop.arrive_timezone || own;
        const startTime = stop.start_time ? String(stop.start_time).slice(0, 5) : '';
        info.arrive = zonedEnd(day.date, startTime, stop.duration_minutes, own, info.arriveZone);
        overnight = overnight || (info.arrive?.offset || 0) > 0;
        zone = info.arriveZone;
      }
      for (const z of [own, info.arriveZone]) if (!zones.includes(z)) zones.push(z);
      stopInfo[stop.id] = info;
    }
    dayInfo[day.id] = { inherited, start, end: zone, zones };
  }
  return { tripZone, days: dayInfo, stops: stopInfo };
}

/** Time zone chooser: city search, or blank to inherit `inherited`. */
function TimeZoneField({ label, value, inherited, inheritedNote, date, onChange, allowBlank = true }) {
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(null);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const effective = value || inherited;
  const results = useMemo(() => (index ? searchCities(index, query, 8) : []), [index, query]);

  const ensureIndex = () => {
    if (!index) loadCityIndex().then(setIndex).catch(() => {});
  };
  const pick = (zone) => {
    onChange(zone);
    setQuery('');
    setOpen(false);
  };

  return (
    <label className="trip-tz-field">
      {label}
      <span className="trip-tz-current">
        <strong>{zoneLabel(effective, date) || 'Not set'}</strong>
        {!value && inheritedNote && <span className="trip-muted"> ({inheritedNote})</span>}
        {value && allowBlank && (
          <button type="button" className="trip-link-button" onClick={() => onChange('')}>Reset</button>
        )}
      </span>
      <span className="trip-tz-search">
        <input
          value={query}
          placeholder="Change: search a city…"
          onFocus={ensureIndex}
          onChange={(e) => { ensureIndex(); setQuery(e.target.value); setOpen(true); setHighlight(0); }}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (!open || !results.length) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); setHighlight((h) => Math.min(h + 1, results.length - 1)); }
            if (e.key === 'ArrowUp') { e.preventDefault(); setHighlight((h) => Math.max(h - 1, 0)); }
            if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); pick(results[highlight].timezone); }
          }}
        />
        {open && query.trim() && (
          <ul className="trip-tz-results" role="listbox">
            {!index && <li className="trip-muted">Loading cities…</li>}
            {index && !results.length && <li className="trip-muted">No matching city</li>}
            {results.map((r, i) => (
              <li
                key={`${r.label}|${r.detail}|${r.timezone}`}
                role="option"
                aria-selected={i === highlight}
                className={i === highlight ? 'is-active' : ''}
                onMouseDown={(e) => { e.preventDefault(); pick(r.timezone); }}
              >
                <span>{r.label}<span className="trip-muted">, {r.detail}</span></span>
                <span className="trip-muted">{zoneAbbr(r.timezone)}</span>
              </li>
            ))}
          </ul>
        )}
      </span>
    </label>
  );
}

const popupHotkeyStack = [];

// A drag that starts inside a popup (selecting text, resizing a text box) and is released over
// the backdrop still fires a click on the backdrop, so only close when the press began there too.
let backdropPressed = null;

function backdropDismiss(onClose) {
  return {
    onMouseDown: (e) => {
      if (e.target === e.currentTarget) backdropPressed = e.currentTarget;
      else if (backdropPressed === e.currentTarget) backdropPressed = null;
    },
    onClick: (e) => {
      const pressed = backdropPressed === e.currentTarget && e.target === e.currentTarget;
      backdropPressed = null;
      if (pressed) onClose();
    },
  };
}

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

function InlineRename({ value, onSave, onCancel }) {
  const [draft, setDraft] = useState(value);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const commit = async () => {
    const next = draft.trim();
    if (!next || next === value) {
      onCancel();
      return;
    }
    setBusy(true);
    setError('');
    try {
      await onSave(next);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };
  usePopupHotkeys({ onClose: onCancel, onSave: commit, busy });
  return (
    <span className="trip-rename">
      <input
        autoFocus
        value={draft}
        disabled={busy}
        onChange={(e) => setDraft(e.target.value)}
        onFocus={(e) => e.target.select()}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            commit();
          }
        }}
        aria-label="New name"
      />
      <button type="button" onClick={commit} disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
      <button type="button" onClick={onCancel} disabled={busy}>Cancel</button>
      {error && <span className="trip-error">{error}</span>}
    </span>
  );
}

function AttachmentIcons({ attachments, onAdd, onRemove, onRename, canEdit }) {
  const [renamingId, setRenamingId] = useState(null);
  if (!attachments?.length && !canEdit) return null;
  const named = canEdit && onRename;
  return (
    <div className={`trip-attach-icons${named ? ' is-named' : ''}`} onClick={(e) => e.stopPropagation()}>
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
            {named && renamingId === item.id && (
              <InlineRename
                value={item.title || ''}
                onCancel={() => setRenamingId(null)}
                onSave={async (title) => {
                  await onRename(item, title);
                  setRenamingId(null);
                }}
              />
            )}
            {named && renamingId !== item.id && (
              <>
                <span className="trip-attach-name">{label}</span>
                <button
                  type="button"
                  className="trip-attach-rename"
                  onClick={() => setRenamingId(item.id)}
                  aria-label={`Rename ${label}`}
                  title="Rename"
                >
                  ✎
                </button>
              </>
            )}
            {canEdit && onRemove && renamingId !== item.id && (
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

function AttachmentEditor({ stop, lodging, tripId, onSaved, addRef, pendingRef }) {
  const [kind, setKind] = useState(lodging ? 'picture' : 'url');
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [address, setAddress] = useState(lodging?.address || stop?.loc || '');
  const [lat, setLat] = useState('');
  const [lng, setLng] = useState('');
  const [file, setFile] = useState(null);
  const [uploadedDocs, setUploadedDocs] = useState(null);
  const [existingId, setExistingId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const busyLock = useRef(false);

  useEffect(() => {
    if (kind !== 'document' || uploadedDocs) return;
    api.json('/api/trips/attachments/documents/').then(setUploadedDocs).catch(() => setUploadedDocs([]));
  }, [kind, uploadedDocs]);

  const docChoices = useMemo(() => {
    const attached = new Set((stop || lodging)?.attachments?.map((a) => (a.asset ? `a${a.asset}` : `u${a.url}`)) || []);
    const available = (uploadedDocs || []).filter((d) => !attached.has(d.asset_id ? `a${d.asset_id}` : `u${d.url}`));
    const here = available.filter((d) => tripId != null && d.trip_id === tripId);
    const elsewhere = available.filter((d) => !(tripId != null && d.trip_id === tripId));
    const byTrip = [...new Set(elsewhere.map((d) => d.trip_title))]
      .map((t) => [t, elsewhere.filter((d) => d.trip_title === t)]);
    return { here, byTrip, count: available.length };
  }, [uploadedDocs, stop, lodging, tripId]);
  const existing = (uploadedDocs || []).find((d) => String(d.id) === existingId) || null;

  const reset = () => {
    setTitle('');
    setUrl('');
    setAddress(lodging?.address || stop?.loc || '');
    setLat('');
    setLng('');
    setFile(null);
    setExistingId('');
    setUploadedDocs(null);
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
      } else if (kind === 'document' && existing) {
        if (existing.asset_id) payload.asset_id = existing.asset_id;
        else payload.url = existing.url;
        if (!payload.title) payload.title = existing.title;
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
    return Boolean(url.trim() || ((kind === 'document' || kind === 'picture') && file) || (kind === 'document' && existing));
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
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={kind === 'document' ? existing?.title || 'Booking confirmation' : ''}
        />
      </label>
      {kind === 'document' && docChoices.count > 0 && (
        <label>
          Already uploaded
          <select value={existingId} onChange={(e) => setExistingId(e.target.value)}>
            <option value="">Choose a document…</option>
            {docChoices.here.length > 0 && (
              <optgroup label="This trip">
                {docChoices.here.map((d) => <option key={d.id} value={d.id}>{d.title || 'Untitled document'}</option>)}
              </optgroup>
            )}
            {docChoices.byTrip.map(([tripTitle, docs]) => (
              <optgroup key={tripTitle} label={tripTitle}>
                {docs.map((d) => <option key={d.id} value={d.id}>{d.title || 'Untitled document'}</option>)}
              </optgroup>
            ))}
          </select>
          {existing && (
            <a className="trip-hint" href={existing.file_url} target="_blank" rel="noreferrer">Open {existing.title || 'document'}</a>
          )}
        </label>
      )}
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
      {(kind === 'picture' || (kind === 'document' && !existing)) && (
        <>
          <label>
            {kind === 'document' && docChoices.count > 0 ? 'Or upload a new file' : 'File'}
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

function AttachmentForm({ stop, lodging, tripId, onClose, onSaved }) {
  const addRef = useRef(null);
  usePopupHotkeys({
    onClose,
    onSave: () => addRef.current?.(),
  });
  const label = lodging ? lodging.name : stop?.text;
  return (
    <div className="trip-modal-backdrop trip-modal-backdrop-stack" {...backdropDismiss(onClose)} role="presentation">
      <div className="trip-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={lodging ? 'Add to lodging' : 'Add to stop'}>
        <h3>{lodging ? 'Add to lodging' : 'Add to stop'}</h3>
        <p className="trip-hint">{label}</p>
        <AttachmentEditor stop={stop} lodging={lodging} tripId={tripId} onSaved={onSaved} addRef={addRef} />
        <div className="trip-modal-actions">
          <button type="button" onClick={onClose} title="Esc">Close</button>
        </div>
      </div>
    </div>
  );
}

function abbrOn(zone, date) {
  return zone ? zoneAbbr(zone, date ? zonedToEpoch(date, '12:00', zone) : Date.now()) : '';
}

/** "7:30 PM · 9:00 PM · 1h 30m"; zone abbreviations on days that span zones; travel shows local arrival and (+1). */
function stopTimeText(stop, day, zones) {
  const info = zones?.stops[stop.id];
  const dayInfo = zones?.days[day.id];
  const crosses = info && info.zone !== info.arriveZone;
  const labelled = info && dayInfo && (dayInfo.zones.length > 1 || info.zone !== dayInfo.start);
  const tag = (zone) => (labelled || crosses ? ` ${abbrOn(zone, day.date)}` : '');
  const start = stop.start_time ? formatStopTime(stop.start_time) + tag(info?.zone) : '';
  let end = '';
  if (stop.kind === 'travel' && info?.arrive) {
    end = formatStopTime(info.arrive.time) + tag(info.arriveZone) + dayOffsetLabel(info.arrive.offset);
  } else {
    const plain = endFromStartAndDuration(stop.start_time, stop.duration_minutes);
    end = plain ? formatStopTime(plain) + tag(info?.zone) : '';
  }
  return [start && end && crosses ? `${start} → ${end}` : start, crosses ? '' : end, formatDuration(stop.duration_minutes)]
    .filter(Boolean).join(' · ');
}

function DayZones({ day, info, tripZone }) {
  if (!info || (info.zones.length === 1 && info.zones[0] === tripZone)) return null;
  const names = info.zones.map((z) => abbrOn(z, day.date));
  return (
    <span className="trip-day-zone" title={info.zones.map((z) => zoneLabel(z, day.date)).join(' → ')}>
      {names.join(' → ')}
    </span>
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

function LodgingForm({ trip, days, initial, defaultDayIds, onClose, onSaved, onSubmit, onAddAttachment, onRemoveAttachment, onRenameAttachment }) {
  const [name, setName] = useState(initial?.name || '');
  const [address, setAddress] = useState(initial?.address || '');
  const [phone, setPhone] = useState(initial?.phone || '');
  const [url, setUrl] = useState(initial?.url || '');
  const [confirmation, setConfirmation] = useState(initial?.confirmation || '');
  const [status, setStatus] = useState(initial?.status || (initial?.confirmation ? 'confirmed' : 'tobook'));
  const [priceText, setPriceText] = useState(formatPrice(initial?.price, initial?.currency));
  const [person, setPerson] = useState(initial?.person || '');
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
  const parsedPrice = parsePrice(priceText);
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
    if (!parsedPrice) {
      setError('Enter a price like 850, $850 or THB 12,000.');
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
      status,
      price: parsedPrice.price,
      currency: parsedPrice.currency,
      person: person.trim(),
      notes: notes.trim(),
      check_in_time: checkIn || null,
      check_out_time: checkOut || null,
      day_ids: dayIds,
    };
    try {
      if (onSubmit) {
        await onSubmit(payload);
      } else if (initial?.id) {
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
    <div className="trip-modal-backdrop" {...backdropDismiss(onClose)} role="presentation">
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
            Status
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {Object.entries(STATUS_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            Confirmation #
            <input value={confirmation} onChange={(e) => setConfirmation(e.target.value)} placeholder="Reservation / PNR" />
          </label>
          <label>
            Phone
            <input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
        </div>
        <div className="trip-form-row-2">
          <label>
            Total price (optional)
            <input
              value={priceText}
              onChange={(e) => setPriceText(e.target.value)}
              placeholder="850 or THB 12,000"
              inputMode="decimal"
            />
            {priceText.trim() && (
              <span className={parsedPrice ? 'trip-hint' : 'trip-error'}>
                {parsedPrice ? formatPrice(parsedPrice.price, parsedPrice.currency) : 'Try 850, $850 or THB 12,000'}
              </span>
            )}
          </label>
          <label>
            Booked by / Person (optional)
            <input value={person} onChange={(e) => setPerson(e.target.value)} placeholder="Who" />
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
              onRename={onRenameAttachment}
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
            <button type="button" className="trip-danger" onClick={remove} disabled={busy}>Delete</button>
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

function TripTodoEditor({ trip, hideDone, onChanged }) {
  const [text, setText] = useState('');
  const [category, setCategory] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const all = (trip.todos || []).filter((t) => !t.day_id && !t.stop_id);
  const todos = hideDone ? all.filter((t) => !t.done) : all;

  const run = async (fn) => {
    setBusy(true);
    setError('');
    try {
      await fn();
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const add = () => {
    if (!text.trim()) return;
    run(async () => {
      await api.json('/api/trips/todos/', {
        method: 'POST',
        body: JSON.stringify({ trip_id: trip.id, text: text.trim(), category: category.trim() }),
      });
      setText('');
    });
  };

  return (
    <section className="trip-todo-group trip-info-todos">
      <h4>Trip to-dos</h4>
      <TodoCategoryList id="trip-info-todo-categories" options={todoCategoryOptions(trip.todos)} />
      {todos.length > 0 && (
        <ul>
          {todos.map((t) => (
            <li key={t.id} className={t.done ? 'is-done' : undefined}>
              <input
                type="checkbox"
                checked={t.done}
                disabled={busy}
                onChange={() => run(() => api.json(`/api/trips/todos/${t.id}/`, {
                  method: 'PATCH',
                  body: JSON.stringify({ done: !t.done }),
                }))}
                aria-label={`Done: ${t.text}`}
              />
              <div className="trip-todo-text"><Markdown inline>{t.text}</Markdown></div>
              <TodoCategoryTag
                todo={t}
                listId="trip-info-todo-categories"
                disabled={busy}
                onSave={(next) => run(() => api.json(`/api/trips/todos/${t.id}/`, {
                  method: 'PATCH',
                  body: JSON.stringify({ category: next }),
                }))}
              />
              <button
                type="button"
                className="trip-docs-delete"
                disabled={busy}
                onClick={() => run(() => api.json(`/api/trips/todos/${t.id}/`, { method: 'DELETE' }))}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
      {!todos.length && (
        <p className="trip-muted">{all.length ? 'All trip to-dos are done.' : 'No trip-level to-dos yet.'}</p>
      )}
      <div className="trip-todo-add">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              add();
            }
          }}
          placeholder="New trip to-do…"
          aria-label="New trip to-do"
        />
        <input
          className="trip-todo-category-input"
          list="trip-info-todo-categories"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              add();
            }
          }}
          placeholder="Category"
          aria-label="Category for the new trip to-do"
        />
        <button type="button" className="trip-primary" onClick={add} disabled={busy || !text.trim()}>Add</button>
      </div>
      {error && <p className="trip-error">{error}</p>}
    </section>
  );
}

function TripInfoForm({ trip, hideDone, onTodosChanged, onClose, onSave }) {
  const [title, setTitle] = useState(trip.title || '');
  const [description, setDescription] = useState(trip.description || '');
  const [notes, setNotes] = useState(trip.notes || '');
  const [timezone, setTimezone] = useState(trip.timezone || localZone());
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
    if (!title.trim()) {
      setError('Enter a trip name.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await onSave({ title: title.trim(), description, notes, timezone });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" {...backdropDismiss(onClose)} role="presentation">
      <form ref={formRef} className="trip-modal trip-modal-scroll" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>Trip details</h3>
        <div className="trip-modal-body">
          <label>
            Name
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Thailand Family Trip" />
          </label>
          <TimeZoneField
            label="Trip starts in time zone"
            value={timezone}
            inherited={localZone()}
            allowBlank={false}
            onChange={(z) => setTimezone(z || localZone())}
          />
          <p className="trip-hint">
            Times are local. Travel switches the zone to its arrival zone for everything after it, and a day can set its own zone.
          </p>
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
          <TripTodoEditor trip={trip} hideDone={hideDone} onChanged={onTodosChanged} />
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

/** The trip's documents, one entry per file, each with every stop or lodging it is attached to (in trip order). */
function tripDocuments(trip) {
  const byFile = new Map();
  const add = (item, where) => {
    if (item.kind !== 'document') return;
    const key = item.asset ? `a${item.asset}` : item.url ? `u${item.url}` : `i${item.id}`;
    if (!byFile.has(key)) byFile.set(key, { key, item, places: [] });
    byFile.get(key).places.push({ item, where });
  };
  const days = [...(trip.days || [])].sort((a, b) => String(a.date).localeCompare(String(b.date)));
  for (const day of days) {
    const stops = [...(day.stops || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id));
    for (const stop of stops) {
      for (const item of stop.attachments || []) add(item, `${formatDay(day)} · ${stop.text}`);
    }
  }
  for (const lodging of trip.lodgings || []) {
    for (const item of lodging.attachments || []) add(item, `Lodging · ${lodging.name}`);
  }
  for (const idea of trip.ideas || []) {
    for (const item of idea.attachments || []) add(item, `Idea · ${idea.text}`);
  }
  const label = (d) => (d.item.title || '').toLowerCase();
  return [...byFile.values()].sort((a, b) => label(a).localeCompare(label(b)));
}

function TripDocuments({ trip, inline = false, onClose, onRename, onRemove, onRemoveAll, onChanged }) {
  const [renamingKey, setRenamingKey] = useState(null);
  const [query, setQuery] = useState('');
  const [target, setTarget] = useState('');
  const [docTitle, setDocTitle] = useState('');
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState('');
  usePopupHotkeys({ onClose: inline ? null : onClose, busy: uploading });

  const docs = tripDocuments(trip);
  const q = query.trim().toLowerCase();
  const visibleDocs = q
    ? docs.filter((d) => (
      (d.item.title || '').toLowerCase().includes(q)
      || d.places.some((p) => p.where.toLowerCase().includes(q))
    ))
    : docs;

  const days = [...(trip.days || [])].sort((a, b) => String(a.date).localeCompare(String(b.date)));
  const lodgings = trip.lodgings || [];
  const ideas = trip.ideas || [];
  const hasTargets = lodgings.length > 0 || days.some((d) => (d.stops || []).length > 0) || ideas.length > 0;

  const uploadDoc = async (e) => {
    e.preventDefault();
    if (!file || !target) return;
    setUploading(true);
    setUploadErr('');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('add_to_gallery', 'false');
      const uploaded = await api.json('/api/gallery/upload/', { method: 'POST', body: form });
      const [kind, idStr] = target.split(':');
      const payload = {
        kind: 'document',
        title: docTitle.trim() || uploaded.filename || file.name,
        asset_id: uploaded.user_media_id,
        url: uploaded.url,
        ...(kind === 'lodging' ? { lodging_id: Number(idStr) } : { stop_id: Number(idStr) }),
      };
      await api.json('/api/trips/attachments/', { method: 'POST', body: JSON.stringify(payload) });
      setFile(null);
      setDocTitle('');
      await onChanged?.();
    } catch (err) {
      setUploadErr(err.message);
    } finally {
      setUploading(false);
    }
  };

  const body = (
    <>
      {hasTargets && onChanged && (
        <form className="trip-docs-upload" onSubmit={uploadDoc}>
          <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Attach document to">
            <option value="">Attach a voucher / PDF to…</option>
            {lodgings.length > 0 && (
              <optgroup label="Lodgings">
                {lodgings.map((l) => <option key={`lodging:${l.id}`} value={`lodging:${l.id}`}>🛏 {l.name}</option>)}
              </optgroup>
            )}
            {days.map((d) => (d.stops?.length ? (
              <optgroup key={d.id} label={formatDay(d)}>
                {d.stops.map((s) => <option key={`stop:${s.id}`} value={`stop:${s.id}`}>{s.text}</option>)}
              </optgroup>
            ) : null))}
            {ideas.length > 0 && (
              <optgroup label="Ideas pool">
                {ideas.map((s) => <option key={`stop:${s.id}`} value={`stop:${s.id}`}>💡 {s.text}</option>)}
              </optgroup>
            )}
          </select>
          <input
            type="file"
            accept=".pdf,application/pdf,image/*,.doc,.docx,.txt,.html"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            aria-label="Choose document file"
          />
          <input
            value={docTitle}
            onChange={(e) => setDocTitle(e.target.value)}
            placeholder="Label (optional)"
          />
          <button type="submit" className="trip-primary" disabled={uploading || !file || !target}>
            {uploading ? 'Uploading…' : 'Upload'}
          </button>
          {uploadErr && <p className="trip-error" style={{ width: '100%', margin: 0 }}>{uploadErr}</p>}
        </form>
      )}
      {docs.length > 1 && (
        <div className="trip-docs-toolbar">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter documents by name, lodging, or stop…"
          />
        </div>
      )}
      {visibleDocs.length === 0 ? (
        <p className="trip-muted">
          {docs.length === 0
            ? 'No documents yet. Upload a ticket, boarding pass, or booking PDF above (or from any stop or lodging).'
            : 'No documents match your filter.'}
        </p>
      ) : (
        <ul className="trip-docs-list">
          {visibleDocs.map(({ key, item, places }) => {
          const href = attachmentHref(item);
          const label = item.title || 'Untitled document';
          const renaming = renamingKey === key;
          return (
            <li key={key}>
              <div className="trip-docs-head">
                <AttachmentGlyph kind="document" />
                <div className="trip-docs-text">
                  {renaming ? (
                    <InlineRename
                      value={item.title || ''}
                      onCancel={() => setRenamingKey(null)}
                      onSave={async (title) => {
                        await onRename(places.map((p) => p.item), title);
                        setRenamingKey(null);
                      }}
                    />
                  ) : href ? (
                    <a href={href} target="_blank" rel="noreferrer">{label}</a>
                  ) : (
                    <span>{label}</span>
                  )}
                </div>
                {!renaming && (
                  <>
                    <button
                      type="button"
                      onClick={() => setRenamingKey(key)}
                      title={places.length > 1 ? `Rename in all ${places.length} places` : 'Rename'}
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      className="trip-docs-delete"
                      onClick={() => onRemoveAll(places.map((p) => p.item), label)}
                      title={places.length > 1 ? `Remove from all ${places.length} places` : 'Delete'}
                    >
                      Delete
                    </button>
                  </>
                )}
              </div>
              <ul className="trip-docs-places">
                {places.map(({ item: placeItem, where }) => (
                  <li key={placeItem.id}>
                    <span className="trip-muted">
                      {where}
                      {placeItem.title && placeItem.title !== item.title ? ` · named “${placeItem.title}”` : ''}
                    </span>
                    {places.length > 1 && (
                      <button
                        type="button"
                        className="trip-attach-remove"
                        onClick={() => onRemove(placeItem)}
                        aria-label={`Remove from ${where}`}
                        title="Remove from here"
                      >
                        ×
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
      )}
    </>
  );
  if (inline) return <div className="trip-inline-panel trip-docs">{body}</div>;
  return (
    <div className="trip-modal-backdrop" {...backdropDismiss(onClose)} role="presentation">
      <div className="trip-modal trip-modal-scroll trip-docs" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Documents">
        <h3>Documents · {trip.title}</h3>
        <div className="trip-modal-body">{body}</div>
        <div className="trip-modal-actions">
          <button type="button" className="trip-primary" onClick={onClose} title="Esc">Close</button>
        </div>
      </div>
    </div>
  );
}

function useStoredFlag(key) {
  const [flag, setFlag] = useState(() => localStorage.getItem(key) === '1');
  const update = useCallback((value) => {
    setFlag(value);
    localStorage.setItem(key, value ? '1' : '0');
  }, [key]);
  return [flag, update];
}

function todoScope(todo) {
  if (todo.stop_id) return `stop:${todo.stop_id}`;
  if (todo.day_id) return `day:${todo.day_id}`;
  return 'trip';
}

const TODO_CATEGORIES = ['Bookings', 'Documents', 'Packing', 'Money', 'Health', 'Shopping'];

/** Categories already used on the trip first (A–Z), then the stock ones not yet used. */
function todoCategoryOptions(todos) {
  const used = [...new Map((todos || []).filter((t) => t.category).map((t) => [t.category.toLowerCase(), t.category])).values()]
    .sort((a, b) => a.localeCompare(b));
  const seen = new Set(used.map((c) => c.toLowerCase()));
  return [...used, ...TODO_CATEGORIES.filter((c) => !seen.has(c.toLowerCase()))];
}

function TodoCategoryList({ id, options }) {
  return <datalist id={id}>{options.map((c) => <option key={c} value={c} />)}</datalist>;
}

function TodoCategoryTag({ todo, listId, disabled, onSave }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(todo.category || '');
  const finish = (save) => {
    setEditing(false);
    const next = value.trim();
    if (save && next !== (todo.category || '')) onSave(next);
    else setValue(todo.category || '');
  };
  if (editing) {
    return (
      <input
        className="trip-todo-category-input"
        list={listId}
        autoFocus
        value={value}
        placeholder="Category"
        aria-label={`Category for ${todo.text}`}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => finish(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); finish(true); }
          if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); finish(false); }
        }}
      />
    );
  }
  return (
    <button
      type="button"
      className={`trip-todo-category${todo.category ? '' : ' is-empty'}`}
      disabled={disabled}
      onClick={() => { setValue(todo.category || ''); setEditing(true); }}
      title={todo.category ? 'Change category' : 'Add a category'}
    >
      {todo.category || '+ Category'}
    </button>
  );
}

function TodoChecklist({ todos, hideDone, onToggle }) {
  const shown = hideDone ? todos.filter((t) => !t.done) : todos;
  if (!shown.length) return null;
  return (
    <ul className="trip-todo-inline" onClick={(e) => e.stopPropagation()}>
      {shown.map((t) => (
        <li key={t.id} className={t.done ? 'is-done' : undefined}>
          <label>
            <input type="checkbox" checked={t.done} onChange={() => onToggle(t)} />
            <Markdown inline>{t.text}</Markdown>
            {t.category && <span className="trip-todo-category is-static">{t.category}</span>}
          </label>
        </li>
      ))}
    </ul>
  );
}

function TripTodos({ trip, days, initialScope = 'trip', inline = false, hideDone, setHideDone, onClose, onChanged }) {
  const [scope, setScope] = useState(initialScope);
  const [text, setText] = useState('');
  const [category, setCategory] = useState('');
  const [groupBy, setGroupBy] = useState(() => localStorage.getItem('trips.todos.groupBy') || 'day');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [editingId, setEditingId] = useState(null);
  const inputRef = useRef(null);
  usePopupHotkeys({ onClose: inline ? null : onClose, busy });

  const todos = trip.todos || [];
  const ideas = trip.ideas || [];
  const categoryOptions = todoCategoryOptions(todos);
  const openCount = todos.filter((t) => !t.done).length;
  const stopsById = new Map([
    ...days.flatMap((d) => d.stops.map((s) => [s.id, s])),
    ...ideas.map((s) => [s.id, s]),
  ]);
  const daysById = new Map(days.map((d) => [d.id, d]));
  const dayGroups = [
    { key: 'trip', title: 'Whole trip', items: todos.filter((t) => !t.day_id && !t.stop_id) },
    ...(ideas.length ? [{
      key: 'ideas',
      title: 'Ideas pool',
      items: todos.filter((t) => !t.day_id && t.stop_id),
    }] : []),
    ...days.map((day) => {
      const order = new Map(day.stops.map((s, i) => [s.id, i]));
      const items = todos
        .filter((t) => t.day_id === day.id)
        .sort((a, b) => (a.stop_id ? 1 + (order.get(a.stop_id) ?? 0) : 0) - (b.stop_id ? 1 + (order.get(b.stop_id) ?? 0) : 0));
      return { key: `day:${day.id}`, title: formatDay(day), items };
    }),
  ];
  const planOrder = dayGroups.flatMap((g) => g.items);
  const categoryGroups = [...new Map(planOrder.map((t) => [(t.category || '').toLowerCase(), t.category || ''])).entries()]
    .sort(([a], [b]) => (a === '') - (b === '') || a.localeCompare(b))
    .map(([key, name]) => ({
      key: `cat:${key}`,
      title: name || 'No category',
      items: planOrder.filter((t) => (t.category || '').toLowerCase() === key),
    }));
  const groups = (groupBy === 'category' ? categoryGroups : dayGroups)
    .map((g) => ({ ...g, items: hideDone ? g.items.filter((t) => !t.done) : g.items }))
    .filter((g) => g.items.length);
  const changeGroupBy = (value) => {
    localStorage.setItem('trips.todos.groupBy', value);
    setGroupBy(value);
  };

  const run = async (fn) => {
    setBusy(true);
    setError('');
    try {
      await fn();
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const add = (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    const [kind, id] = scope.split(':');
    run(async () => {
      await api.json('/api/trips/todos/', {
        method: 'POST',
        body: JSON.stringify({
          trip_id: trip.id,
          text: text.trim(),
          category: category.trim(),
          ...(kind === 'day' ? { day_id: Number(id) } : {}),
          ...(kind === 'stop' ? { stop_id: Number(id) } : {}),
        }),
      });
      setText('');
      inputRef.current?.focus();
    });
  };

  const patch = (todo, body) => api.json(`/api/trips/todos/${todo.id}/`, { method: 'PATCH', body: JSON.stringify(body) });

  const inner = (
    <>
      <div className="trip-todos-head">
        {!inline && <h3>To-dos · {trip.title}</h3>}
        <span className="trip-muted">{openCount} open · {todos.length - openCount} done</span>
        <label className="trip-check">
          Group by
          <select value={groupBy} onChange={(e) => changeGroupBy(e.target.value)}>
            <option value="day">Day</option>
            <option value="category">Category</option>
          </select>
        </label>
        <label className="trip-check">
          <input type="checkbox" checked={hideDone} onChange={(e) => setHideDone(e.target.checked)} />
          Hide done
        </label>
      </div>
      <TodoCategoryList id={inline ? 'trip-todo-categories-inline' : 'trip-todo-categories'} options={categoryOptions} />
      <form className="trip-todo-add" onSubmit={add}>
        <select value={scope} onChange={(e) => setScope(e.target.value)} aria-label="Attach to">
          <option value="trip">Whole trip</option>
          {days.map((day) => (
            <optgroup key={day.id} label={formatDay(day)}>
              <option value={`day:${day.id}`}>{formatDay(day)} (the day)</option>
              {day.stops.map((s) => (
                <option key={s.id} value={`stop:${s.id}`}>{KIND_LABEL[s.kind] || 'Stop'}: {s.text}</option>
              ))}
            </optgroup>
          ))}
          {!!ideas.length && (
            <optgroup label="Ideas pool">
              {ideas.map((s) => (
                <option key={s.id} value={`stop:${s.id}`}>{KIND_LABEL[s.kind] || 'Idea'}: {s.text}</option>
              ))}
            </optgroup>
          )}
        </select>
        <input ref={inputRef} autoFocus={!inline} value={text} onChange={(e) => setText(e.target.value)} placeholder="New to-do…" />
        <input
          className="trip-todo-category-input"
          list={inline ? 'trip-todo-categories-inline' : 'trip-todo-categories'}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="Category"
            aria-label="Category for the new to-do"
          />
          <button type="submit" className="trip-primary" disabled={busy || !text.trim()}>Add</button>
        </form>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-body">
          {!groups.length && (
            <p className="trip-muted">{todos.length ? 'Everything is done.' : 'No to-dos yet.'}</p>
          )}
          {groups.map((g) => (
            <section key={g.key} className="trip-todo-group">
              <h4>{g.title}</h4>
              <ul>
                {g.items.map((t) => {
                  const stop = t.stop_id ? stopsById.get(t.stop_id) : null;
                  const day = groupBy === 'category' && t.day_id ? daysById.get(t.day_id) : null;
                  const context = [day && formatDay(day), stop && `${KIND_LABEL[stop.kind] || 'Stop'}: ${stop.text}`]
                    .filter(Boolean).join(' · ');
                  return (
                    <li key={t.id} className={t.done ? 'is-done' : undefined}>
                      <input
                        type="checkbox"
                        checked={t.done}
                        disabled={busy}
                        onChange={() => run(() => patch(t, { done: !t.done }))}
                        aria-label={`Done: ${t.text}`}
                      />
                      <div className="trip-todo-text">
                        {editingId === t.id ? (
                          <InlineRename
                            value={t.text}
                            onCancel={() => setEditingId(null)}
                            onSave={async (next) => {
                              await patch(t, { text: next });
                              await onChanged();
                              setEditingId(null);
                            }}
                          />
                        ) : (
                          <Markdown inline>{t.text}</Markdown>
                        )}
                        {context && <span className="trip-muted">{context}</span>}
                      </div>
                      <TodoCategoryTag
                        todo={t}
                        listId="trip-todo-categories"
                        disabled={busy}
                        onSave={(next) => run(() => patch(t, { category: next }))}
                      />
                      {editingId !== t.id && (
                        <>
                          <button type="button" onClick={() => setEditingId(t.id)} title="Edit">Edit</button>
                          <button
                            type="button"
                            className="trip-docs-delete"
                            disabled={busy}
                            onClick={() => run(() => api.json(`/api/trips/todos/${t.id}/`, { method: 'DELETE' }))}
                            title="Delete"
                          >
                            Delete
                          </button>
                        </>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
    </>
  );

  if (inline) return <div className="trip-inline-panel trip-todos">{inner}</div>;
  return (
    <div className="trip-modal-backdrop" {...backdropDismiss(onClose)} role="presentation">
      <div className="trip-modal trip-modal-scroll trip-todos" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="To-dos">
        {inner}
        <div className="trip-modal-actions">
          <button type="button" className="trip-primary" onClick={onClose} title="Esc">Close</button>
        </div>
      </div>
    </div>
  );
}

const REPORT_TYPES = [
  { id: 'summary', label: 'Summary', hint: 'One line per day with its title and notes.' },
  { id: 'full', label: 'Full', hint: 'Pick the sections to include.' },
  { id: 'expenses', label: 'Expenses', hint: 'Totals by category and person, then every priced item.' },
];
const REPORT_SECTIONS = [
  { id: 'overview', label: 'Overview (day summary)' },
  { id: 'days', label: 'Day by day' },
  { id: 'todos', label: 'To Dos' },
  { id: 'expenses', label: 'Expenses' },
];
const REPORT_PREFS_KEY = 'trips.reportChoice';

function loadReportChoice() {
  const fallback = { type: 'full', sections: ['overview', 'days', 'todos'] };
  try {
    const saved = JSON.parse(localStorage.getItem(REPORT_PREFS_KEY) || 'null');
    if (!saved || !REPORT_TYPES.some((t) => t.id === saved.type) || !Array.isArray(saved.sections)) return fallback;
    const sections = saved.sections.filter((s) => REPORT_SECTIONS.some((r) => r.id === s));
    return { type: saved.type, sections: sections.length ? sections : fallback.sections };
  } catch {
    return fallback;
  }
}

function ReportChooser({ choice, setChoice, onGenerate, onClose }) {
  const toggleSection = (id) => setChoice((c) => ({
    ...c,
    sections: c.sections.includes(id) ? c.sections.filter((s) => s !== id) : [...c.sections, id],
  }));
  const canGenerate = choice.type !== 'full' || choice.sections.length > 0;
  return (
    <form
      className="trip-modal"
      onClick={(e) => e.stopPropagation()}
      onSubmit={(e) => { e.preventDefault(); if (canGenerate) onGenerate(); }}
    >
      <h3>Report</h3>
      <div className="trip-report-types" role="radiogroup" aria-label="Report type">
        {REPORT_TYPES.map((t) => (
          <label key={t.id} className={`trip-report-type${choice.type === t.id ? ' is-active' : ''}`}>
            <input
              type="radio"
              name="report-type"
              value={t.id}
              checked={choice.type === t.id}
              onChange={() => setChoice((c) => ({ ...c, type: t.id }))}
            />
            <span>
              <strong>{t.label}</strong>
              <span className="trip-hint">{t.hint}</span>
            </span>
          </label>
        ))}
      </div>
      {choice.type === 'full' && (
        <fieldset className="trip-report-sections">
          <legend>Sections</legend>
          {REPORT_SECTIONS.map((s) => (
            <label key={s.id} className="trip-check">
              <input type="checkbox" checked={choice.sections.includes(s.id)} onChange={() => toggleSection(s.id)} />
              {s.label}
            </label>
          ))}
          {!canGenerate && <p className="trip-error">Pick at least one section.</p>}
        </fieldset>
      )}
      <div className="trip-modal-actions">
        <button type="button" onClick={onClose} title="Esc">Cancel</button>
        <button type="submit" className="trip-primary" disabled={!canGenerate}>Generate</button>
      </div>
    </form>
  );
}

function TripReport({ trip, hideDone, onClose }) {
  const [choice, setChoice] = useState(loadReportChoice);
  const [generated, setGenerated] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');
  const [raw, setRaw] = useState(false);
  const [copied, setCopied] = useState('');
  const formattedRef = useRef(null);
  usePopupHotkeys({ onClose, busy: false });

  const generate = () => {
    localStorage.setItem(REPORT_PREFS_KEY, JSON.stringify(choice));
    setReport(null);
    setError('');
    setRaw(false);
    setGenerated({ ...choice });
  };

  useEffect(() => {
    if (!generated) return undefined;
    let cancelled = false;
    const params = new URLSearchParams({ type: generated.type });
    if (generated.type === 'full') {
      params.set('sections', REPORT_SECTIONS.map((s) => s.id).filter((id) => generated.sections.includes(id)).join(','));
    }
    if (hideDone) params.set('hide_done', '1');
    (async () => {
      try {
        const data = await api.json(`/api/trips/trips/${trip.id}/report/?${params}`);
        if (!cancelled) setReport(data);
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [trip.id, hideDone, generated]);

  if (!generated) {
    return (
      <div className="trip-modal-backdrop" {...backdropDismiss(onClose)} role="presentation">
        <ReportChooser choice={choice} setChoice={setChoice} onGenerate={generate} onClose={onClose} />
      </div>
    );
  }
  const typeLabel = REPORT_TYPES.find((t) => t.id === generated.type)?.label;

  const flashCopied = (which) => {
    setCopied(which);
    setTimeout(() => setCopied(''), 1500);
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(report.markdown);
      flashCopied('markdown');
    } catch (err) {
      setError(err.message);
    }
  };

  // Email clients drop form inputs, so to-do checkboxes become glyphs.
  const copyForEmail = async () => {
    const node = formattedRef.current?.cloneNode(true);
    if (!node) return;
    node.querySelectorAll('input[type="checkbox"]').forEach((box) => box.replaceWith(box.checked ? '☑ ' : '☐ '));
    try {
      await navigator.clipboard.write([new ClipboardItem({
        'text/html': new Blob([node.innerHTML], { type: 'text/html' }),
        'text/plain': new Blob([report.markdown], { type: 'text/plain' }),
      })]);
      flashCopied('email');
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
    <div className="trip-modal-backdrop" {...backdropDismiss(onClose)} role="presentation">
      <div className="trip-modal trip-modal-bulk" onClick={(e) => e.stopPropagation()}>
        <h3>{typeLabel} report · {trip.title}</h3>
        <div className="trip-report">
          {!report && !error && <p className="trip-muted">Building report…</p>}
          {report && raw && <pre className="trip-report-raw">{report.markdown}</pre>}
          {report && (
            <div ref={formattedRef} hidden={raw}>
              <Markdown>{report.markdown}</Markdown>
            </div>
          )}
        </div>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={() => setGenerated(null)}>Back</button>
          <button type="button" onClick={() => setRaw((v) => !v)} disabled={!report}>
            {raw ? 'Show formatted' : 'Show markdown'}
          </button>
          <button type="button" onClick={copyForEmail} disabled={!report} title="Formatted copy for Gmail and other email">
            {copied === 'email' ? 'Copied' : 'Copy for email'}
          </button>
          <button type="button" onClick={copy} disabled={!report}>{copied === 'markdown' ? 'Copied' : 'Copy markdown'}</button>
          <button type="button" onClick={download} disabled={!report}>Download .md</button>
          <button type="button" className="trip-primary" onClick={onClose} title="Esc">Close</button>
        </div>
      </div>
    </div>
  );
}

function LegForm({ trip, days, legs = [], initial, onClose, onSaved }) {
  const [name, setName] = useState(initial?.name || '');
  const [location, setLocation] = useState(initial?.location || '');
  const [timezone, setTimezone] = useState(initial?.timezone || '');
  const [notes, setNotes] = useState(initial?.notes || '');
  const initialRange = useMemo(() => {
    const ids = new Set((initial?.assigned_day_ids || []).map(Number));
    const indices = days.map((d, i) => (ids.has(d.id) ? i : -1)).filter((i) => i >= 0);
    if (!indices.length) return { start: '', end: '' };
    return { start: String(days[indices[0]].id), end: String(days[indices[indices.length - 1]].id) };
  }, [days, initial]);
  const [startId, setStartId] = useState(initialRange.start);
  const [endId, setEndId] = useState(initialRange.end);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const formRef = useRef(null);
  usePopupHotkeys({ onClose, busy, onSave: () => formRef.current?.requestSubmit() });

  const legById = useMemo(() => new Map(legs.map((l) => [l.id, l])), [legs]);
  const startIdx = startId ? days.findIndex((d) => String(d.id) === startId) : -1;
  const endIdx = endId ? days.findIndex((d) => String(d.id) === endId) : -1;
  const loIdx = startIdx >= 0 ? Math.min(startIdx, endIdx >= 0 ? endIdx : startIdx) : -1;
  const hiIdx = startIdx >= 0 ? Math.max(startIdx, endIdx >= 0 ? endIdx : startIdx) : -1;
  const selectedDays = loIdx >= 0 ? days.slice(loIdx, hiIdx + 1) : [];
  const selectedIdSet = useMemo(() => new Set(selectedDays.map((d) => d.id)), [selectedDays]);

  const { splitLeg, trimmedNames } = useMemo(() => {
    if (loIdx < 0) return { splitLeg: null, trimmedNames: [] };
    const selfId = initial?.id || null;
    const otherPositions = new Map();
    const touched = new Map();
    days.forEach((d, i) => {
      if (!d.leg || d.leg === selfId) return;
      if (i >= loIdx && i <= hiIdx) {
        touched.set(d.leg, (touched.get(d.leg) || 0) + 1);
      } else {
        const cur = otherPositions.get(d.leg) || { before: false, after: false };
        if (i < loIdx) cur.before = true;
        if (i > hiIdx) cur.after = true;
        otherPositions.set(d.leg, cur);
      }
    });
    let split = null;
    for (const [lid, pos] of otherPositions.entries()) {
      if (pos.before && pos.after) {
        split = legById.get(lid) || { id: lid, name: 'another leg' };
        break;
      }
    }
    const trimmed = [...touched.entries()]
      .filter(([lid]) => lid !== split?.id)
      .map(([lid, count]) => ({ name: legById.get(lid)?.name || 'another leg', count }));
    return { splitLeg: split, trimmedNames: trimmed };
  }, [days, loIdx, hiIdx, initial, legById]);

  const handleStartChange = (val) => {
    setStartId(val);
    if (!val) {
      setEndId('');
      return;
    }
    const nextStart = days.findIndex((d) => String(d.id) === val);
    const curEnd = endId ? days.findIndex((d) => String(d.id) === endId) : -1;
    if (curEnd < nextStart) setEndId(val);
  };

  const handleEndChange = (val) => {
    if (!val) {
      setStartId('');
      setEndId('');
      return;
    }
    setEndId(val);
    if (!startId) setStartId(val);
  };

  const handleDayPillClick = (idx) => {
    const clickedId = String(days[idx].id);
    if (loIdx < 0 || loIdx !== hiIdx) {
      setStartId(clickedId);
      setEndId(clickedId);
    } else if (idx === loIdx) {
      setStartId('');
      setEndId('');
    } else {
      const a = Math.min(loIdx, idx);
      const b = Math.max(loIdx, idx);
      setStartId(String(days[a].id));
      setEndId(String(days[b].id));
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Enter a leg name (e.g., Bangkok or Chiang Mai).');
      return;
    }
    if (splitLeg) {
      setError(`This range would split leg “${splitLeg.name}” into non-contiguous days.`);
      return;
    }
    setBusy(true);
    setError('');
    const payload = {
      trip_id: trip.id,
      name: name.trim(),
      location: location.trim(),
      timezone,
      notes: notes.trim(),
      day_ids: selectedDays.map((d) => d.id),
    };
    try {
      if (initial?.id) {
        await api.json(`/api/trips/legs/${initial.id}/`, { method: 'PATCH', body: JSON.stringify(payload) });
      } else {
        await api.json('/api/trips/legs/', { method: 'POST', body: JSON.stringify(payload) });
      }
      await onSaved();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!initial?.id || !window.confirm(`Delete leg “${initial.name}”? Its days will stay on the trip as ungrouped.`)) return;
    setBusy(true);
    setError('');
    try {
      await api.json(`/api/trips/legs/${initial.id}/`, { method: 'DELETE' });
      await onSaved();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const dayOptionLabel = (d, i) => {
    const owner = d.leg && d.leg !== initial?.id ? legById.get(d.leg)?.name : '';
    return `Day ${i + 1} · ${formatDay(d)}${owner ? ` (${owner})` : ''}`;
  };

  return (
    <div className="trip-modal-backdrop" {...backdropDismiss(onClose)} role="presentation">
      <form ref={formRef} className="trip-modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>{initial?.id ? 'Edit leg' : 'New leg'}</h3>
        <div className="trip-form-row-2">
          <label>
            Leg name
            <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g., Bangkok, Chiang Mai, Transit" required />
          </label>
          <label>
            Location (optional)
            <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g., Bangkok, Thailand" />
          </label>
        </div>
        <TimeZoneField
          label="Default time zone (optional)"
          value={timezone}
          inherited={trip.timezone || localZone()}
          inheritedNote="trip default"
          date={selectedDays[0]?.date || days[0]?.date}
          onChange={setTimezone}
        />
        <label>
          Notes (optional)
          <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Region vibe, logistics, anchor transfers…" />
        </label>
        {days.length > 0 && (
          <fieldset className="trip-day-checks">
            <legend>
              Contiguous day range ({selectedDays.length} {selectedDays.length === 1 ? 'day' : 'days'})
            </legend>
            <div className="trip-leg-range-grid">
              <label>
                From day
                <select value={startId} onChange={(e) => handleStartChange(e.target.value)} aria-label="Leg start day">
                  <option value="">No days assigned yet</option>
                  {days.map((d, i) => <option key={d.id} value={d.id}>{dayOptionLabel(d, i)}</option>)}
                </select>
              </label>
              <label>
                To day
                <select
                  value={endId}
                  onChange={(e) => handleEndChange(e.target.value)}
                  disabled={!startId}
                  aria-label="Leg end day"
                >
                  {!startId && <option value="">—</option>}
                  {days.map((d, i) => (
                    i >= Math.max(0, startIdx) ? (
                      <option key={d.id} value={d.id}>{dayOptionLabel(d, i)}</option>
                    ) : null
                  ))}
                </select>
              </label>
              {selectedDays.length > 0 && (
                <button type="button" className="trip-leg-clear-btn" onClick={() => { setStartId(''); setEndId(''); }}>
                  Clear
                </button>
              )}
            </div>
            <div className="trip-leg-day-strip" role="group" aria-label="Click days to pick a contiguous range">
              {days.map((d, i) => {
                const inRange = selectedIdSet.has(d.id);
                const otherOwner = d.leg && d.leg !== initial?.id ? legById.get(d.leg)?.name : '';
                return (
                  <button
                    key={d.id}
                    type="button"
                    className={`trip-leg-day-pill${inRange ? ' is-selected' : ''}${otherOwner ? ' has-other-leg' : ''}`}
                    onClick={() => handleDayPillClick(i)}
                    title={`Day ${i + 1}: ${formatDay(d)}${otherOwner ? ` (currently in ${otherOwner})` : ''}`}
                  >
                    <span>D{i + 1}</span>
                    <small>{formatDay({ date: d.date })}</small>
                  </button>
                );
              })}
            </div>
            {splitLeg && (
              <p className="trip-error trip-leg-range-note">
                This range would split leg “{splitLeg.name}” into non-contiguous days. Adjust “{splitLeg.name}” first or start/end at its edge.
              </p>
            )}
            {!splitLeg && trimmedNames.length > 0 && (
              <p className="trip-muted trip-leg-range-note">
                {trimmedNames.map((t) => `${t.count} ${t.count === 1 ? 'day' : 'days'} will move from “${t.name}”`).join(' · ')}.
              </p>
            )}
          </fieldset>
        )}
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          {initial?.id && (
            <button type="button" className="trip-danger" onClick={remove} disabled={busy}>Delete leg</button>
          )}
          <button type="button" onClick={onClose} title="Esc">Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy || Boolean(splitLeg)} title={saveHotkeyLabel()}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  );
}

function DayForm({ initial, legs = [], inheritedZone, onClose, onSave, onDelete }) {
  const [date, setDate] = useState(initial?.date || '');
  const [title, setTitle] = useState(initial?.title || '');
  const [notes, setNotes] = useState(initial?.notes || '');
  const [timezone, setTimezone] = useState(initial?.timezone || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const formRef = useRef(null);
  const currentLeg = initial?.leg ? legs.find((l) => l.id === initial.leg) : null;
  usePopupHotkeys({
    onClose,
    busy,
    onSave: () => formRef.current?.requestSubmit(),
  });

  const remove = async () => {
    if (!initial?.id || !onDelete || !window.confirm(`Delete ${formatDay(initial)} and its stops?`)) return;
    setBusy(true);
    setError('');
    try {
      await onDelete(initial);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!date) {
      setError('Pick a date.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await onSave({ date, title: title.trim(), notes, timezone });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" {...backdropDismiss(onClose)} role="presentation">
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
        {currentLeg && (
          <p className="trip-muted trip-day-leg-readonly">
            Leg: <strong>{currentLeg.name}</strong> · Change leg day ranges in <strong>Route → Edit leg</strong>.
          </p>
        )}
        <label>
          Notes
          <textarea
            rows={4}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="High-level plan for the day…"
          />
        </label>
        <TimeZoneField
          label="Day starts in time zone"
          value={timezone}
          inherited={inheritedZone}
          inheritedNote="where the previous day ended"
          date={date}
          onChange={setTimezone}
        />
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          {initial?.id && onDelete && (
            <button type="button" className="trip-danger" onClick={remove} disabled={busy}>Delete day</button>
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

function StopForm({ tripId, days, legs = [], zones, initial, defaultDayId, defaultKind = 'activity', todoCount = 0, onClose, onSave, onDelete, onAddAttachment, onRemoveAttachment, onRenameAttachment }) {
  const kind = initial?.kind || defaultKind || 'activity';
  const isTravel = kind === 'travel';
  const isEvent = kind === 'event';
  const noun = KIND_NOUN[kind] || 'stop';
  const startsUnscheduled = Boolean(initial?.isIdea || (initial?.id && !initial.day && !initial.day_id) || (initial && 'day_id' in initial && initial.day_id === null));
  const [dayId, setDayId] = useState(() => (
    startsUnscheduled ? '' : String(initial?.day || initial?.day_id || defaultDayId || days[0]?.id || '')
  ));
  const [legId, setLegId] = useState(() => (initial?.leg || initial?.leg_id ? String(initial.leg || initial.leg_id) : ''));
  const isIdea = !dayId;
  const [text, setText] = useState(initial?.text || '');
  const [description, setDescription] = useState(initial?.description || '');
  const [travelMode, setTravelMode] = useState(initial?.travel_mode || 'drive');
  const [loc, setLoc] = useState(initial?.loc || '');
  const [arriveLoc, setArriveLoc] = useState(initial?.arrive_loc || '');
  const [cat, setCat] = useState(initial?.cat || (isTravel ? 'Travel' : isEvent ? 'Event' : 'Sight'));
  const [priceText, setPriceText] = useState(formatPrice(initial?.price, initial?.currency));
  const [person, setPerson] = useState(initial?.person || '');
  const [confirmation, setConfirmation] = useState(initial?.confirmation || '');
  const [status, setStatus] = useState(initial?.status || (startsUnscheduled ? 'option' : 'no_booking'));
  const [startTime, setStartTime] = useState(initial?.start_time ? String(initial.start_time).slice(0, 5) : '');
  const [duration, setDuration] = useState(initial?.duration_minutes ?? '');
  const [zone, setZone] = useState(initial?.timezone || '');
  const [arriveZone, setArriveZone] = useState(initial?.arrive_timezone || '');
  const selectedDay = days.find((d) => String(d.id) === String(dayId));
  const ownInfo = initial?.id ? zones?.stops[initial.id] : null;
  const inheritedZone = ownInfo && String(initial.day ?? initial.day_id) === String(dayId)
    ? ownInfo.inherited
    : zones?.days[dayId]?.end || zones?.tripZone || localZone();
  const depZone = zone || inheritedZone;
  const arrZone = isTravel ? arriveZone || depZone : depZone;
  const dayDate = selectedDay?.date;
  const [endTime, setEndTime] = useState(() => (
    zonedEnd(dayDate, startTime, duration, depZone, arrZone)?.time || ''
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
  const suggestions = useMemo(() => {
    const stops = days.flatMap((d) => d.stops || []);
    const uniq = (values) => [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b));
    return { cats: uniq(stops.map((s) => s.cat)), people: uniq(stops.map((s) => s.person)) };
  }, [days]);
  const parsedPrice = parsePrice(priceText);
  const endOffset = zonedEnd(dayDate, startTime, duration, depZone, arrZone)?.offset || 0;
  const crossesZones = isTravel && depZone !== arrZone;
  const abbrAt = (z) => (dayDate ? zoneAbbr(z, zonedToEpoch(dayDate, '12:00', z)) : zoneAbbr(z));

  const changeStartTime = (value) => {
    setStartTime(value);
    if (duration !== '' && Number.isFinite(Number(duration))) {
      setEndTime(zonedEnd(dayDate, value, duration, depZone, arrZone)?.time || '');
    } else if (endTime) {
      setDuration(zonedDuration(dayDate, value, endTime, depZone, arrZone));
    }
  };

  const changeDuration = (value) => {
    setDuration(value);
    setEndTime(zonedEnd(dayDate, startTime, value, depZone, arrZone)?.time || '');
  };

  const changeEndTime = (value) => {
    setEndTime(value);
    if (startTime) setDuration(zonedDuration(dayDate, startTime, value, depZone, arrZone));
  };

  // Times on a ticket are local at each end, so a zone change keeps both times and re-derives the duration.
  const changeZones = (nextZone, nextArriveZone, nextDayId = dayId) => {
    setZone(nextZone);
    setArriveZone(nextArriveZone);
    if (!startTime || !endTime || isEvent) return;
    const nextDay = days.find((d) => String(d.id) === String(nextDayId));
    const nextInherited = ownInfo && String(initial.day ?? initial.day_id) === String(nextDayId)
      ? ownInfo.inherited
      : zones?.days[nextDayId]?.end || zones?.tripZone || localZone();
    const dep = nextZone || nextInherited;
    const arr = isTravel ? nextArriveZone || dep : dep;
    setDuration(zonedDuration(nextDay?.date, startTime, endTime, dep, arr));
  };

  const remove = async () => {
    const attached = (initial?.attachments || []).length;
    const extras = [attached && `${attached} attachment${attached === 1 ? '' : 's'}`, todoCount && `${todoCount} to-do${todoCount === 1 ? '' : 's'}`]
      .filter(Boolean).join(' and ');
    if (!window.confirm(`Delete this ${noun}${initial?.text ? ` "${initial.text}"` : ''}?${extras ? ` Its ${extras} will be removed too.` : ''}`)) return;
    setBusy(true);
    setError('');
    try {
      await onDelete(initial);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    const title = text.trim() || (isTravel ? travelTitle(travelMode, loc.trim(), arriveLoc.trim()) : '');
    if (!title) {
      setError(isTravel ? 'Enter a title or departure/arrival locations.' : `Enter ${isEvent ? 'an event' : 'an activity'}.`);
      return;
    }
    if (!parsedPrice) {
      setError('Enter a price like 120, $120 or THB 1,500.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      if (attachPendingRef.current?.() && !(await attachAddRef.current?.())) return;
      await onSave({
        trip_id: tripId,
        day_id: dayId ? Number(dayId) : null,
        leg_id: !dayId && legId ? Number(legId) : null,
        kind,
        travel_mode: isTravel ? travelMode : '',
        text: title,
        description: description.trim(),
        loc: loc.trim(),
        arrive_loc: isTravel ? arriveLoc.trim() : '',
        cat: cat.trim() || (isTravel ? 'Travel' : ''),
        price: parsedPrice.price,
        currency: parsedPrice.currency,
        person: person.trim(),
        confirmation: confirmation.trim(),
        status,
        start_time: dayId ? (startTime || null) : null,
        duration_minutes: isEvent || duration === '' ? null : Number(duration),
        timezone: dayId ? zone : '',
        arrive_timezone: dayId && isTravel ? arriveZone : '',
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" {...backdropDismiss(onClose)} role="presentation">
      <form ref={formRef} className="trip-modal trip-modal-scroll" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>{initial?.id ? 'Edit' : 'Add'} {isIdea ? 'idea' : noun}</h3>
        <div className="trip-modal-body">
          <div className={isIdea && legs.length > 0 ? 'trip-form-row-2' : ''}>
            <label>
              Day
              <select
                value={dayId}
                onChange={(e) => {
                  const next = e.target.value;
                  if (!next && dayId) {
                    const prevDay = days.find((d) => String(d.id) === String(dayId));
                    if (prevDay?.leg && !legId) setLegId(String(prevDay.leg));
                  }
                  setDayId(next);
                  changeZones(zone, arriveZone, next);
                }}
              >
                <option value="">Ideas pool (unscheduled)</option>
                {days.map((d) => (
                  <option key={d.id} value={d.id}>{formatDay(d)}</option>
                ))}
              </select>
            </label>
            {isIdea && legs.length > 0 && (
              <label>
                Leg (optional)
                <select value={legId} onChange={(e) => setLegId(e.target.value)}>
                  <option value="">Trip-wide</option>
                  {legs.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
              </label>
            )}
          </div>
          {!initial?.id && selectedDay && (
            <p className="trip-hint">Goes at the end of {formatDay(selectedDay)}.</p>
          )}
          {isIdea && (
            <p className="trip-hint">Saved in your Ideas pool until you slot it onto a day.</p>
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
            {isTravel ? 'Title' : isEvent ? 'Event' : 'Activity'}
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
          {isIdea ? (
            !isEvent && (
              <label>
                Estimated duration (min, optional)
                <input
                  type="number"
                  min="0"
                  step="5"
                  value={duration}
                  onChange={(e) => setDuration(e.target.value)}
                  placeholder={isTravel ? '240' : '90'}
                />
              </label>
            )
          ) : (
          <>
          {isEvent ? (
            <div className="trip-form-row">
              <label>
                Time ({abbrAt(depZone)})
                <TimeInput value={startTime} onChange={setStartTime} />
              </label>
            </div>
          ) : (
          <div className="trip-form-row">
            <label>
              {isTravel ? 'Departure time' : 'Start time'} ({abbrAt(depZone)})
              <TimeInput value={startTime} onChange={changeStartTime} />
            </label>
            <label>
              {isTravel ? 'Arrival time' : 'End time'} ({abbrAt(arrZone)})
              <TimeInput value={endTime} onChange={changeEndTime} />
              {endOffset !== 0 && (
                <span className="trip-hint">
                  {isTravel ? 'Arrives' : 'Ends'}{' '}
                  {endOffset === 1 ? 'next day' : endOffset === -1 ? 'the previous day' : `${endOffset > 0 ? '+' : ''}${endOffset} days`}
                </span>
              )}
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
              {crossesZones && duration !== '' && <span className="trip-hint">{formatDuration(duration)} actual</span>}
            </label>
          </div>
          )}
          {isTravel ? (
            <div className="trip-form-row-2">
              <TimeZoneField
                label="Departure time zone"
                value={zone}
                inherited={inheritedZone}
                inheritedNote="from the itinerary"
                date={dayDate}
                onChange={(z) => changeZones(z, arriveZone || arrZone)}
              />
              <TimeZoneField
                label="Arrival time zone"
                value={arriveZone}
                inherited={depZone}
                inheritedNote="same as departure"
                date={dayDate}
                onChange={(z) => changeZones(zone, z)}
              />
            </div>
          ) : (
            <TimeZoneField
              label="Time zone"
              value={zone}
              inherited={inheritedZone}
              inheritedNote="from the itinerary"
              date={dayDate}
              onChange={(z) => changeZones(z, arriveZone)}
            />
          )}
          {isTravel && crossesZones && (
            <p className="trip-hint">Items after this travel are in {zoneLabel(arrZone, dayDate)} until another travel or day changes it.</p>
          )}
          </>
          )}
          {isTravel ? (
            <div className="trip-form-row-2">
              <label>
                Category
                <input value={cat} onChange={(e) => setCat(e.target.value)} placeholder="Travel" list="trip-stop-cats" />
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
                <input
                  value={cat}
                  onChange={(e) => setCat(e.target.value)}
                  placeholder={isEvent ? 'Event' : 'Sight'}
                  list="trip-stop-cats"
                />
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
          <div className="trip-form-row">
            <label>
              Confirmation #
              <input value={confirmation} onChange={(e) => setConfirmation(e.target.value)} placeholder="PNR, ticket #, ref" />
            </label>
            <label>
              Price
              <input
                value={priceText}
                onChange={(e) => setPriceText(e.target.value)}
                placeholder="120 or THB 1,500"
                inputMode="decimal"
              />
              {priceText.trim() && (
                <span className={parsedPrice ? 'trip-hint' : 'trip-error'}>
                  {parsedPrice ? formatPrice(parsedPrice.price, parsedPrice.currency) : 'Try 120, $120 or THB 1,500'}
                </span>
              )}
            </label>
            <label>
              Person
              <input value={person} onChange={(e) => setPerson(e.target.value)} placeholder="Who" list="trip-stop-people" />
            </label>
          </div>
          <datalist id="trip-stop-cats">
            {suggestions.cats.map((c) => <option key={c} value={c} />)}
          </datalist>
          <datalist id="trip-stop-people">
            {suggestions.people.map((p) => <option key={p} value={p} />)}
          </datalist>
          <section className="trip-attach-section">
            <h4>URLs, pictures, and locations</h4>
            {initial?.id ? (
              <>
                <AttachmentIcons
                  attachments={initial.attachments}
                  canEdit
                  onRemove={onRemoveAttachment}
                  onRename={onRenameAttachment}
                />
                <AttachmentEditor
                  stop={initial}
                  tripId={tripId || days[0]?.trip}
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
          {initial?.id && onDelete && (
            <button type="button" className="trip-danger" onClick={remove} disabled={busy}>
              Delete {noun}
            </button>
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
    price: '',
    person: '',
  };
}

function stopToBulkRow(stop, date, info) {
  const start = stop.start_time ? String(stop.start_time).slice(0, 5) : '';
  const zone = info?.zone || '';
  const arriveZone = info?.arriveZone || zone;
  return {
    key: `id-${stop.id}`,
    id: stop.id,
    kind: KIND_NOUN[stop.kind] ? stop.kind : 'activity',
    text: stop.text || '',
    start_time: start,
    end_time: zonedEnd(date, start, stop.duration_minutes, zone, arriveZone)?.time || '',
    zone,
    arrive_zone: arriveZone,
    loc: stop.loc || '',
    arrive_loc: stop.arrive_loc || '',
    travel_mode: stop.travel_mode || 'drive',
    price: formatPrice(stop.price, stop.currency),
    person: stop.person || '',
  };
}

function bulkRowHasContent(row) {
  return Boolean(
    row.text.trim()
    || row.loc.trim()
    || row.arrive_loc.trim()
    || row.start_time
    || row.end_time
    || row.price.trim()
    || row.person.trim(),
  );
}

const BULK_COL_COUNT = 8;

function isBulkTimeCol(col) {
  return col === 2 || col === 3;
}

function bulkCellEnabled(row, col) {
  if (!row || col < 0 || col >= BULK_COL_COUNT) return false;
  if (col === 5 && row.kind !== 'travel') return false;
  if (col === 3 && row.kind === 'event') return false;
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
    <div className="trip-modal-backdrop" {...backdropDismiss(onClose)} role="presentation">
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

/** Departure and arrival zones for a bulk row's time math; new rows use the zone the day ends in. */
function bulkRowZones(row, fallback) {
  const zone = row.zone || fallback;
  return [zone, row.kind === 'travel' ? row.arrive_zone || zone : zone];
}

function BulkDayEditor({ day, zones, people = [], onClose, onSaved }) {
  const fallbackZone = zones?.days[day.id]?.end || '';
  const [rows, setRows] = useState(() => {
    const existing = [...(day.stops || [])]
      .sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id))
      .map((stop) => stopToBulkRow(stop, day.date, zones?.stops[stop.id]));
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
    const [from, to] = bulkRowZones(row, fallbackZone);
    const duration = zonedDuration(day.date, row.start_time, row.end_time, from, to);
    patchRow(row.key, {
      start_time: start,
      end_time: duration !== '' ? zonedEnd(day.date, start, duration, from, to)?.time || '' : row.end_time,
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
        const price = parsePrice(row.price);
        if (!price) throw new Error(`“${title}”: enter a price like 120, $120 or THB 1,500.`);
        const duration = row.kind === 'event'
          ? ''
          : zonedDuration(day.date, row.start_time, row.end_time, ...bulkRowZones(row, fallbackZone));
        return {
          ...(row.id ? { id: row.id } : {}),
          kind: row.kind,
          travel_mode: isTravel ? (row.travel_mode || 'drive') : '',
          text: title,
          loc: row.loc.trim(),
          arrive_loc: isTravel ? row.arrive_loc.trim() : '',
          start_time: row.start_time || null,
          duration_minutes: duration === '' ? null : Number(duration),
          price: price.price,
          currency: price.currency,
          person: row.person.trim(),
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
    <div className="trip-modal-backdrop" {...backdropDismiss(onClose)} role="presentation">
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
                <th>Price</th>
                <th>Person</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const isTravel = row.kind === 'travel';
                const rowPrice = parsePrice(row.price);
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
                      <ClickEditCell {...cellProps(0)} display={KIND_LABEL[row.kind]}>
                        <select
                          value={row.kind}
                          onChange={(e) => {
                            const kind = e.target.value;
                            patchRow(row.key, kind === 'event' ? { kind, end_time: '' } : { kind });
                            if (active.row === index && !bulkCellEnabled({ ...row, kind }, active.col)) {
                              setActive((prev) => ({ ...prev, col: 4, sub: 0 }));
                            }
                          }}
                          aria-label="Type"
                        >
                          {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
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
                      {row.kind === 'event' ? (
                        <span className="trip-bulk-na">—</span>
                      ) : (
                        <ClickEditCell
                          {...cellProps(3)}
                          display={
                            row.end_time && isTravel && row.zone && row.arrive_zone && row.zone !== row.arrive_zone
                              ? `${formatStopTime(row.end_time)} ${zoneAbbr(row.arrive_zone, zonedToEpoch(day.date, '12:00', row.arrive_zone))}`
                              : formatStopTime(row.end_time)
                          }
                          placeholder="End"
                        >
                          <TimeInput value={row.end_time} onChange={(v) => patchRow(row.key, { end_time: v })} />
                        </ClickEditCell>
                      )}
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
                    <td className={cellClass(6)}>
                      <ClickEditCell
                        {...cellProps(6)}
                        display={rowPrice ? formatPrice(rowPrice.price, rowPrice.currency) : row.price}
                        placeholder="Price"
                      >
                        <input
                          value={row.price}
                          onChange={(e) => patchRow(row.key, { price: e.target.value })}
                          placeholder="120 or THB 1,500"
                          inputMode="decimal"
                        />
                      </ClickEditCell>
                    </td>
                    <td className={cellClass(7)}>
                      <ClickEditCell {...cellProps(7)} display={row.person} placeholder="Person">
                        <input
                          value={row.person}
                          onChange={(e) => patchRow(row.key, { person: e.target.value })}
                          placeholder="Who"
                          list="trip-bulk-people"
                        />
                      </ClickEditCell>
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
          <datalist id="trip-bulk-people">
            {people.map((p) => <option key={p} value={p} />)}
          </datalist>
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

function TripDetail({ trip, currentUser, lists, galleries, onBack, onReload, onDeleted }) {
  const myRole = trip.my_role || 'owner';
  const isOwner = myRole === 'owner';
  const canEdit = myRole === 'owner' || myRole === 'editor';
  const commentIndex = useMemo(() => buildCommentIndex(trip.comments || []), [trip.comments]);

  const initialHasStops = (trip.days || []).some((d) => (d.stops || []).length > 0);
  const [workspace, setWorkspace] = useState(() => (initialHasStops ? 'schedule' : 'route'));
  const [scheduleView, setScheduleView] = useState(() => localStorage.getItem('trips.scheduleView') || 'itinerary');
  const [prepTab, setPrepTab] = useState('bookings');
  const [logView, setLogView] = useState('track');
  const [cleanup, setCleanup] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const [showShare, setShowShare] = useState(false);
  const [commentsScope, setCommentsScope] = useState(null);
  const menuRef = useRef(null);
  const [query, setQuery] = useState('');
  const [loc, setLoc] = useState('all');
  const [cat, setCat] = useState('all');
  const [status, setStatus] = useState('all');
  const [legFilter, setLegFilter] = useState('all');
  const [editing, setEditing] = useState(null);
  const [adding, setAdding] = useState(null);
  const [addingDay, setAddingDay] = useState(false);
  const [editingDay, setEditingDay] = useState(null);
  const [legForm, setLegForm] = useState(null);
  const [calendarFocusLegId, setCalendarFocusLegId] = useState(null);
  const [currentDayId, setCurrentDayId] = useState(null);
  const [attaching, setAttaching] = useState(null);
  const [lodgingForm, setLodgingForm] = useState(null);
  const [bulkDay, setBulkDay] = useState(null);
  const [bulkTripDays, setBulkTripDays] = useState(false);
  const [editingInfo, setEditingInfo] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [showDocs, setShowDocs] = useState(false);
  const [todosScope, setTodosScope] = useState(null);
  const [showAssistant, setShowAssistant] = useState(false);
  const [aiEdit, setAiEdit] = useState(null);
  const [hideDone, setHideDone] = useStoredFlag('trips.hideDoneTodos');
  const [hideTodos, setHideTodos] = useStoredFlag('trips.hideTodos');
  const [showIdeasRail, setShowIdeasRail] = useStoredFlag('trips.showIdeasRail');
  const [dropDayId, setDropDayId] = useState(null);
  const [error, setError] = useState('');
  const [journalDrafts, setJournalDrafts] = useState({});
  const [collapsedDayIds, setCollapsedDayIds] = useState(() => new Set());

  const chooseScheduleView = (v) => {
    setScheduleView(v);
    try { localStorage.setItem('trips.scheduleView', v); } catch { /* ignore */ }
  };

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onDocClick = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    const onKey = (e) => { if (e.key === 'Escape') setMenuOpen(false); };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  const isPlanView = workspace === 'schedule' && scheduleView === 'itinerary';
  const isCalendarView = workspace === 'schedule' && scheduleView === 'calendar';
  const isTrackView = workspace === 'log' && logView === 'track';
  const isTravelogView = workspace === 'log' && logView === 'travelog';
  const showDayCards = isPlanView || isTrackView || isTravelogView;

  const days = useMemo(
    () => [...(trip.days || [])].sort((a, b) => String(a.date).localeCompare(String(b.date))),
    [trip],
  );
  const legs = useMemo(
    () => [...(trip.legs || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id)),
    [trip],
  );
  const ideas = useMemo(
    () => [...(trip.ideas || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id)),
    [trip],
  );
  const legById = useMemo(() => new Map(legs.map((l) => [l.id, l])), [legs]);
  const zones = useMemo(() => resolveTripZones(trip, days), [trip, days]);
  const overlapIds = useMemo(() => overlappingStopIds(days, zones), [days, zones]);
  const optionCount = useMemo(
    () => days.reduce((n, d) => n + (d.stops || []).filter((s) => s.status === 'option').length, 0),
    [days],
  );
  const toBookCount = useMemo(() => {
    const stopCount = days.reduce((n, d) => n + (d.stops || []).filter((s) => s.status === 'tobook').length, 0);
    const lodgingCount = (trip.lodgings || []).filter((l) => l.status === 'tobook').length;
    return stopCount + lodgingCount;
  }, [days, trip.lodgings]);
  const documentCount = useMemo(() => tripDocuments(trip).length, [trip]);
  const openTodoCount = useMemo(() => (trip.todos || []).filter((t) => !t.done).length, [trip.todos]);
  const currentDay = days.find((d) => d.id === currentDayId) || null;
  const zoneFilledRef = useRef(null);
  useEffect(() => {
    if (trip.timezone || zoneFilledRef.current === trip.id) return;
    zoneFilledRef.current = trip.id;
    api.json(`/api/trips/trips/${trip.id}/`, { method: 'PATCH', body: JSON.stringify({ timezone: localZone() }) })
      .then(onReload)
      .catch(() => {});
  }, [trip.id, trip.timezone, onReload]);
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
    const today = epochToZoned(Date.now(), localZone()).date;
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
    const activeCleanup = workspace === 'schedule' ? cleanup : '';
    const activeLegFilter = (isPlanView || isTrackView) ? legFilter : 'all';
    return days
      .filter((day) => {
        if (activeLegFilter === 'all') return true;
        if (activeLegFilter === 'none') return !day.leg;
        return String(day.leg || '') === activeLegFilter;
      })
      .map((day) => ({
        ...day,
        stops: [...day.stops].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id)).filter((item) => {
          if (activeCleanup === 'options' && item.status !== 'option') return false;
          if (activeCleanup === 'overlaps' && !overlapIds.has(item.id)) return false;
          if (status !== 'all' && item.status !== status) return false;
          if (loc !== 'all' && item.loc !== loc && item.arrive_loc !== loc) return false;
          if (cat !== 'all' && item.cat !== cat) return false;
          if (query && !`${item.text} ${item.description || ''} ${item.loc} ${item.arrive_loc || ''} ${item.travel_mode || ''}`.toLowerCase().includes(query.toLowerCase())) return false;
          return true;
        }),
      }))
      .filter((d) => isTravelogView || d.stops.length > 0 || (!query && !activeCleanup));
  }, [days, query, loc, cat, status, workspace, cleanup, overlapIds, isTravelogView, isPlanView, isTrackView, legFilter]);
  const filteredDays = useMemo(() => {
    const byId = new Map(visibleDays.map((d) => [d.id, d.stops]));
    return days.map((d) => ({ ...d, stops: byId.get(d.id) || [] }));
  }, [days, visibleDays]);
  const continuing = useMemo(() => continuingStops(filteredDays, zones), [filteredDays, zones]);

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

  const shiftTripDates = async (payload) => {
    await api.json(`/api/trips/trips/${trip.id}/shift-dates/`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    await onReload();
  };

  const insertTripDay = async (payload) => {
    await api.json(`/api/trips/trips/${trip.id}/insert-day/`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    await onReload();
  };

  const removeTripDay = async (payload) => {
    await api.json(`/api/trips/trips/${trip.id}/remove-day/`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    await onReload();
  };

  const swapTripDays = async (payload) => {
    await api.json(`/api/trips/trips/${trip.id}/swap-days/`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    await onReload();
  };

  const moveTripDay = async (payload) => {
    await api.json(`/api/trips/trips/${trip.id}/move-day/`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    await onReload();
  };

  const adjustTripLeg = async (payload) => {
    setError('');
    try {
      await api.json(`/api/trips/trips/${trip.id}/adjust-leg/`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      await onReload();
    } catch (err) {
      setError(err.message);
    }
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

  const applySuggestion = async ({ suggestion, markAdded }, fields) => {
    const updated = await api.json(`/api/trips/suggestions/${suggestion.id}/apply/`, {
      method: 'POST',
      body: JSON.stringify({ fields }),
    });
    markAdded(updated);
    setAiEdit(null);
    await onReload();
  };

  const renameAttachment = async (item, title) => {
    await api.json(`/api/trips/attachments/${item.id}/`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    });
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

  const toggleTodo = async (todo) => {
    try {
      await api.json(`/api/trips/todos/${todo.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ done: !todo.done }),
      });
      await onReload();
    } catch (err) {
      setError(err.message);
    }
  };

  const todosFor = (scope) => (trip.todos || []).filter((t) => todoScope(t) === scope);

  const deleteStop = async (stop) => {
    if (!window.confirm('Delete this stop?')) return;
    await api.json(`/api/trips/stops/${stop.id}/`, { method: 'DELETE' });
    await onReload();
  };

  const setStopStatus = async (stop, nextStatus) => {
    try {
      await api.json(`/api/trips/stops/${stop.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ status: nextStatus }),
      });
      await onReload();
    } catch (err) {
      setError(err.message);
    }
  };

  const patchStopFields = async (stop, body) => {
    try {
      await api.json(`/api/trips/stops/${stop.id}/`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
      await onReload();
    } catch (err) {
      setError(err.message);
    }
  };

  const patchLodgingFields = async (lodging, body) => {
    try {
      await api.json(`/api/trips/lodgings/${lodging.id}/`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
      await onReload();
    } catch (err) {
      setError(err.message);
    }
  };

  const quickAddIdea = async ({ text, leg_id = null, kind = 'activity', loc = '', cat = '' }) => {
    setError('');
    try {
      await api.json('/api/trips/stops/', {
        method: 'POST',
        body: JSON.stringify({
          trip_id: trip.id,
          day_id: null,
          leg_id,
          kind,
          travel_mode: kind === 'travel' ? 'drive' : '',
          text,
          loc,
          cat: cat || (kind === 'event' ? 'Event' : kind === 'travel' ? 'Travel' : 'Sight'),
          status: 'option',
        }),
      });
      await onReload();
    } catch (err) {
      setError(err.message);
      throw err;
    }
  };

  const scheduleIdea = async (ideaOrId, dayId, startTime = null) => {
    const idea = typeof ideaOrId === 'object' ? ideaOrId : ideas.find((i) => i.id === Number(ideaOrId));
    if (!idea || !dayId) return;
    setError('');
    try {
      const body = {
        day_id: Number(dayId),
        status: idea.status === 'option' ? 'no_booking' : idea.status,
      };
      if (startTime) body.start_time = startTime;
      await api.json(`/api/trips/stops/${idea.id}/`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
      setCurrentDayId(Number(dayId));
      await onReload();
    } catch (err) {
      setError(err.message);
    }
  };

  const unscheduleStop = async (stop, legId = null) => {
    setError('');
    try {
      await api.json(`/api/trips/stops/${stop.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({
          day_id: null,
          start_time: null,
          leg_id: legId,
          status: 'option',
        }),
      });
      await onReload();
    } catch (err) {
      setError(err.message);
    }
  };

  const assignIdeaLeg = async (idea, legId) => {
    setError('');
    try {
      await api.json(`/api/trips/stops/${idea.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ leg_id: legId }),
      });
      await onReload();
    } catch (err) {
      setError(err.message);
    }
  };

  const renameDocs = async (items, title) => {
    for (const item of items) {
      await api.json(`/api/trips/attachments/${item.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ title }),
      });
    }
    await onReload();
  };

  const removeAllDocs = async (items, label) => {
    const where = items.length > 1 ? ` from all ${items.length} places it is attached` : '';
    if (!window.confirm(`Remove “${label}”${where}?`)) return;
    for (const item of items) {
      await api.json(`/api/trips/attachments/${item.id}/`, { method: 'DELETE' });
    }
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

  const deleteTrip = async () => {
    const message = `Delete "${trip.title}" with all its days, stops, lodging and attachments? This cannot be undone.`;
    if (!window.confirm(message)) return;
    try {
      await api.json(`/api/trips/trips/${trip.id}/`, { method: 'DELETE' });
      await onDeleted();
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

  const tripDateSummary = useMemo(() => {
    const start = days[0]?.date || trip.start_date;
    const end = days[days.length - 1]?.date || trip.end_date;
    const parts = [];
    if (start && end && start !== end) parts.push(`${formatDay({ date: start })} – ${formatDay({ date: end })}`);
    else if (start) parts.push(formatDay({ date: start }));
    if (days.length) parts.push(`${days.length} ${days.length === 1 ? 'day' : 'days'}`);
    return parts.join(' · ');
  }, [days, trip.start_date, trip.end_date]);

  const leaveTrip = async () => {
    if (!window.confirm(`Leave shared trip "${trip.title}"? You will lose access unless re-invited.`)) return;
    try {
      await api.json(`/api/trips/trips/${trip.id}/leave/`, { method: 'POST' });
      onDeleted();
    } catch (err) {
      setError(err.message);
    }
  };

  const jumpToCommentTarget = (thread, meta) => {
    setCommentsScope(null);
    if (meta?.kind === 'leg') {
      setWorkspace('route');
      return;
    }
    if (meta?.kind === 'lodging') {
      setPrepTab('bookings');
      setWorkspace('prep');
      return;
    }
    if (meta?.kind === 'stop') {
      if (meta.stop?.isIdea) {
        setWorkspace('ideas');
      } else {
        const dayId = meta.stop?.dayObj?.id || meta.stop?.day;
        if (dayId) {
          setCurrentDayId(dayId);
          setCollapsedDayIds((prev) => {
            const next = new Set(prev);
            next.delete(dayId);
            return next;
          });
        }
        chooseScheduleView('itinerary');
        setWorkspace('schedule');
      }
      return;
    }
    if (meta?.kind === 'day' && thread.day) {
      setCurrentDayId(thread.day);
      setCollapsedDayIds((prev) => {
        const next = new Set(prev);
        next.delete(thread.day);
        return next;
      });
      chooseScheduleView('itinerary');
      setWorkspace('schedule');
    }
  };

  const WORKSPACES = [
    { id: 'route', label: 'Route' },
    { id: 'schedule', label: 'Schedule' },
    { id: 'ideas', label: 'Ideas', badge: (ideas.length + optionCount) || null },
    { id: 'prep', label: 'Prep & Bookings', badge: toBookCount || null },
    { id: 'log', label: 'Trip Log' },
  ];

  return (
    <div className="trip-detail">
      <div className="trip-detail-bar">
        <button type="button" onClick={onBack}>← All trips</button>
        <div className="trip-title-block">
          <div className="trip-title-row">
            <h2>{trip.title}</h2>
            {!isOwner && (
              <span className={`trip-role-badge is-${myRole}`} title={trip.owner_label ? `Shared by ${trip.owner_label}` : 'Shared trip'}>
                {myRole === 'editor' ? 'Shared · Editor' : 'Viewer (read-only)'}
              </span>
            )}
            {isOwner && trip.public_enabled && (
              <button type="button" className="trip-role-badge is-public" onClick={() => setShowShare(true)} title="Public read-only link is enabled">
                Public link
              </button>
            )}
          </div>
          {tripDateSummary && <span className="trip-subtitle">{tripDateSummary}</span>}
        </div>
        <div className="trip-icon-row trip-utility-strip">
          <IconButton
            icon="comment"
            label="Comments"
            badge={commentIndex.openThreads || null}
            aria-pressed={Boolean(commentsScope)}
            onClick={() => setCommentsScope((cur) => (cur ? null : 'all'))}
          />
          {isOwner && (
            <IconButton
              icon="share"
              label="Share trip"
              badge={(trip.shares || []).length || null}
              onClick={() => setShowShare(true)}
            />
          )}
          <IconButton
            icon="todo"
            label="To-dos"
            badge={openTodoCount || null}
            onClick={() => setTodosScope('trip')}
          />
          {canEdit && (
            <IconButton icon="ai" label="Ask AI" aria-pressed={showAssistant} onClick={() => setShowAssistant((v) => !v)} />
          )}
          <div className="trip-more-wrap" ref={menuRef}>
            <button
              type="button"
              className="trip-icon-btn trip-more-btn"
              aria-label="More trip options"
              aria-expanded={menuOpen}
              title="Trip settings, links & export"
              onClick={() => setMenuOpen((v) => !v)}
            >
              ⋯
            </button>
            {menuOpen && (
              <div className="trip-more-menu" role="menu">
                {isOwner && (
                  <button type="button" onClick={() => { setMenuOpen(false); setShowShare(true); }}>
                    Share &amp; public link…
                  </button>
                )}
                {canEdit && (
                  <button type="button" onClick={() => { setMenuOpen(false); setEditingInfo(true); }}>
                    Trip details &amp; time zone
                  </button>
                )}
                <button type="button" onClick={() => { setMenuOpen(false); setShowReport(true); }}>
                  Generate report…
                </button>
                <button type="button" onClick={() => { setMenuOpen(false); setShowDocs(true); }}>
                  Documents vault
                </button>
                {isOwner && (
                  <>
                    <div className="trip-more-sep" />
                    <label className="trip-more-field">
                      Packing list
                      <select
                        value={trip.packing_list || ''}
                        onChange={(e) => patchTrip({ packing_list_id: e.target.value ? Number(e.target.value) : null })}
                      >
                        <option value="">None</option>
                        {lists.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                      </select>
                    </label>
                    {trip.packing_list && (
                      <a href="/app/vacation/" className="trip-more-link">Open packing list →</a>
                    )}
                    <label className="trip-more-field">
                      Gallery
                      <select
                        value={trip.gallery || ''}
                        onChange={(e) => patchTrip({ gallery_id: e.target.value || null })}
                      >
                        <option value="">None</option>
                        {galleries.map((g) => <option key={g.id} value={g.id}>{g.title}</option>)}
                      </select>
                    </label>
                    {trip.gallery && (
                      <a href="/app/gallery/" className="trip-more-link">Open gallery →</a>
                    )}
                  </>
                )}
                <div className="trip-more-sep" />
                <button
                  type="button"
                  disabled={exporting}
                  onClick={() => { setMenuOpen(false); exportTrip(); }}
                >
                  {exporting ? 'Exporting…' : 'Export trip (.zip)'}
                </button>
                {isOwner ? (
                  <button
                    type="button"
                    className="is-danger"
                    onClick={() => { setMenuOpen(false); deleteTrip(); }}
                  >
                    Delete trip
                  </button>
                ) : (
                  <button
                    type="button"
                    className="is-danger"
                    onClick={() => { setMenuOpen(false); leaveTrip(); }}
                  >
                    Leave shared trip
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      <nav className="trip-workspaces" aria-label="Trip workspaces">
        {WORKSPACES.map((ws) => (
          <button
            key={ws.id}
            type="button"
            className={workspace === ws.id ? 'is-active' : ''}
            onClick={() => setWorkspace(ws.id)}
          >
            {ws.label}
            {ws.badge ? <span className="trip-ws-badge">{ws.badge}</span> : null}
          </button>
        ))}
      </nav>

      {trip.description && workspace === 'route' && (
        <Markdown className="trip-description">{trip.description}</Markdown>
      )}

      {error && <p className="trip-error">{error}</p>}

      {workspace === 'route' && (
        <RouteWorkspace
          trip={trip}
          days={days}
          legs={legs}
          formatDay={formatDay}
          renderDayZones={(day) => <DayZones day={day} info={zones.days[day.id]} tripZone={zones.tripZone} />}
          renderDayCounts={(stops) => <DayStopCounts stops={stops} />}
          lodgingLabel={lodgingLabel}
          onOpenBulkDays={() => setBulkTripDays(true)}
          onAddDay={() => setAddingDay(true)}
          onEditDay={(day) => setEditingDay(day)}
          onAddLeg={() => setLegForm({ leg: null })}
          onEditLeg={(leg) => setLegForm({ leg })}
          onShiftDates={shiftTripDates}
          onInsertDay={insertTripDay}
          onRemoveDay={removeTripDay}
          onSwapDays={swapTripDays}
          onMoveDay={moveTripDay}
          onAdjustLeg={adjustTripLeg}
          onEditLodging={(lodging, dayIds) => setLodgingForm({ lodging, dayIds })}
          onOpenLegInCalendar={(leg) => {
            setCalendarFocusLegId(leg.id);
            chooseScheduleView('calendar');
            setWorkspace('schedule');
          }}
          onJumpToDay={(day) => {
            setCurrentDayId(day.id);
            setCollapsedDayIds((prev) => {
              const next = new Set(prev);
              next.delete(day.id);
              return next;
            });
            setWorkspace('schedule');
          }}
          canEdit={canEdit}
          commentIndex={commentIndex}
          onOpenComments={(scope) => setCommentsScope(scope)}
        />
      )}

      {workspace === 'ideas' && (
        <IdeasWorkspace
          days={days}
          legs={legs}
          ideas={ideas}
          currentDay={currentDay}
          formatDay={formatDay}
          formatPrice={formatPrice}
          stopTimeText={stopTimeText}
          zones={zones}
          renderAttachments={(atts) => <AttachmentIcons attachments={atts} />}
          onQuickAddIdea={quickAddIdea}
          onAddDetailedIdea={(legId) => setEditing({ isIdea: true, day_id: null, leg_id: legId, kind: 'activity', status: 'option' })}
          onScheduleIdea={scheduleIdea}
          onUnscheduleStop={unscheduleStop}
          onAssignIdeaLeg={assignIdeaLeg}
          onPromote={setStopStatus}
          onEditStop={(stop) => setEditing(stop)}
          onDeleteStop={deleteStop}
          onOpenAssistant={() => setShowAssistant(true)}
          canEdit={canEdit}
          commentIndex={commentIndex}
          onOpenComments={(scope) => setCommentsScope(scope)}
        />
      )}

      {workspace === 'prep' && (
        <PrepWorkspace
          trip={trip}
          days={days}
          legs={legs}
          zones={zones}
          lists={lists}
          documentCount={documentCount}
          subTab={prepTab}
          setSubTab={setPrepTab}
          formatDay={formatDay}
          stopTimeText={stopTimeText}
          formatPrice={formatPrice}
          lodgingLabel={lodgingLabel}
          onSetStopStatus={setStopStatus}
          onPatchStop={patchStopFields}
          onPatchLodging={patchLodgingFields}
          onEditStop={(stop) => setEditing(stop)}
          onEditLodging={(lodging, dayIds) => setLodgingForm({ lodging, dayIds })}
          onOpenReport={() => setShowReport(true)}
          onPatchTrip={patchTrip}
          renderAttachments={(atts) => <AttachmentIcons attachments={atts} />}
          canEdit={canEdit}
          commentIndex={commentIndex}
          onOpenComments={(scope) => setCommentsScope(scope)}
          renderTodos={() => (
            <TripTodos
              inline
              trip={trip}
              days={days}
              hideDone={hideDone}
              setHideDone={setHideDone}
              onChanged={onReload}
            />
          )}
          renderDocuments={() => (
            <TripDocuments
              inline
              trip={trip}
              onRename={renameDocs}
              onRemove={removeAttachment}
              onRemoveAll={removeAllDocs}
              onChanged={onReload}
            />
          )}
        />
      )}

      {workspace === 'log' && (
        <div className="trip-subtabs">
          <button type="button" className={logView === 'track' ? 'is-active' : ''} onClick={() => setLogView('track')}>
            Track (On the trip)
          </button>
          <button type="button" className={logView === 'travelog' ? 'is-active' : ''} onClick={() => setLogView('travelog')}>
            Travelog (Journal &amp; Photos)
          </button>
        </div>
      )}

      {workspace === 'schedule' && (
        <>
          <div className="trip-schedule-bar">
            <div className="trip-view-toggle" role="tablist" aria-label="Schedule view">
              <button
                type="button"
                role="tab"
                aria-selected={scheduleView === 'calendar'}
                className={scheduleView === 'calendar' ? 'is-active' : ''}
                onClick={() => chooseScheduleView('calendar')}
              >
                Calendar
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={scheduleView === 'itinerary'}
                className={scheduleView === 'itinerary' ? 'is-active' : ''}
                onClick={() => chooseScheduleView('itinerary')}
              >
                Itinerary
              </button>
            </div>
            <button
              type="button"
              className={`trip-ideas-rail-toggle${showIdeasRail ? ' is-active' : ''}`}
              aria-pressed={showIdeasRail}
              onClick={() => setShowIdeasRail(!showIdeasRail)}
              title="Toggle unscheduled Ideas rail beside your schedule"
            >
              💡 Ideas{ideas.length ? ` (${ideas.length})` : ''}
            </button>
            {(optionCount > 0 || overlapIds.size > 0) && (
              <div className="trip-cleanup-bar">
                <span className="trip-cleanup-label">Cleanup:</span>
                {optionCount > 0 && (
                  <button
                    type="button"
                    className={`trip-cleanup-pill${cleanup === 'options' ? ' is-active' : ''}`}
                    onClick={() => setCleanup((c) => (c === 'options' ? '' : 'options'))}
                  >
                    {optionCount} {optionCount === 1 ? 'option' : 'options'}
                  </button>
                )}
                {overlapIds.size > 0 && (
                  <button
                    type="button"
                    className={`trip-cleanup-pill${cleanup === 'overlaps' ? ' is-active' : ''}`}
                    onClick={() => setCleanup((c) => (c === 'overlaps' ? '' : 'overlaps'))}
                  >
                    {overlapIds.size} overlapping
                  </button>
                )}
                {cleanup && (
                  <button type="button" className="trip-link-button" onClick={() => setCleanup('')}>Clear</button>
                )}
              </div>
            )}
            {canEdit && (
              <div className="trip-icon-row trip-schedule-adds">
                <IconButton icon="stop" label="Add stop to current day" className="is-primary" onClick={() => setAdding('activity')} disabled={!currentDay} />
                <IconButton icon="travel" label="Add travel to current day" onClick={() => setAdding('travel')} disabled={!currentDay} />
                <IconButton icon="event" label="Add event to current day" onClick={() => setAdding('event')} disabled={!currentDay} />
                <IconButton icon="table" label="Bulk edit current day" onClick={() => setBulkDay(currentDay)} disabled={!currentDay} />
                <IconButton icon="dayAdd" label="Add day" onClick={() => setAddingDay(true)} />
              </div>
            )}
          </div>

          {isPlanView && !hideTodos && todosFor('trip').length > 0 && (
            <section className="trip-trip-todos">
              <div className="trip-trip-todos-head">
                <h4>Trip to-dos</h4>
                <IconButton icon="todo" label="Add trip to-do" onClick={() => setTodosScope('trip')} />
              </div>
              <TodoChecklist todos={todosFor('trip')} hideDone={hideDone} onToggle={toggleTodo} />
            </section>
          )}
        </>
      )}

      {(workspace === 'schedule' || isTrackView) && (
        <div className="trip-filters">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search stops…" />
          {!isCalendarView && legs.length > 0 && (
            <select value={legFilter} onChange={(e) => setLegFilter(e.target.value)} aria-label="Filter by leg">
              <option value="all">All legs</option>
              {legs.map((l) => <option key={l.id} value={String(l.id)}>{l.name}</option>)}
              <option value="none">Ungrouped</option>
            </select>
          )}
          <select value={loc} onChange={(e) => setLoc(e.target.value)}>
            <option value="all">All locations</option>
            {locations.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <select value={cat} onChange={(e) => setCat(e.target.value)}>
            <option value="all">All categories</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <div className="trip-status-tabs">
            {['all', ...STATUS_KEYS].map((s) => (
              <button
                key={s}
                type="button"
                className={status === s ? 'is-active' : ''}
                onClick={() => setStatus(s)}
              >
                {s === 'all' ? 'All' : (s === 'no_booking' ? 'No booking' : STATUS_LABEL[s])}
              </button>
            ))}
          </div>
          {!isCalendarView && (
            <>
              <label className="trip-check" title="Hide completed to-dos everywhere">
                <input type="checkbox" checked={hideDone} onChange={(e) => setHideDone(e.target.checked)} />
                Hide done
              </label>
              <label className="trip-check" title="Don't show to-dos on the itinerary (the To-dos popup still lists them)">
                <input type="checkbox" checked={hideTodos} onChange={(e) => setHideTodos(e.target.checked)} />
                Hide to-dos
              </label>
            </>
          )}
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
        </div>
      )}

      <div className={workspace === 'schedule' && showIdeasRail ? 'trip-schedule-layout has-rail' : 'trip-schedule-layout'}>
        <div className="trip-schedule-main">
      {isCalendarView && (
        <TripCalendar
          days={filteredDays}
          legs={legs}
          focusLegId={calendarFocusLegId}
          onClearFocusLeg={() => setCalendarFocusLegId(null)}
          zones={zones}
          onOpenStop={(stop) => {
            if (canEdit) setEditing(stop);
            else setCommentsScope({ type: 'stop', id: stop.id, label: stop.text });
          }}
          onAddAt={canEdit ? (day, time) => {
            setCurrentDayId(day.id);
            setEditing({ day_id: day.id, kind: 'activity', start_time: time, duration_minutes: 60 });
          } : undefined}
          onDropIdea={canEdit ? (ideaId, day, time) => scheduleIdea(ideaId, day.id, time) : undefined}
        />
      )}

      {showDayCards && !!visibleDays.length && (
        <div className="trip-fold-bar trip-icon-row">
          <IconButton icon="expandAll" label="Expand all days" onClick={expandAllDays} />
          <IconButton icon="collapseAll" label="Collapse all days" onClick={collapseAllDays} />
        </div>
      )}

      {showDayCards && visibleDays.map((day, idx) => {
        const collapsed = collapsedDayIds.has(day.id);
        const prevLegId = idx > 0 ? (visibleDays[idx - 1].leg || null) : undefined;
        const currLegId = day.leg || null;
        const showLegBanner = isPlanView && legs.length > 0 && currLegId !== prevLegId;
        const currLeg = currLegId ? legById.get(currLegId) : null;
        return (
        <React.Fragment key={day.id}>
        {showLegBanner && (
          <div className={`trip-itinerary-leg-banner${currLeg ? '' : ' is-ungrouped'}`}>
            <div className="trip-itinerary-leg-info">
              <strong>{currLeg ? currLeg.name : 'Ungrouped days'}</strong>
              {currLeg?.location && <span className="trip-muted">· {currLeg.location}</span>}
              {currLeg && (
                <span className="trip-muted">
                  · {(currLeg.assigned_day_ids || []).length} {(currLeg.assigned_day_ids || []).length === 1 ? 'day' : 'days'}
                </span>
              )}
            </div>
            {currLeg && (
              <div className="trip-itinerary-leg-actions">
                <button
                  type="button"
                  onClick={() => {
                    setCalendarFocusLegId(currLeg.id);
                    chooseScheduleView('calendar');
                  }}
                >
                  Calendar
                </button>
                <button type="button" onClick={() => setLegForm({ leg: currLeg })}>Edit leg</button>
              </div>
            )}
          </div>
        )}
        <section
          className={`trip-day${day.id === currentDayId ? ' is-current' : ''}${collapsed ? ' is-collapsed' : ''}${dropDayId === day.id ? ' is-drop-target' : ''}`}
          onClick={() => setCurrentDayId(day.id)}
          onDragOver={isPlanView ? (e) => {
            if (!e.dataTransfer.types.includes('application/x-trip-idea')) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            if (dropDayId !== day.id) setDropDayId(day.id);
          } : undefined}
          onDragLeave={isPlanView ? (e) => {
            if (!e.currentTarget.contains(e.relatedTarget) && dropDayId === day.id) setDropDayId(null);
          } : undefined}
          onDrop={isPlanView ? (e) => {
            setDropDayId(null);
            const raw = e.dataTransfer.getData('application/x-trip-idea');
            if (!raw) return;
            e.preventDefault();
            try {
              const { id } = JSON.parse(raw);
              if (id) scheduleIdea(id, day.id);
            } catch { /* ignore */ }
          } : undefined}
        >
          <header>
            <div className="trip-day-head">
              <div className="trip-day-titlebar">
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
                  <DayZones day={day} info={zones.days[day.id]} tripZone={zones.tripZone} />
                  <DayStopCounts stops={(days.find((d) => d.id === day.id) || day).stops} />
                </button>
              </h3>
              {isPlanView && (
                <div className="trip-icon-row">
                  <CommentCountButton
                    openCount={commentIndex.openByKey[`day:${day.id}`] || 0}
                    totalCount={commentIndex.totalByKey[`day:${day.id}`] || 0}
                    label={formatDay(day)}
                    onClick={() => setCommentsScope({ type: 'day', id: day.id, label: formatDay(day) })}
                  />
                  {canEdit && (
                    <>
                      <IconButton icon="stop" label="Add stop" onClick={() => { setCurrentDayId(day.id); setAdding('activity'); }} />
                      <IconButton icon="travel" label="Add travel" onClick={() => { setCurrentDayId(day.id); setAdding('travel'); }} />
                      <IconButton icon="event" label="Add event" onClick={() => { setCurrentDayId(day.id); setAdding('event'); }} />
                      <IconButton icon="todo" label="Add to-do" onClick={() => setTodosScope(`day:${day.id}`)} />
                      <IconButton
                        icon="table"
                        label="Bulk edit stops"
                        onClick={() => { setCurrentDayId(day.id); setBulkDay(days.find((d) => d.id === day.id) || day); }}
                      />
                      <IconButton icon="edit" label="Edit day" onClick={() => setEditingDay(day)} />
                      <IconButton icon="trash" label="Delete day" className="is-danger" onClick={() => deleteDay(day)} />
                    </>
                  )}
                </div>
              )}
              {!collapsed && isTravelogView && canEdit && (
                <div className="trip-icon-row">
                  <IconButton icon="save" label="Save journal" onClick={() => saveJournal(day)} />
                </div>
              )}
              </div>
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
                      canEdit={isPlanView && canEdit}
                      onAdd={() => setAttaching({ lodging: (trip.lodgings || []).find((l) => l.id === day.lodging.id) || day.lodging })}
                      onRemove={removeAttachment}
                    />
                    {isPlanView && canEdit && (
                      <IconButton
                        icon="edit"
                        label="Edit stay"
                        onClick={() => {
                          const full = (trip.lodgings || []).find((l) => l.id === day.lodging.id) || day.lodging;
                          setLodgingForm({ lodging: full, dayIds: [day.id] });
                        }}
                      />
                    )}
                  </>
                ) : (
                  <span className="trip-lodging-empty">No lodging</span>
                )}
                {isPlanView && canEdit && (
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
          </header>
          {!collapsed && isPlanView && day.notes && (
            <Markdown className="trip-day-notes">{day.notes}</Markdown>
          )}
          {!collapsed && isPlanView && !hideTodos && (
            <div className="trip-day-todos">
              <TodoChecklist todos={todosFor(`day:${day.id}`)} hideDone={hideDone} onToggle={toggleTodo} />
            </div>
          )}
          {!collapsed && (isTravelogView ? (
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
              {(continuing[day.date] || []).map(({ stop, span }) => (
                <li key={`cont-${stop.id}`} className={`trip-continuing is-${stop.kind || 'activity'}`}>
                  <button type="button" onClick={(e) => { e.stopPropagation(); setEditing(stop); }}>
                    <span className="trip-stop-time">
                      {span.endDate === day.date ? `until ${formatMinutes(span.endMin % (24 * 60))}` : 'all day'}
                    </span>
                    ↳ {stop.text}
                    <span className="trip-muted"> · continues from {formatDay({ date: span.startDate })}</span>
                  </button>
                </li>
              ))}
              {day.stops.map((stop, index) => (
                <li key={stop.id} className={`is-${stop.kind || 'activity'}${stop.status === 'option' ? ' is-option' : ''}`}>
                  <div>
                    <p>
                      {(stop.start_time || stop.duration_minutes != null) && (
                        <span className="trip-stop-time">
                          {stopTimeText(stop, day, zones)}
                        </span>
                      )}
                      <Markdown inline>{stop.text}</Markdown>
                    </p>
                    <Markdown className="trip-stop-desc">{stop.description}</Markdown>
                    <div className="trip-tags">
                      {stop.kind === 'travel' && (
                        <span className="tag travel">{travelModeLabel(stop.travel_mode)}</span>
                      )}
                      {stop.kind === 'event' && <span className="tag event">Event</span>}
                      <span className={`tag ${stop.status}`}>{STATUS_LABEL[stop.status] || stop.status}</span>
                      {stop.kind === 'travel' && (stop.loc || stop.arrive_loc) ? (
                        <span className="tag">{[stop.loc, stop.arrive_loc].filter(Boolean).join(' → ')}</span>
                      ) : (
                        stop.loc && <span className="tag">{stop.loc}</span>
                      )}
                      {stop.cat && <span className="tag">{stop.cat}</span>}
                      {stop.price != null && <span className="tag price">{formatPrice(stop.price, stop.currency)}</span>}
                      {stop.confirmation && <span className="tag conf" title="Confirmation #"># {stop.confirmation}</span>}
                      {stop.person && <span className="tag person">{stop.person}</span>}
                      {zones.stops[stop.id]?.afterOvernight && (
                        <span className="tag warn" title="Earlier travel on this day arrives on a later date. Move this to the arrival day if it happens after landing.">
                          After overnight travel
                        </span>
                      )}
                    </div>
                    <AttachmentIcons attachments={stop.attachments} />
                    {!hideTodos && (
                      <TodoChecklist todos={todosFor(`stop:${stop.id}`)} hideDone={hideDone} onToggle={toggleTodo} />
                    )}
                  </div>
                  {isPlanView && (
                    <div className="trip-icon-row trip-stop-actions">
                      <CommentCountButton
                        openCount={commentIndex.openByKey[`stop:${stop.id}`] || 0}
                        totalCount={commentIndex.totalByKey[`stop:${stop.id}`] || 0}
                        label={stop.text}
                        onClick={() => setCommentsScope({ type: 'stop', id: stop.id, label: stop.text })}
                      />
                      {canEdit && (
                        <>
                          {stop.status === 'option' && (
                            <button
                              type="button"
                              className="trip-choose-btn"
                              title="Choose this option (set to No booking needed)"
                              onClick={(e) => { e.stopPropagation(); setStopStatus(stop, 'no_booking'); }}
                            >
                              Choose
                            </button>
                          )}
                          <IconButton icon="todo" label="Add to-do" onClick={() => setTodosScope(`stop:${stop.id}`)} />
                          <IconButton icon="up" label="Move up" disabled={index === 0} onClick={() => moveStop(stop, 'up')} />
                          <IconButton
                            icon="down"
                            label="Move down"
                            disabled={index === day.stops.length - 1}
                            onClick={() => moveStop(stop, 'down')}
                          />
                          <IconButton icon="edit" label={`Edit ${KIND_NOUN[stop.kind] || 'stop'}`} onClick={() => setEditing(stop)} />
                          <IconButton icon="trash" label={`Delete ${KIND_NOUN[stop.kind] || 'stop'}`} className="is-danger" onClick={() => deleteStop(stop)} />
                        </>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          ))}
        </section>
        </React.Fragment>
        );
      })}

      {isPlanView && !days.length && (
        <p className="trip-empty">No days yet. Add a day, then add stops.</p>
      )}
        </div>
        {workspace === 'schedule' && showIdeasRail && (
          <IdeasRail
            ideas={ideas}
            legs={legs}
            currentDay={currentDay}
            onQuickAddIdea={quickAddIdea}
            onScheduleIdea={scheduleIdea}
            onEditIdea={(idea) => setEditing(idea)}
            onOpenIdeasTab={() => setWorkspace('ideas')}
            onClose={() => setShowIdeasRail(false)}
          />
        )}
      </div>

      {(addingDay || editingDay) && (
        <DayForm
          initial={editingDay}
          legs={legs}
          inheritedZone={
            editingDay?.id
              ? zones.days[editingDay.id]?.inherited
              : (days.length ? zones.days[days[days.length - 1].id]?.end : zones.tripZone)
          }
          onClose={() => { setAddingDay(false); setEditingDay(null); }}
          onSave={saveDay}
          onDelete={async (day) => {
            await api.json(`/api/trips/days/${day.id}/`, { method: 'DELETE' });
            setAddingDay(false);
            setEditingDay(null);
            await onReload();
          }}
        />
      )}
      {legForm && (
        <LegForm
          trip={trip}
          days={days}
          legs={legs}
          initial={
            legForm.leg?.id
              ? legs.find((l) => l.id === legForm.leg.id) || legForm.leg
              : legForm.leg
          }
          onClose={() => setLegForm(null)}
          onSaved={async () => {
            setLegForm(null);
            await onReload();
          }}
        />
      )}
      {(adding || editing) && (
        <StopForm
          key={editing?.id || (editing?.isIdea ? 'new-idea' : (adding || 'new'))}
          tripId={trip.id}
          days={days}
          legs={legs}
          zones={zones}
          initial={
            editing?.id
              ? days.flatMap((d) => d.stops).find((s) => s.id === editing.id)
                || ideas.find((i) => i.id === editing.id)
                || editing
              : editing
          }
          defaultDayId={currentDayId}
          defaultKind={editing?.kind || adding || 'activity'}
          todoCount={editing?.id ? todosFor(`stop:${editing.id}`).length : 0}
          onClose={() => { setAdding(null); setEditing(null); }}
          onSave={saveStop}
          onDelete={async (stop) => {
            await api.json(`/api/trips/stops/${stop.id}/`, { method: 'DELETE' });
            setAdding(null);
            setEditing(null);
            await onReload();
          }}
          onAddAttachment={onReload}
          onRemoveAttachment={removeAttachment}
          onRenameAttachment={renameAttachment}
        />
      )}
      {bulkDay && (
        <BulkDayEditor
          day={days.find((d) => d.id === bulkDay.id) || bulkDay}
          zones={zones}
          people={[...new Set(days.flatMap((d) => (d.stops || []).map((s) => s.person)).filter(Boolean))].sort()}
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
          hideDone={hideDone}
          onTodosChanged={onReload}
          onClose={() => setEditingInfo(false)}
          onSave={async (body) => {
            await api.json(`/api/trips/trips/${trip.id}/`, { method: 'PATCH', body: JSON.stringify(body) });
            setEditingInfo(false);
            await onReload();
          }}
        />
      )}
      {showReport && <TripReport trip={trip} hideDone={hideDone} onClose={() => setShowReport(false)} />}
      {todosScope && (
        <TripTodos
          trip={trip}
          days={days}
          initialScope={todosScope}
          hideDone={hideDone}
          setHideDone={setHideDone}
          onClose={() => setTodosScope(null)}
          onChanged={onReload}
        />
      )}
      {showAssistant && (
        <TripAssistant
          trip={trip}
          days={days}
          dayLabel={formatDay}
          currentDayId={currentDayId}
          onApplied={onReload}
          onEdit={(suggestion, dayId, markAdded) => setAiEdit({ suggestion, dayId, markAdded })}
          onClose={() => setShowAssistant(false)}
        />
      )}
      {aiEdit && aiEdit.suggestion.kind !== 'lodging' && (
        <StopForm
          key={`ai-${aiEdit.suggestion.id}`}
          tripId={trip.id}
          days={days}
          legs={legs}
          zones={zones}
          initial={{ ...aiEdit.suggestion.draft, day_id: aiEdit.dayId ?? aiEdit.suggestion.draft.day_id }}
          defaultDayId={currentDayId}
          defaultKind={aiEdit.suggestion.draft.kind}
          onClose={() => setAiEdit(null)}
          onSave={async (payload) => {
            await applySuggestion(aiEdit, payload);
            if (payload.day_id) setCurrentDayId(payload.day_id);
          }}
        />
      )}
      {aiEdit && aiEdit.suggestion.kind === 'lodging' && (
        <LodgingForm
          key={`ai-${aiEdit.suggestion.id}`}
          trip={trip}
          days={days}
          initial={aiEdit.suggestion.draft}
          defaultDayIds={aiEdit.suggestion.draft.day_ids}
          onClose={() => setAiEdit(null)}
          onSubmit={(payload) => applySuggestion(aiEdit, payload)}
          onSaved={() => {}}
        />
      )}
      {showDocs && (
        <TripDocuments
          trip={trip}
          onClose={() => setShowDocs(false)}
          onRename={renameDocs}
          onRemove={removeAttachment}
          onRemoveAll={removeAllDocs}
          onChanged={onReload}
        />
      )}
      {showShare && isOwner && (
        <ShareTripModal
          trip={trip}
          onClose={() => setShowShare(false)}
          onChanged={onReload}
        />
      )}
      {commentsScope && (
        <CommentsDrawer
          trip={trip}
          scope={commentsScope}
          currentUser={currentUser}
          canEdit={canEdit}
          isOwner={isOwner}
          onClose={() => setCommentsScope(null)}
          onChangeScope={(next) => setCommentsScope(next)}
          onJumpToTarget={jumpToCommentTarget}
          onReload={onReload}
        />
      )}
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
          onRenameAttachment={renameAttachment}
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
          tripId={trip.id}
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

function NewTripForm({ onClose, onCreate }) {
  const [title, setTitle] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [timezone, setTimezone] = useState(() => localZone());
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const formRef = useRef(null);
  usePopupHotkeys({ onClose, busy, onSave: () => formRef.current?.requestSubmit() });

  const spanDays = startDate && endDate && endDate >= startDate ? dayDiff(startDate, endDate) + 1 : 0;

  const submit = async (e) => {
    e.preventDefault();
    if (!title.trim()) {
      setError('Enter a trip title.');
      return;
    }
    if (startDate && endDate && endDate < startDate) {
      setError('End date must be on or after start date.');
      return;
    }
    if (spanDays > 90) {
      setError('Date range cannot exceed 90 days.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await onCreate({
        title: title.trim(),
        start_date: startDate || null,
        end_date: endDate || null,
        timezone: timezone || localZone(),
        description: description.trim(),
        generate_days: Boolean(startDate && endDate),
      });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" {...backdropDismiss(onClose)} role="presentation">
      <form ref={formRef} className="trip-modal" onSubmit={submit} onClick={(e) => e.stopPropagation()}>
        <h3>Plan a new trip</h3>
        <label>
          Trip title
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g., Japan Autumn 2027"
            required
          />
        </label>
        <div className="trip-form-row">
          <label>
            Start date
            <input
              type="date"
              value={startDate}
              onChange={(e) => {
                const v = e.target.value;
                setStartDate(v);
                if (v && (!endDate || endDate < v)) setEndDate(v);
              }}
            />
          </label>
          <label>
            End date
            <input
              type="date"
              value={endDate}
              min={startDate || undefined}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </label>
        </div>
        {spanDays > 0 && (
          <p className="trip-hint">
            {spanDays} {spanDays === 1 ? 'day' : 'days'} will be created automatically so you can start shaping your route right away.
          </p>
        )}
        <TimeZoneField
          label="Home / starting time zone"
          value={timezone}
          inherited={localZone()}
          date={startDate || undefined}
          allowBlank={false}
          onChange={setTimezone}
        />
        <label>
          Notes / goals (optional)
          <textarea
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Who's going, vibe, priorities…"
          />
        </label>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={onClose} title="Esc">Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy} title={saveHotkeyLabel()}>
            {busy ? 'Creating…' : 'Create trip'}
          </button>
        </div>
      </form>
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
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [creatingTrip, setCreatingTrip] = useState(false);

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
    const requestedTripId = new URLSearchParams(window.location.search).get('trip');
    Promise.all([
      loadTrips(),
      api.json('/api/vacation/lists/').then((d) => setLists(asList(d))).catch(() => setLists([])),
      api.json('/api/gallery/galleries/').then((d) => setGalleries(asList(d))).catch(() => setGalleries([])),
    ])
      .then(() => {
        if (requestedTripId && /^\d+$/.test(requestedTripId)) {
          loadSelected(Number(requestedTripId))
            .then(() => {
              const url = new URL(window.location.href);
              url.searchParams.delete('trip');
              window.history.replaceState({}, '', url.pathname + url.search + url.hash);
            })
            .catch(() => {});
        }
      })
      .catch((err) => setError(err.message));
  }, [isAuthenticated, loadTrips, loadSelected]);

  if (loading) return <div className="p-8 text-center text-stone-500">Loading…</div>;
  if (!user) {
    window.location.replace(getLoginUrl('/app/trips/'));
    return null;
  }

  const createTrip = async (payload) => {
    const created = await api.json('/api/trips/trips/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    setCreatingTrip(false);
    await loadTrips();
    await loadSelected(created.id);
  };

  const importTrip = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const form = new FormData();
      form.append('file', file);
      const data = await api.json('/api/trips/trips/import/', { method: 'POST', body: form });
      await loadTrips();
      const c = data.counts || {};
      const parts = [
        c.trips && `${c.trips} trip${c.trips === 1 ? '' : 's'}`,
        c.legs && `${c.legs} leg${c.legs === 1 ? '' : 's'}`,
        c.days && `${c.days} day${c.days === 1 ? '' : 's'}`,
        c.stops && `${c.stops} stop${c.stops === 1 ? '' : 's'}`,
        c.lodgings && `${c.lodgings} lodging${c.lodgings === 1 ? '' : 's'}`,
        c.todos && `${c.todos} todo${c.todos === 1 ? '' : 's'}`,
        c.comments && `${c.comments} comment${c.comments === 1 ? '' : 's'}`,
        c.shares && `${c.shares} share${c.shares === 1 ? '' : 's'}`,
        c.files && `${c.files} file${c.files === 1 ? '' : 's'}`,
      ].filter(Boolean);
      setNotice(parts.length ? `Imported ${parts.join(' · ')}.` : 'Import complete.');
      if (data.trips?.length === 1) await loadSelected(data.trips[0].id);
    } catch (err) {
      setError(`Import failed: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const exportAllTrips = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const res = await api.fetch('/api/trips/trips/export-all/');
      if (!res.ok) throw new Error(`Export failed (HTTP ${res.status})`);
      const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '')?.[1] || 'trips-export.zip';
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement('a');
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const ownedTripsCount = trips.filter((t) => !t.my_role || t.my_role === 'owner').length;

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
        {notice && (
          <div className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-2 text-sm text-emerald-900">
            <span>{notice}</span>
            <button
              type="button"
              className="text-emerald-700 hover:text-emerald-950"
              onClick={() => setNotice('')}
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        )}
        {selected ? (
          <TripDetail
            key={selected.id}
            trip={selected}
            currentUser={user}
            lists={lists}
            galleries={galleries}
            onBack={() => setSelected(null)}
            onReload={() => loadSelected(selected.id)}
            onDeleted={async () => {
              setSelected(null);
              await loadTrips();
            }}
          />
        ) : (
          <div>
            <div className="trip-list-actions">
              <button type="button" className="trip-primary" onClick={() => setCreatingTrip(true)} disabled={busy}>
                + New trip
              </button>
              <label className={`trip-import${busy ? ' is-disabled' : ''}`} title="Import a trip exported from another server (.zip)">
                {busy ? 'Working…' : 'Import trip…'}
                <input type="file" accept=".zip,.json,application/zip,application/json" onChange={importTrip} disabled={busy} hidden />
              </label>
              {ownedTripsCount > 0 && (
                <button
                  type="button"
                  onClick={exportAllTrips}
                  disabled={busy}
                  title="Export all of your owned trips as a single .zip archive"
                >
                  Export all ({ownedTripsCount}) (.zip)
                </button>
              )}
              <button type="button" onClick={seedDeathValley} disabled={busy}>
                Add Sierra & Death Valley 2026
              </button>
            </div>
            {creatingTrip && (
              <NewTripForm onClose={() => setCreatingTrip(false)} onCreate={createTrip} />
            )}
            <ul className="trip-list">
              {trips.map((t) => (
                <li key={t.id}>
                  <button type="button" onClick={() => loadSelected(t.id)}>
                    <span className="trip-list-title-row">
                      <strong>{t.title}</strong>
                      {t.my_role && t.my_role !== 'owner' && (
                        <span className={`trip-role-badge is-${t.my_role}`}>
                          {t.my_role === 'editor' ? 'Shared · Editor' : 'Shared · Viewer'}
                        </span>
                      )}
                      {t.public_enabled && <span className="trip-role-badge is-public">Public</span>}
                      {t.open_comment_count > 0 && (
                        <span className="trip-list-meta-pill">💬 {t.open_comment_count}</span>
                      )}
                    </span>
                    <span>
                      {[t.start_date, t.end_date].filter(Boolean).join(' – ') || 'No dates'}
                      {t.day_count != null ? ` · ${t.day_count} days` : ''}
                      {t.my_role && t.my_role !== 'owner' && t.owner_label ? ` · by ${t.owner_label}` : ''}
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
