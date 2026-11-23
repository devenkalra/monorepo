import { useEffect, useState } from 'react';
import {
  DAY_FIELDS, ITEM_FIELDS, KIND_LABEL, MODE_GLYPH, MODE_LABEL, TRIP_FIELDS,
  dayNumber, dayTitle, daySubtitle, getPath, itemSubtitle, itemTitle, tripSubtitle,
} from './model';

export function useEscape(active, onEscape) {
  useEffect(() => {
    if (!active) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') onEscape();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [active, onEscape]);
}

export function KindGlyph({ item }) {
  const glyph = item.kind === 'travel' ? MODE_GLYPH[item.mode] || '→' : item.kind === 'event' ? '◆' : '●';
  const label = item.kind === 'travel' ? MODE_LABEL[item.mode] : KIND_LABEL[item.kind];
  return <span className={`nl-glyph is-${item.kind}`} title={label} aria-hidden="true">{glyph}</span>;
}

/** The only list row shape in the lab: a glyph plus at most two single-line texts. */
export function Row({ glyph, title, subtitle, selected, onClick, className = '', trailing }) {
  return (
    <button
      type="button"
      className={`nl-row${selected ? ' is-selected' : ''} ${className}`}
      onClick={onClick}
      aria-current={selected || undefined}
    >
      {glyph}
      <span className="nl-row-text">
        <span className="nl-row-title">{title}</span>
        {subtitle && <span className="nl-row-sub">{subtitle}</span>}
      </span>
      {trailing}
    </button>
  );
}

export function ItemRow({ item, ...rest }) {
  return (
    <Row
      glyph={<KindGlyph item={item} />}
      title={itemTitle(item)}
      subtitle={itemSubtitle(item)}
      className={`is-${item.kind}`}
      {...rest}
    />
  );
}

export function DayRow({ trip, day, ...rest }) {
  return (
    <Row
      glyph={<span className="nl-glyph is-day" aria-hidden="true">{dayNumber(trip, day)}</span>}
      title={dayTitle(trip, day)}
      subtitle={daySubtitle(day)}
      {...rest}
    />
  );
}

export function TripRow({ trip, ...rest }) {
  return (
    <Row
      glyph={<span className="nl-glyph is-trip" aria-hidden="true">◎</span>}
      title={trip.title}
      subtitle={tripSubtitle(trip)}
      {...rest}
    />
  );
}

function ListField({ value, onChange }) {
  const [text, setText] = useState(value.join(', '));
  return (
    <input
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        onChange(e.target.value.split(',').map((s) => s.trim()).filter(Boolean));
      }}
    />
  );
}

function Field({ field, value, onChange }) {
  let input;
  if (field.type === 'textarea') {
    input = <textarea rows={4} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />;
  } else if (field.type === 'select') {
    input = (
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
        {field.options.map((o) => <option key={o} value={o}>{field.labels?.[o] || o}</option>)}
      </select>
    );
  } else if (field.type === 'list') {
    input = <ListField value={value || []} onChange={onChange} />;
  } else if (field.type === 'number') {
    input = (
      <input
        type="number"
        min="0"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
      />
    );
  } else {
    input = <input type={field.type || 'text'} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />;
  }
  return (
    <label className={`nl-field${field.half ? ' is-half' : ''}`}>
      <span>{field.label}</span>
      {input}
    </label>
  );
}

/** Attribute editor for whichever node is selected; edits apply immediately. */
export function Inspector({ trip, node, dispatch, onClose, children }) {
  let eyebrow;
  let title;
  let fields;
  let target;
  let update;
  if (node.type === 'trip') {
    eyebrow = 'Trip';
    title = trip.title;
    fields = TRIP_FIELDS;
    target = trip;
    update = (key, value) => dispatch({ type: 'trip', key, value });
  } else if (node.type === 'day') {
    eyebrow = `Day ${dayNumber(trip, node.day)}`;
    title = node.day.city || 'Unplanned day';
    fields = DAY_FIELDS;
    target = node.day;
    update = (key, value) => dispatch({ type: 'day', dayId: node.day.id, key, value });
  } else {
    const { day, item } = node;
    eyebrow = `${item.kind === 'travel' ? MODE_LABEL[item.mode] : KIND_LABEL[item.kind]} · Day ${dayNumber(trip, day)}`;
    title = itemTitle(item);
    fields = ITEM_FIELDS[item.kind];
    target = item;
    update = (key, value) => dispatch({ type: 'item', dayId: day.id, itemId: item.id, key, value });
  }
  const nodeKey = node.item?.id || node.day?.id || 'trip';

  return (
    <div className="nl-inspector">
      <header className="nl-inspector-head">
        <div>
          <p className="nl-eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
        {onClose && (
          <button type="button" className="nl-icon-btn" onClick={onClose} aria-label="Close inspector">×</button>
        )}
      </header>
      <div className="nl-fields" key={nodeKey}>
        {fields.map((f) => (
          <Field key={f.key} field={f} value={getPath(target, f.key)} onChange={(v) => update(f.key, v)} />
        ))}
      </div>
      {children}
    </div>
  );
}
