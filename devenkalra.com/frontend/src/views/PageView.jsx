import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Breadcrumbs } from '../components/Breadcrumbs';
import { TimeKeeperApp } from '../components/TimeKeeperApp';
import { ExercisePlannerApp } from '../components/ExercisePlannerApp';
import { NotesApp } from '../components/NotesApp';
import { NotesPageEditor } from '../components/NotesPageEditor';
import { MarkdownBody } from '../components/MarkdownBody';

export const PageView = ({ menuItems }) => {
  const { menuItemId, slug } = useParams();
  const { isAuthenticated, token, login, logout, user, openSocialLoginModal } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showAdminLogin, setShowAdminLogin] = useState(false);

  // Helper to find MenuItem by page slug recursively
  const findMenuItemBySlug = (nodes, targetSlug) => {
    for (const node of nodes) {
      if (node.page_slug === targetSlug) return node;
      if (node.children && node.children.length > 0) {
        const found = findMenuItemBySlug(node.children, targetSlug);
        if (found) return found;
      }
    }
    return null;
  };

  const isIdNumeric = menuItemId && !isNaN(Number(menuItemId));
  const activeSlug = isIdNumeric ? slug : menuItemId;

  // Find menu item for breadcrumbs
  let activeMenuItemId = isIdNumeric ? Number(menuItemId) : null;
  if (!activeMenuItemId && activeSlug && menuItems) {
    const item = findMenuItemBySlug(menuItems, activeSlug);
    if (item) {
      activeMenuItemId = item.id;
    }
  }

  const handleHTMLClick = (e) => {
    const a = e.target.closest('a');
    if (a && a.getAttribute('href')) {
      const href = a.getAttribute('href');
      const isInternal = href && !href.startsWith('http://') && !href.startsWith('https://') && !href.startsWith('//') && !href.startsWith('#') && !href.startsWith('mailto:') && !href.startsWith('tel:');
      if (isInternal) {
        e.preventDefault();
        if (href.startsWith('/')) {
          navigate(href);
        } else {
          const currentPath = window.location.pathname;
          const cleanPath = currentPath.endsWith('/') ? currentPath.slice(0, -1) : currentPath;
          const cleanUrl = href.startsWith('./') ? href.slice(2) : href;
          const segments = cleanPath.split('/');
          segments.pop();
          segments.push(cleanUrl);
          navigate(segments.join('/'));
        }
      }
    }
  };

  const renderMarkdown = (content) => (
    <MarkdownBody navigate={navigate}>{content}</MarkdownBody>
  );

  const renderHTML = (content) => (
    <div 
      dangerouslySetInnerHTML={{ __html: content }} 
      onClick={handleHTMLClick}
    />
  );

  const [page, setPage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveError, setSaveError] = useState('');
  
  // Login form state (if page is protected)
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [loggingIn, setLoggingIn] = useState(false);

  // Custom App states
  const [customData, setCustomData] = useState([]);
  const [customLoading, setCustomLoading] = useState(false);
  const [expandedCard, setExpandedCard] = useState(null); // For book reviews toggling
  const [expandedProjects, setExpandedProjects] = useState(() => {
    try {
      const saved = localStorage.getItem('projects-expanded-projects');
      return saved ? JSON.parse(saved) : [];
    } catch (e) {
      return [];
    }
  });
  const [iframeHeight, setIframeHeight] = useState('500px');

  useEffect(() => {
    localStorage.setItem('projects-expanded-projects', JSON.stringify(expandedProjects));
  }, [expandedProjects]);

  const API_URL = '/api';

  // Recursive DFS to find active MenuItem in navigation tree
  const findMenuItem = (nodes, targetId) => {
    for (const node of nodes) {
      if (node.id === Number(targetId)) return node;
      if (node.children && node.children.length > 0) {
        const found = findMenuItem(node.children, targetId);
        if (found) return found;
      }
    }
    return null;
  };

  const handleIFrameLoad = (event) => {
    const iframe = event.target;
    if (iframe && iframe.contentWindow) {
      setTimeout(() => {
        try {
          const doc = iframe.contentDocument || iframe.contentWindow.document;
          if (doc && doc.body) {
            const height = doc.documentElement.scrollHeight || doc.body.scrollHeight;
            setIframeHeight(`${height + 30}px`);
          }
        } catch (e) {
          console.error("Error setting iframe height:", e);
        }
      }, 200);
    }
  };

  const getIFrameContent = (content) => {
    if (!content) return '';
    const styleLink = '<link rel="stylesheet" href="/iframe-editorial.css">';
    const jqueryScript = '<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>';
    const tokenScript = `<script>window.__authToken = ${token ? `'${token}'` : 'null'};</script>`;
    const navScript = `
<script>
  document.addEventListener('click', function(e) {
    var a = e.target.closest('a');
    if (a && a.getAttribute('href')) {
      var href = a.getAttribute('href');
      // Intercept internal links (starts with / or relative page slugs)
      var isInternal = href && !href.startsWith('http://') && !href.startsWith('https://') && !href.startsWith('//') && !href.startsWith('#') && !href.startsWith('mailto:') && !href.startsWith('tel:');
      if (isInternal) {
        e.preventDefault();
        window.parent.postMessage({ type: 'NAVIGATE', url: href }, '*');
      }
    }
  });
</script>
`;
    const headInject = styleLink + jqueryScript + tokenScript + navScript;
    
    // Check if head tag exists (case insensitive)
    const lowerContent = content.toLowerCase();
    const headIndex = lowerContent.indexOf('<head>');
    if (headIndex !== -1) {
      return content.slice(0, headIndex + 6) + headInject + content.slice(headIndex + 6);
    }
    
    // Check if html tag exists
    const htmlIndex = lowerContent.indexOf('<html>');
    if (htmlIndex !== -1) {
      return content.slice(0, htmlIndex + 6) + `<head>${headInject}</head>` + content.slice(htmlIndex + 6);
    }
    
    // Otherwise wrap it as standard document
    return `<!DOCTYPE html><html><head><meta charset="utf-8">${headInject}</head><body>${content}</body></html>`;
  };

  const fetchPage = async () => {
    if (!activeSlug) {
      setPage(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Token ${token}`;
      }

      const response = await fetch(`${API_URL}/pages/${activeSlug}/`, { headers });
      
      if (response.status === 403) {
        // Protected page
        try {
          const errData = await response.json();
          setPage({ 
            roles_with_access: errData.roles_with_access || 'user', 
            no_permission: !!errData.no_permission, 
            content: '' 
          });
        } catch (e) {
          setPage({ roles_with_access: 'user', content: '' });
        }
      } else if (response.ok) {
        const data = await response.json();
        setPage(data);
        // If it's a custom app page, load the database entries
        if (['book-reviews', 'indian-music', 'cooking-snacks', 'track-ideas', 'highschool-photography', 'video-ai-internships'].includes(activeSlug)) {
          fetchCustomData(activeSlug);
        }
      } else {
        setError('Page not found or failed to load.');
      }
    } catch (err) {
      console.error(err);
      setError('Network error occurred.');
    } finally {
      setLoading(false);
    }
  };

  const fetchCustomData = async (pageSlug) => {
    setCustomLoading(true);
    let endpoint = '';
    const headers = { 'Content-Type': 'application/json' };
    if (token) {
      headers['Authorization'] = `Token ${token}`;
    }

    if (pageSlug === 'book-reviews') endpoint = 'books';
    else if (pageSlug === 'indian-music') endpoint = 'tracks';
    else if (pageSlug === 'cooking-snacks') endpoint = 'recipes';
    else if (pageSlug === 'track-ideas') endpoint = 'ideas';
    else if (pageSlug === 'highschool-photography' || pageSlug === 'video-ai-internships') endpoint = 'projects';

    if (!endpoint) {
      setCustomLoading(false);
      return;
    }

    try {
      const response = await fetch(`${API_URL}/${endpoint}/`, { headers });
      if (response.ok) {
        const data = await response.json();
        // Filter projects by category for photography or video AI
        if (pageSlug === 'highschool-photography') {
          setCustomData(data.filter(p => p.category.toLowerCase().includes('photo')));
        } else if (pageSlug === 'video-ai-internships') {
          setCustomData(data.filter(p => p.category.toLowerCase().includes('video') || p.category.toLowerCase().includes('ai')));
        } else {
          setCustomData(data);
        }
      }
    } catch (err) {
      console.error("Error fetching custom database records:", err);
    } finally {
      setCustomLoading(false);
    }
  };

  // Intercept postMessage navigation commands from sandboxed iframes
  useEffect(() => {
    const handleMessage = (event) => {
      if (event.data && event.data.type === 'NAVIGATE') {
        const url = event.data.url;
        if (url.startsWith('/')) {
          navigate(url);
        } else {
          const currentPath = window.location.pathname;
          const cleanPath = currentPath.endsWith('/') ? currentPath.slice(0, -1) : currentPath;
          const cleanUrl = url.startsWith('./') ? url.slice(2) : url;
          const segments = cleanPath.split('/');
          segments.pop();
          segments.push(cleanUrl);
          navigate(segments.join('/'));
        }
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [navigate]);

  useEffect(() => {
    fetchPage();
  }, [activeSlug, activeMenuItemId, token]);

  // Use page_edit (not edit) so NotesApp's ?edit=1 does not open site-page edit.
  const urlEditing = searchParams.get('page_edit') === '1';
  // 403 stub pages lack slug/title; only real loaded pages are editable by superusers.
  const pageIsEditable =
    isAuthenticated &&
    !!token &&
    user?.role === 'superuser' &&
    !!page?.slug &&
    page?.title != null &&
    !page?.no_permission;

  useEffect(() => {
    if (!pageIsEditable) {
      setEditing(false);
      return;
    }
    setEditing(urlEditing);
  }, [urlEditing, pageIsEditable, page?.slug]);

  const writeEditParam = useCallback(
    (enabled, { replace = false } = {}) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (enabled) next.set('page_edit', '1');
          else next.delete('page_edit');
          return next;
        },
        { replace }
      );
    },
    [setSearchParams]
  );

  const openPageEdit = () => {
    if (!pageIsEditable) return;
    setSaveError('');
    setEditing(true);
    writeEditParam(true, { replace: false });
  };

  const closePageEdit = ({ replace = true } = {}) => {
    setEditing(false);
    setSaveError('');
    writeEditParam(false, { replace });
  };

  const savePageEdits = async (payload, { close = true } = {}) => {
    if (!token) {
      setSaveError('Sign in again to edit pages (missing auth token).');
      return false;
    }
    if (!page?.slug) {
      setSaveError('No page selected to edit.');
      return false;
    }
    const originalSlug = page.slug;
    if (close) setSaveBusy(true);
    setSaveError('');
    try {
      const response = await fetch(`${API_URL}/pages/${originalSlug}/`, {
        method: 'PATCH',
        headers: {
          Authorization: `Token ${token}`,
          'Content-Type': 'application/json',
        },
        credentials: 'omit',
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const msg =
          body.slug?.[0] ||
          body.title?.[0] ||
          body.content?.[0] ||
          body.detail ||
          `Could not update page (${response.status})`;
        throw new Error(typeof msg === 'string' ? msg : JSON.stringify(body));
      }
      const updated = await response.json();
      setPage(updated);

      const slugChanged = updated.slug && updated.slug !== originalSlug;
      if (slugChanged) {
        const editSuffix = close ? '' : '?page_edit=1';
        if (isIdNumeric && menuItemId) {
          navigate(`/p/${menuItemId}/${updated.slug}${editSuffix}`, { replace: true });
        } else {
          navigate(`/p/${updated.slug}${editSuffix}`, { replace: true });
        }
      }

      if (close) {
        setEditing(false);
        if (!slugChanged) writeEditParam(false, { replace: true });
      }
      return true;
    } catch (err) {
      setSaveError(err.message || 'Could not update page');
      return false;
    } finally {
      if (close) setSaveBusy(false);
    }
  };

  const handleInlineLogin = async (e) => {
    e.preventDefault();
    setLoginError('');
    setLoggingIn(true);
    
    const result = await login(username, password);
    setLoggingIn(false);

    if (result.success) {
      // Re-fetch page on successful login
      fetchPage();
    } else {
      setLoginError(result.error);
    }
  };

  if (loading) {
    return <div className="text-center" style={{ padding: '3rem 0' }}>Loading content...</div>;
  }

  if (error) {
    return (
      <div>
        <Breadcrumbs menuItemId={activeMenuItemId} menuItems={menuItems} />
        <div className="text-center error-message" style={{ padding: '3rem 0' }}>{error}</div>
      </div>
    );
  }

  const activeItem = findMenuItem(menuItems, activeMenuItemId);

  // If we don't have a slug (it's a folder/directory) or if the menu item exists and has no page
  if (!activeSlug || (activeItem && !activeItem.page)) {
    const children = activeItem?.children || [];
    return (
      <div>
        <Breadcrumbs menuItemId={activeMenuItemId} menuItems={menuItems} />
        <h1 style={{ marginBottom: '0.5rem' }}>{activeItem ? activeItem.title : 'Directory'}</h1>
        <p style={{ fontStyle: 'italic', color: 'var(--text-muted)', marginBottom: '2rem' }}>
          Select a category to explore:
        </p>
        {children.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>This category is currently empty.</p>
        ) : (
          <div className="cards-grid">
            {children.map(child => {
              const toPath = child.page_slug 
                ? `/p/${child.id}/${child.page_slug}` 
                : `/p/${child.id}`;
              return (
                <div 
                  key={child.id} 
                  className="editorial-card" 
                  onClick={() => navigate(toPath)} 
                  style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}
                >
                  <div>
                    <div className="card-title">{child.title}</div>
                    <div className="card-meta" style={{ margin: 0, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      {child.page_slug ? 'Document Page' : 'Sub-Category Directory'}
                    </div>
                  </div>
                  <span style={{ fontSize: '0.8rem', color: 'var(--accent-color)', fontWeight: '500', marginTop: '1.5rem', display: 'inline-block' }}>
                    Open {child.page_slug ? 'Page' : 'Directory'} →
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }


  // If page is protected and user is not logged in / authorized
  if (page?.roles_with_access) {
    if (isAuthenticated && page?.no_permission) {
      return (
        <div>
          <Breadcrumbs menuItemId={activeMenuItemId} menuItems={menuItems} />
          <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem 0' }}>
            <div className="auth-card" style={{ boxShadow: 'none', border: '1px solid var(--border-dark)', textAlign: 'center', maxWidth: '450px', width: '90%' }}>
              <div style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>🚫</div>
              <h2 style={{ borderBottom: 'none', marginTop: 0, marginBottom: '1rem' }}>Access Denied</h2>
              <p style={{ fontSize: '0.95rem', color: 'var(--text-color)', marginBottom: '1rem', lineHeight: '1.6' }}>
                Your account <strong>{user?.email}</strong> (role: <strong>{user?.role || 'user'}</strong>) does not have permission to view this page.
              </p>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1.5rem', lineHeight: '1.6' }}>
                This page requires one of these roles: <strong>{page?.roles_with_access}</strong>.
              </p>
              
              <button 
                type="button" 
                onClick={async () => {
                  await logout();
                  fetchPage();
                }} 
                className="editorial-button"
              >
                Sign Out / Switch Account
              </button>
            </div>
          </div>
        </div>
      );
    }

    if (!isAuthenticated) {
      return (
        <div>
          <Breadcrumbs menuItemId={activeMenuItemId} menuItems={menuItems} />
          <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem 0' }}>
            <div className="auth-card" style={{ boxShadow: 'none', border: '1px solid var(--border-dark)', maxWidth: '450px', width: '100%', padding: '2rem' }}>
              <div style={{ fontSize: '2.5rem', marginBottom: '1rem', color: 'var(--accent-color)' }}>🔒</div>
              <h2 style={{ borderBottom: 'none', marginTop: 0, marginBottom: '0.5rem' }}>Protected Page</h2>
              <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', marginBottom: '1.8rem', lineHeight: '1.5' }}>
                This page is protected and requires sign-in. Authenticate temporarily with a social account to unlock it (no account creation required).
              </p>
              
              {loginError && <div className="error-message" style={{ marginBottom: '1rem' }}>{loginError}</div>}
              
              {!showAdminLogin ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'center', width: '100%' }}>
                  <button 
                    type="button" 
                    onClick={() => openSocialLoginModal(fetchPage)} 
                    className="editorial-button"
                    style={{ width: '280px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', margin: 0 }}
                  >
                    🔑 Sign In to Unlock Page
                  </button>
                  
                  <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--border-color)', width: '100%', paddingTop: '1rem', textAlign: 'center' }}>
                    <button 
                      type="button" 
                      onClick={() => setShowAdminLogin(true)}
                      style={{ background: 'none', border: 'none', color: 'var(--accent-color)', cursor: 'pointer', fontSize: '0.8rem', textDecoration: 'underline' }}
                    >
                      Admin staff sign in
                    </button>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleInlineLogin}>
                  <div className="form-group">
                    <label className="form-label" htmlFor="inline-username">Username</label>
                    <input
                      type="text"
                      id="inline-username"
                      className="form-input"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      required
                      disabled={loggingIn}
                    />
                  </div>
                  
                  <div className="form-group">
                    <label className="form-label" htmlFor="inline-password">Password</label>
                    <input
                      type="password"
                      id="inline-password"
                      className="form-input"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      disabled={loggingIn}
                    />
                  </div>
                  
                  <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginTop: '1.5rem' }}>
                    <button 
                      type="submit" 
                      className="editorial-button"
                      disabled={loggingIn}
                      style={{ margin: 0 }}
                    >
                      {loggingIn ? 'Authenticating...' : 'Unlock Page'}
                    </button>
                    
                    <button 
                      type="button" 
                      onClick={() => {
                        setShowAdminLogin(false);
                        setLoginError('');
                      }}
                      className="editorial-button"
                      style={{ margin: 0, background: 'none', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      );
    }
  }

  return (
    <div>
      <Breadcrumbs
        menuItemId={activeMenuItemId}
        menuItems={menuItems}
        pageTitle={page?.title}
        slug={activeSlug}
        canEdit={pageIsEditable && !editing}
        onEdit={openPageEdit}
      />

      {editing && page?.slug ? (
        <div className="page-view-editor">
          <NotesPageEditor
            mode="edit"
            initialValues={page}
            busy={saveBusy}
            error={saveError}
            navigate={navigate}
            onCancel={() => closePageEdit({ replace: true })}
            onSave={savePageEdits}
          />
        </div>
      ) : (
        <>
      {page?.render_as_html ? (
        <iframe
          title={page.title}
          srcDoc={getIFrameContent(page.content)}
          style={{ 
            width: '100%', 
            height: iframeHeight, 
            border: 'none', 
            overflow: 'hidden',
            backgroundColor: 'transparent'
          }}
          onLoad={handleIFrameLoad}
          sandbox="allow-scripts allow-same-origin allow-downloads allow-modals allow-forms"
        />
      ) : (
        <article className="markdown-body">
          {renderMarkdown(page?.content)}
        </article>
      )}

      {/* --- CUSTOM APP INSERTS --- */}
      {activeSlug === 'time-keeper' && (
        <TimeKeeperApp />
      )}

      {activeSlug === 'exercise-planner' && (
        <ExercisePlannerApp />
      )}

      {activeSlug === 'notes' && (
        <NotesApp />
      )}

      {activeSlug === 'creative-projects' && (
        <CreativeProjectsApp />
      )}

      {activeSlug === 'contacts' && (
        <ContactsApp />
      )}

      {activeSlug === 'book-reviews' && (
        <section className="margin-top">
          <h2>Reviews & Summaries</h2>
          {customLoading ? (
            <p>Loading book catalog...</p>
          ) : (
            <div className="cards-grid">
              {customData.map(book => (
                <div key={book.id} className="editorial-card">
                  <div className="card-title">{book.title}</div>
                  <div className="card-meta">By {book.author}</div>
                  <div className="rating-stars">
                    {'★'.repeat(book.rating)}{'☆'.repeat(5 - book.rating)}
                  </div>
                  <div className="card-content" style={{ marginTop: '0.5rem' }}>
                    <p style={{ fontStyle: 'italic', fontSize: '0.9rem', marginBottom: 0 }}>
                      "{book.summary}"
                    </p>
                  </div>
                  <button 
                    className="editorial-button" 
                    style={{ padding: '0.4rem 0.8rem', fontSize: '0.75rem', width: 'auto', alignSelf: 'flex-start' }}
                    onClick={() => setExpandedCard(expandedCard === book.id ? null : book.id)}
                  >
                    {expandedCard === book.id ? 'Close Review' : 'Read Full Review'}
                  </button>
                  {expandedCard === book.id && (
                    <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--border-color)', paddingTop: '1rem', fontSize: '0.9rem' }} className="markdown-body">
                      {renderMarkdown(book.review_content)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {activeSlug === 'indian-music' && (
        <section className="margin-top">
          <h2>Featured Classical Music Tracks</h2>
          {customLoading ? (
            <p>Loading tracks...</p>
          ) : (
            <div className="cards-grid">
              {customData.map(track => (
                <div key={track.id} className="editorial-card">
                  <div className="card-title">{track.title}</div>
                  <div className="card-meta">{track.artist} | <span className="badge badge-medium">{track.genre}</span></div>
                  <div className="card-content" style={{ fontSize: '0.9rem' }}>
                    {track.description}
                  </div>
                  {track.youtube_url && (
                    <a 
                      href={track.youtube_url} 
                      target="_blank" 
                      rel="noopener noreferrer" 
                      className="editorial-button text-center" 
                      style={{ textDecoration: 'none', padding: '0.4rem 0.8rem', fontSize: '0.75rem', width: 'auto', alignSelf: 'flex-start' }}
                    >
                      Listen on YouTube ↗
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {activeSlug === 'cooking-snacks' && (
        <section className="margin-top">
          <h2>Recipes</h2>
          {customLoading ? (
            <p>Loading recipe book...</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3rem' }}>
              {customData.map(recipe => (
                <div key={recipe.id} style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '2.5rem' }}>
                  <h3 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>{recipe.title}</h3>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1.5rem', fontFamily: 'var(--font-sans)' }}>
                    ⏱ Prep Time: {recipe.prep_time_minutes} minutes
                  </div>
                  
                  <div className="recipe-split">
                    <div className="recipe-ingredients">
                      <h3>Ingredients</h3>
                      <ul>
                        {recipe.ingredients.split('\n').map((ing, idx) => (
                          <li key={idx}>{ing.replace('*', '').trim()}</li>
                        ))}
                      </ul>
                    </div>
                    
                    <div className="recipe-instructions">
                      <h3 style={{ marginTop: 0 }}>Instructions</h3>
                      <div style={{ fontSize: '0.95rem', whiteSpace: 'pre-line' }}>
                        {recipe.instructions}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {activeSlug === 'track-ideas' && (
        <section className="margin-top">
          <h2>Ideas Tracker</h2>
          {customLoading ? (
            <p>Loading workflow board...</p>
          ) : (
            <table className="editorial-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {customData.map(idea => (
                  <tr key={idea.id}>
                    <td style={{ fontWeight: '500' }}>{idea.title}</td>
                    <td>
                      <span className={`badge badge-${idea.priority}`}>
                        {idea.priority}
                      </span>
                    </td>
                    <td>
                      <span className={`badge badge-${idea.status}`}>
                        {idea.status}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-muted)' }}>
                      {idea.render_as_html ? renderHTML(idea.description) : renderMarkdown(idea.description)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {['highschool-photography', 'video-ai-internships'].includes(activeSlug) && (() => {
        const mainProjects = customData.filter(p => !p.parent || !customData.some(parent => parent.id == p.parent));
        const getSubprojectsFor = (parentId) => {
          return customData
            .filter(p => p.parent == parentId)
            .sort((a, b) => (a.rank ?? 9000) - (b.rank ?? 9000));
        };
        const toggleProject = (projectId) => {
          setExpandedProjects(prev =>
            prev.includes(projectId)
              ? prev.filter(id => id !== projectId)
              : [...prev, projectId]
          );
        };
        const renderProjectCard = (project, isSubproject = false) => {
          const subs = !isSubproject ? getSubprojectsFor(project.id) : [];
          const isExpanded = expandedProjects.includes(project.id);

          return (
            <div key={project.id} className="project-group" style={{ marginBottom: isSubproject ? '1rem' : '1.5rem' }}>
              <div 
                className="editorial-card" 
                style={isSubproject ? {
                  background: 'var(--accent-light)',
                  padding: '1.25rem',
                  border: '1px solid var(--border-color)',
                  boxShadow: 'none'
                } : {
                  border: '1px solid var(--border-color)',
                  padding: '1.75rem',
                  borderRadius: '6px'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
                  <div 
                    className="card-title" 
                    style={{ 
                      fontSize: isSubproject ? '1.1rem' : '1.3rem', 
                      fontWeight: 500
                    }}
                  >
                    {project.title}
                  </div>
                  {!isSubproject && subs.length > 0 && (
                    <button
                      onClick={() => toggleProject(project.id)}
                      className="toggle-subs-btn"
                      style={{
                        background: 'none',
                        border: '1px solid var(--border-color)',
                        borderRadius: '4px',
                        padding: '0.25rem 0.5rem',
                        fontSize: '0.75rem',
                        fontFamily: 'var(--font-sans)',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.3rem',
                        color: 'var(--text-color)',
                      }}
                    >
                      <span>{isExpanded ? '▲ Hide' : '▼ Expand'} Subprojects</span>
                      <span className="badge badge-active" style={{ margin: 0, padding: '0.05rem 0.25rem', fontSize: '0.65rem' }}>
                        {subs.length}
                      </span>
                    </button>
                  )}
                </div>
                
                <div className="card-meta" style={{ marginTop: '0.4rem', fontSize: '0.8rem' }}>
                  {isSubproject && <span style={{ marginRight: '0.4rem', fontWeight: 600 }}>Rank: {project.rank} |</span>}
                  Category: {project.category} | Status: <span className={`badge badge-active`} style={{ textTransform: 'capitalize' }}>{project.status.replace('_', ' ')}</span>
                </div>
                
                <div className="card-content" style={{ fontSize: isSubproject ? '0.9rem' : '0.95rem', marginTop: '0.5rem' }}>
                  {project.render_as_html ? renderHTML(project.description) : renderMarkdown(project.description)}
                </div>
                
                <div className="card-meta" style={{ margin: '0.5rem 0 0 0', fontSize: '0.8rem' }}>
                  Timeline: {project.start_date} {project.end_date ? `to ${project.end_date}` : '(Ongoing)'}
                </div>
              </div>

              {!isSubproject && subs.length > 0 && isExpanded && (
                <div
                  className="subprojects-list"
                  style={{
                    marginLeft: '2rem',
                    marginTop: '1rem',
                    paddingLeft: '1.25rem',
                    borderLeft: '2px solid var(--border-color)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '1rem'
                  }}
                >
                  {subs.map(sub => renderProjectCard(sub, true))}
                </div>
              )}
            </div>
          );
        };

        return (
          <section className="margin-top">
            <h2>Project Logs</h2>
            {customLoading ? (
              <p>Loading projects...</p>
            ) : (
              <div className="projects-list-container" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                {mainProjects.map(project => renderProjectCard(project, false))}
              </div>
            )}
          </section>
        );
      })()}
        </>
      )}
    </div>
  );
};

const EditableRank = ({ task, onSave }) => {
  const getTaskRank = (t) => {
    if (!t) return Infinity;
    const rankField = t.custom_fields?.find(cf => cf.name?.toLowerCase() === 'rank');
    if (rankField && rankField.value !== null && rankField.value !== undefined) {
      const parsed = parseFloat(rankField.value);
      return isNaN(parsed) ? Infinity : parsed;
    }
    return Infinity;
  };

  const rankVal = getTaskRank(task);
  const displayVal = rankVal === Infinity ? '' : String(rankVal);
  const [isEditing, setIsEditing] = useState(false);
  const [value, setValue] = useState(displayVal);
  const inputRef = React.useRef(null);
  const spanRef = React.useRef(null);

  useEffect(() => {
    setValue(displayVal);
  }, [displayVal]);

  // Restore focus to span when exiting edit mode
  useEffect(() => {
    if (!isEditing && spanRef.current) {
      spanRef.current.focus({ preventScroll: true });
    }
  }, [isEditing]);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus({ preventScroll: true });
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleSubmit = () => {
    setIsEditing(false);
    if (value !== displayVal) {
      onSave(task.id, value.trim());
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleSubmit();
    } else if (e.key === 'Escape') {
      setIsEditing(false);
      setValue(displayVal);
    }
  };

  const handleSpanKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      setIsEditing(true);
    }
  };

  if (isEditing) {
    return (
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={handleSubmit}
        onKeyDown={handleKeyDown}
        onClick={(e) => e.stopPropagation()}
        data-field="rank"
        style={{
          width: '45px',
          fontSize: '0.7rem',
          fontWeight: 700,
          padding: '0.1rem 0.25rem',
          border: '1px solid var(--accent-color)',
          borderRadius: '3px',
          textAlign: 'center',
          outline: 'none',
          fontFamily: 'var(--font-sans)',
          color: 'var(--text-color)',
          backgroundColor: '#ffffff',
          display: 'inline-block',
          boxShadow: '0 0 0 2px var(--accent-color)'
        }}
      />
    );
  }

  return (
    <span 
      ref={spanRef}
      onClick={(e) => {
        e.stopPropagation();
        setIsEditing(true);
      }}
      onKeyDown={handleSpanKeyDown}
      onFocus={(e) => {
        e.currentTarget.style.boxShadow = '0 0 0 2px var(--text-color)';
      }}
      onBlur={(e) => {
        e.currentTarget.style.boxShadow = 'none';
      }}
      tabIndex={0}
      data-field="rank"
      title="Click to edit rank"
      style={{
        fontSize: '0.65rem',
        fontWeight: 700,
        padding: '0.15rem 0.35rem',
        borderRadius: '3px',
        backgroundColor: rankVal === Infinity ? 'var(--border-color)' : 'var(--accent-color)',
        color: rankVal === Infinity ? 'var(--text-muted)' : '#ffffff',
        whiteSpace: 'nowrap',
        cursor: 'pointer',
        transition: 'all 0.15s ease',
        display: 'inline-block',
        outline: 'none'
      }}
      onMouseOver={(e) => {
        e.currentTarget.style.backgroundColor = 'var(--text-color)';
        e.currentTarget.style.color = 'var(--bg-color)';
      }}
      onMouseOut={(e) => {
        e.currentTarget.style.backgroundColor = rankVal === Infinity ? 'var(--border-color)' : 'var(--accent-color)';
        e.currentTarget.style.color = rankVal === Infinity ? 'var(--text-muted)' : '#ffffff';
      }}
    >
      {rankVal === Infinity ? 'RANK' : `#${rankVal}`}
    </span>
  );
};

export const CreativeProjectsApp = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tasks, setTasks] = useState([]);
  const [rowToFocusAfterSort, setRowToFocusAfterSort] = useState(null);
  const [spaceName, setSpaceName] = useState('Creative Space');
  const [spaceId, setSpaceId] = useState('');
  const [teamId, setTeamId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedTasks, setExpandedTasks] = useState(() => {
    try {
      const saved = localStorage.getItem('creative-projects-expanded-tasks');
      return saved ? JSON.parse(saved) : [];
    } catch (e) {
      return [];
    }
  });
  // Derive viewMode directly from the URL query params (Single Source of Truth)
  const modeParam = searchParams.get('mode')?.toLowerCase();
  const viewMode = (modeParam === 'flat' || modeParam === 'compact' || modeParam === 'group' || modeParam === 'grouped')
    ? (modeParam === 'grouped' ? 'group' : modeParam)
    : 'compact';

  const [showClosed, setShowClosed] = useState(() => {
    return localStorage.getItem('creative-projects-show-closed') === 'true';
  });
  const [showHiddenByShowAfter, setShowHiddenByShowAfter] = useState(() => {
    return localStorage.getItem('creative-projects-show-hidden-by-show-after') === 'true';
  });
  const [collapsedLists, setCollapsedLists] = useState(() => {
    try {
      const saved = localStorage.getItem('creative-projects-collapsed-lists');
      return saved ? JSON.parse(saved) : [];
    } catch (e) {
      return [];
    }
  });
  const { token } = useAuth();

  useEffect(() => {
    localStorage.setItem('creative-projects-expanded-tasks', JSON.stringify(expandedTasks));
  }, [expandedTasks]);

  // Fallback default: set URL parameter to compact if missing/invalid on mount
  useEffect(() => {
    const param = searchParams.get('mode')?.toLowerCase();
    if (!param || !['flat', 'compact', 'group', 'grouped'].includes(param)) {
      setSearchParams(prev => {
        const next = new URLSearchParams(prev);
        next.set('mode', 'compact');
        return next;
      }, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  // Handler to update view mode
  const handleViewModeChange = (newMode) => {
    localStorage.setItem('creative-projects-view-mode', newMode);
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      next.set('mode', newMode);
      return next;
    }, { replace: true });
  };

  useEffect(() => {
    localStorage.setItem('creative-projects-show-closed', showClosed ? 'true' : 'false');
  }, [showClosed]);

  useEffect(() => {
    localStorage.setItem('creative-projects-show-hidden-by-show-after', showHiddenByShowAfter ? 'true' : 'false');
  }, [showHiddenByShowAfter]);

  useEffect(() => {
    localStorage.setItem('creative-projects-collapsed-lists', JSON.stringify(collapsedLists));
  }, [collapsedLists]);

  // Restore focus to the same numerical row index after list re-sorting
  useEffect(() => {
    if (rowToFocusAfterSort) {
      const { rowIndex, fieldType } = rowToFocusAfterSort;
      const timer = setTimeout(() => {
        const container = document.querySelector('.compact-list-container-el');
        if (container) {
          let index = rowIndex;
          const rows = container.querySelectorAll('.compact-task-row');
          if (rows.length > 0) {
            if (index >= rows.length) {
              index = rows.length - 1;
            }
            const targetRow = rows[index];
            if (targetRow) {
              const targetEl = targetRow.querySelector(`[data-field="${fieldType}"]`);
              if (targetEl) {
                targetEl.focus({ preventScroll: true });
              }
            }
          }
        }
      }, 0);
      setRowToFocusAfterSort(null);
      return () => clearTimeout(timer);
    }
  }, [rowToFocusAfterSort]);

  const fetchTasks = async () => {
    setLoading(true);
    setError('');
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Token ${token}`;
      }
      const query = showHiddenByShowAfter ? '?include_hidden_show_after=true' : '';
      const response = await fetch(`/api/clickup/tasks/${query}`, { headers });
      if (response.ok) {
        const data = await response.json();
        setTasks(data.tasks || []);
        if (data.space) {
          if (data.space.name) setSpaceName(data.space.name);
          if (data.space.id) setSpaceId(data.space.id);
        }
        if (data.team_id) {
          setTeamId(data.team_id);
        }
      } else {
        const errData = await response.json().catch(() => ({}));
        setError(errData.detail || 'Failed to fetch ClickUp tasks.');
      }
    } catch (err) {
      console.error(err);
      setError('Network error occurred while fetching ClickUp tasks.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, [token, showHiddenByShowAfter]);

  const findRankFieldId = (task, allTasks) => {
    const field = task.custom_fields?.find(cf => cf.name?.toLowerCase() === 'rank');
    if (field?.id) return field.id;
    for (const t of allTasks) {
      const f = t.custom_fields?.find(cf => cf.name?.toLowerCase() === 'rank');
      if (f?.id) return f.id;
    }
    return null;
  };

  const handleRankChange = async (taskId, newRank) => {
    const oldTasks = tasks;
    const targetTask = tasks.find(t => t.id === taskId);
    if (!targetTask) return;

    const rankFieldId = findRankFieldId(targetTask, tasks);
    if (!rankFieldId) {
      alert('Could not find "rank" custom field ID in ClickUp tasks.');
      return;
    }

    // Record the current row index of the task to restore focus to the same visual slot after re-sort
    const curRowIndex = allFlatTasksSorted.findIndex(t => t.id === taskId);
    if (curRowIndex !== -1) {
      setRowToFocusAfterSort({ rowIndex: curRowIndex, fieldType: 'rank' });
    }

    // Optimistically update local state
    const updatedTasks = tasks.map(t => {
      if (t.id === taskId) {
        const updatedCustomFields = t.custom_fields?.map(cf => {
          if (cf.id === rankFieldId) {
            return { ...cf, value: newRank === '' ? null : newRank };
          }
          return cf;
        }) || [];
        if (!updatedCustomFields.some(cf => cf.id === rankFieldId)) {
          updatedCustomFields.push({ id: rankFieldId, name: 'rank', value: newRank === '' ? null : newRank });
        }
        return { ...t, custom_fields: updatedCustomFields };
      }
      return t;
    });

    setTasks(updatedTasks);

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Token ${token}`;
      }
      const response = await fetch('/api/clickup/tasks/', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          taskId,
          customFieldId: rankFieldId,
          customFieldValue: newRank === '' ? null : newRank
        })
      });

      if (response.ok) {
        const data = await response.json();
        if (data.status !== 'success') {
          throw new Error('Update response status not success');
        }
      } else {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to update rank.');
      }
    } catch (err) {
      console.error(err);
      alert('Failed to update task rank: ' + err.message);
      setTasks(oldTasks);
    }
  };

  const handleKeyDownContainer = (e) => {
    const active = document.activeElement;
    if (!active) return;

    // Check if active element is one of our fields
    const fieldType = active.getAttribute('data-field'); // 'rank', 'title', or 'status'
    if (!fieldType) return;

    // If typing inside the rank input field, ignore ArrowLeft/ArrowRight to let the user move their text cursor
    if (active.tagName === 'INPUT' && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
      return;
    }

    const rowElement = active.closest('.compact-task-row');
    if (!rowElement) return;

    const rowIndex = parseInt(rowElement.getAttribute('data-row-index'), 10);
    if (isNaN(rowIndex)) return;

    const container = rowElement.closest('.compact-list-container-el');
    if (!container) return;

    const fieldsOrder = ['rank', 'title', 'status'];
    const fieldIndex = fieldsOrder.indexOf(fieldType);

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      // Move focus to the same field in previous row
      const targetRow = container.querySelector(`.compact-task-row[data-row-index="${rowIndex - 1}"]`);
      if (targetRow) {
        const targetEl = targetRow.querySelector(`[data-field="${fieldType}"]`);
        if (targetEl) targetEl.focus();
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      // Move focus to the same field in next row
      const targetRow = container.querySelector(`.compact-task-row[data-row-index="${rowIndex + 1}"]`);
      if (targetRow) {
        const targetEl = targetRow.querySelector(`[data-field="${fieldType}"]`);
        if (targetEl) targetEl.focus();
      }
    } else if (e.key === 'ArrowLeft') {
      // Move focus to previous field in the same row
      if (fieldIndex > 0) {
        e.preventDefault();
        const prevFieldType = fieldsOrder[fieldIndex - 1];
        const targetEl = rowElement.querySelector(`[data-field="${prevFieldType}"]`);
        if (targetEl) targetEl.focus();
      }
    } else if (e.key === 'ArrowRight') {
      // Move focus to next field in the same row
      if (fieldIndex < fieldsOrder.length - 1) {
        e.preventDefault();
        const nextFieldType = fieldsOrder[fieldIndex + 1];
        const targetEl = rowElement.querySelector(`[data-field="${nextFieldType}"]`);
        if (targetEl) targetEl.focus();
      }
    }
  };

  const toggleTask = (taskId) => {
    setExpandedTasks(prev =>
      prev.includes(taskId)
        ? prev.filter(id => id !== taskId)
        : [...prev, taskId]
    );
  };

  const handleStatusChange = async (taskId, newStatus) => {
    const oldTasks = tasks;
    
    // Status color mapping matching ClickUp space details
    const STATUS_COLORS = {
      'to do': '#87909e',
      'in progress': '#5f55ee',
      'complete': '#008844'
    };

    // Optimistically update status and color locally
    const updatedTasks = tasks.map(t => {
      if (t.id === taskId) {
        return {
          ...t,
          status: {
            ...t.status,
            status: newStatus,
            color: STATUS_COLORS[newStatus] || t.status?.color || '#87909e'
          }
        };
      }
      return t;
    });
    setTasks(updatedTasks);

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Token ${token}`;
      }
      const response = await fetch('/api/clickup/tasks/', {
        method: 'POST',
        headers,
        body: JSON.stringify({ taskId, status: newStatus })
      });
      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success' && data.task) {
          // Re-update task with the actual data returned by the backend
          setTasks(prev => prev.map(t => t.id === taskId ? data.task : t));
        }
      } else {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to update task status.');
      }
    } catch (err) {
      console.error(err);
      alert('Failed to update task status: ' + err.message);
      // Revert optimistic update
      setTasks(oldTasks);
    }
  };

  const toggleList = (listName) => {
    setCollapsedLists(prev =>
      prev.includes(listName)
        ? prev.filter(name => name !== listName)
        : [...prev, listName]
    );
  };

  if (loading) {
    return (
      <div style={{ padding: '3rem 0', textAlign: 'center', color: 'var(--text-muted)' }}>
        <div className="loading-spinner" style={{ marginBottom: '1rem' }}>⌛</div>
        Loading ClickUp Space tasks...
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-message" style={{ margin: '2rem 0', padding: '1.5rem', borderLeft: '4px solid #dc2626' }}>
        <strong>Error Loading ClickUp Integration</strong>
        <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.9rem' }}>{error}</p>
        <button 
          onClick={fetchTasks} 
          className="editorial-button" 
          style={{ width: 'auto', marginTop: '1rem', padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}
        >
          Retry Connection
        </button>
      </div>
    );
  }

  // --- Rank helper and sorting ---
  const getTaskRank = (task) => {
    if (!task) return Infinity;
    const rankField = task.custom_fields?.find(cf => cf.name?.toLowerCase() === 'rank');
    if (rankField && rankField.value !== null && rankField.value !== undefined) {
      const parsed = parseFloat(rankField.value);
      return isNaN(parsed) ? Infinity : parsed;
    }
    return Infinity;
  };

  const sortTasksByRank = (taskList) => {
    return [...taskList].sort((a, b) => {
      const rA = getTaskRank(a);
      const rB = getTaskRank(b);
      if (rA !== rB) {
        return rA - rB;
      }
      const nameA = a.name || '';
      const nameB = b.name || '';
      return nameA.localeCompare(nameB);
    });
  };

  const getPriorityLabel = (priority) => {
    if (!priority) return null;
    return priority.priority ? priority.priority.toUpperCase() : String(priority).toUpperCase();
  };

  const getPriorityColor = (priority) => {
    if (!priority) return '#f3f4f6';
    return priority.color || '#f3f4f6';
  };

  const isScheduledTask = (task) => {
    return task.custom_fields?.some(cf => cf.name?.toLowerCase() === 'show after' && cf.value !== null && cf.value !== undefined && cf.value !== '');
  };

  const formatDate = (timestamp) => {
    if (!timestamp) return '-';
    const date = new Date(Number(timestamp));
    return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  };



  const isClosed = (task) => {
    return task.status?.type === 'closed' || task.status?.status?.toLowerCase() === 'complete';
  };

  const filteredTasks = tasks.filter(t => {
    if (showClosed) return true;
    return !isClosed(t);
  });

  // Construct subtasks mapping (where each subtask list is sorted by rank)
  const subTasksMap = {};
  filteredTasks.forEach(t => {
    if (t.parent) {
      const parentId = typeof t.parent === 'object' ? t.parent.id : t.parent;
      if (parentId) {
        if (!subTasksMap[parentId]) subTasksMap[parentId] = [];
        subTasksMap[parentId].push(t);
      }
    }
  });
  Object.keys(subTasksMap).forEach(pid => {
    subTasksMap[pid] = sortTasksByRank(subTasksMap[pid]);
  });

  const renderTaskRow = (task, isSubtask = false) => {
    const isExpanded = expandedTasks.includes(task.id);
    const subTasks = !isSubtask ? (subTasksMap[task.id] || []) : [];
    const hasSubs = subTasks.length > 0;
    
    const statusBg = task.status?.color || '#e5e7eb';
    const priorityLabel = getPriorityLabel(task.priority);
    const priorityColor = getPriorityColor(task.priority);
    const rankVal = getTaskRank(task);

    return (
      <div 
        key={task.id} 
        style={{ 
          marginBottom: isSubtask ? '0.75rem' : '1.25rem',
          marginLeft: isSubtask ? '1.5rem' : '0',
          borderLeft: isSubtask ? '2px solid var(--border-color)' : 'none',
          paddingLeft: isSubtask ? '1rem' : '0'
        }}
      >
        <div 
          style={{
            background: isSubtask ? 'var(--accent-light)' : '#ffffff',
            border: '1px solid var(--border-color)',
            borderRadius: '6px',
            padding: '1.25rem',
            boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            transition: 'all 0.2s ease',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.5rem'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {!isSubtask && hasSubs && (
                <button
                  onClick={() => toggleTask(task.id)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--accent-color)',
                    cursor: 'pointer',
                    fontSize: '0.9rem',
                    padding: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '1.25rem',
                    height: '1.25rem'
                  }}
                >
                  {isExpanded ? '▼' : '▶'}
                </button>
              )}
              <div>
                <h4 style={{ margin: 0, fontSize: isSubtask ? '0.95rem' : '1.1rem', fontWeight: 500 }}>
                  <a 
                    href={`https://app.clickup.com/t/${task.id}`} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    style={{ color: 'var(--text-color)', textDecoration: 'none', borderBottom: '1px solid transparent' }}
                    onMouseOver={(e) => e.target.style.borderBottom = '1px solid var(--text-color)'}
                    onMouseOut={(e) => e.target.style.borderBottom = '1px solid transparent'}
                  >
                    {task.name}
                  </a>
                  {showHiddenByShowAfter && isScheduledTask(task) && (
                    <span
                      title="Scheduled task"
                      aria-label="Scheduled task"
                      style={{
                        marginLeft: '0.4rem',
                        fontSize: '0.85rem',
                        verticalAlign: 'middle',
                        color: 'var(--accent-color)'
                      }}
                    >
                      ⏰
                    </span>
                  )}
                </h4>
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
              {rankVal !== Infinity && (
                <span 
                  style={{
                    fontSize: '0.65rem',
                    fontWeight: 600,
                    padding: '0.15rem 0.4rem',
                    borderRadius: '4px',
                    backgroundColor: 'var(--accent-color)',
                    color: '#ffffff'
                  }}
                >
                  RANK {rankVal}
                </span>
              )}
              {priorityLabel && (
                <span 
                  style={{
                    fontSize: '0.65rem',
                    fontWeight: 600,
                    padding: '0.15rem 0.4rem',
                    borderRadius: '4px',
                    backgroundColor: priorityColor,
                    color: '#ffffff',
                    textTransform: 'uppercase'
                  }}
                >
                  {priorityLabel}
                </span>
              )}
              <select
                value={task.status?.status || 'to do'}
                onChange={(e) => handleStatusChange(task.id, e.target.value)}
                onClick={(e) => e.stopPropagation()}
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  padding: '0.15rem 1.25rem 0.15rem 0.5rem',
                  borderRadius: '12px',
                  backgroundColor: statusBg,
                  color: '#ffffff',
                  textTransform: 'uppercase',
                  border: '1px solid rgba(0,0,0,0.05)',
                  cursor: 'pointer',
                  outline: 'none',
                  appearance: 'none',
                  WebkitAppearance: 'none',
                  MozAppearance: 'none',
                  backgroundImage: `url("data:image/svg+xml;utf8,<svg fill='white' height='24' viewBox='0 0 24 24' width='24' xmlns='http://www.w3.org/2000/svg'><path d='M7 10l5 5 5-5z'/><path d='M0 0h24v24H0z' fill='none'/></svg>")`,
                  backgroundRepeat: 'no-repeat',
                  backgroundPosition: 'right 2px center',
                  backgroundSize: '12px'
                }}
              >
                <option value="to do" style={{ color: '#000000' }}>To Do</option>
                <option value="in progress" style={{ color: '#000000' }}>In Progress</option>
                <option value="complete" style={{ color: '#000000' }}>Complete</option>
                {!['to do', 'in progress', 'complete'].includes(task.status?.status) && task.status?.status && (
                  <option value={task.status.status} style={{ color: '#000000' }}>{task.status.status}</option>
                )}
              </select>
            </div>
          </div>

          {task.description && (
            <div 
              style={{ 
                fontSize: '0.85rem', 
                color: 'var(--text-muted)', 
                marginTop: '0.25rem',
                whiteSpace: 'pre-line' 
              }}
            >
              {task.description}
            </div>
          )}

          <div 
            style={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center', 
              fontSize: '0.75rem', 
              color: 'var(--text-muted)',
              marginTop: '0.5rem',
              borderTop: '1px solid var(--border-color)',
              paddingTop: '0.5rem'
            }}
          >
            <div>
              📅 Due: <span style={{ fontWeight: 500 }}>{formatDate(task.due_date)}</span>
              {viewMode === 'flat' && task.list?.name && (
                <span style={{ marginLeft: '1rem', fontStyle: 'italic' }}>
                  📁 List: {task.list.name}
                </span>
              )}
            </div>
            
            {task.assignees && task.assignees.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                👤 {task.assignees.map(a => a.username).join(', ')}
              </div>
            )}
          </div>
        </div>

        {!isSubtask && hasSubs && isExpanded && (
          <div style={{ marginTop: '0.75rem' }}>
            {subTasks.map(sub => renderTaskRow(sub, true))}
          </div>
        )}
      </div>
    );
  };

  const renderCompactTask = (task, idx, isLast = false) => {
    const rankVal = getTaskRank(task);
    const statusBg = task.status?.color || '#e5e7eb';
    const statusName = task.status?.status || 'to do';

    const parentId = task.parent ? (typeof task.parent === 'object' ? task.parent?.id : task.parent) : null;
    const parentTask = parentId ? tasks.find(t => t.id === parentId) : null;
    const parentName = parentTask?.name || task.parent?.name || '';

    return (
      <div 
        key={task.id} 
        className="compact-task-row"
        data-row-index={idx}
        style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'space-between',
          padding: '0.6rem 1rem', 
          borderBottom: isLast ? 'none' : '1px solid var(--border-color)',
          gap: '1rem',
          fontSize: '0.9rem'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
          <EditableRank task={task} onSave={handleRankChange} />
          <span 
            style={{ 
              width: '8px', 
              height: '8px', 
              borderRadius: '50%', 
              backgroundColor: statusBg, 
              flexShrink: 0 
            }} 
          />
          <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
            <a 
              href={`https://app.clickup.com/t/${task.id}`} 
              target="_blank" 
              rel="noopener noreferrer"
              data-field="title"
              style={{ 
                color: 'var(--text-color)', 
                textDecoration: 'none', 
                fontWeight: 500,
                outline: 'none',
                borderRadius: '2px',
                transition: 'box-shadow 0.15s ease'
              }}
              onFocus={(e) => {
                e.currentTarget.style.boxShadow = '0 0 0 2px var(--text-color)';
              }}
              onBlur={(e) => {
                e.currentTarget.style.boxShadow = 'none';
              }}
              onMouseOver={(e) => e.target.style.borderBottom = '1px solid var(--text-color)'}
              onMouseOut={(e) => e.target.style.borderBottom = '1px solid transparent'}
            >
              {task.name}
            </a>
            {showHiddenByShowAfter && isScheduledTask(task) && (
              <span
                title="Scheduled task"
                aria-label="Scheduled task"
                style={{
                  marginLeft: '0.35rem',
                  fontSize: '0.8rem',
                  verticalAlign: 'middle',
                  color: 'var(--accent-color)'
                }}
              >
                ⏰
              </span>
            )}
            {parentName && (
              <span 
                style={{ 
                  fontSize: '0.75rem', 
                  color: 'var(--text-muted)', 
                  marginLeft: '0.5rem',
                  fontStyle: 'italic'
                }}
                title={`Subtask of: ${parentName}`}
              >
                ({parentName.length > 20 ? `${parentName.substring(0, 20)}...` : parentName})
              </span>
            )}
          </span>
        </div>
        <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <select
            value={task.status?.status || 'to do'}
            onChange={(e) => handleStatusChange(task.id, e.target.value)}
            onClick={(e) => e.stopPropagation()}
            data-field="status"
            onFocus={(e) => {
              e.currentTarget.style.boxShadow = '0 0 0 2px var(--text-color)';
            }}
            onBlur={(e) => {
              e.currentTarget.style.boxShadow = 'none';
            }}
            style={{ 
              fontSize: '0.7rem', 
              fontWeight: 600, 
              padding: '0.15rem 1.25rem 0.15rem 0.5rem', 
              borderRadius: '12px', 
              backgroundColor: statusBg, 
              color: '#ffffff', 
              textTransform: 'uppercase',
              border: '1px solid rgba(0,0,0,0.05)',
              cursor: 'pointer',
              outline: 'none',
              appearance: 'none',
              WebkitAppearance: 'none',
              MozAppearance: 'none',
              backgroundImage: `url("data:image/svg+xml;utf8,<svg fill='white' height='24' viewBox='0 0 24 24' width='24' xmlns='http://www.w3.org/2000/svg'><path d='M7 10l5 5 5-5z'/><path d='M0 0h24v24H0z' fill='none'/></svg>")`,
              backgroundRepeat: 'no-repeat',
              backgroundPosition: 'right 2px center',
              backgroundSize: '12px',
              transition: 'box-shadow 0.15s ease'
            }}
          >
            <option value="to do" style={{ color: '#000000' }}>To Do</option>
            <option value="in progress" style={{ color: '#000000' }}>In Progress</option>
            <option value="complete" style={{ color: '#000000' }}>Complete</option>
            {!['to do', 'in progress', 'complete'].includes(task.status?.status) && task.status?.status && (
              <option value={task.status.status} style={{ color: '#000000' }}>{task.status.status}</option>
            )}
          </select>
        </div>
      </div>
    );
  };

  // Root tasks sorted by rank (bubble up active subtasks whose parents are closed/hidden)
  const rootTasks = filteredTasks.filter(t => {
    const parentId = t.parent ? (typeof t.parent === 'object' ? t.parent.id : t.parent) : null;
    return !parentId || !filteredTasks.some(p => p.id === parentId);
  });

  // --- Grouped Mode Math ---
  const listGroups = {};
  rootTasks.forEach(t => {
    const listName = t.list?.name || 'Uncategorized';
    if (!listGroups[listName]) listGroups[listName] = [];
    listGroups[listName].push(t);
  });
  // Sort tasks in each group
  Object.keys(listGroups).forEach(listName => {
    listGroups[listName] = sortTasksByRank(listGroups[listName]);
  });
  const sortedListNames = Object.keys(listGroups).sort((a, b) => a.localeCompare(b));

  const collapseAllLists = () => {
    setCollapsedLists(sortedListNames);
  };

  const expandAllLists = () => {
    setCollapsedLists([]);
  };

  // --- Flat Mode Math ---
  const allFlatTasksSorted = sortTasksByRank(filteredTasks);

  return (
    <section className="margin-top">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem' }}>
        <h2 style={{ margin: 0, fontFamily: 'var(--font-serif)', fontSize: '1.75rem' }}>Projects</h2>
        {teamId && spaceId ? (
          <a 
            href={`https://app.clickup.com/${teamId}/v/l/s/${spaceId}`}
            target="_blank"
            rel="noopener noreferrer"
            className="badge badge-active"
            style={{ fontSize: '0.75rem', textTransform: 'uppercase', textDecoration: 'none' }}
          >
            Space: {spaceName}
          </a>
        ) : (
          <span className="badge badge-active" style={{ fontSize: '0.75rem', textTransform: 'uppercase' }}>
            Space: {spaceName}
          </span>
        )}
      </div>

      {/* View Mode & Filter Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button 
            onClick={() => handleViewModeChange('group')}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: viewMode === 'group' ? 'var(--text-color)' : 'transparent',
              color: viewMode === 'group' ? 'var(--bg-color)' : 'var(--text-color)',
              border: '1px solid var(--text-color)',
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              fontSize: '0.8rem',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'var(--transition-smooth)'
            }}
          >
            🗂 Group by List
          </button>
          <button 
            onClick={() => handleViewModeChange('flat')}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: viewMode === 'flat' ? 'var(--text-color)' : 'transparent',
              color: viewMode === 'flat' ? 'var(--bg-color)' : 'var(--text-color)',
              border: '1px solid var(--text-color)',
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              fontSize: '0.8rem',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'var(--transition-smooth)'
            }}
          >
            📃 Flat List
          </button>
          <button 
            onClick={() => handleViewModeChange('compact')}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: viewMode === 'compact' ? 'var(--text-color)' : 'transparent',
              color: viewMode === 'compact' ? 'var(--bg-color)' : 'var(--text-color)',
              border: '1px solid var(--text-color)',
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              fontSize: '0.8rem',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'var(--transition-smooth)'
            }}
          >
            ⚡ Compact List
          </button>
        </div>

        {/* Toggle Closed Tasks */}
        <button
          onClick={() => setShowHiddenByShowAfter(prev => !prev)}
          style={{
            padding: '0.5rem 1rem',
            backgroundColor: showHiddenByShowAfter ? 'var(--text-color)' : 'transparent',
            color: showHiddenByShowAfter ? 'var(--bg-color)' : 'var(--text-color)',
            border: '1px solid var(--text-color)',
            fontFamily: 'var(--font-sans)',
            fontWeight: 500,
            fontSize: '0.8rem',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            cursor: 'pointer',
            borderRadius: '4px',
            transition: 'var(--transition-smooth)'
          }}
        >
          {showHiddenByShowAfter ? 'Hide Scheduled' : 'Show Scheduled'}
        </button>
        <label 
          style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: '0.5rem', 
            fontSize: '0.85rem', 
            fontWeight: 500, 
            cursor: 'pointer',
            fontFamily: 'var(--font-sans)',
            color: 'var(--text-color)'
          }}
        >
          <input 
            type="checkbox" 
            checked={showClosed} 
            onChange={(e) => setShowClosed(e.target.checked)}
            style={{ 
              cursor: 'pointer',
              accentColor: 'var(--accent-color)'
            }} 
          />
          <span>Show Closed Tasks</span>
        </label>
      </div>

      {/* Grouped View Collapse/Expand All Buttons */}
      {viewMode === 'group' && filteredTasks.length > 0 && (
        <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '2rem', marginTop: '-1rem' }}>
          <button
            onClick={collapseAllLists}
            style={{
              padding: '0.35rem 0.75rem',
              backgroundColor: 'transparent',
              color: 'var(--text-muted)',
              border: '1px solid var(--border-color)',
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              fontSize: '0.75rem',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'var(--transition-smooth)'
            }}
            onMouseOver={(e) => { e.currentTarget.style.borderColor = 'var(--text-color)'; e.currentTarget.style.color = 'var(--text-color)'; }}
            onMouseOut={(e) => { e.currentTarget.style.borderColor = 'var(--border-color)'; e.currentTarget.style.color = 'var(--text-muted)'; }}
          >
            📁 Collapse All Lists
          </button>
          <button
            onClick={expandAllLists}
            style={{
              padding: '0.35rem 0.75rem',
              backgroundColor: 'transparent',
              color: 'var(--text-muted)',
              border: '1px solid var(--border-color)',
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              fontSize: '0.75rem',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'var(--transition-smooth)'
            }}
            onMouseOver={(e) => { e.currentTarget.style.borderColor = 'var(--text-color)'; e.currentTarget.style.color = 'var(--text-color)'; }}
            onMouseOut={(e) => { e.currentTarget.style.borderColor = 'var(--border-color)'; e.currentTarget.style.color = 'var(--text-muted)'; }}
          >
            📂 Expand All Lists
          </button>
        </div>
      )}
      
      {filteredTasks.length === 0 ? (
        <p style={{ color: 'var(--text-muted)', fontStyle: 'italic', padding: '2rem 0', textAlign: 'center' }}>
          {tasks.length === 0 ? `No tasks found in ${spaceName}.` : `No open tasks found in ${spaceName}.`}
        </p>
      ) : viewMode === 'group' ? (
        // Render Grouped by List
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          {sortedListNames.map(listName => {
            const isCollapsed = collapsedLists.includes(listName);
            return (
              <div key={listName}>
                <h3 
                  onClick={() => toggleList(listName)}
                  style={{ 
                    fontFamily: 'var(--font-sans)', 
                    fontSize: '1rem', 
                    fontWeight: 600, 
                    textTransform: 'uppercase', 
                    letterSpacing: '0.05em', 
                    color: 'var(--text-muted)', 
                    borderBottom: '1.5px solid var(--border-color)', 
                    paddingBottom: '0.4rem', 
                    marginBottom: '1rem',
                    marginTop: '0',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    userSelect: 'none',
                    transition: 'var(--transition-smooth)'
                  }}
                  onMouseOver={(e) => e.currentTarget.style.color = 'var(--text-color)'}
                  onMouseOut={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
                >
                  <span>
                    {isCollapsed ? '📁' : '📂'} {listName} ({listGroups[listName].length})
                  </span>
                  <span style={{ fontSize: '0.8rem', color: 'var(--accent-color)' }}>
                    {isCollapsed ? 'Expand' : 'Collapse'}
                  </span>
                </h3>
                {!isCollapsed && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {listGroups[listName].map(task => renderTaskRow(task, false))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : viewMode === 'flat' ? (
        // Render Flat List sorted by Rank
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {sortTasksByRank(rootTasks).map(task => renderTaskRow(task, false))}
        </div>
      ) : (
        // Render Compact List
        <div 
          className="compact-list-container-el"
          onKeyDown={handleKeyDownContainer}
          style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            backgroundColor: '#ffffff', 
            border: '1px solid var(--border-color)', 
            borderRadius: '6px', 
            overflow: 'hidden',
            boxShadow: '0 1px 3px rgba(0,0,0,0.02)'
          }}
        >
          {allFlatTasksSorted.map((task, idx) => {
            const isLast = idx === allFlatTasksSorted.length - 1;
            return renderCompactTask(task, idx, isLast);
          })}
        </div>
      )}
    </section>
  );
};

export const ContactsApp = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [contacts, setContacts] = useState([]);
  const [contactStatuses, setContactStatuses] = useState([]);
  const [organizationFilter, setOrganizationFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('rank');
  const [showFiltersPopup, setShowFiltersPopup] = useState(false);
  const [draftOrganizationFilter, setDraftOrganizationFilter] = useState('all');
  const [draftStatusFilter, setDraftStatusFilter] = useState('all');
  const [selectedContact, setSelectedContact] = useState(null);
  const [contactActivities, setContactActivities] = useState([]);
  const [activitiesLoading, setActivitiesLoading] = useState(false);
  const [activitiesError, setActivitiesError] = useState('');
  const [spaceName, setSpaceName] = useState('Consulting');
  const [teamId, setTeamId] = useState('');
  const [spaceId, setSpaceId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showHiddenByShowAfter, setShowHiddenByShowAfter] = useState(() => {
    return localStorage.getItem('contacts-show-hidden-by-show-after') === 'true';
  });
  const { token } = useAuth();

  const modeParam = searchParams.get('mode')?.toLowerCase();
  const viewMode = (modeParam === 'flat' || modeParam === 'compact' || modeParam === 'group' || modeParam === 'grouped')
    ? (modeParam === 'grouped' ? 'group' : modeParam)
    : 'flat';

  useEffect(() => {
    const param = searchParams.get('mode')?.toLowerCase();
    if (!param || !['flat', 'compact', 'group', 'grouped'].includes(param)) {
      setSearchParams(prev => {
        const next = new URLSearchParams(prev);
        next.set('mode', 'flat');
        return next;
      }, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    localStorage.setItem('contacts-show-hidden-by-show-after', showHiddenByShowAfter ? 'true' : 'false');
  }, [showHiddenByShowAfter]);

  const handleViewModeChange = (newMode) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      next.set('mode', newMode);
      return next;
    }, { replace: true });
  };

  const openFiltersPopup = () => {
    setDraftOrganizationFilter(organizationFilter);
    setDraftStatusFilter(statusFilter);
    setShowFiltersPopup(true);
  };

  const applyFilters = () => {
    setOrganizationFilter(draftOrganizationFilter);
    setStatusFilter(draftStatusFilter);
    setShowFiltersPopup(false);
  };

  const clearFilters = () => {
    setDraftOrganizationFilter('all');
    setDraftStatusFilter('all');
  };

  const getCustomFieldValue = (task, fieldName) => {
    const field = task.custom_fields?.find(
      (cf) => cf.name?.trim().toLowerCase() === fieldName.toLowerCase()
    );
    const value = field?.value;
    if (value === null || value === undefined || value === '') return '';
    if (typeof value === 'string') return value;
    if (typeof value === 'number') return String(value);
    if (typeof value === 'object') {
      if (value.email) return String(value.email);
      if (value.phone) return String(value.phone);
      if (value.name) return String(value.name);
      if (value.value) return String(value.value);
    }
    return '';
  };

  const formatAssignees = (task) => {
    if (!task.assignees || task.assignees.length === 0) return '';
    return task.assignees.map((a) => a.username || a.email || a.initials || 'Unknown').join(', ');
  };

  const findStatusMeta = (statusName) => {
    const normalized = (statusName || '').trim().toLowerCase();
    return contactStatuses.find((s) => (s.status || '').trim().toLowerCase() === normalized) || null;
  };

  const handleStatusChange = async (taskId, newStatus) => {
    const oldContacts = contacts;
    const selectedMeta = findStatusMeta(newStatus);

    const updatedContacts = contacts.map((contact) => {
      if (contact.id !== taskId) return contact;
      return {
        ...contact,
        status: {
          ...contact.status,
          status: newStatus,
          color: selectedMeta?.color || contact.status?.color || '#87909e',
          type: selectedMeta?.type || contact.status?.type
        }
      };
    });
    setContacts(updatedContacts);

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Token ${token}`;
      }

      const response = await fetch('/api/clickup/contacts/', {
        method: 'POST',
        headers,
        body: JSON.stringify({ taskId, status: newStatus })
      });

      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success' && data.task) {
          setContacts((prev) => prev.map((c) => (c.id === taskId ? data.task : c)));
        }
      } else {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to update contact status.');
      }
    } catch (err) {
      console.error(err);
      alert('Failed to update contact status: ' + err.message);
      setContacts(oldContacts);
    }
  };

  const renderStatusSelect = (contact) => {
    const statusBg = contact.status?.color || '#87909e';
    const currentStatus = contact.status?.status || 'to do';
    const hasConfiguredStatuses = contactStatuses.length > 0;
    const currentInConfigured = !!findStatusMeta(currentStatus);

    return (
      <select
        value={currentStatus}
        onChange={(e) => handleStatusChange(contact.id, e.target.value)}
        onClick={(e) => e.stopPropagation()}
        style={{
          fontSize: '0.7rem',
          fontWeight: 600,
          padding: '0.15rem 1.25rem 0.15rem 0.5rem',
          borderRadius: '12px',
          backgroundColor: statusBg,
          color: '#ffffff',
          textTransform: 'uppercase',
          border: '1px solid rgba(0,0,0,0.05)',
          cursor: 'pointer',
          outline: 'none',
          appearance: 'none',
          WebkitAppearance: 'none',
          MozAppearance: 'none',
          backgroundImage: `url("data:image/svg+xml;utf8,<svg fill='white' height='24' viewBox='0 0 24 24' width='24' xmlns='http://www.w3.org/2000/svg'><path d='M7 10l5 5 5-5z'/><path d='M0 0h24v24H0z' fill='none'/></svg>")`,
          backgroundRepeat: 'no-repeat',
          backgroundPosition: 'right 2px center',
          backgroundSize: '12px',
          whiteSpace: 'nowrap'
        }}
      >
        {hasConfiguredStatuses ? contactStatuses.map((statusOption) => (
          <option key={statusOption.id || statusOption.status} value={statusOption.status} style={{ color: '#000000' }}>
            {statusOption.status}
          </option>
        )) : (
          <>
            <option value="to do" style={{ color: '#000000' }}>To Do</option>
            <option value="in progress" style={{ color: '#000000' }}>In Progress</option>
            <option value="complete" style={{ color: '#000000' }}>Complete</option>
          </>
        )}
        {hasConfiguredStatuses && !currentInConfigured && (
          <option value={currentStatus} style={{ color: '#000000' }}>{currentStatus}</option>
        )}
      </select>
    );
  };

  const renderDetailsTrigger = (contact) => {
    return (
      <button
        onClick={(e) => {
          e.stopPropagation();
          setContactActivities([]);
          setActivitiesError('');
          setSelectedContact(contact);
        }}
        title="View contact details"
        aria-label={`View details for ${contact.name}`}
        style={{
          border: '1px solid var(--border-color)',
          backgroundColor: '#ffffff',
          color: 'var(--text-muted)',
          borderRadius: '999px',
          width: '1.25rem',
          height: '1.25rem',
          fontSize: '0.75rem',
          lineHeight: 1,
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0
        }}
      >
        i
      </button>
    );
  };

  const fetchContacts = async () => {
    setLoading(true);
    setError('');
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Token ${token}`;
      }

      const query = showHiddenByShowAfter ? '?include_hidden_show_after=true' : '';
      const response = await fetch(`/api/clickup/contacts/${query}`, { headers });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to fetch contacts from ClickUp.');
      }

      const data = await response.json();
      setContacts(data.tasks || []);
      setContactStatuses(data.statuses || []);
      if (data.space?.name) setSpaceName(data.space.name);
      if (data.space?.id) setSpaceId(data.space.id);
      if (data.team_id) setTeamId(data.team_id);
    } catch (err) {
      console.error(err);
      setError(err.message || 'Network error occurred while loading contacts.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // In React StrictMode (dev), effects mount/unmount/remount once.
    // Deferring to next tick and clearing on cleanup avoids duplicate API calls.
    const timer = setTimeout(() => {
      fetchContacts();
    }, 0);

    return () => clearTimeout(timer);
  }, [token, showHiddenByShowAfter]);

  useEffect(() => {
    const fetchActivities = async () => {
      if (!selectedContact?.id) {
        setContactActivities([]);
        setActivitiesError('');
        setActivitiesLoading(false);
        return;
      }

      setActivitiesLoading(true);
      setActivitiesError('');
      try {
        const headers = { 'Content-Type': 'application/json' };
        if (token) {
          headers['Authorization'] = `Token ${token}`;
        }

        const response = await fetch(`/api/clickup/contacts/${selectedContact.id}/activities/`, { headers });
        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || 'Failed to load contact activities.');
        }

        const data = await response.json();
        setContactActivities(data.activities || []);
      } catch (err) {
        console.error(err);
        setActivitiesError(err.message || 'Failed to load contact activities.');
        setContactActivities([]);
      } finally {
        setActivitiesLoading(false);
      }
    };

    fetchActivities();
  }, [selectedContact, token]);

  const getTaskRank = (task) => {
    const rankRaw = getCustomFieldValue(task, 'rank');
    if (!rankRaw) return Infinity;
    const parsed = parseFloat(rankRaw);
    return isNaN(parsed) ? Infinity : parsed;
  };

  const getOrganization = (task) => {
    const orgField = task.custom_fields?.find(
      (cf) => cf.name?.trim().toLowerCase() === 'organization'
    );
    const rawValue = orgField?.value;

    if (Array.isArray(rawValue) && rawValue.length > 0) {
      const names = rawValue
        .map((item) => (item && typeof item === 'object' ? item.name : null))
        .filter((name) => typeof name === 'string' && name.trim());
      if (names.length > 0) {
        return names.join(', ');
      }
    }

    if (rawValue && typeof rawValue === 'object' && rawValue.name) {
      return String(rawValue.name);
    }
    if (typeof rawValue === 'string' && rawValue.trim()) {
      return rawValue;
    }
    return 'Uncategorized';
  };

  const getOrganizationRaw = (task) => {
    const orgField = task.custom_fields?.find(
      (cf) => cf.name?.trim().toLowerCase() === 'organization'
    );
    const rawValue = orgField?.value;

    if (Array.isArray(rawValue) && rawValue.length > 0) {
      const names = rawValue
        .map((item) => (item && typeof item === 'object' ? item.name : null))
        .filter((name) => typeof name === 'string' && name.trim());
      if (names.length > 0) {
        return names.join(', ');
      }
    }

    if (rawValue && typeof rawValue === 'object' && rawValue.name) {
      return String(rawValue.name);
    }
    if (typeof rawValue === 'string' && rawValue.trim()) {
      return rawValue;
    }
    return '';
  };

  const isScheduledTask = (task) => {
    return task.custom_fields?.some(
      (cf) => cf.name?.toLowerCase() === 'show after' && cf.value !== null && cf.value !== undefined && cf.value !== ''
    );
  };

  const formatDate = (timestamp) => {
    if (!timestamp) return '-';
    const date = new Date(Number(timestamp));
    return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  };

  const sortContacts = (taskList) => {
    return [...taskList].sort((a, b) => {
      const nameA = (a.name || '').toLowerCase();
      const nameB = (b.name || '').toLowerCase();
      const statusA = (a.status?.status || '').toLowerCase();
      const statusB = (b.status?.status || '').toLowerCase();
      const orgA = getOrganization(a).toLowerCase();
      const orgB = getOrganization(b).toLowerCase();
      const rankA = getTaskRank(a);
      const rankB = getTaskRank(b);

      if (sortBy === 'name') {
        const cmp = nameA.localeCompare(nameB);
        if (cmp !== 0) return cmp;
        return rankA - rankB;
      }

      if (sortBy === 'status') {
        const cmp = statusA.localeCompare(statusB);
        if (cmp !== 0) return cmp;
        return nameA.localeCompare(nameB);
      }

      if (sortBy === 'organization') {
        const cmp = orgA.localeCompare(orgB);
        if (cmp !== 0) return cmp;
        return nameA.localeCompare(nameB);
      }

      if (rankA !== rankB) return rankA - rankB;
      return nameA.localeCompare(nameB);
    });
  };

  const sortedContacts = sortContacts(contacts);

  const formatActivityDateTime = (timestamp) => {
    if (!timestamp) return '-';
    const date = new Date(Number(timestamp));
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const organizationOptions = Array.from(new Set(contacts.map((c) => getOrganization(c)))).sort((a, b) => a.localeCompare(b));
  const statusOptions = contactStatuses.length > 0
    ? contactStatuses.map((s) => s.status).filter(Boolean)
    : Array.from(new Set(contacts.map((c) => c.status?.status).filter(Boolean))).sort((a, b) => a.localeCompare(b));
  const activeFilterCount = (organizationFilter !== 'all' ? 1 : 0) + (statusFilter !== 'all' ? 1 : 0);
  const selectedContactMarkdown = (selectedContact?.markdown_description || selectedContact?.description || '').trim();

  const filteredSortedContacts = sortedContacts.filter((contact) => {
    const orgMatch = organizationFilter === 'all' || getOrganization(contact) === organizationFilter;
    const statusMatch = statusFilter === 'all' || (contact.status?.status || '').toLowerCase() === statusFilter.toLowerCase();
    return orgMatch && statusMatch;
  });

  const groupedByOrg = {};
  filteredSortedContacts.forEach((contact) => {
    const org = getOrganization(contact);
    if (!groupedByOrg[org]) groupedByOrg[org] = [];
    groupedByOrg[org].push(contact);
  });

  const sortedOrgNames = Object.keys(groupedByOrg).sort((a, b) => a.localeCompare(b));

  if (loading) {
    return (
      <div style={{ padding: '2rem 0', color: 'var(--text-muted)' }}>
        Loading Consulting contacts...
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-message" style={{ margin: '2rem 0', padding: '1.5rem', borderLeft: '4px solid #dc2626' }}>
        <strong>Error Loading Contacts</strong>
        <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.9rem' }}>{error}</p>
        <button
          onClick={fetchContacts}
          className="editorial-button"
          style={{ width: 'auto', marginTop: '1rem', padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <section className="margin-top">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem', gap: '1rem', flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0, fontFamily: 'var(--font-serif)', fontSize: '1.75rem' }}>Contacts</h2>
        {teamId && spaceId ? (
          <a
            href={`https://app.clickup.com/${teamId}/v/l/s/${spaceId}`}
            target="_blank"
            rel="noopener noreferrer"
            className="badge badge-active"
            style={{ fontSize: '0.75rem', textTransform: 'uppercase', textDecoration: 'none' }}
          >
            Space: {spaceName} | List: Contacts
          </a>
        ) : (
          <span className="badge badge-active" style={{ fontSize: '0.75rem', textTransform: 'uppercase' }}>
            Space: {spaceName} | List: Contacts
          </span>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button
            onClick={() => handleViewModeChange('group')}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: viewMode === 'group' ? 'var(--text-color)' : 'transparent',
              color: viewMode === 'group' ? 'var(--bg-color)' : 'var(--text-color)',
              border: '1px solid var(--text-color)',
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              fontSize: '0.8rem',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'var(--transition-smooth)'
            }}
          >
            Group By Organization
          </button>
          <button
            onClick={() => handleViewModeChange('flat')}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: viewMode === 'flat' ? 'var(--text-color)' : 'transparent',
              color: viewMode === 'flat' ? 'var(--bg-color)' : 'var(--text-color)',
              border: '1px solid var(--text-color)',
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              fontSize: '0.8rem',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'var(--transition-smooth)'
            }}
          >
            Flat List
          </button>
          <button
            onClick={() => handleViewModeChange('compact')}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: viewMode === 'compact' ? 'var(--text-color)' : 'transparent',
              color: viewMode === 'compact' ? 'var(--bg-color)' : 'var(--text-color)',
              border: '1px solid var(--text-color)',
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              fontSize: '0.8rem',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'var(--transition-smooth)'
            }}
          >
            Compact List
          </button>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            style={{
              padding: '0.5rem 0.75rem',
              border: '1px solid var(--border-color)',
              borderRadius: '4px',
              fontFamily: 'var(--font-sans)',
              fontSize: '0.8rem',
              color: 'var(--text-color)',
              backgroundColor: '#ffffff'
            }}
          >
            <option value="name">Sort: Name</option>
            <option value="status">Sort: Status</option>
            <option value="organization">Sort: Organization</option>
            <option value="rank">Sort: Rank</option>
          </select>

          <button
            onClick={openFiltersPopup}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: activeFilterCount > 0 ? 'var(--text-color)' : 'transparent',
              color: activeFilterCount > 0 ? 'var(--bg-color)' : 'var(--text-color)',
              border: '1px solid var(--text-color)',
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              fontSize: '0.8rem',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'var(--transition-smooth)'
            }}
          >
            Filters{activeFilterCount > 0 ? ` (${activeFilterCount})` : ''}
          </button>

          <button
            onClick={() => setShowHiddenByShowAfter(prev => !prev)}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: showHiddenByShowAfter ? 'var(--text-color)' : 'transparent',
              color: showHiddenByShowAfter ? 'var(--bg-color)' : 'var(--text-color)',
              border: '1px solid var(--text-color)',
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              fontSize: '0.8rem',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'var(--transition-smooth)'
            }}
          >
            {showHiddenByShowAfter ? 'Hide Scheduled' : 'Show Scheduled'}
          </button>
        </div>
      </div>

      {filteredSortedContacts.length === 0 ? (
        <p style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
          No contacts match the selected filters.
        </p>
      ) : viewMode === 'group' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          {sortedOrgNames.map((orgName) => (
            <div key={orgName}>
              <h3
                style={{
                  fontFamily: 'var(--font-sans)',
                  fontSize: '1rem',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: 'var(--text-muted)',
                  borderBottom: '1.5px solid var(--border-color)',
                  paddingBottom: '0.4rem',
                  marginBottom: '1rem',
                  marginTop: 0
                }}
              >
                {orgName} ({groupedByOrg[orgName].length})
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {groupedByOrg[orgName].map((contact) => {
                  const rankVal = getTaskRank(contact);
                  return (
                    <div
                      key={contact.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '0.7rem 0.95rem',
                        border: '1px solid var(--border-color)',
                        borderRadius: '6px',
                        backgroundColor: '#ffffff'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
                        <span
                          style={{
                            fontSize: '0.7rem',
                            fontWeight: 700,
                            padding: '0.15rem 0.35rem',
                            borderRadius: '3px',
                            backgroundColor: rankVal === Infinity ? 'var(--border-color)' : 'var(--accent-color)',
                            color: rankVal === Infinity ? 'var(--text-muted)' : '#ffffff',
                            whiteSpace: 'nowrap'
                          }}
                        >
                          {rankVal === Infinity ? 'RANK' : `#${rankVal}`}
                        </span>
                        <a
                          href={`https://app.clickup.com/t/${contact.id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: 'var(--text-color)', textDecoration: 'none', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                        >
                          {contact.name}
                        </a>
                        {renderDetailsTrigger(contact)}
                        {showHiddenByShowAfter && isScheduledTask(contact) && (
                          <span title="Scheduled contact" style={{ color: 'var(--accent-color)' }}>⏰</span>
                        )}
                      </div>
                      {renderStatusSelect(contact)}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      ) : viewMode === 'compact' ? (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-color)',
            borderRadius: '6px',
            overflow: 'hidden',
            boxShadow: '0 1px 3px rgba(0,0,0,0.02)'
          }}
        >
          {filteredSortedContacts.map((contact, idx) => {
            const rankVal = getTaskRank(contact);
            const organization = getOrganization(contact);
            const isLast = idx === filteredSortedContacts.length - 1;
            return (
              <div
                key={contact.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.65rem 0.95rem',
                  borderBottom: isLast ? 'none' : '1px solid var(--border-color)',
                  gap: '1rem'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
                  <span
                    style={{
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      padding: '0.15rem 0.35rem',
                      borderRadius: '3px',
                      backgroundColor: rankVal === Infinity ? 'var(--border-color)' : 'var(--accent-color)',
                      color: rankVal === Infinity ? 'var(--text-muted)' : '#ffffff',
                      whiteSpace: 'nowrap'
                    }}
                  >
                    {rankVal === Infinity ? 'RANK' : `#${rankVal}`}
                  </span>
                  <a
                    href={`https://app.clickup.com/t/${contact.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: 'var(--text-color)', textDecoration: 'none', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                  >
                    {contact.name} ({organization})
                  </a>
                  {renderDetailsTrigger(contact)}
                  {showHiddenByShowAfter && isScheduledTask(contact) && (
                    <span title="Scheduled contact" style={{ color: 'var(--accent-color)' }}>⏰</span>
                  )}
                </div>

                {renderStatusSelect(contact)}
              </div>
            );
          })}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {filteredSortedContacts.map((contact) => {
            const email = getCustomFieldValue(contact, 'email');
            const phone = getCustomFieldValue(contact, 'phone');
            const company = getCustomFieldValue(contact, 'company');
            const owner = formatAssignees(contact);
            const organization = getOrganization(contact);
            const rankVal = getTaskRank(contact);
            const dueDate = formatDate(contact.due_date);

            return (
              <div
                key={contact.id}
                style={{
                  background: '#ffffff',
                  border: '1px solid var(--border-color)',
                  borderRadius: '6px',
                  padding: '1rem 1.1rem',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.02)'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
                    <a
                      href={`https://app.clickup.com/t/${contact.id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: 'var(--text-color)', textDecoration: 'none', fontWeight: 600 }}
                    >
                      {contact.name}
                    </a>
                    {renderDetailsTrigger(contact)}
                    {showHiddenByShowAfter && isScheduledTask(contact) && (
                      <span title="Scheduled contact" style={{ color: 'var(--accent-color)' }}>⏰</span>
                    )}
                  </div>
                  {renderStatusSelect(contact)}
                </div>

                <div style={{ marginTop: '0.55rem', fontSize: '0.85rem', color: 'var(--text-muted)', display: 'flex', gap: '0.9rem', flexWrap: 'wrap' }}>
                  <span>Organization: {organization}</span>
                  <span>Rank: {rankVal === Infinity ? '-' : rankVal}</span>
                  <span>Status: {contact.status?.status || '-'}</span>
                  <span>Due: {dueDate}</span>
                </div>

                {(email || phone || company || owner) && (
                  <div style={{ marginTop: '0.55rem', fontSize: '0.85rem', color: 'var(--text-muted)', display: 'flex', gap: '0.9rem', flexWrap: 'wrap' }}>
                    {company && <span>Company: {company}</span>}
                    {email && <span>Email: {email}</span>}
                    {phone && <span>Phone: {phone}</span>}
                    {owner && <span>Owner: {owner}</span>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {showFiltersPopup && (
        <div
          onClick={() => setShowFiltersPopup(false)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.45)',
            zIndex: 1100,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1rem'
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: '100%',
              maxWidth: '520px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              boxShadow: '0 12px 30px rgba(0,0,0,0.18)',
              overflow: 'hidden'
            }}
          >
            <div style={{ padding: '1rem 1.15rem', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontFamily: 'var(--font-serif)', fontSize: '1.2rem' }}>Filters</h3>
              <button
                onClick={() => setShowFiltersPopup(false)}
                style={{
                  border: '1px solid var(--border-color)',
                  background: '#ffffff',
                  borderRadius: '4px',
                  padding: '0.25rem 0.5rem',
                  cursor: 'pointer',
                  fontSize: '0.8rem'
                }}
              >
                Close
              </button>
            </div>

            <div style={{ padding: '1rem 1.15rem', display: 'grid', gap: '0.9rem' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '0.4rem', fontSize: '0.82rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Organization
                </label>
                <select
                  value={draftOrganizationFilter}
                  onChange={(e) => setDraftOrganizationFilter(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.6rem 0.75rem',
                    border: '1px solid var(--border-color)',
                    borderRadius: '4px',
                    fontFamily: 'var(--font-sans)',
                    fontSize: '0.85rem',
                    color: 'var(--text-color)',
                    backgroundColor: '#ffffff'
                  }}
                >
                  <option value="all">All Organizations</option>
                  {organizationOptions.map((org) => (
                    <option key={org} value={org}>{org}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '0.4rem', fontSize: '0.82rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Status
                </label>
                <select
                  value={draftStatusFilter}
                  onChange={(e) => setDraftStatusFilter(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.6rem 0.75rem',
                    border: '1px solid var(--border-color)',
                    borderRadius: '4px',
                    fontFamily: 'var(--font-sans)',
                    fontSize: '0.85rem',
                    color: 'var(--text-color)',
                    backgroundColor: '#ffffff'
                  }}
                >
                  <option value="all">All Statuses</option>
                  {statusOptions.map((statusName) => (
                    <option key={statusName} value={statusName}>{statusName}</option>
                  ))}
                </select>
              </div>
            </div>

            <div style={{ padding: '0.9rem 1.15rem', borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', gap: '0.75rem' }}>
              <button
                onClick={clearFilters}
                style={{
                  padding: '0.5rem 0.9rem',
                  border: '1px solid var(--border-color)',
                  backgroundColor: '#ffffff',
                  color: 'var(--text-color)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '0.82rem'
                }}
              >
                Clear
              </button>
              <button
                onClick={applyFilters}
                style={{
                  padding: '0.5rem 1rem',
                  border: '1px solid var(--text-color)',
                  backgroundColor: 'var(--text-color)',
                  color: 'var(--bg-color)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '0.82rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  fontWeight: 600
                }}
              >
                Apply
              </button>
            </div>
          </div>
        </div>
      )}

      {selectedContact && (
        <div
          onClick={() => setSelectedContact(null)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.45)',
            zIndex: 1200,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1rem'
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: '100%',
              maxWidth: '640px',
              maxHeight: '85vh',
              overflowY: 'auto',
              backgroundColor: '#ffffff',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              boxShadow: '0 12px 30px rgba(0,0,0,0.18)'
            }}
          >
            <div style={{ padding: '1rem 1.15rem', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontFamily: 'var(--font-serif)', fontSize: '1.2rem' }}>
                <a
                  href={`https://app.clickup.com/t/${selectedContact.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: 'var(--text-color)', textDecoration: 'none' }}
                >
                  {selectedContact.name}
                </a>
              </h3>
              <button
                onClick={() => setSelectedContact(null)}
                style={{
                  border: '1px solid var(--border-color)',
                  background: '#ffffff',
                  borderRadius: '4px',
                  padding: '0.25rem 0.5rem',
                  cursor: 'pointer',
                  fontSize: '0.8rem'
                }}
              >
                Close
              </button>
            </div>

            <div style={{ padding: '1rem 1.15rem', display: 'grid', gap: '0.65rem', fontSize: '0.9rem' }}>
              {getOrganizationRaw(selectedContact) && (
                <div><strong>Organization:</strong> {getOrganizationRaw(selectedContact)}</div>
              )}
              {selectedContactMarkdown && (
                <div style={{ marginTop: '0.35rem' }}>
                  <strong>Description:</strong>
                  <div style={{ marginTop: '0.3rem', color: 'var(--text-muted)' }} className="markdown-body">
                    <MarkdownBody>{selectedContactMarkdown}</MarkdownBody>
                  </div>
                </div>
              )}
              {selectedContact.status?.status?.trim() && <div><strong>Status:</strong> {selectedContact.status.status}</div>}
              {getCustomFieldValue(selectedContact, 'email') && <div><strong>Email:</strong> {getCustomFieldValue(selectedContact, 'email')}</div>}
              {getCustomFieldValue(selectedContact, 'phone') && <div><strong>Phone:</strong> {getCustomFieldValue(selectedContact, 'phone')}</div>}
              {(activitiesLoading || activitiesError || contactActivities.length > 0) && (
                <div style={{ marginTop: '0.35rem' }}>
                  <strong>Activities:</strong>
                  {activitiesLoading ? (
                    <div style={{ marginTop: '0.4rem', color: 'var(--text-muted)' }}>Loading activities...</div>
                  ) : activitiesError ? (
                    <div style={{ marginTop: '0.4rem', color: '#b91c1c' }}>{activitiesError}</div>
                  ) : (
                    <div style={{ marginTop: '0.5rem', display: 'grid', gap: '0.55rem' }}>
                      {contactActivities.map((activity) => (
                        <div
                          key={activity.id || `${activity.timestamp}-${activity.user}`}
                          style={{
                            border: '1px solid var(--border-color)',
                            borderRadius: '6px',
                            padding: '0.55rem 0.65rem',
                            backgroundColor: '#fafafa'
                          }}
                        >
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>
                            {activity.user || 'Unknown'} | {formatActivityDateTime(activity.timestamp)}
                          </div>
                          <div style={{ fontSize: '0.86rem', whiteSpace: 'pre-line' }}>
                            {activity.text || '(No text)'}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
