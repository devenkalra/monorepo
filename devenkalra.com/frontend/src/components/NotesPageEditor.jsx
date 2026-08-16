import { useEffect, useMemo, useRef, useState } from 'react';
import { MarkdownBody } from './MarkdownBody';
import { scrollPreviewToSourceLine, stampHtmlSourceLines, textareaTopSourceLine } from '../utils/notesScrollSync';
import './NotesApp.css';

const AUTOSAVE_DEBOUNCE_MS = 10_000;

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

function payloadFromForm(form) {
  const title = form.title.trim();
  const slug = (form.slug.trim() || slugify(title)).slice(0, 200);
  return {
    title,
    slug,
    category: form.category.trim(),
    roles_with_access: form.roles_with_access.trim(),
    allowed_emails: form.allowed_emails.trim(),
    render_as_html: !!form.render_as_html,
    content: normalizeEscapedNewlines(form.content),
  };
}

function serializePayload(payload) {
  return JSON.stringify(payload);
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
  const pageKey = isEdit
    ? String(initialValues?.id ?? initialValues?.slug ?? '')
    : 'create';

  const [form, setForm] = useState(() => formFromPage(initialValues));
  const [slugTouched, setSlugTouched] = useState(isEdit);
  const [localError, setLocalError] = useState('');
  const [lastSavedKey, setLastSavedKey] = useState(() =>
    isEdit ? serializePayload(payloadFromForm(formFromPage(initialValues))) : ''
  );
  const [autoSaving, setAutoSaving] = useState(false);
  const [saveHint, setSaveHint] = useState('');
  const [showInput, setShowInput] = useState(true);
  const [showPreview, setShowPreview] = useState(true);
  const [syncScroll, setSyncScroll] = useState(true);
  const inputRef = useRef(null);
  const previewRef = useRef(null);

  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;
  const autoSavingRef = useRef(false);
  const formRef = useRef(form);
  formRef.current = form;

  // Reset form only when switching pages / modes — not after autosave updates preview.
  useEffect(() => {
    const next = formFromPage(initialValues);
    setForm(next);
    setSlugTouched(isEdit);
    setLocalError('');
    setSaveHint('');
    setLastSavedKey(isEdit ? serializePayload(payloadFromForm(next)) : '');
    // initialValues read intentionally when pageKey/mode changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageKey, isEdit, mode]);

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

  const syncPreviewToInput = () => {
    if (!syncScroll || !showInput || !showPreview) return;
    const src = inputRef.current;
    const dst = previewRef.current;
    if (!src || !dst) return;
    if (form.render_as_html) {
      stampHtmlSourceLines(dst, previewContent);
    }
    const line = textareaTopSourceLine(src);
    if (scrollPreviewToSourceLine(dst, line)) return;
    const srcMax = src.scrollHeight - src.clientHeight;
    const dstMax = dst.scrollHeight - dst.clientHeight;
    if (srcMax <= 0 || dstMax <= 0) {
      dst.scrollTop = 0;
      return;
    }
    dst.scrollTop = (src.scrollTop / srcMax) * dstMax;
  };

  useEffect(() => {
    if (!syncScroll) return undefined;
    const frame = requestAnimationFrame(syncPreviewToInput);
    return () => cancelAnimationFrame(frame);
  }, [syncScroll, showInput, showPreview, previewContent, form.render_as_html]);

  useEffect(() => {
    const dst = previewRef.current;
    if (!dst || !syncScroll) return undefined;
    const onMedia = () => syncPreviewToInput();
    dst.querySelectorAll('img, iframe').forEach((el) => {
      el.addEventListener('load', onMedia);
    });
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(onMedia);
    ro?.observe(dst);
    return () => {
      dst.querySelectorAll('img, iframe').forEach((el) => {
        el.removeEventListener('load', onMedia);
      });
      ro?.disconnect();
    };
  }, [syncScroll, previewContent, form.render_as_html]);

  const toggleInput = (checked) => {
    if (!checked && !showPreview) return;
    setShowInput(checked);
  };

  const togglePreview = (checked) => {
    if (!checked && !showInput) return;
    setShowPreview(checked);
  };

  const draftPayload = useMemo(() => payloadFromForm(form), [form]);
  const draftKey = useMemo(() => serializePayload(draftPayload), [draftPayload]);
  const isDirty = isEdit && draftKey !== lastSavedKey;
  const draftValid = Boolean(draftPayload.title && draftPayload.slug);

  useEffect(() => {
    if (!isEdit || !isDirty || !draftValid || busy || autoSaving) {
      return undefined;
    }

    const timer = setTimeout(async () => {
      if (autoSavingRef.current) return;
      const payload = payloadFromForm(formRef.current);
      if (!payload.title || !payload.slug) return;

      autoSavingRef.current = true;
      setAutoSaving(true);
      setSaveHint('Saving…');
      setLocalError('');
      try {
        const ok = await onSaveRef.current(payload, { close: false });
        if (ok) {
          setLastSavedKey(serializePayload(payload));
          setSaveHint('Saved');
        } else {
          setSaveHint('Autosave failed');
        }
      } catch {
        setSaveHint('Autosave failed');
      } finally {
        autoSavingRef.current = false;
        setAutoSaving(false);
      }
    }, AUTOSAVE_DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [isEdit, isDirty, draftValid, draftKey, busy, autoSaving]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError('');
    const payload = payloadFromForm(form);
    if (!payload.title) {
      setLocalError('Title is required.');
      return;
    }
    if (!payload.slug) {
      setLocalError('Slug is required.');
      return;
    }
    const ok = await onSave(payload, isEdit ? { close: true } : undefined);
    if (ok !== false && isEdit) {
      setLastSavedKey(serializePayload(payload));
    }
  };

  let statusText = '';
  if (isEdit) {
    if (autoSaving || (busy && isDirty)) statusText = 'Saving…';
    else if (isDirty && draftValid) statusText = 'Unsaved changes';
    else if (saveHint === 'Saved' && !isDirty) statusText = 'Saved';
    else if (saveHint === 'Autosave failed') statusText = 'Autosave failed';
  }

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
                {statusText ? (
                  <>
                    {' · '}
                    <span
                      className={`notes-save-status${
                        statusText === 'Autosave failed' ? ' is-error' : ''
                      }${statusText === 'Unsaved changes' ? ' is-dirty' : ''}`}
                    >
                      {statusText}
                    </span>
                  </>
                ) : null}
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
            disabled={busy || autoSaving}
          >
            {busy ? 'Saving…' : isEdit ? 'Save changes' : 'Save page'}
          </button>
        </div>
      </header>

      {(error || localError) && (
        <p className="notes-error notes-error--toolbar">{error || localError}</p>
      )}

      <form id="notes-page-editor-form" className="notes-page-editor-form" onSubmit={handleSubmit}>
        <div className="notes-page-editor-meta">
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
        </div>

        <div className="notes-page-editor-toolbar">
          <label className="notes-field notes-field--check">
            <input
              type="checkbox"
              checked={showInput}
              onChange={(e) => toggleInput(e.target.checked)}
            />
            <span>Editor</span>
          </label>
          <label className="notes-field notes-field--check">
            <input
              type="checkbox"
              checked={showPreview}
              onChange={(e) => togglePreview(e.target.checked)}
            />
            <span>Preview</span>
          </label>
          <label
            className="notes-field notes-field--check"
            title="Keep the preview scrolled to about the same place as the editor"
          >
            <input
              type="checkbox"
              checked={syncScroll}
              disabled={!showInput || !showPreview}
              onChange={(e) => setSyncScroll(e.target.checked)}
            />
            <span>Sync scroll</span>
          </label>
        </div>

        <div
          className={`notes-page-editor-split${showInput ? '' : ' hide-input'}${
            showPreview ? '' : ' hide-preview'
          }`}
        >
          <label className="notes-field notes-field--content">
            <span className="notes-page-editor-pane-head">
              Content {form.render_as_html ? '(HTML)' : '(Markdown)'}
            </span>
            <textarea
              ref={inputRef}
              value={form.content}
              onChange={(e) => setField('content', e.target.value)}
              onScroll={syncPreviewToInput}
              spellCheck
              placeholder={
                form.render_as_html
                  ? '<h1>Title</h1>\n<p>Content…</p>'
                  : '# Title\n\nWrite markdown here…'
              }
            />
          </label>

          <aside className="notes-page-editor-preview" aria-label="Live preview">
            <div className="notes-page-editor-preview-head notes-page-editor-pane-head">
              <strong>Live Preview</strong>
              <span className={`notes-preview-mode-badge ${form.render_as_html ? 'html' : 'markdown'}`}>
                {form.render_as_html ? 'HTML' : 'Markdown'}
              </span>
            </div>
            <div ref={previewRef} className="notes-page-editor-preview-body markdown-body">
              {form.title && <h1>{form.title}</h1>}
              {form.render_as_html ? (
                <div
                  dangerouslySetInnerHTML={{
                    __html: previewContent || '<p class="notes-muted">Nothing to preview yet.</p>',
                  }}
                />
              ) : previewContent.trim() ? (
                <MarkdownBody navigate={navigate} sourceLines>
                  {previewContent}
                </MarkdownBody>
              ) : (
                <p className="notes-muted" style={{ padding: 0 }}>
                  Nothing to preview yet.
                </p>
              )}
            </div>
          </aside>
        </div>
      </form>
    </div>
  );
}
