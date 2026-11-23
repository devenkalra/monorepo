import { useReducer, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { freshTrip, tripReducer } from './model';
import { ColumnsPattern, DayStripPattern, DrillPattern, TreePattern } from './patterns';
import './navlab.css';

const PATTERNS = [
  { id: '1', name: 'Day strip', blurb: 'Day tabs, a chronological stream, and a slide-over drawer for editing.', Component: DayStripPattern },
  { id: '2', name: 'Tree + inspector', blurb: 'Collapsible Trip → Days → Items outline; the right pane flips between map and attributes.', Component: TreePattern },
  { id: '3', name: 'Day columns', blurb: 'Every day side by side as compact cards; edits open in a modal.', Component: ColumnsPattern },
  { id: '4', name: 'Drill-down', blurb: 'One pane at a time: Trip → Day → Item, with sticky breadcrumbs.', Component: DrillPattern },
];

export default function NavLab() {
  const [params, setParams] = useSearchParams();
  const [trip, dispatch] = useReducer(tripReducer, undefined, freshTrip);
  const [sel, setSel] = useState({ type: 'trip' });
  const active = PATTERNS.find((p) => p.id === params.get('p')) || PATTERNS[0];
  const { Component } = active;

  return (
    <div className="nl-app">
      <header className="nl-switcher">
        <div className="nl-brand">
          <Link to="/" className="nl-link-btn">← Trips</Link>
          <strong>Nav lab</strong>
        </div>
        <div className="nl-segmented nl-pattern-tabs" role="tablist" aria-label="Navigation pattern">
          {PATTERNS.map((p) => (
            <button
              key={p.id}
              type="button"
              role="tab"
              aria-selected={p === active}
              className={p === active ? 'is-active' : ''}
              onClick={() => setParams({ p: p.id }, { replace: true })}
            >
              <span className="nl-tab-num">{p.id}</span> {p.name}
            </button>
          ))}
        </div>
        <button type="button" className="nl-btn" onClick={() => dispatch({ type: 'reset' })}>Reset data</button>
      </header>
      <p className="nl-blurb">{active.blurb}</p>
      <main className="nl-stage">
        <Component key={active.id} trip={trip} dispatch={dispatch} sel={sel} setSel={setSel} />
      </main>
    </div>
  );
}
