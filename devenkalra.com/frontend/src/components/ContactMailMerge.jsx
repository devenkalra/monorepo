import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './contactsApi';

const TOKENS = [
  'first_name', 'name', 'email', 'company', 'title', 'phones', 'groups', 'outreach',
  'PSalutation', 'FSalutation',
];

function statusLabel(s, delivery) {
  if (s === 'completed' && delivery === 'draft') return 'Completed (drafts in Gmail)';
  if (s === 'completed' && delivery === 'send') return 'Completed (sent)';
  return ({
    draft: 'Draft',
    ready: 'Ready',
    running: 'Running',
    paused: 'Paused',
    waiting_quota: 'Waiting for daily quota',
    completed: 'Completed',
    cancelled: 'Cancelled',
    failed: 'Failed',
  })[s] || s;
}

export function MailMergeTab({
  token, googleConnected, googleCanMail, googleCanSend,
  seedAudience = [], onClearSeed, onConnectMail, onGoPeople,
}) {
  const [campaigns, setCampaigns] = useState([]);
  const [sentTodayAll, setSentTodayAll] = useState(0);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [bodyHtml, setBodyHtml] = useState('');
  const [gmailDraftId, setGmailDraftId] = useState('');
  const [draftAttachmentNames, setDraftAttachmentNames] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [draftsLoading, setDraftsLoading] = useState(false);
  const [sendAs, setSendAs] = useState([]);
  const [fromEmail, setFromEmail] = useState('');
  const [delivery, setDelivery] = useState('draft');
  const [dailyLimit, setDailyLimit] = useState(1200);
  const [perMinute, setPerMinute] = useState(20);
  const [audience, setAudience] = useState([]);
  const [showAdvancedIds, setShowAdvancedIds] = useState(false);
  const [showPlainOverride, setShowPlainOverride] = useState(false);
  const [idsText, setIdsText] = useState('');

  useEffect(() => {
    if (!seedAudience?.length) return;
    setAudience(seedAudience);
    setIdsText(seedAudience.map((r) => r.id).join('\n'));
    setShowAdvancedIds(false);
  }, [seedAudience]);

  const loadList = useCallback(async () => {
    const out = await api('mail-campaigns/', { token });
    setCampaigns(out.campaigns || []);
    setSentTodayAll(out.sent_today_all || 0);
  }, [token]);

  const loadDrafts = useCallback(async () => {
    if (!googleCanMail) {
      setDrafts([]);
      return;
    }
    setDraftsLoading(true);
    try {
      const out = await api('mail-campaigns/drafts/', { token });
      setDrafts(out.drafts || []);
    } catch (err) {
      setError(err.message);
      setDrafts([]);
    } finally {
      setDraftsLoading(false);
    }
  }, [token, googleCanMail]);

  const loadSendAs = useCallback(async () => {
    if (!googleCanMail) {
      setSendAs([]);
      return;
    }
    try {
      const out = await api('mail-campaigns/send-as/', { token });
      const rows = out.send_as || [];
      setSendAs(rows);
      if (!fromEmail) {
        // Prefer a real mailbox (primary) over treat-as-alias custom From — aliases
        // often land in Sent but never reach recipients (DMARC fail on custom domains).
        const preferred = rows.find((r) => r.is_primary)
          || rows.find((r) => r.is_default && !r.treat_as_alias)
          || rows.find((r) => r.is_default)
          || rows[0];
        if (preferred) setFromEmail(preferred.email);
      }
    } catch (err) {
      setError(err.message);
      setSendAs([]);
    }
  }, [token, googleCanMail, fromEmail]);

  const selectedFrom = sendAs.find((r) => r.email === fromEmail);
  const fromIsAlias = Boolean(selectedFrom?.treat_as_alias && !selectedFrom?.is_primary);

  const pickDraft = async (draftId) => {
    setGmailDraftId(draftId);
    if (!draftId) {
      setSubject('');
      setBody('');
      setBodyHtml('');
      setDraftAttachmentNames([]);
      return;
    }
    setBusy(true);
    setError('');
    try {
      const tpl = await api(`mail-campaigns/drafts/${encodeURIComponent(draftId)}/`, { token });
      setSubject(tpl.subject || '');
      setBody(tpl.text || '');
      setBodyHtml(tpl.html || '');
      setDraftAttachmentNames(tpl.attachment_names || []);
      if (!name && tpl.subject) setName(tpl.subject);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const loadDetail = useCallback(async (id) => {
    if (!id) {
      setDetail(null);
      return;
    }
    const out = await api(`mail-campaigns/${id}/?recipients=1`, { token });
    setDetail(out);
  }, [token]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await loadList();
        if (!cancelled) {
          await loadDrafts();
          await loadSendAs();
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    })();
    return () => { cancelled = true; };
  }, [loadList, loadDrafts, loadSendAs]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        await loadDetail(selectedId);
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    })();
    const t = setInterval(() => {
      if (detail?.status === 'running' || detail?.status === 'waiting_quota') {
        loadDetail(selectedId).catch(() => {});
        loadList().catch(() => {});
      }
    }, 5000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [selectedId, loadDetail, loadList, detail?.status]);

  const audienceIds = useMemo(() => {
    if (audience.length) return audience.map((r) => r.id);
    return idsText.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);
  }, [audience, idsText]);

  const clearAudience = () => {
    setAudience([]);
    setIdsText('');
    onClearSeed?.();
  };

  const create = async () => {
    setBusy(true);
    setError('');
    try {
      const out = await api('mail-campaigns/', {
        token,
        method: 'POST',
        body: {
          ids: audienceIds,
          name: name || (audience.length ? `Mail merge (${audience.length})` : ''),
          subject_template: subject,
          body_template: body,
          body_html_template: bodyHtml,
          gmail_draft_id: gmailDraftId,
          from_email: fromEmail,
          from_name: (sendAs.find((r) => r.email === fromEmail) || {}).name || '',
          delivery,
          daily_limit: Number(dailyLimit) || 1200,
          per_minute: Number(perMinute) || 20,
        },
      });
      await loadList();
      setSelectedId(out.id);
      setDetail(out);
      clearAudience();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const act = async (action) => {
    if (!selectedId) return;
    setBusy(true);
    setError('');
    try {
      const out = await api(`mail-campaigns/${selectedId}/action/`, {
        token, method: 'POST', body: { action },
      });
      setDetail(out);
      await loadList();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const c = detail?.counts || {};

  return (
    <div className="contacts-mail-merge">
      <p className="email-muted">
        Select people on <strong>People &amp; Orgs</strong>, then click <strong>Mail merge</strong>.
        Compose the message as a <strong>Gmail draft</strong> with tokens
        ({TOKENS.map((t) => `{{${t}}}`).join(', ')}
        — single braces like {'{PSalutation}'} also work), pick that draft here, then start the campaign.
        The worker creates personalized Gmail drafts or sends under a daily cap.
      </p>
      <p className="email-muted">Sent / drafted today (all campaigns, UTC): {sentTodayAll}</p>

      {!googleConnected && (
        <div className="contacts-banner contacts-banner--warn">Connect Google on Overview first.</div>
      )}
      {googleConnected && !googleCanMail && (
        <div className="contacts-banner contacts-banner--warn">
          Gmail access is not granted.
          <button type="button" className="editorial-button" style={{ marginLeft: '0.75rem' }}
            disabled={busy} onClick={onConnectMail}>
            Grant Gmail access
          </button>
        </div>
      )}
      {error && <div className="error-message">{error}</div>}

      <div className="contacts-mail-layout">
        <section className="contacts-bulk-panel">
          <strong>New campaign</strong>

          <div className="contacts-mail-audience">
            {audienceIds.length === 0 ? (
              <div className="contacts-banner contacts-banner--info">
                No audience yet.
                <button type="button" className="editorial-button" style={{ marginLeft: '0.75rem' }}
                  onClick={onGoPeople}>
                  Select on People &amp; Orgs
                </button>
              </div>
            ) : (
              <>
                <div className="contacts-toolbar" style={{ marginBottom: '0.35rem' }}>
                  <span>
                    <strong>{audienceIds.length}</strong> selected
                    {audience.length ? ' from People & Orgs' : ''}
                  </span>
                  <button type="button" className="asset-btn-muted" onClick={clearAudience}>Clear</button>
                  <button type="button" className="asset-btn-muted" onClick={onGoPeople}>
                    Change selection
                  </button>
                </div>
                {audience.length > 0 && (
                  <ul className="contacts-mail-audience-list">
                    {audience.slice(0, 12).map((r) => (
                      <li key={r.id}>
                        {r.name}
                        {r.email ? <span className="email-muted"> · {r.email}</span> : (
                          <span className="email-muted"> · no email</span>
                        )}
                      </li>
                    ))}
                    {audience.length > 12 && (
                      <li className="email-muted">…and {audience.length - 12} more</li>
                    )}
                  </ul>
                )}
              </>
            )}
          </div>

          <label className="contacts-field">
            Campaign name
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Diwali 2026" />
          </label>
          <label className="contacts-field">
            Gmail draft template
            <select
              value={gmailDraftId}
              disabled={busy || draftsLoading || !googleCanMail}
              onChange={(e) => pickDraft(e.target.value)}>
              <option value="">{draftsLoading ? 'Loading drafts…' : 'Select a draft…'}</option>
              {drafts.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.subject}{d.has_html ? ' · HTML' : ''}{d.has_attachments ? ' · attachment' : ''}
                </option>
              ))}
            </select>
          </label>
          <div className="contacts-toolbar email-muted" style={{ marginTop: '-0.25rem' }}>
            <button type="button" className="asset-btn-muted" disabled={busy || !googleCanMail || draftsLoading}
              onClick={() => loadDrafts()}>
              Refresh drafts
            </button>
            <span>Write the email in Gmail first (leave as draft), include {'{{first_name}}'} etc. Attachments on the draft are copied into each merge.</span>
          </div>
          {gmailDraftId && (
            <>
              {draftAttachmentNames.length > 0 && (
                <p className="email-muted" style={{ marginTop: '-0.25rem' }}>
                  Attachments: {draftAttachmentNames.join(', ')}
                </p>
              )}
              <label className="contacts-field">
                Subject (from draft; editable)
                <input value={subject} onChange={(e) => setSubject(e.target.value)} />
              </label>
              {bodyHtml ? (
                <div className="contacts-field">
                  <span className="contacts-field-name">HTML preview</span>
                  <div
                    className="contacts-mail-html-preview"
                    dangerouslySetInnerHTML={{ __html: bodyHtml }}
                  />
                </div>
              ) : null}
              <button type="button" className="asset-btn-muted" style={{ alignSelf: 'flex-start' }}
                onClick={() => setShowPlainOverride((v) => !v)}>
                {showPlainOverride ? 'Hide plain text' : 'Show plain text fallback'}
              </button>
              {showPlainOverride && (
                <label className="contacts-field">
                  Plain text
                  <textarea rows={6} value={body} onChange={(e) => setBody(e.target.value)} />
                </label>
              )}
            </>
          )}
          <label className="contacts-field">
            From (verified send-as)
            <select value={fromEmail} disabled={busy || !sendAs.length}
              onChange={(e) => setFromEmail(e.target.value)}>
              {!sendAs.length && <option value="">Loading…</option>}
              {sendAs.map((r) => (
                <option key={r.email} value={r.email}>
                  {(r.name ? `${r.name} <${r.email}>` : r.email)
                    + (r.is_primary ? ' · Google login' : '')
                    + (r.is_default ? ' · Gmail default' : '')
                    + (r.treat_as_alias && !r.is_primary ? ' · alias (may not deliver)' : '')}
                </option>
              ))}
            </select>
          </label>
          {fromIsAlias ? (
            <div className="contacts-banner contacts-banner--warn" style={{ marginTop: '-0.25rem' }}>
              <strong>{fromEmail}</strong> is a Gmail “Send mail as” alias on
              {' '}{sendAs.find((r) => r.is_primary)?.email || 'this login'}, not the Workspace mailbox.
              Gmail will show it in <strong>Sent</strong>, but recipients (especially @kalra.com) often
              never get it (DMARC). For real delivery from that address, reconnect Google as
              {' '}<strong>{fromEmail}</strong> (Workspace), or pick the Google login From for tests.
            </div>
          ) : (
            <p className="email-muted" style={{ marginTop: '-0.35rem' }}>
              Google login From delivers reliably; a custom-domain From only authenticates if this
              Google account owns that mailbox (not merely a verified alias).
            </p>
          )}
          <label className="contacts-field">
            Delivery
            <select value={delivery} onChange={(e) => setDelivery(e.target.value)}>
              <option value="draft">Gmail drafts (review in Gmail, then send)</option>
              <option value="send" disabled={!googleCanSend}>Send now {!googleCanSend ? '(needs send scope)' : ''}</option>
            </select>
          </label>
          <div className="contacts-mail-limits">
            <label className="contacts-field">
              Daily limit
              <input type="number" min={1} max={1400} value={dailyLimit}
                onChange={(e) => setDailyLimit(e.target.value)} />
            </label>
            <label className="contacts-field">
              Per tick
              <input type="number" min={1} max={60} value={perMinute}
                onChange={(e) => setPerMinute(e.target.value)} />
            </label>
          </div>

          <button type="button" className="asset-btn-muted" style={{ alignSelf: 'flex-start' }}
            onClick={() => setShowAdvancedIds((v) => !v)}>
            {showAdvancedIds ? 'Hide task IDs' : 'Advanced: edit task IDs'}
          </button>
          {showAdvancedIds && (
            <label className="contacts-field">
              People task IDs (one per line)
              <textarea rows={6} value={idsText}
                onChange={(e) => {
                  setIdsText(e.target.value);
                  setAudience([]);
                }}
                placeholder="Only needed if you are not using People & Orgs selection" />
            </label>
          )}

          <button type="button" className="editorial-button"
            disabled={busy || !audienceIds.length || !gmailDraftId || !subject}
            onClick={create}>
            Create campaign ({audienceIds.length || 0})
          </button>
        </section>

        <section>
          <div className="contacts-toolbar email-muted">
            <span>{campaigns.length} campaigns</span>
            <button type="button" className="asset-btn-muted" disabled={busy}
              onClick={() => { loadList().catch((e) => setError(e.message)); }}>
              Refresh
            </button>
          </div>
          <table className="contacts-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Today</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((row) => (
                <tr key={row.id}
                  className={row.id === selectedId ? 'contacts-entity-row--active' : ''}
                  onClick={() => setSelectedId(row.id)}
                  style={{ cursor: 'pointer' }}>
                  <td>{row.name || `#${row.id}`}</td>
                  <td>{statusLabel(row.status, row.delivery)}</td>
                  <td>{row.counts?.done ?? 0}/{row.counts?.total ?? 0}</td>
                  <td>{row.sent_today}/{row.daily_limit}</td>
                </tr>
              ))}
              {campaigns.length === 0 && (
                <tr><td colSpan={4} className="email-muted">No campaigns yet.</td></tr>
              )}
            </tbody>
          </table>
        </section>
      </div>

      {detail && (
        <section className="contacts-bulk-panel" style={{ marginTop: '1rem' }}>
          <strong>{detail.name || `Campaign #${detail.id}`}</strong>
          <p className="email-muted">
            {statusLabel(detail.status, detail.delivery)}
            {' · '}{c.done || 0} done / {c.total || 0}
            {' · '}{c.pending || 0} pending
            {' · '}{c.failed || 0} failed
            {' · '}today {detail.sent_today}/{detail.daily_limit}
            {' · '}{detail.delivery === 'send' ? 'Send' : 'Drafts'}
            {detail.from_email ? ` · From ${detail.from_name ? `${detail.from_name} <${detail.from_email}>` : detail.from_email}` : ''}
            {detail.attachment_names?.length
              ? ` · ${detail.attachment_names.length} attachment${detail.attachment_names.length === 1 ? '' : 's'}`
              : ''}
          </p>
          {detail.status === 'completed' && detail.delivery === 'draft' && (
            <div className="contacts-banner contacts-banner--info">
              Personalized messages were saved as <strong>Drafts</strong> in
              {' '}{googleConnected ? 'your connected Gmail' : 'Gmail'} — they were not sent.
              Open Gmail → Drafts to review, then send (or create a new campaign with Delivery = Send now).
            </div>
          )}
          {detail.status === 'completed' && detail.delivery === 'send' && (
            <div className="contacts-banner contacts-banner--info">
              Gmail accepted the sends — check <strong>Gmail → Sent</strong> for
              {' '}{detail.from_email || 'the From address'} → each recipient.
              If Sent looks right but inboxes are empty, the From address is likely a
              display alias (DMARC drop); reconnect as that Workspace mailbox or use the Google login From.
            </div>
          )}
          {detail.error && <div className="error-message">{detail.error}</div>}
          <div className="contacts-bulk-bar" style={{ marginBottom: '0.75rem' }}>
            {['ready', 'paused', 'waiting_quota'].includes(detail.status) && (
              <button type="button" className="editorial-button" disabled={busy || !googleCanMail}
                onClick={() => act('start')}>Start / Resume</button>
            )}
            {detail.status === 'running' && (
              <button type="button" className="editorial-button" disabled={busy}
                onClick={() => act('pause')}>Pause</button>
            )}
            {!['completed', 'cancelled'].includes(detail.status) && (
              <button type="button" className="asset-btn-muted" disabled={busy}
                onClick={() => act('cancel')}>Cancel pending</button>
            )}
            {(c.failed || 0) > 0 && (
              <button type="button" className="asset-btn-muted" disabled={busy}
                onClick={() => act('retry_failed')}>Retry failed</button>
            )}
            <button type="button" className="asset-btn-muted" disabled={busy || !googleCanMail}
              title="Process one throttle slice now"
              onClick={() => act('tick')}>Tick now</button>
          </div>

          {detail.preview?.length > 0 && (
            <>
              <strong>Preview</strong>
              <table className="contacts-table">
                <thead>
                  <tr><th>To</th><th>Subject</th><th>Body</th></tr>
                </thead>
                <tbody>
                  {detail.preview.slice(0, 10).map((p) => (
                    <tr key={p.id}>
                      <td>{p.email}<div className="email-muted">{p.name}</div></td>
                      <td>{p.subject}</td>
                      <td className="contacts-cell-wrap">
                        {p.body_html ? (
                          <div dangerouslySetInnerHTML={{ __html: p.body_html }} />
                        ) : (
                          <span style={{ whiteSpace: 'pre-wrap' }}>{p.body}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {detail.recipients?.length > 0 && (
            <>
              <strong>Recipients</strong>
              <table className="contacts-table">
                <thead>
                  <tr><th>Email</th><th>Name</th><th>Status</th><th>Error</th></tr>
                </thead>
                <tbody>
                  {detail.recipients.slice(0, 100).map((r) => (
                    <tr key={r.id}>
                      <td>{r.email}</td>
                      <td>{r.name}</td>
                      <td>{r.status}</td>
                      <td className="email-muted">{r.last_error}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {detail.recipients.length > 100 && (
                <p className="email-muted">Showing first 100 of {detail.recipients.length}.</p>
              )}
            </>
          )}

          {(detail.skipped_on_create || []).length > 0 && (
            <div className="contacts-banner contacts-banner--warn">
              Skipped on create: {detail.skipped_on_create.length}
              <ul>
                {detail.skipped_on_create.slice(0, 20).map((s) => (
                  <li key={`${s.task_id}-${s.reason}`}>{s.name || s.task_id}: {s.reason}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
