import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { MarkdownBody } from './MarkdownBody';
import { api, formatWhen, taskUrl } from './contactsApi';

const PAGE = 200;
const KIND_LABEL = { people: 'Person', orgs: 'Org' };
const NUMBER_TYPES = ['number', 'currency', 'emoji', 'rating'];
const COLUMNS = [
  ['name', 'Name'],
  ['list', 'Type'],
  ['company', 'Company · Title'],
  ['groups', 'Groups'],
  ['sources', 'Sources'],
  ['match', 'Match status'],
  ['relationships', 'Links'],
  ['updated', 'Updated'],
];

function sortValue(row, key) {
  const v = row[key];
  if (Array.isArray(v)) return v.join(', ').toLowerCase();
  if (typeof v === 'number') return v;
  return String(v ?? '').toLowerCase();
}

function uniqueValues(rows, key) {
  const set = new Set();
  rows.forEach((r) => (Array.isArray(r[key]) ? r[key] : [r[key]]).forEach((v) => v && set.add(v)));
  return [...set].sort((a, b) => a.localeCompare(b));
}

function msToDateInput(ms) {
  if (ms == null || ms === '') return '';
  const d = new Date(Number(ms));
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function dateInputToMs(s) {
  if (!s) return null;
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d, 12).getTime();
}

function displayValue(spec, value = spec.value) {
  const t = spec.type;
  if (t === 'checkbox') return value ? 'Yes' : 'No';
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) return '';
  if (t === 'drop_down') return spec.options.find((o) => o.id === value)?.name || '';
  if (t === 'labels') return value.map((id) => spec.options.find((o) => o.id === id)?.name || id).join(', ');
  if (t === 'date') return new Date(Number(value)).toLocaleDateString();
  if (Array.isArray(value)) return value.map((v) => (typeof v === 'object' ? v.name || v.id : v)).join(', ');
  return String(value);
}

function isEmpty(spec) {
  return spec.type === 'checkbox' ? !spec.value : displayValue(spec) === '';
}

function groupRelationships(rels) {
  const groups = [];
  rels.forEach((r) => {
    let g = groups.find((x) => x.label.toLowerCase() === r.label.toLowerCase());
    if (!g) {
      g = { label: r.label, items: [] };
      groups.push(g);
    }
    g.items.push(r);
  });
  return groups;
}

function relDraft(r, i) {
  return { key: `r${i}`, label: r.label, target_id: r.target_id, name: r.name, target_list: r.target_list, note: r.note || '' };
}

function draftFrom(entity) {
  return {
    name: entity.name,
    status: entity.status,
    notes: entity.notes || '',
    fields: Object.fromEntries(entity.fields.map((f) => [f.id, f.value])),
    relationships: entity.relationships.map(relDraft),
  };
}

function relKey(rels) {
  return JSON.stringify(rels.map((r) => [r.label.trim(), r.target_id || '', r.note.trim()]));
}

function sameValue(a, b) {
  const norm = (v) => (v == null || v === '' || (Array.isArray(v) && v.length === 0) ? null
    : Array.isArray(v) ? [...v].sort() : v);
  return JSON.stringify(norm(a)) === JSON.stringify(norm(b));
}

function changedFields(entity, draft) {
  return entity.fields.filter((f) => !f.locked && !sameValue(f.value, draft.fields[f.id]));
}

function isDirty(entity, draft) {
  if (!entity || !draft) return false;
  return draft.name.trim() !== entity.name
    || draft.status !== entity.status
    || draft.notes.trim() !== (entity.notes || '').trim()
    || changedFields(entity, draft).length > 0
    || relKey(draft.relationships) !== relKey(entity.relationships.map(relDraft));
}

