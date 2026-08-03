import React, { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';

async function api(path, { token, method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json' };
  if (token) headers.Authorization = `Token ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(`/api/vacation/${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

export function VacationListApp() {
  const { token, isAuthenticated, openSocialLoginModal } = useAuth();
  const [lists, setLists] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [items, setItems] = useState([]);
  const [newListName, setNewListName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all'); // all | need | done | remaining

  const loadLists = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const data = await api('lists/', { token });
      setLists(Array.isArray(data) ? data : data.results || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  const loadItems = useCallback(async (listId) => {
    if (!token || !listId) return;
    try {
      const data = await api(`lists/${listId}/items/`, { token });
      setItems(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message);
    }
  }, [token]);

  useEffect(() => {
    if (isAuthenticated && token) loadLists();
    else setLoading(false);
  }, [isAuthenticated, token, loadLists]);

  useEffect(() => {
    if (selectedId) loadItems(selectedId);
    else setItems([]);
  }, [selectedId, loadItems]);

  const createList = async (e) => {
    e.preventDefault();
    if (!newListName.trim()) return;
    try {
      const created = await api('lists/', {
        token,
        method: 'POST',
        body: { name: newListName.trim() },
      });
      setNewListName('');
      await loadLists();
      setSelectedId(created.id);
    } catch (err) {
      setError(err.message);
    }
  };

  const toggleDone = async (listItem) => {
    try {
      await api(`list-items/${listItem.id}/`, {
        token,
        method: 'PATCH',
        body: { done: !listItem.done },
      });
      loadItems(selectedId);
    } catch (err) {
      setError(err.message);
    }
  };

  const visibleItems = items.filter((li) => {
    if (filter === 'need') return li.need;
    if (filter === 'done') return li.done;
    if (filter === 'remaining') return li.need && !li.done;
    return true;
  });

  if (!isAuthenticated) {
    return (
      <div className="vac-app">
        <p style={{ color: 'var(--text-muted)' }}>Sign in to manage packing lists.</p>
        <button type="button" className="editorial-button" onClick={() => openSocialLoginModal()}>
          Sign in
        </button>
      </div>
    );
  }

  return (
    <div className="vac-app">
      <div className="vac-layout">
        <aside className="vac-sidebar">
          <h3>Lists</h3>
          <form onSubmit={createList} className="vac-new-list">
            <input
              className="form-input"
              placeholder="New trip list…"
              value={newListName}
              onChange={(e) => setNewListName(e.target.value)}
            />
            <button type="submit" className="editorial-button" style={{ width: 'auto', marginTop: 0 }}>
              Add
            </button>
          </form>
          {loading ? (
            <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
          ) : (
            <ul className="vac-list-nav">
              {lists.map((list) => (
                <li key={list.id}>
                  <button
                    type="button"
                    className={selectedId === list.id ? 'active' : ''}
                    onClick={() => setSelectedId(list.id)}
                  >
                    {list.name}
                    <span>{list.item_count ?? ''}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <main className="vac-main">
          {error && <div className="error-message">{error}</div>}
          {!selectedId ? (
            <p style={{ color: 'var(--text-muted)' }}>Select or create a packing list.</p>
          ) : (
            <>
              <div className="vac-filters">
                {['all', 'remaining', 'done', 'need'].map((f) => (
                  <button
                    key={f}
                    type="button"
                    className={filter === f ? 'active' : ''}
                    onClick={() => setFilter(f)}
                  >
                    {f}
                  </button>
                ))}
              </div>
              <ul className="vac-items">
                {visibleItems.map((li) => (
                  <li key={li.id} className={li.done ? 'done' : ''}>
                    <label>
                      <input
                        type="checkbox"
                        checked={!!li.done}
                        onChange={() => toggleDone(li)}
                      />
                      <span>{li.item_detail?.name || li.item}</span>
                      {li.item_detail?.category_detail?.name && (
                        <em>{li.item_detail.category_detail.name}</em>
                      )}
                    </label>
                  </li>
                ))}
              </ul>
              {visibleItems.length === 0 && (
                <p style={{ color: 'var(--text-muted)' }}>
                  No items yet. Add catalog items and tags in admin, set initial tags on the list, then seed.
                </p>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
