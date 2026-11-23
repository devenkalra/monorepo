import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  dayDiff, epochToZoned, localZone, offsetMinutes, zoneAbbr, zoneCity, zonedToEpoch,
} from '@bldrdojo/timezones';

const HOUR_PX = 44;
const DAY_MIN = 24 * 60;
const POINT_MIN = 30;
const GUTTER = '3.5rem';
const SPANS = [
  { id: '3', label: '3 days' },
  { id: '7', label: 'Week' },
  { id: 'all', label: 'All' },
];

export function addDays(date, n) {
  const d = new Date(`${date}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function clockMin(value) {
  if (!value) return null;
  const [h, m] = String(value).split(':').map(Number);
  return Number.isFinite(h) && Number.isFinite(m) ? h * 60 + m : null;
}

function clockText(minutes) {
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
}

export function formatMinutes(total) {
  const h = Math.floor(total / 60) % 24;
  const m = total % 60;
  const h12 = h % 12 || 12;
  return `${h12}${m ? `:${String(m).padStart(2, '0')}` : ''} ${h >= 12 ? 'PM' : 'AM'}`;
}

function formatDuration(minutes) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return [h && `${h}h`, m && `${m}m`].filter(Boolean).join(' ') || '0m';
}

function dateLabel(date, opts = { weekday: 'short', month: 'short', day: 'numeric' }) {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString(undefined, { ...opts, timeZone: 'UTC' });
}

function abbrOn(zone, date) {
  return zoneAbbr(zone, zonedToEpoch(date, '12:00', zone));
}

function ZoneChangeIcon({ title }) {
  return (
    <span className="trip-cal-ico is-shift" title={title} aria-label={title}>
      <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
        <path
          d="M13.2 8a5.2 5.2 0 1 1-1.4-3.6M13.5 2.5v2.7h-2.7M8 5.2V8l2 1.2"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

function OtherZoneIcon({ title }) {
  return (
    <span className="trip-cal-ico is-other-zone" title={title} aria-label={title}>
      <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
        <circle cx="8" cy="8" r="5.8" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <ellipse cx="8" cy="8" rx="2.7" ry="5.8" fill="none" stroke="currentColor" strokeWidth="1.3" />
        <path d="M2.5 8h11" fill="none" stroke="currentColor" strokeWidth="1.3" />
      </svg>
    </span>
  );
}

function spanZoneFlags(span, shownZone) {
  if (!span) return { changesZone: false, otherZone: false };
  const changesZone = Boolean(
    span.zone && span.arriveZone && (
      span.zone !== span.arriveZone
      || (span.t0 != null && span.t1 != null && offsetMinutes(span.zone, span.t0) !== offsetMinutes(span.arriveZone, span.t1))
    ),
  );
  if (shownZone) {
    return { changesZone, otherZone: Boolean(span.zone && span.zone !== shownZone) };
  }
  const dayZones = [span.inheritedZone, span.dayStartZone].filter(Boolean);
  const otherZone = Boolean(span.zone && dayZones.length && !dayZones.includes(span.zone));
  return { changesZone, otherZone };
}

function localTimeSummary(span) {
  if (!span || !span.zone) return '';
  if (span.untimed) return abbrOn(span.zone, span.origStartDate);
  const startAbbr = abbrOn(span.zone, span.origStartDate);
  if (span.point) return `${formatMinutes(span.origStartMin)} ${startAbbr}`;
  const endAbbr = abbrOn(span.arriveZone || span.zone, span.origEndDate);
  const shift = span.origOffset ? ` (${span.origOffset > 0 ? '+' : '−'}${Math.abs(span.origOffset)})` : '';
  if (span.arriveZone && span.arriveZone !== span.zone) {
    return `${formatMinutes(span.origStartMin)} ${startAbbr} → ${formatMinutes(span.origEndMin)} ${endAbbr}${shift}`;
  }
  return `${formatMinutes(span.origStartMin)} – ${formatMinutes(span.origEndMin)} ${startAbbr}${shift}`;
}

function finishSpan(span) {
  const s = { ...span };
  if (s.point) {
    s.endDate = s.startDate;
    s.endMin = Math.min(DAY_MIN, s.startMin + POINT_MIN);
    return s;
  }
  if (s.endMin === 0 && s.endDate > s.startDate) {
    s.endDate = addDays(s.endDate, -1);
    s.endMin = DAY_MIN;
  }
  s.long = s.duration >= DAY_MIN || dayDiff(s.startDate, s.endDate) >= 2;
  return s;
}

/**
 * Where an item sits on the calendar. With no `displayZone` it uses local wall-clock time: from its
 * start on its day to its end, which for travel is the local arrival (possibly a later date) and
 * otherwise start + duration. With a `displayZone` both ends are that zone's clock instead.
 */
export function stopSpan(stop, day, info, displayZone, dayInfo) {
  const startMin = clockMin(stop.start_time);
  const zone = info?.zone;
  const arriveZone = info?.arriveZone || zone;
  const meta = {
    zone, arriveZone, dayStartZone: dayInfo?.start, inheritedZone: info?.inherited, origStartDate: day.date,
  };
  if (startMin == null) return { untimed: true, startDate: day.date, endDate: day.date, ...meta };
  const duration = Number(stop.duration_minutes) || 0;
  const point = duration <= 0;
  const t0 = zone ? zonedToEpoch(day.date, clockText(startMin), zone) : null;
  let origEndDate = day.date;
  let origEndMin = startMin;
  let origOffset = 0;
  if (!point && stop.kind === 'travel' && info?.arrive) {
    origOffset = info.arrive.offset;
    origEndDate = addDays(day.date, origOffset);
    origEndMin = clockMin(info.arrive.time);
  } else if (!point) {
    const total = startMin + duration;
    origOffset = Math.floor(total / DAY_MIN);
    origEndDate = addDays(day.date, origOffset);
    origEndMin = total % DAY_MIN;
  }
  const base = {
    ...meta,
    duration, point, t0, t1: t0 == null ? null : t0 + duration * 60000,
    origStartMin: startMin, origEndDate, origEndMin, origOffset,
  };
  if (displayZone && t0 != null) {
    const s = epochToZoned(t0, displayZone);
    const e = epochToZoned(base.t1, displayZone);
    return finishSpan({
      ...base, startDate: s.date, startMin: clockMin(s.time), endDate: e.date, endMin: clockMin(e.time),
    });
  }
  const span = finishSpan({ ...base, startDate: day.date, startMin, endDate: origEndDate, endMin: origEndMin });
  // Westward across the date line the local arrival can read earlier than the departure; draw the real length.
  if (span.endDate < span.startDate || (span.endDate === span.startDate && span.endMin <= span.startMin)) {
    return { ...span, endDate: span.startDate, endMin: Math.min(DAY_MIN, startMin + Math.max(duration, POINT_MIN)), long: false };
  }
  return span;
}

/** Set of stop IDs whose timed spans overlap another timed stop on at least one calendar date. */
export function overlappingStopIds(days, zones) {
  const byDate = {};
  for (const day of days) {
    for (const stop of day.stops || []) {
      const span = stopSpan(stop, day, zones?.stops[stop.id], undefined, zones?.days[day.id]);
      if (span.untimed || span.long) continue;
      for (let d = span.startDate; d <= span.endDate; d = addDays(d, 1)) {
        const top = d === span.startDate ? span.startMin : 0;
        const bottom = d === span.endDate ? span.endMin : DAY_MIN;
        if (bottom > top) (byDate[d] ||= []).push({ id: stop.id, top, bottom });
      }
    }
  }
  const overlaps = new Set();
  for (const items of Object.values(byDate)) {
    items.sort((a, b) => a.top - b.top || a.bottom - b.bottom);
    for (let i = 0; i < items.length; i += 1) {
      for (let j = i + 1; j < items.length && items[j].top < items[i].bottom; j += 1) {
        if (items[j].id !== items[i].id) {
          overlaps.add(items[i].id);
          overlaps.add(items[j].id);
        }
      }
    }
  }
  return overlaps;
}

/** { 'YYYY-MM-DD': [{ stop, day, span }] } for items that started on an earlier day and are still going. */
export function continuingStops(days, zones) {
  const out = {};
  for (const day of days) {
    for (const stop of day.stops || []) {
      const span = stopSpan(stop, day, zones?.stops[stop.id]);
      if (span.untimed) continue;
      for (let d = addDays(span.startDate, 1); d <= span.endDate; d = addDays(d, 1)) {
        (out[d] ||= []).push({ stop, day, span });
      }
    }
  }
  return out;
}

function sortedStops(day) {
  return [...(day.stops || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id));
}

function layoutColumns(items) {
  const sorted = [...items].sort((a, b) => a.top - b.top || b.bottom - a.bottom);
  let cluster = [];
  let clusterEnd = -1;
  const finish = () => {
    const cols = Math.max(...cluster.map((i) => i.col)) + 1;
    cluster.forEach((i) => { i.cols = cols; });
  };
  for (const item of sorted) {
    if (cluster.length && item.top >= clusterEnd) {
      finish();
      cluster = [];
      clusterEnd = -1;
    }
    const used = new Set(cluster.filter((c) => c.bottom > item.top).map((c) => c.col));
    let col = 0;
    while (used.has(col)) col += 1;
    item.col = col;
    cluster.push(item);
    clusterEnd = Math.max(clusterEnd, item.bottom);
  }
  if (cluster.length) finish();
  return sorted;
}

function layoutLanes(bars) {
  const lanes = [];
  const sorted = [...bars].sort((a, b) => a.from - b.from || (b.to - b.from) - (a.to - a.from));
  for (const bar of sorted) {
    let lane = lanes.findIndex((end) => end < bar.from);
    if (lane === -1) {
      lane = lanes.length;
      lanes.push(bar.to);
    } else {
      lanes[lane] = bar.to;
    }
    bar.lane = lane;
  }
  return sorted;
}

function stored(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function store(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode */
  }
}

export default function TripCalendar({ days, legs = [], zones, focusLegId = null, onClearFocusLeg, onOpenStop, onAddAt, onDropIdea }) {
  const [spanId, setSpanId] = useState(() => stored('trips.calendarSpan', window.innerWidth < 700 ? '3' : '7'));
  const [displayZone, setDisplayZone] = useState(() => stored('trips.calendarZone', ''));
  const [secondZone, setSecondZone] = useState(() => stored('trips.calendarSecondZone', ''));
  const [activeLegId, setActiveLegId] = useState(null);
  const [startIdx, setStartIdx] = useState(null);
  const [dropHint, setDropHint] = useState(null);
  const [now, setNow] = useState(() => Date.now());
  const scrollRef = useRef(null);

  useEffect(() => {
    if (focusLegId != null) {
      setActiveLegId(focusLegId);
      onClearFocusLeg?.();
    }
  }, [focusLegId, onClearFocusLeg]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(t);
  }, []);

  const myZone = localZone();
  const tripZone = zones?.tripZone || myZone;
  const zoneChoices = useMemo(() => {
    const seen = [tripZone, myZone];
    for (const info of Object.values(zones?.stops || {})) seen.push(info.zone, info.arriveZone);
    for (const info of Object.values(zones?.days || {})) seen.push(...info.zones);
    const sample = days[0]?.date;
    return [...new Set(seen.filter(Boolean))].map((z) => ({
      zone: z,
      label: `${sample ? abbrOn(z, sample) : zoneAbbr(z)} · ${z === 'UTC' ? 'UTC' : zoneCity(z)}${z === tripZone ? ' (trip)' : ''}${z === myZone ? ' (mine)' : ''}`,
    }));
  }, [zones, days, tripZone, myZone]);
  const shownZone = zoneChoices.some((c) => c.zone === displayZone) ? displayZone : '';
  const extraZone = zoneChoices.some((c) => c.zone === secondZone) ? secondZone : '';

  const { dates, dayByDate, zoneByDate, timed, bars, switches } = useMemo(() => {
    const byDate = {};
    const timedByDate = {};
    const allBars = [];
    const zoneSwitches = {};
    let first = days.length ? days[0].date : null;
    let last = days.length ? days[days.length - 1].date : null;
    for (const day of days) {
      byDate[day.date] = day;
      for (const stop of sortedStops(day)) {
        const info = zones?.stops[stop.id];
        const span = stopSpan(stop, day, info, shownZone || undefined, zones?.days[day.id]);
        if (span.startDate < first) first = span.startDate;
        if (span.endDate > last) last = span.endDate;
        if (span.untimed || span.long) {
          const flags = spanZoneFlags(span, shownZone);
          const barPrefix = span.untimed
            ? ''
            : `${formatMinutes(span.startMin)}${!shownZone && flags.otherZone && span.zone ? ` ${abbrOn(span.zone, span.origStartDate)}` : ''} `;
          allBars.push({
            key: `s${stop.id}`, stop, span, kind: stop.kind || 'activity', startDate: span.startDate, endDate: span.endDate,
            label: `${barPrefix}${stop.text}`,
          });
          continue;
        }
        for (let d = span.startDate; d <= span.endDate; d = addDays(d, 1)) {
          const top = d === span.startDate ? span.startMin : 0;
          const bottom = d === span.endDate ? span.endMin : DAY_MIN;
          (timedByDate[d] ||= []).push({
            key: `s${stop.id}-${d}`, stop, top, bottom, span,
            fromPrev: d !== span.startDate, toNext: d !== span.endDate,
          });
        }
        if (!shownZone && stop.kind === 'travel' && span.arriveZone && span.arriveZone !== span.zone
          && span.startDate === span.endDate) {
          (zoneSwitches[span.endDate] ||= []).push({
            key: `z${stop.id}`, minute: span.endMin, from: span.zone, to: span.arriveZone,
          });
        }
      }
    }
    let run = null;
    for (const day of days) {
      const id = day.lodging?.id ?? day.lodging_id;
      if (run && id && run.id === id && dayDiff(run.endDate, day.date) === 1) {
        run.endDate = day.date;
        continue;
      }
      if (run) allBars.push(run);
      run = id ? { key: `l${id}-${day.date}`, id, kind: 'lodging', label: day.lodging?.name || 'Lodging', startDate: day.date, endDate: day.date } : null;
    }
    if (run) allBars.push(run);
    const range = [];
    const colZone = {};
    let carry = tripZone;
    if (first) {
      for (let d = first; d <= last; d = addDays(d, 1)) {
        range.push(d);
        const info = byDate[d] && zones?.days[byDate[d].id];
        colZone[d] = info ? { start: info.start, all: info.zones } : { start: carry, all: [carry] };
        if (info) carry = info.end;
      }
    }
    return {
      dates: range, dayByDate: byDate, zoneByDate: colZone, timed: timedByDate, bars: allBars, switches: zoneSwitches,
    };
  }, [days, zones, shownZone, tripZone]);

  const legById = useMemo(() => new Map(legs.map((l) => [l.id, l])), [legs]);
  const legRanges = useMemo(() => (
    legs.map((leg) => {
      const ds = days.filter((d) => d.leg === leg.id).map((d) => d.date).sort();
      return ds.length ? { leg, start: ds[0], end: ds[ds.length - 1], count: ds.length } : null;
    }).filter(Boolean)
  ), [legs, days]);
  const selectedLegRange = activeLegId != null ? legRanges.find((r) => r.leg.id === activeLegId) : null;

  const today = epochToZoned(now, shownZone || myZone).date;
  const count = spanId === 'all' ? dates.length : Number(spanId);
  const maxStart = Math.max(0, dates.length - count);
  const defaultStart = Math.min(maxStart, Math.max(0, dates.indexOf(today)));
  const first = spanId === 'all' ? 0 : Math.min(maxStart, startIdx ?? defaultStart);
  const visible = selectedLegRange
    ? dates.filter((d) => d >= selectedLegRange.start && d <= selectedLegRange.end)
    : dates.slice(first, first + count);

  const visibleBars = useMemo(() => {
    const lo = visible[0];
    const hi = visible[visible.length - 1];
    if (!lo) return [];
    const clipped = bars
      .filter((b) => b.endDate >= lo && b.startDate <= hi)
      .map((b) => ({
        ...b,
        from: dayDiff(lo, b.startDate < lo ? lo : b.startDate),
        to: dayDiff(lo, b.endDate > hi ? hi : b.endDate),
        clippedStart: b.startDate < lo,
        clippedEnd: b.endDate > hi,
      }));
    const stays = clipped.filter((b) => b.kind === 'lodging').map((b) => ({ ...b, lane: 0 }));
    const offset = stays.length ? 1 : 0;
    const others = layoutLanes(clipped.filter((b) => b.kind !== 'lodging')).map((b) => ({ ...b, lane: b.lane + offset }));
    return [...stays, ...others];
  }, [bars, visible]);

  const firstMinute = useMemo(() => {
    const starts = visible.flatMap((d) => (timed[d] || []).filter((i) => !i.fromPrev).map((i) => i.top));
    return starts.length ? Math.min(...starts) : 7 * 60;
  }, [visible, timed]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = Math.max(0, (firstMinute / 60 - 1) * HOUR_PX);
  }, [spanId, first, firstMinute, shownZone]);

  const chooseSpan = (id) => { setActiveLegId(null); setSpanId(id); store('trips.calendarSpan', id); };
  const chooseZone = (z) => { setDisplayZone(z); store('trips.calendarZone', z); };
  const chooseSecond = (z) => { setSecondZone(z); store('trips.calendarSecondZone', z); };

  if (!dates.length) return <p className="trip-empty">No days yet. Add a day to see the calendar.</p>;

  // The hour gutter can only name one clock: the chosen zone, or the one local zone every visible day shares.
  const columnZone = (date) => shownZone || zoneByDate[date]?.start || tripZone;
  const uniformZone = shownZone || (() => {
    const all = new Set(visible.flatMap((d) => zoneByDate[d]?.all || []));
    return all.size === 1 ? [...all][0] : '';
  })();
  const secondGutter = extraZone && uniformZone && extraZone !== uniformZone;
  const secondShift = secondGutter
    ? (() => {
      const at = zonedToEpoch(visible[0], '12:00', uniformZone);
      return offsetMinutes(extraZone, at) - offsetMinutes(uniformZone, at);
    })()
    : 0;
  const gutters = secondGutter ? 2 : 1;
  const colWidth = spanId === 'all' ? '8.5rem' : '7rem';
  const template = `${Array(gutters).fill(GUTTER).join(' ')} repeat(${visible.length}, minmax(${colWidth}, 1fr))`;
  const laneCount = visibleBars.reduce((n, b) => Math.max(n, b.lane + 1), 0);
  const rangeLabel = visible.length > 1
    ? `${dateLabel(visible[0], { month: 'short', day: 'numeric' })} – ${dateLabel(visible[visible.length - 1], { month: 'short', day: 'numeric', year: 'numeric' })}`
    : dateLabel(visible[0], { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' });

  const resolveSlot = (date, event, stepMin = 30) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const rawMin = ((event.clientY - rect.top) / HOUR_PX) * 60;
    const minutes = Math.max(0, Math.min(DAY_MIN - stepMin, Math.floor(rawMin / stepMin) * stepMin));
    let target = { date, time: clockText(minutes) };
    if (shownZone) {
      const instant = zonedToEpoch(date, target.time, shownZone);
      const local = epochToZoned(instant, zoneByDate[date]?.start || tripZone);
      target = epochToZoned(instant, zoneByDate[local.date]?.start || tripZone);
    }
    return { day: dayByDate[target.date], time: target.time, minutes };
  };

  const addAt = (date, event) => {
    if (!onAddAt) return;
    const { day, time } = resolveSlot(date, event, 30);
    if (day) onAddAt(day, time);
  };

  const onColDragOver = (date, event) => {
    if (!onDropIdea || !event.dataTransfer.types.includes('application/x-trip-idea')) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    const { day, minutes } = resolveSlot(date, event, 15);
    if (!day) { setDropHint(null); return; }
    setDropHint({ date, minutes });
  };

  const onColDrop = (date, event) => {
    setDropHint(null);
    if (!onDropIdea) return;
    const raw = event.dataTransfer.getData('application/x-trip-idea');
    if (!raw) return;
    event.preventDefault();
    try {
      const { id } = JSON.parse(raw);
      const { day, time } = resolveSlot(date, event, 15);
      if (id && day) onDropIdea(id, day, time);
    } catch { /* ignore */ }
  };

  const secondText = (epoch) => {
    if (!extraZone || epoch == null) return '';
    const w = epochToZoned(epoch, extraZone);
    return `${formatMinutes(clockMin(w.time))} ${zoneAbbr(extraZone, epoch)}`;
  };

  const visibleSpans = [
    ...visibleBars.map((b) => b.span),
    ...visible.flatMap((d) => (timed[d] || []).map((i) => i.span)),
  ];
  const anyChangesZone = visibleSpans.some((s) => spanZoneFlags(s, shownZone).changesZone);
  const anyOtherZone = visibleSpans.some((s) => spanZoneFlags(s, shownZone).otherZone);

  const iconNotes = (span, date) => {
    const flags = spanZoneFlags(span, shownZone);
    const localSummary = span ? localTimeSummary(span) : '';
    const shiftTitle = flags.changesZone
      ? `Changes time zone: ${abbrOn(span.zone, span.origStartDate || date)} → ${abbrOn(span.arriveZone, span.origEndDate || date)}`
      : '';
    let otherTitle = '';
    if (flags.otherZone && span?.zone) {
      const zName = `${abbrOn(span.zone, span.origStartDate || date)} · ${zoneCity(span.zone)}`;
      if (shownZone) {
        otherTitle = span.untimed
          ? `Local date in ${zName} (calendar is in ${abbrOn(shownZone, date)})`
          : `Local: ${localSummary} (${zoneCity(span.zone)})`;
      } else {
        const colZ = span.dayStartZone ? abbrOn(span.dayStartZone, date) : 'day';
        otherTitle = `Event is in ${zName} (day column is ${colZ})`;
      }
    }
    return { ...flags, localSummary, shiftTitle, otherTitle };
  };

  return (
    <div className="trip-cal">
      <div className="trip-cal-toolbar">
        {!selectedLegRange && spanId !== 'all' && (
          <>
            <button type="button" onClick={() => setStartIdx(Math.max(0, first - count))} disabled={first === 0} aria-label="Previous">‹</button>
            <button type="button" onClick={() => setStartIdx(defaultStart)}>{dates.includes(today) ? 'Today' : 'Start'}</button>
            <button type="button" onClick={() => setStartIdx(Math.min(maxStart, first + count))} disabled={first >= maxStart} aria-label="Next">›</button>
          </>
        )}
        <span className="trip-cal-range">
          {selectedLegRange ? `${selectedLegRange.leg.name} · ` : ''}{rangeLabel}
        </span>
        <div className="trip-status-tabs">
          {SPANS.map((s) => (
            <button
              key={s.id}
              type="button"
              className={!selectedLegRange && spanId === s.id ? 'is-active' : ''}
              onClick={() => chooseSpan(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
      {legRanges.length > 0 && (
        <div className="trip-cal-toolbar trip-cal-legs">
          <span className="trip-muted">Leg:</span>
          <button
            type="button"
            className={`trip-cal-leg-pill${!selectedLegRange ? ' is-active' : ''}`}
            onClick={() => setActiveLegId(null)}
          >
            All dates
          </button>
          {legRanges.map(({ leg, count: c }) => (
            <button
              key={leg.id}
              type="button"
              className={`trip-cal-leg-pill${activeLegId === leg.id ? ' is-active' : ''}`}
              onClick={() => setActiveLegId((cur) => (cur === leg.id ? null : leg.id))}
            >
              {leg.name} ({c}d)
            </button>
          ))}
        </div>
      )}
      <div className="trip-cal-toolbar trip-cal-zones">
        <label>
          Show times in
          <select value={shownZone} onChange={(e) => chooseZone(e.target.value)}>
            <option value="">Local time of each day</option>
            {zoneChoices.map((c) => <option key={c.zone} value={c.zone}>{c.label}</option>)}
          </select>
        </label>
        <label>
          Second clock
          <select value={extraZone} onChange={(e) => chooseSecond(e.target.value)}>
            <option value="">None</option>
            {zoneChoices.map((c) => <option key={c.zone} value={c.zone}>{c.label}</option>)}
          </select>
        </label>
        {extraZone && !secondGutter && extraZone !== uniformZone && (
          <span className="trip-muted">These days span several zones, so {zoneAbbr(extraZone, now)} times are shown on each item.</span>
        )}
        {(anyChangesZone || anyOtherZone) && (
          <span className="trip-cal-legend">
            {anyChangesZone && (
              <span><ZoneChangeIcon title="Changes time zone" /> Changes time zone</span>
            )}
            {anyOtherZone && (
              <span>
                <OtherZoneIcon
                  title={shownZone
                    ? `Event takes place in a different time zone than ${abbrOn(shownZone, visible[0])}`
                    : "Event time zone differs from its day's zone"}
                />
                {shownZone ? `Other local zone (not ${abbrOn(shownZone, visible[0])})` : "Differs from day's zone"}
              </span>
            )}
          </span>
        )}
      </div>
      <div className="trip-cal-scroll" ref={scrollRef}>
        <div className="trip-cal-inner" style={{ minWidth: `calc(${gutters} * ${GUTTER} + ${visible.length} * ${colWidth})` }}>
          <div className="trip-cal-head">
            <div className="trip-cal-row" style={{ gridTemplateColumns: template }}>
              <div className="trip-cal-corner trip-cal-gutter-name" title={uniformZone || 'Each day in its own local time'}>
                {uniformZone ? abbrOn(uniformZone, visible[0]) : 'Local'}
              </div>
              {secondGutter && (
                <div className="trip-cal-corner trip-cal-gutter-name is-second" style={{ left: GUTTER }} title={extraZone}>
                  {abbrOn(extraZone, visible[0])}
                </div>
              )}
              {visible.map((date) => {
                const day = dayByDate[date];
                const dayLeg = day?.leg ? legById.get(day.leg) : null;
                const info = day && zones?.days[day.id];
                const zoneNames = info && !(info.zones.length === 1 && info.zones[0] === tripZone)
                  ? info.zones.map((z) => abbrOn(z, date)).join(' → ')
                  : '';
                return (
                  <div key={date} className={`trip-cal-dayhead${date === today ? ' is-today' : ''}${day ? '' : ' is-gap'}`}>
                    {dayLeg && <span className="trip-cal-dayleg">{dayLeg.name}</span>}
                    <strong>{dateLabel(date)}</strong>
                    {day?.title && <span className="trip-cal-daytitle" title={day.title}>{day.title}</span>}
                    {zoneNames && <span className="trip-day-zone" title={shownZone ? 'Local zones that day' : undefined}>{zoneNames}</span>}
                  </div>
                );
              })}
            </div>
            {laneCount > 0 && (
              <div className="trip-cal-row" style={{ gridTemplateColumns: template }}>
                <div className="trip-cal-corner trip-cal-allday-label" style={{ gridColumn: `1 / span ${gutters}` }}>All day</div>
                <div
                  className="trip-cal-allday"
                  style={{ gridColumn: `${gutters + 1} / span ${visible.length}`, gridTemplateColumns: `repeat(${visible.length}, 1fr)` }}
                >
                  {visibleBars.map((bar) => {
                    const notes = iconNotes(bar.span, bar.startDate);
                    const barZoneTag = shownZone && notes.otherZone && bar.span?.zone
                      ? abbrOn(bar.span.zone, bar.span.origStartDate || bar.startDate)
                      : '';
                    const barTitle = [
                      bar.kind === 'lodging' ? `Stay: ${bar.label}` : bar.label,
                      notes.shiftTitle,
                      notes.otherTitle || (shownZone && notes.changesZone && notes.localSummary ? `Local: ${notes.localSummary}` : ''),
                    ].filter(Boolean).join('\n');
                    return (
                      <button
                        key={bar.key}
                        type="button"
                        className={`trip-cal-bar is-${bar.kind}${bar.stop?.status === 'tobook' ? ' is-tobook' : ''}${bar.stop?.status === 'option' ? ' is-option' : ''}${bar.clippedStart ? ' is-clipped-start' : ''}${bar.clippedEnd ? ' is-clipped-end' : ''}`}
                        style={{ gridColumn: `${bar.from + 1} / ${bar.to + 2}`, gridRow: bar.lane + 1 }}
                        title={barTitle}
                        onClick={() => bar.stop && onOpenStop(bar.stop)}
                        disabled={!bar.stop}
                      >
                        <span className="trip-cal-bar-text">{bar.kind === 'lodging' ? `🛏 ${bar.label}` : bar.label}</span>
                        {bar.stop?.status === 'option' && <span className="trip-cal-bar-zone">Opt</span>}
                        {barZoneTag && <span className="trip-cal-bar-zone">{barZoneTag}</span>}
                        {(notes.changesZone || notes.otherZone) && (
                          <span className="trip-cal-icons">
                            {notes.changesZone && <ZoneChangeIcon title={notes.shiftTitle} />}
                            {notes.otherZone && <OtherZoneIcon title={notes.otherTitle} />}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
          <div className="trip-cal-row trip-cal-body" style={{ gridTemplateColumns: template, height: `${24 * HOUR_PX}px` }}>
            <div className="trip-cal-gutter">
              {Array.from({ length: 23 }, (_, i) => i + 1).map((h) => (
                <span key={h} style={{ top: `${h * HOUR_PX}px` }}>{formatMinutes(h * 60)}</span>
              ))}
            </div>
            {secondGutter && (
              <div className="trip-cal-gutter is-second" style={{ left: GUTTER }}>
                {Array.from({ length: 23 }, (_, i) => i + 1).map((h) => {
                  const m = h * 60 + secondShift;
                  const shift = Math.floor(m / DAY_MIN);
                  return (
                    <span key={h} style={{ top: `${h * HOUR_PX}px` }}>
                      {formatMinutes(((m % DAY_MIN) + DAY_MIN) % DAY_MIN)}{shift ? <sup>{shift > 0 ? `+${shift}` : shift}</sup> : null}
                    </span>
                  );
                })}
              </div>
            )}
            {visible.map((date) => {
              const nowWall = epochToZoned(now, columnZone(date));
              const isDropTarget = dropHint?.date === date;
              return (
                <div
                  key={date}
                  className={`trip-cal-col${dayByDate[date] ? '' : ' is-gap'}${isDropTarget ? ' is-drop-target' : ''}`}
                  style={{ backgroundSize: `100% ${HOUR_PX}px` }}
                  onClick={(e) => addAt(date, e)}
                  onDragOver={(e) => onColDragOver(date, e)}
                  onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDropHint(null); }}
                  onDrop={(e) => onColDrop(date, e)}
                  title="Click to add a stop at this time"
                >
                  {isDropTarget && (
                    <div className="trip-cal-dropline" style={{ top: `${(dropHint.minutes / 60) * HOUR_PX}px` }}>
                      <span>Drop at {formatMinutes(dropHint.minutes)}</span>
                    </div>
                  )}
                  {layoutColumns(timed[date] || []).map((item) => {
                    const { stop, span } = item;
                    const height = Math.max(18, ((item.bottom - item.top) / 60) * HOUR_PX - 2);
                    const offset = dayDiff(span.startDate, span.endDate);
                    const notes = iconNotes(span, date);
                    let when;
                    if (!shownZone && notes.otherZone && notes.localSummary) {
                      when = notes.localSummary;
                    } else if (span.point) {
                      when = formatMinutes(span.startMin);
                    } else {
                      when = `${formatMinutes(span.startMin)} – ${formatMinutes(span.endMin % DAY_MIN)}${offset ? ` (+${offset})` : ''}`;
                    }
                    if (stop.kind === 'travel' && span.duration) when += ` · ${formatDuration(span.duration)}`;
                    const localLine = shownZone && (notes.otherZone || notes.changesZone) ? notes.localSummary : '';
                    const second = secondGutter ? '' : secondText(span.t0);
                    return (
                      <button
                        key={item.key}
                        type="button"
                        className={`trip-cal-event is-${stop.kind || 'activity'}${stop.status === 'tobook' ? ' is-tobook' : ''}${stop.status === 'option' ? ' is-option' : ''}${item.fromPrev ? ' is-cont-prev' : ''}${item.toNext ? ' is-cont-next' : ''}`}
                        style={{
                          top: `${(item.top / 60) * HOUR_PX}px`,
                          height: `${height}px`,
                          left: `calc(${(item.col / item.cols) * 100}% + 2px)`,
                          width: `calc(${100 / item.cols}% - 4px)`,
                        }}
                        title={[
                          `${stop.status === 'option' ? '[Option] ' : ''}${when} · ${stop.text}`,
                          localLine && `Local: ${localLine}`,
                          notes.shiftTitle,
                          !localLine && notes.otherTitle,
                          second && `Starts ${second}`,
                        ].filter(Boolean).join('\n')}
                        onClick={(e) => { e.stopPropagation(); onOpenStop(stop); }}
                      >
                        <span className="trip-cal-event-head">
                          <span className="trip-cal-event-title">{item.fromPrev ? `↳ ${stop.text}` : stop.text}</span>
                          {stop.status === 'option' && <span className="trip-cal-opt-pill">Opt</span>}
                          {(notes.changesZone || notes.otherZone) && (
                            <span className="trip-cal-icons">
                              {notes.changesZone && <ZoneChangeIcon title={notes.shiftTitle} />}
                              {notes.otherZone && <OtherZoneIcon title={notes.otherTitle} />}
                            </span>
                          )}
                        </span>
                        {height > 30 && <span className="trip-cal-event-time">{when}</span>}
                        {localLine && height > 44 && <span className="trip-cal-event-time is-local">{localLine}</span>}
                        {!localLine && second && height > 44 && <span className="trip-cal-event-time is-second">{second}</span>}
                      </button>
                    );
                  })}
                  {(switches[date] || []).map((s) => (
                    <div key={s.key} className="trip-cal-zone-switch" style={{ top: `${(s.minute / 60) * HOUR_PX}px` }}>
                      <span>{abbrOn(s.from, date)} → {abbrOn(s.to, date)}</span>
                    </div>
                  ))}
                  {nowWall.date === date && (
                    <div className="trip-cal-now" style={{ top: `${(clockMin(nowWall.time) / 60) * HOUR_PX}px` }} />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
