import React, { useMemo, useState } from 'react';
import { dayDiff } from '@bldrdojo/timezones';
import { addDays } from './TripCalendar';
import { CommentCountButton } from './TripCollaboration';

function sumByCurrency(stops) {
  const sums = {};
  for (const s of stops) {
    if (s.price == null || s.price === '') continue;
    const cur = s.currency || '';
    sums[cur] = (sums[cur] || 0) + Number(s.price);
  }
  return Object.entries(sums).sort(([a], [b]) => (a === '' ? -1 : b === '' ? 1 : a.localeCompare(b)));
}

function moneyText(amount, currency) {
  const abs = Math.abs(amount).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  const sign = amount < 0 ? '-' : '';
  return currency ? `${sign}${currency} ${abs}` : `${sign}$${abs}`;
}

function totalsLabel(stops) {
  const parts = sumByCurrency(stops).map(([c, v]) => moneyText(v, c));
  return parts.length ? parts.join(' · ') : '$0';
}

function ShiftDatesModal({ days, formatDay, onClose, onShift }) {
  const firstDate = days[0]?.date || '';
  const lastDate = days[days.length - 1]?.date || '';
  const [newStart, setNewStart] = useState(firstDate);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const delta = firstDate && newStart ? dayDiff(firstDate, newStart) : 0;
  const previewEnd = lastDate ? addDays(lastDate, delta) : '';

  const bump = (n) => {
    if (!newStart) return;
    setNewStart(addDays(newStart, n));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!delta) { onClose(); return; }
    setBusy(true);
    setError('');
    try {
      await onShift({ start_date: newStart });
      onClose();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" onMouseDown={onClose} role="presentation">
      <form className="trip-modal" onSubmit={submit} onMouseDown={(e) => e.stopPropagation()} onClick={(e) => e.stopPropagation()}>
        <h3>Shift all trip dates</h3>
        <p className="trip-muted">
          Moves every day, stop, and lodging assignment together while keeping the route intact.
        </p>
        <label>
          New start date
          <input type="date" value={newStart} onChange={(e) => setNewStart(e.target.value)} required />
        </label>
        <div className="trip-quick-bumps">
          {[-7, -3, -1, 1, 3, 7].map((n) => (
            <button key={n} type="button" onClick={() => bump(n)}>{n > 0 ? `+${n}d` : `${n}d`}</button>
          ))}
        </div>
        {delta !== 0 && (
          <p className="trip-hint">
            Shifting by <strong>{delta > 0 ? `+${delta}` : delta} {Math.abs(delta) === 1 ? 'day' : 'days'}</strong>:{' '}
            {formatDay({ date: firstDate })} – {formatDay({ date: lastDate })} →{' '}
            <strong>{formatDay({ date: newStart })} – {formatDay({ date: previewEnd })}</strong>
          </p>
        )}
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy || delta === 0}>
            {busy ? 'Shifting…' : 'Shift dates'}
          </button>
        </div>
      </form>
    </div>
  );
}

function InsertDayModal({ initialDate, initialLegId = '', days = [], legs, onClose, onInsert }) {
  const [date, setDate] = useState(initialDate || '');
  const [title, setTitle] = useState('');
  const [legId, setLegId] = useState(initialLegId ? String(initialLegId) : '');
  const [ripple, setRipple] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const { forcedLeg, allowedLegs } = useMemo(() => {
    if (!legs.length) return { forcedLeg: null, allowedLegs: [] };
    if (!date) return { forcedLeg: null, allowedLegs: legs };
    const post = days
      .map((d) => ({
        date: ripple && d.date >= date ? addDays(d.date, 1) : d.date,
        leg: d.leg || null,
      }))
      .sort((a, b) => a.date.localeCompare(b.date));
    const prev = [...post].reverse().find((r) => r.date < date) || null;
    const next = post.find((r) => r.date > date) || null;
    if (prev?.leg && prev.leg === next?.leg) {
      const enclosing = legs.find((l) => l.id === prev.leg) || null;
      return { forcedLeg: enclosing, allowedLegs: enclosing ? [enclosing] : [] };
    }
    const validIds = new Set();
    if (prev?.leg) validIds.add(prev.leg);
    if (next?.leg) validIds.add(next.leg);
    for (const l of legs) {
      if (!(l.assigned_day_ids || []).length) validIds.add(l.id);
    }
    return { forcedLeg: null, allowedLegs: legs.filter((l) => validIds.has(l.id)) };
  }, [date, ripple, days, legs]);

  const effectiveLegId = forcedLeg
    ? String(forcedLeg.id)
    : (legId && allowedLegs.some((l) => String(l.id) === legId) ? legId : '');

  const submit = async (e) => {
    e.preventDefault();
    if (!date) { setError('Pick a date.'); return; }
    setBusy(true);
    setError('');
    try {
      await onInsert({ date, title: title.trim(), leg_id: effectiveLegId ? Number(effectiveLegId) : null, ripple });
      onClose();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" onMouseDown={onClose} role="presentation">
      <form className="trip-modal" onSubmit={submit} onMouseDown={(e) => e.stopPropagation()} onClick={(e) => e.stopPropagation()}>
        <h3>Insert a day</h3>
        <label>
          Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
        </label>
        <label>
          Title (optional)
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g., Extra day in Chiang Mai" />
        </label>
        {legs.length > 0 && (
          forcedLeg ? (
            <p className="trip-muted trip-day-leg-readonly">
              Leg: <strong>{forcedLeg.name}</strong> (inserted inside this leg)
            </p>
          ) : allowedLegs.length > 0 && (
            <label>
              Leg (adjacent or empty legs)
              <select value={effectiveLegId} onChange={(e) => setLegId(e.target.value)}>
                <option value="">Auto / None</option>
                {allowedLegs.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </label>
          )
        )}
        <label className="trip-check">
          <input type="checkbox" checked={ripple} onChange={(e) => setRipple(e.target.checked)} />
          Push this date and all later days forward by +1 day (ripple)
        </label>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy}>
            {busy ? 'Inserting…' : 'Insert day'}
          </button>
        </div>
      </form>
    </div>
  );
}

function MoveSwapDayModal({ day, days, formatDay, onClose, onSwap, onMove }) {
  const [tab, setTab] = useState('swap');
  const otherDays = days.filter((d) => d.id !== day.id);
  const [otherId, setOtherId] = useState(otherDays[0]?.id ? String(otherDays[0].id) : '');
  const [targetDate, setTargetDate] = useState(day.date);
  const [mode, setMode] = useState('shift');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (tab === 'swap') {
        if (!otherId) { setError('Pick a day to swap with.'); setBusy(false); return; }
        await onSwap({ day_a_id: day.id, day_b_id: Number(otherId) });
      } else {
        if (!targetDate) { setError('Pick a target date.'); setBusy(false); return; }
        await onMove({ day_id: day.id, target_date: targetDate, mode });
      }
      onClose();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" onMouseDown={onClose} role="presentation">
      <form className="trip-modal" onSubmit={submit} onMouseDown={(e) => e.stopPropagation()} onClick={(e) => e.stopPropagation()}>
        <h3>Move or swap · {formatDay(day)}</h3>
        <div className="trip-subtabs">
          <button type="button" className={tab === 'swap' ? 'is-active' : ''} onClick={() => setTab('swap')}>
            Swap with another day
          </button>
          <button type="button" className={tab === 'move' ? 'is-active' : ''} onClick={() => setTab('move')}>
            Move to a date
          </button>
        </div>
        {tab === 'swap' ? (
          <label>
            Swap full itinerary with
            <select value={otherId} onChange={(e) => setOtherId(e.target.value)} disabled={!otherDays.length}>
              {otherDays.map((d) => <option key={d.id} value={d.id}>{formatDay(d)}</option>)}
            </select>
          </label>
        ) : (
          <>
            <label>
              Target date
              <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} required />
            </label>
            <label>
              If target date is occupied
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="shift">Shift days in between by ±1 day (reorder)</option>
                <option value="empty">Only move if date is empty</option>
              </select>
            </label>
          </>
        )}
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="submit" className="trip-primary" disabled={busy || (tab === 'swap' && !otherDays.length)}>
            {busy ? 'Applying…' : (tab === 'swap' ? 'Swap days' : 'Move day')}
          </button>
        </div>
      </form>
    </div>
  );
}

