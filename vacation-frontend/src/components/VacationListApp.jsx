import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { getApiBaseUrl } from '../utils/apiUrl';

async function api(path, { token, method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json' };
  const bearer = token || (typeof localStorage !== 'undefined' && localStorage.getItem('access_token'));
  if (bearer) headers.Authorization = `Bearer ${bearer}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${getApiBaseUrl()}/api/vacation/${path}`, {
    method,
    headers,
    credentials: 'include',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

function asList(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

function toggleId(set, id) {
  set((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
}

function CreateListModal({ lists, onClose, onCreate }) {
  const [name, setName] = useState('');
  const [populate, setPopulate] = useState('blank'); // blank | all_items | copy
  const [copyFromId, setCopyFromId] = useState(lists[0]?.id ? String(lists[0].id) : '');
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState('');

  useEffect(() => {
    if (!copyFromId && lists.length) setCopyFromId(String(lists[0].id));
  }, [lists, copyFromId]);

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setLocalError('Enter a list name.');
      return;
    }
    if (populate === 'copy' && !copyFromId) {
      setLocalError('Choose a list to copy.');
      return;
    }
    setBusy(true);
    setLocalError('');
    try {
      await onCreate({
        name: name.trim(),
        populate,
        copy_from_id: populate === 'copy' ? Number(copyFromId) : null,
      });
    } catch (err) {
      setLocalError(err.message || 'Could not create list.');
      setBusy(false);
    }
  };

  return (
    <div className="vac-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="vac-modal vac-modal--narrow"
        role="dialog"
        aria-modal="true"
        aria-label="Create list"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="vac-modal-header">
          <h3>New packing list</h3>
          <button type="button" className="vac-icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <form onSubmit={submit} className="vac-create-form">
          <label className="vac-field">
            <span>List name</span>
            <input
              className="form-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Patagonia 2027"
              autoFocus
            />
          </label>

          <fieldset className="vac-populate-options">
            <legend>Start with</legend>
            <label className="vac-radio">
              <input
                type="radio"
                name="populate"
                checked={populate === 'blank'}
                onChange={() => setPopulate('blank')}
              />
              <span>
                <strong>Blank</strong>
                <em>Empty list — add items later</em>
              </span>
            </label>
            <label className="vac-radio">
              <input
                type="radio"
                name="populate"
                checked={populate === 'all_items'}
                onChange={() => setPopulate('all_items')}
              />
              <span>
                <strong>All Master catalog items</strong>
                <em>Add every Vacation Item (need on, done off)</em>
              </span>
            </label>
            <label className="vac-radio">
              <input
                type="radio"
                name="populate"
                checked={populate === 'copy'}
                onChange={() => setPopulate('copy')}
                disabled={lists.length === 0}
              />
              <span>
                <strong>Copy an existing list</strong>
                <em>Copy items and need flags; done starts unchecked</em>
              </span>
            </label>
            {populate === 'copy' && (
              <select
                className="form-input"
                value={copyFromId}
                onChange={(e) => setCopyFromId(e.target.value)}
                disabled={lists.length === 0}
              >
                {lists.length === 0 ? (
                  <option value="">No lists to copy</option>
                ) : (
                  lists.map((list) => (
                    <option key={list.id} value={list.id}>
                      {list.name} ({list.item_count ?? 0})
                    </option>
                  ))
                )}
              </select>
            )}
          </fieldset>

          {localError && <div className="error-message">{localError}</div>}

          <div className="vac-modal-footer" style={{ borderTop: 'none', padding: '0.5rem 0 0' }}>
            <button type="button" className="vac-btn-muted" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button type="submit" className="editorial-button vac-btn" disabled={busy}>
              {busy ? 'Creating…' : 'Create list'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function TagChips({ tags }) {
  if (!tags?.length) return <span className="vac-muted">—</span>;
  return (
    <span className="vac-tag-chips">
      {tags.map((t) => (
        <span key={t.id} className="vac-tag-chip">{t.name}</span>
      ))}
    </span>
  );
}

function tagParam(selectedIds) {
  if (!selectedIds?.size) return '';
  return [...selectedIds].join(',');
}

function TagMultiFilter({ tags = [], selectedIds, onChange, label = 'Tags' }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const selected = selectedIds instanceof Set ? selectedIds : new Set(selectedIds || []);

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  let summary = 'All tags';
  if (selected.size === 1) {
    const id = [...selected][0];
    summary = tags.find((t) => t.id === id)?.name || '1 tag';
  } else if (selected.size > 1) {
    summary = `${selected.size} tags`;
  }

  return (
    <div className={`vac-msel${open ? ' open' : ''}`} ref={rootRef}>
      <button
        type="button"
        className="form-input vac-msel-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="vac-msel-summary">{summary}</span>
        <span className="vac-msel-caret" aria-hidden>▾</span>
      </button>
      {open && (
        <div className="vac-msel-menu" role="listbox" aria-multiselectable="true" aria-label={label}>
          {tags.length === 0 ? (
            <div className="vac-muted vac-msel-empty">No tags</div>
          ) : (
            tags.map((tag) => (
              <label
                key={tag.id}
                className="vac-msel-option"
                role="option"
                aria-selected={selected.has(tag.id)}
              >
                <input
                  type="checkbox"
                  checked={selected.has(tag.id)}
                  onChange={() => toggleId(onChange, tag.id)}
                />
                {tag.name}
              </label>
            ))
          )}
          {selected.size > 0 && (
            <button
              type="button"
              className="vac-btn-muted vac-msel-clear"
              onClick={() => onChange(new Set())}
            >
              Clear tags
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function CatalogItemModal({ categories, tags = [], onCreateTag, initial, onClose, onSave }) {
  const [name, setName] = useState(initial?.name || '');
  const [nameGroup, setNameGroup] = useState(initial?.name_group || '');
  const [description, setDescription] = useState(initial?.description || '');
  const [categoryId, setCategoryId] = useState(
    initial?.category != null
      ? String(initial.category)
      : initial?.category_detail?.id != null
        ? String(initial.category_detail.id)
        : ''
  );
  const [selectedTagIds, setSelectedTagIds] = useState(() => {
    const fromDetail = initial?.tags_detail?.map((t) => t.id) || [];
    const fromIds = Array.isArray(initial?.tags) ? initial.tags : [];
    return new Set(fromDetail.length ? fromDetail : fromIds);
  });
  const [newTagName, setNewTagName] = useState('');
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState('');
  const isEdit = Boolean(initial?.id);

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setLocalError('Name is required.');
      return;
    }
    setBusy(true);
    setLocalError('');
    try {
      await onSave({
        name: name.trim(),
        name_group: nameGroup.trim(),
        description: description.trim(),
        category_id: categoryId ? Number(categoryId) : null,
        tag_ids: [...selectedTagIds],
      });
    } catch (err) {
      setLocalError(err.message || 'Could not save item.');
      setBusy(false);
    }
  };

  const createTag = async () => {
    const trimmed = newTagName.trim();
    if (!trimmed || !onCreateTag) return;
    try {
      const tag = await onCreateTag(trimmed);
      setSelectedTagIds((prev) => new Set(prev).add(tag.id));
      setNewTagName('');
    } catch (err) {
      setLocalError(err.message || 'Could not create tag.');
    }
  };

  return (
    <div className="vac-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="vac-modal vac-modal--narrow"
        role="dialog"
        aria-modal="true"
        aria-label={isEdit ? 'Edit item' : 'Add item'}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="vac-modal-header">
          <h3>{isEdit ? 'Edit Vacation Item' : 'Add Vacation Item'}</h3>
          <button type="button" className="vac-icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <form onSubmit={submit} className="vac-create-form">
          <label className="vac-field">
            <span>Name</span>
            <input
              className="form-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </label>
          <label className="vac-field">
            <span>Group</span>
            <input
              className="form-input"
              value={nameGroup}
              onChange={(e) => setNameGroup(e.target.value)}
              placeholder="Optional grouping"
            />
          </label>
          <label className="vac-field">
            <span>Category</span>
            <select
              className="form-input"
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
            >
              <option value="">— None —</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </label>
          <fieldset className="vac-tag-picker">
            <legend>Tags</legend>
            <div className="vac-tag-options">
              {tags.map((tag) => (
                <label key={tag.id} className="vac-tag-option">
                  <input
                    type="checkbox"
                    checked={selectedTagIds.has(tag.id)}
                    onChange={() => toggleId(setSelectedTagIds, tag.id)}
                  />
                  {tag.name}
                </label>
              ))}
              {tags.length === 0 && <span className="vac-muted">No tags yet.</span>}
            </div>
            <div className="vac-toolbar" style={{ marginBottom: 0 }}>
              <input
                className="form-input"
                placeholder="New tag name…"
                value={newTagName}
                onChange={(e) => setNewTagName(e.target.value)}
              />
              <button
                type="button"
                className="vac-btn-muted"
                disabled={!newTagName.trim()}
                onClick={createTag}
              >
                Add tag
              </button>
            </div>
          </fieldset>
          <label className="vac-field">
            <span>Description</span>
            <textarea
              className="form-input"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          {localError && <div className="error-message">{localError}</div>}
          <div className="vac-modal-footer" style={{ borderTop: 'none', padding: '0.5rem 0 0' }}>
            <button type="button" className="vac-btn-muted" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button type="submit" className="editorial-button vac-btn" disabled={busy}>
              {busy ? 'Saving…' : isEdit ? 'Save' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function SortHeader({ label, field, sort, onSort }) {
  const active = sort.key === field;
  const arrow = active ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : '';
  return (
    <button
      type="button"
      className={`vac-sort-btn${active ? ' active' : ''}`}
      onClick={() => onSort(field)}
    >
      {label}
      {arrow}
    </button>
  );
}

function ItemPickerModal({
  token,
  categories,
  tags,
  excludeItemIds,
  onClose,
  onConfirm,
  title = 'Add items from catalog',
}) {
  const [catalog, setCatalog] = useState([]);
  const [q, setQ] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [tagIds, setTagIds] = useState(() => new Set());
  const [selected, setSelected] = useState(() => new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (q) params.set('q', q);
      if (categoryId) params.set('category', categoryId);
      const tagsParam = tagParam(tagIds);
      if (tagsParam) params.set('tag', tagsParam);
      const data = await api(`items/?${params}`, { token });
      setCatalog(asList(data));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, q, categoryId, tagIds]);

  useEffect(() => {
    load();
  }, [load]);

  const exclude = useMemo(() => new Set(excludeItemIds || []), [excludeItemIds]);
  const rows = catalog.filter((item) => !exclude.has(item.id));

  return (
    <div className="vac-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="vac-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="vac-modal-header">
          <h3>{title}</h3>
          <button type="button" className="vac-icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <div className="vac-toolbar">
          <input
            className="form-input"
            placeholder="Search name or tag…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select
            className="form-input"
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value)}
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <TagMultiFilter tags={tags} selectedIds={tagIds} onChange={setTagIds} />
          <button type="button" className="editorial-button vac-btn" onClick={load}>
            Search
          </button>
        </div>
        {error && <div className="error-message">{error}</div>}
        <div className="vac-modal-body">
          {loading ? (
            <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
          ) : (
            <table className="vac-table">
              <thead>
                <tr>
                  <th style={{ width: '2.5rem' }}>
                    <input
                      type="checkbox"
                      checked={rows.length > 0 && rows.every((r) => selected.has(r.id))}
                      onChange={(e) => {
                        if (e.target.checked) setSelected(new Set(rows.map((r) => r.id)));
                        else setSelected(new Set());
                      }}
                      aria-label="Select all visible"
                    />
                  </th>
                  <th>Name</th>
                  <th>Category</th>
                  <th>Tags</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.has(item.id)}
                        onChange={() => toggleId(setSelected, item.id)}
                        aria-label={`Select ${item.name}`}
                      />
                    </td>
                    <td>{item.name}</td>
                    <td>{item.category_detail?.name || '—'}</td>
                    <td><TagChips tags={item.tags_detail} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!loading && rows.length === 0 && (
            <p style={{ color: 'var(--text-muted)' }}>No matching catalog items.</p>
          )}
        </div>
        <div className="vac-modal-footer">
          <span className="vac-muted">{selected.size} selected</span>
          <button type="button" className="vac-btn-muted" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="editorial-button vac-btn"
            disabled={selected.size === 0}
            onClick={() => onConfirm([...selected])}
          >
            Add selected
          </button>
        </div>
      </div>
    </div>
  );
}

export function VacationListApp() {
  const { accessToken: token, isAuthenticated } = useAuth();
  const [tab, setTab] = useState('lists'); // lists | catalog
  const [lists, setLists] = useState([]);
  const [archivedLists, setArchivedLists] = useState([]);
  const [showArchived, setShowArchived] = useState(false);
  const [categories, setCategories] = useState([]);
  const [tags, setTags] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [listItems, setListItems] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [listsExpanded, setListsExpanded] = useState(true);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(true);

  // List view controls
  const [editMode, setEditMode] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all'); // all | remaining | done | need
  const [categoryFilter, setCategoryFilter] = useState('');
  const [tagFilter, setTagFilter] = useState(() => new Set());
  const [listQ, setListQ] = useState('');
  const [sort, setSort] = useState({ key: 'name', dir: 'asc' });
  const [selectedListItemIds, setSelectedListItemIds] = useState(() => new Set());
  const [showAddModal, setShowAddModal] = useState(false);

  // Catalog controls
  const [catalogQ, setCatalogQ] = useState('');
  const [catalogCategory, setCatalogCategory] = useState('');
  const [catalogTags, setCatalogTags] = useState(() => new Set());
  const [selectedCatalogIds, setSelectedCatalogIds] = useState(() => new Set());
  const [assignListId, setAssignListId] = useState('');
  const [itemEditor, setItemEditor] = useState(null); // null | { mode:'create' } | { mode:'edit', item }

  const loadLists = useCallback(async () => {
    if (!isAuthenticated) return;
    const data = await api('lists/', { token });
    setLists(asList(data));
  }, [isAuthenticated, token]);

  const loadArchivedLists = useCallback(async () => {
    if (!isAuthenticated) return;
    const data = await api('lists/?archived=1', { token });
    setArchivedLists(asList(data));
  }, [isAuthenticated, token]);

  const loadCategories = useCallback(async () => {
    if (!isAuthenticated) return;
    const data = await api('categories/', { token });
    setCategories(asList(data));
  }, [isAuthenticated, token]);

  const loadTags = useCallback(async () => {
    if (!isAuthenticated) return;
    const data = await api('tags/', { token });
    setTags(asList(data));
  }, [isAuthenticated, token]);

  const loadListItems = useCallback(async (listId) => {
    if (!isAuthenticated || !listId) return;
    const data = await api(`lists/${listId}/items/`, { token });
    setListItems(asList(data));
    setSelectedListItemIds(new Set());
  }, [isAuthenticated, token]);

  const loadCatalog = useCallback(async () => {
    if (!isAuthenticated) return;
    const params = new URLSearchParams();
    if (catalogQ) params.set('q', catalogQ);
    if (catalogCategory) params.set('category', catalogCategory);
    const tagsParam = tagParam(catalogTags);
    if (tagsParam) params.set('tag', tagsParam);
    const data = await api(`items/?${params}`, { token });
    setCatalog(asList(data));
  }, [isAuthenticated, token, catalogQ, catalogCategory, catalogTags]);

  useEffect(() => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    Promise.all([loadLists(), loadCategories(), loadTags()])
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [isAuthenticated, loadLists, loadCategories, loadTags]);

  useEffect(() => {
    if (selectedId) loadListItems(selectedId).catch((err) => setError(err.message));
    else setListItems([]);
  }, [selectedId, loadListItems]);

  useEffect(() => {
    if (tab === 'catalog') {
      loadCatalog().catch((err) => setError(err.message));
    }
  }, [tab, loadCatalog]);

  useEffect(() => {
    if (showArchived) {
      loadArchivedLists().catch((err) => setError(err.message));
    }
  }, [showArchived, loadArchivedLists]);

  useEffect(() => {
    setEditMode(false);
    setSelectedListItemIds(new Set());
    setShowAddModal(false);
    // On stacked layouts (phones incl. landscape), collapse lists once a list is open
    if (
      selectedId
      && typeof window !== 'undefined'
      && window.matchMedia('(max-width: 1024px)').matches
    ) {
      setListsExpanded(false);
    }
  }, [selectedId]);

  const selectedList =
    lists.find((l) => l.id === selectedId) ||
    archivedLists.find((l) => l.id === selectedId) ||
    null;

  const handleSort = (field) => {
    setSort((prev) =>
      prev.key === field
        ? { key: field, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key: field, dir: 'asc' }
    );
  };

  const displayedListItems = useMemo(() => {
    let rows = [...listItems];
    if (statusFilter === 'need') rows = rows.filter((li) => li.need);
    else if (statusFilter === 'done') rows = rows.filter((li) => li.done);
    else if (statusFilter === 'remaining') rows = rows.filter((li) => li.need && !li.done);

    if (categoryFilter) {
      const catId = Number(categoryFilter);
      rows = rows.filter((li) => li.item_detail?.category === catId || li.item_detail?.category_detail?.id === catId);
    }

    if (tagFilter.size > 0) {
      rows = rows.filter((li) =>
        (li.item_detail?.tags_detail || []).some((t) => tagFilter.has(t.id))
      );
    }

    if (listQ.trim()) {
      const needle = listQ.trim().toLowerCase();
      rows = rows.filter((li) => {
        const item = li.item_detail || {};
        const tagHit = (item.tags_detail || []).some((t) =>
          (t.name || '').toLowerCase().includes(needle)
        );
        return (
          (item.name || '').toLowerCase().includes(needle)
          || (item.name_group || '').toLowerCase().includes(needle)
          || (item.description || '').toLowerCase().includes(needle)
          || tagHit
        );
      });
    }

    const dir = sort.dir === 'asc' ? 1 : -1;
    rows.sort((a, b) => {
      const nameA = (a.item_detail?.name || '').toLowerCase();
      const nameB = (b.item_detail?.name || '').toLowerCase();
      const catA = (a.item_detail?.category_detail?.name || '').toLowerCase();
      const catB = (b.item_detail?.category_detail?.name || '').toLowerCase();
      switch (sort.key) {
        case 'done':
          return (Number(a.done) - Number(b.done)) * dir || nameA.localeCompare(nameB);
        case 'need':
          return (Number(a.need) - Number(b.need)) * dir || nameA.localeCompare(nameB);
        case 'category':
          return catA.localeCompare(catB) * dir || nameA.localeCompare(nameB);
        case 'name':
        default:
          return nameA.localeCompare(nameB) * dir;
      }
    });
    return rows;
  }, [listItems, statusFilter, categoryFilter, tagFilter, listQ, sort]);

  const createTag = async (name) => {
    const tag = await api('tags/', {
      token,
      method: 'POST',
      body: { name },
    });
    await loadTags();
    return tag;
  };

  const createList = async ({ name, populate, copy_from_id }) => {
    const body = { name, populate };
    if (populate === 'copy' && copy_from_id) body.copy_from_id = copy_from_id;
    const created = await api('lists/', {
      token,
      method: 'POST',
      body,
    });
    await loadLists();
    setSelectedId(created.id);
    setTab('lists');
    setShowCreateModal(false);
    const added = created.added ?? 0;
    const modeLabel =
      populate === 'all_items'
        ? `with ${added} master catalog item(s)`
        : populate === 'copy'
          ? `copied ${added} item(s)`
          : 'blank';
    setStatus(`Created list “${created.name}” (${modeLabel}).`);
  };

  const patchListItem = async (listItem, patch) => {
    try {
      await api(`list-items/${listItem.id}/`, {
        token,
        method: 'PATCH',
        body: patch,
      });
      await loadListItems(selectedId);
    } catch (err) {
      setError(err.message);
    }
  };

  const bulkListAction = async (payload) => {
    if (!selectedId || selectedListItemIds.size === 0) return;
    try {
      const result = await api(`lists/${selectedId}/bulk/`, {
        token,
        method: 'POST',
        body: { ids: [...selectedListItemIds], ...payload },
      });
      await loadListItems(selectedId);
      await loadLists();
      if (payload.remove) setStatus(`Removed ${result.removed || 0} item(s).`);
      else setStatus(`Updated ${result.updated || 0} item(s).`);
    } catch (err) {
      setError(err.message);
    }
  };

  const addItemsToList = async (listId, itemIds) => {
    if (!listId || !itemIds.length) return;
    try {
      const result = await api(`lists/${listId}/add-items/`, {
        token,
        method: 'POST',
        body: { item_ids: itemIds },
      });
      setStatus(`Added ${result.added} item(s)${result.skipped ? ` (${result.skipped} already on list)` : ''}.`);
      if (selectedId === listId) await loadListItems(listId);
      await loadLists();
      return result;
    } catch (err) {
      setError(err.message);
      return null;
    }
  };

  const assignCatalogToList = async () => {
    if (!assignListId || selectedCatalogIds.size === 0) return;
    const result = await addItemsToList(Number(assignListId), [...selectedCatalogIds]);
    if (result) setSelectedCatalogIds(new Set());
  };

  const onModalConfirm = async (itemIds) => {
    const result = await addItemsToList(selectedId, itemIds);
    if (result) setShowAddModal(false);
  };

  const saveCatalogItem = async (payload) => {
    if (itemEditor?.mode === 'edit' && itemEditor.item?.id) {
      await api(`items/${itemEditor.item.id}/`, {
        token,
        method: 'PATCH',
        body: payload,
      });
      setStatus(`Updated “${payload.name}”.`);
    } else {
      await api('items/', {
        token,
        method: 'POST',
        body: payload,
      });
      setStatus(`Created “${payload.name}”.`);
    }
    setItemEditor(null);
    await loadCatalog();
  };

  const deleteCatalogItem = async (item) => {
    if (!window.confirm(`Delete “${item.name}” from the catalog? It will also disappear from packing lists.`)) {
      return;
    }
    try {
      await api(`items/${item.id}/`, { token, method: 'DELETE' });
      setSelectedCatalogIds((prev) => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
      setStatus(`Deleted “${item.name}”.`);
      await loadCatalog();
      if (selectedId) await loadListItems(selectedId);
    } catch (err) {
      setError(err.message);
    }
  };

  const archiveSelectedList = async () => {
    if (!selectedId) return;
    if (!window.confirm(`Archive “${selectedList?.name}”? It will be hidden from the list picker.`)) {
      return;
    }
    try {
      await api(`lists/${selectedId}/archive/`, { token, method: 'POST' });
      setStatus(`Archived “${selectedList?.name}”.`);
      setSelectedId(null);
      setListsExpanded(true);
      await loadLists();
      if (showArchived) await loadArchivedLists();
    } catch (err) {
      setError(err.message);
    }
  };

  const unarchiveList = async (listId) => {
    try {
      const data = await api(`lists/${listId}/unarchive/`, { token, method: 'POST' });
      setStatus(`Unarchived “${data.name}”.`);
      await loadLists();
      await loadArchivedLists();
      setSelectedId(data.id);
    } catch (err) {
      setError(err.message);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="vac-app">
        <p style={{ color: 'var(--text-muted)' }}>Sign in to manage packing lists.</p>
      </div>
    );
  }

  return (
    <div className="vac-app">
      <div className="vac-tabs">
        <button
          type="button"
          className={tab === 'lists' ? 'active' : ''}
          onClick={() => setTab('lists')}
        >
          Lists
        </button>
        <button
          type="button"
          className={tab === 'catalog' ? 'active' : ''}
          onClick={() => setTab('catalog')}
        >
          Vacation Items
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}
      {status && <div className="vac-status">{status}</div>}

      {tab === 'catalog' ? (
        <div className="vac-catalog">
          <div className="vac-toolbar">
            <input
              className="form-input"
              placeholder="Search name or tag…"
              value={catalogQ}
              onChange={(e) => setCatalogQ(e.target.value)}
            />
            <select
              className="form-input"
              value={catalogCategory}
              onChange={(e) => setCatalogCategory(e.target.value)}
            >
              <option value="">All categories</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            <TagMultiFilter tags={tags} selectedIds={catalogTags} onChange={setCatalogTags} />
            <button type="button" className="editorial-button vac-btn" onClick={loadCatalog}>
              Search
            </button>
            <button
              type="button"
              className="editorial-button vac-btn"
              onClick={() => setItemEditor({ mode: 'create' })}
            >
              Add item…
            </button>
          </div>

          <div className="vac-toolbar vac-assign-bar">
            <span className="vac-muted">{selectedCatalogIds.size} selected</span>
            <select
              className="form-input"
              value={assignListId}
              onChange={(e) => setAssignListId(e.target.value)}
            >
              <option value="">Add to list…</option>
              {lists.map((list) => (
                <option key={list.id} value={list.id}>{list.name}</option>
              ))}
            </select>
            <button
              type="button"
              className="editorial-button vac-btn"
              disabled={!assignListId || selectedCatalogIds.size === 0}
              onClick={assignCatalogToList}
            >
              Add selected to list
            </button>
          </div>

          <table className="vac-table">
            <thead>
              <tr>
                <th style={{ width: '2.5rem' }}>
                  <input
                    type="checkbox"
                    checked={catalog.length > 0 && catalog.every((r) => selectedCatalogIds.has(r.id))}
                    onChange={(e) => {
                      if (e.target.checked) setSelectedCatalogIds(new Set(catalog.map((r) => r.id)));
                      else setSelectedCatalogIds(new Set());
                    }}
                    aria-label="Select all catalog items"
                  />
                </th>
                <th>Name</th>
                <th>Group</th>
                <th>Category</th>
                <th>Tags</th>
                <th style={{ width: '8rem' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {catalog.map((item) => (
                <tr key={item.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedCatalogIds.has(item.id)}
                      onChange={() => toggleId(setSelectedCatalogIds, item.id)}
                      aria-label={`Select ${item.name}`}
                    />
                  </td>
                  <td>{item.name}</td>
                  <td>{item.name_group || '—'}</td>
                  <td>{item.category_detail?.name || '—'}</td>
                  <td><TagChips tags={item.tags_detail} /></td>
                  <td className="vac-row-actions">
                    <button
                      type="button"
                      className="vac-btn-muted"
                      onClick={() => setItemEditor({ mode: 'edit', item })}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="vac-btn-danger"
                      onClick={() => deleteCatalogItem(item)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {catalog.length === 0 && (
            <p style={{ color: 'var(--text-muted)' }}>No catalog items found.</p>
          )}
        </div>
      ) : (
        <div className={`vac-layout${listsExpanded ? '' : ' sidebar-collapsed'}`}>
          <aside className="vac-sidebar">
            <div className="vac-sidebar-top">
              <h3>Lists</h3>
              <button
                type="button"
                className="vac-btn-muted vac-collapse-lists"
                onClick={() => setListsExpanded(false)}
                aria-label="Collapse lists"
                title="Collapse lists"
              >
                Hide
              </button>
            </div>
            <button
              type="button"
              className="editorial-button vac-btn vac-new-list-btn"
              onClick={() => setShowCreateModal(true)}
            >
              New list…
            </button>
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
            <div className="vac-archived-toggle">
              <button
                type="button"
                className="vac-btn-muted"
                onClick={() => setShowArchived((v) => !v)}
              >
                {showArchived ? 'Hide archived' : 'Show archived'}
              </button>
            </div>
            {showArchived && (
              <ul className="vac-list-nav vac-list-nav--archived">
                {archivedLists.length === 0 ? (
                  <li className="vac-muted" style={{ padding: '0.45rem 0.25rem' }}>No archived lists</li>
                ) : (
                  archivedLists.map((list) => (
                    <li key={list.id}>
                      <button
                        type="button"
                        className={selectedId === list.id ? 'active' : ''}
                        onClick={() => setSelectedId(list.id)}
                      >
                        {list.name}
                        <span>archived</span>
                      </button>
                    </li>
                  ))
                )}
              </ul>
            )}
          </aside>

          <main className="vac-main">
            {!selectedId ? (
              listsExpanded ? (
                <p style={{ color: 'var(--text-muted)' }}>Select or create a packing list.</p>
              ) : (
                <button
                  type="button"
                  className="vac-select-list-cta"
                  onClick={() => setListsExpanded(true)}
                >
                  Select a list
                </button>
              )
            ) : (
              <>
                <div className="vac-list-header">
                  <div className="vac-list-header-titles">
                    {!listsExpanded && (
                      <button
                        type="button"
                        className="vac-btn-muted vac-show-lists"
                        onClick={() => setListsExpanded(true)}
                      >
                        ← Lists
                      </button>
                    )}
                    <h2>
                      {selectedList?.name}
                      {selectedList?.is_archived ? (
                        <span className="vac-archived-badge">Archived</span>
                      ) : null}
                    </h2>
                  </div>
                  <div className="vac-list-header-actions">
                    {selectedList?.is_archived ? (
                      <button
                        type="button"
                        className="vac-btn-muted"
                        onClick={() => unarchiveList(selectedId)}
                      >
                        Unarchive
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="vac-btn-muted"
                        onClick={archiveSelectedList}
                      >
                        Archive
                      </button>
                    )}
                    {!selectedList?.is_archived && (
                      <button
                        type="button"
                        className={`vac-btn-muted${editMode ? ' active' : ''}`}
                        onClick={() => {
                          setEditMode((v) => !v);
                          setSelectedListItemIds(new Set());
                        }}
                      >
                        {editMode ? 'Done editing' : 'Edit list'}
                      </button>
                    )}
                  </div>
                </div>

                <div className="vac-toolbar">
                  <div className="vac-filters">
                    {['all', 'remaining', 'done', 'need'].map((f) => (
                      <button
                        key={f}
                        type="button"
                        className={statusFilter === f ? 'active' : ''}
                        onClick={() => setStatusFilter(f)}
                      >
                        {f}
                      </button>
                    ))}
                  </div>
                  <input
                    className="form-input"
                    placeholder="Search name or tag…"
                    value={listQ}
                    onChange={(e) => setListQ(e.target.value)}
                    aria-label="Search list items"
                  />
                  <select
                    className="form-input"
                    value={categoryFilter}
                    onChange={(e) => setCategoryFilter(e.target.value)}
                    aria-label="Filter by category"
                  >
                    <option value="">All categories</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                  <TagMultiFilter tags={tags} selectedIds={tagFilter} onChange={setTagFilter} />
                </div>

                {editMode && (
                  <div className="vac-toolbar vac-edit-actions">
                    <span className="vac-muted">{selectedListItemIds.size} selected</span>
                    <button
                      type="button"
                      className="vac-btn-muted"
                      disabled={selectedListItemIds.size === 0}
                      onClick={() => bulkListAction({ need: true })}
                    >
                      Mark need
                    </button>
                    <button
                      type="button"
                      className="vac-btn-muted"
                      disabled={selectedListItemIds.size === 0}
                      onClick={() => bulkListAction({ need: false })}
                    >
                      Mark not need
                    </button>
                    <button
                      type="button"
                      className="vac-btn-muted"
                      disabled={selectedListItemIds.size === 0}
                      onClick={() => bulkListAction({ done: true })}
                    >
                      Mark done
                    </button>
                    <button
                      type="button"
                      className="vac-btn-muted"
                      disabled={selectedListItemIds.size === 0}
                      onClick={() => bulkListAction({ done: false })}
                    >
                      Mark not done
                    </button>
                    <button
                      type="button"
                      className="vac-btn-danger"
                      disabled={selectedListItemIds.size === 0}
                      onClick={() => bulkListAction({ remove: true })}
                    >
                      Remove selected
                    </button>
                    <button
                      type="button"
                      className="editorial-button vac-btn"
                      onClick={() => setShowAddModal(true)}
                    >
                      Add items…
                    </button>
                  </div>
                )}

                <table className="vac-table">
                  <thead>
                    <tr>
                      {editMode && (
                        <th style={{ width: '2.5rem' }}>
                          <input
                            type="checkbox"
                            checked={
                              displayedListItems.length > 0 &&
                              displayedListItems.every((r) => selectedListItemIds.has(r.id))
                            }
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedListItemIds(new Set(displayedListItems.map((r) => r.id)));
                              } else {
                                setSelectedListItemIds(new Set());
                              }
                            }}
                            aria-label="Select all visible list items"
                          />
                        </th>
                      )}
                      <th>
                        <SortHeader label="Need" field="need" sort={sort} onSort={handleSort} />
                      </th>
                      <th>
                        <SortHeader label="Done" field="done" sort={sort} onSort={handleSort} />
                      </th>
                      <th>
                        <SortHeader label="Name" field="name" sort={sort} onSort={handleSort} />
                      </th>
                      <th>
                        <SortHeader label="Category" field="category" sort={sort} onSort={handleSort} />
                      </th>
                      <th>Tags</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayedListItems.map((li) => (
                      <tr key={li.id} className={li.done ? 'done' : ''}>
                        {editMode && (
                          <td>
                            <input
                              type="checkbox"
                              checked={selectedListItemIds.has(li.id)}
                              onChange={() => toggleId(setSelectedListItemIds, li.id)}
                              aria-label={`Select ${li.item_detail?.name || li.id}`}
                            />
                          </td>
                        )}
                        <td>
                          <input
                            type="checkbox"
                            checked={!!li.need}
                            onChange={() => patchListItem(li, { need: !li.need })}
                            aria-label="Need"
                          />
                        </td>
                        <td>
                          <input
                            type="checkbox"
                            checked={!!li.done}
                            onChange={() => patchListItem(li, { done: !li.done })}
                            aria-label="Done"
                          />
                        </td>
                        <td className="vac-name-cell">{li.item_detail?.name || li.item}</td>
                        <td>{li.item_detail?.category_detail?.name || '—'}</td>
                        <td><TagChips tags={li.item_detail?.tags_detail} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {displayedListItems.length === 0 && (
                  <p style={{ color: 'var(--text-muted)' }}>
                    No items match this filter.
                    {editMode ? ' Use “Add items…” to pull from the catalog.' : ' Switch to Edit list to add items.'}
                  </p>
                )}
              </>
            )}
          </main>
        </div>
      )}

      {showAddModal && selectedId && (
        <ItemPickerModal
          token={token}
          categories={categories}
          tags={tags}
          excludeItemIds={listItems.map((li) => li.item_detail?.id || li.item)}
          onClose={() => setShowAddModal(false)}
          onConfirm={onModalConfirm}
        />
      )}

      {showCreateModal && (
        <CreateListModal
          lists={lists}
          onClose={() => setShowCreateModal(false)}
          onCreate={createList}
        />
      )}

      {itemEditor && (
        <CatalogItemModal
          key={itemEditor.mode === 'edit' ? itemEditor.item.id : 'new'}
          categories={categories}
          tags={tags}
          onCreateTag={createTag}
          initial={itemEditor.mode === 'edit' ? itemEditor.item : null}
          onClose={() => setItemEditor(null)}
          onSave={saveCatalogItem}
        />
      )}
    </div>
  );
}
