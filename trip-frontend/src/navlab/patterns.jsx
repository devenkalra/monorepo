import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  dayNumber, dayTitle, daySubtitle, findNode, fmtDate, itemTitle, sortedDays, sortedItems, tripSubtitle,
} from './model';
import { DayRow, Inspector, ItemRow, Row, TripRow, useEscape } from './parts';

const daySel = (day) => ({ type: 'day', dayId: day.id });
const itemSel = (day, item) => ({ type: 'item', dayId: day.id, itemId: item.id });
const isSel = (sel, type, id) => sel?.type === type && (type === 'day' ? sel.dayId : sel.itemId) === id;

function useFocusedDay(trip, sel) {
  const days = sortedDays(trip);
  return days.find((d) => d.id === sel?.dayId) || days[0];
}

function TripHeader({ trip, onDetails, detailsLabel = 'Trip details' }) {
  return (
    <header className="nl-trip-head">
      <div className="nl-row-text">
        <h1 className="nl-row-title">{trip.title}</h1>
        <span className="nl-row-sub">{tripSubtitle(trip)}</span>
      </div>
      <button type="button" className="nl-btn" onClick={onDetails}>{detailsLabel}</button>
    </header>
  );
}

/* ---------- Pattern 1: day strip + chronological stream + slide-over drawer ---------- */

export function DayStripPattern({ trip, dispatch, sel, setSel }) {
  const days = sortedDays(trip);
  const day = useFocusedDay(trip, sel);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const close = useCallback(() => setDrawerOpen(false), []);
  useEscape(drawerOpen, close);

  const open = (next) => {
    setSel(next);
    setDrawerOpen(true);
  };

  return (
    <div className="nl-p1">
      <TripHeader trip={trip} onDetails={() => open({ type: 'trip' })} />
      <nav className="nl-daystrip" aria-label="Days">
        {days.map((d) => (
          <button
            key={d.id}
            type="button"
            className={`nl-daytab${d.id === day.id ? ' is-active' : ''}`}
            onClick={() => setSel(daySel(d))}
            aria-current={d.id === day.id ? 'date' : undefined}
          >
            <span className="nl-row-title">Day {dayNumber(trip, d)} · {d.city}</span>
            <span className="nl-row-sub">{fmtDate(d.date)}</span>
          </button>
        ))}
      </nav>
      <section className="nl-stream">
        <div className="nl-stream-head">
          <div className="nl-row-text">
            <h2 className="nl-row-title">{fmtDate(day.date, { weekday: 'long', month: 'long', day: 'numeric' })}</h2>
            <span className="nl-row-sub">{day.city} · {day.items.length} items</span>
          </div>
          <button type="button" className="nl-btn" onClick={() => open(daySel(day))}>Day details</button>
        </div>
        <ol className="nl-timeline">
          {sortedItems(day).map((item) => (
            <li key={item.id}>
              <ItemRow
                item={item}
                selected={drawerOpen && isSel(sel, 'item', item.id)}
                onClick={() => open(itemSel(day, item))}
              />
            </li>
          ))}
        </ol>
      </section>

      <div className={`nl-drawer-backdrop${drawerOpen ? ' is-open' : ''}`} onClick={close} role="presentation" />
      <aside className={`nl-drawer${drawerOpen ? ' is-open' : ''}`} aria-hidden={!drawerOpen} inert={!drawerOpen}>
        {drawerOpen && <Inspector trip={trip} node={findNode(trip, sel)} dispatch={dispatch} onClose={close} />}
      </aside>
    </div>
  );
}

/* ---------- Pattern 2: master tree + context inspector (map / attributes) ---------- */

function pinPosition(id, i, n) {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const x = 12 + (76 * (i + 0.5)) / Math.max(n, 1);
  const y = 45 + 28 * Math.sin(i * 2.1 + (h % 7));
  return { x, y };
}

function MapPlaceholder({ trip, sel, setSel }) {
  const node = findNode(trip, sel);
  const day = node.day;
  const pins = day
    ? sortedItems(day).map((item, i, all) => ({
      id: item.id, label: i + 1, title: itemTitle(item), sel: itemSel(day, item), ...pinPosition(item.id, i, all.length),
    }))
    : sortedDays(trip).map((d, i, all) => ({
      id: d.id, label: i + 1, title: dayTitle(trip, d), sel: daySel(d), ...pinPosition(d.id, i, all.length),
    }));
  const activeId = node.item?.id;

  return (
    <div className="nl-map">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="nl-map-svg" aria-hidden="true">
        <polyline points={pins.map((p) => `${p.x},${p.y}`).join(' ')} />
      </svg>
      {pins.map((p) => (
        <button
          key={p.id}
          type="button"
          className={`nl-pin${p.id === activeId ? ' is-active' : ''}`}
          style={{ left: `${p.x}%`, top: `${p.y}%` }}
          onClick={() => setSel(p.sel)}
          title={p.title}
          aria-label={p.title}
        >
          {p.label}
        </button>
      ))}
      <p className="nl-map-caption">
        Map placeholder · {day ? `${dayTitle(trip, day)} · ${pins.length} pins` : `${pins.length} overnight stops`}
      </p>
    </div>
  );
}

