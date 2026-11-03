import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './contactsApi';

const EMPTY_ROW = {
  first_name: '', last_name: '', email: '', phone: '', labels: '', city: '', state: '', country: '',
};

function formatSummary(out) {
  const parts = [];
  if (out.ok) parts.push(`${out.ok} updated`);
  if (out.skipped) parts.push(`${out.skipped} skipped`);
  if (out.failed) parts.push(`${out.failed} failed`);
  return parts.join(' · ') || 'Nothing changed.';
}

function draftFromContact(c) {
  return {
    first_name: c.given_name || '',
    last_name: c.family_name || '',
    emails: (c.emails || []).join(', '),
    phones: (c.phones || []).join(', '),
    labels: [...(c.labels || [])],
    city: c.city || '',
    state: c.state || '',
    country: c.country || '',
  };
}

export function GoogleTab({ token, googleConnected, googleCanWrite }) {
  const [q, setQ] = useState('');
  const [label, setLabel] = useState('');
  const [labels, setLabels] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [nextToken, setNextToken] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [checked, setChecked] = useState(() => new Set());
  const [bulkLabels, setBulkLabels] = useState([]);
  const [bulkCity, setBulkCity] = useState('');
  const [bulkState, setBulkState] = useState('');
  const [bulkCountry, setBulkCountry] = useState('');
  const [edit, setEdit] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [createRows, setCreateRows] = useState([{ ...EMPTY_ROW }, { ...EMPTY_ROW }, { ...EMPTY_ROW }]);

  const blocked = !googleConnected
    ? 'Connect Google from the Overview tab first.'
    : !googleCanWrite
      ? 'Grant write access to Google Contacts from the Overview tab (needed for updates and creates).'
      : '';

  const load = useCallback(async ({ append = false, pageToken = '', keepChecked = false } = {}) => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.set('q', q.trim());
      if (label) params.set('label', label);
      if (pageToken) params.set('page_token', pageToken);
      const qs = params.toString();
      const out = await api(`google/contacts/${qs ? `?${qs}` : ''}`, { token });
      setContacts((prev) => (append ? [...prev, ...(out.contacts || [])] : (out.contacts || [])));
      setNextToken(out.next_page_token || null);
      if (out.labels) setLabels(out.labels);
      if (!append && !keepChecked) setChecked(new Set());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, q, label]);

  useEffect(() => {
    if (!googleConnected) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const out = await api('google/labels/', { token });
        if (!cancelled) setLabels(out.labels || []);
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    })();
    return () => { cancelled = true; };
  }, [token, googleConnected]);

  useEffect(() => {
    if (!googleConnected) return;
    load();
  }, [googleConnected]); // eslint-disable-line react-hooks/exhaustive-deps -- initial load only

  const selectedList = useMemo(
    () => contacts.filter((c) => checked.has(c.id)),
    [contacts, checked],
  );
  const single = selectedList.length === 1 ? selectedList[0] : null;

  useEffect(() => {
    if (single) setEdit(draftFromContact(single));
    else setEdit(null);
  }, [single?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const allChecked = contacts.length > 0 && contacts.every((c) => checked.has(c.id));
  const someChecked = contacts.some((c) => checked.has(c.id));
  const labelOptions = useMemo(() => labels.map((l) => l.name), [labels]);

  const toggle = (id, on) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const toggleAll = (on) => {
    setChecked(on ? new Set(contacts.map((c) => c.id)) : new Set());
  };

  const runBulkUpdate = async () => {
    if (checked.size < 2 || blocked) return;
    const body = { ids: [...checked] };
    if (bulkLabels.length) body.labels = bulkLabels;
    if (bulkCity.trim()) body.city = bulkCity.trim();
    if (bulkState.trim()) body.state = bulkState.trim();
    if (bulkCountry.trim()) body.country = bulkCountry.trim();
    if (!body.labels && body.city === undefined && body.state === undefined && body.country === undefined) {
      setError('Set at least one of: labels, city, state, country.');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const out = await api('google/contacts/bulk-update/', { token, method: 'POST', body });
      setNotice(formatSummary(out));
      const fails = (out.results || []).filter((r) => !r.ok);
      if (fails.length) {
        setChecked(new Set(fails.map((r) => r.id)));
        setError(fails.map((r) => `${r.id}: ${r.error}`).join('\n'));
      } else {
        setChecked(new Set());
        setBulkLabels([]);
        setBulkCity('');
        setBulkState('');
        setBulkCountry('');
      }
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const runSingleSave = async () => {
    if (!single || !edit || blocked) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const out = await api(`google/contacts/${single.id}/`, {
        token,
        method: 'PUT',
        body: {
          first_name: edit.first_name.trim(),
          last_name: edit.last_name.trim(),
          emails: edit.emails,
          phones: edit.phones,
          labels: edit.labels,
          city: edit.city.trim(),
          state: edit.state.trim(),
          country: edit.country.trim(),
        },
      });
      setNotice(out.changed ? 'Saved.' : 'No changes.');
      await load({ keepChecked: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const setCreateCell = (i, key, value) => {
    setCreateRows((rows) => rows.map((r, idx) => (idx === i ? { ...r, [key]: value } : r)));
  };

  const runBulkCreate = async () => {
    if (blocked) return;
    const contactsPayload = createRows
      .map((r) => ({
        first_name: r.first_name.trim(),
        last_name: r.last_name.trim(),
        email: r.email.trim(),
        phone: r.phone.trim(),
        labels: r.labels.split(',').map((x) => x.trim()).filter(Boolean),
        city: r.city.trim(),
        state: r.state.trim(),
        country: r.country.trim(),
      }))
      .filter((r) => r.first_name || r.last_name || r.email || r.phone);
    if (!contactsPayload.length) {
      setError('Fill at least one row with a name, email or phone.');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const out = await api('google/contacts/bulk-create/', {
        token, method: 'POST', body: { contacts: contactsPayload },
      });
      setNotice(`${out.ok} created` + (out.failed ? ` · ${out.failed} failed` : ''));
      const fails = (out.results || []).filter((r) => !r.ok);
      if (fails.length) {
        setError(fails.map((r) => `Row ${r.index + 1}: ${r.error}`).join('\n'));
      } else {
        setCreateRows([{ ...EMPTY_ROW }, { ...EMPTY_ROW }, { ...EMPTY_ROW }]);
        setShowCreate(false);
      }
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const toggleEditLabel = (name) => {
    setEdit((d) => ({
      ...d,
      labels: d.labels.includes(name) ? d.labels.filter((x) => x !== name) : [...d.labels, name],
    }));
  };

  if (!googleConnected) {
    return <p className="email-muted">Connect Google on the Overview tab to manage contacts here.</p>;
  }

  return (
    <div className="contacts-google">
      <p className="email-muted">
        Edits write to Google Contacts only. Run a Google sync afterward if you want ClickUp updated.
      </p>
      {blocked && <div className="contacts-banner contacts-banner--warn">{blocked}</div>}
      {notice && <div className="asset-status">{notice}</div>}
      {error && <div className="error-message" style={{ whiteSpace: 'pre-wrap' }}>{error}</div>}

      <div className="contacts-toolbar">
        <input type="search" placeholder="Search name or email…" value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') load(); }} />
        <select value={label} onChange={(e) => setLabel(e.target.value)}>
          <option value="">Any label</option>
          {labelOptions.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
        <button type="button" className="editorial-button" disabled={loading} onClick={() => load()}>
          {loading ? 'Loading…' : 'Search'}
        </button>
        <button type="button" className="asset-btn-muted" disabled={!!blocked || busy}
          onClick={() => setShowCreate((v) => !v)}>
          {showCreate ? 'Hide add form' : 'Add contacts'}
        </button>
      </div>

      {showCreate && (
        <div className="contacts-bulk-panel">
          <strong>Bulk add to Google</strong>
          <p className="email-muted">Labels are comma-separated and must already exist in Google.</p>
          <div className="contacts-scroll">
            <table className="contacts-table">
              <thead>
                <tr>
                  <th>First</th><th>Last</th><th>Email</th><th>Phone</th>
                  <th>Labels</th><th>City</th><th>State</th><th>Country</th>
                </tr>
              </thead>
              <tbody>
                {createRows.map((row, i) => (
                  <tr key={i}>
                    {['first_name', 'last_name', 'email', 'phone', 'labels', 'city', 'state', 'country'].map((key) => (
                      <td key={key}>
                        <input type="text" className="contacts-input" value={row[key]} disabled={busy}
                          onChange={(e) => setCreateCell(i, key, e.target.value)} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="contacts-rel-add-actions">
            <button type="button" className="asset-btn-muted" disabled={busy}
              onClick={() => setCreateRows((rows) => [...rows, { ...EMPTY_ROW }, { ...EMPTY_ROW }])}>
              + Rows
            </button>
            <button type="button" className="editorial-button" disabled={busy || !!blocked} onClick={runBulkCreate}>
              {busy ? 'Creating…' : 'Create in Google'}
            </button>
          </div>
        </div>
      )}

      {checked.size > 1 && (
        <div className="contacts-bulk-panel">
          <strong>Bulk edit ({checked.size})</strong>
          <p className="email-muted">Fill any combination — labels are added; city/state/country overwrite when set.</p>
          <div className="contacts-field">
            <span className="contacts-field-name">Add labels</span>
            <div className="contacts-chips">
              {labelOptions.map((name) => (
                <label key={name} className="contacts-check">
                  <input type="checkbox" disabled={busy} checked={bulkLabels.includes(name)}
                    onChange={() => setBulkLabels((xs) => (
                      xs.includes(name) ? xs.filter((x) => x !== name) : [...xs, name]
                    ))} />
                  {name}
                </label>
              ))}
            </div>
          </div>
          <div className="contacts-field-grid" style={{ maxWidth: '36rem' }}>
            <label className="contacts-field">
              <span className="contacts-field-name">City</span>
              <input type="text" className="contacts-input" value={bulkCity} disabled={busy}
                onChange={(e) => setBulkCity(e.target.value)} />
            </label>
            <label className="contacts-field">
              <span className="contacts-field-name">State</span>
              <input type="text" className="contacts-input" value={bulkState} disabled={busy}
                onChange={(e) => setBulkState(e.target.value)} />
            </label>
            <label className="contacts-field">
              <span className="contacts-field-name">Country</span>
              <input type="text" className="contacts-input" value={bulkCountry} disabled={busy}
                onChange={(e) => setBulkCountry(e.target.value)} />
            </label>
          </div>
          <div className="contacts-rel-add-actions">
            <button type="button" className="editorial-button" disabled={busy || !!blocked} onClick={runBulkUpdate}>
              {busy ? 'Applying…' : 'Apply to selected'}
            </button>
            <button type="button" className="asset-btn-muted" disabled={busy} onClick={() => setChecked(new Set())}>
              Clear selection
            </button>
          </div>
        </div>
      )}

      {single && edit && (
        <div className="contacts-bulk-panel">
          <strong>Edit {single.name}</strong>
          <p className="email-muted">Emails and phones are comma-separated (replaces the list). Labels replace membership.</p>
          <div className="contacts-field-grid">
            <label className="contacts-field">
              <span className="contacts-field-name">First name</span>
              <input type="text" className="contacts-input" value={edit.first_name} disabled={busy}
                onChange={(e) => setEdit((d) => ({ ...d, first_name: e.target.value }))} />
            </label>
            <label className="contacts-field">
              <span className="contacts-field-name">Last name</span>
              <input type="text" className="contacts-input" value={edit.last_name} disabled={busy}
                onChange={(e) => setEdit((d) => ({ ...d, last_name: e.target.value }))} />
            </label>
            <label className="contacts-field">
              <span className="contacts-field-name">Email(s)</span>
              <input type="text" className="contacts-input" value={edit.emails} disabled={busy}
                onChange={(e) => setEdit((d) => ({ ...d, emails: e.target.value }))} />
            </label>
            <label className="contacts-field">
              <span className="contacts-field-name">Phone(s)</span>
              <input type="text" className="contacts-input" value={edit.phones} disabled={busy}
                onChange={(e) => setEdit((d) => ({ ...d, phones: e.target.value }))} />
            </label>
            <label className="contacts-field">
              <span className="contacts-field-name">City</span>
              <input type="text" className="contacts-input" value={edit.city} disabled={busy}
                onChange={(e) => setEdit((d) => ({ ...d, city: e.target.value }))} />
            </label>
            <label className="contacts-field">
              <span className="contacts-field-name">State</span>
              <input type="text" className="contacts-input" value={edit.state} disabled={busy}
                onChange={(e) => setEdit((d) => ({ ...d, state: e.target.value }))} />
            </label>
            <label className="contacts-field">
              <span className="contacts-field-name">Country</span>
              <input type="text" className="contacts-input" value={edit.country} disabled={busy}
                onChange={(e) => setEdit((d) => ({ ...d, country: e.target.value }))} />
            </label>
          </div>
          <div className="contacts-field">
            <span className="contacts-field-name">Labels</span>
            <div className="contacts-chips">
              {labelOptions.map((name) => (
                <label key={name} className="contacts-check">
                  <input type="checkbox" disabled={busy} checked={edit.labels.includes(name)}
                    onChange={() => toggleEditLabel(name)} />
                  {name}
                </label>
              ))}
            </div>
          </div>
          <div className="contacts-rel-add-actions">
            <button type="button" className="editorial-button" disabled={busy || !!blocked} onClick={runSingleSave}>
              {busy ? 'Saving…' : 'Save'}
            </button>
            <button type="button" className="asset-btn-muted" disabled={busy} onClick={() => setChecked(new Set())}>
              Clear selection
            </button>
          </div>
        </div>
      )}

      <div className="contacts-scroll">
        <table className="contacts-table">
          <thead>
            <tr>
              <th className="contacts-check-col">
                <input type="checkbox" checked={allChecked}
                  ref={(el) => { if (el) el.indeterminate = !allChecked && someChecked; }}
                  onChange={(e) => toggleAll(e.target.checked)}
                  aria-label="Select all visible" />
              </th>
              <th>Name</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Labels</th>
              <th>City</th>
              <th>State</th>
              <th>Country</th>
            </tr>
          </thead>
          <tbody>
            {contacts.map((c) => (
              <tr key={c.id} className={checked.has(c.id) ? 'contacts-entity-row--checked' : ''}>
                <td className="contacts-check-col">
                  <input type="checkbox" checked={checked.has(c.id)}
                    onChange={(e) => toggle(c.id, e.target.checked)} aria-label={`Select ${c.name}`} />
                </td>
                <td>
                  {c.link ? <a href={c.link} target="_blank" rel="noreferrer">{c.name}</a> : c.name}
                </td>
                <td className="contacts-cell-wrap">{(c.emails || []).join(', ')}</td>
                <td className="contacts-cell-wrap">{(c.phones || []).join(', ')}</td>
                <td className="contacts-cell-wrap">{(c.labels || []).join(', ')}</td>
                <td>{c.city}</td>
                <td>{c.state}</td>
                <td>{c.country}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && contacts.length === 0 && <p className="email-muted">Loading…</p>}
        {!loading && contacts.length === 0 && <p className="email-muted">No contacts match.</p>}
        {nextToken && (
          <button type="button" className="asset-btn-muted contacts-more" disabled={loading}
            onClick={() => load({ append: true, pageToken: nextToken })}>
            {loading ? 'Loading…' : 'Show more'}
          </button>
        )}
      </div>
    </div>
  );
}
