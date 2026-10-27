import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { MarkdownBody } from './MarkdownBody';
import helpText from './contactSyncHelp.md?raw';
import { EntitiesTab } from './ContactEntities';
import { api, formatWhen, taskUrl } from './contactsApi';

const SOURCES = { google: 'Google', linkedin: 'LinkedIn', whatsapp: 'WhatsApp' };
const RUN_KINDS = { ...SOURCES, merge: 'Merge', export: 'Export', import: 'Import' };
const ACTION_ORDER = [
  'EXPORT', 'RELATION', 'CREATE', 'UPDATE', 'LINK', 'LINK(email)', 'LINK(phone)', 'LINK(name)', 'LINK(review)',
  'REVIEW', 'PENDING', 'DELETED', 'ARCHIVE', 'MESSAGE', 'PHOTO', 'MERGE', 'ERROR', 'WARN', 'SKIP', 'INFO',
  'UNCHANGED',
];
const ACTION_HELP = {
  CREATE: 'new ClickUp task',
  UPDATE: 'existing linked contact changed',
  REVIEW: 'new contact flagged as a possible duplicate',
  PENDING: 'waiting for a decision in Review',
  DELETED: 'marked "deleted in google"',
  EXPORT: 'list read into the export file',
  RELATION: 'link between two tasks found in the export',
  LINK: 'links pointed at the imported copies',
  ARCHIVE: 'archived, as it was in the export',
};
const ACTIVE_STATUSES = ['queued', 'running'];
const MAX_ROWS = 400;

function keyUrl(source, key) {
  if (source === 'linkedin') return key;
  if (source === 'google' && key?.startsWith('people/')) {
    return `https://contacts.google.com/person/${key.split('/').pop()}`;
  }
  return null;
}

function actionRank(action) {
  const i = ACTION_ORDER.indexOf(action);
  return i === -1 ? ACTION_ORDER.length : i;
}

function sortedStats(stats) {
  return Object.entries(stats || {}).sort(([a], [b]) => actionRank(a) - actionRank(b));
}

function StatusPill({ status }) {
  const tone = { done: 'success', failed: 'failed', stopped: 'failed', interrupted: 'failed' }[status] || '';
  return <span className={`email-pill ${tone ? `email-pill--${tone}` : ''}`}>{status}</span>;
}

function runLabel(run) {
  if (run.source === 'export') return `Export #${run.id}`;
  return `${run.mode === 'live' ? 'Live run' : 'Preview'} #${run.id} · ${RUN_KINDS[run.source] || run.source}`;
}

function runSummary(run) {
  if (run.source === 'export') return run.output ? `${run.output.rows} tasks` : 'reading…';
  return run.mode === 'live' ? `${run.ops} writes` : `${run.ops} planned`;
}

function TaskLink({ id, children }) {
  if (!id) return <span>{children}</span>;
  return (
    <a href={taskUrl(id)} target="_blank" rel="noopener noreferrer" title="Open in ClickUp">
      {children}
    </a>
  );
}