function RemoveDayModal({ day, formatDay, hasLater, onClose, onRemove }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const run = async (ripple) => {
    setBusy(true);
    setError('');
    try {
      await onRemove({ day_id: day.id, ripple });
      onClose();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="trip-modal-backdrop" onMouseDown={onClose} role="presentation">
      <div className="trip-modal" onMouseDown={(e) => e.stopPropagation()} onClick={(e) => e.stopPropagation()} role="dialog">
        <h3>Remove {formatDay(day)}?</h3>
        <p className="trip-muted">
          This deletes the day and its {(day.stops || []).length} {(day.stops || []).length === 1 ? 'item' : 'items'}.
        </p>
        {error && <p className="trip-error">{error}</p>}
        <div className="trip-modal-actions">
          <button type="button" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className="trip-danger-text" disabled={busy} onClick={() => run(false)}>
            Delete (leave gap)
          </button>
          {hasLater && (
            <button type="button" className="trip-primary" disabled={busy} onClick={() => run(true)}>
              Delete &amp; pull later days −1d
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function RouteWorkspace({
  trip,
  days,
  legs = [],
  formatDay,
  renderDayZones,
  renderDayCounts,
  lodgingLabel,
  onOpenBulkDays,
  onAddDay,
  onEditDay,
  onEditLodging,
  onAddLeg,
  onEditLeg,
  onShiftDates,
  onInsertDay,
  onRemoveDay,
  onSwapDays,
  onMoveDay,
  onAdjustLeg,
  onJumpToDay,
  onOpenLegInCalendar,
  canEdit = true,
  commentIndex = null,
  onOpenComments,
}) {
  const [showShift, setShowShift] = useState(false);
  const [insertTarget, setInsertTarget] = useState(null);
  const [moveSwapDay, setMoveSwapDay] = useState(null);
  const [removeTarget, setRemoveTarget] = useState(null);
  const [busyLegId, setBusyLegId] = useState(null);

  const lodgings = trip.lodgings || [];
  const totalStops = days.reduce((n, d) => n + (d.stops || []).length, 0);
  const nightsBooked = days.filter((d) => d.lodging || d.lodging_id).length;
  const dayNumberById = useMemo(() => new Map(days.map((d, i) => [d.id, i + 1])), [days]);
  const lastDate = days[days.length - 1]?.date || '';

  const legSections = useMemo(() => {
    const orderedLegs = [...legs].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id));
    const sections = orderedLegs.map((leg, idx) => ({
      leg,
      idx,
      totalLegs: orderedLegs.length,
      days: days.filter((d) => d.leg === leg.id),
    }));
    const ungrouped = days.filter((d) => !d.leg || !orderedLegs.some((l) => l.id === d.leg));
    return { sections, ungrouped };
  }, [legs, days]);

  const runLegAction = async (legId, action, ripple = true) => {
    if (action === 'remove_day') {
      const sec = legSections.sections.find((s) => s.leg.id === legId);
      const last = sec?.days[sec.days.length - 1];
      if (!last) return;
      if (!window.confirm(`Remove the last day of ${sec.leg.name} (${formatDay(last)}) and pull later days back 1 day?`)) return;
    }
    setBusyLegId(legId);
    try {
      await onAdjustLeg({ leg_id: legId, action, ripple });
    } finally {
      setBusyLegId(null);
    }
  };

  const renderDayRow = (day) => {
    const firstNote = (day.notes || '').split('\n').map((l) => l.trim()).find(Boolean) || '';
    const fullLodging = day.lodging
      ? (lodgings.find((l) => l.id === day.lodging.id) || day.lodging)
      : null;
    const num = dayNumberById.get(day.id) || 0;
    return (
      <li key={day.id} className="trip-route-row">
        <button
          type="button"
          className="trip-route-main"
          onClick={() => onJumpToDay(day)}
          title="Open this day in Schedule"
        >
          <span className="trip-route-num">Day {num}</span>
          <div className="trip-route-body">
            <div className="trip-route-head">
              <strong>{formatDay(day)}</strong>
              {renderDayZones(day)}
              {renderDayCounts(day.stops)}
            </div>
            {firstNote && <p className="trip-route-note">{firstNote}</p>}
          </div>
        </button>
        <div className="trip-route-stay">
          {fullLodging ? (
            canEdit ? (
              <button
                type="button"
                className="trip-route-lodging-btn"
                onClick={() => onEditLodging(fullLodging, [day.id])}
                title="Edit lodging"
              >
                🛏 {lodgingLabel(fullLodging)}
              </button>
            ) : (
              <span className="trip-route-lodging-btn">🛏 {lodgingLabel(fullLodging)}</span>
            )
          ) : canEdit ? (
            <button
              type="button"
              className="trip-route-lodging-btn is-empty"
              onClick={() => onEditLodging(null, [day.id])}
              title="Assign lodging"
            >
              + Lodging
            </button>
          ) : null}
        </div>
        <div className="trip-route-btns">
          {onOpenComments && (
            <CommentCountButton
              openCount={commentIndex?.openByKey?.[`day:${day.id}`] || 0}
              totalCount={commentIndex?.totalByKey?.[`day:${day.id}`] || 0}
              label={formatDay(day)}
              onClick={() => onOpenComments({ type: 'day', id: day.id, label: formatDay(day) })}
            />
          )}
          {canEdit && (
            <>
              <button
                type="button"
                title="Insert a new day before this date (pushing later days +1)"
                onClick={() => setInsertTarget({ date: day.date, legId: day.leg || '' })}
              >
                + Before
              </button>
              {days.length > 1 && (
                <button type="button" onClick={() => setMoveSwapDay(day)} title="Swap with another day or move to a different date">
                  Move/Swap
                </button>
              )}
              <button type="button" onClick={() => onEditDay(day)}>Edit</button>
              <button type="button" className="trip-danger-text" onClick={() => setRemoveTarget(day)}>Remove</button>
            </>
          )}
        </div>
      </li>
    );
  };

  return (
    <div className="trip-workspace-panel">
      <div className="trip-route-toolbar">
        <div className="trip-route-stats">
          <span><strong>{days.length}</strong> {days.length === 1 ? 'day' : 'days'}</span>
          {legs.length > 0 && <span><strong>{legs.length}</strong> {legs.length === 1 ? 'leg' : 'legs'}</span>}
          <span><strong>{nightsBooked}</strong> / {days.length} lodging assigned</span>
          <span><strong>{totalStops}</strong> {totalStops === 1 ? 'item' : 'items'} scheduled</span>
        </div>
        {canEdit && (
          <div className="trip-route-actions">
            <button type="button" className="trip-primary" onClick={onAddLeg}>+ Add leg</button>
            {days.length > 0 && (
              <button type="button" onClick={() => setShowShift(true)}>Shift dates…</button>
            )}
            <button
              type="button"
              onClick={() => setInsertTarget({ date: lastDate ? addDays(lastDate, 1) : '', legId: '' })}
            >
              Insert day…
            </button>
            <button type="button" onClick={onOpenBulkDays}>Plan days outline</button>
            <button type="button" onClick={() => onEditLodging(null, [])}>+ Lodging</button>
          </div>
        )}
      </div>

      {legSections.sections.length > 0 && (
        <div className="trip-leg-arc" aria-label="Trip route legs">
          {legSections.sections.map(({ leg, days: legDays }, i) => {
            const stayNames = [...new Set(legDays.map((d) => d.lodging?.name).filter(Boolean))];
            return (
              <React.Fragment key={leg.id}>
                {i > 0 && <span className="trip-leg-arrow" aria-hidden="true">→</span>}
                <button
                  type="button"
                  className="trip-leg-chip"
                  onClick={() => (legDays.length ? onOpenLegInCalendar(leg) : onEditLeg(leg))}
                  title={legDays.length ? `Open ${leg.name} in Calendar` : `Edit ${leg.name}`}
                >
                  <strong>{leg.name}</strong>
                  <span>{legDays.length}d{stayNames.length ? ` · ${stayNames[0]}` : ''}</span>
                </button>
              </React.Fragment>
            );
          })}
        </div>
      )}

      {!days.length && !legs.length ? (
        <div className="trip-empty-card">
          <p>No days in this trip yet.</p>
          <p className="trip-muted">Use <strong>Plan days outline</strong> or <strong>Insert day…</strong> to map out your route.</p>
          <div className="trip-route-actions" style={{ justifyContent: 'center', marginTop: '0.6rem' }}>
            <button type="button" className="trip-primary" onClick={onAddDay}>+ Add first day</button>
          </div>
        </div>
      ) : (
        <div className="trip-route-groups">
          {legSections.sections.map(({ leg, idx, totalLegs, days: legDays }) => {
            const spanText = legDays.length
              ? `${formatDay({ date: legDays[0].date })}${legDays.length > 1 ? ` – ${formatDay({ date: legDays[legDays.length - 1].date })}` : ''} · ${legDays.length} ${legDays.length === 1 ? 'day' : 'days'}`
              : 'No days assigned';
            const busy = busyLegId === leg.id;
            return (
              <section key={leg.id} className="trip-leg-card">
                <header className="trip-leg-head">
                  <div className="trip-leg-title">
                    <h4>{leg.name}</h4>
                    <span className="trip-muted">{spanText}</span>
                    {leg.location && <span className="tag">{leg.location}</span>}
                  </div>
                  <div className="trip-route-btns">
                    {onOpenComments && (
                      <CommentCountButton
                        openCount={commentIndex?.openByKey?.[`leg:${leg.id}`] || 0}
                        totalCount={commentIndex?.totalByKey?.[`leg:${leg.id}`] || 0}
                        label={`Leg: ${leg.name}`}
                        onClick={() => onOpenComments({ type: 'leg', id: leg.id, label: leg.name })}
                      />
                    )}
                    {canEdit && (
                      <>
                        <button
                          type="button"
                          disabled={busy}
                          title="Add 1 day to this leg (shifts later days +1)"
                          onClick={() => runLegAction(leg.id, 'add_day', true)}
                        >
                          +1 day
                        </button>
                        {legDays.length > 0 && (
                          <button
                            type="button"
                            disabled={busy}
                            title="Remove last day of this leg (pulls later days −1)"
                            onClick={() => runLegAction(leg.id, 'remove_day', true)}
                          >
                            −1 day
                          </button>
                        )}
                        <button
                          type="button"
                          disabled={busy || idx === 0}
                          title="Move leg earlier"
                          onClick={() => runLegAction(leg.id, 'move_up')}
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          disabled={busy || idx === totalLegs - 1}
                          title="Move leg later"
                          onClick={() => runLegAction(leg.id, 'move_down')}
                        >
                          ↓
                        </button>
                      </>
                    )}
                    {legDays.length > 0 && (
                      <button type="button" onClick={() => onOpenLegInCalendar(leg)}>Calendar</button>
                    )}
                    {canEdit && <button type="button" onClick={() => onEditLeg(leg)}>Edit leg</button>}
                  </div>
                </header>
                {leg.notes && <p className="trip-leg-notes">{leg.notes}</p>}
                {legDays.length > 0 ? (
                  <ol className="trip-route-list">{legDays.map(renderDayRow)}</ol>
                ) : (
                  <p className="trip-muted trip-leg-empty">No days assigned yet. Click <strong>Edit leg</strong> or <strong>+1 day</strong>.</p>
                )}
              </section>
            );
          })}

          {legSections.ungrouped.length > 0 && (
            <section className={legSections.sections.length > 0 ? 'trip-leg-card is-ungrouped' : ''}>
              {legSections.sections.length > 0 && (
                <header className="trip-leg-head">
                  <div className="trip-leg-title">
                    <h4>Ungrouped days</h4>
                    <span className="trip-muted">{legSections.ungrouped.length} {legSections.ungrouped.length === 1 ? 'day' : 'days'}</span>
                  </div>
                </header>
              )}
              <ol className="trip-route-list">{legSections.ungrouped.map(renderDayRow)}</ol>
            </section>
          )}
        </div>
      )}

      {showShift && (
        <ShiftDatesModal
          days={days}
          formatDay={formatDay}
          onClose={() => setShowShift(false)}
          onShift={onShiftDates}
        />
      )}
      {insertTarget && (
        <InsertDayModal
          initialDate={insertTarget.date}
          initialLegId={insertTarget.legId}
          days={days}
          legs={legs}
          onClose={() => setInsertTarget(null)}
          onInsert={onInsertDay}
        />
      )}
      {moveSwapDay && (
        <MoveSwapDayModal
          day={moveSwapDay}
          days={days}
          formatDay={formatDay}
          onClose={() => setMoveSwapDay(null)}
          onSwap={onSwapDays}
          onMove={onMoveDay}
        />
      )}
      {removeTarget && (
        <RemoveDayModal
          day={removeTarget}
          formatDay={formatDay}
          hasLater={days.some((d) => d.date > removeTarget.date)}
          onClose={() => setRemoveTarget(null)}
          onRemove={onRemoveDay}
        />
      )}
    </div>
  );
}

function shortDayLabel(iso) {
  if (!iso) return '';
  const [y, m, d] = String(iso).split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC',
  });
}

function IdeaRow({
  idea,
  days,
  legs,
  defaultDayId,
  formatDay,
  formatPrice,
  renderAttachments,
  onSchedule,
  onAssignLeg,
  onEdit,
  onDelete,
  canEdit = true,
  commentIndex = null,
  onOpenComments,
}) {
  const [targetDayId, setTargetDayId] = useState(() => String(defaultDayId || days[0]?.id || ''));
  const [busy, setBusy] = useState(false);

  const scheduleNow = async () => {
    if (!targetDayId) return;
    setBusy(true);
    try {
      await onSchedule(idea, Number(targetDayId));
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="trip-prep-row trip-idea-row">
      <div className="trip-prep-info">
        <div className="trip-prep-title">
          {idea.kind === 'event' && <span className="tag event">Event</span>}
          {idea.kind === 'travel' && <span className="tag travel">Travel</span>}
          <strong>{idea.text}</strong>
          {idea.loc && <span className="tag">{idea.loc}</span>}
          {idea.cat && <span className="tag">{idea.cat}</span>}
          {idea.duration_minutes != null && <span className="tag">{idea.duration_minutes}m</span>}
          {idea.price != null && formatPrice && (
            <span className="tag price">{formatPrice(idea.price, idea.currency)}</span>
          )}
        </div>
        {idea.description && <p className="trip-muted trip-prep-desc">{idea.description}</p>}
        {renderAttachments && (idea.attachments || []).length > 0 && renderAttachments(idea.attachments)}
      </div>
      <div className="trip-prep-actions trip-idea-actions">
        {onOpenComments && (
          <CommentCountButton
            openCount={commentIndex?.openByKey?.[`stop:${idea.id}`] || 0}
            totalCount={commentIndex?.totalByKey?.[`stop:${idea.id}`] || 0}
            label={idea.text}
            onClick={() => onOpenComments({ type: 'stop', id: idea.id, label: idea.text })}
          />
        )}
        {canEdit && legs.length > 0 && (
          <select
            className="trip-route-leg-select"
            aria-label={`Leg for ${idea.text}`}
            value={idea.leg || ''}
            onChange={(e) => onAssignLeg(idea, e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Trip-wide</option>
            {legs.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        )}
        {canEdit && days.length > 0 && (
          <span className="trip-idea-schedule-group">
            <select
              className="trip-idea-day-select"
              aria-label={`Day for ${idea.text}`}
              value={targetDayId}
              disabled={busy}
              onChange={(e) => setTargetDayId(e.target.value)}
            >
              {days.map((d) => <option key={d.id} value={d.id}>{formatDay(d)}</option>)}
            </select>
            <button
              type="button"
              className="trip-primary"
              disabled={busy || !targetDayId}
              onClick={scheduleNow}
            >
              {busy ? '…' : 'Schedule'}
            </button>
          </span>
        )}
        {canEdit && <button type="button" onClick={() => onEdit(idea)}>Edit</button>}
        {canEdit && <button type="button" className="trip-danger-text" onClick={() => onDelete(idea)}>Delete</button>}
      </div>
    </li>
  );
}

export function IdeasWorkspace({
  days,
  legs = [],
  ideas = [],
  currentDay,
  formatDay,
  formatPrice,
  stopTimeText,
  zones,
  renderAttachments,
  onQuickAddIdea,
  onAddDetailedIdea,
  onScheduleIdea,
  onUnscheduleStop,
  onAssignIdeaLeg,
  onPromote,
  onEditStop,
  onDeleteStop,
  onOpenAssistant,
  canEdit = true,
  commentIndex = null,
  onOpenComments,
}) {
  const [view, setView] = useState('all'); // 'all' | 'pool' | 'scheduled'
  const [legFilter, setLegFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [quickText, setQuickText] = useState('');
  const [quickLegId, setQuickLegId] = useState(() => (currentDay?.leg ? String(currentDay.leg) : ''));
  const [quickKind, setQuickKind] = useState('activity');
  const [quickLoc, setQuickLoc] = useState('');
  const [adding, setAdding] = useState(false);

  const q = search.trim().toLowerCase();
  const matchesSearch = (s) => !q || `${s.text} ${s.description || ''} ${s.loc || ''} ${s.cat || ''}`.toLowerCase().includes(q);

  const filteredIdeas = useMemo(() => (
    ideas.filter((idea) => {
      if (!matchesSearch(idea)) return false;
      if (legFilter === 'none') return !idea.leg;
      if (legFilter !== 'all') return String(idea.leg || '') === legFilter;
      return true;
    })
  ), [ideas, legFilter, q]);

  const ideaGroups = useMemo(() => {
    if (!legs.length) return [{ key: 'all', leg: null, title: 'Unscheduled ideas', items: filteredIdeas }];
    const groups = legs
      .map((leg) => ({
        key: `leg-${leg.id}`,
        leg,
        title: leg.name,
        items: filteredIdeas.filter((i) => i.leg === leg.id),
      }))
      .filter((g) => g.items.length > 0);
    const untagged = filteredIdeas.filter((i) => !i.leg || !legs.some((l) => l.id === i.leg));
    if (untagged.length > 0) {
      groups.push({ key: 'untagged', leg: null, title: 'Trip-wide / untagged', items: untagged });
    }
    return groups;
  }, [legs, filteredIdeas]);

  const optionGroups = useMemo(() => (
    days
      .filter((day) => {
        if (legFilter === 'none') return !day.leg;
        if (legFilter !== 'all') return String(day.leg || '') === legFilter;
        return true;
      })
      .map((day) => ({
        day,
        items: (day.stops || []).filter((s) => s.status === 'option' && matchesSearch(s)),
      }))
      .filter((g) => g.items.length > 0)
  ), [days, legFilter, q]);

  const totalOptions = days.reduce((n, d) => n + (d.stops || []).filter((s) => s.status === 'option').length, 0);

  const defaultDayForLeg = (legId) => {
    if (legId) {
      const legDay = days.find((d) => d.leg === legId);
      if (legDay) return legDay.id;
    }
    return currentDay?.id || days[0]?.id || '';
  };

  const submitQuick = async (e) => {
    e.preventDefault();
    if (!quickText.trim()) return;
    setAdding(true);
    try {
      await onQuickAddIdea({
        text: quickText.trim(),
        leg_id: quickLegId ? Number(quickLegId) : null,
        kind: quickKind,
        loc: quickLoc.trim(),
        cat: quickKind === 'event' ? 'Event' : quickKind === 'travel' ? 'Travel' : 'Sight',
      });
      setQuickText('');
      setQuickLoc('');
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="trip-workspace-panel">
      <div className="trip-route-toolbar">
        <div className="trip-route-stats">
          <span><strong>{ideas.length}</strong> unscheduled {ideas.length === 1 ? 'idea' : 'ideas'}</span>
          <span><strong>{totalOptions}</strong> tentative {totalOptions === 1 ? 'option' : 'options'} on schedule</span>
        </div>
        {canEdit && (
          <div className="trip-route-actions">
            <button type="button" onClick={() => onAddDetailedIdea(quickLegId ? Number(quickLegId) : null)}>
              + Detailed idea…
            </button>
            <button type="button" className="trip-primary" onClick={onOpenAssistant}>✨ Ask AI for ideas</button>
          </div>
        )}
      </div>

      {canEdit && (
      <form className="trip-idea-quickadd" onSubmit={submitQuick}>
        <input
          value={quickText}
          onChange={(e) => setQuickText(e.target.value)}
          placeholder="Jot an idea (restaurant, sight, tour, excursion)…"
          disabled={adding}
        />
        <input
          className="trip-idea-quickadd-loc"
          value={quickLoc}
          onChange={(e) => setQuickLoc(e.target.value)}
          placeholder="Neighborhood / place"
          disabled={adding}
        />
        <select value={quickKind} onChange={(e) => setQuickKind(e.target.value)} aria-label="Idea type" disabled={adding}>
          <option value="activity">Activity</option>
          <option value="event">Event</option>
          <option value="travel">Travel</option>
        </select>
        {legs.length > 0 && (
          <select value={quickLegId} onChange={(e) => setQuickLegId(e.target.value)} aria-label="Leg" disabled={adding}>
            <option value="">Trip-wide</option>
            {legs.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        )}
        <button type="submit" className="trip-primary" disabled={adding || !quickText.trim()}>
          {adding ? 'Adding…' : '+ Add idea'}
        </button>
      </form>
      )}

      {(ideas.length > 0 || totalOptions > 0) && (
        <div className="trip-ideas-filters">
          <div className="trip-status-tabs">
            <button type="button" className={view === 'all' ? 'is-active' : ''} onClick={() => setView('all')}>
              All ({ideas.length + totalOptions})
            </button>
            <button type="button" className={view === 'pool' ? 'is-active' : ''} onClick={() => setView('pool')}>
              Unscheduled ({ideas.length})
            </button>
            <button type="button" className={view === 'scheduled' ? 'is-active' : ''} onClick={() => setView('scheduled')}>
              On schedule ({totalOptions})
            </button>
          </div>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter ideas…" />
          {legs.length > 0 && (
            <select value={legFilter} onChange={(e) => setLegFilter(e.target.value)} aria-label="Filter ideas by leg">
              <option value="all">All legs</option>
              {legs.map((l) => <option key={l.id} value={String(l.id)}>{l.name}</option>)}
              <option value="none">Trip-wide</option>
            </select>
          )}
        </div>
      )}

      {ideas.length === 0 && totalOptions === 0 ? (
        <div className="trip-empty-card">
          <p>Your Ideas pool is empty.</p>
          <p className="trip-muted">
            Brainstorm restaurants, sights, and activities above — or click <strong>Ask AI for ideas</strong> and save
            suggestions straight here before slotting them onto days.
          </p>
        </div>
      ) : (
        <div className="trip-ideas-groups">
          {(view === 'all' || view === 'pool') && (
            <>
              {filteredIdeas.length === 0 && view === 'pool' && (
                <div className="trip-empty-card"><p className="trip-muted">No unscheduled ideas match this filter.</p></div>
              )}
              {ideaGroups.map((group) => (
                <section key={group.key} className="trip-prep-card">
                  <div className="trip-prep-card-head">
                    <h4>
                      {group.title}{' '}
                      <span className="trip-muted">({group.items.length})</span>
                    </h4>
                    {group.leg?.location && <span className="trip-muted">{group.leg.location}</span>}
                  </div>
                  <ul className="trip-prep-list">
                    {group.items.map((idea) => (
                      <IdeaRow
                        key={idea.id}
                        idea={idea}
                        days={days}
                        legs={legs}
                        defaultDayId={defaultDayForLeg(idea.leg)}
                        formatDay={formatDay}
                        formatPrice={formatPrice}
                        renderAttachments={renderAttachments}
                        onSchedule={onScheduleIdea}
                        onAssignLeg={onAssignIdeaLeg}
                        onEdit={onEditStop}
                        onDelete={onDeleteStop}
                        canEdit={canEdit}
                        commentIndex={commentIndex}
                        onOpenComments={onOpenComments}
                      />
                    ))}
                  </ul>
                </section>
              ))}
            </>
          )}

          {(view === 'all' || view === 'scheduled') && optionGroups.length > 0 && (
            <>
              {view === 'all' && ideas.length > 0 && (
                <h4 className="trip-ideas-section-label">Tentative options already on the schedule</h4>
              )}
              {optionGroups.map(({ day, items }) => (
                <section key={day.id} className="trip-prep-card">
                  <h4>{formatDay(day)}</h4>
                  <ul className="trip-prep-list">
                    {items.map((stop) => (
                      <li key={stop.id} className="trip-prep-row">
                        <div className="trip-prep-info">
                          <div className="trip-prep-title">
                            {(stop.start_time || stop.duration_minutes != null) && (
                              <span className="trip-stop-time">{stopTimeText(stop, day, zones)}</span>
                            )}
                            <strong>{stop.text}</strong>
                            {stop.loc && <span className="tag">{stop.loc}</span>}
                            {stop.cat && <span className="tag">{stop.cat}</span>}
                          </div>
                          {stop.description && <p className="trip-muted trip-prep-desc">{stop.description}</p>}
                        </div>
                        <div className="trip-prep-actions">
                          {onOpenComments && (
                            <CommentCountButton
                              openCount={commentIndex?.openByKey?.[`stop:${stop.id}`] || 0}
                              totalCount={commentIndex?.totalByKey?.[`stop:${stop.id}`] || 0}
                              label={stop.text}
                              onClick={() => onOpenComments({ type: 'stop', id: stop.id, label: stop.text })}
                            />
                          )}
                          {canEdit && (
                            <>
                              <button type="button" className="trip-primary" onClick={() => onPromote(stop, 'no_booking')}>
                                Choose
                              </button>
                              <button type="button" onClick={() => onPromote(stop, 'tobook')}>
                                To book
                              </button>
                              <button type="button" onClick={() => onUnscheduleStop(stop, day.leg || null)} title="Move off this day back into the unscheduled Ideas pool">
                                To Ideas
                              </button>
                              <button type="button" onClick={() => onEditStop(stop)}>Edit</button>
                              <button type="button" className="trip-danger-text" onClick={() => onDeleteStop(stop)}>Delete</button>
                            </>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function IdeasRail({
  ideas = [],
  legs = [],
  currentDay,
  onQuickAddIdea,
  onScheduleIdea,
  onEditIdea,
  onOpenIdeasTab,
  onClose,
}) {
  const [scopeLeg, setScopeLeg] = useState('all');
  const [quickText, setQuickText] = useState('');
  const [adding, setAdding] = useState(false);

  const legById = useMemo(() => new Map(legs.map((l) => [l.id, l])), [legs]);
  const visible = useMemo(() => {
    if (scopeLeg === 'current' && currentDay?.leg) {
      return ideas.filter((i) => i.leg === currentDay.leg || !i.leg);
    }
    if (scopeLeg !== 'all' && scopeLeg !== 'current') {
      return ideas.filter((i) => String(i.leg || '') === scopeLeg);
    }
    return ideas;
  }, [ideas, scopeLeg, currentDay]);

  const submitQuick = async (e) => {
    e.preventDefault();
    if (!quickText.trim()) return;
    setAdding(true);
    try {
      const legId = scopeLeg === 'current'
        ? (currentDay?.leg || null)
        : (scopeLeg !== 'all' ? Number(scopeLeg) : (currentDay?.leg || null));
      await onQuickAddIdea({ text: quickText.trim(), leg_id: legId, kind: 'activity', cat: 'Sight' });
      setQuickText('');
    } finally {
      setAdding(false);
    }
  };

  const dayShort = currentDay ? shortDayLabel(currentDay.date) : '';

  return (
    <aside className="trip-ideas-rail" aria-label="Unscheduled ideas">
      <header className="trip-ideas-rail-head">
        <div>
          <strong>Ideas pool</strong>
          <span className="trip-muted"> ({ideas.length})</span>
        </div>
        <div className="trip-ideas-rail-head-btns">
          <button type="button" className="trip-link-button" onClick={onOpenIdeasTab}>Manage</button>
          <button type="button" className="trip-ideas-rail-close" onClick={onClose} aria-label="Close ideas rail" title="Hide ideas">×</button>
        </div>
      </header>

      <form className="trip-ideas-rail-add" onSubmit={submitQuick}>
        <input
          value={quickText}
          onChange={(e) => setQuickText(e.target.value)}
          placeholder="+ Quick idea…"
          disabled={adding}
        />
        <button type="submit" disabled={adding || !quickText.trim()}>Add</button>
      </form>

      {legs.length > 0 && (
        <select
          className="trip-ideas-rail-filter"
          value={scopeLeg}
          onChange={(e) => setScopeLeg(e.target.value)}
          aria-label="Filter ideas rail by leg"
        >
          <option value="all">All legs ({ideas.length})</option>
          {currentDay?.leg && legById.get(currentDay.leg) && (
            <option value="current">This leg ({legById.get(currentDay.leg).name})</option>
          )}
          {legs.map((l) => <option key={l.id} value={String(l.id)}>{l.name}</option>)}
        </select>
      )}

      {visible.length === 0 ? (
        <p className="trip-muted trip-ideas-rail-empty">
          {ideas.length === 0
            ? 'No unscheduled ideas yet. Add one above or drag ideas here later.'
            : 'No ideas in this leg.'}
        </p>
      ) : (
        <>
          <p className="trip-muted trip-ideas-rail-tip">Drag onto a day or click + to schedule.</p>
          <ul className="trip-ideas-rail-list">
            {visible.map((idea) => {
              const leg = idea.leg ? legById.get(idea.leg) : null;
              return (
                <li
                  key={idea.id}
                  className="trip-ideas-rail-card"
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData('application/x-trip-idea', JSON.stringify({ id: idea.id }));
                    e.dataTransfer.effectAllowed = 'move';
                  }}
                >
                  <div className="trip-ideas-rail-card-top">
                    <span className="trip-ideas-rail-grip" aria-hidden="true">⋮⋮</span>
                    <button type="button" className="trip-ideas-rail-title" onClick={() => onEditIdea(idea)}>
                      {idea.text}
                    </button>
                  </div>
                  <div className="trip-ideas-rail-meta">
                    {leg && <span className="trip-ideas-rail-leg">{leg.name}</span>}
                    {idea.loc && <span className="trip-muted">{idea.loc}</span>}
                    {idea.duration_minutes != null && <span className="trip-muted">{idea.duration_minutes}m</span>}
                  </div>
                  {currentDay && (
                    <div className="trip-ideas-rail-card-actions">
                      <button
                        type="button"
                        onClick={() => onScheduleIdea(idea, currentDay.id)}
                        title={`Add to ${dayShort}`}
                      >
                        + {dayShort}
                      </button>
                      <button type="button" onClick={() => onEditIdea(idea)}>Edit</button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </aside>
  );
}

const BOOKING_BUCKETS = [
  { key: 'tobook', title: 'To book', next: 'booked', nextLabel: 'Mark Booked' },
  { key: 'booked', title: 'Booked (awaiting confirmation)', next: 'confirmed', nextLabel: 'Mark Confirmed' },
  { key: 'confirmed', title: 'Confirmed', next: null, nextLabel: null },
];

const PREP_STATUS_LABELS = {
  option: 'Option',
  no_booking: 'No booking needed',
  tobook: 'To book',
  booked: 'Booked',
  confirmed: 'Confirmed',
};

function ConfirmationPill({ value, onSave, emphasizeMissing = false, readOnly = false }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || '');
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  const openEdit = () => {
    setDraft(value || '');
    setEditing(true);
  };

  const commit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave(draft.trim());
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const copyCode = async () => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore */
    }
  };

  if (editing) {
    return (
      <form className="trip-conf-inline" onSubmit={commit}>
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="PNR / confirmation #"
          aria-label="Confirmation number"
          disabled={saving}
        />
        <button type="submit" className="trip-primary" disabled={saving}>Save</button>
        <button type="button" onClick={() => setEditing(false)} disabled={saving}>Cancel</button>
      </form>
    );
  }

  if (value) {
    return (
      <span className="trip-conf-group">
        <button
          type="button"
          className="trip-conf-chip"
          onClick={copyCode}
          title="Click to copy confirmation #"
        >
          {copied ? '✓ Copied' : `# ${value}`}
        </button>
        {!readOnly && (
          <button
            type="button"
            className="trip-conf-edit-btn"
            onClick={openEdit}
            title="Edit confirmation #"
            aria-label="Edit confirmation number"
          >
            ✎
          </button>
        )}
      </span>
    );
  }

  if (readOnly) return null;

  return (
    <button
      type="button"
      className={`trip-conf-add-btn${emphasizeMissing ? ' is-warn' : ''}`}
      onClick={openEdit}
    >
      + Confirmation #
    </button>
  );
}

export function PrepWorkspace({
  trip,
  days,
  legs = [],
  zones,
  lists,
  documentCount = 0,
  subTab,
  setSubTab,
  formatDay,
  stopTimeText,
  formatPrice,
  lodgingLabel,
  onSetStopStatus,
  onPatchStop,
  onPatchLodging,
  onEditStop,
  onEditLodging,
  onOpenReport,
  onPatchTrip,
  renderTodos,
  renderDocuments,
  renderAttachments,
  canEdit = true,
  commentIndex = null,
  onOpenComments,
}) {
  const [typeFilter, setTypeFilter] = useState('all'); // 'all' | 'lodging' | 'travel' | 'activity'
  const [missingConfOnly, setMissingConfOnly] = useState(false);
  const [query, setQuery] = useState('');
  const [includeOptions, setIncludeOptions] = useState(false);

  const legById = useMemo(() => new Map(legs.map((l) => [l.id, l])), [legs]);
  const lodgings = trip.lodgings || [];

  const unassignedDays = useMemo(
    () => days.filter((d) => !(d.lodging || d.lodging_id)),
    [days],
  );

  // Unified booking items: Lodgings + Stops in chronological order
  const allBookingRows = useMemo(() => {
    const rows = [];
    for (const l of lodgings) {
      const stayDays = days.filter((d) => (d.lodging?.id ?? d.lodging_id) === l.id);
      const firstDate = stayDays[0]?.date || '9999-99-99';
      const legId = stayDays[0]?.leg || null;
      const hasDoc = (l.attachments || []).some((a) => a.kind === 'document');
      rows.push({
        uid: `lodging-${l.id}`,
        itemType: 'lodging',
        status: l.status || (l.confirmation ? 'confirmed' : 'tobook'),
        sortDate: firstDate,
        sortOrder: -1,
        title: l.name,
        subtitle: stayDays.length
          ? `${stayDays.length} ${stayDays.length === 1 ? 'night' : 'nights'} · ${formatDay({ date: stayDays[0].date })}${stayDays.length > 1 ? ` – ${formatDay({ date: stayDays[stayDays.length - 1].date })}` : ''}`
          : 'Unassigned nights',
        meta: [
          l.check_in_time ? `In ${String(l.check_in_time).slice(0, 5)}` : '',
          l.check_out_time ? `Out ${String(l.check_out_time).slice(0, 5)}` : '',
        ].filter(Boolean).join(' · '),
        confirmation: l.confirmation || '',
        hasDoc,
        price: l.price,
        currency: l.currency || '',
        person: l.person || '',
        leg: legId ? legById.get(legId) : null,
        attachments: l.attachments || [],
        lodging: l,
        stayDays,
      });
    }
    for (const day of days) {
      const leg = day.leg ? legById.get(day.leg) : null;
      for (const stop of day.stops || []) {
        if (!['tobook', 'booked', 'confirmed'].includes(stop.status)) continue;
        const hasDoc = (stop.attachments || []).some((a) => a.kind === 'document');
        rows.push({
          uid: `stop-${stop.id}`,
          itemType: stop.kind === 'travel' ? 'travel' : 'activity',
          kind: stop.kind || 'activity',
          status: stop.status,
          sortDate: day.date,
          sortOrder: stop.sort_order ?? 0,
          title: stop.text,
          subtitle: formatDay({ date: day.date }),
          meta: (stop.start_time || stop.duration_minutes != null) ? stopTimeText(stop, day, zones) : '',
          confirmation: stop.confirmation || '',
          hasDoc,
          price: stop.price,
          currency: stop.currency || '',
          person: stop.person || '',
          leg,
          attachments: stop.attachments || [],
          day,
          stop,
        });
      }
    }
    return rows.sort((a, b) => a.sortDate.localeCompare(b.sortDate) || (a.sortOrder - b.sortOrder));
  }, [lodgings, days, legById, formatDay, stopTimeText, zones]);

  const missingConfCount = useMemo(
    () => allBookingRows.filter((r) => (r.status === 'booked' || r.status === 'confirmed') && !r.confirmation && !r.hasDoc).length,
    [allBookingRows],
  );

  const toBookCount = useMemo(
    () => allBookingRows.filter((r) => r.status === 'tobook').length,
    [allBookingRows],
  );
  const bookedCount = useMemo(
    () => allBookingRows.filter((r) => r.status === 'booked').length,
    [allBookingRows],
  );
  const confirmedCount = useMemo(
    () => allBookingRows.filter((r) => r.status === 'confirmed').length,
    [allBookingRows],
  );
  const openTodoCount = (trip.todos || []).filter((t) => !t.done).length;

  const filteredBookings = useMemo(() => {
    const q = query.trim().toLowerCase();
    return allBookingRows.filter((r) => {
      if (typeFilter !== 'all' && r.itemType !== typeFilter) return false;
      if (missingConfOnly && !((r.status === 'booked' || r.status === 'confirmed') && !r.confirmation && !r.hasDoc)) {
        return false;
      }
      if (q) {
        const hay = `${r.title} ${r.subtitle} ${r.confirmation} ${r.person} ${r.leg?.name || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [allBookingRows, typeFilter, missingConfOnly, query]);

  const bookingBuckets = useMemo(() => {
    const groups = { tobook: [], booked: [], confirmed: [] };
    for (const row of filteredBookings) {
      if (groups[row.status]) groups[row.status].push(row);
    }
    return groups;
  }, [filteredBookings]);

  const otherLodgings = useMemo(
    () => filteredBookings.filter((r) => r.itemType === 'lodging' && !['tobook', 'booked', 'confirmed'].includes(r.status)),
    [filteredBookings],
  );

  const expenseData = useMemo(() => {
    const allItems = [];
    for (const l of lodgings) {
      if (l.price == null || l.price === '') continue;
      const stayDays = days.filter((d) => (d.lodging?.id ?? d.lodging_id) === l.id);
      const leg = stayDays[0]?.leg ? legById.get(stayDays[0].leg) : null;
      allItems.push({
        uid: `lodging-${l.id}`,
        itemType: 'lodging',
        sortDate: stayDays[0]?.date || '9999-99-99',
        dateLabel: stayDays.length
          ? `${formatDay({ date: stayDays[0].date })} (${stayDays.length}n)`
          : 'Lodging',
        title: l.name,
        cat: 'Lodging',
        person: l.person || '',
        status: l.status || (l.confirmation ? 'confirmed' : 'tobook'),
        confirmation: l.confirmation || '',
        price: l.price,
        currency: l.currency || '',
        legName: leg?.name || '',
        lodging: l,
        stayDays,
      });
    }
    for (const day of days) {
      const leg = day.leg ? legById.get(day.leg) : null;
      for (const stop of day.stops || []) {
        if (stop.price == null || stop.price === '') continue;
        allItems.push({
          uid: `stop-${stop.id}`,
          itemType: 'stop',
          sortDate: day.date,
          dateLabel: formatDay({ date: day.date }),
          title: stop.text,
          cat: stop.cat || '',
          person: stop.person || '',
          status: stop.status || 'no_booking',
          confirmation: stop.confirmation || '',
          price: stop.price,
          currency: stop.currency || '',
          legName: leg?.name || '',
          stop,
        });
      }
    }
    allItems.sort((a, b) => a.sortDate.localeCompare(b.sortDate));

    const optionItems = allItems.filter((i) => i.status === 'option');
    const items = includeOptions ? allItems : allItems.filter((i) => i.status !== 'option');

    const groupBy = (fn, blank, sortFn) => {
      const map = new Map();
      for (const it of items) {
        const raw = (fn(it) || '').trim();
        const k = raw.toLowerCase();
        if (!map.has(k)) map.set(k, { name: raw || blank, items: [] });
        map.get(k).items.push(it);
      }
      const arr = [...map.values()];
      return sortFn ? arr.sort(sortFn) : arr.sort((a, b) => a.name.localeCompare(b.name));
    };

    const statusOrder = ['Confirmed', 'Booked', 'To book', 'No booking needed', 'Option'];
    return {
      allItems,
      optionItems,
      items,
      byStatus: groupBy(
        (it) => PREP_STATUS_LABELS[it.status] || it.status,
        'Other',
        (a, b) => statusOrder.indexOf(a.name) - statusOrder.indexOf(b.name),
      ),
      byLeg: legs.length > 0 ? groupBy((it) => it.legName, 'Trip-wide / ungrouped') : [],
      byCat: groupBy((it) => it.cat, 'Uncategorized'),
      byPerson: items.some((it) => it.person) ? groupBy((it) => it.person, 'Unassigned') : [],
    };
  }, [lodgings, days, legs.length, legById, formatDay, includeOptions]);

  const setRowStatus = (row, nextStatus) => {
    if (row.itemType === 'lodging') return onPatchLodging(row.lodging, { status: nextStatus });
    return onSetStopStatus(row.stop, nextStatus);
  };

  const saveRowConfirmation = (row, conf) => {
    if (row.itemType === 'lodging') return onPatchLodging(row.lodging, { confirmation: conf });
    return onPatchStop(row.stop, { confirmation: conf });
  };

  const renderBookingRow = (row, next, nextLabel) => {
    const missingConf = (row.status === 'booked' || row.status === 'confirmed') && !row.confirmation && !row.hasDoc;
    const typeBadge = row.itemType === 'lodging'
      ? '🛏 Lodging'
      : (row.itemType === 'travel' ? '✈ Travel' : (row.kind === 'event' ? '🎟 Event' : '📍 Activity'));
    return (
      <li key={row.uid} className={`trip-prep-row${missingConf ? ' is-missing-conf' : ''}`}>
        <div className="trip-prep-info">
          <div className="trip-prep-title">
            <span className={`tag prep-kind is-${row.itemType}`}>{typeBadge}</span>
            <span className="trip-muted">{row.subtitle}</span>
            {row.meta && <span className="trip-stop-time">{row.meta}</span>}
            <strong>{row.title}</strong>
            {row.leg && <span className="tag">{row.leg.name}</span>}
            {row.price != null && row.price !== '' && (
              <span className="tag price">{formatPrice(row.price, row.currency)}</span>
            )}
            {row.person && <span className="tag person">{row.person}</span>}
          </div>
          <div className="trip-prep-subrow">
            <ConfirmationPill
              value={row.confirmation}
              emphasizeMissing={missingConf}
              readOnly={!canEdit}
              onSave={(val) => saveRowConfirmation(row, val)}
            />
            {missingConf && (
              <span className="trip-missing-hint">No confirmation # or voucher attached</span>
            )}
          </div>
          {renderAttachments(row.attachments)}
        </div>
        <div className="trip-prep-actions">
          {onOpenComments && (
            <CommentCountButton
              openCount={commentIndex?.openByKey?.[row.itemType === 'lodging' ? `lodging:${row.lodging.id}` : `stop:${row.stop.id}`] || 0}
              totalCount={commentIndex?.totalByKey?.[row.itemType === 'lodging' ? `lodging:${row.lodging.id}` : `stop:${row.stop.id}`] || 0}
              label={row.title}
              onClick={() => onOpenComments(
                row.itemType === 'lodging'
                  ? { type: 'lodging', id: row.lodging.id, label: row.title }
                  : { type: 'stop', id: row.stop.id, label: row.title },
              )}
            />
          )}
          {canEdit && next && (
            <button type="button" className="trip-primary" onClick={() => setRowStatus(row, next)}>
              {nextLabel}
            </button>
          )}
          {canEdit && (
            <select
              className="trip-prep-status-select"
              aria-label={`Status for ${row.title}`}
              value={row.status}
              onChange={(e) => setRowStatus(row, e.target.value)}
            >
              {Object.entries(PREP_STATUS_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          )}
          {canEdit && (
            <button
              type="button"
              onClick={() => (
                row.itemType === 'lodging'
                  ? onEditLodging(row.lodging, row.stayDays.map((d) => d.id))
                  : onEditStop(row.stop)
              )}
            >
              Edit
            </button>
          )}
        </div>
      </li>
    );
  };

  return (
    <div className="trip-workspace-panel">
      {/* Trip Readiness Summary Strip */}
      <div className="trip-readiness-strip" aria-label="Trip readiness overview">
        <button
          type="button"
          className={`trip-readiness-tile${unassignedDays.length > 0 ? ' is-warn' : ' is-ok'}`}
          onClick={() => { setSubTab('bookings'); setMissingConfOnly(false); }}
        >
          <span className="trip-readiness-label">Nights covered</span>
          <strong>{days.length - unassignedDays.length} / {days.length}</strong>
          <small>{unassignedDays.length > 0 ? `${unassignedDays.length} unassigned` : (days.length ? 'All nights booked' : 'No days yet')}</small>
        </button>
        <button
          type="button"
          className={`trip-readiness-tile${toBookCount > 0 ? ' is-warn' : ' is-ok'}`}
          onClick={() => { setSubTab('bookings'); setMissingConfOnly(false); }}
        >
          <span className="trip-readiness-label">Bookings</span>
          <strong>{toBookCount} to book</strong>
          <small>{bookedCount} booked · {confirmedCount} confirmed</small>
        </button>
        <button
          type="button"
          className={`trip-readiness-tile${missingConfCount > 0 ? ' is-warn' : ''}`}
          onClick={() => { setSubTab('bookings'); setMissingConfOnly(missingConfCount > 0); }}
        >
          <span className="trip-readiness-label">Confirmations</span>
          <strong>{missingConfCount > 0 ? `${missingConfCount} missing` : 'All set'}</strong>
          <small>{missingConfCount > 0 ? 'Click to filter missing' : 'Refs or vouchers attached'}</small>
        </button>
        <button
          type="button"
          className="trip-readiness-tile"
          onClick={() => setSubTab('todos')}
        >
          <span className="trip-readiness-label">To-dos &amp; Docs</span>
          <strong>{openTodoCount} open</strong>
          <small>{documentCount} {documentCount === 1 ? 'document' : 'documents'}</small>
        </button>
      </div>

      <div className="trip-subtabs">
        <button type="button" className={subTab === 'bookings' ? 'is-active' : ''} onClick={() => setSubTab('bookings')}>
          Bookings{toBookCount ? ` (${toBookCount})` : ''}
        </button>
        <button type="button" className={subTab === 'todos' ? 'is-active' : ''} onClick={() => setSubTab('todos')}>
          To-dos{openTodoCount ? ` (${openTodoCount})` : ''}
        </button>
        <button type="button" className={subTab === 'documents' ? 'is-active' : ''} onClick={() => setSubTab('documents')}>
          Documents{documentCount ? ` (${documentCount})` : ''}
        </button>
        <button type="button" className={subTab === 'budget' ? 'is-active' : ''} onClick={() => setSubTab('budget')}>
          Budget &amp; Reports
        </button>
      </div>

      {subTab === 'bookings' && (
        <div className="trip-prep-stack">
          {unassignedDays.length > 0 && (
            <div className="trip-prep-callout is-warn">
              <div>
                <strong>🛏 {unassignedDays.length} {unassignedDays.length === 1 ? 'night has' : 'nights have'} no lodging assigned</strong>
                <p className="trip-muted">
                  {unassignedDays.slice(0, 6).map((d) => formatDay({ date: d.date })).join(' · ')}
                  {unassignedDays.length > 6 ? ` · +${unassignedDays.length - 6} more` : ''}
                </p>
              </div>
              {canEdit && (
                <button
                  type="button"
                  className="trip-primary"
                  onClick={() => onEditLodging(null, unassignedDays.map((d) => d.id))}
                >
                  + Assign lodging
                </button>
              )}
            </div>
          )}

          <div className="trip-prep-filters">
            <div className="trip-status-tabs" role="group" aria-label="Filter bookings by type">
              {[
                ['all', 'All'],
                ['lodging', 'Lodgings'],
                ['travel', 'Travel'],
                ['activity', 'Activities & Events'],
              ].map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={typeFilter === key ? 'is-active' : ''}
                  onClick={() => setTypeFilter(key)}
                >
                  {label}
                </button>
              ))}
            </div>
            <button
              type="button"
              className={`trip-prep-toggle${missingConfOnly ? ' is-active' : ''}`}
              onClick={() => setMissingConfOnly((v) => !v)}
            >
              Missing confirmation{missingConfCount ? ` (${missingConfCount})` : ''}
            </button>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search bookings or confirmation #…"
              aria-label="Search bookings"
            />
            {canEdit && <button type="button" onClick={() => onEditLodging(null, [])}>+ Add lodging</button>}
          </div>

          {BOOKING_BUCKETS.map(({ key, title, next, nextLabel }) => (
            <section key={key} className="trip-prep-card">
              <h4>{title} ({bookingBuckets[key].length})</h4>
              {bookingBuckets[key].length === 0 ? (
                <p className="trip-muted">None.</p>
              ) : (
                <ul className="trip-prep-list">
                  {bookingBuckets[key].map((row) => renderBookingRow(row, next, nextLabel))}
                </ul>
              )}
            </section>
          ))}

          {otherLodgings.length > 0 && (
            <section className="trip-prep-card">
              <h4>Other lodgings ({otherLodgings.length})</h4>
              <ul className="trip-prep-list">
                {otherLodgings.map((row) => renderBookingRow(row, 'tobook', 'Move to To book'))}
              </ul>
            </section>
          )}
        </div>
      )}

      {subTab === 'todos' && (
        <div className="trip-prep-stack">
          <div className="trip-prep-packing">
            <label>
              Packing list
              <select
                value={trip.packing_list || ''}
                onChange={(e) => onPatchTrip({ packing_list_id: e.target.value ? Number(e.target.value) : null })}
              >
                <option value="">None</option>
                {lists.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </label>
            {trip.packing_list && (
              <a href="/app/vacation/" className="trip-ext-link">Open packing list →</a>
            )}
          </div>
          {renderTodos()}
        </div>
      )}

      {subTab === 'documents' && (
        <div className="trip-prep-stack">
          {renderDocuments()}
        </div>
      )}

      {subTab === 'budget' && (
        <div className="trip-prep-stack">
          <div className="trip-route-toolbar">
            <div>
              <strong>Total budgeted:</strong>{' '}
              <span className="trip-budget-total">{totalsLabel(expenseData.items)}</span>
              <span className="trip-muted">
                {' '}across {expenseData.items.length} priced {expenseData.items.length === 1 ? 'item' : 'items'}
                {!includeOptions && expenseData.optionItems.length > 0 && (
                  <> · excluding {expenseData.optionItems.length} option{expenseData.optionItems.length === 1 ? '' : 's'} ({totalsLabel(expenseData.optionItems)})</>
                )}
              </span>
            </div>
            <div className="trip-route-actions">
              {expenseData.optionItems.length > 0 && (
                <label className="trip-check">
                  <input
                    type="checkbox"
                    checked={includeOptions}
                    onChange={(e) => setIncludeOptions(e.target.checked)}
                  />
                  Include options
                </label>
              )}
              <button type="button" className="trip-primary" onClick={onOpenReport}>Generate Report…</button>
            </div>
          </div>

          {expenseData.items.length === 0 ? (
            <div className="trip-empty-card">
              <p>No prices entered yet.</p>
              <p className="trip-muted">Add a price on any lodging, stop, travel, or event to track trip expenses here.</p>
            </div>
          ) : (
            <>
              <div className="trip-budget-grid">
                <section className="trip-prep-card">
                  <h4>By booking status</h4>
                  <ul className="trip-budget-breakdown">
                    {expenseData.byStatus.map((g) => (
                      <li key={g.name}><span>{g.name}</span><strong>{totalsLabel(g.items)}</strong></li>
                    ))}
                  </ul>
                </section>
                <section className="trip-prep-card">
                  <h4>By category</h4>
                  <ul className="trip-budget-breakdown">
                    {expenseData.byCat.map((g) => (
                      <li key={g.name}><span>{g.name}</span><strong>{totalsLabel(g.items)}</strong></li>
                    ))}
                  </ul>
                </section>
                {expenseData.byLeg.length > 0 && (
                  <section className="trip-prep-card">
                    <h4>By leg</h4>
                    <ul className="trip-budget-breakdown">
                      {expenseData.byLeg.map((g) => (
                        <li key={g.name}><span>{g.name}</span><strong>{totalsLabel(g.items)}</strong></li>
                      ))}
                    </ul>
                  </section>
                )}
                {expenseData.byPerson.length > 0 && (
                  <section className="trip-prep-card">
                    <h4>By person</h4>
                    <ul className="trip-budget-breakdown">
                      {expenseData.byPerson.map((g) => (
                        <li key={g.name}><span>{g.name}</span><strong>{totalsLabel(g.items)}</strong></li>
                      ))}
                    </ul>
                  </section>
                )}
              </div>
              <section className="trip-prep-card">
                <h4>Priced items ({expenseData.items.length})</h4>
                <ul className="trip-prep-list">
                  {expenseData.items.map((it) => (
                    <li key={it.uid} className="trip-prep-row">
                      <div className="trip-prep-info">
                        <div className="trip-prep-title">
                          <span className="trip-muted">{it.dateLabel}</span>
                          <strong>{it.itemType === 'lodging' ? `🛏 ${it.title}` : it.title}</strong>
                          {it.cat && <span className="tag">{it.cat}</span>}
                          {it.legName && <span className="tag">{it.legName}</span>}
                          {it.person && <span className="tag person">{it.person}</span>}
                          {it.confirmation && <span className="tag conf"># {it.confirmation}</span>}
                          <span className={`tag ${it.status}`}>{PREP_STATUS_LABELS[it.status] || it.status}</span>
                        </div>
                      </div>
                      <div className="trip-prep-actions">
                        <strong className="trip-budget-amt">{formatPrice(it.price, it.currency)}</strong>
                        <button
                          type="button"
                          onClick={() => (
                            it.itemType === 'lodging'
                              ? onEditLodging(it.lodging, it.stayDays.map((d) => d.id))
                              : onEditStop(it.stop)
                          )}
                        >
                          Edit
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}
        </div>
      )}
    </div>
  );
}
