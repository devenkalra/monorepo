import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { MarkdownBody } from './MarkdownBody';
import { NotesPageEditor } from './NotesPageEditor';
import './NotesApp.css';

function authHeaders(token, json = false) {
  const headers = {};
  if (token) headers.Authorization = `Token ${token}`;
  if (json) headers['Content-Type'] = 'application/json';
  return headers;
}

/** Token-only fetch — omit cookies so SessionAuthentication/CSRF cannot block POSTs. */
async function apiFetch(url, { token, json, method = 'GET', body } = {}) {
  const options = {
    method,
    headers: authHeaders(token, json || body !== undefined),
    credentials: 'omit',
  };
  if (body !== undefined) {
    options.body = typeof body === 'string' ? body : JSON.stringify(body);
  }
  return fetch(url, options);
}

function collectExpandedDefaults(nodes, depth = 0, into = new Set()) {
  for (const n of nodes || []) {
    if (n.is_folder && depth < 1) into.add(n.id);
    if (n.children?.length) collectExpandedDefaults(n.children, depth + 1, into);
  }
  return into;
}

/** Return path from root → matching node, or null. */
function findNodePath(nodes, predicate, path = []) {
  for (const n of nodes || []) {
    const next = [...path, n];
    if (predicate(n)) return next;
    if (n.children?.length) {
      const found = findNodePath(n.children, predicate, next);
      if (found) return found;
    }
  }
  return null;
}

