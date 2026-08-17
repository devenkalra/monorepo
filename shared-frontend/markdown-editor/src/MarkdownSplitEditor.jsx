import { useCallback, useRef, useState } from 'react';
import { MarkdownBody } from './MarkdownBody';
import { scrollPreviewToSourceLine, textareaTopSourceLine } from './scrollSync';
import './markdown-editor.css';

export function MarkdownSplitEditor({
  value,
  onChange,
  placeholder = '# Title\n\nWrite markdown here…',
  disabled = false,
}) {
  const [showInput, setShowInput] = useState(true);
  const [showPreview, setShowPreview] = useState(true);
  const [syncScroll, setSyncScroll] = useState(true);
  const inputRef = useRef(null);
  const previewRef = useRef(null);

  const syncPreviewToInput = useCallback(() => {
    if (!syncScroll || !showInput || !showPreview) return;
    const input = inputRef.current;
    const preview = previewRef.current;
    if (!input || !preview) return;
    scrollPreviewToSourceLine(preview, textareaTopSourceLine(input));
  }, [syncScroll, showInput, showPreview]);

  return (
    <div className="md-split">
      <div className="md-split-toolbar">
        <label>
          <input
            type="checkbox"
            checked={showInput}
            onChange={(e) => setShowInput(e.target.checked || !showPreview)}
          />
          Editor
        </label>
        <label>
          <input
            type="checkbox"
            checked={showPreview}
            onChange={(e) => setShowPreview(e.target.checked || !showInput)}
          />
          Preview
        </label>
        <label>
          <input
            type="checkbox"
            checked={syncScroll}
            disabled={!showInput || !showPreview}
            onChange={(e) => setSyncScroll(e.target.checked)}
          />
          Sync scroll
        </label>
      </div>
      <div
        className={`md-split-panes${showInput ? '' : ' hide-input'}${showPreview ? '' : ' hide-preview'}`}
      >
        <label className="md-split-input">
          <span>Markdown</span>
          <textarea
            ref={inputRef}
            value={value}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
            onScroll={syncPreviewToInput}
            spellCheck
            placeholder={placeholder}
          />
        </label>
        <aside className="md-split-preview" aria-label="Live preview">
          <div className="md-split-preview-head">Live preview</div>
          <div ref={previewRef} className="md-split-preview-body">
            {String(value || '').trim() ? (
              <MarkdownBody sourceLines>{value}</MarkdownBody>
            ) : (
              <p className="md-split-empty">Nothing to preview yet.</p>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
