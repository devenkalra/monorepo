import React, { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';

async function api(path, { token, method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json' };
  if (token) headers.Authorization = `Token ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(`/api/assets/${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

export function AssetManagerApp() {
  const { token, isAuthenticated, openSocialLoginModal } = useAuth();
  const [items, setItems] = useState([]);
  const [areas, setAreas] = useState([]);
  const [boxes, setBoxes] = useState([]);
  const [q, setQ] = useState('');
  const [areaFilter, setAreaFilter] = useState('');
  const [boxFilter, setBoxFilter] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState('');

  const loadMeta = useCallback(async () => {
    if (!token) return;
    const [a, b] = await Promise.all([
      api('areas/', { token }),
      api('boxes/', { token }),
    ]);
    setAreas(Array.isArray(a) ? a : a.results || []);
    setBoxes(Array.isArray(b) ? b : b.results || []);
  }, [token]);

  const loadItems = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (q) params.set('q', q);
      if (areaFilter) params.set('area', areaFilter);
      if (boxFilter) params.set('box', boxFilter);
      const data = await api(`items/?${params}`, { token });
      setItems(Array.isArray(data) ? data : data.results || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, q, areaFilter, boxFilter]);

  useEffect(() => {
    if (isAuthenticated && token) {
      loadMeta().catch((err) => setError(err.message));
      loadItems();
    } else {
      setLoading(false);
    }
  }, [isAuthenticated, token, loadMeta, loadItems]);

  const createItem = async (e) => {
    e.preventDefault();
    if (!newName.trim()) return;
    try {
      const body = { name: newName.trim() };
      if (boxFilter) body.box_id = Number(boxFilter);
      else if (areaFilter) body.area_id = Number(areaFilter);
      await api('items/', { token, method: 'POST', body });
      setNewName('');
      loadItems();
    } catch (err) {
      setError(err.message);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="asset-app">
        <p style={{ color: 'var(--text-muted)' }}>Sign in to browse your asset inventory.</p>
        <button type="button" className="editorial-button" onClick={() => openSocialLoginModal()}>
          Sign in
        </button>
      </div>
    );
  }

  return (
    <div className="asset-app">
      <form
        className="asset-toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          loadItems();
        }}
      >
        <input
          className="form-input"
          placeholder="Search items…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          className="form-input"
          value={areaFilter}
          onChange={(e) => {
            setAreaFilter(e.target.value);
            setBoxFilter('');
          }}
        >
          <option value="">All areas</option>
          {areas.map((a) => (
            <option key={a.id} value={a.id}>{a.full_path || a.name}</option>
          ))}
        </select>
        <select
          className="form-input"
          value={boxFilter}
          onChange={(e) => {
            setBoxFilter(e.target.value);
            if (e.target.value) setAreaFilter('');
          }}
        >
          <option value="">All boxes</option>
          {boxes.map((b) => (
            <option key={b.id} value={b.id}>{b.full_path || b.name}</option>
          ))}
        </select>
        <button type="submit" className="editorial-button" style={{ width: 'auto', marginTop: 0 }}>
          Search
        </button>
      </form>

      <form onSubmit={createItem} className="asset-toolbar">
        <input
          className="form-input"
          placeholder="Quick-add item name…"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <button type="submit" className="editorial-button" style={{ width: 'auto', marginTop: 0 }}>
          Add item
        </button>
      </form>

      {error && <div className="error-message">{error}</div>}
      {loading ? (
        <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
      ) : (
        <ul className="asset-items">
          {items.map((item) => (
            <li key={item.id}>
              <strong>{item.name}</strong>
              <span>{item.full_path}</span>
              {item.category_detail?.name && <em>{item.category_detail.name}</em>}
              {item.locator_code && <code>{item.locator_type}:{item.locator_code}</code>}
            </li>
          ))}
        </ul>
      )}
      {!loading && items.length === 0 && (
        <p style={{ color: 'var(--text-muted)' }}>
          No items found. Create areas/boxes/items in admin or quick-add above.
        </p>
      )}
    </div>
  );
}
