import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  dayDiff, epochToZoned, loadCityIndex, localZone, searchCities, zoneAbbr, zoneCity, zonedToEpoch,
} from '@bldrdojo/timezones';
import { useAuth } from '../contexts/AuthContext';
import api from '../services/api';
import { getLoginUrl } from '../utils/apiUrl';
import AppsMenu from './AppsMenu';
import {
  buildCommentIndex,
  CommentsDrawer,
  ShareTripModal,
} from './TripCollaboration';
import '../mockup/mockup.css';

const LEG_PALETTE = [
  { color: '#0f766e', tint: '#f0fdfa' },
  { color: '#b45309', tint: '#fffbeb' },
  { color: '#0369a1', tint: '#f0f9ff' },
  { color: '#7c3aed', tint: '#f5f3ff' },
  { color: '#be123c', tint: '#fff1f2' },
  { color: '#15803d', tint: '#f0fdf4' },
];

const STATUS_LABEL = {
  option: 'Option',
  no_booking: 'No booking',
  tobook: 'To book',
  booked: 'Booked',
  confirmed: 'Confirmed',
};

const STATUS_OPTIONS = [
  { id: 'option', label: 'Option' },
  { id: 'no_booking', label: 'No booking needed' },
  { id: 'tobook', label: 'To book' },
  { id: 'booked', label: 'Booked' },
  { id: 'confirmed', label: 'Confirmed' },
];

const STOP_TYPE_OPTIONS = [
  { id: 'activity', label: 'Activity', icon: '✦', kind: 'activity', travel_mode: '' },
  { id: 'event', label: 'Event / Dining', icon: '🎟', kind: 'event', travel_mode: '' },
  { id: 'flight', label: 'Flight', icon: '✈', kind: 'travel', travel_mode: 'flight' },
  { id: 'drive', label: 'Drive', icon: '🚗', kind: 'travel', travel_mode: 'drive' },
  { id: 'walk', label: 'Walk', icon: '🚶', kind: 'travel', travel_mode: 'walk' },
  { id: 'boat', label: 'Boat', icon: '⛵', kind: 'travel', travel_mode: 'boat' },
];

function stopTypeId(stop) {
  if (!stop) return 'activity';
  if (stop.kind === 'travel') return stop.travel_mode || 'drive';
  if (stop.kind === 'event') return 'event';
  return 'activity';
}

function stopTypeMeta(stop) {
  const id = stopTypeId(stop);
  return STOP_TYPE_OPTIONS.find((o) => o.id === id) || STOP_TYPE_OPTIONS[0];
}

function stopTypePayload(typeId) {
  const found = STOP_TYPE_OPTIONS.find((o) => o.id === typeId) || STOP_TYPE_OPTIONS[0];
  return { kind: found.kind, travel_mode: found.travel_mode };
}

function parseIsoDate(str) {
  if (!str) return null;
  const d = new Date(`${str}T12:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function addDaysIso(str, delta) {
  const d = parseIsoDate(str);
  if (!d) return '';
  d.setDate(d.getDate() + delta);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function formatShortDate(str) {
  const d = parseIsoDate(str);
  if (!d) return str || '';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatWeekday(str) {
  const d = parseIsoDate(str);
  if (!d) return '';
  return d.toLocaleDateString('en-US', { weekday: 'short' });
}

function formatDateRange(start, end) {
  if (!start && !end) return '';
  if (start && !end) return formatShortDate(start);
  if (!start && end) return formatShortDate(end);
  const ds = parseIsoDate(start);
  const de = parseIsoDate(end);
  if (!ds || !de) return `${start} – ${end}`;
  const sameYear = ds.getFullYear() === de.getFullYear();
  const s = ds.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  const e = de.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  return sameYear ? `${s} – ${e}` : `${ds.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} – ${e}`;
}

function formatTime(t) {
  if (!t) return '';
  const m = String(t).match(/^(\d{1,2}):(\d{2})/);
  return m ? `${m[1].padStart(2, '0')}:${m[2]}` : '';
}

function normalizeTimeInput(val) {
  const s = (val || '').trim();
  if (!s) return null;
  const m = s.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h < 0 || h > 23 || min < 0 || min > 59) return null;
  return `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
}

function parseClockMinutes(str) {
  const m = String(str || '').match(/^(\d{1,2}):(\d{2})/);
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

function formatClock(totalMinutes) {
  const mod = ((totalMinutes % 1440) + 1440) % 1440;
  return `${String(Math.floor(mod / 60)).padStart(2, '0')}:${String(mod % 60).padStart(2, '0')}`;
}

function formatDuration(mins) {
  const n = Number(mins);
  if (!Number.isFinite(n) || n <= 0) return '';
  const h = Math.floor(n / 60);
  const m = n % 60;
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

function durationFromStartAndEnd(start, end) {
  const s = parseClockMinutes(start);
  const e = parseClockMinutes(end);
  if (s === null || e === null) return '';
  const diff = e >= s ? e - s : 1440 - s + e;
  return String(diff);
}

function zonedEnd(date, start, duration, fromZone, toZone) {
  const mins = Number(duration);
  if (!start || duration === '' || duration == null || !Number.isFinite(mins)) return null;
  if (!date || !fromZone || !toZone) {
    const base = parseClockMinutes(start);
    if (base === null) return null;
    const total = base + mins;
    return { time: formatClock(total), offset: Math.floor(total / 1440) };
  }
  const end = epochToZoned(zonedToEpoch(date, start, fromZone) + mins * 60000, toZone);
  return { time: end.time, offset: dayDiff(date, end.date) };
}

function zonedDuration(date, start, end, fromZone, toZone) {
  if (!date || !fromZone || !toZone || fromZone === toZone) return durationFromStartAndEnd(start, end);
  if (!start || !end) return '';
  const dep = zonedToEpoch(date, start, fromZone);
  const gaps = [-1, 0, 1, 2]
    .map((n) => Math.round((zonedToEpoch(addDaysIso(date, n), end, toZone) - dep) / 60000))
    .filter((m) => m >= 0);
  return gaps.length ? String(Math.min(...gaps)) : '';
}

function dayOffsetLabel(offset) {
  return offset ? ` (+${offset})`.replace('+-', '−') : '';
}

function zoneLabel(zone, date) {
  if (!zone) return '';
  const when = date ? zonedToEpoch(date, '12:00', zone) : Date.now();
  return `${zoneAbbr(zone, when)} · ${zone === 'UTC' ? 'UTC' : zoneCity(zone)}`;
}

function zoneShortAbbr(zone, date) {
  if (!zone) return '';
  const when = date ? zonedToEpoch(date, '12:00', zone) : Date.now();
  return zoneAbbr(zone, when);
}

/**
 * Mirrors trips/zones.py: trip timezone → day override → travel arrival zone cascades forward.
 */
function resolveTripZones(trip, days) {
  const tripZone = trip?.timezone || localZone();
  let zone = tripZone;
  const dayInfo = {};
  const stopInfo = {};
  for (const day of [...days].sort((a, b) => String(a.date || '').localeCompare(String(b.date || '')))) {
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
        const startTime = formatTime(stop.start_time);
        info.arrive = zonedEnd(day.date, startTime, stop.duration_minutes, own, info.arriveZone);
        overnight = overnight || (info.arrive?.offset || 0) > 0;
        zone = info.arriveZone;
      } else if (stop.kind === 'activity') {
        const startTime = formatTime(stop.start_time);
        info.arrive = zonedEnd(day.date, startTime, stop.duration_minutes, own, own);
      }
      for (const z of [own, info.arriveZone]) if (z && !zones.includes(z)) zones.push(z);
      stopInfo[stop.id] = info;
    }
    dayInfo[day.id] = { inherited, start, end: zone, zones };
  }
  return { tripZone, days: dayInfo, stops: stopInfo };
}

function formatStopTimeSummary(stop, day, stopZoneInfo, dayZoneInfo) {
  const start = formatTime(stop.start_time);
  const depZone = stopZoneInfo?.zone;
  const arrZone = stopZoneInfo?.arriveZone || depZone;
  const crosses = stop.kind === 'travel' && depZone && arrZone && depZone !== arrZone;
  const overridesDay = Boolean(stop.timezone && dayZoneInfo && stop.timezone !== dayZoneInfo.start);
  const depAbbr = depZone ? zoneShortAbbr(depZone, day?.date) : '';
  const arrAbbr = arrZone ? zoneShortAbbr(arrZone, day?.date) : '';
  const dur = formatDuration(stop.duration_minutes);
  const arrive = stopZoneInfo?.arrive;

  if (!start && !dur) return { primary: '—', detail: '' };

  if (crosses && start && arrive?.time) {
    const off = arrive.offset ? ` (${arrive.offset > 0 ? '+' : '−'}${Math.abs(arrive.offset)})` : '';
    return {
      primary: `${start} ${depAbbr}`,
      detail: `→ ${arrive.time}${off} ${arrAbbr}${dur ? ` · ${dur}` : ''}`,
    };
  }
  if (start && arrive?.time && stop.duration_minutes) {
    const off = arrive.offset ? ` (${arrive.offset > 0 ? '+' : '−'}${Math.abs(arrive.offset)})` : '';
    return {
      primary: `${start}${overridesDay ? ` ${depAbbr}` : ''}`,
      detail: `– ${arrive.time}${off}${dur ? ` · ${dur}` : ''}`,
    };
  }
  if (start) {
    return {
      primary: `${start}${overridesDay ? ` ${depAbbr}` : ''}`,
      detail: dur || '',
    };
  }
  return { primary: '—', detail: dur };
}

/** City-searchable time zone chooser (mirrors TripApp.jsx). */
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
    <label className="tm-field tm-tz-field">
      <span>{label}</span>
      <span className="tm-tz-current">
        <strong>{zoneLabel(effective, date) || 'Not set'}</strong>
        {!value && inheritedNote && <span className="tm-muted"> ({inheritedNote})</span>}
        {value && allowBlank && (
          <button type="button" className="tm-link-inline" style={{ marginLeft: 6 }} onClick={() => onChange('')}>
            Reset
          </button>
        )}
      </span>
      <span className="tm-tz-search">
        <input
          type="text"
          value={query}
          placeholder="Search a city to change…"
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
          <ul className="tm-tz-results" role="listbox">
            {!index && <li className="tm-muted">Loading cities…</li>}
            {index && !results.length && <li className="tm-muted">No matching city</li>}
            {results.map((r, i) => (
              <li
                key={`${r.label}|${r.detail}|${r.timezone}`}
                role="option"
                aria-selected={i === highlight}
                className={i === highlight ? 'is-active' : ''}
                onMouseDown={(e) => { e.preventDefault(); pick(r.timezone); }}
              >
                <span>{r.label}<span className="tm-muted">, {r.detail}</span></span>
                <span className="tm-muted">{zoneAbbr(r.timezone)}</span>
              </li>
            ))}
          </ul>
        )}
      </span>
    </label>
  );
}

function formatPrice(price, currency) {
  if (price === null || price === undefined || price === '') return '';
  const num = Number(price);
  if (Number.isNaN(num)) return String(price);
  const code = (currency || 'USD').toUpperCase();
  if (code === 'USD') return `$${num.toLocaleString()}`;
  return `${num.toLocaleString()} ${code}`;
}