// ---- small inputs ----------------------------------------------------------------------
function FieldInput({ spec, value, onChange }) {
  const disabled = Boolean(spec.locked);
  const common = { disabled, title: spec.locked || undefined, className: 'contacts-input' };
  switch (spec.type) {
    case 'drop_down':
      return (
        <select {...common} value={value || ''} onChange={(e) => onChange(e.target.value || null)}>
          <option value="">—</option>
          {spec.options.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      );
    case 'labels':
      return (
        <div className="contacts-chips" title={spec.locked || undefined}>
          {spec.options.map((o) => {
            const on = (value || []).includes(o.id);
            return (
              <button key={o.id} type="button" disabled={disabled}
                className={`contacts-chip ${on ? 'contacts-chip--active' : ''}`}
                onClick={() => onChange(on ? value.filter((x) => x !== o.id) : [...(value || []), o.id])}>
                {o.name}
              </button>
            );
          })}
        </div>
      );
    case 'checkbox':
      return <input type="checkbox" checked={!!value} disabled={disabled} title={spec.locked || undefined}
        onChange={(e) => onChange(e.target.checked)} />;
    case 'date':
      return <input type="date" {...common} value={msToDateInput(value)}
        onChange={(e) => onChange(dateInputToMs(e.target.value))} />;
    case 'text':
      return <textarea {...common} rows={3} value={value || ''} onChange={(e) => onChange(e.target.value)} />;
    case 'short_text':
    case 'url':
    case 'email':
    case 'phone':
      return <input type="text" {...common} value={value || ''} onChange={(e) => onChange(e.target.value)} />;
    default:
      if (NUMBER_TYPES.includes(spec.type)) {
        return <input type="number" {...common} value={value ?? ''}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))} />;
      }
      return <div className="contacts-input contacts-input--static" title={spec.locked || undefined}>
        {displayValue(spec, value) || '—'}
      </div>;
  }
}

