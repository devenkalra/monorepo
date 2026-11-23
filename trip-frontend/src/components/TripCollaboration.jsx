import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  dayDiff, epochToZoned, localZone, zoneAbbr, zonedToEpoch,
} from '@bldrdojo/timezones';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import api from '../services/api';
import { getApiBaseUrl } from '../utils/apiUrl';
import TripCalendar from './TripCalendar';

function shortDayDate(dateStr) {
  if (!dateStr) return '';
  return new Date(`${dateStr}T12:00:00Z`).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

function formatClock(timeStr) {
  if (!timeStr) return '';
  const [h, m] = String(timeStr).split(':').map(Number);
  if (!Number.isFinite(h)) return '';
  const h12 = h % 12 || 12;
  return `${h12}:${String(m || 0).padStart(2, '0')} ${h >= 12 ? 'PM' : 'AM'}`;
}

function formatCommentTime(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const diffMs = Date.now() - d.getTime();
    const mins = Math.round(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch (_) {
    return '';
  }
}

function initialsOf(label) {
  const clean = (label || '?').trim();
  const parts = clean.split(/[\s@._-]+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return clean.slice(0, 2).toUpperCase();
}

export function commentScopeKey(scope) {
  if (!scope || scope === 'all') return 'all';
  if (scope.type === 'trip') return 'trip';
  return `${scope.type}:${scope.id}`;
}

export function commentTargetKey(comment) {
  if (comment.stop) return `stop:${comment.stop}`;
  if (comment.lodging) return `lodging:${comment.lodging}`;
  if (comment.day) return `day:${comment.day}`;
  if (comment.leg) return `leg:${comment.leg}`;
  return 'trip';
}

export function buildCommentIndex(comments = []) {
  const roots = [];
  const repliesByParent = new Map();
  for (const c of comments) {
    if (c.parent) {
      if (!repliesByParent.has(c.parent)) repliesByParent.set(c.parent, []);
      repliesByParent.get(c.parent).push(c);
    } else {
      roots.push(c);
    }
  }
  const threads = roots
    .map((root) => ({
      ...root,
      targetKey: commentTargetKey(root),
      replies: (repliesByParent.get(root.id) || []).sort((a, b) =>
        String(a.created_at).localeCompare(String(b.created_at)) || (a.id - b.id),
      ),
    }))
    .sort((a, b) => {
      if (a.resolved !== b.resolved) return a.resolved ? 1 : -1;
      return String(b.created_at).localeCompare(String(a.created_at)) || (b.id - a.id);
    });

  const openByKey = {};
  const totalByKey = {};
  let openThreads = 0;
  let resolvedThreads = 0;
  for (const t of threads) {
    totalByKey[t.targetKey] = (totalByKey[t.targetKey] || 0) + 1;
    if (t.resolved) {
      resolvedThreads += 1;
    } else {
      openThreads += 1;
      openByKey[t.targetKey] = (openByKey[t.targetKey] || 0) + 1;
    }
  }
  return { threads, openByKey, totalByKey, openThreads, resolvedThreads };
}

export function CommentCountButton({ openCount = 0, totalCount = 0, label = 'Comments', onClick, className = '' }) {
  return (
    <button
      type="button"
      className={`trip-comment-chip${openCount > 0 ? ' has-open' : totalCount > 0 ? ' has-resolved' : ''} ${className}`}
      title={openCount > 0 ? `${label}: ${openCount} open` : totalCount > 0 ? `${label}: ${totalCount} resolved` : `Comment on ${label}`}
      aria-label={openCount > 0 ? `${label}: ${openCount} open comments` : `Comment on ${label}`}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
      {openCount > 0 ? <span>{openCount}</span> : totalCount > 0 ? <span className="is-muted">✓</span> : null}
    </button>
  );
}

export function ShareTripModal({ trip, onClose, onChanged }) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('viewer');
  const [busy, setBusy] = useState(false);
  const [resendingId, setResendingId] = useState(null);
  const [linkBusy, setLinkBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [noticeKind, setNoticeKind] = useState('ok');

  const shares = trip.shares || [];
  const publicUrl = trip.public_enabled && trip.public_path
    ? `${window.location.origin}${trip.public_path}`
    : '';

  const showEmailStatus = (targetEmail, emailStatus, verb = 'Invited') => {
    if (!emailStatus) return;
    if (emailStatus.sent && !emailStatus.console_only) {
      setNoticeKind('ok');
      setNotice(`Invitation email sent to ${targetEmail}.`);
    } else if (emailStatus.sent && emailStatus.console_only) {
      setNoticeKind('warn');
      setNotice(`${verb} ${targetEmail}, but SMTP is not configured on this server (email logged to server console only).`);
    } else {
      setNoticeKind('warn');
      const reason = emailStatus.error ? ` (${emailStatus.error})` : '';
      setNotice(`${verb} ${targetEmail}, but the email failed to send${reason}.`);
    }
  };

  const togglePublic = async (enabled) => {
    setLinkBusy(true);
    setError('');
    try {
      await api.json(`/api/trips/trips/${trip.id}/public-link/`, {
        method: 'POST',
        body: JSON.stringify({ enabled }),
      });
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setLinkBusy(false);
    }
  };

  const regenerateLink = async () => {
    if (!window.confirm('Generate a new public link? Anyone using the previous link will immediately lose access.')) return;
    setLinkBusy(true);
    setError('');
    try {
      await api.json(`/api/trips/trips/${trip.id}/public-link/`, {
        method: 'POST',
        body: JSON.stringify({ enabled: true, regenerate: true }),
      });
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setLinkBusy(false);
    }
  };

  const copyPublicUrl = async () => {
    if (!publicUrl) return;
    try {
      await navigator.clipboard.writeText(publicUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch (_) {
      window.prompt('Copy public link:', publicUrl);
    }
  };

  const invite = async (e) => {
    e.preventDefault();
    const cleaned = email.trim().toLowerCase();
    if (!cleaned) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const created = await api.json('/api/trips/shares/', {
        method: 'POST',
        body: JSON.stringify({ trip_id: trip.id, email: cleaned, role }),
      });
      setEmail('');
      await onChanged();
      showEmailStatus(cleaned, created?.email_status, 'Added');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const resendInvite = async (share) => {
    setResendingId(share.id);
    setError('');
    setNotice('');
    try {
      const res = await api.json(`/api/trips/shares/${share.id}/resend/`, {
        method: 'POST',
        body: '{}',
      });
      showEmailStatus(share.email, res?.email_status, 'Checked');
    } catch (err) {
      setError(err.message);
    } finally {
      setResendingId(null);
    }
  };

  const updateRole = async (share, nextRole) => {
    setError('');
    try {
      await api.json(`/api/trips/shares/${share.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ role: nextRole }),
      });
      await onChanged();
    } catch (err) {
      setError(err.message);
    }
  };

  const removeShare = async (share) => {
    setError('');
    try {
      await api.json(`/api/trips/shares/${share.id}/`, { method: 'DELETE' });
      await onChanged();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="trip-modal-backdrop" onClick={onClose}>
      <div className="trip-modal trip-share-modal" onClick={(e) => e.stopPropagation()}>
        <div className="trip-modal-head">
          <h3>Share “{trip.title}”</h3>
          <button type="button" onClick={onClose}>Close</button>
        </div>

        {error && <p className="trip-error">{error}</p>}
        {notice && (
          <div
            className={`mb-3 flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-xs ${
              noticeKind === 'ok'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                : 'border-amber-200 bg-amber-50 text-amber-900'
            }`}
          >
            <span>{notice}</span>
            <button type="button" onClick={() => setNotice('')} aria-label="Dismiss">×</button>
          </div>
        )}

        <section className="trip-share-card">
          <div className="trip-share-card-head">
            <div>
              <strong>Public read-only link</strong>
              <p className="trip-hint">
                Anyone with the unguessable link can view the route, schedule, ideas, and lodgings — without signing in.
                Private vouchers/documents, confirmation numbers, prices, to-dos, and comments stay hidden.
              </p>
            </div>
            <label className="trip-switch">
              <input
                type="checkbox"
                checked={Boolean(trip.public_enabled)}
                disabled={linkBusy}
                onChange={(e) => togglePublic(e.target.checked)}
              />
              <span>{trip.public_enabled ? 'On' : 'Off'}</span>
            </label>
          </div>
          {publicUrl && (
            <div className="trip-share-link-row">
              <input type="text" readOnly value={publicUrl} onFocus={(e) => e.target.select()} aria-label="Public read-only URL" />
              <button type="button" className="trip-primary" onClick={copyPublicUrl}>
                {copied ? 'Copied!' : 'Copy link'}
              </button>
              <a href={trip.public_path} target="_blank" rel="noreferrer" className="trip-share-open-btn">
                Open ↗
              </a>
              <button type="button" onClick={regenerateLink} disabled={linkBusy} title="Invalidate old link and generate a new token">
                Regenerate
              </button>
            </div>
          )}
        </section>

        <section className="trip-share-card">
          <strong>Collaborators</strong>
          <p className="trip-hint">
            <strong>Editor</strong> can edit the route, schedule, ideas, bookings, and resolve comments.{' '}
            <strong>Viewer</strong> has read-only access and can post comments.
          </p>

          <form className="trip-share-invite" onSubmit={invite}>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@example.com"
              aria-label="Collaborator email"
              required
            />
            <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Collaborator role">
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
            </select>
            <button type="submit" className="trip-primary" disabled={busy || !email.trim()}>
              {busy ? 'Adding…' : 'Invite'}
            </button>
          </form>

          <ul className="trip-share-list">
            <li className="trip-share-person">
              <span className="trip-avatar">{initialsOf(trip.owner_label)}</span>
              <div className="trip-share-person-info">
                <strong>{trip.owner_label || 'You'}</strong>
                <span className="trip-hint">Trip owner</span>
              </div>
              <span className="trip-role-badge is-owner">Owner</span>
            </li>
            {shares.map((s) => (
              <li key={s.id} className="trip-share-person">
                <span className="trip-avatar">{initialsOf(s.user_label || s.email)}</span>
                <div className="trip-share-person-info">
                  <strong>{s.user_label || s.email}</strong>
                  <span className="trip-hint">
                    {s.email}
                    {!s.accepted ? ' · pending signup' : ''}
                  </span>
                </div>
                <select
                  value={s.role}
                  onChange={(e) => updateRole(s, e.target.value)}
                  aria-label={`Role for ${s.email}`}
                >
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                </select>
                <button
                  type="button"
                  onClick={() => resendInvite(s)}
                  disabled={resendingId === s.id}
                  title={`Send invitation email to ${s.email} again`}
                >
                  {resendingId === s.id ? 'Sending…' : 'Resend'}
                </button>
                <button type="button" className="trip-danger-link" onClick={() => removeShare(s)}>
                  Remove
                </button>
              </li>
            ))}
            {shares.length === 0 && (
              <li className="trip-empty">No collaborators invited yet.</li>
            )}
          </ul>
        </section>
      </div>
    </div>
  );
}

export function CommentsDrawer({
  trip,
  scope = 'all',
  currentUser,
  canEdit,
  isOwner,
  onClose,
  onChangeScope,
  onJumpToTarget,
  onReload,
}) {
  const [statusFilter, setStatusFilter] = useState('open');
  const [levelFilter, setLevelFilter] = useState('all');
  const [newTarget, setNewTarget] = useState('trip');
  const [body, setBody] = useState('');
  const [saving, setSaving] = useState(false);
  const [replyOpenId, setReplyOpenId] = useState(null);
  const [replyDrafts, setReplyDrafts] = useState({});
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState('');
  const [error, setError] = useState('');

  const days = trip.days || [];
  const legs = trip.legs || [];
  const ideas = trip.ideas || [];
  const lodgings = trip.lodgings || [];

  const lookup = useMemo(() => {
    const legMap = new Map(legs.map((l) => [l.id, l]));
    const dayMap = new Map(days.map((d, idx) => [d.id, { ...d, dayNumber: idx + 1 }]));
    const lodgingMap = new Map(lodgings.map((l) => [l.id, l]));
    const stopMap = new Map();
    for (const d of days) {
      for (const s of d.stops || []) stopMap.set(s.id, { ...s, dayObj: dayMap.get(d.id), isIdea: false });
    }
    for (const s of ideas) {
      stopMap.set(s.id, { ...s, dayObj: null, isIdea: true });
    }
    return { legMap, dayMap, lodgingMap, stopMap };
  }, [days, legs, ideas, lodgings]);

  const targetMeta = useCallback((comment) => {
    if (comment.stop) {
      const s = lookup.stopMap.get(comment.stop);
      if (!s) return { kind: 'stop', badge: 'Stop', label: `Stop #${comment.stop}` };
      return {
        kind: 'stop',
        badge: s.isIdea ? 'Idea' : 'Stop',
        label: s.isIdea ? s.text : `${s.text} · ${shortDayDate(s.dayObj?.date)}`,
        stop: s,
      };
    }
    if (comment.lodging) {
      const l = lookup.lodgingMap.get(comment.lodging);
      return { kind: 'lodging', badge: 'Lodging', label: l?.name || `Lodging #${comment.lodging}`, lodging: l };
    }
    if (comment.day) {
      const d = lookup.dayMap.get(comment.day);
      return {
        kind: 'day',
        badge: d ? `Day ${d.dayNumber}` : 'Day',
        label: d ? [shortDayDate(d.date), d.title].filter(Boolean).join(' — ') : `Day #${comment.day}`,
        day: d,
      };
    }
    if (comment.leg) {
      const leg = lookup.legMap.get(comment.leg);
      return { kind: 'leg', badge: 'Leg', label: leg?.name || `Leg #${comment.leg}`, leg };
    }
    return { kind: 'trip', badge: 'Trip', label: trip.title };
  }, [lookup, trip.title]);

  const { threads, openThreads, resolvedThreads } = useMemo(
    () => buildCommentIndex(trip.comments || []),
    [trip.comments],
  );

  const isGlobal = !scope || scope === 'all';
  const activeScopeKey = isGlobal ? 'all' : commentScopeKey(scope);

  useEffect(() => {
    if (!isGlobal) {
      setNewTarget(activeScopeKey);
    }
  }, [isGlobal, activeScopeKey]);

  const scopedThreads = useMemo(() => {
    let list = isGlobal ? threads : threads.filter((t) => t.targetKey === activeScopeKey);
    if (isGlobal && levelFilter !== 'all') {
      list = list.filter((t) => t.target_type === levelFilter);
    }
    if (statusFilter === 'open') list = list.filter((t) => !t.resolved);
    else if (statusFilter === 'resolved') list = list.filter((t) => t.resolved);
    return list;
  }, [threads, isGlobal, activeScopeKey, levelFilter, statusFilter]);

  const openInScope = useMemo(
    () => (isGlobal ? openThreads : threads.filter((t) => t.targetKey === activeScopeKey && !t.resolved).length),
    [isGlobal, openThreads, threads, activeScopeKey],
  );
  const resolvedInScope = useMemo(
    () => (isGlobal ? resolvedThreads : threads.filter((t) => t.targetKey === activeScopeKey && t.resolved).length),
    [isGlobal, resolvedThreads, threads, activeScopeKey],
  );

  const postComment = async (e) => {
    e.preventDefault();
    if (!body.trim()) return;
    setSaving(true);
    setError('');
    try {
      const payload = { trip_id: trip.id, body: body.trim() };
      const targetKey = isGlobal ? newTarget : activeScopeKey;
      if (targetKey && targetKey !== 'trip') {
        const [kind, rawId] = targetKey.split(':');
        const id = Number(rawId);
        if (kind === 'leg') payload.leg_id = id;
        else if (kind === 'day') payload.day_id = id;
        else if (kind === 'stop') payload.stop_id = id;
        else if (kind === 'lodging') payload.lodging_id = id;
      }
      await api.json('/api/trips/comments/', { method: 'POST', body: JSON.stringify(payload) });
      setBody('');
      if (statusFilter === 'resolved') setStatusFilter('open');
      await onReload();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const postReply = async (e, rootId) => {
    e.preventDefault();
    const text = (replyDrafts[rootId] || '').trim();
    if (!text) return;
    setSaving(true);
    setError('');
    try {
      await api.json('/api/trips/comments/', {
        method: 'POST',
        body: JSON.stringify({ trip_id: trip.id, parent_id: rootId, body: text }),
      });
      setReplyDrafts((d) => ({ ...d, [rootId]: '' }));
      setReplyOpenId(null);
      await onReload();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const saveEdit = async (commentId) => {
    if (!editDraft.trim()) return;
    setError('');
    try {
      await api.json(`/api/trips/comments/${commentId}/`, {
        method: 'PATCH',
        body: JSON.stringify({ body: editDraft.trim() }),
      });
      setEditingId(null);
      setEditDraft('');
      await onReload();
    } catch (err) {
      setError(err.message);
    }
  };

  const toggleResolve = async (thread) => {
    setError('');
    try {
      const endpoint = thread.resolved ? 'reopen' : 'resolve';
      await api.json(`/api/trips/comments/${thread.id}/${endpoint}/`, { method: 'POST' });
      await onReload();
    } catch (err) {
      setError(err.message);
    }
  };

  const deleteComment = async (comment) => {
    if (!window.confirm(comment.parent ? 'Delete this reply?' : 'Delete this comment thread?')) return;
    setError('');
    try {
      await api.json(`/api/trips/comments/${comment.id}/`, { method: 'DELETE' });
      await onReload();
    } catch (err) {
      setError(err.message);
    }
  };

  const isMe = (authorId) => currentUser && Number(currentUser.id ?? currentUser.pk) === Number(authorId);
  const canResolve = (thread) => canEdit || isMe(thread.author);
  const canDelete = (comment) => isOwner || isMe(comment.author);

  const renderMessageRow = (c, isReply = false) => {
    const editing = editingId === c.id;
    return (
      <div key={c.id} className={`trip-comment-msg${isReply ? ' is-reply' : ''}`}>
        <span className="trip-avatar is-sm">{initialsOf(c.author_label)}</span>
        <div className="trip-comment-msg-body">
          <div className="trip-comment-meta">
            <strong>{c.author_label || 'Collaborator'}</strong>
            <span className="trip-hint">{formatCommentTime(c.created_at)}</span>
            <div className="trip-comment-msg-actions">
              {isMe(c.author) && !editing && (
                <button
                  type="button"
                  onClick={() => {
                    setEditingId(c.id);
                    setEditDraft(c.body);
                  }}
                >
                  Edit
                </button>
              )}
              {canDelete(c) && (
                <button type="button" className="trip-danger-link" onClick={() => deleteComment(c)}>
                  Delete
                </button>
              )}
            </div>
          </div>
          {editing ? (
            <div className="trip-comment-edit-box">
              <textarea
                rows={2}
                value={editDraft}
                onChange={(e) => setEditDraft(e.target.value)}
                autoFocus
              />
              <div className="trip-form-actions">
                <button type="button" className="trip-primary" onClick={() => saveEdit(c.id)}>Save</button>
                <button type="button" onClick={() => { setEditingId(null); setEditDraft(''); }}>Cancel</button>
              </div>
            </div>
          ) : (
            <p className="trip-comment-text">{c.body}</p>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="trip-drawer-backdrop" onClick={onClose}>
      <aside className="trip-drawer trip-comments-drawer" onClick={(e) => e.stopPropagation()} aria-label="Trip comments">
        <header className="trip-drawer-head">
          <div>
            {!isGlobal && (
              <button type="button" className="trip-link-btn" onClick={() => onChangeScope?.('all')}>
                ← All trip comments ({threads.length})
              </button>
            )}
            <h3>{isGlobal ? 'Comments' : `Comments · ${scope.label || scope.type}`}</h3>
          </div>
          <button type="button" onClick={onClose}>Close</button>
        </header>

        <div className="trip-comments-toolbar">
          <div className="trip-status-tabs" role="group" aria-label="Filter comments by status">
            <button type="button" className={statusFilter === 'open' ? 'is-active' : ''} onClick={() => setStatusFilter('open')}>
              Open ({openInScope})
            </button>
            <button type="button" className={statusFilter === 'resolved' ? 'is-active' : ''} onClick={() => setStatusFilter('resolved')}>
              Resolved ({resolvedInScope})
            </button>
            <button type="button" className={statusFilter === 'all' ? 'is-active' : ''} onClick={() => setStatusFilter('all')}>
              All ({openInScope + resolvedInScope})
            </button>
          </div>
          {isGlobal && (
            <select
              value={levelFilter}
              onChange={(e) => setLevelFilter(e.target.value)}
              aria-label="Filter comments by level"
            >
              <option value="all">All levels</option>
              <option value="trip">Trip</option>
              <option value="leg">Legs</option>
              <option value="day">Days</option>
              <option value="stop">Stops &amp; Ideas</option>
              <option value="lodging">Lodgings</option>
            </select>
          )}
        </div>

        {error && <p className="trip-error">{error}</p>}

        <form className="trip-comment-composer" onSubmit={postComment}>
          {isGlobal && (
            <select
              value={newTarget}
              onChange={(e) => setNewTarget(e.target.value)}
              aria-label="Attach comment to"
            >
              <option value="trip">Trip — {trip.title}</option>
              {legs.length > 0 && (
                <optgroup label="Legs">
                  {legs.map((l) => <option key={`leg:${l.id}`} value={`leg:${l.id}`}>Leg · {l.name}</option>)}
                </optgroup>
              )}
              {days.length > 0 && (
                <optgroup label="Days">
                  {days.map((d, idx) => (
                    <option key={`day:${d.id}`} value={`day:${d.id}`}>
                      Day {idx + 1} · {shortDayDate(d.date)}{d.title ? ` — ${d.title}` : ''}
                    </option>
                  ))}
                </optgroup>
              )}
              {lodgings.length > 0 && (
                <optgroup label="Lodgings">
                  {lodgings.map((l) => <option key={`lodging:${l.id}`} value={`lodging:${l.id}`}>Lodging · {l.name}</option>)}
                </optgroup>
              )}
              {days.some((d) => (d.stops || []).length > 0) && (
                <optgroup label="Scheduled stops">
                  {days.flatMap((d) => (d.stops || []).map((s) => (
                    <option key={`stop:${s.id}`} value={`stop:${s.id}`}>
                      {shortDayDate(d.date)} · {s.text.slice(0, 60)}
                    </option>
                  )))}
                </optgroup>
              )}
              {ideas.length > 0 && (
                <optgroup label="Unscheduled ideas">
                  {ideas.map((s) => (
                    <option key={`stop:${s.id}`} value={`stop:${s.id}`}>
                      Idea · {s.text.slice(0, 60)}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
          )}
          <textarea
            rows={2}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={isGlobal ? 'Add a comment or question…' : `Comment on ${scope.label || scope.type}…`}
          />
          <div className="trip-comment-composer-foot">
            <button type="submit" className="trip-primary" disabled={saving || !body.trim()}>
              {saving ? 'Posting…' : 'Post comment'}
            </button>
          </div>
        </form>

        <div className="trip-comments-list">
          {scopedThreads.map((thread) => {
            const meta = targetMeta(thread);
            const replyOpen = replyOpenId === thread.id;
            return (
              <article key={thread.id} className={`trip-comment-thread${thread.resolved ? ' is-resolved' : ''}`}>
                <div className="trip-comment-thread-head">
                  {isGlobal ? (
                    <button
                      type="button"
                      className="trip-comment-target-link"
                      onClick={() => onJumpToTarget?.(thread, meta)}
                      title="Jump to item"
                    >
                      <span className="trip-tag">{meta.badge}</span>
                      <span>{meta.label}</span>
                    </button>
                  ) : (
                    <span className="trip-hint">
                      {thread.resolved
                        ? `Resolved${thread.resolved_by_label ? ` by ${thread.resolved_by_label}` : ''}`
                        : 'Open thread'}
                    </span>
                  )}
                  {canResolve(thread) && (
                    <button
                      type="button"
                      className={`trip-resolve-btn${thread.resolved ? ' is-resolved' : ''}`}
                      onClick={() => toggleResolve(thread)}
                    >
                      {thread.resolved ? 'Reopen' : '✓ Resolve'}
                    </button>
                  )}
                </div>

                {renderMessageRow(thread, false)}

                {thread.replies.length > 0 && (
                  <div className="trip-comment-replies">
                    {thread.replies.map((r) => renderMessageRow(r, true))}
                  </div>
                )}

                <div className="trip-comment-thread-foot">
                  {thread.resolved && isGlobal && (
                    <span className="trip-hint">
                      Resolved{thread.resolved_by_label ? ` by ${thread.resolved_by_label}` : ''}
                    </span>
                  )}
                  {!replyOpen ? (
                    <button type="button" className="trip-link-btn" onClick={() => setReplyOpenId(thread.id)}>
                      Reply{thread.replies.length ? ` (${thread.replies.length})` : ''}
                    </button>
                  ) : (
                    <form className="trip-comment-reply-form" onSubmit={(e) => postReply(e, thread.id)}>
                      <input
                        type="text"
                        value={replyDrafts[thread.id] || ''}
                        onChange={(e) => setReplyDrafts((d) => ({ ...d, [thread.id]: e.target.value }))}
                        placeholder="Write a reply…"
                        autoFocus
                      />
                      <button type="submit" className="trip-primary" disabled={saving || !(replyDrafts[thread.id] || '').trim()}>
                        Reply
                      </button>
                      <button type="button" onClick={() => setReplyOpenId(null)}>Cancel</button>
                    </form>
                  )}
                </div>
              </article>
            );
          })}
          {scopedThreads.length === 0 && (
            <p className="trip-empty">
              {statusFilter === 'open'
                ? 'No open comments here. Start a thread above!'
                : statusFilter === 'resolved'
                  ? 'No resolved threads yet.'
                  : 'No comments yet.'}
            </p>
          )}
        </div>
      </aside>
    </div>
  );
}

/* ---------- Public Read-Only Trip View (/app/trips/share/:token) ---------- */

function publicZonedEnd(dateStr, startTime, durationMinutes, depZone, arrZone) {
  if (!dateStr || !startTime || durationMinutes == null) return null;
  const startEpoch = zonedToEpoch(dateStr, startTime, depZone);
  if (startEpoch == null) return null;
  const end = epochToZoned(startEpoch + durationMinutes * 60000, arrZone);
  return { ...end, offset: dayDiff(dateStr, end.date) };
}

function resolvePublicZones(trip, days) {
  const tripZone = trip?.timezone || localZone();
  let zone = tripZone;
  const dayInfo = {};
  const stopInfo = {};
  for (const day of [...days].sort((a, b) => String(a.date).localeCompare(String(b.date)))) {
    const inherited = zone;
    if (day.timezone) zone = day.timezone;
    const start = zone;
    const zones = [zone];
    let overnight = false;
    const stops = [...(day.stops || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id));
    for (const stop of stops) {
      const own = stop.timezone || zone;
      const info = { inherited: zone, zone: own, arriveZone: own, arrive: null, afterOvernight: overnight };
      if (stop.kind === 'travel') {
        info.arriveZone = stop.arrive_timezone || own;
        const startTime = stop.start_time ? String(stop.start_time).slice(0, 5) : '';
        info.arrive = publicZonedEnd(day.date, startTime, stop.duration_minutes, own, info.arriveZone);
        overnight = overnight || (info.arrive?.offset || 0) > 0;
        zone = info.arriveZone;
      }
      for (const z of [own, info.arriveZone]) if (!zones.includes(z)) zones.push(z);
      stopInfo[stop.id] = info;
    }
    dayInfo[day.id] = { inherited, start, end: zone, zones };
  }
  return { tripZone, days: dayInfo, stops: stopInfo };
}

export function PublicTripView() {
  const { token } = useParams();
  const [trip, setTrip] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('schedule');
  const [scheduleView, setScheduleView] = useState('itinerary');
  const [previewStop, setPreviewStop] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    fetch(`${getApiBaseUrl()}/api/trips/public/${encodeURIComponent(token || '')}/`)
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(res.status === 404 ? 'This shared trip link is unavailable or has been disabled.' : `HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        if (!cancelled) setTrip(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const days = trip?.days || [];
  const legs = trip?.legs || [];
  const ideas = trip?.ideas || [];
  const lodgings = trip?.lodgings || [];
  const zones = useMemo(() => resolvePublicZones(trip, days), [trip, days]);

  if (loading) {
    return <div className="p-10 text-center text-stone-500">Loading shared trip…</div>;
  }

  if (error || !trip) {
    return (
      <div className="min-h-screen bg-[#f7f6f2] px-4 py-16 text-center text-[#202426]">
        <div className="mx-auto max-w-md rounded-xl border border-stone-200 bg-white p-8 shadow-sm">
          <h1 className="text-lg font-semibold">Shared trip unavailable</h1>
          <p className="mt-2 text-sm text-stone-600">{error || 'This link is no longer active.'}</p>
          <a href="/app/trips/" className="mt-4 inline-block text-sm font-medium text-[#2c5e74] underline">
            Open Trips app
          </a>
        </div>
      </div>
    );
  }

  const dateRange = [trip.start_date, trip.end_date].filter(Boolean).map(shortDayDate).join(' – ');

  return (
    <div className="min-h-screen bg-[#f7f6f2] text-[#202426]">
      <header className="sticky top-0 z-20 border-b border-stone-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3">
          <span className="text-sm font-semibold text-stone-800">Trips</span>
          <span className="trip-role-badge is-public">Shared read-only</span>
          {trip.owner_label && <span className="text-xs text-stone-500">by {trip.owner_label}</span>}
          <a href="/app/trips/" className="ml-auto text-xs font-medium text-[#2c5e74] hover:underline">
            My Trips →
          </a>
        </div>
      </header>

      <main className="trip-app mx-auto max-w-5xl px-4 py-6">
        <div className="trip-public-header">
          <h1>{trip.title}</h1>
          <p className="trip-subtitle">
            {[dateRange, days.length ? `${days.length} ${days.length === 1 ? 'day' : 'days'}` : ''].filter(Boolean).join(' · ')}
          </p>
          {trip.description && (
            <div className="trip-md trip-description">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{trip.description}</ReactMarkdown>
            </div>
          )}
        </div>

        <nav className="trip-workspaces" aria-label="Shared trip views">
          {[
            ['route', `Route${legs.length ? ` (${legs.length})` : ''}`],
            ['schedule', 'Schedule'],
            ['ideas', `Ideas${ideas.length ? ` (${ideas.length})` : ''}`],
            ['lodgings', `Lodgings${lodgings.length ? ` (${lodgings.length})` : ''}`],
          ].map(([id, label]) => (
            <button key={id} type="button" className={tab === id ? 'is-active' : ''} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>

        {tab === 'route' && (
          <section className="trip-public-section">
            {legs.length > 0 && (
              <div className="trip-leg-arc">
                {legs.map((leg, i) => {
                  const legDays = days.filter((d) => d.leg === leg.id);
                  return (
                    <div key={leg.id} className="trip-leg-card">
                      <div className="trip-leg-card-head">
                        <span className="trip-leg-index">{i + 1}</span>
                        <div>
                          <strong>{leg.name}</strong>
                          <span className="trip-hint">
                            {legDays.length} {legDays.length === 1 ? 'day' : 'days'}
                            {leg.location ? ` · ${leg.location}` : ''}
                          </span>
                        </div>
                      </div>
                      {leg.notes && <p className="trip-hint">{leg.notes}</p>}
                    </div>
                  );
                })}
              </div>
            )}
            <div className="trip-days">
              {days.map((day, idx) => (
                <div key={day.id} className="trip-day-card">
                  <div className="trip-day-head">
                    <strong>Day {idx + 1} · {shortDayDate(day.date)}{day.title ? ` — ${day.title}` : ''}</strong>
                    {day.lodging && <span className="trip-tag">Stay: {day.lodging.name}</span>}
                  </div>
                  {day.notes && (
                    <div className="trip-md trip-day-notes">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{day.notes}</ReactMarkdown>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {tab === 'schedule' && (
          <section className="trip-public-section">
            <div className="trip-schedule-top">
              <div className="trip-view-toggle" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={scheduleView === 'itinerary'}
                  className={scheduleView === 'itinerary' ? 'is-active' : ''}
                  onClick={() => setScheduleView('itinerary')}
                >
                  Itinerary
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={scheduleView === 'calendar'}
                  className={scheduleView === 'calendar' ? 'is-active' : ''}
                  onClick={() => setScheduleView('calendar')}
                >
                  Calendar
                </button>
              </div>
            </div>

            {scheduleView === 'calendar' ? (
              <TripCalendar
                days={days}
                legs={legs}
                zones={zones}
                onOpenStop={(stop) => setPreviewStop({ day: days.find((d) => d.id === stop.day), stop })}
              />
            ) : (
              <div className="trip-days">
                {days.map((day, idx) => (
                  <div key={day.id} className="trip-day-card">
                    <div className="trip-day-head">
                      <strong>Day {idx + 1} · {shortDayDate(day.date)}{day.title ? ` — ${day.title}` : ''}</strong>
                      {day.lodging && <span className="trip-tag">Stay: {day.lodging.name}</span>}
                    </div>
                    {day.notes && (
                      <div className="trip-md trip-day-notes">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{day.notes}</ReactMarkdown>
                      </div>
                    )}
                    <ul className="trip-stops">
                      {(day.stops || []).map((stop) => {
                        const info = zones.stops[stop.id];
                        const tzAbbr = info?.zone ? zoneAbbr(info.zone, zonedToEpoch(day.date, '12:00', info.zone)) : '';
                        return (
                          <li key={stop.id} className="trip-stop">
                            <div className="trip-stop-main">
                              <span className="trip-stop-text">
                                {stop.start_time && (
                                  <span className="trip-stop-time">
                                    {formatClock(stop.start_time)}{tzAbbr ? ` ${tzAbbr}` : ''} ·{' '}
                                  </span>
                                )}
                                {stop.text}
                              </span>
                              <div className="trip-stop-tags">
                                {stop.loc && <span className="trip-tag">{stop.loc}{stop.arrive_loc ? ` → ${stop.arrive_loc}` : ''}</span>}
                                {stop.cat && <span className="trip-tag">{stop.cat}</span>}
                              </div>
                              {stop.description && (
                                <div className="trip-md trip-stop-desc">
                                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{stop.description}</ReactMarkdown>
                                </div>
                              )}
                              {(stop.attachments || []).length > 0 && (
                                <div className="trip-stop-tags">
                                  {stop.attachments.map((att) => (
                                    <a key={att.id} href={att.file_url || att.url} target="_blank" rel="noreferrer" className="trip-tag">
                                      {att.title || att.address || att.kind} ↗
                                    </a>
                                  ))}
                                </div>
                              )}
                            </div>
                          </li>
                        );
                      })}
                      {(day.stops || []).length === 0 && <li className="trip-empty">No stops scheduled.</li>}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {tab === 'ideas' && (
          <section className="trip-public-section">
            <ul className="trip-stops">
              {ideas.map((idea) => (
                <li key={idea.id} className="trip-stop">
                  <div className="trip-stop-main">
                    <span className="trip-stop-text">{idea.text}</span>
                    <div className="trip-stop-tags">
                      {idea.loc && <span className="trip-tag">{idea.loc}</span>}
                      {idea.cat && <span className="trip-tag">{idea.cat}</span>}
                    </div>
                    {idea.description && (
                      <div className="trip-md trip-stop-desc">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{idea.description}</ReactMarkdown>
                      </div>
                    )}
                  </div>
                </li>
              ))}
              {ideas.length === 0 && <li className="trip-empty">No unscheduled ideas on this trip.</li>}
            </ul>
          </section>
        )}

        {tab === 'lodgings' && (
          <section className="trip-public-section">
            <ul className="trip-bookings-list">
              {lodgings.map((l) => (
                <li key={l.id} className="trip-booking-row">
                  <div className="trip-booking-main">
                    <div className="trip-booking-title">{l.name}</div>
                    {l.address && <p className="trip-hint">{l.address}</p>}
                    <div className="trip-stop-tags">
                      {l.check_in_time && <span className="trip-tag">Check-in {formatClock(l.check_in_time)}</span>}
                      {l.check_out_time && <span className="trip-tag">Check-out {formatClock(l.check_out_time)}</span>}
                      {l.url && <a href={l.url} target="_blank" rel="noreferrer" className="trip-tag">Website ↗</a>}
                      {l.maps_url && <a href={l.maps_url} target="_blank" rel="noreferrer" className="trip-tag">Maps ↗</a>}
                    </div>
                    {l.notes && <p className="trip-hint">{l.notes}</p>}
                  </div>
                </li>
              ))}
              {lodgings.length === 0 && <li className="trip-empty">No lodgings listed yet.</li>}
            </ul>
          </section>
        )}
      </main>

      {previewStop && (
        <div className="trip-modal-backdrop" onClick={() => setPreviewStop(null)}>
          <div className="trip-modal" onClick={(e) => e.stopPropagation()}>
            <div className="trip-modal-head">
              <h3>{previewStop.stop.text}</h3>
              <button type="button" onClick={() => setPreviewStop(null)}>Close</button>
            </div>
            <p className="trip-hint">
              {shortDayDate(previewStop.day?.date)}
              {previewStop.stop.start_time ? ` · ${formatClock(previewStop.stop.start_time)}` : ''}
              {previewStop.stop.loc ? ` · ${previewStop.stop.loc}` : ''}
            </p>
            {previewStop.stop.description && (
              <div className="trip-md">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{previewStop.stop.description}</ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