function TreeNode({
  node,
  depth,
  expanded,
  selectedId,
  onToggle,
  onSelect,
  onDelete,
  canEdit,
}) {
  const isFolder = node.is_folder;
  const isOpen = expanded.has(node.id);
  const isSelected = selectedId === node.id;
  const pad = 0.55 + depth * 0.85;

  return (
    <li className="notes-tree-item">
      <div
        className={`notes-tree-row${isSelected ? ' is-selected' : ''}${isFolder ? ' is-folder' : ' is-page'}`}
        style={{ paddingLeft: `${pad}rem` }}
      >
        {isFolder ? (
          <button
            type="button"
            className="notes-tree-twist"
            aria-label={isOpen ? 'Collapse folder' : 'Expand folder'}
            onClick={() => onToggle(node.id)}
          >
            {isOpen ? '▾' : '▸'}
          </button>
        ) : (
          <span className="notes-tree-twist notes-tree-twist--leaf" aria-hidden="true">
            ·
          </span>
        )}
        <button
          type="button"
          className="notes-tree-label"
          onClick={() => onSelect(node)}
          title={node.page_slug ? `/${node.page_slug}` : 'Folder'}
        >
          <span className="notes-tree-icon" aria-hidden="true">
            {isFolder ? '📁' : '📄'}
          </span>
          <span className="notes-tree-title">{node.title}</span>
        </button>
        {canEdit && (
          <button
            type="button"
            className="notes-tree-delete"
            title="Remove from Notes"
            aria-label={`Remove ${node.title}`}
            onClick={(e) => {
              e.stopPropagation();
              onDelete(node);
            }}
          >
            ×
          </button>
        )}
      </div>
      {isFolder && isOpen && node.children?.length > 0 && (
        <ul className="notes-tree-list">
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              selectedId={selectedId}
              onToggle={onToggle}
              onSelect={onSelect}
              onDelete={onDelete}
              canEdit={canEdit}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function NotesApp() {
  const { token, isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const isSuperuser = user?.role === 'superuser';

  const urlNodeId = searchParams.get('node');
  const urlDoc = searchParams.get('doc');
  const urlCollapsed = searchParams.get('sidebar') === 'collapsed';
  const urlCreating = searchParams.get('new') === '1';
  const urlEditing = searchParams.get('edit') === '1';

  const [tree, setTree] = useState([]);
  const [expanded, setExpanded] = useState(() => new Set());
  const [sidebarOpen, setSidebarOpen] = useState(() => !urlCollapsed);
  const [selected, setSelected] = useState(null);
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [showAddFolder, setShowAddFolder] = useState(false);
  const [showLinkPage, setShowLinkPage] = useState(false);
  const [showCreatePage, setShowCreatePage] = useState(() => urlCreating);
  const [showEditPage, setShowEditPage] = useState(() => urlEditing && isSuperuser);
  const [folderTitle, setFolderTitle] = useState('');
  const [pageQuery, setPageQuery] = useState('');
  const [pageOptions, setPageOptions] = useState([]);
  const [targetParentId, setTargetParentId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [createError, setCreateError] = useState('');

  const writeNotesUrl = useCallback(
    ({
      node = undefined,
      sidebarCollapsed = undefined,
      creating = undefined,
      editing = undefined,
      replace = false,
    } = {}) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);

          if (node === null) {
            next.delete('node');
            next.delete('doc');
          } else if (node) {
            next.set('node', String(node.id));
            if (!node.is_folder && node.page_slug) {
              next.set('doc', node.page_slug);
            } else {
              next.delete('doc');
            }
          }

          const collapsed =
            sidebarCollapsed === undefined ? next.get('sidebar') === 'collapsed' : sidebarCollapsed;
          if (collapsed) next.set('sidebar', 'collapsed');
          else next.delete('sidebar');

          const isCreating = creating === undefined ? next.get('new') === '1' : creating;
          const isEditing = editing === undefined ? next.get('edit') === '1' : editing;
          // create and edit are mutually exclusive in the URL
          if (isCreating) {
            next.set('new', '1');
            next.delete('edit');
          } else if (isEditing) {
            next.set('edit', '1');
            next.delete('new');
          } else {
            next.delete('new');
            next.delete('edit');
          }

          return next;
        },
        { replace }
      );
    },
    [setSearchParams]
  );

  const loadTree = useCallback(async () => {
    setError('');
    try {
      const res = await apiFetch('/api/note-nodes/tree/');
      if (!res.ok) throw new Error('Failed to load Notes tree');
      const data = await res.json();
      setTree(Array.isArray(data) ? data : []);
      setExpanded((prev) => {
        if (prev.size > 0) return prev;
        return collectExpandedDefaults(data);
      });
    } catch (e) {
      setError(e.message || 'Failed to load Notes tree');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTree();
  }, [loadTree]);

  // Restore sidebar + editor modes from URL (back/forward / bookmarks)
  useEffect(() => {
    setSidebarOpen(!urlCollapsed);
    setShowCreatePage(urlCreating);
    setShowEditPage(isSuperuser && urlEditing && !urlCreating);
    if (!urlCreating && !urlEditing) setCreateError('');
  }, [urlCollapsed, urlCreating, urlEditing, isSuperuser]);

  // Restore selection from URL once the tree is available
  useEffect(() => {
    if (loading) return;

    let path = null;
    if (urlNodeId) {
      path = findNodePath(tree, (n) => String(n.id) === String(urlNodeId));
    }
    if (!path && urlDoc) {
      path = findNodePath(tree, (n) => n.page_slug === urlDoc);
    }

    if (path?.length) {
      const node = path[path.length - 1];
      setSelected((prev) => (prev?.id === node.id ? prev : node));
      setExpanded((prev) => {
        const next = new Set(prev);
        path.slice(0, -1).forEach((ancestor) => next.add(ancestor.id));
        if (node.is_folder) next.add(node.id);
        return next;
      });
      if (node.is_folder) setTargetParentId(node.id);
      return;
    }

    if (!urlNodeId && !urlDoc) {
      setSelected(null);
    }
  }, [tree, loading, urlNodeId, urlDoc]);

  useEffect(() => {
    if (!selected || selected.is_folder || !selected.page_slug) {
      setPreview(null);
      setPreviewError('');
      return;
    }

    let cancelled = false;
    (async () => {
      setPreviewLoading(true);
      setPreviewError('');
      try {
        const res = await apiFetch(`/api/pages/${selected.page_slug}/`, { token });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `Could not load page (${res.status})`);
        }
        const data = await res.json();
        if (!cancelled) setPreview(data);
      } catch (e) {
        if (!cancelled) {
          setPreview(null);
          setPreviewError(e.message || 'Preview failed');
        }
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selected, token]);

  const folderChoices = useMemo(() => {
    const out = [{ id: null, label: 'Notes (root)' }];
    const walk = (nodes, prefix = '') => {
      for (const n of nodes || []) {
        if (!n.is_folder) continue;
        out.push({ id: n.id, label: `${prefix}${n.title}` });
        if (n.children?.length) walk(n.children, `${prefix}${n.title} / `);
      }
    };
    walk(tree);
    return out;
  }, [tree]);

  /** Live children of the selected folder (from current tree, not stale selection). */
  const selectedFolderListing = useMemo(() => {
    if (!selected?.is_folder) return null;
    const path = findNodePath(tree, (n) => n.id === selected.id);
    const node = path?.[path.length - 1] || selected;
    const children = [...(node.children || [])].sort((a, b) => {
      if (a.is_folder !== b.is_folder) return a.is_folder ? -1 : 1;
      return (a.order - b.order) || a.title.localeCompare(b.title);
    });
    return {
      title: node.title || selected.title,
      folders: children.filter((c) => c.is_folder),
      pages: children.filter((c) => !c.is_folder),
    };
  }, [selected, tree]);

  const toggleExpand = (id) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const onSelect = (node) => {
    setSelected(node);
    setShowCreatePage(false);
    setShowEditPage(false);
    if (node.is_folder) {
      setExpanded((prev) => new Set(prev).add(node.id));
      setTargetParentId(node.id);
    }
    writeNotesUrl({ node, creating: false, editing: false, replace: false });
  };

  const collapseSidebar = () => {
    setSidebarOpen(false);
    writeNotesUrl({ sidebarCollapsed: true, replace: true });
  };

  const expandSidebar = () => {
    setSidebarOpen(true);
    writeNotesUrl({ sidebarCollapsed: false, replace: true });
  };

  const onDelete = async (node) => {
    if (!isAuthenticated) return;
    if (!token) {
      setError('Sign in again to edit Notes (missing auth token).');
      return;
    }
    const label = node.is_folder
      ? `Delete folder “${node.title}” and everything inside it?`
      : `Remove “${node.title}” from Notes? (Does not delete the page itself.)`;
    if (!window.confirm(label)) return;
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch(`/api/note-nodes/${node.id}/`, {
        method: 'DELETE',
        token,
      });
      if (!res.ok && res.status !== 204) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Delete failed (${res.status})`);
      }
      if (selected?.id === node.id) {
        setSelected(null);
        setPreview(null);
        writeNotesUrl({ node: null, creating: false, replace: true });
      }
      await loadTree();
    } catch (e) {
      setError(e.message || 'Delete failed');
    } finally {
      setBusy(false);
    }
  };

  const createFolder = async (e) => {
    e.preventDefault();
    if (!folderTitle.trim()) return;
    if (!token) {
      setError('Sign in again to edit Notes (missing auth token).');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch('/api/note-nodes/', {
        method: 'POST',
        token,
        body: {
          title: folderTitle.trim(),
          parent: targetParentId,
          page: null,
          order: 0,
        },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(
          body.parent?.[0] || body.title?.[0] || body.detail || `Could not create folder (${res.status})`
        );
      }
      setFolderTitle('');
      setShowAddFolder(false);
      await loadTree();
      if (targetParentId) setExpanded((prev) => new Set(prev).add(targetParentId));
    } catch (err) {
      setError(err.message || 'Could not create folder');
    } finally {
      setBusy(false);
    }
  };

  const searchPages = async (q) => {
    setPageQuery(q);
    if (!q.trim()) {
      setPageOptions([]);
      return;
    }
    try {
      const res = await apiFetch('/api/pages/', { token });
      if (!res.ok) return;
      const data = await res.json();
      const list = Array.isArray(data) ? data : data.results || [];
      const needle = q.trim().toLowerCase();
      setPageOptions(
        list
          .filter(
            (p) =>
              (p.title || '').toLowerCase().includes(needle) ||
              (p.slug || '').toLowerCase().includes(needle)
          )
          .slice(0, 12)
      );
    } catch {
      /* ignore */
    }
  };

  const parentLabel = useMemo(() => {
    const match = folderChoices.find((f) => f.id === targetParentId);
    return match?.label || 'Notes (root)';
  }, [folderChoices, targetParentId]);

  const openCreatePage = () => {
    setShowCreatePage(true);
    setShowEditPage(false);
    setShowLinkPage(false);
    setShowAddFolder(false);
    setCreateError('');
    setError('');
    writeNotesUrl({ creating: true, editing: false, replace: false });
  };

  const openEditPage = () => {
    if (!isSuperuser || !preview || !selected || selected.is_folder) return;
    setShowEditPage(true);
    setShowCreatePage(false);
    setShowLinkPage(false);
    setShowAddFolder(false);
    setCreateError('');
    setError('');
    writeNotesUrl({ editing: true, creating: false, replace: false });
  };

  const closePageEditor = ({ replace = true } = {}) => {
    setShowCreatePage(false);
    setShowEditPage(false);
    setCreateError('');
    writeNotesUrl({ creating: false, editing: false, replace });
  };

  const createNewPage = async (payload) => {
    if (!token) {
      setCreateError('Sign in again to create pages (missing auth token).');
      return;
    }
    setBusy(true);
    setCreateError('');
    setError('');
    try {
      const pageRes = await apiFetch('/api/pages/', {
        method: 'POST',
        token,
        body: payload,
      });
      if (!pageRes.ok) {
        const body = await pageRes.json().catch(() => ({}));
        const msg =
          body.slug?.[0] ||
          body.title?.[0] ||
          body.content?.[0] ||
          body.detail ||
          `Could not create page (${pageRes.status})`;
        throw new Error(typeof msg === 'string' ? msg : JSON.stringify(body));
      }
      const page = await pageRes.json();

      const nodeRes = await apiFetch('/api/note-nodes/', {
        method: 'POST',
        token,
        body: {
          title: page.title,
          parent: targetParentId,
          page: page.id,
          order: 0,
        },
      });
      if (!nodeRes.ok) {
        const body = await nodeRes.json().catch(() => ({}));
        throw new Error(
          body.detail ||
            body.page?.[0] ||
            `Page created, but failed to add it to Notes (${nodeRes.status})`
        );
      }
      const created = await nodeRes.json();
      setShowCreatePage(false);
      setShowEditPage(false);
      await loadTree();
      if (targetParentId) setExpanded((prev) => new Set(prev).add(targetParentId));
      const selectedNode = {
        ...created,
        is_folder: false,
        page_slug: page.slug,
        page_title: page.title,
      };
      setSelected(selectedNode);
      setPreview(page);
      writeNotesUrl({ node: selectedNode, creating: false, editing: false, replace: true });
    } catch (err) {
      setCreateError(err.message || 'Could not create page');
    } finally {
      setBusy(false);
    }
  };

  const saveEditedPage = async (payload, { close = true } = {}) => {
    if (!token) {
      setCreateError('Sign in again to edit pages (missing auth token).');
      return false;
    }
    if (!selected?.page_slug || !preview) {
      setCreateError('No page selected to edit.');
      return false;
    }
    const originalSlug = preview.slug || selected.page_slug;
    if (close) setBusy(true);
    setCreateError('');
    setError('');
    try {
      const pageRes = await apiFetch(`/api/pages/${originalSlug}/`, {
        method: 'PATCH',
        token,
        body: payload,
      });
      if (!pageRes.ok) {
        const body = await pageRes.json().catch(() => ({}));
        const msg =
          body.slug?.[0] ||
          body.title?.[0] ||
          body.content?.[0] ||
          body.detail ||
          `Could not update page (${pageRes.status})`;
        throw new Error(typeof msg === 'string' ? msg : JSON.stringify(body));
      }
      const page = await pageRes.json();

      // Keep the Notes tree label in sync with the page title
      if (selected.id != null && payload.title && payload.title !== selected.title) {
        await apiFetch(`/api/note-nodes/${selected.id}/`, {
          method: 'PATCH',
          token,
          body: { title: page.title },
        });
      }

      const selectedNode = {
        ...selected,
        title: page.title,
        page_slug: page.slug,
        page_title: page.title,
        is_folder: false,
      };
      setSelected(selectedNode);
      setPreview(page);

      if (close) {
        setShowEditPage(false);
        await loadTree();
        writeNotesUrl({ node: selectedNode, creating: false, editing: false, replace: true });
      } else if (payload.title && payload.title !== selected.title) {
        await loadTree();
        writeNotesUrl({ node: selectedNode, creating: false, editing: true, replace: true });
      } else if (page.slug !== originalSlug) {
        writeNotesUrl({ node: selectedNode, creating: false, editing: true, replace: true });
      }
      return true;
    } catch (err) {
      setCreateError(err.message || 'Could not update page');
      return false;
    } finally {
      if (close) setBusy(false);
    }
  };

  const addPageLink = async (page) => {
    if (!page) return;
    if (!token) {
      setError('Sign in again to edit Notes (missing auth token).');
      return;
    }
    if (page.id == null) {
      setError('Selected page is missing an id.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch('/api/note-nodes/', {
        method: 'POST',
        token,
        body: {
          title: page.title,
          parent: targetParentId,
          page: page.id,
          order: 0,
        },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const msg =
          body.detail ||
          body.page?.[0] ||
          body.parent?.[0] ||
          body.non_field_errors?.[0] ||
          `Could not add page (${res.status})`;
        throw new Error(typeof msg === 'string' ? msg : JSON.stringify(body));
      }
      const created = await res.json();
      setShowLinkPage(false);
      setPageQuery('');
      setPageOptions([]);
      await loadTree();
      if (targetParentId) setExpanded((prev) => new Set(prev).add(targetParentId));
      const selectedNode = {
        ...created,
        is_folder: false,
        page_slug: page.slug,
        page_title: page.title,
      };
      setSelected(selectedNode);
      writeNotesUrl({ node: selectedNode, creating: false, replace: false });
    } catch (err) {
      setError(err.message || 'Could not add page');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={`notes-app${sidebarOpen ? '' : ' notes-app--sidebar-collapsed'}`}>
      <aside className="notes-sidebar" aria-label="Notes folders and pages">
        <div className="notes-sidebar-header">
          <div className="notes-sidebar-heading">
            <span className="notes-sidebar-kicker">Notebook</span>
            <strong>Notes</strong>
          </div>
          <button
            type="button"
            className="notes-icon-btn"
            onClick={collapseSidebar}
            title="Collapse panel"
            aria-label="Collapse folder panel"
          >
            «
          </button>
        </div>

        {isAuthenticated && (
          <div className="notes-toolbar">
            <label className="notes-parent-picker">
              <span>Add under</span>
              <select
                value={targetParentId ?? ''}
                onChange={(e) =>
                  setTargetParentId(e.target.value === '' ? null : Number(e.target.value))
                }
              >
                {folderChoices.map((f) => (
                  <option key={f.id ?? 'root'} value={f.id ?? ''}>
                    {f.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="notes-toolbar-actions">
              <button
                type="button"
                className="notes-btn"
                disabled={busy}
                onClick={() => {
                  setShowAddFolder((v) => !v);
                  setShowLinkPage(false);
                  setShowCreatePage(false);
                  setShowEditPage(false);
                  writeNotesUrl({ creating: false, editing: false, replace: true });
                }}
              >
                New folder
              </button>
              <button
                type="button"
                className="notes-btn notes-btn--primary"
                disabled={busy}
                onClick={openCreatePage}
              >
                New page
              </button>
              <button
                type="button"
                className="notes-btn"
                disabled={busy}
                onClick={() => {
                  setShowLinkPage((v) => !v);
                  setShowAddFolder(false);
                  setShowCreatePage(false);
                  setShowEditPage(false);
                  writeNotesUrl({ creating: false, editing: false, replace: true });
                }}
              >
                Link page
              </button>
            </div>
          </div>
        )}

        {error && <p className="notes-error notes-error--toolbar">{error}</p>}

        {showAddFolder && (
          <form className="notes-inline-form" onSubmit={createFolder}>
            <input
              type="text"
              value={folderTitle}
              onChange={(e) => setFolderTitle(e.target.value)}
              placeholder="Folder name"
              autoFocus
            />
            <button type="submit" className="notes-btn notes-btn--primary" disabled={busy || !folderTitle.trim()}>
              Create
            </button>
          </form>
        )}

        {showLinkPage && (
          <div className="notes-inline-form notes-add-page">
            <input
              type="search"
              value={pageQuery}
              onChange={(e) => searchPages(e.target.value)}
              placeholder="Search pages by title or slug…"
              autoFocus
            />
            {pageOptions.length > 0 && (
              <ul className="notes-page-results">
                {pageOptions.map((p) => (
                  <li key={p.id}>
                    <button type="button" onClick={() => addPageLink(p)} disabled={busy}>
                      <strong>{p.title}</strong>
                      <span>{p.slug}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="notes-tree-scroll">
          {loading && <p className="notes-muted">Loading…</p>}
          {error && <p className="notes-error">{error}</p>}
          {!loading && !tree.length && (
            <p className="notes-muted">
              No folders or pages yet.
              {isAuthenticated
                ? ' Create a folder or add an existing page.'
                : ' Sign in to organize selected pages here.'}
            </p>
          )}
          {!loading && tree.length > 0 && (
            <ul className="notes-tree-list notes-tree-root">
              {tree.map((node) => (
                <TreeNode
                  key={node.id}
                  node={node}
                  depth={0}
                  expanded={expanded}
                  selectedId={selected?.id}
                  onToggle={toggleExpand}
                  onSelect={onSelect}
                  onDelete={onDelete}
                  canEdit={isAuthenticated}
                />
              ))}
            </ul>
          )}
        </div>
      </aside>

      {!sidebarOpen && (
        <button
          type="button"
          className="notes-sidebar-reopen"
          onClick={expandSidebar}
          title="Show folders"
          aria-label="Expand folder panel"
        >
          »
        </button>
      )}

      <div
        className={`notes-preview${
          showCreatePage || (showEditPage && preview) ? ' notes-preview--editing' : ''
        }`}
        aria-live="polite"
      >
        {showCreatePage || (showEditPage && preview) ? (
          <NotesPageEditor
            mode={showEditPage ? 'edit' : 'create'}
            initialValues={showEditPage ? preview : null}
            parentLabel={parentLabel}
            busy={busy}
            error={createError}
            navigate={navigate}
            onCancel={() => closePageEditor({ replace: true })}
            onSave={showEditPage ? saveEditedPage : createNewPage}
          />
        ) : (
          <>
            {!selected && (
              <div className="notes-preview-empty">
                <h2>Select a page</h2>
                <p>Choose a page from the left panel to preview its content here.</p>
              </div>
            )}
            {selected?.is_folder && selectedFolderListing && (
              <div className="notes-folder-view">
                <header className="notes-preview-header">
                  <div>
                    <h2>{selectedFolderListing.title}</h2>
                    <p className="notes-folder-meta">
                      {selectedFolderListing.folders.length} folder
                      {selectedFolderListing.folders.length === 1 ? '' : 's'}
                      {' · '}
                      {selectedFolderListing.pages.length} page
                      {selectedFolderListing.pages.length === 1 ? '' : 's'}
                    </p>
                  </div>
                </header>

                {!selectedFolderListing.folders.length && !selectedFolderListing.pages.length ? (
                  <p className="notes-muted" style={{ paddingLeft: 0 }}>
                    This folder is empty.
                    {isAuthenticated
                      ? ' Use New folder, New page, or Link page to add items under it.'
                      : ''}
                  </p>
                ) : (
                  <div className="notes-folder-sections">
                    {selectedFolderListing.folders.length > 0 && (
                      <section className="notes-folder-section">
                        <h3>Folders</h3>
                        <ul className="notes-folder-grid">
                          {selectedFolderListing.folders.map((child) => (
                            <li key={child.id}>
                              <button
                                type="button"
                                className="notes-folder-card is-folder"
                                onClick={() => onSelect(child)}
                              >
                                <span className="notes-folder-card-icon" aria-hidden="true">
                                  📁
                                </span>
                                <span className="notes-folder-card-title">{child.title}</span>
                                <span className="notes-folder-card-meta">
                                  {(child.children || []).length} item
                                  {(child.children || []).length === 1 ? '' : 's'}
                                </span>
                              </button>
                            </li>
                          ))}
                        </ul>
                      </section>
                    )}
                    {selectedFolderListing.pages.length > 0 && (
                      <section className="notes-folder-section">
                        <h3>Pages</h3>
                        <ul className="notes-folder-grid">
                          {selectedFolderListing.pages.map((child) => (
                            <li key={child.id}>
                              <button
                                type="button"
                                className="notes-folder-card is-page"
                                onClick={() => onSelect(child)}
                              >
                                <span className="notes-folder-card-icon" aria-hidden="true">
                                  📄
                                </span>
                                <span className="notes-folder-card-title">{child.title}</span>
                                {child.page_slug && (
                                  <span className="notes-folder-card-meta">{child.page_slug}</span>
                                )}
                              </button>
                            </li>
                          ))}
                        </ul>
                      </section>
                    )}
                  </div>
                )}
              </div>
            )}
            {selected && !selected.is_folder && (
              <>
                <header className="notes-preview-header">
                  <div>
                    <div className="notes-preview-title-row">
                      <h2>{preview?.title || selected.title}</h2>
                      {isSuperuser && (
                        <button
                          type="button"
                          className="notes-edit-icon-btn"
                          onClick={openEditPage}
                          disabled={busy || previewLoading || !preview}
                          title="Edit page"
                          aria-label="Edit page"
                        >
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                            <path
                              d="M4 20h4.5L19 9.5 14.5 5 4 15.5V20z"
                              stroke="currentColor"
                              strokeWidth="1.75"
                              strokeLinejoin="round"
                            />
                            <path
                              d="M12.5 6.5l5 5"
                              stroke="currentColor"
                              strokeWidth="1.75"
                              strokeLinecap="round"
                            />
                          </svg>
                        </button>
                      )}
                    </div>
                    {selected.page_slug && (
                      <button
                        type="button"
                        className="notes-open-full"
                        onClick={() => navigate(`/p/${selected.page_slug}`)}
                      >
                        Open full page →
                      </button>
                    )}
                  </div>
                </header>
                {previewLoading && <p className="notes-muted">Loading preview…</p>}
                {previewError && <p className="notes-error">{previewError}</p>}
                {preview && !previewLoading && (
                  <article className="markdown-body notes-preview-body">
                    {preview.render_as_html ? (
                      <div dangerouslySetInnerHTML={{ __html: preview.content }} />
                    ) : (
                      <MarkdownBody navigate={navigate}>{preview.content}</MarkdownBody>
                    )}
                  </article>
                )}
              </>
            )}
          </>
        )}
      </div>
    </section>
  );
}