function EntityPicker({ entities, kinds, value, valueName, excludeId, onChange, disabled }) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return entities
      .filter((e) => kinds.includes(e.list) && e.id !== excludeId && !e.archived
        && (e.name.toLowerCase().includes(q) || e.company.toLowerCase().includes(q)))
      .sort((a, b) => Number(!a.name.toLowerCase().startsWith(q)) - Number(!b.name.toLowerCase().startsWith(q))
        || a.name.localeCompare(b.name))
      .slice(0, 8);
  }, [entities, kinds, excludeId, query]);

  return (
    <div className="contacts-picker">
      <input type="text" className="contacts-input" disabled={disabled}
        placeholder={kinds.length > 1 ? 'Search people and orgs…' : 'Search people…'}
        value={open ? query : valueName || ''}
        onFocus={() => { setOpen(true); setQuery(''); }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => setQuery(e.target.value)} />
      {open && matches.length > 0 && (
        <ul className="contacts-picker-menu">
          {matches.map((e) => (
            <li key={e.id}>
              <button type="button" onMouseDown={(ev) => ev.preventDefault()}
                onClick={() => { onChange(e); setOpen(false); }}>
                <span>{e.name}</span>
                <span className="email-muted">
                  {KIND_LABEL[e.list]}{e.company && e.list === 'people' ? ` · ${e.company}` : ''}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {value && !open && <span className="email-muted contacts-picker-kind">{KIND_LABEL[entities.find((e) => e.id === value)?.list] || ''}</span>}
    </div>
  );
}

function targetKindsFor(entity, label) {
  const kinds = Object.keys(entity.suggestions);
  const key = label.trim().toLowerCase();
  const matching = kinds.filter((k) => entity.suggestions[k].some((s) => s.toLowerCase() === key));
  return matching.length ? matching : kinds;
}

function AddRelationships({ entity, entities, existing, onAdd, onCancel }) {
  const [label, setLabel] = useState('');
  const [step, setStep] = useState('type');
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState([]);
  const [note, setNote] = useState('');
  const allSuggestions = [...new Set(Object.values(entity.suggestions).flat())].sort();
  const kinds = useMemo(() => targetKindsFor(entity, label), [entity, label]);
  const taken = new Set(existing.filter((r) => r.label.trim().toLowerCase() === label.trim().toLowerCase())
    .map((r) => r.target_id));
  const pickedIds = new Set(picked.map((e) => e.id));

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return entities
      .filter((e) => kinds.includes(e.list) && e.id !== entity.id && !e.archived
        && (e.name.toLowerCase().includes(q) || e.company.toLowerCase().includes(q)))
      .sort((a, b) => Number(!a.name.toLowerCase().startsWith(q)) - Number(!b.name.toLowerCase().startsWith(q))
        || a.name.localeCompare(b.name))
      .slice(0, 30);
  }, [entities, kinds, entity.id, query]);

  const toggle = (e) => setPicked(pickedIds.has(e.id) ? picked.filter((x) => x.id !== e.id) : [...picked, e]);
  const next = () => { if (label.trim()) setStep('targets'); };
  const add = () => onAdd(picked.map((e, i) => ({
    key: `new${Date.now()}-${i}`, label: label.trim(), target_id: e.id, name: e.name, target_list: e.list,
    note: note.trim(),
  })));

  if (step === 'type') {
    return (
      <div className="contacts-rel-add-panel">
        <label className="contacts-field">
          <span className="contacts-field-name">Relationship type</span>
          <input type="text" className="contacts-input" list="rel-add-labels" autoFocus
            placeholder="Pick or type, e.g. Works at" value={label}
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); next(); } }} />
          <datalist id="rel-add-labels">{allSuggestions.map((s) => <option key={s} value={s} />)}</datalist>
        </label>
        <div className="contacts-rel-add-actions">
          <button type="button" className="editorial-button" disabled={!label.trim()} onClick={next}>Next</button>
          <button type="button" className="asset-btn-muted" onClick={onCancel}>Cancel</button>
        </div>
      </div>
    );
  }

  return (
    <div className="contacts-rel-add-panel">
      <div>
        <strong>{label.trim()}</strong>{' '}
        <button type="button" className="contacts-linkish" onClick={() => setStep('type')}>change</button>
        <span className="email-muted"> · pick {kinds.length > 1 ? 'people and organizations' : kinds[0] === 'orgs' ? 'organizations' : 'people'}</span>
      </div>
      {picked.length > 0 && (
        <div className="contacts-chips">
          {picked.map((e) => (
            <button key={e.id} type="button" className="contacts-chip contacts-chip--active" title="Remove"
              onClick={() => toggle(e)}>
              {e.name} ×
            </button>
          ))}
        </div>
      )}
      <input type="search" className="contacts-input" autoFocus placeholder="Search by name or company…"
        value={query} onChange={(e) => setQuery(e.target.value)} />
      {query.trim() && (
        <ul className="contacts-rel-add-results">
          {matches.length === 0 && <li className="email-muted">No matches.</li>}
          {matches.map((e) => {
            const already = taken.has(e.id);
            return (
              <li key={e.id}>
                <label className={`contacts-check ${already ? 'contacts-check--disabled' : ''}`}
                  title={already ? `Already "${label.trim()}"` : undefined}>
                  <input type="checkbox" disabled={already} checked={already || pickedIds.has(e.id)}
                    onChange={() => toggle(e)} />
                  <span>
                    {e.name}
                    <span className="email-muted">
                      {' '}· {KIND_LABEL[e.list]}{e.company && e.list === 'people' ? ` · ${e.company}` : ''}
                    </span>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      )}
      <input type="text" className="contacts-input" placeholder="Note for all of them (optional)" value={note}
        onChange={(e) => setNote(e.target.value)} />
      <div className="contacts-rel-add-actions">
        <button type="button" className="editorial-button" disabled={picked.length === 0} onClick={add}>
          Add {picked.length || ''} {picked.length === 1 ? 'relationship' : 'relationships'}
        </button>
        <button type="button" className="asset-btn-muted" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

function RelationshipEditor({ entity, rows, setRows, entities }) {
  const [adding, setAdding] = useState(false);
  const kinds = entity.list === 'people' ? ['people', 'orgs'] : ['people'];
  const allSuggestions = [...new Set(Object.values(entity.suggestions).flat())];
  const update = (key, patch) => setRows(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  return (
    <div className="contacts-rel-editor">
      {rows.length === 0 && <p className="email-muted">No relationships.</p>}
      {rows.map((r) => {
        const listId = `rel-labels-${r.key}`;
        const suggestions = r.target_list ? entity.suggestions[r.target_list] || [] : allSuggestions;
        return (
          <div key={r.key} className="contacts-rel-row">
            <input type="text" className="contacts-input" list={listId} placeholder="Type, e.g. Works at"
              value={r.label} onChange={(e) => update(r.key, { label: e.target.value })} />
            <datalist id={listId}>{suggestions.map((s) => <option key={s} value={s} />)}</datalist>
            {r.target_id && !r.target_list ? (
              <div className="contacts-input contacts-input--static" title="This task isn't in the People or Orgs list">
                {r.name} <span className="email-muted">(outside the lists)</span>
              </div>
            ) : (
              <EntityPicker entities={entities} kinds={kinds} value={r.target_id} valueName={r.name}
                excludeId={entity.id}
                onChange={(e) => update(r.key, { target_id: e.id, name: e.name, target_list: e.list })} />
            )}
            <input type="text" className="contacts-input" placeholder="Note (optional)" value={r.note}
              onChange={(e) => update(r.key, { note: e.target.value })} />
            <button type="button" className="asset-btn-muted" title="Remove this relationship"
              onClick={() => setRows(rows.filter((x) => x.key !== r.key))}>
              Remove
            </button>
          </div>
        );
      })}
      {adding ? (
        <AddRelationships entity={entity} entities={entities} existing={rows}
          onCancel={() => setAdding(false)}
          onAdd={(added) => { setRows([...rows, ...added]); setAdding(false); }} />
      ) : (
        <button type="button" className="asset-btn-muted contacts-rel-add" onClick={() => setAdding(true)}>
          + Add relationships
        </button>
      )}
      <p className="email-muted contacts-rel-help">
        Saving also updates the other side: a "Parent of" here shows as "Child of" on the other person, and
        "Works at" shows as "Employs" on the organization.
      </p>
    </div>
  );
}

function RelationshipSummary({ rels, onOpen, known }) {
  if (rels.length === 0) return <p className="email-muted">No relationships.</p>;
  return (
    <ul className="contacts-rel-summary">
      {groupRelationships(rels).map((g) => (
        <li key={g.label}>
          <strong>{g.label}:</strong>{' '}
          {g.items.map((r, i) => (
            <span key={`${r.target_id}-${i}`}>
              {i > 0 && ', '}
              {known.has(r.target_id) ? (
                <button type="button" className="contacts-linkish" onClick={() => onOpen(r.target_id)}>{r.name}</button>
              ) : (
                <a href={taskUrl(r.target_id)} target="_blank" rel="noopener noreferrer">{r.name}</a>
              )}
              {r.note && <span className="email-muted"> ({r.note})</span>}
            </span>
          ))}
        </li>
      ))}
    </ul>
  );
}

function fieldByKey(entity, key) {
  return entity.fields.find((f) => f.key === key);
}

function duplicateOf(entity) {
  const v = fieldByKey(entity, 'dup_of')?.value;
  return (typeof v === 'string' && v.match(/\/t\/([A-Za-z0-9_-]+)/)?.[1]) || null;
}

function MergePanel({ entity, entities, onStart, onCancel }) {
  const suggested = duplicateOf(entity);
  const [otherId, setOtherId] = useState(suggested && suggested !== entity.id ? suggested : '');
  const [keepThis, setKeepThis] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const other = entities.find((e) => e.id === otherId);

  const start = async () => {
    setBusy(true);
    setError('');
    try {
      await onStart(keepThis ? entity.id : otherId, keepThis ? otherId : entity.id);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="contacts-rel-add-panel">
      <strong>Merge two records for the same person</strong>
      <label className="contacts-field">
        <span className="contacts-field-name">Other record</span>
        <EntityPicker entities={entities} kinds={['people']} value={otherId} valueName={other?.name || ''}
          excludeId={entity.id} onChange={(e) => setOtherId(e.id)} />
        {other && (
          <span className="email-muted">
            {[other.company, other.title].filter(Boolean).join(' · ') || 'no company'}
            {' · '}{other.sources.join(', ') || 'no sources'}{other.match ? ` · ${other.match}` : ''}
            {' · '}<a href={taskUrl(other.id)} target="_blank" rel="noopener noreferrer">open in ClickUp</a>
          </span>
        )}
      </label>
      {other && (
        <div className="contacts-merge-choice">
          <label className="contacts-check">
            <input type="radio" checked={keepThis} onChange={() => setKeepThis(true)} />
            <span>Keep <strong>this record</strong> ({entity.name}) and fold the other into it</span>
          </label>
          <label className="contacts-check">
            <input type="radio" checked={!keepThis} onChange={() => setKeepThis(false)} />
            <span>Keep <strong>the other record</strong> ({other.name}) and fold this one into it</span>
          </label>
        </div>
      )}
      <p className="email-muted contacts-rel-help">
        The record you keep gains the other’s emails, phones, groups and sources, plus its LinkedIn and WhatsApp
        links, company, title and other details wherever it has none, and becomes active. The other is marked merged and archived. Two records that
        are both linked to live Google contacts can’t be merged: merge them in Google first. This starts a
        preview; nothing changes until you apply it in Runs.
      </p>
      {error && <div className="error-message">{error}</div>}
      <div className="contacts-rel-add-actions">
        <button type="button" className="editorial-button" disabled={!other || busy} onClick={start}>
          {busy ? 'Starting…' : 'Preview merge'}
        </button>
        <button type="button" className="asset-btn-muted" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

// ---- detail / editor -------------------------------------------------------------------
function EntityDetail({ token, id, entities, known, canEdit, editBlocked, onOpen, onSaved, onDirtyChange,
  onStartMerge }) {
  const [entity, setEntity] = useState(null);
  const [merging, setMerging] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [notice, setNotice] = useState(null);

  const load = useCallback(async () => {
    setLoadError('');
    try {
      setEntity(await api(`entities/${id}/`, { token }));
    } catch (err) {
      setLoadError(err.message);
    }
  }, [id, token]);

  useEffect(() => {
    let cancelled = false;
    api(`entities/${id}/`, { token })
      .then((e) => !cancelled && setEntity(e))
      .catch((err) => !cancelled && setLoadError(err.message));
    return () => { cancelled = true; };
  }, [id, token]);

  const dirty = isDirty(entity, draft);
  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);

  const startEdit = () => {
    setDraft(draftFrom(entity));
    setSaveError(null);
    setNotice(null);
  };

  const cancel = () => {
    if (dirty && !window.confirm('Discard your unsaved changes?')) return;
    setDraft(null);
    setSaveError(null);
  };

  const reload = async () => {
    setDraft(null);
    setSaveError(null);
    await load();
  };

  const save = async () => {
    const body = { date_updated: entity.date_updated };
    if (draft.name.trim() !== entity.name) body.name = draft.name;
    if (draft.status !== entity.status) body.status = draft.status;
    if (draft.notes.trim() !== (entity.notes || '').trim()) body.notes = draft.notes;
    const fields = changedFields(entity, draft);
    if (fields.length) body.fields = Object.fromEntries(fields.map((f) => [f.id, draft.fields[f.id] ?? null]));
    if (relKey(draft.relationships) !== relKey(entity.relationships.map(relDraft))) {
      const incomplete = draft.relationships.some((r) => !r.label.trim() || !r.target_id);
      if (incomplete) {
        setSaveError({ message: 'Every relationship needs a type and a person or organization (or remove the row).' });
        return;
      }
      body.relationships = draft.relationships.map((r) => ({ label: r.label, target_id: r.target_id, note: r.note }));
    }
    setSaving(true);
    setSaveError(null);
    try {
      const out = await api(`entities/${id}/`, { token, method: 'PUT', body });
      setEntity(out.entity);
      setDraft(null);
      onSaved(out.rows);
      setNotice({ text: out.changed ? 'Saved to ClickUp.' : 'Nothing changed.', warnings: out.warnings || [] });
    } catch (err) {
      setSaveError({ message: err.message, conflict: err.status === 409 && /changed in ClickUp/.test(err.message) });
    } finally {
      setSaving(false);
    }
  };

  if (loadError) return <div className="error-message">{loadError}</div>;
  if (!entity) return <p className="email-muted">Loading from ClickUp…</p>;

  const editing = Boolean(draft);
  const editable = entity.fields.filter((f) => !f.locked);
  const locked = entity.fields.filter((f) => f.locked);
  const setField = (fid, v) => setDraft({ ...draft, fields: { ...draft.fields, [fid]: v } });

  return (
    <div className="contacts-entity">
      <div className="contacts-entity-head">
        <div>
          {editing ? (
            <input type="text" className="contacts-input contacts-entity-name-input" value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })} aria-label="Name" />
          ) : (
            <h3>{entity.name}</h3>
          )}
          <div className="email-muted">
            {entity.list_name} · {editing ? (
              <select value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })}>
                {entity.statuses.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            ) : entity.status}
            {entity.archived && ' · archived'}
            {' · '}
            <a href={entity.url} target="_blank" rel="noopener noreferrer">Open in ClickUp</a>
          </div>
        </div>
        <div className="contacts-entity-actions">
          {editing ? (
            <>
              <button type="button" className="editorial-button" disabled={!dirty || saving} onClick={save}>
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button type="button" className="asset-btn-muted" disabled={saving} onClick={cancel}>Cancel</button>
            </>
          ) : (
            <>
              <button type="button" className="editorial-button" disabled={!canEdit || !!editBlocked}
                title={editBlocked || undefined} onClick={startEdit}>
                Edit
              </button>
              {entity.list === 'people' && !entity.archived && (
                <button type="button" className="asset-btn-muted" onClick={() => setMerging(!merging)}
                  title="Merge this record with another record for the same person">
                  Merge…
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {!editing && !merging && duplicateOf(entity) && duplicateOf(entity) !== entity.id && (
        <div className="contacts-banner contacts-banner--warn">
          Possibly a duplicate of{' '}
          {known.has(duplicateOf(entity)) ? (
            <button type="button" className="contacts-linkish" onClick={() => onOpen(duplicateOf(entity))}>
              {entities.find((e) => e.id === duplicateOf(entity))?.name || duplicateOf(entity)}
            </button>
          ) : (
            <a href={taskUrl(duplicateOf(entity))} target="_blank" rel="noopener noreferrer">another record</a>
          )}
          .{' '}
          {entity.list === 'people' && (
            <button type="button" className="contacts-linkish" onClick={() => setMerging(true)}>Merge them…</button>
          )}
        </div>
      )}
      {!editing && merging && (
        <MergePanel entity={entity} entities={entities} onCancel={() => setMerging(false)}
          onStart={onStartMerge} />
      )}

      {editing && editBlocked && <div className="contacts-banner contacts-banner--warn">{editBlocked}</div>}
      {notice && (
        <div className="asset-status">
          {notice.text}
          {notice.warnings.map((w) => <div key={w} className="contacts-banner contacts-banner--warn">{w}</div>)}
        </div>
      )}
      {saveError && (
        <div className="error-message">
          {saveError.message}{' '}
          {saveError.conflict && <button type="button" className="asset-btn-muted" onClick={reload}>Reload</button>}
        </div>
      )}

      <section>
        <h4>Relationships</h4>
        {editing && entity.relationships_editable ? (
          <RelationshipEditor entity={entity} entities={entities} rows={draft.relationships}
            setRows={(rows) => setDraft({ ...draft, relationships: rows })} />
        ) : (
          <>
            <RelationshipSummary rels={entity.relationships} onOpen={onOpen} known={known} />
            {editing && (
              <div className="contacts-banner contacts-banner--warn">
                The relationship sections of this description contain text the editor doesn’t understand
                ({entity.unparsed.join(' / ')}), so relationships and notes can only be changed in ClickUp.
              </div>
            )}
          </>
        )}
      </section>

      <section>
        <h4>Details</h4>
        {editing ? (
          <div className="contacts-field-grid">
            {editable.map((f) => (
              <label key={f.id} className="contacts-field">
                <span className="contacts-field-name">{f.name}</span>
                <FieldInput spec={f} value={draft.fields[f.id]} onChange={(v) => setField(f.id, v)} />
                {f.hint && <span className="email-muted contacts-field-hint">{f.hint}</span>}
              </label>
            ))}
          </div>
        ) : (
          <FieldList specs={editable} />
        )}
      </section>

      <section>
        <h4>Notes</h4>
        {editing ? (
          <textarea className="contacts-input contacts-notes" rows={6} value={draft.notes}
            disabled={!entity.relationships_editable}
            onChange={(e) => setDraft({ ...draft, notes: e.target.value })} />
        ) : entity.notes ? (
          <div className="contacts-notes-view"><MarkdownBody>{entity.notes}</MarkdownBody></div>
        ) : (
          <p className="email-muted">No notes.</p>
        )}
      </section>

      {locked.length > 0 && (
        <details className="contacts-locked">
          <summary><h4>Managed by sync ({locked.length})</h4></summary>
          <p className="email-muted">
            These are filled in by the Google, LinkedIn and WhatsApp syncs, so they can’t be changed here. Hover a
            field to see why.
          </p>
          {editing ? (
            <div className="contacts-field-grid">
              {locked.map((f) => (
                <label key={f.id} className="contacts-field contacts-field--locked" title={f.locked}>
                  <span className="contacts-field-name">{f.name}</span>
                  <FieldInput spec={f} value={f.value} onChange={() => {}} />
                </label>
              ))}
            </div>
          ) : (
            <FieldList specs={locked} lockedStyle />
          )}
        </details>
      )}
    </div>
  );
}

function FieldList({ specs, lockedStyle }) {
  const filled = specs.filter((f) => !isEmpty(f));
  const empty = specs.length - filled.length;
  return (
    <>
      {filled.length === 0 ? <p className="email-muted">Nothing filled in.</p> : (
        <dl className={`contacts-dl ${lockedStyle ? 'contacts-dl--locked' : ''}`}>
          {filled.map((f) => (
            <div key={f.id} title={f.locked || undefined}>
              <dt>{f.name}</dt>
              <dd>
                {f.type === 'url' && f.value ? (
                  <a href={f.value} target="_blank" rel="noopener noreferrer">{f.value}</a>
                ) : displayValue(f)}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {empty > 0 && <p className="email-muted contacts-empty-count">{empty} empty field{empty === 1 ? '' : 's'} not shown.</p>}
    </>
  );
}

// ---- the tab ---------------------------------------------------------------------------
export function EntitiesTab({ token, writesEnabled, liveRunActive, onDirtyChange, onStartMerge }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [q, setQ] = useState('');
  const [kind, setKind] = useState('');
  const [group, setGroup] = useState('');
  const [source, setSource] = useState('');
  const [match, setMatch] = useState('');
  const [linkedOnly, setLinkedOnly] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [sort, setSort] = useState({ key: 'name', dir: 1 });
  const [shown, setShown] = useState({ key: '', n: PAGE });
  const [selectedId, setSelectedId] = useState(null);
  const dirtyRef = useRef(false);
  const query = useDeferredValue(q);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setError('');
    try {
      setData(await api('entities/', { token, method: 'POST' }));
    } catch (err) {
      setError(err.message);
    } finally {
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => {
    let cancelled = false;
    api('entities/', { token })
      .then((d) => {
        if (cancelled) return;
        setData(d);
        if (!d.loaded) refresh();
      })
      .catch((err) => !cancelled && setError(err.message));
    return () => { cancelled = true; };
  }, [token, refresh]);

  const setDirty = useCallback((d) => {
    dirtyRef.current = d;
    onDirtyChange(d);
  }, [onDirtyChange]);

  useEffect(() => {
    const warn = (e) => {
      if (!dirtyRef.current) return;
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, []);

  const open = (id) => {
    if (id === selectedId) return;
    if (dirtyRef.current && !window.confirm('Discard your unsaved changes?')) return;
    setSelectedId(id);
  };

  const entities = useMemo(() => data?.entities || [], [data]);
  const known = useMemo(() => new Set(entities.map((e) => e.id)), [entities]);
  const options = useMemo(() => ({
    groups: uniqueValues(entities, 'groups'),
    sources: uniqueValues(entities, 'sources'),
    matches: uniqueValues(entities, 'match'),
  }), [entities]);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const out = entities.filter((e) => (showArchived || !e.archived)
      && (!kind || e.list === kind)
      && (!group || e.groups.includes(group))
      && (!source || e.sources.includes(source))
      && (!match || e.match === match)
      && (!linkedOnly || e.relationships > 0)
      && (!needle || [e.name, e.company, e.title, e.emails, e.phones].some((v) => v.toLowerCase().includes(needle))));
    out.sort((a, b) => {
      const x = sortValue(a, sort.key);
      const y = sortValue(b, sort.key);
      const c = typeof x === 'number' ? x - y : x.localeCompare(y);
      return c * sort.dir || a.name.localeCompare(b.name);
    });
    return out;
  }, [entities, query, kind, group, source, match, linkedOnly, showArchived, sort]);

  const filterKey = JSON.stringify([query, kind, group, source, match, linkedOnly, showArchived, sort]);
  const limit = shown.key === filterKey ? shown.n : PAGE;
  const showMore = () => setShown({ key: filterKey, n: limit + PAGE });

  const onSaved = useCallback((updated) => {
    if (!updated?.length) return;
    setData((d) => {
      const byId = Object.fromEntries(updated.map((r) => [r.id, r]));
      const kept = d.entities.map((e) => byId[e.id] || e);
      const added = updated.filter((r) => !d.entities.some((e) => e.id === r.id));
      return { ...d, entities: [...kept, ...added] };
    });
  }, []);

  const toggleSort = (key) => setSort((s) => (s.key === key ? { key, dir: -s.dir }
    : { key, dir: ['updated', 'relationships'].includes(key) ? -1 : 1 }));

  const editBlocked = !writesEnabled
    ? 'Editing needs live ClickUp writes, which are off on this server (CONTACTS_CLICKUP_WRITES_ENABLED).'
    : liveRunActive ? 'A sync is running. Edit when it has finished.' : '';

  if (!data && !error) return <p className="email-muted">Loading…</p>;

  return (
    <>
      <div className="contacts-toolbar">
        <input type="search" placeholder="Search name, company, email, phone…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">People and Orgs</option>
          <option value="people">People</option>
          <option value="orgs">Orgs</option>
        </select>
        <select value={group} onChange={(e) => setGroup(e.target.value)}>
          <option value="">Any group</option>
          {options.groups.map((g) => <option key={g} value={g}>{g}</option>)}
        </select>
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">Any source</option>
          {options.sources.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={match} onChange={(e) => setMatch(e.target.value)}>
          <option value="">Any match status</option>
          {options.matches.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <label className="contacts-check"><input type="checkbox" checked={linkedOnly} onChange={(e) => setLinkedOnly(e.target.checked)} /> Has relationships</label>
        <label className="contacts-check"><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> Archived</label>
      </div>
      <div className="contacts-toolbar email-muted">
        <span>
          {rows.length} of {entities.length} · list read from ClickUp {formatWhen(data?.refreshed_at)}
        </span>
        <button type="button" className="asset-btn-muted" disabled={refreshing} onClick={refresh}
          title="Re-read both lists from ClickUp. Only reads; takes about a minute.">
          {refreshing ? 'Reading ClickUp…' : 'Refresh list'}
        </button>
      </div>
      {error && <div className="error-message">{error}</div>}
      {data?.stale && !refreshing && (
        <div className="contacts-banner contacts-banner--warn">
          A live sync changed ClickUp after this list was read. Refresh the list to see its changes (details are always
          read fresh).
        </div>
      )}
      {refreshing && !data?.loaded && (
        <p className="email-muted">Reading the People and Orgs lists from ClickUp for the first time. This takes about a minute.</p>
      )}

      <div className="contacts-entities-layout">
        <div className="contacts-scroll contacts-entity-list">
          <table className="contacts-table">
            <thead>
              <tr>
                {COLUMNS.map(([key, label]) => (
                  <th key={key}>
                    <button type="button" className="contacts-sort" onClick={() => toggleSort(key)}>
                      {label}{sort.key === key ? (sort.dir > 0 ? ' ▲' : ' ▼') : ''}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, limit).map((e) => (
                <tr key={e.id} className={`contacts-entity-row ${e.id === selectedId ? 'contacts-entity-row--active' : ''}`}
                  onClick={() => open(e.id)}>
                  <td>{e.name}{e.archived && <span className="email-muted"> (archived)</span>}</td>
                  <td>{KIND_LABEL[e.list]}</td>
                  <td className="contacts-cell-wrap">{[e.company, e.title].filter(Boolean).join(' · ')}</td>
                  <td className="contacts-cell-wrap">{e.groups.join(', ')}</td>
                  <td>{e.sources.join(', ')}</td>
                  <td>{e.match}</td>
                  <td>{e.relationships || ''}</td>
                  <td>{e.updated ? new Date(e.updated).toLocaleDateString() : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > limit && (
            <button type="button" className="asset-btn-muted contacts-more" onClick={showMore}>
              Show {Math.min(PAGE, rows.length - limit)} more
            </button>
          )}
          {data?.loaded && rows.length === 0 && <p className="email-muted">Nothing matches these filters.</p>}
        </div>
        <div className="contacts-entity-panel">
          {selectedId ? (
            <EntityDetail key={selectedId} token={token} id={selectedId} entities={entities} known={known}
              canEdit={writesEnabled} editBlocked={editBlocked} onOpen={open} onSaved={onSaved}
              onDirtyChange={setDirty} onStartMerge={onStartMerge} />
          ) : (
            <p className="email-muted">Select a person or organization to see its details.</p>
          )}
        </div>
      </div>
    </>
  );
}
