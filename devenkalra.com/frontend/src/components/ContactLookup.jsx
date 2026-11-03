import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, formatWhen } from './contactsApi';

const OUTCOMES = {
  exists: ['Exists', 'success'],
  unlinked: ['Exists, unlinked', 'warn'],
  clickup_only: ['ClickUp only', 'warn'],
  google_only: ['Google only', 'warn'],
  not_found: ['Not found', ''],
  review: ['Needs review', 'warn'],
  conflict: ['Conflict', 'failed'],
};
const ACTIONS = {
  link: 'Link',
  create_google: 'Create in Google & link',
  import_clickup: 'Import into ClickUp',
  create_both: 'Create in Google & ClickUp',
};
const AS_NEW = {
  create_both: 'Create in Google & ClickUp as new',
  import_clickup: 'Import into ClickUp as new',
  create_google: 'Create in Google as new & link',
};
const DONE = {
  link: 'Linked', create_google: 'Created in Google', import_clickup: 'Imported into ClickUp',
  create_both: 'Created in both',
};
const SIDES = { clickup: 'ClickUp', google: 'Google' };
const OLD_CACHE_MS = 60 * 60 * 1000;
const EMPTY_ENTRY = { name: '', email: '', phone: '' };

const CATEGORIES = {
  ...Object.fromEntries(Object.entries(OUTCOMES).map(([k, [label]]) => [k, label])),
  done: 'Done',
};

function category(row) {
  return row.done ? 'done' : row.result?.outcome;
}

function OutcomePill({ outcome }) {
  const [label, tone] = OUTCOMES[outcome] || [outcome, ''];
  return <span className={`email-pill ${tone ? `email-pill--${tone}` : ''}`}>{label}</span>;
}

function ageMs(iso) {
  return iso ? Date.now() - new Date(iso).getTime() : Infinity;
}

