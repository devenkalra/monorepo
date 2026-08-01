import { useEffect, useMemo, useState } from 'react';
import { MarkdownBody } from './MarkdownBody';

function slugify(title) {
  return String(title || '')
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/[\s_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 200);
}

function normalizeEscapedNewlines(text) {
  if (!text) return text || '';
  let out = String(text);
  for (let i = 0; i < 3; i++) {
    const next = out
      .replace(/\\r\\n/g, '\n')
      .replace(/\\n/g, '\n')
      .replace(/\\r/g, '\n');
    if (next === out) break;
    out = next;
  }
  return out;
}

const EMPTY_FORM = {
  title: '',
  slug: '',
  category: 'Notebook',
  roles_with_access: '',
  allowed_emails: '',
  render_as_html: false,
  content: '',
};

function formFromPage(page) {
  if (!page) return { ...EMPTY_FORM };
  return {
    title: page.title || '',
    slug: page.slug || '',
    category: page.category || '',
    roles_with_access: page.roles_with_access || '',
    allowed_emails: page.allowed_emails || '',
    render_as_html: !!page.render_as_html,
    content: page.content || '',
  };
}

/**
 * Admin-like page create/edit form: metadata + content editor + live preview.
 */
export function NotesPageEditor({
  mode = 'create',
  initialValues = null,
  parentLabel,
  busy,
  error,
  onCancel,
  onSave,
  navigate,
}) {
  const isEdit = mode === 'edit';
  const [form, setForm] = useState(() => formFromPage(initialValues));
  const [slugTouched, setSlugTouched] = useState(isEdit);
  const [localError, setLocalError] = useState('');

  useEffect(() => {
    setForm(formFromPage(initialValues));
    setSlugTouched(isEdit);
    setLocalError('');
  }, [initialValues, isEdit, mode]);

  const setField = (key, value) => {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      if (key === 'title' && !slugTouched && !isEdit) {
        next.slug = slugify(value);
      }
      return next;
    });
  };

  const previewContent = useMemo(
    () => normalizeEscapedNewlines(form.content),
    [form.content]
  );

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError('');
    const title = form.title.trim();
    const slug = (form.slug.trim() || slugify(title)).slice(0, 200);
    if (!title) {
      setLocalError('Title is required.');
      return;
    }
    if (!slug) {
      setLocalError('Slug is required.');
      return;
    }
    await onSave({
      title,
      slug,
      category: form.category.trim(),
      roles_with_access: form.roles_with_access.trim(),
      allowed_emails: form.allowed_emails.trim(),
      render_as_html: !!form.render_as_html,
      content: normalizeEscapedNewlines(form.content),
    });
  };

  return (
    <div className="notes-page-editor">
      <header className="notes-page-editor-header">
        <div>
          <span className="notes-sidebar-kicker">{isEdit ? 'Edit page' : 'New page'}</span>
          <h2>{isEdit ? 'Edit page' : 'Create page'}</h2>
          <p className="notes-page-editor-dest">
            {isEdit ? (
              <>
                Editing: <strong>{initialValues?.slug || form.slug}</strong>
              </>
            ) : (
              <>
                Saves into: <strong>{parentLabel || 'Notes (root)'}</strong>
              </>
            )}
          </p>
        </div>
        <div className="notes-page-editor-actions">
          <button type="button" className="notes-btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="submit"
            form="notes-page-editor-form"
            className="notes-btn notes-btn--primary"
            disabled={busy}
          >
            {busy ? 'Saving…' : isEdit ? 'Save changes' : 'Save page'}
          </button>
        </div>
      </header>

      {(error || localError) && (
        <p className="notes-error notes-error--toolbar">{error || localError}</p>
      )}

      <div className="notes-page-editor-split">
        <form id="notes-page-editor-form" className="notes-page-editor-form" onSubmit={handleSubmit}>
          <div className="notes-field-grid">
            <label className="notes-field">
              <span>Title</span>
              <input
                type="text"
                value={form.title}
                onChange={(e) => setField('title', e.target.value)}
                required
                autoFocus
              />
            </label>
            <label className="notes-field">
              <span>Slug</span>
              <input
                type="text"
                value={form.slug}
                onChange={(e) => {
                  setSlugTouched(true);
                  setField('slug', e.target.value);
                }}
                required
                pattern="[-a-zA-Z0-9_]+"
                title="Letters, numbers, hyphens, underscores"
              />
            </label>
            <label className="notes-field">
              <span>Category</span>
              <input
                type="text"
                value={form.category}
                onChange={(e) => setField('category', e.target.value)}
              />
            </label>
            <label className="notes-field">
              <span>Roles with access</span>
              <input
                type="text"
                value={form.roles_with_access}
                onChange={(e) => setField('roles_with_access', e.target.value)}
                placeholder="blank = public; e.g. user, superuser"
              />
            </label>
            <label className="notes-field notes-field--wide">
              <span>Allowed emails</span>
              <input
                type="text"
                value={form.allowed_emails}
                onChange={(e) => setField('allowed_emails', e.target.value)}
                placeholder="Optional comma-separated emails"
              />
            </label>
            <label className="notes-field notes-field--check">
              <input
                type="checkbox"
                checked={form.render_as_html}
                onChange={(e) => setField('render_as_html', e.target.checked)}
              />
              <span>Render as HTML</span>
            </label>
          </div>

          <label className="notes-field notes-field--content">
            <span>Content {form.render_as_html ? '(HTML)' : '(Markdown)'}</span>
            <textarea
              value={form.content}
              onChange={(e) => setField('content', e.target.value)}
              rows={18}
              spellCheck
              placeholder={
                form.render_as_html
                  ? '<h1>Title</h1>\n<p>Content…</p>'
                  : '# Title\n\nWrite markdown here…'
              }
            />
          </label>
        </form>

        <aside className="notes-page-editor-preview" aria-label="Live preview">
          <div className="notes-page-editor-preview-head">
            <strong>Live Preview</strong>
            <span className={`notes-preview-mode-badge ${form.render_as_html ? 'html' : 'markdown'}`}>
              {form.render_as_html ? 'HTML' : 'Markdown'}
            </span>
          </div>
          <div className="notes-page-editor-preview-body markdown-body">
            {form.title && <h1>{form.title}</h1>}
            {form.render_as_html ? (
              <div dangerouslySetInnerHTML={{ __html: previewContent || '<p class="notes-muted">Nothing to preview yet.</p>' }} />
            ) : previewContent.trim() ? (
              <MarkdownBody navigate={navigate}>{previewContent}</MarkdownBody>
            ) : (
              <p className="notes-muted" style={{ padding: 0 }}>
                Nothing to preview yet.
              </p>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