function asList(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

function stopSubtitle(stop) {
  const parts = [];
  if (stop.loc && stop.arrive_loc) parts.push(`${stop.loc} → ${stop.arrive_loc}`);
  else if (stop.loc) parts.push(stop.loc);
  if (stop.cat) parts.push(stop.cat);
  if (stop.price !== null && stop.price !== undefined && stop.price !== '') {
    parts.push(formatPrice(stop.price, stop.currency));
  }
  if (stop.confirmation) parts.push(`Conf # ${stop.confirmation}`);
  if (stop.description && !parts.length) {
    parts.push(stop.description.split('\n')[0].slice(0, 90));
  }
  return parts.join(' · ');
}

function buildViewModel(rawTrip) {
  if (!rawTrip) return null;
  const rawLegs = [...(rawTrip.legs || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id));
  const legById = new Map();
  rawLegs.forEach((l, idx) => {
    const pal = LEG_PALETTE[idx % LEG_PALETTE.length];
    legById.set(l.id, {
      ...l,
      color: pal.color,
      tint: pal.tint,
      isVirtual: false,
    });
  });

  const rawDays = [...(rawTrip.days || [])].sort((a, b) => {
    if (a.date && b.date && a.date !== b.date) return a.date.localeCompare(b.date);
    return (a.sort_order - b.sort_order) || (a.id - b.id);
  });

  const days = rawDays.map((d, idx) => {
    const stops = [...(d.stops || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id));
    const legObj = d.leg && legById.has(d.leg) ? legById.get(d.leg) : null;
    return {
      ...d,
      num: idx + 1,
      weekday: formatWeekday(d.date),
      shortDate: formatShortDate(d.date),
      stay: d.lodging?.name || '',
      stops,
      legObj,
    };
  });

  // Build ordered leg sections (grouping contiguous unassigned days cleanly)
  const legSections = [];
  const usedLegIds = new Set();
  for (const day of days) {
    const leg = day.legObj || {
      id: 'unassigned',
      name: rawLegs.length ? 'Other Days' : 'Trip Days',
      location: '',
      notes: '',
      color: '#57534e',
      tint: '#fafaf9',
      isVirtual: true,
    };
    if (!leg.isVirtual) usedLegIds.add(leg.id);
    const last = legSections[legSections.length - 1];
    if (last && last.id === leg.id) {
      last.days.push(day);
    } else {
      legSections.push({
        ...leg,
        days: [day],
      });
    }
  }
  // Include empty legs at the end so users can see/edit them
  for (const l of rawLegs) {
    if (!usedLegIds.has(l.id)) {
      const full = legById.get(l.id);
      legSections.push({ ...full, days: [] });
    }
  }

  const enrichedLegSections = legSections.map((sec) => {
    const first = sec.days[0]?.date;
    const last = sec.days[sec.days.length - 1]?.date;
    const stays = [...new Set(sec.days.map((d) => d.stay).filter(Boolean))];
    return {
      ...sec,
      dates: first && last ? (first === last ? formatShortDate(first) : `${formatShortDate(first)} – ${formatShortDate(last)}`) : '',
      stay: stays.join(' / '),
    };
  });

  const allDays = days.map((day) => {
    const sec = enrichedLegSections.find((s) => s.days.some((d) => d.id === day.id));
    return { day, leg: sec };
  });

  const ideas = (rawTrip.ideas || []).map((idea) => {
    const legObj = idea.leg && legById.has(idea.leg) ? legById.get(idea.leg) : null;
    return {
      ...idea,
      legName: legObj ? legObj.name : 'Trip-wide',
      legColor: legObj ? legObj.color : '#57534e',
    };
  });

  // Bookings aggregation (Stays + Stops with booking status / confirmation / price)
  const stayBookings = (rawTrip.lodgings || []).map((l) => {
    const assigned = days.filter((d) => d.lodging?.id === l.id);
    const dates = assigned.length
      ? (assigned.length === 1
        ? assigned[0].shortDate
        : `${assigned[0].shortDate} – ${assigned[assigned.length - 1].shortDate}`)
      : '';
    return {
      key: `lodging-${l.id}`,
      entityType: 'lodging',
      id: l.id,
      group: 'Stays',
      title: l.name,
      dates: dates ? `${dates} (${assigned.length}n)` : 'Unassigned dates',
      status: l.status || 'option',
      conf: l.confirmation || '',
      price: formatPrice(l.price, l.currency),
      raw: l,
    };
  });

  const stopBookings = [];
  for (const { day } of allDays) {
    for (const s of day.stops) {
      const isTravel = s.kind === 'travel';
      const hasBookingState = ['tobook', 'booked', 'confirmed'].includes(s.status) || Boolean(s.confirmation) || isTravel;
      if (!hasBookingState) continue;
      stopBookings.push({
        key: `stop-${s.id}`,
        entityType: 'stop',
        id: s.id,
        group: isTravel ? 'Flights & Travel' : 'Activities & Events',
        title: s.text,
        dates: `Day ${day.num} · ${day.shortDate}${s.start_time ? ` · ${formatTime(s.start_time)}` : ''}`,
        status: s.status || 'no_booking',
        conf: s.confirmation || '',
        price: formatPrice(s.price, s.currency),
        dayId: day.id,
        raw: s,
      });
    }
  }

  const bookings = [...stayBookings, ...stopBookings];

  // Documents aggregation (attachments from lodgings + stops + day media)
  const documents = [];
  for (const l of rawTrip.lodgings || []) {
    for (const att of l.attachments || []) {
      documents.push({
        id: `att-${att.id}`,
        attachmentId: att.id,
        category: 'Stays',
        name: att.title || att.address || att.url || 'Attachment',
        kind: att.kind,
        url: att.file_url || att.url || att.osm_url || '',
        linked: l.name,
        note: att.address || '',
      });
    }
  }
  for (const { day } of allDays) {
    for (const s of day.stops) {
      for (const att of s.attachments || []) {
        documents.push({
          id: `att-${att.id}`,
          attachmentId: att.id,
          category: s.kind === 'travel' ? 'Flights & Travel' : 'Activities',
          name: att.title || att.address || att.url || 'Attachment',
          kind: att.kind,
          url: att.file_url || att.url || att.osm_url || '',
          linked: `Day ${day.num} · ${s.text}`,
          note: att.address || '',
        });
      }
    }
    for (const m of day.media || []) {
      documents.push({
        id: `media-${m.id}`,
        mediaId: m.id,
        category: 'Photos & Media',
        name: m.caption || m.filename || 'Photo',
        kind: 'picture',
        url: m.url || '',
        linked: `Day ${day.num} · ${day.shortDate}`,
        note: '',
      });
    }
  }

  const zones = resolveTripZones(rawTrip, days);

  return {
    raw: rawTrip,
    legs: rawLegs,
    legSections: enrichedLegSections,
    days,
    allDays,
    ideas,
    bookings,
    documents,
    zones,
    dateRange: formatDateRange(
      rawTrip.start_date || days[0]?.date,
      rawTrip.end_date || days[days.length - 1]?.date,
    ),
  };
}

/* ================= DRAWERS & MODALS ================= */

function DayPeekDrawer({ day, leg, zones, canEdit, onClose, onOpenItinerary, onEditDay }) {
  if (!day) return null;
  const dayZ = zones?.days?.[day.id];
  const dayZoneTag = dayZ?.zones?.length
    ? dayZ.zones.map((z) => zoneShortAbbr(z, day.date)).filter((v, i, a) => a.indexOf(v) === i).join(' → ')
    : '';
  return (
    <div className="tm-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label={`Day ${day.num} details`}>
      <aside className="tm-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="tm-drawer-head">
          <div>
            <span className="tm-eyebrow" style={{ color: leg?.color || '#0f766e' }}>
              {leg?.name || 'Trip'} · Day {day.num} · {day.weekday}, {day.shortDate}
              {dayZoneTag ? ` · ${dayZoneTag}` : ''}
            </span>
            <h2>{day.title || `Day ${day.num}`}</h2>
          </div>
          <button type="button" className="tm-close-btn" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="tm-drawer-body">
          {day.stay && (
            <div className="tm-stay-banner">
              <span className="tm-stay-icon">🛏</span>
              <div>
                <strong>{day.stay}</strong>
                {day.lodging?.confirmation && <span className="tm-muted"> · Conf # {day.lodging.confirmation}</span>}
              </div>
            </div>
          )}

          {day.notes && (
            <div className="tm-drawer-notes">
              <h4>Day notes</h4>
              <p>{day.notes}</p>
            </div>
          )}

          <div className="tm-drawer-list">
            <h4>Schedule ({day.stops.length})</h4>
            {day.stops.length === 0 ? (
              <p className="tm-muted">No activities scheduled yet.</p>
            ) : (
              <ul>
                {day.stops.map((stop) => {
                  const meta = stopTypeMeta(stop);
                  const sub = stopSubtitle(stop);
                  const tInfo = formatStopTimeSummary(stop, day, zones?.stops?.[stop.id], dayZ);
                  return (
                    <li key={stop.id} className="tm-peek-item">
                      <span className="tm-peek-time">{tInfo.primary}</span>
                      <span className="tm-peek-icon" aria-hidden="true">{meta.icon}</span>
                      <div className="tm-peek-content">
                        <div className="tm-peek-title-row">
                          <strong>{stop.text}</strong>
                          {tInfo.detail && <span className="tm-tz-inline">{tInfo.detail}</span>}
                          {stop.status && stop.status !== 'no_booking' && (
                            <span className={`tm-status is-${stop.status}`}>{STATUS_LABEL[stop.status] || stop.status}</span>
                          )}
                        </div>
                        {sub && <span className="tm-muted">{sub}</span>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        <div className="tm-drawer-foot">
          {canEdit && (
            <button type="button" className="tm-btn-ghost" onClick={() => onEditDay(day, leg)}>
              Edit day
            </button>
          )}
          <button type="button" className="tm-btn-primary" onClick={() => onOpenItinerary(day.id)}>
            Open in Itinerary →
          </button>
        </div>
      </aside>
    </div>
  );
}

function ActivityDrawer({ state, legs, zones, saving, onClose, onSave, onDelete, onMoveToIdeas }) {
  const isNew = !state?.stop;
  const isIdeaMode = Boolean(state?.isIdea);
  const dayDate = state?.day?.date || '';
  const inheritedZone = (state?.stop && zones?.stops?.[state.stop.id]?.inherited)
    || (state?.day && zones?.days?.[state.day.id]?.end)
    || zones?.tripZone
    || localZone();

  const initialKind = state?.stop?.kind || 'activity';
  const [kind, setKind] = useState(initialKind); // activity | travel | event
  const [travelMode, setTravelMode] = useState(state?.stop?.travel_mode || 'flight');
  const [text, setText] = useState(state?.stop?.text || '');
  const [startTime, setStartTime] = useState(formatTime(state?.stop?.start_time));
  const [durationMinutes, setDurationMinutes] = useState(state?.stop?.duration_minutes ?? '');
  const [timezone, setTimezone] = useState(state?.stop?.timezone || '');
  const [arriveTimezone, setArriveTimezone] = useState(state?.stop?.arrive_timezone || '');
  const [endTime, setEndTime] = useState(() => {
    const depZ = state?.stop?.timezone || inheritedZone;
    const arrZ = initialKind === 'travel' ? (state?.stop?.arrive_timezone || depZ) : depZ;
    return zonedEnd(dayDate, formatTime(state?.stop?.start_time), state?.stop?.duration_minutes, depZ, arrZ)?.time || '';
  });
  const [status, setStatus] = useState(state?.stop?.status || 'no_booking');
  const [confirmation, setConfirmation] = useState(state?.stop?.confirmation || '');
  const [loc, setLoc] = useState(state?.stop?.loc || '');
  const [arriveLoc, setArriveLoc] = useState(state?.stop?.arrive_loc || '');
  const [cat, setCat] = useState(state?.stop?.cat || '');
  const [price, setPrice] = useState(state?.stop?.price ?? '');
  const [currency, setCurrency] = useState(state?.stop?.currency || '');
  const [person, setPerson] = useState(state?.stop?.person || '');
  const [description, setDescription] = useState(state?.stop?.description || '');
  const [legId, setLegId] = useState(state?.stop?.leg ? String(state.stop.leg) : '');

  if (!state) return null;
  const isTravel = kind === 'travel';
  const isEvent = kind === 'event';

  const depZone = timezone || inheritedZone;
  const arrZone = isTravel ? (arriveTimezone || depZone) : depZone;
  const crossesZones = isTravel && depZone !== arrZone;
  const depAbbr = zoneShortAbbr(depZone, dayDate);
  const arrAbbr = zoneShortAbbr(arrZone, dayDate);

  const computedEnd = !isEvent && startTime && durationMinutes !== ''
    ? zonedEnd(dayDate, normalizeTimeInput(startTime) || '', durationMinutes, depZone, arrZone)
    : null;
  const endOffset = computedEnd?.offset || 0;

  const handleStartChange = (nextStart) => {
    setStartTime(nextStart);
    const norm = normalizeTimeInput(nextStart);
    if (!norm || isEvent) return;
    if (durationMinutes !== '') {
      setEndTime(zonedEnd(dayDate, norm, durationMinutes, depZone, arrZone)?.time || '');
    } else if (normalizeTimeInput(endTime)) {
      setDurationMinutes(zonedDuration(dayDate, norm, normalizeTimeInput(endTime), depZone, arrZone));
    }
  };

  const handleEndChange = (nextEnd) => {
    setEndTime(nextEnd);
    const normStart = normalizeTimeInput(startTime);
    const normEnd = normalizeTimeInput(nextEnd);
    if (normStart && normEnd && !isEvent) {
      setDurationMinutes(zonedDuration(dayDate, normStart, normEnd, depZone, arrZone));
    }
  };

  const handleDurationChange = (nextDur) => {
    setDurationMinutes(nextDur);
    const normStart = normalizeTimeInput(startTime);
    if (normStart && nextDur !== '' && !isEvent) {
      setEndTime(zonedEnd(dayDate, normStart, nextDur, depZone, arrZone)?.time || '');
    } else if (nextDur === '') {
      setEndTime('');
    }
  };

  const handleZonesChange = (nextZone, nextArriveZone) => {
    setTimezone(nextZone);
    setArriveTimezone(nextArriveZone);
    const normStart = normalizeTimeInput(startTime);
    const normEnd = normalizeTimeInput(endTime);
    if (normStart && normEnd && !isEvent) {
      const dZ = nextZone || inheritedZone;
      const aZ = isTravel ? (nextArriveZone || dZ) : dZ;
      setDurationMinutes(zonedDuration(dayDate, normStart, normEnd, dZ, aZ));
    }
  };

  const travelModeLabel = { flight: 'Flight', drive: 'Drive', walk: 'Walk', boat: 'Boat' }[travelMode] || 'Travel';
  const autoTravelTitle = loc.trim() && arriveLoc.trim()
    ? `${travelModeLabel}: ${loc.trim()} → ${arriveLoc.trim()}`
    : loc.trim()
      ? `${travelModeLabel} from ${loc.trim()}`
      : arriveLoc.trim()
        ? `${travelModeLabel} to ${arriveLoc.trim()}`
        : '';

  const effectiveTitle = text.trim() || (isTravel ? autoTravelTitle : '');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!effectiveTitle) return;
    onSave({
      text: effectiveTitle,
      kind,
      travel_mode: isTravel ? travelMode : '',
      start_time: isIdeaMode ? null : normalizeTimeInput(startTime),
      duration_minutes: isEvent || durationMinutes === '' || durationMinutes === null ? null : Number(durationMinutes),
      timezone: isIdeaMode ? '' : timezone.trim(),
      arrive_timezone: !isIdeaMode && isTravel ? arriveTimezone.trim() : '',
      status,
      confirmation: confirmation.trim(),
      loc: loc.trim(),
      arrive_loc: isTravel ? arriveLoc.trim() : '',
      cat: cat.trim() || (isTravel ? 'Travel' : ''),
      price: price === '' || price === null ? null : Number(price),
      currency: currency.trim().toUpperCase(),
      person: person.trim(),
      description: description.trim(),
      ...(isIdeaMode ? { leg_id: legId ? Number(legId) : null } : {}),
    });
  };

  return (
    <div className="tm-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label={isNew ? 'Add item' : 'Edit item'}>
      <aside className="tm-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="tm-drawer-head">
          <div>
            <span className="tm-eyebrow" style={{ color: state.leg?.color || '#0f766e' }}>
              {isIdeaMode ? 'Ideas Pool' : `Day ${state.day?.num} · ${state.day?.shortDate}`}
            </span>
            <h2>
              {isNew
                ? (isIdeaMode ? 'Add idea' : isTravel ? `Add ${travelModeLabel.toLowerCase()}` : isEvent ? 'Add event' : 'Add activity')
                : (isIdeaMode ? 'Edit idea' : isTravel ? `Edit ${travelModeLabel.toLowerCase()}` : isEvent ? 'Edit event' : 'Edit activity')}
            </h2>
          </div>
          <button type="button" className="tm-close-btn" onClick={onClose} aria-label="Close">×</button>
        </div>

        <form className="tm-drawer-form" onSubmit={handleSubmit}>
          <div className="tm-drawer-body tm-form-fields">
            {/* Prominent Type selector at top so fields adapt immediately */}
            <div className="tm-type-tabs" role="tablist" aria-label="Item type">
              {[
                { id: 'activity', label: '✦ Activity' },
                { id: 'travel', label: '✈ Travel' },
                { id: 'event', label: '🎟 Event' },
              ].map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={kind === t.id}
                  className={`tm-type-tab${kind === t.id ? ' is-active' : ''}`}
                  onClick={() => setKind(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {isTravel && (
              <div className="tm-mode-pills" role="group" aria-label="Travel mode">
                {[
                  { id: 'flight', label: '✈ Flight' },
                  { id: 'drive', label: '🚗 Drive' },
                  { id: 'walk', label: '🚶 Walk' },
                  { id: 'boat', label: '⛵ Boat' },
                ].map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    className={`tm-idea-pill${travelMode === m.id ? ' is-active' : ''}`}
                    onClick={() => setTravelMode(m.id)}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            )}

            {isTravel && (
              <div className="tm-field-row">
                <label className="tm-field">
                  <span>Departure location</span>
                  <input
                    type="text"
                    autoFocus={isNew}
                    placeholder={travelMode === 'flight' ? 'e.g., SFO' : 'e.g., Bangkok'}
                    value={loc}
                    onChange={(e) => setLoc(e.target.value)}
                  />
                </label>
                <label className="tm-field">
                  <span>Arrival location</span>
                  <input
                    type="text"
                    placeholder={travelMode === 'flight' ? 'e.g., BKK' : 'e.g., Chiang Mai'}
                    value={arriveLoc}
                    onChange={(e) => setArriveLoc(e.target.value)}
                  />
                </label>
              </div>
            )}

            <label className="tm-field">
              <span>{isTravel ? 'Title (optional if From/To filled)' : isEvent ? 'Event' : 'Activity'}</span>
              <input
                type="text"
                required={!isTravel}
                autoFocus={!isTravel}
                placeholder={
                  isTravel
                    ? (autoTravelTitle || (travelMode === 'flight' ? 'e.g., EVA Air BR17 SFO → BKK' : 'e.g., Private transfer'))
                    : isEvent
                      ? 'e.g., Dinner at Phra Nakhon or Cooking Class'
                      : 'e.g., Grand Palace & Wat Phra Kaew'
                }
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </label>

            {isIdeaMode ? (
              <div className="tm-field-row">
                <label className="tm-field">
                  <span>Leg</span>
                  <select value={legId} onChange={(e) => setLegId(e.target.value)}>
                    <option value="">Trip-wide</option>
                    {legs.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                  </select>
                </label>
                {!isEvent && (
                  <label className="tm-field">
                    <span>Est. duration (min)</span>
                    <input
                      type="number"
                      min="0"
                      step="5"
                      placeholder={isTravel ? '120' : '90'}
                      value={durationMinutes}
                      onChange={(e) => setDurationMinutes(e.target.value)}
                    />
                  </label>
                )}
              </div>
            ) : isEvent ? (
              <>
                <label className="tm-field">
                  <span>Event time ({depAbbr})</span>
                  <input type="text" placeholder="19:30" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
                </label>
                <TimeZoneField
                  label="Time zone"
                  value={timezone}
                  inherited={inheritedZone}
                  inheritedNote="from itinerary"
                  date={dayDate}
                  onChange={(z) => handleZonesChange(z, arriveTimezone)}
                />
              </>
            ) : (
              <>
                <div className="tm-field-row-3">
                  <label className="tm-field">
                    <span>{isTravel ? `Depart (${depAbbr})` : `Start (${depAbbr})`}</span>
                    <input type="text" placeholder={isTravel ? '10:40' : '09:30'} value={startTime} onChange={(e) => handleStartChange(e.target.value)} />
                  </label>
                  <label className="tm-field">
                    <span>{isTravel ? `Arrive (${arrAbbr})` : `End (${arrAbbr})`}</span>
                    <input type="text" placeholder={isTravel ? '14:35' : '11:00'} value={endTime} onChange={(e) => handleEndChange(e.target.value)} />
                    {endOffset !== 0 && (
                      <small className="tm-tz-hint">
                        {isTravel ? 'Arrives' : 'Ends'} {endOffset === 1 ? 'next day' : endOffset === -1 ? 'previous day' : `${endOffset > 0 ? '+' : ''}${endOffset} days`}
                      </small>
                    )}
                  </label>
                  <label className="tm-field">
                    <span>Duration (min)</span>
                    <input
                      type="number"
                      min="0"
                      step="5"
                      placeholder={isTravel ? '240' : '90'}
                      value={durationMinutes}
                      onChange={(e) => handleDurationChange(e.target.value)}
                    />
                    {crossesZones && durationMinutes !== '' && (
                      <small className="tm-tz-hint">{formatDuration(durationMinutes)} actual</small>
                    )}
                  </label>
                </div>

                {isTravel ? (
                  <div className="tm-field-row">
                    <TimeZoneField
                      label="Departure time zone"
                      value={timezone}
                      inherited={inheritedZone}
                      inheritedNote="from itinerary"
                      date={dayDate}
                      onChange={(z) => handleZonesChange(z, arriveTimezone)}
                    />
                    <TimeZoneField
                      label="Arrival time zone"
                      value={arriveTimezone}
                      inherited={depZone}
                      inheritedNote="same as departure"
                      date={dayDate}
                      onChange={(z) => handleZonesChange(timezone, z)}
                    />
                  </div>
                ) : (
                  <TimeZoneField
                    label="Time zone"
                    value={timezone}
                    inherited={inheritedZone}
                    inheritedNote="from itinerary"
                    date={dayDate}
                    onChange={(z) => handleZonesChange(z, arriveTimezone)}
                  />
                )}
                {crossesZones && (
                  <p className="tm-tz-cascade-note">
                    Items after this travel will automatically use {zoneLabel(arrZone, dayDate)}.
                  </p>
                )}
              </>
            )}

            {!isTravel && (
              <div className="tm-field-row">
                <label className="tm-field">
                  <span>Location</span>
                  <input type="text" placeholder="Address, venue, or neighborhood" value={loc} onChange={(e) => setLoc(e.target.value)} />
                </label>
                <label className="tm-field">
                  <span>Category</span>
                  <input type="text" placeholder={isEvent ? 'Dining, Tour, Show…' : 'Sight, Food, Culture…'} value={cat} onChange={(e) => setCat(e.target.value)} />
                </label>
              </div>
            )}

            <div className="tm-field-row">
              <label className="tm-field">
                <span>Booking status</span>
                <select value={status} onChange={(e) => setStatus(e.target.value)}>
                  {STATUS_OPTIONS.map((opt) => (
                    <option key={opt.id} value={opt.id}>{opt.label}</option>
                  ))}
                </select>
              </label>

              <label className="tm-field">
                <span>Confirmation #</span>
                <input type="text" placeholder="Optional" value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
              </label>
            </div>

            <div className="tm-field-row">
              <label className="tm-field">
                <span>Price</span>
                <input type="number" step="0.01" placeholder="Optional" value={price} onChange={(e) => setPrice(e.target.value)} />
              </label>
              <label className="tm-field">
                <span>Currency</span>
                <input type="text" maxLength={3} placeholder="USD" value={currency} onChange={(e) => setCurrency(e.target.value)} />
              </label>
            </div>

            <label className="tm-field">
              <span>Person / booked by</span>
              <input type="text" placeholder="Optional" value={person} onChange={(e) => setPerson(e.target.value)} />
            </label>

            <label className="tm-field">
              <span>Notes</span>
              <textarea rows={3} placeholder={isTravel ? 'Terminal, seat numbers, transfer notes…' : 'Tips, dress code, reservation notes…'} value={description} onChange={(e) => setDescription(e.target.value)} />
            </label>
          </div>

          <div className="tm-drawer-foot">
            <div style={{ display: 'flex', gap: 6 }}>
              {!isNew && (
                <button type="button" className="tm-btn-danger" disabled={saving} onClick={() => onDelete(state.stop.id)}>
                  Delete
                </button>
              )}
              {!isNew && !isIdeaMode && onMoveToIdeas && (
                <button type="button" className="tm-btn-ghost" disabled={saving} onClick={() => onMoveToIdeas(state.stop.id)}>
                  Move to Ideas
                </button>
              )}
            </div>
            <div className="tm-foot-right">
              <button type="button" className="tm-btn-ghost" onClick={onClose}>Cancel</button>
              <button type="submit" className="tm-btn-primary" disabled={saving || !effectiveTitle}>
                {saving ? 'Saving…' : isNew ? 'Add' : 'Save changes'}
              </button>
            </div>
          </div>
        </form>
      </aside>
    </div>
  );
}

function DayDrawer({ state, legs, lodgings, zones, defaultDate, saving, onClose, onSave, onDelete }) {
  const isNew = Boolean(state?.isNew);
  const [title, setTitle] = useState(state?.day?.title || '');
  const [date, setDate] = useState(state?.day?.date || state?.suggestedDate || defaultDate || '');
  const [legId, setLegId] = useState(
    state?.day?.leg ? String(state.day.leg) : (state?.leg && !state.leg.isVirtual ? String(state.leg.id) : ''),
  );
  const [lodgingId, setLodgingId] = useState(state?.day?.lodging?.id ? String(state.day.lodging.id) : '');
  const [timezone, setTimezone] = useState(state?.day?.timezone || '');
  const [notes, setNotes] = useState(state?.day?.notes || '');
  const [ripple, setRipple] = useState(state?.ripple ?? true);

  if (!state) return null;
  const inheritedZone = (state.day && zones?.days?.[state.day.id]?.inherited) || zones?.tripZone || localZone();

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!date) return;
    onSave({
      title: title.trim(),
      date,
      leg_id: legId ? Number(legId) : null,
      lodging_id: lodgingId ? Number(lodgingId) : null,
      timezone: timezone.trim(),
      notes: notes.trim(),
      ripple,
    });
  };

  return (
    <div className="tm-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label={isNew ? 'Add day' : 'Edit day'}>
      <aside className="tm-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="tm-drawer-head">
          <div>
            <span className="tm-eyebrow">{isNew ? 'New Day' : `Day ${state.day?.num}`}</span>
            <h2>{isNew ? (state.insertPosition ? `Insert day ${state.insertPosition}` : 'Add day') : 'Edit day details'}</h2>
          </div>
          <button type="button" className="tm-close-btn" onClick={onClose} aria-label="Close">×</button>
        </div>

        <form className="tm-drawer-form" onSubmit={handleSubmit}>
          <div className="tm-drawer-body tm-form-fields">
            <label className="tm-field">
              <span>Day title</span>
              <input type="text" autoFocus placeholder="e.g., Temples & Riverside Dinner" value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>

            <div className="tm-field-row">
              <label className="tm-field">
                <span>Date</span>
                <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
              </label>

              <label className="tm-field">
                <span>Leg</span>
                <select value={legId} onChange={(e) => setLegId(e.target.value)}>
                  <option value="">No leg</option>
                  {legs.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
              </label>
            </div>

            {!isNew && (
              <>
                <label className="tm-field">
                  <span>Overnight stay</span>
                  <select value={lodgingId} onChange={(e) => setLodgingId(e.target.value)}>
                    <option value="">None</option>
                    {lodgings.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                  </select>
                </label>

                <TimeZoneField
                  label="Time zone"
                  value={timezone}
                  inherited={inheritedZone}
                  inheritedNote="from itinerary"
                  date={date}
                  onChange={setTimezone}
                />
              </>
            )}

            {isNew && (
              <label className="tm-checkbox-row">
                <input type="checkbox" checked={ripple} onChange={(e) => setRipple(e.target.checked)} />
                <span>Shift subsequent days forward by 1 day if this date is already taken</span>
              </label>
            )}

            {!isNew && (
              <label className="tm-field">
                <span>Day notes</span>
                <textarea rows={4} placeholder="Logistics, pacing, reminders…" value={notes} onChange={(e) => setNotes(e.target.value)} />
              </label>
            )}
          </div>

          <div className="tm-drawer-foot">
            {!isNew ? (
              <button type="button" className="tm-btn-danger" disabled={saving} onClick={() => onDelete(state.day.id)}>
                Delete day
              </button>
            ) : <span />}
            <div className="tm-foot-right">
              <button type="button" className="tm-btn-ghost" onClick={onClose}>Cancel</button>
              <button type="submit" className="tm-btn-primary" disabled={saving || !date}>
                {saving ? 'Saving…' : isNew ? 'Add day' : 'Save day'}
              </button>
            </div>
          </div>
        </form>
      </aside>
    </div>
  );
}

function SimpleModal({ title, onClose, onSubmit, saving, submitLabel = 'Save', children }) {
  return (
    <div className="tm-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label={title}>
      <div className="tm-doc-modal" onClick={(e) => e.stopPropagation()}>
        <div className="tm-drawer-head">
          <h2>{title}</h2>
          <button type="button" className="tm-close-btn" onClick={onClose} aria-label="Close">×</button>
        </div>
        <form onSubmit={onSubmit}>
          <div className="tm-doc-preview-body tm-form-fields">{children}</div>
          <div className="tm-drawer-foot">
            <span />
            <div className="tm-foot-right">
              <button type="button" className="tm-btn-ghost" onClick={onClose}>Cancel</button>
              <button type="submit" className="tm-btn-primary" disabled={saving}>{saving ? 'Saving…' : submitLabel}</button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

function CalendarSummary({ allDays, onSelectDay }) {
  if (!allDays.length) {
    return (
      <div className="tm-card" style={{ padding: 28, textAlign: 'center' }}>
        <p className="tm-muted">No days yet — switch to Itinerary and add your first day.</p>
      </div>
    );
  }
  const firstDate = parseIsoDate(allDays[0].day.date);
  const startDow = firstDate ? firstDate.getDay() : 0;
  const leadingBlanks = Array.from({ length: startDow });

  return (
    <div className="tm-cal-wrap">
      <div className="tm-cal-grid">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
          <div key={d} className="tm-cal-dow">{d}</div>
        ))}
        {leadingBlanks.map((_, i) => <div key={`b-${i}`} className="tm-cal-blank" />)}
        {allDays.map(({ day, leg }) => {
          const hasFlight = day.stops.some((s) => s.kind === 'travel' && s.travel_mode === 'flight');
          return (
            <button
              key={day.id}
              type="button"
              className="tm-cal-cell"
              style={{ borderTopColor: leg?.color || '#0f766e' }}
              onClick={() => onSelectDay(day, leg)}
            >
              <div className="tm-cal-cell-head">
                <span className="tm-cal-date">{day.shortDate}</span>
                <span className="tm-cal-daynum" style={{ color: leg?.color || '#0f766e' }}>D{day.num}</span>
              </div>
              <div className="tm-cal-leg" style={{ background: leg?.tint || '#f0fdfa', color: leg?.color || '#0f766e' }}>
                {leg?.name || 'Trip'}
              </div>
              <div className="tm-cal-title">{day.title || `Day ${day.num}`}</div>
              <div className="tm-cal-foot">
                <span>{day.stops.length} items</span>
                {hasFlight && <span>✈ Flight</span>}
                {day.stay && <span>🛏 {day.stay}</span>}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ================= MAIN LIVE APP ================= */

export default function TripLiveApp() {
  const { user, loading: authLoading, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const [trips, setTrips] = useState([]);
  const [tripsLoading, setTripsLoading] = useState(true);
  const [activeTripId, setActiveTripId] = useState(null);
  const [rawTrip, setRawTrip] = useState(null);
  const [tripLoading, setTripLoading] = useState(false);

  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [saving, setSaving] = useState(false);

  // Workspace view state
  const [section, setSection] = useState('summary'); // summary | itinerary | ideas | bookings | documents
  const [summaryMode, setSummaryMode] = useState('overview'); // overview | detail | calendar
  const [legFilter, setLegFilter] = useState('all');
  const [peek, setPeek] = useState(null);

  // Itinerary state
  const [showAllDays, setShowAllDays] = useState(true);
  const [selectedDayIds, setSelectedDayIds] = useState([]);
  const [anchorDayId, setAnchorDayId] = useState(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [rangeMode, setRangeMode] = useState(false);
  const [collapsedDayIds, setCollapsedDayIds] = useState({});
  const [collapsedLegIds, setCollapsedLegIds] = useState({});
  const [pinEditControls, setPinEditControls] = useState(false);
  const [openDayMenuId, setOpenDayMenuId] = useState(null);

  // Ideas split pane state
  const [showIdeasPane, setShowIdeasPane] = useState(false);
  const [ideaLegFilter, setIdeaLegFilter] = useState('all');
  const [ideaSearch, setIdeaSearch] = useState('');
  const [ideaTargetDayById, setIdeaTargetDayById] = useState({});
  const [dragOverDayId, setDragOverDayId] = useState(null);

  // Drawers & Modals
  const [editingDayState, setEditingDayState] = useState(null);
  const [editingActivityState, setEditingActivityState] = useState(null);
  const [quickAddByDay, setQuickAddByDay] = useState({});
  const [showCreateTrip, setShowCreateTrip] = useState(false);
  const [showEditTrip, setShowEditTrip] = useState(false);
  const [showCreateLeg, setShowCreateLeg] = useState(false);
  const [showCreateLodging, setShowCreateLodging] = useState(false);
  const [showShareModal, setShowShareModal] = useState(false);
  const [showCommentsDrawer, setShowCommentsDrawer] = useState(false);
  const [commentScope, setCommentScope] = useState('all');

  // Form states for simple modals
  const [tripForm, setTripForm] = useState({ title: '', description: '', start_date: '', end_date: '', timezone: '', generate_days: true });
  const [legForm, setLegForm] = useState({ name: '', location: '', timezone: '', notes: '' });
  const [lodgingForm, setLodgingForm] = useState({ name: '', status: 'tobook', confirmation: '', price: '', currency: 'USD', address: '' });

  const daySliderRef = useRef(null);
  const importInputRef = useRef(null);

  const showToast = useCallback((msg) => {
    setToast(msg);
    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => setToast(''), 2800);
  }, []);

  const fetchTripsList = useCallback(async () => {
    setTripsLoading(true);
    try {
      const data = await api.json('/api/trips/trips/');
      setTrips(asList(data));
    } catch (e) {
      if (e.message !== 'Unauthorized') setError(e.message || 'Failed to load trips');
    } finally {
      setTripsLoading(false);
    }
  }, []);

  const loadTrip = useCallback(async (id, { silent = false } = {}) => {
    if (!id) return;
    if (!silent) setTripLoading(true);
    try {
      const data = await api.json(`/api/trips/trips/${id}/`);
      setRawTrip(data);
      setActiveTripId(data.id);
      setError('');
    } catch (e) {
      setError(e.message || 'Failed to load trip');
    } finally {
      if (!silent) setTripLoading(false);
    }
  }, []);

  // Resolve ?invite=<token> or URL /<id> on load
  useEffect(() => {
    if (authLoading || !user) return;
    let cancelled = false;
    (async () => {
      const params = new URLSearchParams(location.search);
      const inviteToken = params.get('invite');
      if (inviteToken) {
        try {
          const res = await api.json(`/api/trips/shares/resolve-invite/?token=${encodeURIComponent(inviteToken)}`);
          if (!cancelled && res?.trip_id) {
            await fetchTripsList();
            await loadTrip(res.trip_id);
            navigate(`/${res.trip_id}`, { replace: true });
            return;
          }
        } catch (e) {
          if (!cancelled) setError(e.message || 'Could not open invite link');
        }
      }
      await fetchTripsList();
      const match = location.pathname.match(/^\/(\d+)/);
      if (!cancelled && match) {
        await loadTrip(Number(match[1]));
      }
    })();
    return () => { cancelled = true; };
  }, [authLoading, user, fetchTripsList, loadTrip, location.pathname, location.search, navigate]);

  const vm = useMemo(() => buildViewModel(rawTrip), [rawTrip]);
  const canEdit = rawTrip ? rawTrip.my_role !== 'viewer' : false;
  const isOwner = rawTrip ? rawTrip.my_role === 'owner' : false;

  const commentIndex = useMemo(
    () => buildCommentIndex(rawTrip?.comments || []),
    [rawTrip?.comments],
  );

  // Derived Itinerary selections
  const allDays = vm?.allDays || [];
  const visibleLegSections = useMemo(() => {
    if (!vm) return [];
    return legFilter === 'all' ? vm.legSections : vm.legSections.filter((l) => String(l.id) === String(legFilter));
  }, [vm, legFilter]);

  const selectedItineraryDays = useMemo(() => {
    if (showAllDays) return allDays;
    const set = new Set(selectedDayIds);
    const chosen = allDays.filter(({ day }) => set.has(day.id));
    return chosen.length ? chosen : allDays.slice(0, 1);
  }, [allDays, selectedDayIds, showAllDays]);

  const selectedLegGroups = useMemo(() => {
    const groups = [];
    for (const entry of selectedItineraryDays) {
      const last = groups[groups.length - 1];
      if (last && last.leg.id === entry.leg.id) {
        last.days.push(entry.day);
      } else {
        groups.push({ leg: entry.leg, days: [entry.day] });
      }
    }
    return groups;
  }, [selectedItineraryDays]);

  const selectionSummary = useMemo(() => {
    if (!allDays.length) return 'No days yet';
    if (showAllDays) return `Showing all ${allDays.length} days`;
    const nums = selectedItineraryDays.map(({ day }) => day.num);
    if (nums.length === 1) {
      const { day, leg } = selectedItineraryDays[0];
      return `Day ${day.num} · ${day.weekday}, ${day.shortDate} · ${leg.name}`;
    }
    const isContiguous = nums.every((n, i) => i === 0 || n === nums[i - 1] + 1);
    return isContiguous
      ? `Days ${nums[0]}–${nums[nums.length - 1]} (${nums.length} days selected)`
      : `${nums.length} days selected`;
  }, [showAllDays, allDays.length, selectedItineraryDays]);

  const bookingCounts = useMemo(() => {
    const list = vm?.bookings || [];
    return {
      confirmed: list.filter((b) => b.status === 'confirmed').length,
      booked: list.filter((b) => b.status === 'booked').length,
      tobook: list.filter((b) => b.status === 'tobook').length,
    };
  }, [vm]);

  const anyVisibleExpanded = useMemo(
    () => selectedItineraryDays.some(({ day, leg }) => !collapsedLegIds[leg.id] && !collapsedDayIds[day.id]),
    [selectedItineraryDays, collapsedDayIds, collapsedLegIds],
  );
  const anyVisibleCollapsed = useMemo(
    () => selectedItineraryDays.some(({ day, leg }) => Boolean(collapsedLegIds[leg.id] || collapsedDayIds[day.id])),
    [selectedItineraryDays, collapsedDayIds, collapsedLegIds],
  );

  const ideaLegOptions = useMemo(() => {
    const seen = new Set();
    const opts = [];
    for (const idea of vm?.ideas || []) {
      if (idea.legName && !seen.has(idea.legName)) {
        seen.add(idea.legName);
        opts.push(idea.legName);
      }
    }
    return opts;
  }, [vm?.ideas]);

  const filteredIdeas = useMemo(() => {
    const q = ideaSearch.trim().toLowerCase();
    return (vm?.ideas || []).filter((idea) => {
      if (ideaLegFilter !== 'all' && idea.legName !== ideaLegFilter) return false;
      if (!q) return true;
      return (
        (idea.text || '').toLowerCase().includes(q)
        || (idea.description || '').toLowerCase().includes(q)
        || (idea.cat || '').toLowerCase().includes(q)
        || (idea.legName || '').toLowerCase().includes(q)
      );
    });
  }, [vm?.ideas, ideaLegFilter, ideaSearch]);

  /* ================= NAVIGATION & SELECTION HELPERS ================= */

  const openTrip = (id) => {
    setSection('summary');
    setLegFilter('all');
    setShowAllDays(true);
    setSelectedDayIds([]);
    setCollapsedDayIds({});
    setCollapsedLegIds({});
    setPickerOpen(false);
    setShowIdeasPane(false);
    navigate(`/${id}`);
    loadTrip(id);
  };

  const backToList = () => {
    setActiveTripId(null);
    setRawTrip(null);
    navigate('/');
    fetchTripsList();
  };

  const handleDayPillClick = (dayId, e) => {
    const orderedIds = allDays.map(({ day }) => day.id);
    const clickedIdx = orderedIds.indexOf(dayId);
    const anchorIdx = orderedIds.indexOf(anchorDayId);
    setShowAllDays(false);

    if (e.shiftKey || (rangeMode && anchorIdx !== -1 && selectedDayIds.length === 1 && anchorDayId !== dayId)) {
      const start = Math.min(anchorIdx === -1 ? clickedIdx : anchorIdx, clickedIdx);
      const end = Math.max(anchorIdx === -1 ? clickedIdx : anchorIdx, clickedIdx);
      setSelectedDayIds(orderedIds.slice(start, end + 1));
      if (rangeMode) setRangeMode(false);
      return;
    }
    if (e.ctrlKey || e.metaKey) {
      setSelectedDayIds((prev) => {
        if (prev.includes(dayId)) return prev.length > 1 ? prev.filter((id) => id !== dayId) : prev;
        return [...prev, dayId];
      });
      setAnchorDayId(dayId);
      return;
    }
    setSelectedDayIds([dayId]);
    setAnchorDayId(dayId);
  };

  const selectByLeg = (legSec) => {
    const ids = legSec.days.map((d) => d.id);
    if (!ids.length) return;
    setShowAllDays(false);
    setRangeMode(false);
    setSelectedDayIds(ids);
    setAnchorDayId(ids[0]);
  };

  const isLegSelected = (legSec) => {
    if (showAllDays || !legSec.days.length) return false;
    if (selectedDayIds.length !== legSec.days.length) return false;
    return legSec.days.every((d) => selectedDayIds.includes(d.id));
  };

  const toggleDayCollapsed = (dayId) => setCollapsedDayIds((p) => ({ ...p, [dayId]: !p[dayId] }));
  const toggleLegCollapsed = (legId) => setCollapsedLegIds((p) => ({ ...p, [legId]: !p[legId] }));

  const collapseVisibleDays = () => {
    setCollapsedDayIds((prev) => {
      const next = { ...prev };
      for (const { day } of selectedItineraryDays) next[day.id] = true;
      return next;
    });
  };

  const expandVisibleDays = () => {
    setCollapsedLegIds((prev) => {
      const next = { ...prev };
      for (const { leg } of selectedLegGroups) delete next[leg.id];
      return next;
    });
    setCollapsedDayIds((prev) => {
      const next = { ...prev };
      for (const { day } of selectedItineraryDays) delete next[day.id];
      return next;
    });
  };

  const slideDays = (dir) => {
    daySliderRef.current?.scrollBy({ left: dir * 280, behavior: 'smooth' });
  };

  const jumpToItinerary = (dayId) => {
    setPeek(null);
    setShowAllDays(false);
    setSelectedDayIds([dayId]);
    setAnchorDayId(dayId);
    setPickerOpen(false);
    const entry = allDays.find((f) => f.day.id === dayId);
    if (entry) {
      setCollapsedLegIds((prev) => { const n = { ...prev }; delete n[entry.leg.id]; return n; });
    }
    setCollapsedDayIds((prev) => { const n = { ...prev }; delete n[dayId]; return n; });
    setSection('itinerary');
  };

  const getDefaultTargetDayId = (idea) => {
    if (ideaTargetDayById[idea.id]) return ideaTargetDayById[idea.id];
    const matchingVisible = selectedItineraryDays.find(({ leg }) => !leg.isVirtual && leg.id === idea.leg);
    if (matchingVisible) return String(matchingVisible.day.id);
    const matchingAny = allDays.find(({ leg }) => !leg.isVirtual && leg.id === idea.leg);
    if (matchingAny) return String(matchingAny.day.id);
    return allDays[0] ? String(allDays[0].day.id) : '';
  };

  /* ================= BACKEND CRUD HANDLERS ================= */

  const runMutation = async (fn, successMsg) => {
    setSaving(true);
    setError('');
    try {
      await fn();
      if (activeTripId) await loadTrip(activeTripId, { silent: true });
      if (successMsg) showToast(successMsg);
    } catch (e) {
      setError(e.message || 'Action failed');
    } finally {
      setSaving(false);
    }
  };

  const handleCreateTrip = async (e) => {
    e.preventDefault();
    if (!tripForm.title.trim()) return;
    setSaving(true);
    setError('');
    try {
      const created = await api.json('/api/trips/trips/', {
        method: 'POST',
        body: JSON.stringify({
          title: tripForm.title.trim(),
          description: tripForm.description.trim(),
          start_date: tripForm.start_date || null,
          end_date: tripForm.end_date || null,
          timezone: tripForm.timezone || localZone(),
          generate_days: Boolean(tripForm.generate_days && tripForm.start_date && tripForm.end_date),
        }),
      });
      setShowCreateTrip(false);
      setTripForm({ title: '', description: '', start_date: '', end_date: '', timezone: '', generate_days: true });
      await fetchTripsList();
      openTrip(created.id);
      showToast('Trip created');
    } catch (err) {
      setError(err.message || 'Could not create trip');
    } finally {
      setSaving(false);
    }
  };

  const handleEditTrip = async (e) => {
    e.preventDefault();
    if (!rawTrip || !tripForm.title.trim()) return;
    await runMutation(async () => {
      await api.json(`/api/trips/trips/${rawTrip.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({
          title: tripForm.title.trim(),
          description: tripForm.description.trim(),
          start_date: tripForm.start_date || null,
          end_date: tripForm.end_date || null,
          timezone: tripForm.timezone || '',
        }),
      });
      setShowEditTrip(false);
    }, 'Trip updated');
  };

  const handleCreateLeg = async (e) => {
    e.preventDefault();
    if (!rawTrip || !legForm.name.trim()) return;
    await runMutation(async () => {
      await api.json('/api/trips/legs/', {
        method: 'POST',
        body: JSON.stringify({
          trip_id: rawTrip.id,
          name: legForm.name.trim(),
          location: legForm.location.trim(),
          timezone: legForm.timezone || '',
          notes: legForm.notes.trim(),
        }),
      });
      setShowCreateLeg(false);
      setLegForm({ name: '', location: '', timezone: '', notes: '' });
    }, 'Leg added');
  };

  const handleSaveDay = async (payload) => {
    if (!rawTrip || !editingDayState) return;
    await runMutation(async () => {
      if (editingDayState.isNew) {
        await api.json(`/api/trips/trips/${rawTrip.id}/insert-day/`, {
          method: 'POST',
          body: JSON.stringify({
            date: payload.date,
            title: payload.title,
            leg_id: payload.leg_id,
            ripple: payload.ripple,
          }),
        });
      } else {
        await api.json(`/api/trips/days/${editingDayState.day.id}/`, {
          method: 'PATCH',
          body: JSON.stringify({
            title: payload.title,
            date: payload.date,
            leg_id: payload.leg_id,
            lodging_id: payload.lodging_id,
            timezone: payload.timezone ?? '',
            notes: payload.notes,
          }),
        });
      }
      setEditingDayState(null);
    }, editingDayState.isNew ? 'Day added' : 'Day saved');
  };

  const handleDeleteDay = async (dayId) => {
    if (!rawTrip) return;
    if (!window.confirm('Delete this day and shift later dates back by 1 day?')) return;
    await runMutation(async () => {
      await api.json(`/api/trips/trips/${rawTrip.id}/remove-day/`, {
        method: 'POST',
        body: JSON.stringify({ day_id: dayId, ripple: true }),
      });
      setEditingDayState(null);
      setOpenDayMenuId(null);
      setSelectedDayIds((prev) => prev.filter((id) => id !== dayId));
    }, 'Day deleted');
  };

  const handleSaveStop = async (payload) => {
    if (!rawTrip || !editingActivityState) return;
    const isNew = !editingActivityState.stop;
    await runMutation(async () => {
      if (isNew) {
        await api.json('/api/trips/stops/', {
          method: 'POST',
          body: JSON.stringify({
            ...payload,
            trip_id: rawTrip.id,
            day_id: editingActivityState.isIdea ? null : editingActivityState.day.id,
          }),
        });
      } else {
        await api.json(`/api/trips/stops/${editingActivityState.stop.id}/`, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        });
      }
      setEditingActivityState(null);
    }, isNew ? (editingActivityState.isIdea ? 'Idea added' : 'Activity added') : 'Saved');
  };

  const handleDeleteStop = async (stopId) => {
    await runMutation(async () => {
      await api.json(`/api/trips/stops/${stopId}/`, { method: 'DELETE' });
      setEditingActivityState(null);
    }, 'Deleted');
  };

  const handleMoveStop = async (stopId, direction) => {
    await runMutation(async () => {
      await api.json(`/api/trips/stops/${stopId}/move/`, {
        method: 'POST',
        body: JSON.stringify({ direction }),
      });
    });
  };

  const handleMoveStopToIdeas = async (stopId) => {
    await runMutation(async () => {
      await api.json(`/api/trips/stops/${stopId}/`, {
        method: 'PATCH',
        body: JSON.stringify({ day_id: null }),
      });
      setEditingActivityState(null);
    }, 'Moved to Ideas Pool');
  };

  const handleScheduleIdeaToDay = async (idea, targetDayId) => {
    const dayNumId = Number(targetDayId);
    const dayEntry = allDays.find((e) => e.day.id === dayNumId);
    if (!dayEntry) return;
    await runMutation(async () => {
      await api.json(`/api/trips/stops/${idea.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ day_id: dayNumId }),
      });
      setCollapsedLegIds((prev) => { const n = { ...prev }; delete n[dayEntry.leg.id]; return n; });
      setCollapsedDayIds((prev) => { const n = { ...prev }; delete n[dayNumId]; return n; });
      if (!showAllDays && !selectedDayIds.includes(dayNumId)) {
        setSelectedDayIds((prev) => [...prev, dayNumId]);
      }
    }, `Added "${idea.text}" to Day ${dayEntry.day.num}`);
  };

  const handleQuickAdd = async (dayId, e) => {
    e.preventDefault();
    const draft = quickAddByDay[dayId] || {};
    const text = (draft.title || '').trim();
    if (!text || !rawTrip) return;
    const { kind, travel_mode } = stopTypePayload(draft.typeId || 'activity');
    await runMutation(async () => {
      await api.json('/api/trips/stops/', {
        method: 'POST',
        body: JSON.stringify({
          trip_id: rawTrip.id,
          day_id: dayId,
          kind,
          travel_mode,
          text,
          start_time: normalizeTimeInput(draft.time),
          status: 'no_booking',
        }),
      });
      setQuickAddByDay((prev) => ({ ...prev, [dayId]: { time: '', title: '', typeId: draft.typeId || 'activity' } }));
    }, 'Added');
  };

  const handleUpdateBookingStatus = async (booking, nextStatus) => {
    await runMutation(async () => {
      const endpoint = booking.entityType === 'lodging'
        ? `/api/trips/lodgings/${booking.id}/`
        : `/api/trips/stops/${booking.id}/`;
      await api.json(endpoint, {
        method: 'PATCH',
        body: JSON.stringify({ status: nextStatus }),
      });
    }, `Status updated to ${STATUS_LABEL[nextStatus]}`);
  };

  const handleCreateLodging = async (e) => {
    e.preventDefault();
    if (!rawTrip || !lodgingForm.name.trim()) return;
    await runMutation(async () => {
      await api.json('/api/trips/lodgings/', {
        method: 'POST',
        body: JSON.stringify({
          trip_id: rawTrip.id,
          name: lodgingForm.name.trim(),
          status: lodgingForm.status,
          confirmation: lodgingForm.confirmation.trim(),
          price: lodgingForm.price ? Number(lodgingForm.price) : null,
          currency: lodgingForm.currency.trim().toUpperCase(),
          address: lodgingForm.address.trim(),
        }),
      });
      setShowCreateLodging(false);
      setLodgingForm({ name: '', status: 'tobook', confirmation: '', price: '', currency: 'USD', address: '' });
    }, 'Stay added');
  };

  const handleExportZip = async (url, filename) => {
    try {
      const res = await api.fetch(url);
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objUrl);
    } catch (e) {
      setError(e.message || 'Export failed');
    }
  };

  const handleImportZip = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setSaving(true);
    setError('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const data = await api.json('/api/trips/trips/import/', { method: 'POST', body: fd });
      await fetchTripsList();
      const imported = data?.trips || [];
      if (imported.length === 1) openTrip(imported[0].id);
      showToast(`Imported ${imported.length || 1} trip(s)`);
    } catch (err) {
      setError(err.message || 'Import failed');
    } finally {
      setSaving(false);
    }
  };

  /* ================= AUTH GATE ================= */

  if (authLoading) {
    return <div className="tm-page"><div className="tm-container" style={{ padding: 48 }}>Loading…</div></div>;
  }

  if (!user) {
    const loginHref = getLoginUrl(`${window.location.pathname}${window.location.search}`);
    return (
      <div className="tm-page">
        <div className="tm-container" style={{ padding: '72px 20px', textAlign: 'center' }}>
          <h1 style={{ marginBottom: 8 }}>Trips</h1>
          <p className="tm-muted" style={{ marginBottom: 20 }}>Sign in to plan and view your trips.</p>
          <a href={loginHref} className="tm-btn-primary" style={{ textDecoration: 'none', display: 'inline-block' }}>
            Sign in
          </a>
        </div>
      </div>
    );
  }

  /* ================= TRIPS LIST VIEW ================= */

  if (!activeTripId) {
    return (
      <div className="tm-page">
        <header className="tm-header">
          <div className="tm-container tm-header-inner" style={{ paddingBottom: 14 }}>
            <div className="tm-topbar-row">
              <div className="tm-title-row">
                <AppsMenu current="trips" />
                <span className="tm-topbar-sep">/</span>
                <h1>Trips</h1>
              </div>
              <div className="tm-itin-actions">
                <input ref={importInputRef} type="file" accept=".zip,.json" hidden onChange={handleImportZip} />
                <button type="button" className="tm-tool-btn" onClick={() => importInputRef.current?.click()} disabled={saving}>
                  Import
                </button>
                {trips.length > 0 && (
                  <button
                    type="button"
                    className="tm-tool-btn"
                    onClick={() => handleExportZip('/api/trips/trips/export-all/', 'all-trips.zip')}
                  >
                    Export all
                  </button>
                )}
                <button
                  type="button"
                  className="tm-btn-primary tm-btn-sm"
                  onClick={() => {
                    setTripForm({ title: '', description: '', start_date: '', end_date: '', generate_days: true });
                    setShowCreateTrip(true);
                  }}
                >
                  + Add Trip
                </button>
                <button type="button" className="tm-tool-btn" onClick={logout}>Sign out</button>
              </div>
            </div>
          </div>
        </header>

        <main className="tm-container tm-main">
          {error && (
            <div className="tm-alert-error">
              <span>{error}</span>
              <button type="button" onClick={() => setError('')}>×</button>
            </div>
          )}
          {toast && <div className="tm-toast">{toast}</div>}

          {tripsLoading ? (
            <p className="tm-muted">Loading trips…</p>
          ) : trips.length === 0 ? (
            <div className="tm-card" style={{ padding: 40, textAlign: 'center' }}>
              <h2 style={{ margin: '0 0 8px' }}>No trips yet</h2>
              <p className="tm-muted" style={{ marginBottom: 18 }}>Create your first trip or import a `.zip` backup to get started.</p>
              <button type="button" className="tm-btn-primary" onClick={() => setShowCreateTrip(true)}>
                + Add Trip
              </button>
            </div>
          ) : (
            <div className="tm-trip-list-grid">
              {trips.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className="tm-card tm-trip-card"
                  onClick={() => openTrip(t.id)}
                >
                  <div className="tm-trip-card-top">
                    <h3>{t.title}</h3>
                    {t.my_role && t.my_role !== 'owner' && (
                      <span className="tm-chip-subtle">Shared · {t.my_role}</span>
                    )}
                  </div>
                  <div className="tm-trip-card-meta">
                    {formatDateRange(t.start_date, t.end_date) && (
                      <span className="tm-meta-pill">{formatDateRange(t.start_date, t.end_date)}</span>
                    )}
                    <span className="tm-meta-pill">{t.day_count || 0} days</span>
                    {t.open_comment_count > 0 && (
                      <span className="tm-nav-warn">{t.open_comment_count} comments</span>
                    )}
                  </div>
                  {t.description && <p className="tm-muted tm-trip-card-desc">{t.description}</p>}
                </button>
              ))}
            </div>
          )}
        </main>

        {showCreateTrip && (
          <SimpleModal
            title="New Trip"
            submitLabel="Create Trip"
            saving={saving}
            onClose={() => setShowCreateTrip(false)}
            onSubmit={handleCreateTrip}
          >
            <label className="tm-field">
              <span>Trip title</span>
              <input type="text" required autoFocus placeholder="e.g., Japan Autumn 2026" value={tripForm.title} onChange={(e) => setTripForm((p) => ({ ...p, title: e.target.value }))} />
            </label>
            <label className="tm-field">
              <span>Description</span>
              <input type="text" placeholder="Optional subtitle or cities" value={tripForm.description} onChange={(e) => setTripForm((p) => ({ ...p, description: e.target.value }))} />
            </label>
            <div className="tm-field-row">
              <label className="tm-field">
                <span>Start date</span>
                <input type="date" value={tripForm.start_date} onChange={(e) => setTripForm((p) => ({ ...p, start_date: e.target.value }))} />
              </label>
              <label className="tm-field">
                <span>End date</span>
                <input type="date" value={tripForm.end_date} onChange={(e) => setTripForm((p) => ({ ...p, end_date: e.target.value }))} />
              </label>
            </div>
            <TimeZoneField
              label="Default time zone"
              value={tripForm.timezone}
              inherited={localZone()}
              inheritedNote="your browser zone"
              date={tripForm.start_date}
              onChange={(z) => setTripForm((p) => ({ ...p, timezone: z }))}
            />
            <label className="tm-checkbox-row">
              <input type="checkbox" checked={tripForm.generate_days} onChange={(e) => setTripForm((p) => ({ ...p, generate_days: e.target.checked }))} />
              <span>Automatically create days for this date range</span>
            </label>
          </SimpleModal>
        )}
      </div>
    );
  }

  /* ================= TRIP WORKSPACE ================= */

  const nextNewDayDate = vm?.days.length
    ? addDaysIso(vm.days[vm.days.length - 1].date, 1)
    : (rawTrip?.start_date || new Date().toISOString().slice(0, 10));

  return (
    <div className="tm-page" onClick={() => openDayMenuId && setOpenDayMenuId(null)}>
      <header className="tm-header">
        <div className="tm-container tm-header-inner">
          <div className="tm-topbar-row">
            <div className="tm-title-block">
              <div className="tm-title-row">
                <AppsMenu current="trips" />
                <span className="tm-topbar-sep">/</span>
                <button type="button" className="tm-back-btn" onClick={backToList}>← Trips</button>
                <h1>{rawTrip?.title || 'Loading…'}</h1>
                {vm?.dateRange && <span className="tm-meta-pill">{vm.dateRange}</span>}
                {vm && (
                  <span className="tm-meta-pill">
                    {vm.days.length} {vm.days.length === 1 ? 'day' : 'days'}
                    {vm.legs.length > 0 ? ` · ${vm.legs.length} legs` : ''}
                  </span>
                )}
                {vm?.zones?.tripZone && (
                  <span className="tm-meta-pill" title={`Default trip time zone: ${vm.zones.tripZone}`}>
                    🕒 {zoneLabel(vm.zones.tripZone, rawTrip?.start_date)}
                  </span>
                )}
              </div>
              {rawTrip?.description && <p className="tm-subtitle">{rawTrip.description}</p>}
            </div>

            {rawTrip && (
              <div className="tm-itin-actions">
                {canEdit && (
                  <button
                    type="button"
                    className="tm-tool-btn"
                    onClick={() => {
                      setTripForm({
                        title: rawTrip.title || '',
                        description: rawTrip.description || '',
                        start_date: rawTrip.start_date || '',
                        end_date: rawTrip.end_date || '',
                        timezone: rawTrip.timezone || '',
                        generate_days: false,
                      });
                      setShowEditTrip(true);
                    }}
                  >
                    Edit trip
                  </button>
                )}
                <button
                  type="button"
                  className="tm-tool-btn"
                  onClick={() => { setCommentScope('all'); setShowCommentsDrawer(true); }}
                >
                  Comments{commentIndex.totalOpen > 0 ? ` (${commentIndex.totalOpen})` : ''}
                </button>
                {isOwner && (
                  <button type="button" className="tm-tool-btn" onClick={() => setShowShareModal(true)}>
                    Share{rawTrip.share_count > 0 ? ` (${rawTrip.share_count})` : ''}
                  </button>
                )}
                <button
                  type="button"
                  className="tm-tool-btn"
                  onClick={() => handleExportZip(`/api/trips/trips/${rawTrip.id}/export/`, `${(rawTrip.title || 'trip').replace(/[^a-z0-9-_]+/gi, '_')}.zip`)}
                >
                  Export
                </button>
                <Link to="/legacy" className="tm-tool-btn" style={{ textDecoration: 'none' }} title="Open previous classic view">
                  Classic
                </Link>
              </div>
            )}
          </div>

          <nav className="tm-nav" aria-label="Trip sections">
            {[
              { id: 'summary', label: 'Summary' },
              { id: 'itinerary', label: 'Itinerary' },
              { id: 'ideas', label: 'Ideas', count: vm?.ideas.length || 0 },
              { id: 'bookings', label: 'Bookings', badge: bookingCounts.tobook ? `${bookingCounts.tobook} to book` : null },
              { id: 'documents', label: 'Documents', count: vm?.documents.length || 0 },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`tm-nav-btn${section === tab.id ? ' is-active' : ''}`}
                onClick={() => setSection(tab.id)}
              >
                <span>{tab.label}</span>
                {tab.count != null && <span className="tm-nav-count">{tab.count}</span>}
                {tab.badge && <span className="tm-nav-warn">{tab.badge}</span>}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className={`tm-container tm-main${section === 'itinerary' && showIdeasPane ? ' tm-main-wide' : ''}`}>
        {error && (
          <div className="tm-alert-error">
            <span>{error}</span>
            <button type="button" onClick={() => setError('')}>×</button>
          </div>
        )}
        {toast && <div className="tm-toast">{toast}</div>}

        {tripLoading || !vm ? (
          <p className="tm-muted" style={{ padding: 24 }}>Loading trip…</p>
        ) : (
          <>
            {/* ================= SUMMARY (LANDING PAGE) ================= */}
            {section === 'summary' && (
              <div className="tm-summary">
                <div className="tm-summary-bar">
                  <div className="tm-route-ribbon" role="group" aria-label="Filter by leg">
                    <button
                      type="button"
                      className={`tm-ribbon-pill${legFilter === 'all' ? ' is-active' : ''}`}
                      onClick={() => setLegFilter('all')}
                    >
                      All legs
                    </button>
                    {vm.legSections.map((leg) => (
                      <button
                        key={leg.id}
                        type="button"
                        className={`tm-ribbon-pill${String(legFilter) === String(leg.id) ? ' is-active' : ''}`}
                        onClick={() => setLegFilter(String(legFilter) === String(leg.id) ? 'all' : leg.id)}
                      >
                        <i className="tm-dot" style={{ background: leg.color }} />
                        <span>{leg.name}</span>
                        <small>{leg.days.length}d</small>
                      </button>
                    ))}
                    {canEdit && (
                      <button type="button" className="tm-ribbon-pill" onClick={() => setShowCreateLeg(true)}>
                        + Add leg
                      </button>
                    )}
                  </div>

                  <div className="tm-segmented" role="tablist" aria-label="Summary view mode">
                    {[
                      { id: 'overview', label: 'Overview' },
                      { id: 'detail', label: 'Detail' },
                      { id: 'calendar', label: 'Calendar' },
                    ].map((m) => (
                      <button
                        key={m.id}
                        type="button"
                        role="tab"
                        aria-selected={summaryMode === m.id}
                        className={summaryMode === m.id ? 'is-active' : ''}
                        onClick={() => setSummaryMode(m.id)}
                      >
                        {m.label}
                      </button>
                    ))}
                  </div>
                </div>

                {summaryMode === 'calendar' ? (
                  <CalendarSummary
                    allDays={visibleLegSections.flatMap((leg) => leg.days.map((day) => ({ day, leg })))}
                    onSelectDay={(day, leg) => setPeek({ day, leg })}
                  />
                ) : (
                  <div className="tm-legs-stack">
                    {visibleLegSections.length === 0 && (
                      <div className="tm-card" style={{ padding: 32, textAlign: 'center' }}>
                        <p className="tm-muted">No days in this trip yet.</p>
                        {canEdit && (
                          <button
                            type="button"
                            className="tm-btn-primary tm-btn-sm"
                            onClick={() => {
                              setSection('itinerary');
                              setEditingDayState({ isNew: true, suggestedDate: nextNewDayDate });
                            }}
                          >
                            + Add first day
                          </button>
                        )}
                      </div>
                    )}

                    {visibleLegSections.map((leg) => (
                      <section key={leg.id} className="tm-leg-card">
                        <header className="tm-leg-head" style={{ borderLeftColor: leg.color }}>
                          <div className="tm-leg-head-main">
                            <div className="tm-leg-title-row">
                              <span className="tm-leg-kicker" style={{ color: leg.color }}>Leg</span>
                              <h2>{leg.name}</h2>
                              {leg.location && <span className="tm-leg-region">{leg.location}</span>}
                            </div>
                            <div className="tm-leg-meta">
                              {leg.dates && <span>{leg.dates}</span>}
                              {leg.dates && <span>·</span>}
                              <span>{leg.days.length} {leg.days.length === 1 ? 'day' : 'days'}</span>
                              {leg.stay && (
                                <>
                                  <span>·</span>
                                  <span className="tm-leg-stay-pill">🛏 {leg.stay}</span>
                                </>
                              )}
                            </div>
                          </div>
                          {leg.notes && <p className="tm-leg-summary">{leg.notes}</p>}
                        </header>

                        <ul className="tm-day-list">
                          {leg.days.map((day) => {
                            const toBookCount = day.stops.filter((s) => s.status === 'tobook').length;
                            const hasFlight = day.stops.some((s) => s.kind === 'travel' && s.travel_mode === 'flight');
                            return (
                              <li key={day.id} className="tm-day-row">
                                <button
                                  type="button"
                                  className="tm-day-btn"
                                  onClick={() => setPeek({ day, leg })}
                                >
                                  <div className="tm-day-top">
                                    <div className="tm-day-datecol">
                                      <span className="tm-day-num">Day {day.num}</span>
                                      <span className="tm-day-date">{day.weekday}, {day.shortDate}</span>
                                    </div>
                                    <div className="tm-day-main">
                                      <strong className="tm-day-title">{day.title || `Day ${day.num}`}</strong>
                                      {summaryMode === 'detail' && (
                                        <div className="tm-day-detail">
                                          {day.notes && <p className="tm-day-notes">{day.notes}</p>}
                                          <ul className="tm-inline-items">
                                            {day.stops.map((stop) => {
                                              const tInfo = formatStopTimeSummary(stop, day, vm.zones.stops[stop.id], vm.zones.days[day.id]);
                                              return (
                                                <li key={stop.id}>
                                                  <span className="tm-inline-time">{tInfo.primary}</span>
                                                  <span aria-hidden="true">{stopTypeMeta(stop).icon}</span>
                                                  <span className="tm-inline-title">{stop.text}</span>
                                                  {tInfo.detail && <span className="tm-tz-inline">{tInfo.detail}</span>}
                                                  {stop.status === 'tobook' && (
                                                    <span className="tm-status is-tobook">To book</span>
                                                  )}
                                                </li>
                                              );
                                            })}
                                          </ul>
                                        </div>
                                      )}
                                    </div>
                                    <div className="tm-day-right">
                                      {hasFlight && <span className="tm-tag is-flight">✈ Flight</span>}
                                      {toBookCount > 0 && (
                                        <span className="tm-tag is-warn">{toBookCount} to book</span>
                                      )}
                                      <span className="tm-day-count">{day.stops.length} items</span>
                                      <span className="tm-chevron" aria-hidden="true">›</span>
                                    </div>
                                  </div>
                                </button>
                              </li>
                            );
                          })}
                          {leg.days.length === 0 && (
                            <li className="tm-empty-row">No days assigned to this leg yet.</li>
                          )}
                        </ul>
                      </section>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ================= ITINERARY ================= */}
            {section === 'itinerary' && (
              <div className="tm-itinerary">
                <div className="tm-itin-toolbar">
                  <div className="tm-itin-status">
                    <strong>{selectionSummary}</strong>
                    {!showAllDays && allDays.length > 0 && (
                      <button
                        type="button"
                        className="tm-link-inline"
                        onClick={() => { setShowAllDays(true); setRangeMode(false); }}
                      >
                        Show all
                      </button>
                    )}
                  </div>

                  <div className="tm-itin-actions">
                    {allDays.length > 0 && (
                      <button
                        type="button"
                        className={`tm-tool-btn${pickerOpen ? ' is-active' : ''}`}
                        aria-expanded={pickerOpen}
                        onClick={() => setPickerOpen((v) => !v)}
                      >
                        Select range {pickerOpen ? '▴' : '▾'}
                      </button>
                    )}
                    {selectedItineraryDays.length > 1 && (
                      <div className="tm-btn-group" role="group" aria-label="Collapse or expand visible days">
                        <button type="button" className="tm-tool-btn" disabled={!anyVisibleExpanded} onClick={collapseVisibleDays}>
                          Collapse all
                        </button>
                        <button type="button" className="tm-tool-btn" disabled={!anyVisibleCollapsed} onClick={expandVisibleDays}>
                          Expand all
                        </button>
                      </div>
                    )}
                    <button
                      type="button"
                      className={`tm-tool-btn${showIdeasPane ? ' is-active' : ''}`}
                      aria-pressed={showIdeasPane}
                      onClick={() => setShowIdeasPane((v) => !v)}
                    >
                      {showIdeasPane ? `Hide ideas (${vm.ideas.length})` : `Show ideas (${vm.ideas.length})`}
                    </button>
                    {canEdit && (
                      <>
                        <button
                          type="button"
                          className={`tm-tool-btn${pinEditControls ? ' is-active' : ''}`}
                          onClick={() => setPinEditControls((v) => !v)}
                        >
                          {pinEditControls ? 'Edit controls: On' : 'Edit controls'}
                        </button>
                        <button
                          type="button"
                          className="tm-btn-primary tm-btn-sm"
                          onClick={() => setEditingDayState({ isNew: true, suggestedDate: nextNewDayDate, ripple: true })}
                        >
                          + Add day
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {pickerOpen && allDays.length > 0 && (
                  <section className="tm-card tm-picker-panel" aria-label="Day selection panel">
                    <div className="tm-picker-row">
                      <span className="tm-picker-label">By leg</span>
                      <div className="tm-picker-pills">
                        <button
                          type="button"
                          className={`tm-ribbon-pill${showAllDays ? ' is-active' : ''}`}
                          onClick={() => { setShowAllDays(true); setRangeMode(false); }}
                        >
                          All days ({allDays.length})
                        </button>
                        {vm.legSections.filter((l) => l.days.length > 0).map((leg) => (
                          <button
                            key={leg.id}
                            type="button"
                            className={`tm-ribbon-pill${isLegSelected(leg) ? ' is-active' : ''}`}
                            onClick={() => selectByLeg(leg)}
                          >
                            <i className="tm-dot" style={{ background: leg.color }} />
                            <span>{leg.name}</span>
                            <small>{leg.days.length}d</small>
                          </button>
                        ))}
                      </div>
                      <button type="button" className="tm-picker-done" onClick={() => setPickerOpen(false)}>Hide</button>
                    </div>

                    <div className="tm-picker-row">
                      <span className="tm-picker-label">By day</span>
                      <div className="tm-slider-shell">
                        <button type="button" className="tm-slide-arrow" onClick={() => slideDays(-1)} aria-label="Scroll days left">‹</button>
                        <div className="tm-day-slider" ref={daySliderRef}>
                          {allDays.map(({ day, leg }) => {
                            const isSelected = !showAllDays && selectedDayIds.includes(day.id);
                            return (
                              <button
                                key={day.id}
                                type="button"
                                className={`tm-day-pill${isSelected ? ' is-active' : ''}`}
                                style={{
                                  borderTopColor: leg.color,
                                  ...(isSelected ? { borderColor: leg.color, background: leg.tint } : {}),
                                }}
                                onClick={(e) => handleDayPillClick(day.id, e)}
                              >
                                <span className="tm-day-pill-top">
                                  <i className="tm-dot" style={{ background: leg.color }} />
                                  <strong>D{day.num}</strong>
                                </span>
                                <small>{day.shortDate}</small>
                              </button>
                            );
                          })}
                        </div>
                        <button type="button" className="tm-slide-arrow" onClick={() => slideDays(1)} aria-label="Scroll days right">›</button>
                      </div>
                    </div>

                    <div className="tm-picker-foot">
                      <span className="tm-picker-hint">
                        Click a day · <strong>Shift+click</strong> for a range · <strong>Ctrl/Cmd+click</strong> to multi-select
                      </span>
                      <button
                        type="button"
                        className={`tm-range-toggle${rangeMode ? ' is-active' : ''}`}
                        onClick={() => setRangeMode((v) => !v)}
                      >
                        {rangeMode ? 'Pick end day… (click to cancel)' : 'Pick range by clicking'}
                      </button>
                    </div>
                  </section>
                )}

                <div className={`tm-itin-workspace${showIdeasPane ? ' has-ideas' : ''}`}>
                  <div className="tm-itin-days-pane">
                    <div className={`tm-itin-stack${pinEditControls ? ' is-editing' : ''}`}>
                      {selectedLegGroups.length === 0 && (
                        <div className="tm-card" style={{ padding: 32, textAlign: 'center' }}>
                          <p className="tm-muted">No days yet. Click "+ Add day" to start building your itinerary.</p>
                        </div>
                      )}

                      {selectedLegGroups.map(({ leg, days: legDays }) => {
                        const isLegCollapsed = Boolean(collapsedLegIds[leg.id]);
                        const legAllDaysCollapsed = legDays.every((d) => Boolean(collapsedDayIds[d.id]));

                        const toggleLegDays = (collapse) => {
                          if (isLegCollapsed && !collapse) {
                            setCollapsedLegIds((prev) => { const n = { ...prev }; delete n[leg.id]; return n; });
                          }
                          setCollapsedDayIds((prev) => {
                            const next = { ...prev };
                            for (const d of legDays) {
                              if (collapse) next[d.id] = true;
                              else delete next[d.id];
                            }
                            return next;
                          });
                        };

                        return (
                          <div key={leg.id} className="tm-itin-leg-group">
                            <div
                              className={`tm-leg-bar${isLegCollapsed ? ' is-collapsed' : ''}`}
                              style={{ borderLeftColor: leg.color }}
                            >
                              <button
                                type="button"
                                className="tm-leg-fold-btn"
                                aria-expanded={!isLegCollapsed}
                                onClick={() => toggleLegCollapsed(leg.id)}
                              >
                                <span className="tm-fold-chevron" aria-hidden="true">{isLegCollapsed ? '▸' : '▾'}</span>
                                <span className="tm-leg-kicker" style={{ color: leg.color }}>Leg</span>
                                <strong className="tm-leg-bar-name">{leg.name}</strong>
                                <span className="tm-muted">
                                  {leg.dates ? `${leg.dates} · ` : ''}{legDays.length} {legDays.length === 1 ? 'day' : 'days'}
                                </span>
                                {leg.stay && <span className="tm-leg-bar-stay">🛏 {leg.stay}</span>}
                              </button>

                              {!isLegCollapsed && legDays.length > 1 && (
                                <button
                                  type="button"
                                  className="tm-link-inline"
                                  onClick={() => toggleLegDays(!legAllDaysCollapsed)}
                                >
                                  {legAllDaysCollapsed ? 'Expand days' : 'Collapse days'}
                                </button>
                              )}
                            </div>

                            {!isLegCollapsed && (
                              <div className="tm-itin-leg-days" style={{ borderLeftColor: `${leg.color}38` }}>
                                {legDays.map((day) => {
                                  const draft = quickAddByDay[day.id] || { time: '', title: '', typeId: 'activity' };
                                  const isCollapsed = Boolean(collapsedDayIds[day.id]);
                                  const dayZ = vm.zones.days[day.id];
                                  const dayZoneTag = dayZ?.zones?.length
                                    ? dayZ.zones.map((z) => zoneShortAbbr(z, day.date)).filter((v, i, a) => a.indexOf(v) === i).join(' → ')
                                    : '';

                                  return (
                                    <section
                                      key={day.id}
                                      className={`tm-card tm-itin-card${isCollapsed ? ' is-collapsed' : ''}${dragOverDayId === day.id ? ' is-drop-target' : ''}`}
                                      onDragOver={(e) => {
                                        if (!showIdeasPane || !canEdit) return;
                                        e.preventDefault();
                                        if (dragOverDayId !== day.id) setDragOverDayId(day.id);
                                      }}
                                      onDragLeave={(e) => {
                                        if (!e.currentTarget.contains(e.relatedTarget)) {
                                          setDragOverDayId((cur) => (cur === day.id ? null : cur));
                                        }
                                      }}
                                      onDrop={(e) => {
                                        e.preventDefault();
                                        setDragOverDayId(null);
                                        if (!canEdit) return;
                                        const ideaId = Number(e.dataTransfer.getData('text/trip-idea-id'));
                                        const idea = vm.ideas.find((i) => i.id === ideaId);
                                        if (idea) handleScheduleIdeaToDay(idea, day.id);
                                      }}
                                    >
                                      <header className="tm-itin-head">
                                        <button
                                          type="button"
                                          className="tm-day-fold-btn"
                                          aria-expanded={!isCollapsed}
                                          onClick={() => toggleDayCollapsed(day.id)}
                                        >
                                          <span className="tm-fold-chevron" aria-hidden="true">{isCollapsed ? '▸' : '▾'}</span>
                                          <div>
                                            <span className="tm-day-kicker">
                                              Day {day.num} · {day.weekday}, {day.shortDate}
                                              {dayZoneTag && <span className="tm-day-tz-badge">{dayZoneTag}</span>}
                                            </span>
                                            <h2>{day.title || `Day ${day.num}`}</h2>
                                          </div>
                                        </button>

                                        <div className="tm-day-crud">
                                          {isCollapsed && <span className="tm-day-count">{day.stops.length} items</span>}
                                          {day.stay && <span className="tm-leg-stay-pill">🛏 {day.stay}</span>}
                                          {canEdit && !isCollapsed && (
                                            <button
                                              type="button"
                                              className="tm-tool-btn"
                                              onClick={() => setEditingActivityState({ day, leg, stop: null, isIdea: false })}
                                            >
                                              + Add item
                                            </button>
                                          )}
                                          {canEdit && (
                                            <div className="tm-menu-wrap" onClick={(e) => e.stopPropagation()}>
                                              <button
                                                type="button"
                                                className="tm-more-btn"
                                                aria-label={`Day ${day.num} actions`}
                                                onClick={() => setOpenDayMenuId(openDayMenuId === day.id ? null : day.id)}
                                              >
                                                ⋯
                                              </button>
                                              {openDayMenuId === day.id && (
                                                <div className="tm-dropdown" role="menu">
                                                  <button
                                                    type="button"
                                                    role="menuitem"
                                                    onClick={() => {
                                                      setOpenDayMenuId(null);
                                                      setEditingDayState({ day, leg, isNew: false });
                                                    }}
                                                  >
                                                    Edit day details & notes
                                                  </button>
                                                  <button
                                                    type="button"
                                                    role="menuitem"
                                                    onClick={() => {
                                                      setOpenDayMenuId(null);
                                                      setEditingDayState({
                                                        isNew: true,
                                                        leg,
                                                        insertPosition: 'before',
                                                        suggestedDate: day.date,
                                                        ripple: true,
                                                      });
                                                    }}
                                                  >
                                                    Insert day before
                                                  </button>
                                                  <button
                                                    type="button"
                                                    role="menuitem"
                                                    onClick={() => {
                                                      setOpenDayMenuId(null);
                                                      setEditingDayState({
                                                        isNew: true,
                                                        leg,
                                                        insertPosition: 'after',
                                                        suggestedDate: addDaysIso(day.date, 1),
                                                        ripple: true,
                                                      });
                                                    }}
                                                  >
                                                    Insert day after
                                                  </button>
                                                  <hr />
                                                  <button
                                                    type="button"
                                                    role="menuitem"
                                                    className="is-danger"
                                                    onClick={() => handleDeleteDay(day.id)}
                                                  >
                                                    Delete day
                                                  </button>
                                                </div>
                                              )}
                                            </div>
                                          )}
                                        </div>
                                      </header>

                                      {!isCollapsed && (
                                        <>
                                          {day.notes && <p className="tm-notes-text tm-itin-notes">{day.notes}</p>}

                                          <ul className="tm-timeline">
                                            {day.stops.map((stop, itemIdx) => {
                                              const meta = stopTypeMeta(stop);
                                              const sub = stopSubtitle(stop);
                                              const tInfo = formatStopTimeSummary(stop, day, vm.zones.stops[stop.id], dayZ);
                                              return (
                                                <li key={stop.id} className="tm-timeline-item">
                                                  <button
                                                    type="button"
                                                    className="tm-timeline-main"
                                                    onClick={() => canEdit && setEditingActivityState({ day, leg, stop, isIdea: false })}
                                                    title={canEdit ? 'Click to edit activity' : undefined}
                                                  >
                                                    <span className="tm-timeline-time">{tInfo.primary}</span>
                                                    <span className="tm-timeline-icon" aria-hidden="true">{meta.icon}</span>
                                                    <div className="tm-timeline-body">
                                                      <div className="tm-peek-title-row">
                                                        <strong>{stop.text}</strong>
                                                        {tInfo.detail && <span className="tm-tz-inline">{tInfo.detail}</span>}
                                                        {stop.status && stop.status !== 'no_booking' && (
                                                          <span className={`tm-status is-${stop.status}`}>{STATUS_LABEL[stop.status] || stop.status}</span>
                                                        )}
                                                      </div>
                                                      {sub && <span className="tm-muted">{sub}</span>}
                                                    </div>
                                                  </button>

                                                  {canEdit && (
                                                    <div className="tm-item-crud">
                                                      <button
                                                        type="button"
                                                        disabled={itemIdx === 0 || saving}
                                                        title="Move up"
                                                        onClick={() => handleMoveStop(stop.id, 'up')}
                                                      >
                                                        ↑
                                                      </button>
                                                      <button
                                                        type="button"
                                                        disabled={itemIdx === day.stops.length - 1 || saving}
                                                        title="Move down"
                                                        onClick={() => handleMoveStop(stop.id, 'down')}
                                                      >
                                                        ↓
                                                      </button>
                                                      <button
                                                        type="button"
                                                        title="Edit"
                                                        onClick={() => setEditingActivityState({ day, leg, stop, isIdea: false })}
                                                      >
                                                        Edit
                                                      </button>
                                                      <button
                                                        type="button"
                                                        className="is-danger"
                                                        title="Delete"
                                                        disabled={saving}
                                                        onClick={() => handleDeleteStop(stop.id)}
                                                      >
                                                        ×
                                                      </button>
                                                    </div>
                                                  )}
                                                </li>
                                              );
                                            })}
                                            {day.stops.length === 0 && (
                                              <li className="tm-empty-row">No activities yet{canEdit ? ' — add one below or drag an idea here.' : '.'}</li>
                                            )}
                                          </ul>

                                          {canEdit && (
                                            <form className="tm-quick-add" onSubmit={(e) => handleQuickAdd(day.id, e)}>
                                              <select
                                                aria-label="Activity type"
                                                value={draft.typeId || 'activity'}
                                                onChange={(e) => setQuickAddByDay((p) => ({ ...p, [day.id]: { ...draft, typeId: e.target.value } }))}
                                              >
                                                {STOP_TYPE_OPTIONS.map((k) => (
                                                  <option key={k.id} value={k.id}>{k.icon} {k.label}</option>
                                                ))}
                                              </select>
                                              <input
                                                type="text"
                                                className="tm-qa-time"
                                                placeholder="HH:MM"
                                                value={draft.time || ''}
                                                onChange={(e) => setQuickAddByDay((p) => ({ ...p, [day.id]: { ...draft, time: e.target.value } }))}
                                              />
                                              <input
                                                type="text"
                                                className="tm-qa-title"
                                                placeholder="Quick add activity, flight, or meal…"
                                                value={draft.title || ''}
                                                onChange={(e) => setQuickAddByDay((p) => ({ ...p, [day.id]: { ...draft, title: e.target.value } }))}
                                              />
                                              <button type="submit" className="tm-tool-btn" disabled={saving || !(draft.title || '').trim()}>
                                                Add
                                              </button>
                                            </form>
                                          )}
                                        </>
                                      )}
                                    </section>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {showIdeasPane && (
                    <aside className="tm-itin-ideas-pane" aria-label="Trip ideas panel">
                      <div className="tm-ideas-pane-head">
                        <div>
                          <h3>Ideas Pool</h3>
                          <span className="tm-muted">{filteredIdeas.length} of {vm.ideas.length} · Click Add or drag onto a day</span>
                        </div>
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                          {canEdit && (
                            <button
                              type="button"
                              className="tm-tool-btn tm-btn-xs"
                              onClick={() => setEditingActivityState({ isIdea: true, stop: null })}
                            >
                              + Idea
                            </button>
                          )}
                          <button type="button" className="tm-close-btn" aria-label="Hide ideas panel" onClick={() => setShowIdeasPane(false)}>
                            ×
                          </button>
                        </div>
                      </div>

                      <div className="tm-ideas-pane-controls">
                        <input
                          type="search"
                          className="tm-ideas-search"
                          placeholder="Filter ideas…"
                          value={ideaSearch}
                          onChange={(e) => setIdeaSearch(e.target.value)}
                        />
                        <div className="tm-ideas-leg-pills" role="group" aria-label="Filter ideas by leg">
                          <button
                            type="button"
                            className={`tm-idea-pill${ideaLegFilter === 'all' ? ' is-active' : ''}`}
                            onClick={() => setIdeaLegFilter('all')}
                          >
                            All
                          </button>
                          {ideaLegOptions.map((legName) => (
                            <button
                              key={legName}
                              type="button"
                              className={`tm-idea-pill${ideaLegFilter === legName ? ' is-active' : ''}`}
                              onClick={() => setIdeaLegFilter(legName)}
                            >
                              {legName}
                            </button>
                          ))}
                        </div>
                      </div>

                      <div className="tm-ideas-pane-list">
                        {filteredIdeas.map((idea) => {
                          const targetDayId = getDefaultTargetDayId(idea);
                          return (
                            <article
                              key={idea.id}
                              className="tm-card tm-idea-pane-card"
                              draggable={canEdit}
                              onDragStart={(e) => {
                                e.dataTransfer.setData('text/trip-idea-id', String(idea.id));
                                e.dataTransfer.effectAllowed = 'move';
                              }}
                            >
                              <div className="tm-idea-meta">
                                <span className="tm-chip-subtle">{idea.legName}</span>
                                {idea.cat && <span className="tm-muted">{idea.cat}</span>}
                                {canEdit && (
                                  <button
                                    type="button"
                                    className="tm-idea-remove"
                                    title="Delete idea"
                                    onClick={() => handleDeleteStop(idea.id)}
                                  >
                                    ×
                                  </button>
                                )}
                              </div>
                              <h4
                                style={{ cursor: canEdit ? 'pointer' : 'default' }}
                                onClick={() => canEdit && setEditingActivityState({ isIdea: true, stop: idea })}
                              >
                                {idea.text}
                              </h4>
                              {idea.description && <p className="tm-muted">{idea.description}</p>}

                              {canEdit && allDays.length > 0 && (
                                <div className="tm-idea-add-row">
                                  <select
                                    aria-label={`Target day for ${idea.text}`}
                                    value={targetDayId}
                                    onChange={(e) => setIdeaTargetDayById((prev) => ({ ...prev, [idea.id]: e.target.value }))}
                                  >
                                    {allDays.map(({ day, leg }) => (
                                      <option key={day.id} value={day.id}>
                                        Day {day.num} ({day.shortDate}) · {leg.name}
                                      </option>
                                    ))}
                                  </select>
                                  <button
                                    type="button"
                                    className="tm-btn-primary tm-btn-xs"
                                    disabled={saving || !targetDayId}
                                    onClick={() => handleScheduleIdeaToDay(idea, targetDayId)}
                                  >
                                    + Add
                                  </button>
                                </div>
                              )}
                            </article>
                          );
                        })}
                        {filteredIdeas.length === 0 && (
                          <div className="tm-empty-row">No unscheduled ideas yet.</div>
                        )}
                      </div>
                    </aside>
                  )}
                </div>
              </div>
            )}

            {/* ================= IDEAS TAB ================= */}
            {section === 'ideas' && (
              <div className="tm-section-stack">
                <div className="tm-itin-toolbar">
                  <div>
                    <h2 style={{ margin: '0 0 2px', fontSize: 19 }}>Ideas Pool</h2>
                    <p className="tm-muted" style={{ margin: 0 }}>Unscheduled places and experiences — schedule them into any day when ready.</p>
                  </div>
                  {canEdit && (
                    <button
                      type="button"
                      className="tm-btn-primary tm-btn-sm"
                      onClick={() => setEditingActivityState({ isIdea: true, stop: null })}
                    >
                      + Add idea
                    </button>
                  )}
                </div>

                {vm.ideas.length === 0 ? (
                  <div className="tm-card" style={{ padding: 32, textAlign: 'center' }}>
                    <p className="tm-muted">No ideas saved yet.</p>
                  </div>
                ) : (
                  <div className="tm-ideas-grid">
                    {vm.ideas.map((idea) => {
                      const targetDayId = getDefaultTargetDayId(idea);
                      return (
                        <article key={idea.id} className="tm-card tm-idea-card">
                          <div className="tm-idea-meta">
                            <span className="tm-chip-subtle">{idea.legName}</span>
                            {idea.cat && <span className="tm-muted">{idea.cat}</span>}
                            {canEdit && (
                              <button
                                type="button"
                                className="tm-idea-remove"
                                title="Delete idea"
                                onClick={() => handleDeleteStop(idea.id)}
                              >
                                ×
                              </button>
                            )}
                          </div>
                          <h3
                            style={{ cursor: canEdit ? 'pointer' : 'default' }}
                            onClick={() => canEdit && setEditingActivityState({ isIdea: true, stop: idea })}
                          >
                            {idea.text}
                          </h3>
                          {idea.description && <p className="tm-muted">{idea.description}</p>}
                          {canEdit && allDays.length > 0 && (
                            <div className="tm-idea-add-row" style={{ marginTop: 10 }}>
                              <select
                                value={targetDayId}
                                onChange={(e) => setIdeaTargetDayById((prev) => ({ ...prev, [idea.id]: e.target.value }))}
                              >
                                {allDays.map(({ day, leg }) => (
                                  <option key={day.id} value={day.id}>
                                    Day {day.num} ({day.shortDate}) · {leg.name}
                                  </option>
                                ))}
                              </select>
                              <button
                                type="button"
                                className="tm-btn-primary tm-btn-xs"
                                disabled={saving || !targetDayId}
                                onClick={() => handleScheduleIdeaToDay(idea, targetDayId)}
                              >
                                Schedule
                              </button>
                            </div>
                          )}
                        </article>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* ================= BOOKINGS TAB ================= */}
            {section === 'bookings' && (
              <div className="tm-section-stack">
                <div className="tm-itin-toolbar">
                  <div className="tm-readiness-strip">
                    <div className="tm-stat"><strong>{bookingCounts.confirmed}</strong><span>Confirmed</span></div>
                    <div className="tm-stat"><strong>{bookingCounts.booked}</strong><span>Booked</span></div>
                    <div className="tm-stat is-warn"><strong>{bookingCounts.tobook}</strong><span>To book</span></div>
                  </div>
                  {canEdit && (
                    <button type="button" className="tm-btn-primary tm-btn-sm" onClick={() => setShowCreateLodging(true)}>
                      + Add stay
                    </button>
                  )}
                </div>

                {vm.bookings.length === 0 ? (
                  <div className="tm-card" style={{ padding: 32, textAlign: 'center' }}>
                    <p className="tm-muted">No bookings or stays yet. Add stays or mark itinerary items as To book / Booked / Confirmed.</p>
                  </div>
                ) : (
                  ['Stays', 'Flights & Travel', 'Activities & Events'].map((group) => {
                    const rows = vm.bookings.filter((b) => b.group === group);
                    if (!rows.length) return null;
                    return (
                      <section key={group} className="tm-card tm-table-card">
                        <h3 className="tm-table-title">{group}</h3>
                        <ul className="tm-booking-list">
                          {rows.map((b) => (
                            <li key={b.key} className="tm-booking-row">
                              <div>
                                <strong>{b.title}</strong>
                                <span className="tm-muted">
                                  {b.dates}
                                  {b.conf ? ` · Conf # ${b.conf}` : ''}
                                </span>
                              </div>
                              <div className="tm-booking-right">
                                {b.price && <span className="tm-price">{b.price}</span>}
                                {canEdit ? (
                                  <select
                                    className={`tm-status-select is-${b.status}`}
                                    aria-label={`Booking status for ${b.title}`}
                                    value={b.status}
                                    onChange={(e) => handleUpdateBookingStatus(b, e.target.value)}
                                  >
                                    {STATUS_OPTIONS.map((opt) => (
                                      <option key={opt.id} value={opt.id}>{opt.label}</option>
                                    ))}
                                  </select>
                                ) : (
                                  <span className={`tm-status is-${b.status}`}>{STATUS_LABEL[b.status] || b.status}</span>
                                )}
                              </div>
                            </li>
                          ))}
                        </ul>
                      </section>
                    );
                  })
                )}
              </div>
            )}

            {/* ================= DOCUMENTS TAB ================= */}
            {section === 'documents' && (
              <div className="tm-section-stack">
                <div className="tm-section-intro">
                  <h2>Trip Documents</h2>
                  <p className="tm-muted">All files, links, and media attached across your stays and itinerary stops.</p>
                </div>
                {vm.documents.length === 0 ? (
                  <div className="tm-card" style={{ padding: 32, textAlign: 'center' }}>
                    <p className="tm-muted">No documents attached yet.</p>
                  </div>
                ) : (
                  <div className="tm-docs-grid">
                    {vm.documents.map((doc) => (
                      <a
                        key={doc.id}
                        href={doc.url || '#'}
                        target={doc.url ? '_blank' : undefined}
                        rel="noreferrer"
                        className="tm-card tm-doc-card"
                        style={{ textDecoration: 'none', color: 'inherit' }}
                        onClick={(e) => { if (!doc.url) e.preventDefault(); }}
                      >
                        <div className="tm-doc-top">
                          <span className="tm-chip-subtle">{doc.category}</span>
                          <span className="tm-muted">{doc.kind}</span>
                        </div>
                        <div className="tm-doc-icon" aria-hidden="true">
                          {doc.kind === 'picture' ? '🖼' : doc.kind === 'location' ? '📍' : doc.kind === 'url' ? '🔗' : '📄'}
                        </div>
                        <strong className="tm-doc-name">{doc.name}</strong>
                        <span className="tm-muted">{doc.linked}</span>
                        {doc.note && <p className="tm-muted">{doc.note}</p>}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </main>

      {/* ================= DRAWERS & MODALS ================= */}
      <DayPeekDrawer
        day={peek?.day}
        leg={peek?.leg}
        zones={vm?.zones}
        canEdit={canEdit}
        onClose={() => setPeek(null)}
        onOpenItinerary={jumpToItinerary}
        onEditDay={(day, leg) => {
          setPeek(null);
          setEditingDayState({ day, leg, isNew: false });
        }}
      />

      {editingActivityState && (
        <ActivityDrawer
          key={editingActivityState.stop?.id || 'new-stop'}
          state={editingActivityState}
          legs={vm?.legs || []}
          zones={vm?.zones}
          saving={saving}
          onClose={() => setEditingActivityState(null)}
          onSave={handleSaveStop}
          onDelete={handleDeleteStop}
          onMoveToIdeas={handleMoveStopToIdeas}
        />
      )}

      {editingDayState && (
        <DayDrawer
          key={editingDayState.day?.id || 'new-day'}
          state={editingDayState}
          legs={vm?.legs || []}
          lodgings={rawTrip?.lodgings || []}
          zones={vm?.zones}
          defaultDate={nextNewDayDate}
          saving={saving}
          onClose={() => setEditingDayState(null)}
          onSave={handleSaveDay}
          onDelete={handleDeleteDay}
        />
      )}

      {showEditTrip && (
        <SimpleModal
          title="Edit Trip"
          submitLabel="Save Trip"
          saving={saving}
          onClose={() => setShowEditTrip(false)}
          onSubmit={handleEditTrip}
        >
          <label className="tm-field">
            <span>Title</span>
            <input type="text" required value={tripForm.title} onChange={(e) => setTripForm((p) => ({ ...p, title: e.target.value }))} />
          </label>
          <label className="tm-field">
            <span>Description</span>
            <input type="text" value={tripForm.description} onChange={(e) => setTripForm((p) => ({ ...p, description: e.target.value }))} />
          </label>
          <div className="tm-field-row">
            <label className="tm-field">
              <span>Start date</span>
              <input type="date" value={tripForm.start_date} onChange={(e) => setTripForm((p) => ({ ...p, start_date: e.target.value }))} />
            </label>
            <label className="tm-field">
              <span>End date</span>
              <input type="date" value={tripForm.end_date} onChange={(e) => setTripForm((p) => ({ ...p, end_date: e.target.value }))} />
            </label>
          </div>
          <TimeZoneField
            label="Default time zone"
            value={tripForm.timezone}
            inherited={localZone()}
            inheritedNote="your browser zone"
            date={tripForm.start_date}
            onChange={(z) => setTripForm((p) => ({ ...p, timezone: z }))}
          />
        </SimpleModal>
      )}

      {showCreateLeg && (
        <SimpleModal
          title="Add Trip Leg"
          submitLabel="Add Leg"
          saving={saving}
          onClose={() => setShowCreateLeg(false)}
          onSubmit={handleCreateLeg}
        >
          <label className="tm-field">
            <span>Leg name</span>
            <input type="text" required autoFocus placeholder="e.g., Chiang Mai" value={legForm.name} onChange={(e) => setLegForm((p) => ({ ...p, name: e.target.value }))} />
          </label>
          <label className="tm-field">
            <span>Region / Location</span>
            <input type="text" placeholder="e.g., Northern Thailand" value={legForm.location} onChange={(e) => setLegForm((p) => ({ ...p, location: e.target.value }))} />
          </label>
          <TimeZoneField
            label="Time zone"
            value={legForm.timezone}
            inherited={vm?.zones?.tripZone || localZone()}
            inheritedNote="from trip"
            date={rawTrip?.start_date}
            onChange={(z) => setLegForm((p) => ({ ...p, timezone: z }))}
          />
          <label className="tm-field">
            <span>Summary / Notes</span>
            <textarea rows={3} placeholder="What this leg is about…" value={legForm.notes} onChange={(e) => setLegForm((p) => ({ ...p, notes: e.target.value }))} />
          </label>
        </SimpleModal>
      )}

      {showCreateLodging && (
        <SimpleModal
          title="Add Stay / Lodging"
          submitLabel="Add Stay"
          saving={saving}
          onClose={() => setShowCreateLodging(false)}
          onSubmit={handleCreateLodging}
        >
          <label className="tm-field">
            <span>Hotel / Stay name</span>
            <input type="text" required autoFocus placeholder="e.g., Capella Bangkok" value={lodgingForm.name} onChange={(e) => setLodgingForm((p) => ({ ...p, name: e.target.value }))} />
          </label>
          <div className="tm-field-row">
            <label className="tm-field">
              <span>Status</span>
              <select value={lodgingForm.status} onChange={(e) => setLodgingForm((p) => ({ ...p, status: e.target.value }))}>
                {STATUS_OPTIONS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
            </label>
            <label className="tm-field">
              <span>Confirmation #</span>
              <input type="text" value={lodgingForm.confirmation} onChange={(e) => setLodgingForm((p) => ({ ...p, confirmation: e.target.value }))} />
            </label>
          </div>
          <div className="tm-field-row">
            <label className="tm-field">
              <span>Price</span>
              <input type="number" step="0.01" value={lodgingForm.price} onChange={(e) => setLodgingForm((p) => ({ ...p, price: e.target.value }))} />
            </label>
            <label className="tm-field">
              <span>Currency</span>
              <input type="text" maxLength={3} value={lodgingForm.currency} onChange={(e) => setLodgingForm((p) => ({ ...p, currency: e.target.value }))} />
            </label>
          </div>
          <label className="tm-field">
            <span>Address</span>
            <input type="text" value={lodgingForm.address} onChange={(e) => setLodgingForm((p) => ({ ...p, address: e.target.value }))} />
          </label>
        </SimpleModal>
      )}

      {showShareModal && rawTrip && (
        <ShareTripModal
          trip={rawTrip}
          onClose={() => setShowShareModal(false)}
          onChanged={() => loadTrip(rawTrip.id, { silent: true })}
        />
      )}

      {showCommentsDrawer && rawTrip && (
        <CommentsDrawer
          trip={rawTrip}
          scope={commentScope}
          currentUser={user}
          canEdit={canEdit}
          isOwner={isOwner}
          onClose={() => setShowCommentsDrawer(false)}
          onChangeScope={setCommentScope}
          onJumpToTarget={(target) => {
            setShowCommentsDrawer(false);
            if (target?.dayId) jumpToItinerary(target.dayId);
          }}
          onReload={() => loadTrip(rawTrip.id, { silent: true })}
        />
      )}
    </div>
  );
}