function csvCell(v) {
  const s = String(v ?? '');
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadResults(lk) {
  const head = ['Line', 'Name', 'Emails', 'Phones', 'Outcome', 'ClickUp', 'ClickUp link', 'Google', 'Google link',
    'Conflicts', 'Notes', 'Done'];
  const lines = lk.rows.map((r) => {
    const res = r.result || {};
    const cu = res.clickup?.status === 'exact' ? res.clickup.candidates[0] : null;
    const g = res.google?.status === 'exact' ? res.google.candidates[0] : null;
    return [r.line ?? r.index + 1, r.input.name, r.input.emails.join('; '), r.input.phones.join('; '),
      OUTCOMES[res.outcome]?.[0] || res.outcome, cu?.name, cu?.link, g?.name, g?.link,
      (res.conflicts || []).join(' | '), (res.notes || []).join(' | '), r.done ? DONE[r.done.action] : '']
      .map(csvCell).join(',');
  });
  const blob = new Blob([[head.join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${(lk.name || 'comparison').replace(/\.csv$/i, '')}-results.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function Match({ side }) {
  if (!side) return null;
  if (side.status === 'exact') {
    const c = side.candidates[0];
    return (
      <div>
        <a href={c.link} target="_blank" rel="noreferrer">{c.name || '(no name)'}</a>
        <div className="email-muted">{c.reasons.join(', ')}</div>
      </div>
    );
  }
  if (side.status === 'rough') return <span className="email-muted">{side.candidates.length} possible</span>;
  if (side.status === 'conflict') return <span className="email-muted">several records</span>;
  return <span className="email-muted">{side.chosen ? 'marked as not here' : 'none'}</span>;
}

function Chooser({ row, sideKey, disabled, onChoose }) {
  const side = row.result[sideKey];
  const chosen = row.choice?.[sideKey];
  if (side.status !== 'rough' && !chosen) return null;
  return (
    <div className="contacts-lookup-choose">
      <strong>{SIDES[sideKey]}:</strong>
      {side.status === 'rough' && side.candidates.map((c) => (
        <div key={c.id} className="contacts-lookup-cand">
          <a href={c.link} target="_blank" rel="noreferrer">{c.name || '(no name)'}</a>
          <span className="email-muted"> {[...c.emails, ...c.phones].join(', ')} · {c.reasons.join(', ')}</span>
          <button type="button" className="asset-btn-muted" disabled={disabled}
            onClick={() => onChoose(row, sideKey, c.id)}>Use this match</button>
        </div>
      ))}
      {side.status === 'rough' && (
        <button type="button" className="asset-btn-muted" disabled={disabled}
          onClick={() => onChoose(row, sideKey, 'new')}>Not in {SIDES[sideKey]}</button>
      )}
      {chosen && (
        <button type="button" className="asset-btn-muted" disabled={disabled}
          onClick={() => onChoose(row, sideKey, '')}>Undo my choice</button>
      )}
    </div>
  );
}

export function LookupTab({ token, writesEnabled, googleConnected, googleCanWrite, liveRunActive }) {
  const [caches, setCaches] = useState(null);
  const [saved, setSaved] = useState([]);
  const [current, setCurrent] = useState(null);
  const [entry, setEntry] = useState(EMPTY_ENTRY);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [hidden, setHidden] = useState(() => new Set());
  const [checked, setChecked] = useState(() => new Set());
  const [progress, setProgress] = useState(null);
  const cancelRun = useRef(false);

  const blocked = !writesEnabled
    ? 'Live ClickUp writes are disabled on this server, so actions are off.'
    : !googleConnected
      ? 'Connect Google on the Overview tab first.'
      : !googleCanWrite
        ? 'Grant write access to Google Contacts on the Overview tab to run actions.'
        : liveRunActive ? 'A live sync is running; run actions after it finishes.' : '';

  const loadCaches = useCallback(async () => setCaches(await api('lookups/caches/', { token })), [token]);
  const loadSaved = useCallback(async () => setSaved(await api('lookups/', { token })), [token]);

  useEffect(() => {
    if (!googleConnected) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const [c, s] = await Promise.all([api('lookups/caches/', { token }), api('lookups/', { token })]);
        if (!cancelled) {
          setCaches(c);
          setSaved(s);
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    })();
    return () => { cancelled = true; };
  }, [googleConnected, token]);

  const call = async (label, fn) => {
    setBusy(label);
    setError('');
    setNotice('');
    try {
      await fn();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const show = (lk) => {
    setCurrent(lk);
    setChecked(new Set());
    loadSaved().catch(() => {});
  };

  const refreshClickUp = () => call('clickup', async () => {
    await api('entities/', { token, method: 'POST' });
    await loadCaches();
    setNotice('ClickUp cache refreshed. Re-check an open comparison to use it.');
  });

  const refreshGoogle = () => call('google', async () => {
    setCaches(await api('lookups/caches/', { token, method: 'POST' }));
  });

  const checkEntry = () => call('check', async () => {
    show(await api('lookups/', { token, method: 'POST', body: { rows: [entry] } }));
    setEntry(EMPTY_ENTRY);
  });

  const upload = (file) => call('upload', async () => {
    const form = new FormData();
    form.append('file', file);
    show(await api('lookups/', { token, method: 'POST', form }));
  });

  const open = (id) => call('open', async () => show(await api(`lookups/${id}/`, { token })));

  const remove = (id) => call('delete', async () => {
    if (!window.confirm('Delete this saved comparison? Nothing in ClickUp or Google changes.')) return;
    await api(`lookups/${id}/`, { token, method: 'DELETE' });
    if (current?.id === id) setCurrent(null);
    await loadSaved();
  });

  const recheck = () => call('recheck', async () => {
    show(await api(`lookups/${current.id}/recheck/`, { token, method: 'POST' }));
    await loadCaches();
  });

  const choose = (row, side, value) => call('choose', async () => {
    setCurrent(await api(`lookups/${current.id}/choose/`,
      { token, method: 'POST', body: { row: row.index, side, value } }));
  });

  const runOne = async (row, action = row.result.action) => {
    const lk = await api(`lookups/${current.id}/act/`, { token, method: 'POST', body: { row: row.index, action } });
    setCurrent(lk);
    return lk.rows.find((r) => r.index === row.index)?.done?.warnings || [];
  };

  const actOne = (row, action = row.result.action) => call('act', async () => {
    const warnings = await runOne(row, action);
    setNotice(warnings.length ? warnings.join('\n') : `${DONE[action]}: ${row.input.name || 'row'}.`);
    loadSaved().catch(() => {});
  });

  const actAsNew = (row) => {
    const { new_action: action } = row.result;
    if (!window.confirm(`${AS_NEW[action]}?\n\nThe possible matches are ignored and "${row.input.name
      || 'this row'}" is created from the row's data.`)) return;
    actOne(row, action);
  };

  const runSelected = async () => {
    const rows = current.rows.filter((r) => checked.has(r.index) && r.result?.action && !r.done
      && !hidden.has(category(r)));
    if (!rows.length) return;
    const counts = rows.reduce((acc, r) => ({ ...acc, [r.result.action]: (acc[r.result.action] || 0) + 1 }), {});
    const summary = Object.entries(counts).map(([a, n]) => `${n} × ${ACTIONS[a]}`).join('\n');
    if (!window.confirm(`Run these actions?\n\n${summary}`)) return;
    cancelRun.current = false;
    setBusy('bulk');
    setError('');
    setNotice('');
    const failed = [];
    const warnings = [];
    for (let i = 0; i < rows.length; i += 1) {
      if (cancelRun.current) break;
      setProgress({ done: i, total: rows.length });
      try {
        warnings.push(...await runOne(rows[i]));
      } catch (err) {
        failed.push(`Row ${rows[i].line ?? rows[i].index + 1} (${rows[i].input.name || 'no name'}): ${err.message}`);
      }
    }
    setProgress(null);
    setBusy('');
    setChecked(new Set());
    if (failed.length) setError(failed.join('\n'));
    setNotice([cancelRun.current ? 'Stopped.' : 'Finished.', ...warnings].join('\n'));
    loadSaved().catch(() => {});
  };

  const rows = useMemo(() => {
    if (!current) return [];
    return current.rows.filter((r) => !hidden.has(category(r)));
  }, [current, hidden]);
  const counts = useMemo(() => (current ? current.rows.reduce((acc, r) => {
    const k = category(r);
    return { ...acc, [k]: (acc[k] || 0) + 1 };
  }, {}) : {}), [current]);
  const showCategory = (key, on) => setHidden((prev) => {
    const next = new Set(prev);
    if (on) next.delete(key);
    else next.add(key);
    return next;
  });
  const showOnly = (key) => setHidden(new Set(Object.keys(CATEGORIES).filter((k) => k !== key)));
  const actionable = rows.filter((r) => r.result?.action && !r.done);
  const selectedCount = actionable.filter((r) => checked.has(r.index)).length;
  const allChecked = actionable.length > 0 && actionable.every((r) => checked.has(r.index));
  const toggle = (index, on) => setChecked((prev) => {
    const next = new Set(prev);
    if (on) next.add(index);
    else next.delete(index);
    return next;
  });

  if (!googleConnected) {
    return <p className="email-muted">Connect Google on the Overview tab to check contacts.</p>;
  }

  const cu = caches?.clickup;
  const cacheWarn = cu && (!cu.loaded || cu.outdated || cu.stale || ageMs(cu.refreshed_at) > OLD_CACHE_MS);
  const newerCache = current && cu?.refreshed_at && current.clickup_as_of
    && new Date(cu.refreshed_at) > new Date(current.clickup_as_of);
  const working = !!busy;

  return (
    <div className="contacts-lookup">
      <div className="contacts-banner contacts-banner--info">
        Refresh the ClickUp cache before comparing. Comparisons read ClickUp from that cache, not live, so people
        added or changed in ClickUp since the last refresh aren’t seen. Comparing never writes anything; each
        action runs only when you click its button.
      </div>
      {notice && <div className="asset-status" style={{ whiteSpace: 'pre-wrap' }}>{notice}</div>}
      {error && <div className="error-message" style={{ whiteSpace: 'pre-wrap' }}>{error}</div>}

      <div className="contacts-lookup-caches">
        <div className={cacheWarn ? 'contacts-lookup-cache--warn' : ''}>
          <strong>ClickUp cache:</strong>{' '}
          {!cu ? '…' : !cu.loaded ? 'not loaded' : (
            <>
              {cu.people} people · refreshed {formatWhen(cu.refreshed_at)}
              {cu.outdated && ' · predates Google links, refresh required'}
              {!cu.outdated && cu.stale && ' · a live sync ran since'}
              {!cu.outdated && !cu.stale && ageMs(cu.refreshed_at) > OLD_CACHE_MS && ' · over an hour old'}
            </>
          )}
          <button type="button" className="asset-btn-muted" disabled={working} onClick={refreshClickUp}>
            {busy === 'clickup' ? 'Refreshing… (about a minute)' : 'Refresh ClickUp cache'}
          </button>
        </div>
        <div>
          <strong>Google:</strong>{' '}
          {caches?.google?.fetched_at
            ? `${caches.google.contacts} contacts · read ${formatWhen(caches.google.fetched_at)}`
            : 'read on the first comparison'}
          <button type="button" className="asset-btn-muted" disabled={working} onClick={refreshGoogle}>
            {busy === 'google' ? 'Reading…' : 'Refresh Google'}
          </button>
        </div>
      </div>

      <div className="contacts-bulk-panel">
        <strong>Check one contact</strong>
        <div className="contacts-field-grid">
          {[['name', 'Name'], ['email', 'Email'], ['phone', 'Phone']].map(([key, label]) => (
            <label key={key} className="contacts-field">
              <span className="contacts-field-name">{label}</span>
              <input type="text" className="contacts-input" value={entry[key]} disabled={working}
                onChange={(e) => setEntry((d) => ({ ...d, [key]: e.target.value }))}
                onKeyDown={(e) => { if (e.key === 'Enter') checkEntry(); }} />
            </label>
          ))}
        </div>
        <div className="contacts-rel-add-actions">
          <button type="button" className="editorial-button" onClick={checkEntry}
            disabled={working || !(entry.name.trim() || entry.email.trim() || entry.phone.trim())}>
            {busy === 'check' ? 'Checking…' : 'Check'}
          </button>
          <label className="asset-btn-muted contacts-file-btn">
            {busy === 'upload' ? 'Comparing…' : 'Compare a CSV file'}
            <input type="file" accept=".csv,text/csv" hidden disabled={working}
              onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) upload(f); }} />
          </label>
          <span className="email-muted">
            CSV headers: Name (or First name / Last name), Email, Phone. Google Contacts exports work as-is.
          </span>
        </div>
      </div>

      {saved.length > 0 && (
        <details className="contacts-details">
          <summary>Saved comparisons ({saved.length})</summary>
          <table className="contacts-table">
            <tbody>
              {saved.map((s) => (
                <tr key={s.id} className={current?.id === s.id ? 'contacts-entity-row--checked' : ''}>
                  <td><button type="button" className="contacts-link-btn" onClick={() => open(s.id)}>{s.name}</button></td>
                  <td className="email-muted">{formatWhen(s.created_at)}</td>
                  <td className="email-muted">
                    {s.summary?.total} rows{s.summary?.done ? ` · ${s.summary.done} done` : ''}
                  </td>
                  <td>
                    <button type="button" className="asset-btn-muted" disabled={working} onClick={() => remove(s.id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      {current && (
        <section className="contacts-lookup-result">
          <div className="contacts-lookup-head">
            <div>
              <h3>{current.name}</h3>
              <p className="email-muted">
                Compared {formatWhen(current.checked_at)} using the ClickUp cache from{' '}
                {formatWhen(current.clickup_as_of)} and Google as read {formatWhen(current.google_as_of)}.
                {current.columns?.ignored?.length > 0 && ` Ignored columns: ${current.columns.ignored.join(', ')}.`}
              </p>
              {newerCache && (
                <p className="contacts-lookup-cache--warn">The ClickUp cache is newer than this comparison; re-check it.</p>
              )}
            </div>
            <div className="contacts-entity-actions">
              <button type="button" className="asset-btn-muted" disabled={working} onClick={recheck}>
                {busy === 'recheck' ? 'Re-checking…' : 'Re-check'}
              </button>
              <button type="button" className="asset-btn-muted" onClick={() => downloadResults(current)}>
                Download results
              </button>
            </div>
          </div>

          <div className="contacts-lookup-filters">
            {Object.entries(CATEGORIES).filter(([k]) => counts[k]).map(([k, label]) => (
              <span key={k} className="contacts-lookup-filter">
                <label className="contacts-check">
                  <input type="checkbox" checked={!hidden.has(k)} onChange={(e) => showCategory(k, e.target.checked)} />
                  {label} ({counts[k]})
                </label>
                <button type="button" className="contacts-link-btn email-muted" onClick={() => showOnly(k)}
                  title={`Show only ${label}`}>only</button>
              </span>
            ))}
            <button type="button" className="asset-btn-muted" disabled={!hidden.size}
              onClick={() => setHidden(new Set())}>Show all</button>
            <button type="button" className="asset-btn-muted"
              onClick={() => setHidden(new Set(Object.keys(CATEGORIES)))}>Hide all</button>
          </div>

          {blocked && <div className="contacts-banner contacts-banner--warn">{blocked}</div>}
          {(selectedCount > 0 || progress) && (
            <div className="contacts-bulk-bar">
              {progress ? (
                <>
                  <span>Running {progress.done + 1} of {progress.total}…</span>
                  <button type="button" className="asset-btn-muted" onClick={() => { cancelRun.current = true; }}>Stop</button>
                </>
              ) : (
                <>
                  <span>{selectedCount} selected</span>
                  <button type="button" className="editorial-button" disabled={working || !!blocked} onClick={runSelected}>
                    Run actions on {selectedCount} selected
                  </button>
                  <button type="button" className="asset-btn-muted" disabled={working} onClick={() => setChecked(new Set())}>
                    Clear selection
                  </button>
                </>
              )}
            </div>
          )}

          <div className="contacts-scroll">
            <table className="contacts-table contacts-lookup-table">
              <thead>
                <tr>
                  <th className="contacts-check-col">
                    <input type="checkbox" checked={allChecked} disabled={!actionable.length || working}
                      onChange={(e) => setChecked(e.target.checked ? new Set(actionable.map((r) => r.index)) : new Set())}
                      aria-label="Select every shown row that has an action" />
                  </th>
                  <th>Row</th>
                  <th>Input</th>
                  <th>Outcome</th>
                  <th>ClickUp</th>
                  <th>Google</th>
                  <th>Details</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const res = r.result || {};
                  const canAct = res.action && !r.done;
                  return (
                    <tr key={r.index} className={checked.has(r.index) ? 'contacts-entity-row--checked' : ''}>
                      <td className="contacts-check-col">
                        {canAct && (
                          <input type="checkbox" checked={checked.has(r.index)} disabled={working}
                            onChange={(e) => toggle(r.index, e.target.checked)} aria-label={`Select row ${r.index + 1}`} />
                        )}
                      </td>
                      <td className="email-muted">{r.line ?? r.index + 1}</td>
                      <td className="contacts-cell-wrap">
                        <div>{r.input.name || <span className="email-muted">(no name)</span>}</div>
                        <div className="email-muted">{[...r.input.emails, ...r.input.phones].join(', ')}</div>
                      </td>
                      <td><OutcomePill outcome={res.outcome} /></td>
                      <td className="contacts-cell-wrap"><Match side={res.clickup} /></td>
                      <td className="contacts-cell-wrap"><Match side={res.google} /></td>
                      <td className="contacts-cell-wrap">
                        {(res.conflicts || []).map((c) => <div key={c} className="contacts-lookup-conflict">{c}</div>)}
                        {res.outcome === 'conflict' && (
                          <div className="email-muted">Fix it in ClickUp or Google, then Re-check.</div>
                        )}
                        {(res.notes || []).map((n) => <div key={n} className="email-muted">{n}</div>)}
                        {!r.done && ['clickup', 'google'].map((s) => (
                          <Chooser key={s} row={r} sideKey={s} disabled={working} onChoose={choose} />
                        ))}
                        {(r.done?.warnings || []).map((w) => <div key={w} className="contacts-lookup-conflict">{w}</div>)}
                      </td>
                      <td>
                        {r.done && <span className="email-pill email-pill--success">{DONE[r.done.action]}</span>}
                        {canAct && (
                          <button type="button" className="editorial-button" disabled={working || !!blocked}
                            title={blocked || ''} onClick={() => actOne(r)}>
                            {ACTIONS[res.action]}
                          </button>
                        )}
                        {!r.done && res.outcome === 'review' && res.new_action && (
                          <button type="button" className="asset-btn-muted" disabled={working || !!blocked}
                            title={blocked || 'Ignore the possible matches and create this row as a new contact'}
                            onClick={() => actAsNew(r)}>
                            {AS_NEW[res.new_action]}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {rows.length === 0 && <p className="email-muted">No rows in the categories you’re showing.</p>}
          </div>
        </section>
      )}
    </div>
  );
}