export function TreePattern({ trip, dispatch, sel, setSel }) {
  const days = sortedDays(trip);
  const [collapsed, setCollapsed] = useState(() => new Set());
  const [tripOpen, setTripOpen] = useState(true);
  const [pane, setPane] = useState('attrs');
  const node = findNode(trip, sel);

  const toggle = (id) => setCollapsed((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
  const allCollapsed = days.every((d) => collapsed.has(d.id));

  return (
    <div className="nl-p2">
      <aside className="nl-tree" aria-label="Trip outline">
        <div className="nl-tree-tools">
          <span>Outline</span>
          <button
            type="button"
            className="nl-link-btn"
            onClick={() => setCollapsed(allCollapsed ? new Set() : new Set(days.map((d) => d.id)))}
          >
            {allCollapsed ? 'Expand all' : 'Collapse all'}
          </button>
        </div>
        <ul role="tree">
          <li role="treeitem" aria-expanded={tripOpen} aria-selected={node.type === 'trip'}>
            <div className="nl-tree-node">
              <button type="button" className="nl-caret" onClick={() => setTripOpen(!tripOpen)} aria-label="Toggle trip">
                {tripOpen ? '▾' : '▸'}
              </button>
              <TripRow trip={trip} selected={node.type === 'trip'} onClick={() => setSel({ type: 'trip' })} />
            </div>
            {tripOpen && (
              <ul role="group">
                {days.map((d) => {
                  const open = !collapsed.has(d.id);
                  return (
                    <li key={d.id} role="treeitem" aria-expanded={open} aria-selected={isSel(sel, 'day', d.id)}>
                      <div className="nl-tree-node">
                        <button type="button" className="nl-caret" onClick={() => toggle(d.id)} aria-label={`Toggle day ${dayNumber(trip, d)}`}>
                          {open ? '▾' : '▸'}
                        </button>
                        <DayRow trip={trip} day={d} selected={isSel(sel, 'day', d.id)} onClick={() => setSel(daySel(d))} />
                      </div>
                      {open && (
                        <ul role="group">
                          {sortedItems(d).map((item) => (
                            <li key={item.id} role="treeitem" aria-selected={isSel(sel, 'item', item.id)}>
                              <ItemRow
                                item={item}
                                selected={isSel(sel, 'item', item.id)}
                                onClick={() => setSel(itemSel(d, item))}
                              />
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </li>
        </ul>
      </aside>
      <section className="nl-context">
        <div className="nl-segmented" role="tablist" aria-label="Context pane">
          <button type="button" role="tab" aria-selected={pane === 'map'} className={pane === 'map' ? 'is-active' : ''} onClick={() => setPane('map')}>Map</button>
          <button type="button" role="tab" aria-selected={pane === 'attrs'} className={pane === 'attrs' ? 'is-active' : ''} onClick={() => setPane('attrs')}>Attributes</button>
        </div>
        {pane === 'map'
          ? <MapPlaceholder trip={trip} sel={sel} setSel={setSel} />
          : <Inspector trip={trip} node={node} dispatch={dispatch} />}
      </section>
    </div>
  );
}

/* ---------- Pattern 3: multi-day columns + modal inspector ---------- */

export function ColumnsPattern({ trip, dispatch, sel, setSel }) {
  const [modalOpen, setModalOpen] = useState(false);
  const close = useCallback(() => setModalOpen(false), []);
  useEscape(modalOpen, close);
  const columnsRef = useRef(null);
  useEffect(() => {
    columnsRef.current?.querySelector('.is-focused')?.scrollIntoView({ inline: 'start', block: 'nearest' });
  }, []);
  const open = (next) => {
    setSel(next);
    setModalOpen(true);
  };

  return (
    <div className="nl-p3">
      <TripHeader trip={trip} onDetails={() => open({ type: 'trip' })} />
      <div className="nl-columns" ref={columnsRef}>
        {sortedDays(trip).map((d) => (
          <section key={d.id} className={`nl-column${sel?.dayId === d.id ? ' is-focused' : ''}`}>
            <Row
              className="nl-column-head"
              title={dayTitle(trip, d)}
              subtitle={daySubtitle(d)}
              selected={modalOpen && isSel(sel, 'day', d.id)}
              onClick={() => open(daySel(d))}
            />
            <ol className="nl-cards">
              {sortedItems(d).map((item) => (
                <li key={item.id}>
                  <ItemRow
                    item={item}
                    className="nl-card"
                    selected={isSel(sel, 'item', item.id)}
                    onClick={() => open(itemSel(d, item))}
                  />
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
      {modalOpen && (
        <div className="nl-modal-backdrop" onClick={close} role="presentation">
          <div className="nl-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <Inspector trip={trip} node={findNode(trip, sel)} dispatch={dispatch} onClose={close} />
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------- Pattern 4: drill-down stack with sticky breadcrumbs ---------- */

function initialView(sel) {
  if (sel?.type === 'item') return { level: 'item', dayId: sel.dayId, itemId: sel.itemId };
  if (sel?.type === 'day') return { level: 'day', dayId: sel.dayId };
  return { level: 'trip' };
}

export function DrillPattern({ trip, dispatch, sel, setSel }) {
  const [view, setView] = useState(() => initialView(sel));
  const days = sortedDays(trip);
  const day = days.find((d) => d.id === view.dayId);
  const items = day ? sortedItems(day) : [];
  const item = items.find((i) => i.id === view.itemId);

  const go = (next) => {
    setView(next);
    if (next.level === 'item') setSel({ type: 'item', dayId: next.dayId, itemId: next.itemId });
    else if (next.dayId) setSel({ type: 'day', dayId: next.dayId });
    else setSel({ type: 'trip' });
    window.scrollTo({ top: 0 });
  };

  const crumbs = useMemo(() => {
    const list = [{ label: trip.title, view: { level: 'trip' } }];
    if (view.level === 'tripDetails') list.push({ label: 'Trip details' });
    if (day) list.push({ label: dayTitle(trip, day), view: { level: 'day', dayId: day.id } });
    if (view.level === 'dayDetails') list.push({ label: 'Day details' });
    if (item) list.push({ label: itemTitle(item) });
    return list;
  }, [trip, view.level, day, item]);
  const back = [...crumbs].reverse().find((c, i) => i > 0 && c.view);

  const sibling = (list, index, toView) => (
    <div className="nl-pager">
      <button type="button" className="nl-btn" disabled={index <= 0} onClick={() => go(toView(list[index - 1]))}>← Previous</button>
      <button type="button" className="nl-btn" disabled={index >= list.length - 1} onClick={() => go(toView(list[index + 1]))}>Next →</button>
    </div>
  );

  let body;
  if (view.level === 'tripDetails') {
    body = <Inspector trip={trip} node={{ type: 'trip' }} dispatch={dispatch} />;
  } else if (view.level === 'dayDetails' && day) {
    body = <Inspector trip={trip} node={{ type: 'day', day }} dispatch={dispatch} />;
  } else if (view.level === 'item' && item) {
    body = (
      <>
        <Inspector trip={trip} node={{ type: 'item', day, item }} dispatch={dispatch} />
        {sibling(items, items.indexOf(item), (i) => ({ level: 'item', dayId: day.id, itemId: i.id }))}
      </>
    );
  } else if (view.level === 'day' && day) {
    body = (
      <>
        <div className="nl-stream-head">
          <div className="nl-row-text">
            <h2 className="nl-row-title">{dayTitle(trip, day)}</h2>
            <span className="nl-row-sub">{fmtDate(day.date, { weekday: 'long', month: 'long', day: 'numeric' })}</span>
          </div>
        </div>
        <ol className="nl-list">
          <li>
            <Row
              className="nl-details-row"
              glyph={<span className="nl-glyph is-info" aria-hidden="true">i</span>}
              title="Day details"
              subtitle="Hotel, summary, weather and transit"
              onClick={() => go({ level: 'dayDetails', dayId: day.id })}
              trailing={<span className="nl-chevron" aria-hidden="true">›</span>}
            />
          </li>
          {items.map((i) => (
            <li key={i.id}>
              <ItemRow
                item={i}
                onClick={() => go({ level: 'item', dayId: day.id, itemId: i.id })}
                trailing={<span className="nl-chevron" aria-hidden="true">›</span>}
              />
            </li>
          ))}
        </ol>
        {sibling(days, days.indexOf(day), (d) => ({ level: 'day', dayId: d.id }))}
      </>
    );
  } else {
    body = (
      <>
        <TripHeader trip={trip} onDetails={() => go({ level: 'tripDetails' })} />
        <ol className="nl-list">
          {days.map((d) => (
            <li key={d.id}>
              <DayRow
                trip={trip}
                day={d}
                onClick={() => go({ level: 'day', dayId: d.id })}
                trailing={<span className="nl-chevron" aria-hidden="true">›</span>}
              />
            </li>
          ))}
        </ol>
      </>
    );
  }

  return (
    <div className="nl-p4">
      <nav className="nl-crumbs" aria-label="Breadcrumb">
        <button type="button" className="nl-btn" disabled={!back} onClick={() => back && go(back.view)} aria-label="Back">←</button>
        <ol>
          {crumbs.map((c, i) => (
            <li key={`${i}-${c.label}`}>
              {i < crumbs.length - 1 && c.view
                ? <button type="button" className="nl-link-btn" onClick={() => go(c.view)}>{c.label}</button>
                : <span aria-current="page">{c.label}</span>}
            </li>
          ))}
        </ol>
      </nav>
      <div className="nl-drill-body">{body}</div>
    </div>
  );
}
