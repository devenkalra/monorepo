import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';

function formatBytes(n) {
  const v = Number(n) || 0;
  if (v < 1024) return `${v} B`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
  return `${(v / (1024 * 1024)).toFixed(1)} MB`;
}

async function api(path, { token, method = 'GET', body, form } = {}) {
  if (!token) {
    throw new Error('Not signed in with an API token. Sign out and sign in again.');
  }
  const headers = { Accept: 'application/json', Authorization: `Token ${token}` };
  let payload = body;
  if (form) {
    payload = form;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(`/api/link-media/${path}`, {
      method,
      headers,
      body: payload,
      credentials: 'omit',
    });
  } catch (err) {
    throw new Error(
      `Network error talking to /api/link-media/ (${err.message}). `
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

export function LinkMediaApp() {
  const { token, isAuthenticated, user } = useAuth();
  const [items, setItems] = useState([]);
  const [baseUrl, setBaseUrl] = useState('https://devenkalra.com/f/');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');
  const [slug, setSlug] = useState('');
  const [title, setTitle] = useState('');
  const [file, setFile] = useState(null);

  const isSuper = user?.role === 'superuser' || Boolean(user?.isStaff);

  const load = useCallback(async () => {
    if (!token) return;
    const out = await api('', { token });
    setItems(out.items || []);
    if (out.base_url) setBaseUrl(out.base_url);
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

  const upload = async () => {
    if (!file) {
      setError('Choose a file first.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      if (slug.trim()) form.append('slug', slug.trim().toLowerCase());
      if (title.trim()) form.append('title', title.trim());
      const created = await api('', { token, method: 'POST', form });
      setFile(null);
      setSlug('');
      setTitle('');
      await load();
      if (created?.url) {
        try {
          await navigator.clipboard.writeText(created.url);
          setCopied(created.url);
        } catch {
          setCopied(created.url);
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const copyUrl = async (url) => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(url);
    } catch {
      setCopied(url);
    }
  };

  const replaceFile = async (item, nextFile) => {
    if (!nextFile) return;
    setBusy(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', nextFile);
      await api(`${item.id}/`, { token, method: 'PATCH', form });
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (item) => {
    if (!window.confirm(`Delete /f/${item.slug}? Emails using this link will break.`)) return;
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
    return <div className="contacts-banner contacts-banner--warn">Sign in as superuser to manage link media.</div>;
  }
  if (!isSuper) {
    return <div className="contacts-banner contacts-banner--warn">Superuser access required.</div>;
  }

  return (
    <div className="contacts-mail-merge">
      <p className="email-muted">
        Upload a file, set a short slug, and use <code>{baseUrl}your-slug</code> in emails.
        Replacing the file keeps the same URL so old messages stay valid.
      </p>

      {error && <div className="contacts-banner contacts-banner--warn">{error}</div>}
      {copied && (
        <div className="contacts-banner contacts-banner--info">
          Copied: <a href={copied} target="_blank" rel="noopener noreferrer">{copied}</a>
        </div>
      )}

      <section className="contacts-bulk-panel">
        <h2 style={{ margin: 0, fontSize: '1.1rem' }}>Upload file</h2>
        <p className="email-muted">Choose a PDF/image/doc, optionally set a short slug, then upload.</p>
        <div className="contacts-mail-limits" style={{ marginTop: '0.75rem' }}>
          <label className="contacts-field">
            File
            <input type="file" disabled={busy} onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </label>
          <label className="contacts-field">
            Slug (optional)
            <input
              value={slug}
              disabled={busy}
              placeholder="ytf-flyer"
              onChange={(e) => setSlug(e.target.value)}
            />
          </label>
          <label className="contacts-field">
            Title (optional)
            <input
              value={title}
              disabled={busy}
              placeholder="Young Tinker flyer"
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
        </div>
        {file && <p className="email-muted">Selected: {file.name}</p>}
        <button type="button" className="editorial-button asset-btn" disabled={busy || !file}
          onClick={upload} style={{ marginTop: '0.75rem' }}>
          {busy ? 'Uploading…' : 'Upload & copy link'}
        </button>
      </section>

      <section className="contacts-bulk-panel" style={{ marginTop: '1rem' }}>
        <strong>Your links</strong>
        {!items.length ? (
          <p className="email-muted">No files yet.</p>
        ) : (
          <table className="contacts-table" style={{ marginTop: '0.75rem' }}>
            <thead>
              <tr>
                <th>Slug</th>
                <th>Title</th>
                <th>Size</th>
                <th>Hits</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <a href={item.path} target="_blank" rel="noopener noreferrer">/f/{item.slug}</a>
                    {!item.is_public && <span className="email-muted"> · private</span>}
                  </td>
                  <td>{item.title || item.filename}</td>
                  <td>{formatBytes(item.byte_size)}</td>
                  <td>{item.download_count}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button type="button" className="asset-btn-muted" disabled={busy}
                      onClick={() => copyUrl(item.url)}>Copy</button>{' '}
                    <label className="asset-btn-muted" style={{ display: 'inline-block', cursor: busy ? 'default' : 'pointer' }}>
                      Replace
                      <input
                        type="file"
                        hidden
                        disabled={busy}
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          e.target.value = '';
                          replaceFile(item, f);
                        }}
                      />
                    </label>{' '}
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
