import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
  if (!res.ok) {
    const detail = data.detail
      || (typeof data === 'object' && Object.values(data).flat?.().join?.(' '))
      || `Request failed (${res.status})`;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return data;
}

function collectionPath(kind) {
  return kind === 'area' ? 'areas' : 'items';
}

async function uploadPhoto(kind, id, file, token, description = '') {
  const form = new FormData();
  form.append('image', file);
  if (description) form.append('description', description);
  const res = await fetch(`/api/assets/${collectionPath(kind)}/${id}/photos/`, {
    method: 'POST',
    headers: { Authorization: `Token ${token}`, Accept: 'application/json' },
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Upload failed (${res.status})`);
  return data;
}

async function deletePhoto(kind, id, photoId, token) {
  const res = await fetch(
    `/api/assets/${collectionPath(kind)}/${id}/photos/${photoId}/`,
    {
      method: 'DELETE',
      headers: { Authorization: `Token ${token}`, Accept: 'application/json' },
    }
  );
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Delete failed (${res.status})`);
  return data;
}

async function reorderPhotos(kind, id, photoIds, token) {
  return api(`${collectionPath(kind)}/${id}/reorder-photos/`, {
    token,
    method: 'POST',
    body: { photo_ids: photoIds },
  });
}

function moveIndex(list, from, to) {
  if (to < 0 || to >= list.length || from === to) return list;
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

const LOCATOR_TYPES = [
  { value: '', label: '— None —' },
  { value: 'LABEL', label: 'Label' },
  { value: 'QR', label: 'QR Code' },
  { value: 'EPC', label: 'EPC (RFID)' },
];

function asList(data) {
  return Array.isArray(data) ? data : data?.results || [];
}

function photoUrl(entity) {
  const img = entity?.photos?.[0]?.image;
  if (!img) return null;
  return img.startsWith('http') || img.startsWith('/') ? img : `/api/media/${img}`;
}

function truncate(name, max = 22) {
  if (!name) return '';
  return name.length > max ? `${name.slice(0, max - 1)}…` : name;
}

function areaCounts(entity) {
  return {
    containers: Number(entity?.descendant_container_count) || 0,
    items: Number(entity?.descendant_item_count) || 0,
  };
}

function formatCounts({ containers, items }, { compact = false } = {}) {
  if (compact) {
    return `${containers} ▤ · ${items} ▭`;
  }
  const cLabel = containers === 1 ? 'container' : 'containers';
  const iLabel = items === 1 ? 'item' : 'items';
  return `${containers} ${cLabel} · ${items} ${iLabel}`;
}

const ROOT = { type: 'root' };

function ContainerIcon() {
  return <span className="asset-glyph asset-glyph--area" aria-hidden>▤</span>;
}

function FileIcon() {
  return <span className="asset-glyph asset-glyph--file" aria-hidden>▭</span>;
}

function resolveAreaChain(startAreaId, areas) {
  const chain = [];
  let node = areas.find((a) => a.id === startAreaId);
  const seen = new Set();
  while (node && !seen.has(node.id)) {
    chain.push(node);
    seen.add(node.id);
    node = node.parent_area ? areas.find((a) => a.id === node.parent_area) : null;
  }
  return chain.reverse();
}

function buildContainmentTrail(kind, entity, areas) {
  const trail = [{ label: 'Inventory', loc: ROOT }];

  if (kind === 'area') {
    resolveAreaChain(entity.id, areas).forEach((a, idx, arr) => {
      const isLast = idx === arr.length - 1;
      trail.push({
        label: a.name,
        loc: isLast ? null : { type: 'area', id: a.id },
        current: isLast,
      });
    });
    return trail;
  }

  const areaId = entity.area ?? null;
  if (areaId != null) {
    resolveAreaChain(areaId, areas).forEach((a) => {
      trail.push({ label: a.name, loc: { type: 'area', id: a.id } });
    });
  }
  trail.push({ label: entity.name, loc: null, current: true });
  return trail;
}

function PhotoLightbox({ urls, index, onClose, onIndexChange }) {
  const hasMultiple = urls.length > 1;

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
      if (!hasMultiple) return;
      if (e.key === 'ArrowLeft') {
        onIndexChange((index - 1 + urls.length) % urls.length);
      }
      if (e.key === 'ArrowRight') {
        onIndexChange((index + 1) % urls.length);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [index, urls.length, hasMultiple, onClose, onIndexChange]);

  return (
    <div
      className="asset-lightbox"
      role="dialog"
      aria-modal="true"
      aria-label="Photo viewer"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
    >
      <button
        type="button"
        className="asset-lightbox-close"
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
        aria-label="Close"
      >
        ✕
      </button>
      {hasMultiple && (
        <button
          type="button"
          className="asset-lightbox-nav prev"
          aria-label="Previous photo"
          onClick={(e) => {
            e.stopPropagation();
            onIndexChange((index - 1 + urls.length) % urls.length);
          }}
        >
          ‹
        </button>
      )}
      <div
        className="asset-lightbox-stage"
        onClick={(e) => e.stopPropagation()}
      >
        <img src={urls[index]} alt="" />
      </div>
      {hasMultiple && (
        <button
          type="button"
          className="asset-lightbox-nav next"
          aria-label="Next photo"
          onClick={(e) => {
            e.stopPropagation();
            onIndexChange((index + 1) % urls.length);
          }}
        >
          ›
        </button>
      )}
      {hasMultiple && (
        <p className="asset-lightbox-count">
          {index + 1} / {urls.length}
        </p>
      )}
    </div>
  );
}

function DetailPanel({
  kind,
  entity,
  areas = [],
  onClose,
  onEdit,
  onMove,
  onDelete,
  onOpen,
  onNavigate,
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [photoIndex, setPhotoIndex] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const photos = entity.photos || [];
  const photoUrls = useMemo(
    () => photos.map((p) => photoUrl({ photos: [p] })).filter(Boolean),
    [photos]
  );
  const activeSrc = photoUrls[photoIndex] || null;
  const kindLabel = kind === 'item' ? 'Item' : 'Container';
  const containment = useMemo(
    () => buildContainmentTrail(kind, entity, areas),
    [kind, entity, areas]
  );

  useEffect(() => {
    setPhotoIndex(0);
    setLightboxOpen(false);
  }, [entity.id, kind]);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await onDelete();
    } catch (err) {
      setDeleting(false);
      setConfirmDelete(false);
      throw err;
    }
  };

  return (
    <>
    <div
      className="asset-detail-backdrop"
      role="presentation"
      onClick={lightboxOpen ? undefined : onClose}
    >
      <aside
        className="asset-detail-panel"
        role="dialog"
        aria-modal="true"
        aria-label={`${kindLabel} details`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="asset-detail-header">
          <div>
            <p className="asset-detail-kind">{kindLabel}</p>
            <h3>{entity.name}</h3>
          </div>
          <button type="button" className="asset-icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="asset-detail-body">
          <div className="asset-detail-location">
            <span className="asset-detail-location-label">Location</span>
            <nav className="asset-detail-crumbs" aria-label="Containment path">
              {containment.map((crumb, i) => (
                <React.Fragment key={`${crumb.label}-${i}`}>
                  {i > 0 && <span className="asset-crumb-sep">/</span>}
                  {crumb.loc && !crumb.current ? (
                    <button
                      type="button"
                      onClick={() => {
                        onNavigate?.(crumb.loc);
                        onClose();
                      }}
                    >
                      {crumb.label}
                    </button>
                  ) : (
                    <span className={crumb.current ? 'current' : ''}>{crumb.label}</span>
                  )}
                </React.Fragment>
              ))}
            </nav>
          </div>

          <div className="asset-detail-cover">
            {activeSrc ? (
              <>
                <img src={activeSrc} alt="" />
                <button
                  type="button"
                  className="asset-cover-fullscreen"
                  aria-label="View full screen"
                  onClick={() => setLightboxOpen(true)}
                >
                  Full screen
                </button>
              </>
            ) : (
              <span className="asset-tile-placeholder" aria-hidden>
                {kind === 'item' ? '▭' : '▤'}
              </span>
            )}
          </div>

          {photoUrls.length > 1 && (
            <div className="asset-detail-gallery" role="list">
              {photoUrls.map((src, idx) => (
                <button
                  key={`${src}-${idx}`}
                  type="button"
                  role="listitem"
                  className={`asset-gallery-thumb${idx === photoIndex ? ' active' : ''}`}
                  onClick={() => setPhotoIndex(idx)}
                  aria-label={`Show photo ${idx + 1}`}
                  aria-current={idx === photoIndex ? 'true' : undefined}
                >
                  <img src={src} alt="" />
                </button>
              ))}
            </div>
          )}

          {entity.description ? (
            <p className="asset-detail-description">{entity.description}</p>
          ) : (
            <p className="asset-muted">No description.</p>
          )}

          <dl className="asset-detail-meta">
            <div>
              <dt>Category</dt>
              <dd>{entity.category_detail?.name || '—'}</dd>
            </div>
            <div>
              <dt>Tags</dt>
              <dd>
                {(entity.tags_detail || []).length
                  ? entity.tags_detail.map((t) => t.name).join(', ')
                  : '—'}
              </dd>
            </div>
            <div>
              <dt>Locator</dt>
              <dd>
                {entity.locator_code
                  ? `${entity.locator_type || 'CODE'}: ${entity.locator_code}`
                  : '—'}
              </dd>
            </div>
          </dl>
        </div>

        <div className="asset-detail-footer">
          {confirmDelete ? (
            <div className="asset-detail-confirm" role="alertdialog" aria-label="Confirm delete">
              <p>
                {kind === 'area'
                  ? `Delete container “${entity.name}” and everything inside it? This cannot be undone.`
                  : `Delete item “${entity.name}”? This cannot be undone.`}
              </p>
              <div className="asset-detail-confirm-actions">
                <button
                  type="button"
                  className="asset-btn-muted"
                  disabled={deleting}
                  onClick={() => setConfirmDelete(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="asset-btn-danger"
                  disabled={deleting}
                  onClick={handleDelete}
                >
                  {deleting ? 'Deleting…' : `Yes, delete ${kindLabel.toLowerCase()}`}
                </button>
              </div>
            </div>
          ) : (
            <div className="asset-detail-actions">
              {kind === 'area' && (
                <button type="button" className="editorial-button asset-btn" onClick={onOpen}>
                  Open
                </button>
              )}
              <button type="button" className="editorial-button asset-btn" onClick={onEdit}>
                Edit
              </button>
              <button type="button" className="asset-btn-muted" onClick={onMove}>
                Move…
              </button>
              <button
                type="button"
                className="asset-btn-danger"
                onClick={() => setConfirmDelete(true)}
              >
                Delete
              </button>
            </div>
          )}
        </div>
      </aside>
    </div>

    {lightboxOpen && activeSrc && (
      <PhotoLightbox
        urls={photoUrls}
        index={photoIndex}
        onClose={() => setLightboxOpen(false)}
        onIndexChange={setPhotoIndex}
      />
    )}
    </>
  );
}

function NameModal({ title, initial = '', confirmLabel = 'Create', onClose, onSubmit }) {
  const [name, setName] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setLocalError('Name is required.');
      return;
    }
    setBusy(true);
    setLocalError('');
    try {
      await onSubmit(name.trim());
    } catch (err) {
      setLocalError(err.message || 'Could not save.');
      setBusy(false);
    }
  };

  return (
    <div className="asset-modal-backdrop" role="presentation" onClick={onClose}>
      <div className="asset-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="asset-modal-header">
          <h3>{title}</h3>
          <button type="button" className="asset-icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <form onSubmit={submit} className="asset-modal-body">
          <label className="asset-field">
            <span>Name</span>
            <input
              className="form-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </label>
          {localError && <div className="error-message">{localError}</div>}
          <div className="asset-modal-footer">
            <button type="button" className="asset-btn-muted" onClick={onClose} disabled={busy}>Cancel</button>
            <button type="submit" className="editorial-button asset-btn" disabled={busy}>
              {busy ? 'Saving…' : confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EditEntityModal({
  kind,
  entity,
  categories,
  tags,
  token,
  onClose,
  onSaved,
  onCreateCategory,
  onCreateTag,
}) {
  const [name, setName] = useState(entity.name || '');
  const [description, setDescription] = useState(entity.description || '');
  const [categoryId, setCategoryId] = useState(
    entity.category != null
      ? String(entity.category)
      : entity.category_detail?.id != null
        ? String(entity.category_detail.id)
        : ''
  );
  const [selectedTagIds, setSelectedTagIds] = useState(() => {
    const fromDetail = entity.tags_detail?.map((t) => t.id) || [];
    const fromIds = Array.isArray(entity.tags) ? entity.tags : [];
    return new Set(fromDetail.length ? fromDetail : fromIds);
  });
  const [locatorType, setLocatorType] = useState(entity.locator_type || '');
  const [locatorCode, setLocatorCode] = useState(entity.locator_code || '');
  const [photoSlots, setPhotoSlots] = useState(() =>
    (entity.photos || []).map((photo) => ({ type: 'existing', id: photo.id, photo }))
  );
  const [newCategoryName, setNewCategoryName] = useState('');
  const [newTagName, setNewTagName] = useState('');
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState('');

  const kindLabel = kind === 'item' ? 'item' : 'container';

  const toggleTag = (id) => {
    setSelectedTagIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const onPickFiles = (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length) {
      setPhotoSlots((prev) => [
        ...prev,
        ...files.map((file, i) => ({
          type: 'pending',
          key: `${Date.now()}-${i}-${file.name}`,
          file,
        })),
      ]);
    }
    e.target.value = '';
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setLocalError('Name is required.');
      return;
    }
    setBusy(true);
    setLocalError('');
    try {
      const body = {
        name: name.trim(),
        description: description.trim(),
        category_id: categoryId ? Number(categoryId) : null,
        tag_ids: [...selectedTagIds],
        locator_type: locatorType || '',
        locator_code: locatorCode.trim() || null,
      };
      const updated = await api(`${collectionPath(kind)}/${entity.id}/`, {
        token,
        method: 'PATCH',
        body,
      });

      const originalIds = new Set((entity.photos || []).map((p) => p.id));
      const keptExistingIds = new Set(
        photoSlots.filter((s) => s.type === 'existing').map((s) => s.id)
      );
      for (const photoId of originalIds) {
        if (!keptExistingIds.has(photoId)) {
          await deletePhoto(kind, entity.id, photoId, token);
        }
      }

      const finalIds = [];
      for (const slot of photoSlots) {
        if (slot.type === 'existing') finalIds.push(slot.id);
        else {
          const created = await uploadPhoto(kind, entity.id, slot.file, token);
          finalIds.push(created.id);
        }
      }
      if (finalIds.length > 0) {
        await reorderPhotos(kind, entity.id, finalIds, token);
      }

      const refreshed = await api(`${collectionPath(kind)}/${entity.id}/`, { token });
      await onSaved(refreshed || updated);
    } catch (err) {
      setLocalError(err.message || 'Could not save.');
      setBusy(false);
    }
  };

  return (
    <div className="asset-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="asset-modal asset-modal--wide"
        role="dialog"
        aria-modal="true"
        aria-label={`Edit ${kindLabel}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="asset-modal-header">
          <h3>Edit {kindLabel}</h3>
          <button type="button" className="asset-icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <form onSubmit={submit} className="asset-modal-body">
          <label className="asset-field">
            <span>Name</span>
            <input className="form-input" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </label>
          <label className="asset-field">
            <span>Description</span>
            <textarea
              className="form-input"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <label className="asset-field">
            <span>Category</span>
            <select className="form-input" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              <option value="">— None —</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </label>
          <div className="asset-inline-create">
            <input
              className="form-input"
              placeholder="New category…"
              value={newCategoryName}
              onChange={(e) => setNewCategoryName(e.target.value)}
            />
            <button
              type="button"
              className="asset-btn-muted"
              disabled={!newCategoryName.trim() || busy}
              onClick={async () => {
                try {
                  const created = await onCreateCategory(newCategoryName.trim());
                  setCategoryId(String(created.id));
                  setNewCategoryName('');
                } catch (err) {
                  setLocalError(err.message);
                }
              }}
            >
              Add
            </button>
          </div>
          <fieldset className="asset-tag-picker">
            <legend>Tags</legend>
            <div className="asset-tag-options">
              {tags.map((tag) => (
                <label key={tag.id} className="asset-tag-option">
                  <input
                    type="checkbox"
                    checked={selectedTagIds.has(tag.id)}
                    onChange={() => toggleTag(tag.id)}
                  />
                  {tag.name}
                </label>
              ))}
              {tags.length === 0 && <span className="asset-muted">No tags yet.</span>}
            </div>
            <div className="asset-inline-create">
              <input
                className="form-input"
                placeholder="New tag…"
                value={newTagName}
                onChange={(e) => setNewTagName(e.target.value)}
              />
              <button
                type="button"
                className="asset-btn-muted"
                disabled={!newTagName.trim() || busy}
                onClick={async () => {
                  try {
                    const created = await onCreateTag(newTagName.trim());
                    setSelectedTagIds((prev) => new Set(prev).add(created.id));
                    setNewTagName('');
                  } catch (err) {
                    setLocalError(err.message);
                  }
                }}
              >
                Add
              </button>
            </div>
          </fieldset>
          <div className="asset-locator-row">
            <label className="asset-field">
              <span>Locator type</span>
              <select className="form-input" value={locatorType} onChange={(e) => setLocatorType(e.target.value)}>
                {LOCATOR_TYPES.map((opt) => (
                  <option key={opt.value || 'none'} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </label>
            <label className="asset-field">
              <span>Locator code</span>
              <input className="form-input" value={locatorCode} onChange={(e) => setLocatorCode(e.target.value)} />
            </label>
          </div>

          <fieldset className="asset-photo-editor">
            <legend>Images</legend>
            <p className="asset-photo-hint">
              First image is the cover. Use arrows or “Make cover” to reorder.
            </p>
            <div className="asset-photo-grid">
              {photoSlots.map((slot, index) => {
                const src = slot.type === 'existing'
                  ? photoUrl({ photos: [slot.photo] })
                  : URL.createObjectURL(slot.file);
                const key = slot.type === 'existing' ? `ex-${slot.id}` : `p-${slot.key}`;
                return (
                  <div
                    key={key}
                    className={`asset-photo-thumb${index === 0 ? ' is-cover' : ''}${slot.type === 'pending' ? ' pending' : ''}`}
                  >
                    {src ? <img src={src} alt="" /> : <span className="asset-tile-placeholder">▭</span>}
                    {index === 0 && <span className="asset-photo-cover-badge">Cover</span>}
                    {slot.type === 'pending' && <span className="asset-photo-pending-label">New</span>}
                    <div className="asset-photo-controls">
                      <button
                        type="button"
                        className="asset-btn-muted"
                        disabled={index === 0}
                        aria-label="Move earlier"
                        onClick={() => setPhotoSlots((prev) => moveIndex(prev, index, index - 1))}
                      >
                        ←
                      </button>
                      <button
                        type="button"
                        className="asset-btn-muted"
                        disabled={index === photoSlots.length - 1}
                        aria-label="Move later"
                        onClick={() => setPhotoSlots((prev) => moveIndex(prev, index, index + 1))}
                      >
                        →
                      </button>
                      <button
                        type="button"
                        className="asset-btn-muted"
                        disabled={index === 0}
                        onClick={() => setPhotoSlots((prev) => moveIndex(prev, index, 0))}
                      >
                        Make cover
                      </button>
                      <button
                        type="button"
                        className="asset-btn-danger"
                        onClick={() => setPhotoSlots((prev) => prev.filter((_, i) => i !== index))}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
            <label className="asset-file-input">
              <span>Add images</span>
              <input type="file" accept="image/*" multiple onChange={onPickFiles} />
            </label>
          </fieldset>

          {localError && <div className="error-message">{localError}</div>}
          <div className="asset-modal-footer">
            <button type="button" className="asset-btn-muted" onClick={onClose} disabled={busy}>Cancel</button>
            <button type="submit" className="editorial-button asset-btn" disabled={busy}>
              {busy ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function MoveModal({ title, destinations, currentKey, onClose, onMove }) {
  const [dest, setDest] = useState('root');
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState('');

  const options = useMemo(
    () => destinations.filter((d) => d.key !== currentKey),
    [destinations, currentKey]
  );

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setLocalError('');
    try {
      const target = dest === 'root'
        ? ROOT
        : { type: 'area', id: Number(dest.slice(5)) };
      await onMove(target);
    } catch (err) {
      setLocalError(err.message || 'Could not move.');
      setBusy(false);
    }
  };

  return (
    <div className="asset-modal-backdrop" role="presentation" onClick={onClose}>
      <div className="asset-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="asset-modal-header">
          <h3>{title}</h3>
          <button type="button" className="asset-icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <form onSubmit={submit} className="asset-modal-body">
          <label className="asset-field">
            <span>Destination</span>
            <select className="form-input" value={dest} onChange={(e) => setDest(e.target.value)}>
              <option value="root">Inventory root</option>
              {options.map((d) => (
                <option key={d.key} value={d.key}>{d.label}</option>
              ))}
            </select>
          </label>
          {localError && <div className="error-message">{localError}</div>}
          <div className="asset-modal-footer">
            <button type="button" className="asset-btn-muted" onClick={onClose} disabled={busy}>Cancel</button>
            <button type="submit" className="editorial-button asset-btn" disabled={busy}>
              {busy ? 'Moving…' : 'Move'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function AssetManagerApp() {
  const { token, isAuthenticated, openSocialLoginModal } = useAuth();
  const [viewMode, setViewMode] = useState('list');
  const [location, setLocation] = useState(ROOT);
  const [folders, setFolders] = useState([]);
  const [items, setItems] = useState([]);
  const [allAreas, setAllAreas] = useState([]);
  const [categories, setCategories] = useState([]);
  const [tags, setTags] = useState([]);
  const [inventorySummary, setInventorySummary] = useState({
    container_count: 0,
    item_count: 0,
    unlocated_item_count: 0,
  });
  const [crumbs, setCrumbs] = useState([{ label: 'Inventory', loc: ROOT }]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState(null);
  const [createModal, setCreateModal] = useState(null);
  const [editModal, setEditModal] = useState(false);
  const [moveModal, setMoveModal] = useState(false);
  const [q, setQ] = useState('');

  const refreshMeta = useCallback(async () => {
    if (!token) return;
    const [a, c, t, summary] = await Promise.all([
      api('areas/', { token }),
      api('categories/', { token }),
      api('tags/', { token }),
      api('areas/summary/', { token }),
    ]);
    setAllAreas(asList(a));
    setCategories(asList(c));
    setTags(asList(t));
    setInventorySummary({
      container_count: Number(summary?.container_count) || 0,
      item_count: Number(summary?.item_count) || 0,
      unlocated_item_count: Number(summary?.unlocated_item_count) || 0,
    });
  }, [token]);

  const buildCrumbs = useCallback((loc, areas) => {
    if (loc.type === 'root') return [{ label: 'Inventory', loc: ROOT }];
    const trail = [{ label: 'Inventory', loc: ROOT }];
    const chain = [];
    let node = areas.find((a) => a.id === loc.id);
    const seen = new Set();
    while (node && !seen.has(node.id)) {
      chain.push(node);
      seen.add(node.id);
      node = node.parent_area ? areas.find((a) => a.id === node.parent_area) : null;
    }
    chain.reverse().forEach((a) => {
      trail.push({ label: a.name, loc: { type: 'area', id: a.id } });
    });
    return trail;
  }, []);

  const loadContents = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      let areaList = [];
      let itemList = [];

      if (location.type === 'root') {
        const [areas, itemsData] = await Promise.all([
          api('areas/?parent_area=null', { token }),
          api(q ? `items/?q=${encodeURIComponent(q)}` : 'items/?unlocated=1', { token }),
        ]);
        areaList = asList(areas);
        itemList = asList(itemsData);
      } else {
        const id = location.id;
        const [areas, itemsData] = await Promise.all([
          api(`areas/?parent_area=${id}`, { token }),
          api(
            q ? `items/?q=${encodeURIComponent(q)}&area=${id}` : `items/?area=${id}`,
            { token }
          ),
        ]);
        areaList = asList(areas);
        itemList = asList(itemsData);
      }

      const nextFolders = areaList
        .map((data) => ({ kind: 'area', data }))
        .sort((a, b) => a.data.name.localeCompare(b.data.name));
      const sortedItems = itemList.sort((a, b) => a.name.localeCompare(b.name));
      setFolders(nextFolders);
      setItems(sortedItems);
      setSelected((prev) => {
        if (!prev) return null;
        if (prev.kind === 'item') {
          const found = sortedItems.find((i) => i.id === prev.data.id);
          return found ? { kind: 'item', data: found } : null;
        }
        const found = nextFolders.find((f) => f.data.id === prev.data.id);
        return found || null;
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, location, q]);

  useEffect(() => {
    if (!isAuthenticated || !token) {
      setLoading(false);
      return;
    }
    refreshMeta().catch((err) => setError(err.message));
  }, [isAuthenticated, token, refreshMeta]);

  useEffect(() => {
    if (!isAuthenticated || !token) return;
    loadContents();
  }, [isAuthenticated, token, loadContents]);

  useEffect(() => {
    setCrumbs(buildCrumbs(location, allAreas));
  }, [location, allAreas, buildCrumbs]);

  const destinations = useMemo(
    () => allAreas
      .map((a) => ({
        key: `area:${a.id}`,
        label: a.full_path || a.name,
        loc: { type: 'area', id: a.id },
      }))
      .sort((a, b) => a.label.localeCompare(b.label)),
    [allAreas]
  );

  const openFolder = (folder) => {
    setQ('');
    setSelected(null);
    setLocation({ type: 'area', id: folder.data.id });
  };

  const goUp = () => {
    if (location.type !== 'area') return;
    const area = allAreas.find((a) => a.id === location.id);
    setQ('');
    setSelected(null);
    if (area?.parent_area) {
      setLocation({ type: 'area', id: area.parent_area });
    } else {
      setLocation(ROOT);
    }
  };

  const createContainer = async (name) => {
    await api('areas/', {
      token,
      method: 'POST',
      body: {
        name,
        parent_area_id: location.type === 'area' ? location.id : null,
      },
    });
    setCreateModal(null);
    setStatus(`Created container “${name}”.`);
    await refreshMeta();
    await loadContents();
  };

  const createItem = async (name) => {
    const body = { name };
    if (location.type === 'area') body.area_id = location.id;
    await api('items/', { token, method: 'POST', body });
    setCreateModal(null);
    setStatus(`Created item “${name}”.`);
    await refreshMeta();
    await loadContents();
  };

  const createCategory = async (name) => {
    const created = await api('categories/', { token, method: 'POST', body: { name } });
    setCategories((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
    return created;
  };

  const createTag = async (name) => {
    const created = await api('tags/', { token, method: 'POST', body: { name } });
    setTags((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
    return created;
  };

  const currentArea = useMemo(() => {
    if (location.type !== 'area') return null;
    return allAreas.find((a) => a.id === location.id) || null;
  }, [location, allAreas]);

  const locationCounts = useMemo(() => {
    if (location.type === 'root') {
      return {
        containers: inventorySummary.container_count,
        items: inventorySummary.item_count,
      };
    }
    if (!currentArea) return null;
    return areaCounts(currentArea);
  }, [location, currentArea, inventorySummary]);

  const isEditingCurrentArea = (entity) => (
    entity?.kind === 'area'
    && location.type === 'area'
    && entity.data.id === location.id
  );

  const onEditSaved = async (refreshed) => {
    setEditModal(false);
    setStatus(`Updated “${refreshed.name}”.`);
    setSelected((prev) => {
      if (!prev) return null;
      if (isEditingCurrentArea(prev)) return null;
      return { ...prev, data: refreshed };
    });
    await refreshMeta();
    await loadContents();
  };

  const deleteSelected = async () => {
    if (!selected) return;
    const label = selected.data.name;
    const path = selected.kind === 'area'
      ? `areas/${selected.data.id}/`
      : `items/${selected.data.id}/`;
    await api(path, { token, method: 'DELETE' });
    setStatus(`Deleted “${label}”.`);
    setSelected(null);
    await refreshMeta();
    await loadContents();
  };

  const moveSelected = async (target) => {
    if (!selected) return;
    if (selected.kind === 'area') {
      if (target.type === 'area' && target.id === selected.data.id) {
        throw new Error('Cannot move a container into itself.');
      }
      await api(`areas/${selected.data.id}/`, {
        token,
        method: 'PATCH',
        body: { parent_area_id: target.type === 'area' ? target.id : null },
      });
    } else {
      await api(`items/${selected.data.id}/`, {
        token,
        method: 'PATCH',
        body: { area_id: target.type === 'area' ? target.id : null },
      });
    }
    setMoveModal(false);
    setStatus(`Moved “${selected.data.name}”.`);
    setSelected(null);
    await refreshMeta();
    await loadContents();
  };

  const selectedKey = selected ? `${selected.kind}:${selected.data.id}` : null;

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
      <div className="asset-toolbar asset-toolbar--top">
        <div className="asset-view-toggle" role="group" aria-label="View mode">
          <button
            type="button"
            className={viewMode === 'list' ? 'active' : ''}
            onClick={() => setViewMode('list')}
          >
            List
          </button>
          <button
            type="button"
            className={viewMode === 'icons' ? 'active' : ''}
            onClick={() => setViewMode('icons')}
          >
            Icons
          </button>
        </div>
        <form
          className="asset-search"
          onSubmit={(e) => {
            e.preventDefault();
            loadContents();
          }}
        >
          <input
            className="form-input"
            placeholder="Search items here…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <button type="submit" className="asset-btn-muted">Search</button>
        </form>
      </div>

      <div className="asset-location-bar">
        <div className="asset-location-nav">
          {location.type !== 'root' && (
            <button
              type="button"
              className="asset-up-btn"
              onClick={goUp}
              aria-label="Go up one container"
            >
              ↑ Up
            </button>
          )}
          <nav className="asset-breadcrumbs" aria-label="Location">
            {crumbs.map((c, i) => {
              const isCurrent = i === crumbs.length - 1;
              return (
                <React.Fragment key={`${c.label}-${i}`}>
                  {i > 0 && <span className="asset-crumb-sep">/</span>}
                  <button
                    type="button"
                    className={isCurrent ? 'current' : ''}
                    disabled={isCurrent}
                    onClick={() => {
                      if (!c.loc || isCurrent) return;
                      setQ('');
                      setSelected(null);
                      setLocation(c.loc);
                    }}
                  >
                    {c.label}
                  </button>
                </React.Fragment>
              );
            })}
          </nav>
        </div>
        {locationCounts && (
          <p className="asset-location-counts" aria-live="polite">
            {formatCounts(locationCounts)}
          </p>
        )}
      </div>

      <div className="asset-actions">
        <button
          type="button"
          className="editorial-button asset-btn"
          onClick={() => setCreateModal('container')}
        >
          New container
        </button>
        <button
          type="button"
          className="editorial-button asset-btn"
          onClick={() => setCreateModal('item')}
        >
          New item
        </button>
        {currentArea && (
          <button
            type="button"
            className="asset-btn-muted"
            onClick={() => {
              setSelected({ kind: 'area', data: currentArea });
              setEditModal(true);
            }}
          >
            Edit container
          </button>
        )}
      </div>

      {status && <div className="asset-status">{status}</div>}
      {error && <div className="error-message">{error}</div>}

      {loading ? (
        <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
      ) : viewMode === 'list' ? (
        <div className="asset-browser-list" role="list">
          {folders.map((folder) => {
            const key = `area:${folder.data.id}`;
            const data = allAreas.find((a) => a.id === folder.data.id) || folder.data;
            const counts = areaCounts(data);
            return (
              <button
                key={key}
                type="button"
                role="listitem"
                className={`asset-row asset-row--folder${selectedKey === key ? ' selected' : ''}`}
                onClick={() => openFolder(folder)}
              >
                <ContainerIcon />
                <span className="asset-row-name">{folder.data.name}</span>
                <span className="asset-row-meta asset-row-counts" title={formatCounts(counts)}>
                  {formatCounts(counts, { compact: true })}
                </span>
              </button>
            );
          })}
          {items.map((item) => {
            const key = `item:${item.id}`;
            return (
              <button
                key={key}
                type="button"
                role="listitem"
                className={`asset-row asset-row--file${selectedKey === key ? ' selected' : ''}`}
                onClick={() => setSelected({ kind: 'item', data: item })}
              >
                <FileIcon />
                <span className="asset-row-name">{item.name}</span>
                <span className="asset-row-meta">{item.category_detail?.name || 'Item'}</span>
              </button>
            );
          })}
          {folders.length === 0 && items.length === 0 && (
            <p className="asset-empty">This container is empty.</p>
          )}
        </div>
      ) : (
        <div className="asset-icon-view">
          {items.length > 0 && (
            <section className="asset-icon-section">
              <h4>Items</h4>
              <div className="asset-icon-grid">
                {items.map((item) => {
                  const src = photoUrl(item);
                  const key = `item:${item.id}`;
                  return (
                    <button
                      key={key}
                      type="button"
                      className={`asset-tile${selectedKey === key ? ' selected' : ''}`}
                      onClick={() => setSelected({ kind: 'item', data: item })}
                      title={item.name}
                    >
                      <span className="asset-tile-media">
                        {src ? <img src={src} alt="" /> : <span className="asset-tile-placeholder" aria-hidden>▭</span>}
                      </span>
                      <span className="asset-tile-name">{truncate(item.name)}</span>
                    </button>
                  );
                })}
              </div>
            </section>
          )}
          {folders.length > 0 && (
            <section className="asset-icon-section">
              <h4>Containers</h4>
              <div className="asset-icon-grid">
                {folders.map((folder) => {
                  const data = allAreas.find((a) => a.id === folder.data.id) || folder.data;
                  const src = photoUrl(data);
                  const key = `area:${folder.data.id}`;
                  const counts = areaCounts(data);
                  return (
                    <button
                      key={key}
                      type="button"
                      className={`asset-tile asset-tile--folder${selectedKey === key ? ' selected' : ''}`}
                      onClick={() => openFolder(folder)}
                      title={`${folder.data.name} — ${formatCounts(counts)}`}
                    >
                      <span className="asset-tile-media">
                        {src ? <img src={src} alt="" /> : <span className="asset-tile-placeholder" aria-hidden>▤</span>}
                      </span>
                      <span className="asset-tile-name">{truncate(folder.data.name)}</span>
                      <span className="asset-tile-counts">{formatCounts(counts, { compact: true })}</span>
                    </button>
                  );
                })}
              </div>
            </section>
          )}
          {folders.length === 0 && items.length === 0 && (
            <p className="asset-empty">This container is empty.</p>
          )}
        </div>
      )}

      {selected && !editModal && !moveModal && (
        <DetailPanel
          kind={selected.kind}
          entity={selected.data}
          areas={allAreas}
          onClose={() => setSelected(null)}
          onEdit={() => setEditModal(true)}
          onMove={() => setMoveModal(true)}
          onDelete={deleteSelected}
          onNavigate={(loc) => {
            setQ('');
            setLocation(loc);
          }}
          onOpen={() => openFolder(selected)}
        />
      )}

      {createModal === 'container' && (
        <NameModal
          title="New container"
          onClose={() => setCreateModal(null)}
          onSubmit={createContainer}
        />
      )}
      {createModal === 'item' && (
        <NameModal title="New item" onClose={() => setCreateModal(null)} onSubmit={createItem} />
      )}
      {editModal && selected && (
        <EditEntityModal
          key={`${selected.kind}-${selected.data.id}`}
          kind={selected.kind}
          entity={selected.data}
          categories={categories}
          tags={tags}
          token={token}
          onClose={() => {
            setEditModal(false);
            if (isEditingCurrentArea(selected)) setSelected(null);
          }}
          onSaved={onEditSaved}
          onCreateCategory={createCategory}
          onCreateTag={createTag}
        />
      )}
      {moveModal && selected && (
        <MoveModal
          title={`Move “${selected.data.name}”`}
          destinations={destinations}
          currentKey={selectedKey}
          onClose={() => setMoveModal(false)}
          onMove={moveSelected}
        />
      )}
    </div>
  );
}