function Checkbox({ label, hint, checked, onChange, disabled }) {
  return (
    <label className={`contacts-check ${disabled ? 'contacts-check--disabled' : ''}`}>
      <input type="checkbox" checked={!!checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span>
        {label}
        {hint ? <span className="email-muted"> — {hint}</span> : null}
      </span>
    </label>
  );
}

function FilePicker({ label, kind, file, onUploaded, token, required, setError }) {
  const [busy, setBusy] = useState(false);
  const onPick = async (e) => {
    const picked = e.target.files?.[0];
    e.target.value = '';
    if (!picked) return;
    setBusy(true);
    setError('');
    try {
      const form = new FormData();
      form.append('kind', kind);
      form.append('file', picked);
      onUploaded(await api('uploads/', { token, method: 'POST', form }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="contacts-file">
      <div>
        <strong>{label}</strong>
        {required ? '' : <span className="email-muted"> (optional)</span>}
      </div>
      {file ? (
        <div className="email-muted">
          {file.original_name} · {file.rows} rows · uploaded {formatWhen(file.uploaded_at)}
        </div>
      ) : (
        <div className="email-muted">No file yet.</div>
      )}
      <label className="asset-btn-muted contacts-file-btn">
        {busy ? 'Uploading…' : file ? 'Replace file' : 'Choose file'}
        <input type="file" hidden onChange={onPick} disabled={busy} />
      </label>
    </div>
  );
}

const HELP_SECTIONS = {
  overview: 'tab-overview', sync: 'tab-sync', runs: 'tab-runs', review: 'tab-review', transfer: 'tab-transfer',
  entities: 'tab-people-orgs',
};

function scrollToAnchor(root, id) {
  root?.querySelector(`[id="${id}"]`)?.scrollIntoView({ block: 'start' });
}

function HelpPanel({ section, onClose }) {
  const body = useRef(null);

  useEffect(() => {
    if (section) scrollToAnchor(body.current, section);
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [section, onClose]);

  const onClick = (e) => {
    const link = e.target.closest('a[href^="#"]');
    if (!link) return;
    e.preventDefault();
    scrollToAnchor(body.current, link.getAttribute('href').slice(1));
  };

  return (
    <div className="contacts-help-backdrop" onClick={onClose}>
      <aside className="contacts-help" role="dialog" aria-label="Contact Sync guide" onClick={(e) => e.stopPropagation()}>
        <div className="contacts-help-top">
          <strong>Help</strong>
          <button type="button" className="asset-btn-muted" onClick={onClose}>Close</button>
        </div>
        <div className="contacts-help-body" ref={body} onClick={onClick}>
          <MarkdownBody>{helpText}</MarkdownBody>
        </div>
      </aside>
    </div>
  );
}

function OverviewTab({ status, token, busy, run, onRefresh }) {
  const [check, setCheck] = useState(status?.last_check || null);
  const google = status?.google || {};
  const clickup = status?.clickup || {};

  const doCheck = () => run('check', async () => {
    setCheck(await api('check/', { token, method: 'POST' }));
  });
  const connect = (write) => run('connect', async () => {
    const data = await api(`oauth/start/${write ? '?write=1' : ''}`, { token });
    window.location.href = data.authorize_url;
  });
  const disconnect = () => {
    if (!window.confirm('Disconnect Google? Syncing Google contacts will stop until you connect again.')) return;
    run('disconnect', async () => {
      await api('google/disconnect/', { token, method: 'POST' });
      await onRefresh();
    });
  };
  const missingOptional = (check?.expected || []).filter((f) => !f.present && !f.required);

  return (
    <>
      <div className="contacts-grid">
        <section className="contacts-card">
          <h3>ClickUp Contacts list</h3>
          <dl className="email-meta">
            <div><dt>List</dt><dd>{clickup.list_id || <span className="error-message">not configured</span>}</dd></div>
            <div><dt>Live writes</dt><dd>{clickup.writes_enabled ? 'enabled' : 'disabled (previews only)'}</dd></div>
            <div><dt>Last check</dt><dd>{check?.checked_at ? formatWhen(check.checked_at) : 'never'}</dd></div>
          </dl>
          <div className="email-review-actions">
            <button type="button" className="asset-btn-muted" onClick={doCheck} disabled={!!busy || !clickup.configured}>
              {busy === 'check' ? 'Checking…' : 'Check list fields'}
            </button>
          </div>
          {check && (
            <div className="contacts-check-result">
              <p>
                {check.ready ? (
                  <span className="email-pill email-pill--success">ready</span>
                ) : (
                  <span className="email-pill email-pill--failed">needs setup</span>
                )}
              </p>
              {check.missing_required?.length > 0 && (
                <p className="error-message">Missing required fields: {check.missing_required.join(', ')}</p>
              )}
              {check.status_missing_options?.length > 0 && (
                <p className="error-message">
                  “Match status” needs options: {check.status_missing_options.join(', ')}
                </p>
              )}
              {check.sources_missing_options?.length > 0 && (
                <p className="email-muted">“Sources” has no option for: {check.sources_missing_options.join(', ')}</p>
              )}
              {missingOptional.length > 0 && (
                <p className="email-muted">
                  Optional fields not on the list (skipped): {missingOptional.map((f) => f.name).join(', ')}
                </p>
              )}
            </div>
          )}
        </section>

        <section className="contacts-card">
          <h3>Google account</h3>
          {google.connected ? (
            <dl className="email-meta">
              <div><dt>Account</dt><dd>{google.email || 'connected'}</dd></div>
              <div><dt>Access</dt><dd>{google.can_write ? 'read + write (writeback)' : 'read-only'}</dd></div>
              <div><dt>Next sync</dt><dd>{google.has_sync_token ? 'incremental' : 'full (no sync token yet)'}</dd></div>
              {google.last_error ? <div><dt>Last error</dt><dd className="error-message">{google.last_error}</dd></div> : null}
            </dl>
          ) : (
            <p className="email-muted">Not connected. Contacts are read with read-only access unless you grant more.</p>
          )}
          <div className="email-review-actions">
            {!google.connected && (
              <button type="button" className="editorial-button asset-btn" onClick={() => connect(false)} disabled={!!busy}>
                Connect Google (read-only)
              </button>
            )}
            {google.connected && !google.can_write && (
              <button type="button" className="asset-btn-muted" onClick={() => connect(true)} disabled={!!busy}>
                Grant write access
              </button>
            )}
            {google.connected && (
              <button type="button" className="asset-btn-muted" onClick={disconnect} disabled={!!busy}>
                Disconnect
              </button>
            )}
          </div>
        </section>
      </div>

      <section className="email-panel">
        <h3>Latest runs</h3>
        <table className="contacts-table">
          <thead>
            <tr><th>Source</th><th>Last preview</th><th>Last live run</th><th>Pending review</th></tr>
          </thead>
          <tbody>
            {Object.entries(SOURCES).map(([key, label]) => {
              const latest = status?.latest?.[key] || {};
              const cell = (r) => (r ? (
                <span><StatusPill status={r.status} /> #{r.id} · {formatWhen(r.finished_at || r.created_at)}</span>
              ) : <span className="email-muted">—</span>);
              return (
                <tr key={key}>
                  <td>{label}</td>
                  <td>{cell(latest.dry)}</td>
                  <td>{cell(latest.live)}</td>
                  <td>{status?.pending_reviews?.[key] || 0}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </>
  );
}

function SyncTab({ status, token, busy, run, startPreview, setError }) {
  const google = status?.google || {};
  const [g, setG] = useState({ full: false, photos: false, rename_tasks: false, overwrite_values: true, writeback: false });
  const [ignoreText, setIgnoreText] = useState((status?.ignore_labels || []).join('\n'));
  const [li, setLi] = useState({ overwrite_values: true });
  const [liFiles, setLiFiles] = useState({});
  const [wa, setWa] = useState({ no_create: false, only_saved: false, trust_exact_names: false, overwrite_values: true });
  const [waFiles, setWaFiles] = useState({});
  const blocked = !!busy || !!status?.active_run;

  useEffect(() => {
    api('uploads/', { token }).then((uploads) => {
      const latest = (kind) => uploads.find((u) => u.kind === kind);
      setLiFiles((cur) => ({
        connections: cur.connections || latest('linkedin_connections'),
        messages: cur.messages || latest('linkedin_messages'),
      }));
      setWaFiles((cur) => ({ export: cur.export || latest('whatsapp') }));
    }).catch(() => {});
  }, [token]);

  const previewGoogle = () => run('preview-google', async () => {
    const ignore = ignoreText.split('\n').map((s) => s.trim()).filter(Boolean);
    await api('settings/', { token, method: 'PUT', body: { ignore_labels: ignore } });
    await startPreview('google', { ...g, ignore_labels: ignore }, {});
  });
  const fileIds = (files) => Object.fromEntries(Object.entries(files).map(([k, f]) => [k, f.id]));

  return (
    <>
      {status?.active_run && (
        <div className="contacts-banner">Run #{status.active_run.id} is {status.active_run.status}; start another when it finishes.</div>
      )}
      <p className="email-muted">
        Every sync starts as a <strong>preview</strong>: it reads Google/LinkedIn/WhatsApp and ClickUp and lists what
        would change, without writing anything. You can apply a finished preview from the Runs tab.
      </p>
      <div className="contacts-grid">
        <section className="contacts-card">
          <h3>Google Contacts</h3>
          {!google.connected && <p className="error-message">Connect Google on the Overview tab first.</p>}
          <Checkbox label="Full sync" hint="re-read every contact and mark ones removed from Google as deleted"
            checked={g.full} onChange={(v) => setG({ ...g, full: v })} />
          <Checkbox label="Check photos on every contact" hint="not just changed ones"
            checked={g.photos} onChange={(v) => setG({ ...g, photos: v })} />
          <Checkbox label="Update values already set in ClickUp" hint="company, title, birthday, address…; off = only fill blanks"
            checked={g.overwrite_values} onChange={(v) => setG({ ...g, overwrite_values: v })} />
          <Checkbox label="Rename ClickUp tasks when the Google name changes"
            checked={g.rename_tasks} onChange={(v) => setG({ ...g, rename_tasks: v })} />
          <Checkbox label="Write the ClickUp task id back to Google" hint={google.can_write ? '' : 'needs write access'}
            disabled={!google.can_write} checked={g.writeback} onChange={(v) => setG({ ...g, writeback: v })} />
          <label className="contacts-label">
            Ignore Google labels (one per line, * wildcards)
            <textarea rows={3} value={ignoreText} onChange={(e) => setIgnoreText(e.target.value)} />
          </label>
          <button type="button" className="editorial-button asset-btn" onClick={previewGoogle}
            disabled={blocked || !google.connected}>
            Preview Google sync
          </button>
        </section>

        <section className="contacts-card">
          <h3>LinkedIn</h3>
          <p className="email-muted">From LinkedIn’s “Get a copy of your data” export.</p>
          <FilePicker label="Connections.csv" kind="linkedin_connections" required token={token} setError={setError}
            file={liFiles.connections} onUploaded={(f) => setLiFiles({ ...liFiles, connections: f })} />
          <FilePicker label="messages.csv" kind="linkedin_messages" token={token} setError={setError}
            file={liFiles.messages} onUploaded={(f) => setLiFiles({ ...liFiles, messages: f })} />
          <Checkbox label="Update company/title already set in ClickUp" hint="off = only fill blanks"
            checked={li.overwrite_values} onChange={(v) => setLi({ ...li, overwrite_values: v })} />
          <button type="button" className="editorial-button asset-btn" disabled={blocked || !liFiles.connections}
            onClick={() => run('preview-linkedin', () => startPreview('linkedin', li, fileIds(liFiles)))}>
            Preview LinkedIn sync
          </button>
        </section>

        <section className="contacts-card">
          <h3>WhatsApp</h3>
          <p className="email-muted">Contacts JSON from a WhatsApp contact-export tool.</p>
          <FilePicker label="Contacts export (.json)" kind="whatsapp" required token={token} setError={setError}
            file={waFiles.export} onUploaded={(f) => setWaFiles({ export: f })} />
          <Checkbox label="Don’t create new contacts" hint="only link/update existing ones"
            checked={wa.no_create} onChange={(v) => setWa({ ...wa, no_create: v })} />
          <Checkbox label="Only numbers saved in my address book"
            checked={wa.only_saved} onChange={(v) => setWa({ ...wa, only_saved: v })} />
          <Checkbox label="Link exact, unique name matches without review"
            checked={wa.trust_exact_names} onChange={(v) => setWa({ ...wa, trust_exact_names: v })} />
          <button type="button" className="editorial-button asset-btn" disabled={blocked || !waFiles.export}
            onClick={() => run('preview-whatsapp', () => startPreview('whatsapp', wa, fileIds(waFiles)))}>
            Preview WhatsApp sync
          </button>
        </section>
      </div>
    </>
  );
}

function TransferTab({ status, token, busy, run, startPreview, setError }) {
  const [file, setFile] = useState(null);
  const [peopleList, setPeopleList] = useState('');
  const [orgsList, setOrgsList] = useState('');
  const clickup = status?.clickup || {};
  const blocked = !!busy || !!status?.active_run;

  useEffect(() => {
    api('uploads/', { token }).then((uploads) => {
      setFile((cur) => cur || uploads.find((u) => u.kind === 'contacts_export') || null);
    }).catch(() => {});
  }, [token]);

  const previewImport = () => run('preview-import', () => startPreview(
    'import', { people_list_id: peopleList.trim(), orgs_list_id: orgsList.trim() }, { export: file.id },
  ));

  return (
    <>
      {status?.active_run && (
        <div className="contacts-banner">Run #{status.active_run.id} is {status.active_run.status}; start another when it finishes.</div>
      )}
      <div className="contacts-grid">
        <section className="contacts-card">
          <h3>Export</h3>
          <p className="email-muted">
            Saves the People list ({clickup.list_id || 'not set'}) and the Orgs list ({clickup.orgs_list_id || 'not set'})
            to one JSON file: every task’s name, status, tags, description and custom fields, archived tasks included,
            plus the relationships between them. It only reads ClickUp.
          </p>
          {!clickup.orgs_list_id && (
            <p className="error-message">Set CONTACTS_CLICKUP_ORGS_LIST_ID on the server to include Orgs.</p>
          )}
          <button type="button" className="editorial-button asset-btn" disabled={blocked || !clickup.configured}
            onClick={() => run('export', () => startPreview('export', {}, {}))}>
            Export People and Orgs
          </button>
        </section>

        <section className="contacts-card">
          <h3>Import</h3>
          <p className="email-muted">
            Creates the tasks from an export in new, empty lists, then points every relationship at the new copies.
            Lists that already have tasks are refused, so this can’t change your People or Orgs lists. Create the
            target lists in ClickUp first with the same custom fields (duplicating a list without its tasks works).
          </p>
          <FilePicker label="Export file (.json)" kind="contacts_export" required token={token} setError={setError}
            file={file} onUploaded={setFile} />
          <label className="contacts-label">
            Import People into list ID
            <input type="text" inputMode="numeric" value={peopleList} onChange={(e) => setPeopleList(e.target.value)} />
          </label>
          <label className="contacts-label">
            Import Orgs into list ID
            <input type="text" inputMode="numeric" value={orgsList} onChange={(e) => setOrgsList(e.target.value)} />
          </label>
          <button type="button" className="editorial-button asset-btn" onClick={previewImport}
            disabled={blocked || !file || !peopleList.trim()}>
            Preview import
          </button>
        </section>
      </div>
    </>
  );
}

function ChangeLogTable({ token, runId }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    api(`runs/${runId}/changes/`, { token }).then(setRows).catch((e) => setError(e.message));
  }, [token, runId]);
  if (error) return <p className="error-message">{error}</p>;
  if (!rows) return <p className="email-muted">Loading change log…</p>;
  if (rows.length === 0) return <p className="email-muted">No writes were made.</p>;
  const show = (v) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));
  return (
    <div className="contacts-scroll">
      <table className="contacts-table">
        <thead><tr><th>Op</th><th>Contact</th><th>Field</th><th>Before</th><th>After</th><th>Result</th></tr></thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id}>
              <td>{c.op}</td>
              <td><TaskLink id={c.task_id !== '(new)' ? c.task_id : null}>{c.task_name || c.task_id}</TaskLink></td>
              <td>{c.field || '—'}</td>
              <td className="contacts-cell-wrap">{show(c.before)}</td>
              <td className="contacts-cell-wrap">{show(c.after)}</td>
              <td>{c.ok ? 'ok' : <span className="error-message">{c.error || 'not confirmed'}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunDetail({ detail, token, busy, run, onApplied, onChanged }) {
  const [filter, setFilter] = useState('');
  const [search, setSearch] = useState('');
  const [showUnchanged, setShowUnchanged] = useState(false);
  const [showChanges, setShowChanges] = useState(false);
  const [limit, setLimit] = useState(MAX_ROWS);

  const actions = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (detail.actions || []).filter((a) => (
      (filter ? a.action === filter : (showUnchanged || a.action !== 'UNCHANGED'))
      && (!q || `${a.name} ${a.detail}`.toLowerCase().includes(q))
    ));
  }, [detail.actions, filter, search, showUnchanged]);

  const isActive = ACTIVE_STATUSES.includes(detail.status);
  const pct = detail.progress_total ? Math.round((100 * detail.progress_done) / detail.progress_total) : null;

  const apply = () => {
    const lines = sortedStats(detail.stats)
      .filter(([k]) => !['UNCHANGED', 'INFO', 'SKIP', 'PENDING'].includes(k))
      .map(([k, n]) => `  ${k}: ${n}`).join('\n');
    const budget = Math.ceil(detail.ops * 1.2) + 10;
    const ok = window.confirm(
      `Apply preview #${detail.id} to ClickUp?\n\n${lines}\n\nPlanned writes: ${detail.ops}. `
      + `The live run stops automatically if it needs more than ${budget}.\n`
      + (detail.source === 'import'
        ? 'It only writes into the empty target lists, and every write is logged.'
        : 'A snapshot of the list is saved first, and every write is logged.'),
    );
    if (!ok) return;
    run('apply', async () => {
      const live = await api(`runs/${detail.id}/apply/`, { token, method: 'POST' });
      onApplied(live.id);
    });
  };
  const cancel = () => run('cancel', async () => {
    await api(`runs/${detail.id}/cancel/`, { token, method: 'POST' });
    onChanged();
  });
  const download = () => run('download', async () => {
    const res = await fetch(`/api/contacts/runs/${detail.id}/download/`, {
      headers: { Authorization: `Token ${token}` }, credentials: 'omit',
    });
    if (!res.ok) throw new Error(`Download failed (${res.status})`);
    const url = URL.createObjectURL(await res.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = detail.output.original_name;
    link.click();
    URL.revokeObjectURL(url);
  });
  const isExport = detail.source === 'export';

  return (
    <div className="contacts-run-detail">
      <div className="email-review-top">
        <h3 style={{ margin: 0 }}>{runLabel(detail)}</h3>
        <StatusPill status={detail.status} />
      </div>
      <p className="email-muted">
        Started {formatWhen(detail.started_at || detail.created_at)}
        {detail.finished_at ? ` · finished ${formatWhen(detail.finished_at)}` : ''}
        {detail.created_by ? ` · by ${detail.created_by}` : ''}
        {detail.plan ? ` · applies preview #${detail.plan}` : ''}
      </p>

      {isActive && (
        <div className="contacts-progress-wrap">
          <div className="email-muted">{detail.phase || 'Waiting to start…'}{pct !== null ? ` · ${detail.progress_done}/${detail.progress_total}` : ''}</div>
          <div className="contacts-progress"><div style={{ width: `${pct ?? 5}%` }} /></div>
          <button type="button" className="asset-btn-muted" onClick={cancel} disabled={!!busy || detail.cancel_requested}>
            {detail.cancel_requested ? 'Cancelling…' : 'Cancel'}
          </button>
        </div>
      )}

      {detail.error && <pre className="contacts-error">{detail.error}</pre>}

      <div className="contacts-chips">
        {sortedStats(detail.stats).map(([k, n]) => (
          <button key={k} type="button" title={ACTION_HELP[k] || ''}
            className={`contacts-chip ${filter === k ? 'contacts-chip--active' : ''}`}
            onClick={() => setFilter(filter === k ? '' : k)}>
            {k} <strong>{n}</strong>
          </button>
        ))}
      </div>
      {isExport ? (
        detail.output && (
          <div className="contacts-apply">
            <button type="button" className="editorial-button asset-btn" onClick={download} disabled={!!busy}>
              Download export
            </button>
            <span className="email-muted">
              {detail.output.original_name} · {detail.output.rows} tasks · {Math.ceil(detail.output.size / 1024)} KB
            </span>
          </div>
        )
      ) : (
        <p className="email-muted">
          {detail.mode === 'live'
            ? `Writes made: ${detail.ops} of a budget of ${detail.max_ops}.`
            : `Writes this preview would make: ${detail.ops}.`}
          {detail.has_snapshot ? ' A snapshot of the list was saved before writing.' : ''}
        </p>
      )}

      {!isExport && detail.mode === 'dry' && detail.status === 'done' && (
        <div className="contacts-apply">
          {detail.applied_by?.length ? (
            <span className="email-muted">Applied by live run #{detail.applied_by.join(', #')}.</span>
          ) : detail.apply_blocker ? (
            <span className="email-muted">Can’t apply: {detail.apply_blocker}</span>
          ) : (
            <button type="button" className="editorial-button asset-btn" onClick={apply} disabled={!!busy}>
              Apply to ClickUp…
            </button>
          )}
        </div>
      )}

      {detail.warnings?.length > 0 && (
        <div className="contacts-banner contacts-banner--warn">
          {detail.warnings.map((w, i) => <div key={i}>{w}</div>)}
        </div>
      )}
      {detail.unknown_sources?.length > 0 && (
        <p className="email-muted">Add these options to the ClickUp “Sources” field: {detail.unknown_sources.join(', ')}</p>
      )}
      {Object.keys(detail.unknown_groups || {}).length > 0 && (
        <details className="contacts-details">
          <summary>{Object.keys(detail.unknown_groups).length} Google labels have no matching “Groups” option</summary>
          <ul>
            {Object.entries(detail.unknown_groups).sort((a, b) => b[1] - a[1]).map(([g, n]) => (
              <li key={g}>{g} <span className="email-muted">({n})</span></li>
            ))}
          </ul>
        </details>
      )}

      {detail.mode === 'live' && (
        <div className="contacts-subsection">
          <button type="button" className="asset-btn-muted" onClick={() => setShowChanges(!showChanges)}>
            {showChanges ? 'Hide' : 'Show'} change log ({detail.change_counts?.total || 0}
            {detail.change_counts?.failed ? `, ${detail.change_counts.failed} not confirmed` : ''})
          </button>
          {showChanges && <ChangeLogTable token={token} runId={detail.id} />}
        </div>
      )}

      <div className="contacts-subsection">
        <div className="contacts-toolbar">
          <input type="search" placeholder="Search names or details" value={search}
            onChange={(e) => setSearch(e.target.value)} />
          {!filter && (
            <Checkbox label="Show unchanged" checked={showUnchanged} onChange={setShowUnchanged} />
          )}
          {filter && (
            <button type="button" className="asset-btn-muted" onClick={() => setFilter('')}>Clear filter: {filter}</button>
          )}
        </div>
        {actions.length === 0 ? (
          <p className="email-muted">{isActive ? 'Nothing yet…' : 'No matching actions.'}</p>
        ) : (
          <div className="contacts-scroll">
            <table className="contacts-table">
              <thead><tr><th>Action</th><th>Contact</th><th>Detail</th></tr></thead>
              <tbody>
                {actions.slice(0, limit).map((a, i) => (
                  <tr key={i}>
                    <td><span className="email-pill">{a.action}</span></td>
                    <td><TaskLink id={a.task_id}>{a.name || '—'}</TaskLink></td>
                    <td className="contacts-cell-wrap">{a.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {actions.length > limit && (
              <button type="button" className="asset-btn-muted" onClick={() => setLimit(limit + MAX_ROWS)}>
                Show more ({actions.length - limit} hidden)
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function RunsTab({ runs, selectedId, setSelectedId, detail, token, busy, run, onChanged }) {
  return (
    <div className="contacts-runs-layout">
      <div className="contacts-run-list">
        {runs.length === 0 && <p className="email-muted">No runs yet. Start a preview on the Sync tab.</p>}
        {runs.map((r) => (
          <button key={r.id} type="button"
            className={`contacts-run-row ${r.id === selectedId ? 'contacts-run-row--active' : ''}`}
            onClick={() => setSelectedId(r.id)}>
            <span className="contacts-run-row-top">
              <span>{runLabel(r)}</span>
              <StatusPill status={r.status} />
            </span>
            <span className="email-muted">
              {formatWhen(r.created_at)} · {runSummary(r)}
            </span>
          </button>
        ))}
      </div>
      <div>
        {detail ? (
          <RunDetail key={detail.id} detail={detail} token={token} busy={busy} run={run}
            onApplied={(id) => { setSelectedId(id); onChanged(); }} onChanged={onChanged} />
        ) : (
          <p className="email-muted">Select a run.</p>
        )}
      </div>
    </div>
  );
}

function ReviewTab({ token, busy, run, reviews, onChanged }) {
  const [source, setSource] = useState('');
  const [decided, setDecided] = useState(null);
  const pending = reviews.filter((r) => !source || r.source === source);

  const loadDecided = useCallback(async () => {
    const list = await api('reviews/?decision=same', { token });
    const list2 = await api('reviews/?decision=new', { token });
    setDecided([...list, ...list2].sort((a, b) => (b.decided_at || '').localeCompare(a.decided_at || '')));
  }, [token]);

  const decide = (item, decision) => run(`decide-${item.id}`, async () => {
    await api(`reviews/${item.id}/decide/`, { token, method: 'POST', body: { decision } });
    await onChanged();
    if (decided) await loadDecided();
  });

  return (
    <>
      <p className="email-muted">
        These Google/LinkedIn/WhatsApp contacts look like someone already in ClickUp, but not certainly. Decisions are
        used by the next preview, so run a new preview after deciding.
      </p>
      <div className="contacts-toolbar">
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">All sources ({reviews.length})</option>
          {Object.entries(SOURCES).map(([k, label]) => (
            <option key={k} value={k}>{label} ({reviews.filter((r) => r.source === k).length})</option>
          ))}
        </select>
      </div>
      {pending.length === 0 ? (
        <p className="email-muted">Nothing to review.</p>
      ) : (
        <ul className="email-review-list">
          {pending.map((item) => {
            const href = keyUrl(item.source, item.key);
            return (
              <li key={item.id} className="email-review-card">
                <div className="contacts-review-pair">
                  <div>
                    <div className="email-muted">{SOURCES[item.source]} contact</div>
                    <strong>{href ? <a href={href} target="_blank" rel="noopener noreferrer">{item.name}</a> : item.name}</strong>
                    <div className="email-muted">{[item.title, item.company].filter(Boolean).join(' · ') || '—'}</div>
                  </div>
                  <div>
                    <div className="email-muted">Possibly the same as</div>
                    <strong><TaskLink id={item.suggested_task_id}>{item.suggested_task_name || item.suggested_task_id}</TaskLink></strong>
                  </div>
                </div>
                {item.note && <div className="contacts-banner contacts-banner--warn">{item.note}</div>}
                <div className="email-review-actions">
                  <button type="button" className="asset-btn-muted" disabled={!!busy} onClick={() => decide(item, 'same')}>
                    Same person
                  </button>
                  <button type="button" className="asset-btn-muted" disabled={!!busy} onClick={() => decide(item, 'new')}>
                    Different person
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <details className="contacts-details" onToggle={(e) => { if (e.target.open && !decided) loadDecided(); }}>
        <summary>Decided</summary>
        {!decided ? <p className="email-muted">Loading…</p> : decided.length === 0 ? (
          <p className="email-muted">No decisions yet.</p>
        ) : (
          <table className="contacts-table">
            <thead><tr><th>Contact</th><th>Decision</th><th>ClickUp task</th><th>When</th><th /></tr></thead>
            <tbody>
              {decided.map((item) => (
                <tr key={item.id}>
                  <td>{item.name} <span className="email-muted">({SOURCES[item.source]})</span></td>
                  <td>{item.decision === 'same' ? 'same person' : 'different person'}</td>
                  <td><TaskLink id={item.chosen_task_id || item.suggested_task_id}>{item.suggested_task_name}</TaskLink></td>
                  <td>{formatWhen(item.decided_at)}</td>
                  <td>
                    <button type="button" className="asset-btn-muted" disabled={!!busy} onClick={() => decide(item, 'pending')}>
                      Undo
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </details>
    </>
  );
}

function fetchOverview(token) {
  return Promise.all([
    api('status/', { token }),
    api('runs/', { token }),
    api('reviews/?decision=pending', { token }),
  ]);
}

function initialNotice() {
  const google = new URLSearchParams(window.location.search).get('google');
  return {
    msg: google === 'connected' ? 'Google connected.' : '',
    error: google === 'denied' ? 'Google access was not granted.' : '',
  };
}

export function ContactSyncApp() {
  const { token, isAuthenticated, user, openSocialLoginModal } = useAuth();
  const [tab, setTab] = useState('overview');
  const [status, setStatus] = useState(null);
  const [runs, setRuns] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [pickedId, setSelectedId] = useState(null);
  const [loadedDetail, setDetail] = useState(null);
  const [error, setError] = useState(() => initialNotice().error);
  const [msg, setMsg] = useState(() => initialNotice().msg);
  const [busy, setBusy] = useState('');
  const [helpOpen, setHelpOpen] = useState(false);
  const closeHelp = useCallback(() => setHelpOpen(false), []);
  const editorDirty = useRef(false);
  const setEditorDirty = useCallback((d) => { editorDirty.current = d; }, []);
  const selectedId = pickedId ?? runs[0]?.id ?? null;
  const detail = loadedDetail && loadedDetail.id === selectedId ? loadedDetail : null;

  const isSuperuser = user?.role === 'superuser' || Boolean(user?.isStaff);

  const applyOverview = useCallback(([st, runList, pending]) => {
    setStatus(st);
    setRuns(runList);
    setReviews(pending);
  }, []);

  const refresh = useCallback(async () => {
    if (!token) return;
    applyOverview(await fetchOverview(token));
  }, [token, applyOverview]);

  const loadDetail = useCallback(async (id) => {
    if (!token || !id) return;
    setDetail(await api(`runs/${id}/`, { token }));
  }, [token]);

  const run = useCallback(async (label, fn) => {
    setBusy(label);
    setError('');
    setMsg('');
    try {
      await fn();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated || !token || !isSuperuser) return;
    fetchOverview(token).then(applyOverview).catch((err) => setError(err.message));
  }, [isAuthenticated, token, isSuperuser, applyOverview]);

  useEffect(() => {
    if (!token || !selectedId) return;
    api(`runs/${selectedId}/`, { token }).then(setDetail).catch((err) => setError(err.message));
  }, [token, selectedId]);

  const polling = Boolean(status?.active_run) || ACTIVE_STATUSES.includes(detail?.status);
  useEffect(() => {
    if (!polling) return undefined;
    const t = setInterval(() => {
      refresh().catch(() => {});
      if (selectedId) loadDetail(selectedId).catch(() => {});
    }, 2000);
    return () => clearInterval(t);
  }, [polling, refresh, loadDetail, selectedId]);

  const startPreview = async (source, options, files) => {
    const created = await api('runs/', { token, method: 'POST', body: { source, options, files } });
    await refresh();
    setSelectedId(created.id);
    setTab('runs');
  };

  if (!isAuthenticated) {
    return (
      <div className="email-app">
        <p style={{ color: 'var(--text-muted)' }}>Sign in as superuser to manage contacts.</p>
        <button type="button" className="editorial-button" onClick={() => openSocialLoginModal()}>Sign in</button>
      </div>
    );
  }
  if (!isSuperuser) {
    return <div className="email-app"><p className="error-message">Contact Sync is limited to superuser accounts.</p></div>;
  }

  const pendingCount = reviews.length;
  const tabs = [
    ['overview', 'Overview'],
    ['sync', 'Sync'],
    ['runs', `Runs${status?.active_run ? ' •' : ''}`],
    ['review', `Review${pendingCount ? ` (${pendingCount})` : ''}`],
    ['entities', 'People & Orgs'],
    ['transfer', 'Export / Import'],
  ];
  const switchTab = (key) => {
    if (key === tab) return;
    if (editorDirty.current && !window.confirm('Discard your unsaved changes?')) return;
    editorDirty.current = false;
    setTab(key);
  };

  return (
    <div className="email-app">
      <header className="email-chrome">
        <div>
          <h2 style={{ marginTop: 0, borderBottom: 'none', paddingBottom: 0 }}>Contact Sync</h2>
          <p className="email-muted">Sync Google, LinkedIn and WhatsApp into the ClickUp Contacts list.</p>
        </div>
        <div className="email-chrome-actions">
          <button type="button" className="asset-btn-muted" onClick={() => setHelpOpen(true)}
            title="How to use Contact Sync (opens at the section for this tab)">
            Help
          </button>
          <button type="button" className="asset-btn-muted" onClick={() => run('refresh', refresh)} disabled={!!busy}>
            Refresh
          </button>
        </div>
      </header>
      {helpOpen && <HelpPanel section={HELP_SECTIONS[tab]} onClose={closeHelp} />}

      {status && !status.clickup.configured && (
        <div className="contacts-banner contacts-banner--warn">
          ClickUp isn’t configured: set CONTACTS_CLICKUP_LIST_ID (and CLICKUP_API_TOKEN) on the server.
        </div>
      )}
      {status && status.clickup.configured && (
        <div className={`contacts-banner ${status.clickup.writes_enabled ? '' : 'contacts-banner--info'}`}>
          {status.clickup.writes_enabled
            ? 'Live writes are enabled. Changes reach ClickUp only when you apply a finished preview; existing values are never cleared, and emails, phones and labels are only ever added.'
            : 'Preview-only mode: this server can’t write to ClickUp (CONTACTS_CLICKUP_WRITES_ENABLED is off).'}
        </div>
      )}
      {msg && <div className="asset-status">{msg}</div>}
      {error && <div className="error-message">{error}</div>}

      <nav className="contacts-tabs">
        {tabs.map(([key, label]) => (
          <button key={key} type="button" className={`contacts-tab ${tab === key ? 'contacts-tab--active' : ''}`}
            onClick={() => switchTab(key)}>
            {label}
          </button>
        ))}
      </nav>

      {!status ? (
        <p className="email-muted">Loading…</p>
      ) : (
        <>
          {tab === 'overview' && <OverviewTab status={status} token={token} busy={busy} run={run} onRefresh={refresh} />}
          {tab === 'sync' && (
            <SyncTab status={status} token={token} busy={busy} run={run} startPreview={startPreview} setError={setError} />
          )}
          {tab === 'runs' && (
            <RunsTab runs={runs} selectedId={selectedId} setSelectedId={setSelectedId} detail={detail} token={token}
              busy={busy} run={run} onChanged={async () => { await refresh(); if (selectedId) await loadDetail(selectedId); }} />
          )}
          {tab === 'review' && <ReviewTab token={token} busy={busy} run={run} reviews={reviews} onChanged={refresh} />}
          {tab === 'entities' && (
            <EntitiesTab token={token} writesEnabled={status.clickup.writes_enabled}
              liveRunActive={status.active_run?.mode === 'live'} onDirtyChange={setEditorDirty}
              onStartMerge={(survivor, loser) => startPreview('merge', { survivor, loser }, {})} />
          )}
          {tab === 'transfer' && (
            <TransferTab status={status} token={token} busy={busy} run={run} startPreview={startPreview} setError={setError} />
          )}
        </>
      )}
    </div>
  );
}
