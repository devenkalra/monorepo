import React, { useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { MOCK_TRIP } from './mockData';
import './mockup.css';

const KIND_ICON = {
  flight: '✈',
  travel: '🚤',
  stay: '🛏',
  food: '🍽',
  event: '🎟',
  activity: '📍',
};

const KIND_OPTIONS = [
  { id: 'activity', label: 'Activity' },
  { id: 'flight', label: 'Flight' },
  { id: 'travel', label: 'Transfer / Boat' },
  { id: 'food', label: 'Dining' },
  { id: 'event', label: 'Tour / Event' },
  { id: 'stay', label: 'Stay / Check-in' },
];

const STATUS_LABEL = {
  confirmed: 'Confirmed',
  booked: 'Booked',
  tobook: 'To book',
  no_booking: 'No booking',
};

function cloneTrip() {
  return JSON.parse(JSON.stringify(MOCK_TRIP));
}

function DayPeekDrawer({ day, leg, onClose, onOpenItinerary }) {
  if (!day) return null;
  return (
    <div className="tm-drawer-backdrop" onClick={onClose} role="presentation">
      <aside className="tm-drawer" onClick={(e) => e.stopPropagation()} aria-label={`Day ${day.num} details`}>
        <header className="tm-drawer-head">
          <div>
            <span className="tm-eyebrow" style={{ color: leg.color }}>
              {leg.name} · Day {day.num} · {day.weekday}, {day.shortDate}
            </span>
            <h2>{day.title}</h2>
          </div>
          <button type="button" className="tm-icon-close" onClick={onClose} aria-label="Close">×</button>
        </header>

        <div className="tm-drawer-body">
          {day.stay && (
            <div className="tm-peek-stay">
              <span>🛏</span>
              <div>
                <strong>{day.stay}</strong>
                {day.stayCheckIn && <span className="tm-chip-subtle">Check-in</span>}
              </div>
            </div>
          )}

          {day.notes && (
            <section className="tm-peek-section">
              <h4>Day Notes</h4>
              <p className="tm-notes-text">{day.notes}</p>
            </section>
          )}

          <section className="tm-peek-section">
            <h4>Plan ({day.items.length})</h4>
            <ul className="tm-peek-items">
              {day.items.map((item) => (
                <li key={item.id} className="tm-peek-item">
                  <span className="tm-peek-time">{item.time}</span>
                  <span className="tm-peek-icon" aria-hidden="true">{KIND_ICON[item.kind] || '•'}</span>
                  <div className="tm-peek-info">
                    <div className="tm-peek-title-row">
                      <strong>{item.title}</strong>
                      {item.status && item.status !== 'no_booking' && (
                        <span className={`tm-status is-${item.status}`}>{STATUS_LABEL[item.status]}</span>
                      )}
                    </div>
                    {(item.meta || item.conf) && (
                      <span className="tm-muted">
                        {item.meta}
                        {item.conf ? `${item.meta ? ' · ' : ''}Conf # ${item.conf}` : ''}
                      </span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <footer className="tm-drawer-foot">
          <button type="button" className="tm-btn-secondary" onClick={onClose}>Close</button>
          <button type="button" className="tm-btn-primary" onClick={() => onOpenItinerary(day.id)}>
            Open in Itinerary →
          </button>
        </footer>
      </aside>
    </div>
  );
}

function DayEditDrawer({ day, leg, legs, isNew, onClose, onSave, onDelete }) {
  const [title, setTitle] = useState(day?.title || '');
  const [shortDate, setShortDate] = useState(day?.shortDate || 'Jan 24');
  const [weekday, setWeekday] = useState(day?.weekday || 'Sun');
  const [stay, setStay] = useState(day?.stay || leg?.stay || '');
  const [legId, setLegId] = useState(leg?.id || legs[0]?.id || '');
  const [notes, setNotes] = useState(day?.notes || '');

  const submit = (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    onSave({
      id: day?.id || `d-${Date.now()}`,
      title: title.trim(),
      shortDate: shortDate.trim() || 'TBD',
      weekday: weekday.trim() || '',
      stay: stay.trim(),
      notes: notes.trim(),
      legId,
    });
  };

  return (
    <div className="tm-drawer-backdrop" onClick={onClose} role="presentation">
      <form className="tm-drawer" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <header className="tm-drawer-head">
          <div>
            <span className="tm-eyebrow">{isNew ? 'Add Day' : `Edit Day ${day.num}`}</span>
            <h2>{isNew ? 'New trip day' : day.title}</h2>
          </div>
          <button type="button" className="tm-icon-close" onClick={onClose} aria-label="Close">×</button>
        </header>

        <div className="tm-drawer-body tm-form">
          <label>
            Day title
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Old City Temples & Night Market"
              autoFocus
              required
            />
          </label>
          <div className="tm-form-row-2">
            <label>
              Date label
              <input type="text" value={shortDate} onChange={(e) => setShortDate(e.target.value)} placeholder="Jan 24" />
            </label>
            <label>
              Weekday
              <input type="text" value={weekday} onChange={(e) => setWeekday(e.target.value)} placeholder="Sun" />
            </label>
          </div>
          <label>
            Leg
            <select value={legId} onChange={(e) => setLegId(e.target.value)}>
              {legs.map((l) => (
                <option key={l.id} value={l.id}>{l.name}</option>
              ))}
            </select>
          </label>
          <label>
            Stay / Lodging
            <input type="text" value={stay} onChange={(e) => setStay(e.target.value)} placeholder="Hotel or resort name" />
          </label>
          <label>
            Day notes
            <textarea
              rows={4}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="High-level plan, logistics, reminders…"
            />
          </label>
        </div>

        <footer className="tm-drawer-foot">
          {!isNew && onDelete ? (
            <button type="button" className="tm-btn-danger" onClick={() => onDelete(day.id)}>
              Delete day
            </button>
          ) : (
            <span />
          )}
          <div className="tm-foot-right">
            <button type="button" className="tm-btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="tm-btn-primary">{isNew ? 'Add day' : 'Save changes'}</button>
          </div>
        </footer>
      </form>
    </div>
  );
}

function ActivityEditDrawer({ day, leg, item, onClose, onSave, onDelete }) {
  const isNew = !item?.id;
  const [title, setTitle] = useState(item?.title || '');
  const [kind, setKind] = useState(item?.kind || 'activity');
  const [time, setTime] = useState(item?.time || '10:00');
  const [status, setStatus] = useState(item?.status || 'no_booking');
  const [conf, setConf] = useState(item?.conf || '');
  const [meta, setMeta] = useState(item?.meta || '');

  const submit = (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    onSave(day.id, {
      id: item?.id || `s-${Date.now()}`,
      title: title.trim(),
      kind,
      time: time.trim() || '—',
      status,
      conf: conf.trim(),
      meta: meta.trim(),
    });
  };

  return (
    <div className="tm-drawer-backdrop" onClick={onClose} role="presentation">
      <form className="tm-drawer" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <header className="tm-drawer-head">
          <div>
            <span className="tm-eyebrow" style={{ color: leg.color }}>
              {leg.name} · Day {day.num} · {day.shortDate}
            </span>
            <h2>{isNew ? 'Add activity' : 'Edit activity'}</h2>
          </div>
          <button type="button" className="tm-icon-close" onClick={onClose} aria-label="Close">×</button>
        </header>

        <div className="tm-drawer-body tm-form">
          <label>
            Title
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Morning kayak or BKK → CNX flight"
              autoFocus
              required
            />
          </label>
          <div className="tm-form-row-2">
            <label>
              Type
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                {KIND_OPTIONS.map((k) => (
                  <option key={k.id} value={k.id}>{KIND_ICON[k.id]} {k.label}</option>
                ))}
              </select>
            </label>
            <label>
              Time
              <input type="text" value={time} onChange={(e) => setTime(e.target.value)} placeholder="09:30" />
            </label>
          </div>
          <div className="tm-form-row-2">
            <label>
              Booking status
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="no_booking">No booking</option>
                <option value="tobook">To book</option>
                <option value="booked">Booked</option>
                <option value="confirmed">Confirmed</option>
              </select>
            </label>
            <label>
              Confirmation #
              <input type="text" value={conf} onChange={(e) => setConf(e.target.value)} placeholder="Optional" />
            </label>
          </div>
          <label>
            Notes / Details
            <textarea
              rows={3}
              value={meta}
              onChange={(e) => setMeta(e.target.value)}
              placeholder="Meeting point, dress code, terminal, seats…"
            />
          </label>
        </div>

        <footer className="tm-drawer-foot">
          {!isNew && onDelete ? (
            <button type="button" className="tm-btn-danger" onClick={() => onDelete(day.id, item.id)}>
              Delete
            </button>
          ) : (
            <span />
          )}
          <div className="tm-foot-right">
            <button type="button" className="tm-btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="tm-btn-primary">{isNew ? 'Add to day' : 'Save'}</button>
          </div>
        </footer>
      </form>
    </div>
  );
}

function CalendarSummaryView({ legs, onSelectDay }) {
  const dayByDate = useMemo(() => {
    const map = new Map();
    for (const leg of legs) {
      for (const day of leg.days) {
        if (day.date) map.set(day.date, { day, leg });
      }
    }
    return map;
  }, [legs]);

  const cells = useMemo(() => {
    const out = [];
    for (let d = 10; d <= 23; d += 1) {
      const iso = `2027-01-${String(d).padStart(2, '0')}`;
      out.push({ iso, dayNum: d, entry: dayByDate.get(iso) || null });
    }
    return out;
  }, [dayByDate]);

  return (
    <div className="tm-cal-wrap">
      <div className="tm-cal-header">
        <h3>January 2027</h3>
        <div className="tm-cal-legend">
          {legs.map((leg) => (
            <span key={leg.id} className="tm-legend-item">
              <i style={{ background: leg.color }} />
              {leg.name}
            </span>
          ))}
        </div>
      </div>

      <div className="tm-cal-grid">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((w) => (
          <div key={w} className="tm-cal-dow">{w}</div>
        ))}
        {cells.map(({ iso, dayNum, entry }) => {
          if (!entry) {
            return (
              <div key={iso} className="tm-cal-cell is-empty">
                <span className="tm-cal-date">{dayNum}</span>
              </div>
            );
          }
          const { day, leg } = entry;
          const hasFlight = day.items.some((i) => i.kind === 'flight');
          return (
            <button
              key={iso}
              type="button"
              className="tm-cal-cell is-trip"
              style={{ borderTopColor: leg.color, background: leg.tint }}
              onClick={() => onSelectDay(day, leg)}
            >
              <div className="tm-cal-cell-top">
                <span className="tm-cal-date">Jan {dayNum}</span>
                <span className="tm-cal-daybadge" style={{ color: leg.color }}>Day {day.num}</span>
              </div>
              <strong className="tm-cal-title">{day.title}</strong>
              <div className="tm-cal-meta">
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

function renumberDays(legs) {
  let n = 1;
  return legs.map((leg) => ({
    ...leg,
    nights: leg.days.length,
    days: leg.days.map((d) => ({ ...d, num: n++ })),
  }));
}

export default function TripMockup() {
  const [trip, setTrip] = useState(cloneTrip);
  const [section, setSection] = useState('summary'); // summary | itinerary | ideas | bookings | documents
  const [summaryMode, setSummaryMode] = useState('overview'); // overview | detail | calendar
  const [legFilter, setLegFilter] = useState('all');
  const [peek, setPeek] = useState(null);
  const [previewDoc, setPreviewDoc] = useState(null);

  // Itinerary selection state (panel hidden on demand; supports All days, Select by leg, single, range, multi)
  const [showAllDays, setShowAllDays] = useState(true);
  const [selectedDayIds, setSelectedDayIds] = useState(() => [MOCK_TRIP.legs[0].days[0].id]);
  const [anchorDayId, setAnchorDayId] = useState(() => MOCK_TRIP.legs[0].days[0].id);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [rangeMode, setRangeMode] = useState(false); // touch-friendly range picker toggle
  const [collapsedDayIds, setCollapsedDayIds] = useState({}); // { [dayId]: true }
  const [collapsedLegIds, setCollapsedLegIds] = useState({}); // { [legId]: true }
  const [pinEditControls, setPinEditControls] = useState(false);
  const [openDayMenuId, setOpenDayMenuId] = useState(null);
  const [showIdeasPane, setShowIdeasPane] = useState(false);
  const [ideaLegFilter, setIdeaLegFilter] = useState('all');
  const [ideaSearch, setIdeaSearch] = useState('');
  const [ideaTargetDayById, setIdeaTargetDayById] = useState({});
  const [addedIdeaLog, setAddedIdeaLog] = useState({});
  const [dragOverDayId, setDragOverDayId] = useState(null);

  // CRUD drawers & inline quick-add state
  const [editingDayState, setEditingDayState] = useState(null); // { day, leg, isNew }
  const [editingActivityState, setEditingActivityState] = useState(null); // { day, leg, item }
  const [quickAddByDay, setQuickAddByDay] = useState({}); // { [dayId]: { time, title } }

  const daySliderRef = useRef(null);

  const allDays = useMemo(
    () => trip.legs.flatMap((leg) => leg.days.map((day) => ({ day, leg }))),
    [trip],
  );

  const visibleLegs = useMemo(
    () => (legFilter === 'all' ? trip.legs : trip.legs.filter((l) => l.id === legFilter)),
    [trip, legFilter],
  );

  const bookingCounts = useMemo(() => {
    const confirmed = trip.bookings.filter((b) => b.status === 'confirmed').length;
    const booked = trip.bookings.filter((b) => b.status === 'booked').length;
    const tobook = trip.bookings.filter((b) => b.status === 'tobook').length;
    return { confirmed, booked, tobook };
  }, [trip]);

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
    if (showAllDays) return `Showing all ${allDays.length} days`;
    const nums = selectedItineraryDays.map(({ day }) => day.num);
    if (nums.length === 1) {
      const { day, leg } = selectedItineraryDays[0];
      return `Day ${day.num} · ${day.weekday}, ${day.shortDate} · ${leg.name}`;
    }
    const isContiguous = nums.every((n, i) => i === 0 || n === nums[i - 1] + 1);
    if (isContiguous) {
      return `Days ${nums[0]}–${nums[nums.length - 1]} (${nums.length} days selected)`;
    }
    return `${nums.length} days selected (Days ${nums.join(', ')})`;
  }, [showAllDays, allDays.length, selectedItineraryDays]);

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
        if (prev.includes(dayId)) {
          return prev.length > 1 ? prev.filter((id) => id !== dayId) : prev;
        }
        return [...prev, dayId];
      });
      setAnchorDayId(dayId);
      return;
    }

    setSelectedDayIds([dayId]);
    setAnchorDayId(dayId);
  };

  const selectByLeg = (leg) => {
    const ids = leg.days.map((d) => d.id);
    if (!ids.length) return;
    setShowAllDays(false);
    setRangeMode(false);
    setSelectedDayIds(ids);
    setAnchorDayId(ids[0]);
  };

  const isLegSelected = (leg) => {
    if (showAllDays || !leg.days.length) return false;
    if (selectedDayIds.length !== leg.days.length) return false;
    return leg.days.every((d) => selectedDayIds.includes(d.id));
  };

  const toggleDayCollapsed = (dayId) => {
    setCollapsedDayIds((prev) => ({ ...prev, [dayId]: !prev[dayId] }));
  };

  const toggleLegCollapsed = (legId) => {
    setCollapsedLegIds((prev) => ({ ...prev, [legId]: !prev[legId] }));
  };

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

  const anyVisibleExpanded = useMemo(
    () => selectedItineraryDays.some(({ day, leg }) => !collapsedLegIds[leg.id] && !collapsedDayIds[day.id]),
    [selectedItineraryDays, collapsedDayIds, collapsedLegIds],
  );
  const anyVisibleCollapsed = useMemo(
    () => selectedItineraryDays.some(({ day, leg }) => Boolean(collapsedLegIds[leg.id] || collapsedDayIds[day.id])),
    [selectedItineraryDays, collapsedDayIds, collapsedLegIds],
  );

  const slideDays = (dir) => {
    const el = daySliderRef.current;
    if (!el) return;
    el.scrollBy({ left: dir * 280, behavior: 'smooth' });
  };

  const jumpToItinerary = (dayId) => {
    setPeek(null);
    setShowAllDays(false);
    setSelectedDayIds([dayId]);
    setAnchorDayId(dayId);
    setPickerOpen(false);
    const targetEntry = allDays.find((f) => f.day.id === dayId);
    if (targetEntry) {
      setCollapsedLegIds((prev) => {
        const next = { ...prev };
        delete next[targetEntry.leg.id];
        return next;
      });
    }
    setCollapsedDayIds((prev) => {
      const next = { ...prev };
      delete next[dayId];
      return next;
    });
    setSection('itinerary');
  };

  // ================= MOCK CRUD HANDLERS =================
  const saveDay = (payload) => {
    setTrip((prev) => {
      const isNew = editingDayState?.isNew;
      let nextLegs = prev.legs.map((leg) => ({ ...leg, days: [...leg.days] }));
      if (isNew) {
        const targetLeg = nextLegs.find((l) => l.id === payload.legId) || nextLegs[nextLegs.length - 1];
        const newDay = {
          id: payload.id,
          num: 0,
          date: '',
          weekday: payload.weekday,
          shortDate: payload.shortDate,
          title: payload.title,
          stay: payload.stay,
          notes: payload.notes,
          items: [],
        };
        const insertRefId = editingDayState?.insertRefId;
        const insertPosition = editingDayState?.insertPosition; // 'before' | 'after'
        if (insertRefId) {
          const refLeg = nextLegs.find((l) => l.days.some((d) => d.id === insertRefId));
          if (refLeg) {
            const idx = refLeg.days.findIndex((d) => d.id === insertRefId);
            refLeg.days.splice(insertPosition === 'before' ? idx : idx + 1, 0, newDay);
          } else {
            targetLeg.days.push(newDay);
          }
        } else {
          targetLeg.days.push(newDay);
        }
        nextLegs = renumberDays(nextLegs);
        setShowAllDays(false);
        setSelectedDayIds([newDay.id]);
        setAnchorDayId(newDay.id);
      } else {
        let existingDay = null;
        for (const l of nextLegs) {
          const idx = l.days.findIndex((d) => d.id === payload.id);
          if (idx !== -1) {
            existingDay = {
              ...l.days[idx],
              title: payload.title,
              shortDate: payload.shortDate,
              weekday: payload.weekday,
              stay: payload.stay,
              notes: payload.notes,
            };
            if (l.id === payload.legId) {
              l.days[idx] = existingDay;
            } else {
              l.days.splice(idx, 1);
              const dest = nextLegs.find((x) => x.id === payload.legId) || l;
              dest.days.push(existingDay);
            }
            break;
          }
        }
        nextLegs = renumberDays(nextLegs);
      }
      return { ...prev, legs: nextLegs };
    });
    setEditingDayState(null);
  };

  const deleteDay = (dayId) => {
    if (!window.confirm('Delete this day from the mockup trip?')) return;
    setTrip((prev) => {
      const nextLegs = renumberDays(
        prev.legs.map((l) => ({ ...l, days: l.days.filter((d) => d.id !== dayId) })),
      );
      return { ...prev, legs: nextLegs };
    });
    setSelectedDayIds((prev) => prev.filter((id) => id !== dayId));
    setEditingDayState(null);
    setOpenDayMenuId(null);
  };

  const saveActivity = (dayId, nextItem) => {
    setTrip((prev) => ({
      ...prev,
      legs: prev.legs.map((leg) => ({
        ...leg,
        days: leg.days.map((day) => {
          if (day.id !== dayId) return day;
          const exists = day.items.some((i) => i.id === nextItem.id);
          const items = exists
            ? day.items.map((i) => (i.id === nextItem.id ? nextItem : i))
            : [...day.items, nextItem];
          return { ...day, items };
        }),
      })),
    }));
    setEditingActivityState(null);
  };

  const deleteActivity = (dayId, itemId) => {
    setTrip((prev) => ({
      ...prev,
      legs: prev.legs.map((leg) => ({
        ...leg,
        days: leg.days.map((day) => (
          day.id === dayId ? { ...day, items: day.items.filter((i) => i.id !== itemId) } : day
        )),
      })),
    }));
    setEditingActivityState(null);
  };

  const moveActivity = (dayId, itemId, dir) => {
    setTrip((prev) => ({
      ...prev,
      legs: prev.legs.map((leg) => ({
        ...leg,
        days: leg.days.map((day) => {
          if (day.id !== dayId) return day;
          const idx = day.items.findIndex((i) => i.id === itemId);
          const target = idx + dir;
          if (idx < 0 || target < 0 || target >= day.items.length) return day;
          const items = [...day.items];
          [items[idx], items[target]] = [items[target], items[idx]];
          return { ...day, items };
        }),
      })),
    }));
  };

  const submitQuickAdd = (dayId, e) => {
    e.preventDefault();
    const draft = quickAddByDay[dayId] || {};
    const title = (draft.title || '').trim();
    if (!title) return;
    saveActivity(dayId, {
      id: `s-${Date.now()}`,
      time: (draft.time || '').trim() || '12:00',
      kind: draft.kind || 'activity',
      title,
      status: 'no_booking',
      meta: '',
      conf: '',
    });
    setQuickAddByDay((prev) => ({ ...prev, [dayId]: { time: '', title: '', kind: draft.kind || 'activity' } }));
  };

  const inferKindFromIdeaCat = (cat = '') => {
    const c = cat.toLowerCase();
    if (c.includes('food') || c.includes('coffee') || c.includes('drink') || c.includes('dining')) return 'food';
    if (c.includes('stay') || c.includes('hotel')) return 'stay';
    if (c.includes('flight')) return 'flight';
    if (c.includes('travel') || c.includes('transport')) return 'travel';
    return 'activity';
  };

  const getDefaultTargetDayId = (idea) => {
    if (ideaTargetDayById[idea.id]) return ideaTargetDayById[idea.id];
    const matchingVisible = selectedItineraryDays.find(({ leg }) => leg.name === idea.leg);
    if (matchingVisible) return matchingVisible.day.id;
    const matchingAny = allDays.find(({ leg }) => leg.name === idea.leg);
    if (matchingAny) return matchingAny.day.id;
    return selectedItineraryDays[0]?.day.id || allDays[0]?.day.id || '';
  };

  const addIdeaToDay = (idea, targetDayId) => {
    const dayEntry = allDays.find((e) => e.day.id === targetDayId);
    if (!dayEntry) return;
    saveActivity(targetDayId, {
      id: `s-idea-${Date.now()}`,
      time: 'Flexible',
      kind: inferKindFromIdeaCat(idea.cat),
      title: idea.title,
      status: 'no_booking',
      meta: idea.note || '',
      conf: '',
    });
    // Ensure target leg and day are expanded so user sees the newly added item
    setCollapsedLegIds((prev) => {
      if (!prev[dayEntry.leg.id]) return prev;
      const next = { ...prev };
      delete next[dayEntry.leg.id];
      return next;
    });
    setCollapsedDayIds((prev) => {
      if (!prev[targetDayId]) return prev;
      const next = { ...prev };
      delete next[targetDayId];
      return next;
    });
    // If filtered to specific days and target day isn't visible, include it
    if (!showAllDays && !selectedDayIds.includes(targetDayId)) {
      setSelectedDayIds((prev) => [...prev, targetDayId]);
    }
    setAddedIdeaLog((prev) => {
      const existing = prev[idea.id] || [];
      return existing.includes(dayEntry.day.num)
        ? prev
        : { ...prev, [idea.id]: [...existing, dayEntry.day.num] };
    });
  };

  const removeIdea = (ideaId) => {
    setTrip((prev) => ({
      ...prev,
      ideas: prev.ideas.filter((i) => i.id !== ideaId),
    }));
  };

  const ideaLegOptions = useMemo(() => {
    const seen = new Set();
    const opts = [];
    for (const idea of trip.ideas) {
      if (idea.leg && !seen.has(idea.leg)) {
        seen.add(idea.leg);
        opts.push(idea.leg);
      }
    }
    return opts;
  }, [trip.ideas]);

  const filteredIdeas = useMemo(() => {
    const q = ideaSearch.trim().toLowerCase();
    return trip.ideas.filter((idea) => {
      if (ideaLegFilter !== 'all' && idea.leg !== ideaLegFilter) return false;
      if (!q) return true;
      return (
        idea.title.toLowerCase().includes(q)
        || (idea.note || '').toLowerCase().includes(q)
        || (idea.cat || '').toLowerCase().includes(q)
        || (idea.leg || '').toLowerCase().includes(q)
      );
    });
  }, [trip.ideas, ideaLegFilter, ideaSearch]);

  const resetMock = () => {
    setTrip(cloneTrip());
    setShowAllDays(true);
    setSelectedDayIds([MOCK_TRIP.legs[0].days[0].id]);
    setAnchorDayId(MOCK_TRIP.legs[0].days[0].id);
    setPickerOpen(false);
    setCollapsedDayIds({});
    setCollapsedLegIds({});
    setAddedIdeaLog({});
    setIdeaLegFilter('all');
    setIdeaSearch('');
    setIdeaTargetDayById({});
  };

  return (
    <div className="tm-page" onClick={() => openDayMenuId && setOpenDayMenuId(null)}>
      {/* Subtle mockup banner */}
      <div className="tm-banner">
        <span>Interactive UI Mockup · Lightweight read-first layout (in-memory sample data)</span>
        <div className="tm-banner-actions">
          <button type="button" className="tm-banner-btn" onClick={resetMock}>Reset mock data</button>
          <Link to="/" className="tm-banner-link">Back to live Trips →</Link>
        </div>
      </div>

      {/* Minimal sticky top header */}
      <header className="tm-header">
        <div className="tm-container tm-header-inner">
          <div className="tm-title-block">
            <div className="tm-title-row">
              <h1>{trip.title}</h1>
              <span className="tm-meta-pill">{trip.dateRange}</span>
              <span className="tm-meta-pill">{allDays.length} days · {trip.legs.length} legs</span>
            </div>
            <p className="tm-subtitle">{trip.subtitle} · {trip.travelers.join(', ')}</p>
          </div>

          <nav className="tm-nav" aria-label="Trip sections">
            {[
              { id: 'summary', label: 'Summary' },
              { id: 'itinerary', label: 'Itinerary' },
              { id: 'ideas', label: 'Ideas', count: trip.ideas.length },
              { id: 'bookings', label: 'Bookings', badge: bookingCounts.tobook ? `${bookingCounts.tobook} to book` : null },
              { id: 'documents', label: 'Documents', count: trip.documents.length },
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
                {trip.legs.map((leg, idx) => (
                  <React.Fragment key={leg.id}>
                    {idx > 0 && <span className="tm-ribbon-arrow" aria-hidden="true">→</span>}
                    <button
                      type="button"
                      className={`tm-ribbon-pill${legFilter === leg.id ? ' is-active' : ''}`}
                      onClick={() => setLegFilter(legFilter === leg.id ? 'all' : leg.id)}
                    >
                      <i className="tm-dot" style={{ background: leg.color }} />
                      <span>{leg.name}</span>
                      <small>{leg.nights}n</small>
                    </button>
                  </React.Fragment>
                ))}
              </div>

              <div className="tm-segmented" role="tablist" aria-label="Summary view">
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
              <CalendarSummaryView
                legs={visibleLegs}
                onSelectDay={(day, leg) => setPeek({ day, leg })}
              />
            ) : (
              <div className="tm-legs-stack">
                {visibleLegs.map((leg) => (
                  <section key={leg.id} className="tm-leg-card">
                    <header className="tm-leg-head">
                      <div className="tm-leg-accent" style={{ background: leg.color }} />
                      <div className="tm-leg-title">
                        <div className="tm-leg-name-row">
                          <h2>{leg.name}</h2>
                          <span className="tm-muted">{leg.dates} · {leg.nights} nights</span>
                        </div>
                        {summaryMode === 'detail' && (
                          <p className="tm-leg-summary">{leg.summary}</p>
                        )}
                      </div>
                      <div className="tm-leg-stay-pill">
                        <span>🛏</span> {leg.stay}
                      </div>
                    </header>

                    <ul className="tm-day-list">
                      {leg.days.map((day) => {
                        const hasFlight = day.items.some((i) => i.kind === 'flight');
                        const toBookCount = day.items.filter((i) => i.status === 'tobook').length;
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
                                  <strong className="tm-day-title">{day.title}</strong>
                                  {summaryMode === 'detail' && (
                                    <div className="tm-day-detail">
                                      {day.notes && <p className="tm-day-notes">{day.notes}</p>}
                                      <ul className="tm-inline-items">
                                        {day.items.map((item) => (
                                          <li key={item.id}>
                                            <span className="tm-inline-time">{item.time}</span>
                                            <span aria-hidden="true">{KIND_ICON[item.kind] || '•'}</span>
                                            <span className="tm-inline-title">{item.title}</span>
                                            {item.status === 'tobook' && (
                                              <span className="tm-status is-tobook">To book</span>
                                            )}
                                          </li>
                                        ))}
                                      </ul>
                                    </div>
                                  )}
                                </div>
                                <div className="tm-day-right">
                                  {hasFlight && <span className="tm-tag is-flight">✈ Flight</span>}
                                  {toBookCount > 0 && (
                                    <span className="tm-tag is-warn">{toBookCount} to book</span>
                                  )}
                                  <span className="tm-day-count">{day.items.length} items</span>
                                  <span className="tm-chevron" aria-hidden="true">›</span>
                                </div>
                              </div>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </section>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ================= ITINERARY (EXPANDED SCHEDULE VIEW) ================= */}
        {section === 'itinerary' && (
          <div className="tm-itinerary">
            {/* Compact single-row Itinerary toolbar (day selector opens on demand) */}
            <div className="tm-itin-toolbar">
              <div className="tm-itin-status">
                <strong>{selectionSummary}</strong>
                {!showAllDays && (
                  <button
                    type="button"
                    className="tm-link-inline"
                    onClick={() => {
                      setShowAllDays(true);
                      setRangeMode(false);
                    }}
                  >
                    Show all
                  </button>
                )}
              </div>

              <div className="tm-itin-actions">
                <button
                  type="button"
                  className={`tm-tool-btn${pickerOpen ? ' is-active' : ''}`}
                  aria-expanded={pickerOpen}
                  onClick={() => setPickerOpen((v) => !v)}
                >
                  Select range {pickerOpen ? '▴' : '▾'}
                </button>
                {selectedItineraryDays.length > 1 && (
                  <div className="tm-btn-group" role="group" aria-label="Collapse or expand visible days">
                    <button
                      type="button"
                      className="tm-tool-btn"
                      disabled={!anyVisibleExpanded}
                      onClick={collapseVisibleDays}
                    >
                      Collapse all
                    </button>
                    <button
                      type="button"
                      className="tm-tool-btn"
                      disabled={!anyVisibleCollapsed}
                      onClick={expandVisibleDays}
                    >
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
                  {showIdeasPane ? `Hide ideas (${trip.ideas.length})` : `Show ideas (${trip.ideas.length})`}
                </button>
                <button
                  type="button"
                  className={`tm-tool-btn${pinEditControls ? ' is-active' : ''}`}
                  onClick={() => setPinEditControls((v) => !v)}
                  title="Keep edit, reorder, and delete buttons visible on every item"
                >
                  {pinEditControls ? 'Edit controls: On' : 'Edit controls'}
                </button>
                <button
                  type="button"
                  className="tm-btn-primary tm-btn-sm"
                  onClick={() => setEditingDayState({ day: null, leg: trip.legs[trip.legs.length - 1], isNew: true })}
                >
                  + Add day
                </button>
              </div>
            </div>

            {/* On-demand collapsible Day & Leg Selection Panel */}
            {pickerOpen && (
              <section className="tm-card tm-picker-panel" aria-label="Day selection panel">
                <div className="tm-picker-row">
                  <span className="tm-picker-label">By leg</span>
                  <div className="tm-picker-pills">
                    <button
                      type="button"
                      className={`tm-ribbon-pill${showAllDays ? ' is-active' : ''}`}
                      onClick={() => {
                        setShowAllDays(true);
                        setRangeMode(false);
                      }}
                    >
                      All days ({allDays.length})
                    </button>
                    {trip.legs.map((leg) => (
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
                  <button type="button" className="tm-picker-done" onClick={() => setPickerOpen(false)}>
                    Hide
                  </button>
                </div>

                <div className="tm-picker-row">
                  <span className="tm-picker-label">By day</span>
                  <div className="tm-slider-shell">
                    <button
                      type="button"
                      className="tm-slide-arrow"
                      onClick={() => slideDays(-1)}
                      aria-label="Scroll days left"
                    >
                      ‹
                    </button>
                    <div className="tm-day-slider" ref={daySliderRef} role="listbox" aria-multiselectable="true" aria-label="Select days">
                      {allDays.map(({ day, leg }) => {
                        const isSelected = !showAllDays && selectedDayIds.includes(day.id);
                        const isAnchor = !showAllDays && rangeMode && anchorDayId === day.id;
                        return (
                          <button
                            key={day.id}
                            type="button"
                            role="option"
                            aria-selected={isSelected}
                            className={`tm-itin-day-pill${isSelected ? ' is-active' : ''}${isAnchor ? ' is-anchor' : ''}`}
                            style={{
                              borderTopColor: leg.color,
                              ...(isSelected ? { borderColor: leg.color, background: leg.tint } : {}),
                            }}
                            onClick={(e) => handleDayPillClick(day.id, e)}
                            title={`Day ${day.num} (${leg.name}) — Click to view · Shift-click for range · Ctrl-click to multi-select`}
                          >
                            <span className="tm-pill-day">Day {day.num}</span>
                            <small>{day.shortDate}</small>
                          </button>
                        );
                      })}
                    </div>
                    <button
                      type="button"
                      className="tm-slide-arrow"
                      onClick={() => slideDays(1)}
                      aria-label="Scroll days right"
                    >
                      ›
                    </button>
                  </div>
                </div>

                <div className="tm-picker-foot">
                  <button
                    type="button"
                    className={`tm-tool-btn${rangeMode ? ' is-active' : ''}`}
                    onClick={() => {
                      setShowAllDays(false);
                      setRangeMode((v) => !v);
                    }}
                  >
                    {rangeMode ? 'Click an end day…' : 'Pick range by clicking'}
                  </button>
                  <span className="tm-toolbar-hint">
                    Tip: Shift-click for a range · Ctrl/Cmd-click to toggle multiple days
                  </span>
                </div>
              </section>
            )}

            {/* Workspace: independently scrollable Days pane + optional Ideas side pane */}
            <div className={`tm-itin-workspace${showIdeasPane ? ' has-ideas' : ''}`}>
              <div className="tm-itin-days-pane">
                {/* Selected leg groups & day cards (collapsible at both leg and day levels) */}
                <div className={`tm-itin-stack${pinEditControls ? ' is-editing' : ''}`}>
              {selectedLegGroups.map(({ leg, days: legDays }) => {
                const isLegCollapsed = Boolean(collapsedLegIds[leg.id]);
                const legAllDaysCollapsed = legDays.every((d) => Boolean(collapsedDayIds[d.id]));

                const toggleLegDays = (collapse) => {
                  if (isLegCollapsed && !collapse) {
                    setCollapsedLegIds((prev) => {
                      const next = { ...prev };
                      delete next[leg.id];
                      return next;
                    });
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
                        title={isLegCollapsed ? `Expand ${leg.name}` : `Collapse ${leg.name}`}
                      >
                        <span className="tm-fold-chevron" aria-hidden="true">{isLegCollapsed ? '▸' : '▾'}</span>
                        <span className="tm-leg-kicker" style={{ color: leg.color }}>Leg</span>
                        <strong className="tm-leg-bar-name">{leg.name}</strong>
                        <span className="tm-muted">
                          {leg.dates} · {legDays.length} {legDays.length === 1 ? 'day' : 'days'}
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
                          const draft = quickAddByDay[day.id] || { time: '', title: '', kind: 'activity' };
                          const isCollapsed = Boolean(collapsedDayIds[day.id]);

                          return (
                            <section
                              key={day.id}
                              className={`tm-card tm-itin-card${isCollapsed ? ' is-collapsed' : ''}${dragOverDayId === day.id ? ' is-drop-target' : ''}`}
                              onDragOver={(e) => {
                                if (!showIdeasPane) return;
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
                                const ideaId = e.dataTransfer.getData('text/trip-idea-id');
                                if (!ideaId) return;
                                const idea = trip.ideas.find((i) => i.id === ideaId);
                                if (idea) addIdeaToDay(idea, day.id);
                              }}
                            >
                              <header className="tm-itin-head">
                                <button
                                  type="button"
                                  className="tm-day-fold-btn"
                                  aria-expanded={!isCollapsed}
                                  onClick={() => toggleDayCollapsed(day.id)}
                                  title={isCollapsed ? 'Expand day' : 'Collapse day'}
                                >
                                  <span className="tm-fold-chevron" aria-hidden="true">{isCollapsed ? '▸' : '▾'}</span>
                                  <div>
                                    <span className="tm-day-kicker">
                                      Day {day.num} · {day.weekday}, {day.shortDate}
                                    </span>
                                    <h2>{day.title}</h2>
                                  </div>
                                </button>

                                {/* Calm Day-level CRUD controls */}
                                <div className="tm-day-crud">
                                  {isCollapsed && (
                                    <span className="tm-day-count">{day.items.length} items</span>
                                  )}
                                  {day.stay && <span className="tm-leg-stay-pill">🛏 {day.stay}</span>}
                                  {!isCollapsed && (
                                    <button
                                      type="button"
                                      className="tm-tool-btn"
                                      onClick={() => setEditingActivityState({ day, leg, item: null })}
                                    >
                                      + Add item
                                    </button>
                                  )}
                                  <div className="tm-menu-wrap" onClick={(e) => e.stopPropagation()}>
                                    <button
                                      type="button"
                                      className="tm-more-btn"
                                      aria-label={`Day ${day.num} actions`}
                                      aria-expanded={openDayMenuId === day.id}
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
                                            setEditingDayState({ day: null, leg, isNew: true, insertRefId: day.id, insertPosition: 'before' });
                                          }}
                                        >
                                          Insert day before
                                        </button>
                                        <button
                                          type="button"
                                          role="menuitem"
                                          onClick={() => {
                                            setOpenDayMenuId(null);
                                            setEditingDayState({ day: null, leg, isNew: true, insertRefId: day.id, insertPosition: 'after' });
                                          }}
                                        >
                                          Insert day after
                                        </button>
                                        <hr />
                                        <button
                                          type="button"
                                          role="menuitem"
                                          className="is-danger"
                                          onClick={() => deleteDay(day.id)}
                                        >
                                          Delete day
                                        </button>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </header>

                              {!isCollapsed && (
                                <>
                                  {day.notes && <p className="tm-notes-text tm-itin-notes">{day.notes}</p>}

                                  {/* Activity rows with hover-revealed (or pinned) CRUD controls */}
                                  <ul className="tm-timeline">
                                    {day.items.map((item, itemIdx) => (
                                      <li key={item.id} className="tm-timeline-item">
                                        <button
                                          type="button"
                                          className="tm-timeline-main"
                                          onClick={() => setEditingActivityState({ day, leg, item })}
                                          title="Click to edit activity"
                                        >
                                          <span className="tm-timeline-time">{item.time}</span>
                                          <span className="tm-timeline-icon" aria-hidden="true">{KIND_ICON[item.kind] || '•'}</span>
                                          <div className="tm-timeline-body">
                                            <div className="tm-peek-title-row">
                                              <strong>{item.title}</strong>
                                              {item.status && item.status !== 'no_booking' && (
                                                <span className={`tm-status is-${item.status}`}>{STATUS_LABEL[item.status]}</span>
                                              )}
                                            </div>
                                            {(item.meta || item.conf) && (
                                              <span className="tm-muted">
                                                {item.meta}
                                                {item.conf ? `${item.meta ? ' · ' : ''}Conf # ${item.conf}` : ''}
                                              </span>
                                            )}
                                          </div>
                                        </button>

                                        <div className="tm-item-crud">
                                          <button
                                            type="button"
                                            disabled={itemIdx === 0}
                                            title="Move up"
                                            onClick={() => moveActivity(day.id, item.id, -1)}
                                          >
                                            ↑
                                          </button>
                                          <button
                                            type="button"
                                            disabled={itemIdx === day.items.length - 1}
                                            title="Move down"
                                            onClick={() => moveActivity(day.id, item.id, 1)}
                                          >
                                            ↓
                                          </button>
                                          <button
                                            type="button"
                                            title="Edit activity"
                                            onClick={() => setEditingActivityState({ day, leg, item })}
                                          >
                                            Edit
                                          </button>
                                          <button
                                            type="button"
                                            className="is-danger"
                                            title="Delete activity"
                                            onClick={() => deleteActivity(day.id, item.id)}
                                          >
                                            ×
                                          </button>
                                        </div>
                                      </li>
                                    ))}
                                    {day.items.length === 0 && (
                                      <li className="tm-empty-row">No activities yet — add one below.</li>
                                    )}
                                  </ul>

                                  {/* Lightweight inline quick-add bar at bottom of day */}
                                  <form className="tm-quick-add" onSubmit={(e) => submitQuickAdd(day.id, e)}>
                                    <select
                                      aria-label="Activity type"
                                      value={draft.kind || 'activity'}
                                      onChange={(e) => setQuickAddByDay((p) => ({ ...p, [day.id]: { ...draft, kind: e.target.value } }))}
                                    >
                                      {KIND_OPTIONS.map((k) => (
                                        <option key={k.id} value={k.id}>{KIND_ICON[k.id]} {k.label}</option>
                                      ))}
                                    </select>
                                    <input
                                      type="text"
                                      className="tm-qa-time"
                                      placeholder="Time"
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
                                    <button type="submit" className="tm-tool-btn" disabled={!(draft.title || '').trim()}>
                                      Add
                                    </button>
                                  </form>
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
                      <span className="tm-muted">{filteredIdeas.length} of {trip.ideas.length} · Click Add or drag onto a day</span>
                    </div>
                    <button
                      type="button"
                      className="tm-close-btn"
                      aria-label="Hide ideas panel"
                      onClick={() => setShowIdeasPane(false)}
                    >
                      ×
                    </button>
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
                      const addedDays = addedIdeaLog[idea.id] || [];
                      return (
                        <article
                          key={idea.id}
                          className="tm-card tm-idea-pane-card"
                          draggable
                          onDragStart={(e) => {
                            e.dataTransfer.setData('text/trip-idea-id', idea.id);
                            e.dataTransfer.effectAllowed = 'copy';
                          }}
                        >
                          <div className="tm-idea-meta">
                            <span className="tm-chip-subtle">{idea.leg}</span>
                            <span className="tm-muted">{idea.cat}</span>
                            <button
                              type="button"
                              className="tm-idea-remove"
                              title="Remove from ideas"
                              onClick={() => removeIdea(idea.id)}
                            >
                              ×
                            </button>
                          </div>
                          <h4>{idea.title}</h4>
                          {idea.note && <p className="tm-muted">{idea.note}</p>}

                          {addedDays.length > 0 && (
                            <div className="tm-idea-added-row">
                              {addedDays.map((num) => (
                                <span key={num} className="tm-status is-confirmed">✓ Added to Day {num}</span>
                              ))}
                            </div>
                          )}

                          <div className="tm-idea-add-row">
                            <select
                              aria-label={`Target day for ${idea.title}`}
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
                              disabled={!targetDayId}
                              onClick={() => addIdeaToDay(idea, targetDayId)}
                            >
                              + Add
                            </button>
                          </div>
                        </article>
                      );
                    })}
                    {filteredIdeas.length === 0 && (
                      <div className="tm-empty-row">No ideas match this filter.</div>
                    )}
                  </div>
                </aside>
              )}
            </div>
          </div>
        )}

        {/* ================= IDEAS ================= */}
        {section === 'ideas' && (
          <div className="tm-section-stack">
            <div className="tm-section-intro">
              <h2>Ideas Pool</h2>
              <p className="tm-muted">Places and experiences saved for later — slot them into the itinerary whenever you’re ready.</p>
            </div>
            <div className="tm-ideas-grid">
              {trip.ideas.map((idea) => (
                <article key={idea.id} className="tm-card tm-idea-card">
                  <div className="tm-idea-meta">
                    <span className="tm-chip-subtle">{idea.leg}</span>
                    <span className="tm-muted">{idea.cat}</span>
                  </div>
                  <h3>{idea.title}</h3>
                  <p className="tm-muted">{idea.note}</p>
                </article>
              ))}
            </div>
          </div>
        )}

        {/* ================= BOOKINGS ================= */}
        {section === 'bookings' && (
          <div className="tm-section-stack">
            <div className="tm-readiness-strip">
              <div className="tm-stat"><strong>{bookingCounts.confirmed}</strong><span>Confirmed</span></div>
              <div className="tm-stat"><strong>{bookingCounts.booked}</strong><span>Booked</span></div>
              <div className="tm-stat is-warn"><strong>{bookingCounts.tobook}</strong><span>To book</span></div>
            </div>
            {['Flights', 'Stays', 'Activities & Dining'].map((group) => {
              const rows = trip.bookings.filter((b) => b.group === group);
              return (
                <section key={group} className="tm-card tm-table-card">
                  <h3 className="tm-table-title">{group}</h3>
                  <ul className="tm-booking-list">
                    {rows.map((row) => (
                      <li key={row.id} className="tm-booking-row">
                        <div>
                          <strong>{row.title}</strong>
                          <span className="tm-muted">{row.dates}{row.conf ? ` · Conf # ${row.conf}` : ''}</span>
                        </div>
                        <div className="tm-booking-right">
                          <span className="tm-price">{row.price}</span>
                          <span className={`tm-status is-${row.status}`}>{STATUS_LABEL[row.status]}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
          </div>
        )}

        {/* ================= DOCUMENTS ================= */}
        {section === 'documents' && (
          <div className="tm-section-stack">
            <div className="tm-section-intro">
              <h2>Documents & Vouchers</h2>
              <p className="tm-muted">All tickets, hotel vouchers, and receipts in one place.</p>
            </div>
            <div className="tm-docs-grid">
              {trip.documents.map((doc) => (
                <button
                  key={doc.id}
                  type="button"
                  className="tm-card tm-doc-card"
                  onClick={() => setPreviewDoc(doc)}
                >
                  <div className="tm-doc-top">
                    <span className="tm-doc-icon" aria-hidden="true">📄</span>
                    <span className="tm-chip-subtle">{doc.category}</span>
                  </div>
                  <strong className="tm-doc-name">{doc.name}</strong>
                  <span className="tm-muted">{doc.linked} · {doc.size}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </main>

      <DayPeekDrawer
        day={peek?.day}
        leg={peek?.leg}
        onClose={() => setPeek(null)}
        onOpenItinerary={jumpToItinerary}
      />

      {editingDayState && (
        <DayEditDrawer
          day={editingDayState.day}
          leg={editingDayState.leg}
          legs={trip.legs}
          isNew={editingDayState.isNew}
          onClose={() => setEditingDayState(null)}
          onSave={saveDay}
          onDelete={deleteDay}
        />
      )}

      {editingActivityState && (
        <ActivityEditDrawer
          day={editingActivityState.day}
          leg={editingActivityState.leg}
          item={editingActivityState.item}
          onClose={() => setEditingActivityState(null)}
          onSave={saveActivity}
          onDelete={deleteActivity}
        />
      )}

      {previewDoc && (
        <div className="tm-drawer-backdrop" onClick={() => setPreviewDoc(null)} role="presentation">
          <div className="tm-doc-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={previewDoc.name}>
            <header className="tm-drawer-head">
              <div>
                <span className="tm-eyebrow">{previewDoc.category} · {previewDoc.linked}</span>
                <h2>{previewDoc.name}</h2>
              </div>
              <button type="button" className="tm-icon-close" onClick={() => setPreviewDoc(null)} aria-label="Close">×</button>
            </header>
            <div className="tm-doc-preview-body">
              <p>{previewDoc.note}</p>
              <div className="tm-doc-placeholder">PDF Preview Placeholder ({previewDoc.size})</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
