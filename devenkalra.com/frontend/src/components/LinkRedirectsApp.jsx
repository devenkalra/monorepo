import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';

async function api(path, { token, method = 'GET', body } = {}) {
  if (!token) {
    throw new Error('Not signed in with an API token. Sign out and sign in again.');
  }
  const headers = { Accept: 'application/json', Authorization: `Token ${token}` };
  let payload;
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(`/api/link-redirects/${path}`, {
      method,
      headers,
      body: payload,
      credentials: 'omit',
    });
  } catch (err) {
    throw new Error(
      `Network error talking to /api/link-redirects/ (${err.message}). `
      + 'Hard-refresh the page; if it persists, sign out and back in.',
    );
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg = typeof detail === 'string'
      ? detail
      : (detail && JSON.stringify(detail)) || data.error || `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

export function LinkRedirectsApp() {
  const { token, isAuthenticated, user } = useAuth();
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');
  const [slug, setSlug] = useState('');
  const [title, setTitle] = useState('');
  const [targetUrl, setTargetUrl] = useState('');
  const [permanent, setPermanent] = useState(false);

  const isSuper = user?.role === 'superuser' || Boolean(user?.isStaff);

  const load = useCallback(async () => {
    if (!token) return;
    const out = await api('', { token });
    setItems(out.items || []);
  }, [token]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await load();
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    })();
    return () => { cancelled = true; };
  }, [load]);

  const create = async () => {
    if (!targetUrl.trim()) {
      setError('Target URL is required.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const created = await api('', {
        token,
        method: 'POST',
        body: {
          slug: slug.trim().toLowerCase() || undefined,
          title: title.trim() || undefined,
          target_url: targetUrl.trim(),
          permanent: permanent ? '1' : '0',
        },
      });
      setSlug('');
      setTitle('');
      setTargetUrl('');
      setPermanent(false);
      await load();
      const shortPath = created?.path || (created?.slug ? `/${created.slug}` : '');
      if (shortPath) {
        try {
          await navigator.clipboard.writeText(shortPath);
          setCopied(shortPath);
        } catch {
          setCopied(shortPath);
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const copyPath = async (path) => {
    try {
      await navigator.clipboard.writeText(path);
      setCopied(path);
    } catch {
      setCopied(path);
    }
  };

  const saveTarget = async (item, nextTarget) => {
    const target = (nextTarget || '').trim();
    if (!target || target === item.target_url) return;
    setBusy(true);
    setError('');
    try {
      await api(`${item.id}/`, { token, method: 'PATCH', body: { target_url: target } });
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (item) => {
    if (!window.confirm(`Delete /${item.slug}? Anyone with that link will get a 404.`)) return;
    setBusy(true);
    setError('');
    try {
      await api(`${item.id}/`, { token, method: 'DELETE' });
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (!isAuthenticated) {
    return <div className="contacts-banner contacts-banner--warn">Sign in as superuser to manage redirects.</div>;
  }
  if (!isSuper) {
    return <div className="contacts-banner contacts-banner--warn">Superuser access required.</div>;
  }

  return (
    <div className="contacts-mail-merge">
      <p className="email-muted">
        Create a short root link like <code>/rsvp</code> that forwards to a Google Form
        or any https URL. Prefer temporary (302) redirects unless you are sure the destination
        will never change. Links are host-relative so the same slug works on localhost and prod.
      </p>

      {error && <div className="contacts-banner contacts-banner--warn">{error}</div>}
      {copied && (
        <div className="contacts-banner contacts-banner--info">
          Copied: <a href={copied}>{copied}</a>
        </div>
      )}

      <section className="contacts-bulk-panel">
        <h2 style={{ margin: 0, fontSize: '1.1rem' }}>New redirect</h2>
        <div className="contacts-mail-limits" style={{ marginTop: '0.75rem' }}>
          <label className="contacts-field">
            Target URL
            <input
              value={targetUrl}
              disabled={busy}
              placeholder="https://forms.gle/…"
              onChange={(e) => setTargetUrl(e.target.value)}
            />
          </label>
          <label className="contacts-field">
            Slug (optional)
            <input
              value={slug}
              disabled={busy}
              placeholder="rsvp"
              onChange={(e) => setSlug(e.target.value)}
            />
          </label>
          <label className="contacts-field">
            Title (optional)
            <input
              value={title}
              disabled={busy}
              placeholder="Party RSVP"
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label className="contacts-field" style={{ flexDirection: 'row', alignItems: 'center', gap: '0.5rem' }}>
            <input
              type="checkbox"
              checked={permanent}
              disabled={busy}
              onChange={(e) => setPermanent(e.target.checked)}
            />
            Permanent (301)
          </label>
        </div>
        <button type="button" className="editorial-button asset-btn" disabled={busy || !targetUrl.trim()}
          onClick={create} style={{ marginTop: '0.75rem' }}>
          {busy ? 'Saving…' : 'Create & copy link'}
        </button>
      </section>

      <section className="contacts-bulk-panel" style={{ marginTop: '1rem' }}>
        <strong>Your redirects</strong>
        {!items.length ? (
          <p className="email-muted">No redirects yet.</p>
        ) : (
          <table className="contacts-table" style={{ marginTop: '0.75rem' }}>
            <thead>
              <tr>
                <th>Short URL</th>
                <th>Target</th>
                <th>Hits</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <a href={item.path} target="_blank" rel="noopener noreferrer">/{item.slug}</a>
                    {item.permanent && <span className="email-muted"> · 301</span>}
                    {!item.is_public && <span className="email-muted"> · private</span>}
                    {item.title ? <div className="email-muted">{item.title}</div> : null}
                  </td>
                  <td>
                    <input
                      className="contacts-input"
                      defaultValue={item.target_url}
                      disabled={busy}
                      style={{ minWidth: '16rem', width: '100%' }}
                      onBlur={(e) => saveTarget(item, e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.currentTarget.blur();
                        }
                      }}
                    />
                  </td>
                  <td>{item.hit_count}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button type="button" className="asset-btn-muted" disabled={busy}
                      onClick={() => copyPath(item.path || `/${item.slug}`)}>Copy</button>{' '}
                    <button type="button" className="asset-btn-muted" disabled={busy}
                      onClick={() => remove(item)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
