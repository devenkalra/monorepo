import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';

async function api(path, { token, method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json' };
  if (token) headers.Authorization = `Token ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(`/api/email/${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: 'omit',
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return data;
}

function formatWhen(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function formatBriefDate(iso) {
  if (!iso) return '';
  try {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '';
    const now = new Date();
    const ageMs = now.getTime() - date.getTime();
    if (ageMs >= 0 && ageMs < 24 * 60 * 60 * 1000) {
      return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
    }
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    const yy = String(date.getFullYear()).slice(-2);
    if (date.getFullYear() === now.getFullYear()) {
      return `${mm}/${dd}`;
    }
    return `${yy}/${dd}/${mm}`;
  } catch {
    return '';
  }
}

function displayFrom(fromAddress) {
  if (!fromAddress) return '—';
  const named = fromAddress.match(/^"?([^"<]+)"?\s*</);
  if (named?.[1]?.trim()) return named[1].trim();
  return fromAddress.replace(/[<>]/g, '').trim() || '—';
}

function emailHoverTitle({ from, subject, snippet, extra }) {
  return [from || '', subject || '(no subject)', snippet || '', extra || '']
    .filter((part, idx, arr) => part || (idx < 2 && arr.some(Boolean)))
    .filter(Boolean)
    .join('\n');
}

function gmailThreadUrl(threadId) {
  if (!threadId) return null;
  return `https://mail.google.com/mail/u/0/#all/${encodeURIComponent(threadId)}`;
}

function MailSubject({ subject, threadId }) {
  const href = gmailThreadUrl(threadId);
  const label = subject || '(no subject)';
  if (!href) {
    return <span className="email-mail-subject">{label}</span>;
  }
  return (
    <a
      className="email-mail-subject email-mail-subject-link"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title="Open in Gmail"
      onClick={(e) => e.stopPropagation()}
    >
      {label}
    </a>
  );
}

const SAVED_PROMPTS_KEY = 'email-processor-saved-prompts';
const SAVED_PROMPTS_MIGRATED_KEY = 'email-processor-saved-prompts-migrated';

function readLocalSavedPrompts() {
  try {
    const raw = localStorage.getItem(SAVED_PROMPTS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function normalizeSavedList(data) {
  const list = Array.isArray(data) ? data : data?.results || [];
  return list.map((item) => ({
    id: item.id,
    label: item.label || '',
    prompt: item.prompt || '',
    gmail_query: item.gmail_query || '',
    savedAt: item.updated_at || item.created_at || item.savedAt || '',
  }));
}

function defaultSaveLabel(promptText, queryText) {
  const text = (promptText || queryText || '').trim();
  if (!text) return '';
  return text.length > 60 ? `${text.slice(0, 57)}…` : text;
}

export function EmailProcessorApp() {
  const { token, isAuthenticated, user, openSocialLoginModal } = useAuth();
  const [status, setStatus] = useState(null);
  const [review, setReview] = useState([]);
  const [recent, setRecent] = useState([]);
  const [runs, setRuns] = useState([]);
  const [commandSession, setCommandSession] = useState(null);
  const [commandExamples, setCommandExamples] = useState([]);
  const [commandLabels, setCommandLabels] = useState([]);
  const [commandLog, setCommandLog] = useState([]);
  const [prompt, setPrompt] = useState('');
  const [pendingConfirm, setPendingConfirm] = useState(null);
  const [selectedMessageIds, setSelectedMessageIds] = useState(() => new Set());
  const [selectedReviewIds, setSelectedReviewIds] = useState(() => new Set());
  const [labelChoice, setLabelChoice] = useState('');
  const [customLabel, setCustomLabel] = useState('');
  const [reviewLabelChoice, setReviewLabelChoice] = useState('');
  const [reviewCustomLabel, setReviewCustomLabel] = useState('');
  const [savedPrompts, setSavedPrompts] = useState([]);
  const [showSavedPrompts, setShowSavedPrompts] = useState(false);
  const [showSaveSearchForm, setShowSaveSearchForm] = useState(false);
  const [saveLabelDraft, setSaveLabelDraft] = useState('');
  const [editingSavedId, setEditingSavedId] = useState(null);
  const [editLabelDraft, setEditLabelDraft] = useState('');
  const [selectionSummary, setSelectionSummary] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState('');
  const shiftAnchorRef = useRef(null);
  const reviewShiftAnchorRef = useRef(null);

  const isSuperuser = user?.role === 'superuser' || Boolean(user?.isStaff);

  const loadSavedSearches = useCallback(async () => {
    if (!token) return;
    let list = normalizeSavedList(await api('saved-searches/', { token }));
    // One-time import of browser-local saves into the DB
    if (
      list.length === 0
      && localStorage.getItem(SAVED_PROMPTS_MIGRATED_KEY) !== '1'
    ) {
      const localItems = readLocalSavedPrompts();
      for (const item of localItems) {
        const promptText = (item.prompt || item.gmail_query || '').trim();
        if (!promptText) continue;
        try {
          await api('saved-searches/', {
            token,
            method: 'POST',
            body: {
              label: (item.label || promptText).trim().slice(0, 120),
              prompt: promptText,
              gmail_query: item.gmail_query || '',
            },
          });
        } catch {
          // ignore individual migration failures
        }
      }
      localStorage.setItem(SAVED_PROMPTS_MIGRATED_KEY, '1');
      list = normalizeSavedList(await api('saved-searches/', { token }));
    }
    setSavedPrompts(list);
  }, [token]);

  const refresh = useCallback(async () => {
    if (!token) return;
    setError('');
    const [st, messages, allMessages, runList, command] = await Promise.all([
      api('mailbox/status/', { token }),
      api('messages/?status=needs_review', { token }),
      api('messages/', { token }),
      api('runs/', { token }),
      api('command/', { token }),
    ]);
    setStatus(st);
    const reviewList = Array.isArray(messages) ? messages : messages.results || [];
    setReview(reviewList);
    const recentList = Array.isArray(allMessages) ? allMessages : allMessages.results || [];
    setRecent(
      recentList
        .filter((m) => m.classification || ['processed', 'needs_review', 'failed', 'processing'].includes(m.status))
        .slice(0, 25),
    );
    setRuns(Array.isArray(runList) ? runList : runList.results || []);
    setCommandSession(command?.session || null);
    setCommandExamples(command?.examples || []);
    setCommandLabels(command?.labels || []);
    const liveMessageIds = new Set(
      (command?.session?.items || []).map((item) => item.gmail_id).filter(Boolean),
    );
    setSelectedMessageIds((prev) => new Set([...prev].filter((id) => liveMessageIds.has(id))));
    const liveReviewIds = new Set(reviewList.map((m) => m.id));
    setSelectedReviewIds((prev) => new Set([...prev].filter((id) => liveReviewIds.has(id))));
    await loadSavedSearches();
  }, [token, loadSavedSearches]);

  useEffect(() => {
    if (!isAuthenticated || !token || !isSuperuser) return;
    refresh().catch((err) => setError(err.message));
  }, [isAuthenticated, token, isSuperuser, refresh]);

  const connectGmail = async () => {
    setBusy('oauth');
    setError('');
    try {
      const data = await api('oauth/start/', { token });
      window.location.href = data.authorize_url;
    } catch (err) {
      setError(err.message);
      setBusy('');
    }
  };

  const syncNow = async () => {
    setBusy('sync');
    setError('');
    try {
      await api('mailbox/sync_now/', { token, method: 'POST', body: {} });
      setMsg('Sync job queued.');
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const renewWatch = async () => {
    setBusy('watch');
    setError('');
    try {
      await api('mailbox/renew_watch/', { token, method: 'POST', body: {} });
      setMsg('Gmail watch renewed.');
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const approve = async (id, intent) => {
    setBusy(`approve-${id}`);
    setError('');
    try {
      await api(`messages/${id}/approve/`, {
        token,
        method: 'POST',
        body: intent ? { intent } : {},
      });
      setMsg('Workflow started.');
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const dismiss = async (id) => {
    setBusy(`dismiss-${id}`);
    setError('');
    try {
      await api(`messages/${id}/dismiss/`, { token, method: 'POST', body: {} });
      setMsg('Archived as ignored.');
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const setReviewSelected = (message, index, { shiftKey = false, selected } = {}) => {
    const wantSelected = selected ?? !selectedReviewIds.has(message.id);
    setSelectedReviewIds((prev) => {
      const next = new Set(prev);
      if (shiftKey && reviewShiftAnchorRef.current != null) {
        const start = Math.min(reviewShiftAnchorRef.current, index);
        const end = Math.max(reviewShiftAnchorRef.current, index);
        for (let i = start; i <= end; i += 1) {
          const id = review[i]?.id;
          if (id == null) continue;
          if (wantSelected) next.add(id);
          else next.delete(id);
        }
      } else if (wantSelected) {
        next.add(message.id);
      } else {
        next.delete(message.id);
      }
      return next;
    });
    if (!shiftKey) reviewShiftAnchorRef.current = index;
  };

  const selectAllReview = (checked) => {
    if (!checked) {
      setSelectedReviewIds(new Set());
      reviewShiftAnchorRef.current = null;
      return;
    }
    setSelectedReviewIds(new Set(review.map((m) => m.id)));
    reviewShiftAnchorRef.current = review.length ? 0 : null;
  };

  const runReviewBulk = async (action, { intent, confirm = false, ids: overrideIds } = {}) => {
    const ids = overrideIds ? [...overrideIds] : [...selectedReviewIds];
    if (!ids.length) {
      setError('Select one or more review messages first.');
      return;
    }
    const body = { action, ids, confirm };
    if (intent) body.intent = intent;
    if (action === 'label') {
      if (reviewLabelChoice === '__custom__') {
        if (!reviewCustomLabel.trim()) {
          setError('Enter a label name.');
          return;
        }
        body.label_name = reviewCustomLabel.trim();
      } else if (reviewLabelChoice) {
        body.label_id = reviewLabelChoice;
      } else {
        setError('Choose a label to assign.');
        return;
      }
    }

    setBusy(`review-bulk-${action}`);
    setError('');
    setMsg('');
    try {
      const result = await api('messages/bulk/', { token, method: 'POST', body });
      if (result.type === 'confirm') {
        setPendingConfirm({
          kind: 'review-bulk',
          action,
          ids,
          result,
        });
        return;
      }
      setPendingConfirm(null);
      setSelectedReviewIds(new Set());
      reviewShiftAnchorRef.current = null;
      const failed = result.failed?.length || 0;
      setMsg(
        failed
          ? `${action}: ${result.affected} ok, ${failed} failed.`
          : `${action}: ${result.affected} message(s).`,
      );
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const pushLog = (entry) => {
    setCommandLog((prev) => [entry, ...prev].slice(0, 12));
  };

  const runCommand = async ({ text, confirm = false, forceSearch = false } = {}) => {
    const value = (text ?? prompt).trim();
    if (!value) return;
    setBusy(confirm ? 'command-confirm' : 'command');
    setError('');
    setMsg('');
    try {
      const result = await api('command/', {
        token,
        method: 'POST',
        body: { prompt: value, confirm, force_search: forceSearch },
      });
      setCommandSession(result.session || null);
      if (result.type === 'confirm') {
        setPendingConfirm({ prompt: value, result });
        pushLog({
          kind: 'confirm',
          prompt: value,
          detail: result.detail || result.explanation,
          count: result.target_count,
        });
      } else {
        setPendingConfirm(null);
        pushLog({
          kind: result.type,
          prompt: value,
          detail: result.explanation || result.question || result.detail || '',
          query: result.gmail_query,
          count: result.count ?? result.affected,
          action: result.action,
        });
        if (result.type === 'search') {
          setMsg(`Found ${result.count} message(s).`);
        } else if (result.type === 'action') {
          setMsg(`${result.action}: ${result.affected} message(s).`);
        } else if (result.type === 'clarify') {
          setMsg(result.question || result.explanation);
        }
        if (!confirm) setPrompt('');
      }
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const clearCommandSession = async () => {
    setBusy('command-clear');
    setError('');
    try {
      await api('command/', { token, method: 'DELETE' });
      setCommandSession(null);
      setPendingConfirm(null);
      setSelectionSummary(null);
      setSelectedMessageIds(new Set());
      shiftAnchorRef.current = null;
      setMsg('Command session cleared.');
      pushLog({ kind: 'clear', prompt: '', detail: 'Session cleared.' });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const openSaveSearchForm = () => {
    const text = (commandSession?.prompt || prompt || '').trim();
    const query = (commandSession?.gmail_query || '').trim();
    if (!text && !query) {
      setError('Nothing to save yet. Run a search first.');
      return;
    }
    setSaveLabelDraft(defaultSaveLabel(text, query));
    setShowSaveSearchForm(true);
    setError('');
    setMsg('');
  };

  const saveCurrentSearch = async () => {
    const text = (commandSession?.prompt || prompt || '').trim();
    const query = (commandSession?.gmail_query || '').trim();
    if (!text && !query) {
      setError('Nothing to save yet. Run a search first.');
      return;
    }
    const label = (saveLabelDraft || defaultSaveLabel(text, query)).trim();
    if (!label) {
      setError('Enter a label for this saved search.');
      return;
    }
    setBusy('save-search');
    setError('');
    try {
      await api('saved-searches/', {
        token,
        method: 'POST',
        body: { label, prompt: text || query, gmail_query: query },
      });
      await loadSavedSearches();
      setShowSaveSearchForm(false);
      setShowSavedPrompts(true);
      setMsg('Search saved.');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const renameSavedPrompt = async (id) => {
    const label = editLabelDraft.trim();
    if (!label) {
      setError('Label cannot be empty.');
      return;
    }
    setBusy(`rename-saved-${id}`);
    setError('');
    try {
      const updated = await api(`saved-searches/${id}/`, {
        token,
        method: 'PATCH',
        body: { label },
      });
      setSavedPrompts((prev) =>
        prev.map((item) => (
          item.id === id
            ? { ...item, label: updated.label || label, savedAt: updated.updated_at || item.savedAt }
            : item
        )),
      );
      setEditingSavedId(null);
      setEditLabelDraft('');
      setMsg('Label updated.');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const removeSavedPrompt = async (id) => {
    setBusy(`remove-saved-${id}`);
    setError('');
    try {
      await api(`saved-searches/${id}/`, { token, method: 'DELETE' });
      setSavedPrompts((prev) => prev.filter((item) => item.id !== id));
      if (editingSavedId === id) {
        setEditingSavedId(null);
        setEditLabelDraft('');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const cancelPromptEdit = () => {
    setPrompt('');
    setShowSavedPrompts(false);
    setPendingConfirm(null);
    setError('');
    setMsg('');
  };

  const setMessageSelected = (item, index, { shiftKey = false, selected } = {}) => {
    const messageId = item.gmail_id;
    if (!messageId) return;
    const list = commandSession?.items || [];
    const wantSelected = selected ?? !selectedMessageIds.has(messageId);
    setSelectedMessageIds((prev) => {
      const next = new Set(prev);
      if (shiftKey && shiftAnchorRef.current != null) {
        const start = Math.min(shiftAnchorRef.current, index);
        const end = Math.max(shiftAnchorRef.current, index);
        for (let i = start; i <= end; i += 1) {
          const mid = list[i]?.gmail_id;
          if (!mid) continue;
          if (wantSelected) next.add(mid);
          else next.delete(mid);
        }
      } else if (wantSelected) {
        next.add(messageId);
      } else {
        next.delete(messageId);
      }
      return next;
    });
    if (!shiftKey) shiftAnchorRef.current = index;
  };

  const selectAllMessages = (checked) => {
    const list = commandSession?.items || [];
    if (!checked) {
      setSelectedMessageIds(new Set());
      shiftAnchorRef.current = null;
      return;
    }
    setSelectedMessageIds(new Set(list.map((item) => item.gmail_id).filter(Boolean)));
    shiftAnchorRef.current = list.length ? 0 : null;
  };

  const threadIdsForSelectedMessages = (messageIds) => {
    const wanted = new Set(messageIds);
    const threads = [];
    const seen = new Set();
    for (const item of commandSession?.items || []) {
      if (!wanted.has(item.gmail_id) || !item.thread_id || seen.has(item.thread_id)) continue;
      seen.add(item.thread_id);
      threads.push(item.thread_id);
    }
    return threads;
  };

  const runSelectionAction = async (action, { confirm = false, threadIds: overrideIds } = {}) => {
    const threadIds = overrideIds
      ? [...overrideIds]
      : threadIdsForSelectedMessages([...selectedMessageIds]);
    if (!threadIds.length) {
      setError('Select one or more messages first.');
      return;
    }
    const body = { action, thread_ids: threadIds, confirm };
    if (action === 'label') {
      if (labelChoice === '__custom__') {
        if (!customLabel.trim()) {
          setError('Enter a label name.');
          return;
        }
        body.label_name = customLabel.trim();
      } else if (labelChoice) {
        body.label_id = labelChoice;
      } else {
        setError('Choose a label to assign.');
        return;
      }
    }

    setBusy(`selection-${action}`);
    setError('');
    setMsg('');
    try {
      const result = await api('command/selection/', { token, method: 'POST', body });
      setCommandSession(result.session || null);
      if (result.type === 'confirm') {
        setPendingConfirm({ kind: 'selection', action, threadIds, result });
        pushLog({
          kind: 'confirm',
          prompt: `${action} selected`,
          detail: result.detail,
          count: result.target_count,
          action,
        });
      } else {
        setPendingConfirm(null);
        setSelectedMessageIds(new Set());
        shiftAnchorRef.current = null;
        setMsg(result.explanation || `${action}: ${result.affected} thread(s).`);
        pushLog({
          kind: 'action',
          prompt: `${action} selected`,
          detail: result.explanation,
          count: result.affected,
          action,
        });
        await refresh();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const summarizeSelected = async () => {
    const gmailIds = [...selectedMessageIds];
    if (!gmailIds.length) {
      setError('Select one or more messages first.');
      return;
    }
    if (gmailIds.length > 10) {
      setError('Summarize supports up to 10 messages at a time.');
      return;
    }
    setBusy('selection-summarize');
    setError('');
    setMsg('');
    try {
      const result = await api('command/selection/', {
        token,
        method: 'POST',
        body: { action: 'summarize', gmail_ids: gmailIds },
      });
      setCommandSession(result.session || null);
      const brief = result.brief_summary || result.summary || '';
      const keyPoints = Array.isArray(result.key_points) ? result.key_points : [];
      const detailed = result.detailed_summary || '';
      setSelectionSummary({
        briefSummary: brief,
        keyPoints,
        detailedSummary: detailed,
        count: Array.isArray(result.items) ? result.items.length : gmailIds.length,
        model: result.model || '',
        explanation: result.explanation || '',
      });
      setMsg(result.explanation || `Summarized ${gmailIds.length} message(s).`);
      pushLog({
        kind: 'summary',
        prompt: 'summarize selected',
        detail: brief || result.explanation,
        count: Array.isArray(result.items) ? result.items.length : gmailIds.length,
        action: 'summarize',
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="email-app">
        <p style={{ color: 'var(--text-muted)' }}>Sign in as superuser to manage email automation.</p>
        <button type="button" className="editorial-button" onClick={() => openSocialLoginModal()}>
          Sign in
        </button>
      </div>
    );
  }

  if (!isSuperuser) {
    return (
      <div className="email-app">
        <p className="error-message">Email Processor is limited to superuser accounts.</p>
      </div>
    );
  }

  const mailbox = status?.mailbox;
  const items = commandSession?.items || [];
  const allMessageIds = items.map((item) => item.gmail_id).filter(Boolean);
  const allSelected = allMessageIds.length > 0 && allMessageIds.every((id) => selectedMessageIds.has(id));
  const someSelected = selectedMessageIds.size > 0 && !allSelected;
  const allReviewSelected = review.length > 0 && review.every((m) => selectedReviewIds.has(m.id));
  const someReviewSelected = selectedReviewIds.size > 0 && !allReviewSelected;

  return (
    <div className="email-app">
      <header className="email-chrome">
        <div>
          <h2 style={{ marginTop: 0, borderBottom: 'none', paddingBottom: 0 }}>Email Processor</h2>
          <p className="email-muted">
            Gmail watch → classify → ClickUp / Static Files. Command Center for Prompt-to-Select batch ops.
          </p>
        </div>
        <div className="email-chrome-actions">
          {!mailbox?.has_refresh_token ? (
            <button type="button" className="editorial-button asset-btn" onClick={connectGmail} disabled={!!busy}>
              Connect Gmail
            </button>
          ) : (
            <>
              <button type="button" className="asset-btn-muted" onClick={syncNow} disabled={!!busy}>
                Sync now
              </button>
              <button type="button" className="asset-btn-muted" onClick={renewWatch} disabled={!!busy}>
                Renew watch
              </button>
              <button type="button" className="asset-btn-muted" onClick={() => refresh()} disabled={!!busy}>
                Refresh
              </button>
            </>
          )}
        </div>
      </header>

      {msg && <div className="asset-status">{msg}</div>}
      {error && <div className="error-message">{error}</div>}

      <section className="email-panel email-command">
        <h3>Command Center</h3>
        <p className="email-muted" style={{ marginTop: 0 }}>
          Natural language search → numbered list. Select with checkboxes
          (Shift+click for ranges), then Archive / Delete / Assign label —
          applied deterministically by Gmail thread id.
        </p>
        <form
          className="email-command-form"
          onSubmit={(e) => {
            e.preventDefault();
            runCommand();
          }}
        >
          <textarea
            className="email-command-input"
            rows={3}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder='Try: Find all newsletters from today'
            disabled={!!busy || !mailbox?.has_refresh_token}
          />
          <div className="email-review-actions">
            <button
              type="submit"
              className="editorial-button asset-btn"
              disabled={!!busy || !prompt.trim() || !mailbox?.has_refresh_token}
            >
              Run prompt
            </button>
            <button
              type="button"
              className="asset-btn-muted"
              disabled={!!busy || !prompt.trim() || !mailbox?.has_refresh_token}
              onClick={() => runCommand({ forceSearch: true })}
            >
              Force search
            </button>
            <button
              type="button"
              className="asset-btn-muted"
              disabled={!!busy}
              onClick={() => setShowSavedPrompts((open) => !open)}
            >
              {showSavedPrompts ? 'Hide saved' : `Saved prompts (${savedPrompts.length})`}
            </button>
            <button
              type="button"
              className="asset-btn-muted"
              disabled={!!busy || (!prompt.trim() && !showSavedPrompts && !pendingConfirm)}
              onClick={cancelPromptEdit}
            >
              Cancel
            </button>
            <button
              type="button"
              className="asset-btn-muted"
              disabled={!!busy || !commandSession}
              onClick={clearCommandSession}
            >
              Clear list
            </button>
          </div>
        </form>

        {showSavedPrompts && (
          <div className="email-saved-prompts">
            <div className="email-review-top">
              <strong>Saved prompts</strong>
              <span className="email-muted">Click one to fill the box (does not run)</span>
            </div>
            {savedPrompts.length === 0 ? (
              <p className="email-muted">No saved searches yet. Save one from an active list.</p>
            ) : (
              <ul className="email-saved-list">
                {savedPrompts.map((item) => {
                  const title = item.label || item.prompt || item.gmail_query || 'Saved search';
                  const isEditing = editingSavedId === item.id;
                  return (
                    <li key={item.id} className="email-saved-item">
                      {isEditing ? (
                        <form
                          className="email-saved-rename"
                          onSubmit={(e) => {
                            e.preventDefault();
                            renameSavedPrompt(item.id);
                          }}
                        >
                          <input
                            type="text"
                            value={editLabelDraft}
                            onChange={(e) => setEditLabelDraft(e.target.value)}
                            maxLength={120}
                            disabled={!!busy}
                            autoFocus
                            aria-label="Saved search label"
                          />
                          <button type="submit" className="asset-btn-muted" disabled={!!busy || !editLabelDraft.trim()}>
                            Save
                          </button>
                          <button
                            type="button"
                            className="asset-btn-muted"
                            disabled={!!busy}
                            onClick={() => {
                              setEditingSavedId(null);
                              setEditLabelDraft('');
                            }}
                          >
                            Cancel
                          </button>
                        </form>
                      ) : (
                        <button
                          type="button"
                          className="email-saved-pick"
                          disabled={!!busy}
                          onClick={() => {
                            setPrompt(item.prompt || item.gmail_query || '');
                            setShowSavedPrompts(false);
                            setMsg('Prompt loaded — edit or Run prompt.');
                          }}
                        >
                          <span className="email-saved-prompt-text">{title}</span>
                          {item.label && item.prompt && item.label !== item.prompt ? (
                            <span className="email-muted">{item.prompt}</span>
                          ) : null}
                          {item.gmail_query && item.gmail_query !== item.prompt ? (
                            <span className="email-muted">query: {item.gmail_query}</span>
                          ) : null}
                          <span className="email-muted">{formatBriefDate(item.savedAt) || formatWhen(item.savedAt)}</span>
                        </button>
                      )}
                      <div className="email-saved-actions">
                        {!isEditing ? (
                          <button
                            type="button"
                            className="asset-btn-muted"
                            disabled={!!busy}
                            onClick={() => {
                              setEditingSavedId(item.id);
                              setEditLabelDraft(item.label || item.prompt || item.gmail_query || '');
                            }}
                            title="Rename label"
                          >
                            Label
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="asset-btn-muted"
                          disabled={!!busy}
                          onClick={() => removeSavedPrompt(item.id)}
                          title="Remove saved prompt"
                        >
                          Remove
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}

        {commandExamples.length > 0 && (
          <div className="email-command-examples">
            {commandExamples.map((ex) => (
              <button
                key={ex}
                type="button"
                className="email-example-chip"
                disabled={!!busy || !mailbox?.has_refresh_token}
                onClick={() => {
                  setPrompt(ex);
                  runCommand({ text: ex });
                }}
              >
                {ex}
              </button>
            ))}
          </div>
        )}

        {pendingConfirm && (
          <div className="email-confirm-banner">
            <p>
              <strong>Confirm {pendingConfirm.result.action}</strong>
              {' on '}
              {pendingConfirm.result.target_count}{' '}
              {pendingConfirm.kind === 'selection' ? 'thread(s)' : 'message(s)'}.
            </p>
            <p className="email-muted">{pendingConfirm.result.detail}</p>
            <div className="email-review-actions">
              <button
                type="button"
                className="editorial-button asset-btn"
                disabled={!!busy}
                onClick={() => {
                  if (pendingConfirm.kind === 'selection') {
                    runSelectionAction(pendingConfirm.action, {
                      confirm: true,
                      threadIds: pendingConfirm.threadIds,
                    });
                  } else if (pendingConfirm.kind === 'review-bulk') {
                    runReviewBulk(pendingConfirm.action, {
                      confirm: true,
                      ids: pendingConfirm.ids,
                    });
                  } else {
                    runCommand({ text: pendingConfirm.prompt, confirm: true });
                  }
                }}
              >
                Confirm {pendingConfirm.result.action}
              </button>
              <button
                type="button"
                className="asset-btn-muted"
                disabled={!!busy}
                onClick={() => setPendingConfirm(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {commandSession && (
          <div className="email-command-session">
            <div className="email-searching-for">
              <div className="email-searching-for-text">
                <strong>Searching for</strong>
                <span className="email-muted">
                  {commandSession.prompt || commandSession.gmail_query || '—'}
                  {commandSession.gmail_query && commandSession.prompt !== commandSession.gmail_query
                    ? ` · query: ${commandSession.gmail_query}`
                    : ''}
                  {' · '}expires {formatWhen(commandSession.expires_at)}
                </span>
              </div>
              {!showSaveSearchForm ? (
                <button
                  type="button"
                  className="asset-btn-muted"
                  disabled={!!busy || !(commandSession.prompt || commandSession.gmail_query)}
                  onClick={openSaveSearchForm}
                >
                  Save search
                </button>
              ) : null}
            </div>
            {showSaveSearchForm ? (
              <form
                className="email-save-search-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  saveCurrentSearch();
                }}
              >
                <label className="email-save-search-label">
                  <span>Label</span>
                  <input
                    type="text"
                    value={saveLabelDraft}
                    onChange={(e) => setSaveLabelDraft(e.target.value)}
                    maxLength={120}
                    disabled={!!busy}
                    autoFocus
                    placeholder="e.g. Newsletters"
                  />
                </label>
                <button type="submit" className="asset-btn" disabled={!!busy || !saveLabelDraft.trim()}>
                  Save
                </button>
                <button
                  type="button"
                  className="asset-btn-muted"
                  disabled={!!busy}
                  onClick={() => {
                    setShowSaveSearchForm(false);
                    setSaveLabelDraft('');
                  }}
                >
                  Cancel
                </button>
              </form>
            ) : null}
            {commandSession.explanation ? (
              <p className="email-muted">{commandSession.explanation}</p>
            ) : null}

            {items.length > 0 && (
              <div className="email-selection-bar">
                <label className="email-select-all">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    ref={(el) => {
                      if (el) el.indeterminate = someSelected;
                    }}
                    onChange={(e) => selectAllMessages(e.target.checked)}
                    disabled={!!busy}
                  />
                  Select all
                </label>
                <span className="email-muted">{selectedMessageIds.size} selected</span>
                <button
                  type="button"
                  className="asset-btn-muted"
                  disabled={!!busy || selectedMessageIds.size === 0}
                  onClick={() => runSelectionAction('archive')}
                >
                  Archive
                </button>
                <button
                  type="button"
                  className="asset-btn-muted"
                  disabled={!!busy || selectedMessageIds.size === 0}
                  onClick={() => runSelectionAction('trash')}
                >
                  Delete
                </button>
                <button
                  type="button"
                  className="asset-btn-muted"
                  disabled={!!busy || selectedMessageIds.size === 0}
                  onClick={summarizeSelected}
                  title="Fetch content and summarize with AI (max 10)"
                >
                  {busy === 'selection-summarize' ? 'Summarizing…' : 'Summarize'}
                </button>
                <div className="email-label-assign">
                  <select
                    value={labelChoice}
                    onChange={(e) => setLabelChoice(e.target.value)}
                    disabled={!!busy || selectedMessageIds.size === 0}
                  >
                    <option value="">Assign label…</option>
                    {commandLabels.map((label) => (
                      <option key={label.id} value={label.id}>
                        {label.name}
                      </option>
                    ))}
                    <option value="__custom__">New label…</option>
                  </select>
                  {labelChoice === '__custom__' && (
                    <input
                      type="text"
                      value={customLabel}
                      onChange={(e) => setCustomLabel(e.target.value)}
                      placeholder="Label name"
                      disabled={!!busy}
                    />
                  )}
                  <button
                    type="button"
                    className="asset-btn-muted"
                    disabled={!!busy || selectedMessageIds.size === 0 || !labelChoice}
                    onClick={() => runSelectionAction('label')}
                  >
                    Apply label
                  </button>
                </div>
              </div>
            )}

            {selectionSummary ? (
              <div className="email-summary-panel">
                <div className="email-review-top">
                  <strong>AI summary</strong>
                  <span className="email-muted">
                    {selectionSummary.count} message(s)
                    {selectionSummary.model ? ` · ${selectionSummary.model}` : ''}
                  </span>
                  <button
                    type="button"
                    className="asset-btn-muted"
                    disabled={!!busy}
                    onClick={() => setSelectionSummary(null)}
                  >
                    Dismiss
                  </button>
                </div>
                <section className="email-summary-section">
                  <h4>Brief Summary</h4>
                  {selectionSummary.briefSummary ? (
                    <p className="email-summary-text">{selectionSummary.briefSummary}</p>
                  ) : (
                    <p className="email-muted">No brief summary returned.</p>
                  )}
                </section>
                <section className="email-summary-section">
                  <h4>Key Points</h4>
                  {selectionSummary.keyPoints.length > 0 ? (
                    <ul className="email-summary-keypoints">
                      {selectionSummary.keyPoints.map((point, idx) => (
                        <li key={`${idx}-${point.slice(0, 24)}`}>{point}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="email-muted">No key points returned.</p>
                  )}
                </section>
                <section className="email-summary-section">
                  <h4>Detailed Summary</h4>
                  {selectionSummary.detailedSummary ? (
                    <p className="email-summary-text">{selectionSummary.detailedSummary}</p>
                  ) : (
                    <p className="email-muted">No detailed summary returned.</p>
                  )}
                </section>
              </div>
            ) : null}

            {items.length === 0 ? (
              <p className="email-muted">List is empty (all selected messages were acted on).</p>
            ) : (
              <ol className="email-mail-list">
                {items.map((item, index) => {
                  const checked = item.gmail_id ? selectedMessageIds.has(item.gmail_id) : false;
                  const from = displayFrom(item.from_address);
                  const subject = item.subject || '(no subject)';
                  const snippet = item.snippet || '';
                  return (
                    <li
                      key={`${item.n}-${item.gmail_id}`}
                      className={`email-mail-row${checked ? ' email-command-row--selected' : ''}`}
                    >
                      <span className="email-command-check">
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={!!busy || !item.gmail_id}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) => {
                            setMessageSelected(item, index, {
                              shiftKey: e.nativeEvent.shiftKey,
                              selected: e.target.checked,
                            });
                          }}
                        />
                      </span>
                      <span className="email-command-n">{item.n}</span>
                      <div
                        className={`email-mail-line${!item.gmail_id || busy ? ' email-mail-line--disabled' : ''}`}
                        title={emailHoverTitle({
                          from: item.from_address || from,
                          subject,
                          snippet,
                          extra: formatWhen(item.received_at),
                        })}
                        role="button"
                        tabIndex={busy || !item.gmail_id ? -1 : 0}
                        onClick={(e) => {
                          if (busy || !item.gmail_id) return;
                          if (e.target.closest('a')) return;
                          setMessageSelected(item, index, {
                            shiftKey: e.shiftKey,
                            selected: !checked,
                          });
                        }}
                        onKeyDown={(e) => {
                          if (busy || !item.gmail_id) return;
                          if (e.key !== 'Enter' && e.key !== ' ') return;
                          e.preventDefault();
                          setMessageSelected(item, index, { selected: !checked });
                        }}
                      >
                        <span className="email-mail-from">{from}</span>
                        <MailSubject subject={subject} threadId={item.thread_id} />
                        {snippet ? (
                          <>
                            <span className="email-mail-sep">—</span>
                            <span className="email-mail-snippet">{snippet}</span>
                          </>
                        ) : null}
                      </div>
                      <time className="email-mail-date" dateTime={item.received_at || undefined}>
                        {formatBriefDate(item.received_at) || '—'}
                      </time>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        )}

        {commandLog.length > 0 && (
          <div className="email-command-log">
            <h4>Recent prompts</h4>
            {commandLog.map((entry, idx) => (
              <div key={`${entry.prompt}-${idx}`} className="email-run-row">
                <span className={`email-pill email-pill--${entry.kind}`}>{entry.kind}</span>
                {entry.prompt ? <span>{entry.prompt}</span> : null}
                {entry.query ? <span className="email-muted">{entry.query}</span> : null}
                {entry.action ? <span className="email-muted">{entry.action}</span> : null}
                {entry.count != null ? <span className="email-muted">n={entry.count}</span> : null}
                {entry.detail ? <span className="email-muted">{entry.detail}</span> : null}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="email-panel">
        <h3>Mailbox</h3>
        {!mailbox ? (
          <p className="email-muted">No mailbox connected yet.</p>
        ) : (
          <dl className="email-meta">
            <div><dt>Email</dt><dd>{mailbox.email}</dd></div>
            <div><dt>History ID</dt><dd>{mailbox.history_id || '—'}</dd></div>
            <div><dt>Watch expires</dt><dd>{formatWhen(mailbox.watch_expiration)}</dd></div>
            <div><dt>Last sync</dt><dd>{formatWhen(mailbox.last_sync_at)}</dd></div>
            <div><dt>Pending jobs</dt><dd>{status?.pending_jobs ?? 0}</dd></div>
            <div><dt>Needs review</dt><dd>{status?.needs_review ?? 0}</dd></div>
            {mailbox.last_error ? (
              <div><dt>Last error</dt><dd className="error-message">{mailbox.last_error}</dd></div>
            ) : null}
          </dl>
        )}
      </section>

      <section className="email-panel">
        <h3>Needs review ({review.length})</h3>
        {review.length === 0 ? (
          <p className="email-muted">Queue is empty.</p>
        ) : (
          <>
            <div className="email-selection-bar">
              <label className="email-select-all">
                <input
                  type="checkbox"
                  checked={allReviewSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = someReviewSelected;
                  }}
                  onChange={(e) => selectAllReview(e.target.checked)}
                  disabled={!!busy}
                />
                Select all
              </label>
              <span className="email-muted">{selectedReviewIds.size} selected</span>
              <button
                type="button"
                className="editorial-button asset-btn"
                disabled={!!busy || selectedReviewIds.size === 0}
                onClick={() => runReviewBulk('approve')}
              >
                Approve
              </button>
              <button
                type="button"
                className="asset-btn-muted"
                disabled={!!busy || selectedReviewIds.size === 0}
                onClick={() => runReviewBulk('approve', { intent: 'writing_idea' })}
              >
                As writing idea
              </button>
              <button
                type="button"
                className="asset-btn-muted"
                disabled={!!busy || selectedReviewIds.size === 0}
                onClick={() => runReviewBulk('approve', { intent: 'image_ingest' })}
              >
                As images
              </button>
              <button
                type="button"
                className="asset-btn-muted"
                disabled={!!busy || selectedReviewIds.size === 0}
                onClick={() => runReviewBulk('dismiss')}
              >
                Ignore & archive
              </button>
              <button
                type="button"
                className="asset-btn-muted"
                disabled={!!busy || selectedReviewIds.size === 0}
                onClick={() => runReviewBulk('archive')}
              >
                Archive
              </button>
              <button
                type="button"
                className="asset-btn-muted"
                disabled={!!busy || selectedReviewIds.size === 0}
                onClick={() => runReviewBulk('trash')}
              >
                Delete
              </button>
              <div className="email-label-assign">
                <select
                  value={reviewLabelChoice}
                  onChange={(e) => setReviewLabelChoice(e.target.value)}
                  disabled={!!busy || selectedReviewIds.size === 0}
                >
                  <option value="">Assign label…</option>
                  {commandLabels.map((label) => (
                    <option key={label.id} value={label.id}>
                      {label.name}
                    </option>
                  ))}
                  <option value="__custom__">New label…</option>
                </select>
                {reviewLabelChoice === '__custom__' && (
                  <input
                    type="text"
                    value={reviewCustomLabel}
                    onChange={(e) => setReviewCustomLabel(e.target.value)}
                    placeholder="Label name"
                    disabled={!!busy}
                  />
                )}
                <button
                  type="button"
                  className="asset-btn-muted"
                  disabled={!!busy || selectedReviewIds.size === 0 || !reviewLabelChoice}
                  onClick={() => runReviewBulk('label')}
                >
                  Apply label
                </button>
              </div>
            </div>
            <ul className="email-mail-list">
              {review.map((m, index) => {
                const c = m.classification;
                const checked = selectedReviewIds.has(m.id);
                const from = displayFrom(m.from_address);
                const subject = m.subject || '(no subject)';
                const snippet = c?.summary || m.snippet || '';
                return (
                  <li
                    key={m.id}
                    className={`email-mail-row email-mail-row--review${checked ? ' email-command-row--selected' : ''}`}
                  >
                    <span className="email-command-check">
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={!!busy}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => {
                          setReviewSelected(m, index, {
                            shiftKey: e.nativeEvent.shiftKey,
                            selected: e.target.checked,
                          });
                        }}
                      />
                    </span>
                    <div
                      className={`email-mail-line${busy ? ' email-mail-line--disabled' : ''}`}
                      title={emailHoverTitle({
                        from: m.from_address || from,
                        subject,
                        snippet,
                        extra: [
                          c ? `${c.intent} ${Math.round((c.confidence || 0) * 100)}%` : '',
                          formatWhen(m.received_at),
                        ].filter(Boolean).join(' · '),
                      })}
                      role="button"
                      tabIndex={busy ? -1 : 0}
                      onClick={(e) => {
                        if (busy) return;
                        if (e.target.closest('a')) return;
                        setReviewSelected(m, index, {
                          shiftKey: e.shiftKey,
                          selected: !checked,
                        });
                      }}
                      onKeyDown={(e) => {
                        if (busy) return;
                        if (e.key !== 'Enter' && e.key !== ' ') return;
                        e.preventDefault();
                        setReviewSelected(m, index, { selected: !checked });
                      }}
                    >
                      <span className="email-mail-from">{from}</span>
                      {c?.intent ? <span className="email-pill email-mail-intent">{c.intent}</span> : null}
                      <MailSubject subject={subject} threadId={m.thread_id} />
                      {snippet ? (
                        <>
                          <span className="email-mail-sep">—</span>
                          <span className="email-mail-snippet">{snippet}</span>
                        </>
                      ) : null}
                    </div>
                    <time className="email-mail-date" dateTime={m.received_at || undefined}>
                      {formatBriefDate(m.received_at) || '—'}
                    </time>
                    <div className="email-mail-row-actions">
                      <button type="button" className="asset-btn-muted" disabled={!!busy} onClick={() => approve(m.id)}>
                        Approve
                      </button>
                      <button type="button" className="asset-btn-muted" disabled={!!busy} onClick={() => approve(m.id, 'writing_idea')}>
                        Idea
                      </button>
                      <button type="button" className="asset-btn-muted" disabled={!!busy} onClick={() => approve(m.id, 'image_ingest')}>
                        Images
                      </button>
                      <button type="button" className="asset-btn-muted" disabled={!!busy} onClick={() => dismiss(m.id)}>
                        Ignore
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </section>

      <section className="email-panel">
        <h3>Recent classifications</h3>
        {recent.length === 0 ? (
          <p className="email-muted">No classifications yet.</p>
        ) : (
          <ul className="email-mail-list">
            {recent.map((m) => {
              const c = m.classification;
              const from = displayFrom(m.from_address);
              const subject = m.subject || '(no subject)';
              const snippet = c?.summary || c?.reason || m.snippet || '';
              return (
                <li key={m.id} className="email-mail-row email-mail-row--recent">
                  <div
                    className="email-mail-line"
                    title={emailHoverTitle({
                      from: m.from_address || from,
                      subject,
                      snippet,
                      extra: c
                        ? `${c.intent} ${Math.round((c.confidence || 0) * 100)}% · ${formatWhen(m.received_at)}`
                        : formatWhen(m.received_at),
                    })}
                  >
                    <span className="email-mail-from">{from}</span>
                    {c?.intent ? <span className="email-pill email-mail-intent">{c.intent}</span> : null}
                    <span className={`email-pill email-pill--${m.status}`}>{m.status}</span>
                    <MailSubject subject={subject} threadId={m.thread_id} />
                    {snippet ? (
                      <>
                        <span className="email-mail-sep">—</span>
                        <span className="email-mail-snippet">{snippet}</span>
                      </>
                    ) : null}
                  </div>
                  <time className="email-mail-date" dateTime={m.received_at || undefined}>
                    {formatBriefDate(m.received_at) || '—'}
                  </time>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="email-panel">
        <h3>Recent runs</h3>
        {runs.length === 0 ? (
          <p className="email-muted">No workflow runs yet.</p>
        ) : (
          <div className="email-runs">
            {runs.slice(0, 20).map((r) => (
              <div key={r.id} className="email-run-row">
                <span className={`email-pill email-pill--${r.status}`}>{r.status}</span>
                <span>{r.kind}</span>
                <span className="email-muted">{r.message_subject || `#${r.message}`}</span>
                <span className="email-muted">{formatWhen(r.created_at)}</span>
                {r.error ? <span className="error-message">{r.error}</span> : null}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
