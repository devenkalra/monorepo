import React, { useCallback, useRef, useState } from 'react';
import api from '../services/api';

function collectDropPayload(event) {
  const dt = event.dataTransfer || event.clipboardData;
  const types = Array.from(dt?.types || []);
  if (types.includes('application/x-entity-photo')) {
    return { files: [], html: '', text: '', url: '' };
  }
  const files = dt?.files ? Array.from(dt.files) : [];
  const html = dt?.getData?.('text/html') || '';
  const uriList = dt?.getData?.('text/uri-list') || '';
  const text = dt?.getData?.('text/plain') || dt?.getData?.('text') || '';
  const url = uriList.split(/\r?\n/).find((line) => line && !line.startsWith('#') && /^https?:\/\//i.test(line)) || '';
  return { files, html, text, url };
}

function isEmptyPayload(payload) {
  return !payload.text && !payload.html && !payload.url && payload.files.length === 0;
}

function flattenErrorValue(value) {
  if (value == null || value === '') return '';
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(flattenErrorValue).filter(Boolean).join('\n');
  if (typeof value === 'object') {
    return Object.entries(value)
      .map(([key, item]) => {
        const text = flattenErrorValue(item);
        if (!text) return '';
        return key === 'detail' || key === 'non_field_errors' ? text : `${key}: ${text}`;
      })
      .filter(Boolean)
      .join('\n');
  }
  return String(value);
}

function formatDropError(status, raw, data) {
  if (status === 401 || status === 403) {
    return 'You are not signed in, or the session expired. Refresh and log in, then try the drop again.';
  }
  if (status === 413) {
    return 'That drop was too large for the server to accept. Try less HTML, fewer files, or a shorter page.';
  }
  const fromJson = flattenErrorValue(data?.detail) || flattenErrorValue(data?.error) || flattenErrorValue(data);
  if (fromJson) return fromJson;
  const trimmed = (raw || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  if (trimmed) return `HTTP ${status}: ${trimmed.slice(0, 800)}`;
  if (status) return `Could not create an entity from that drop (HTTP ${status}).`;
  return 'Could not create an entity from that drop.';
}

export default function DropCreateZone({ onCreated, entityType, size = 'lg', hidden = false }) {
  const [active, setActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [summary, setSummary] = useState(null);
  const dragDepth = useRef(0);
  const label = entityType ? `Drop to create ${entityType}` : 'Drop to create';
  const isCompact = size === 'md';

  const ingest = useCallback(async (payload) => {
    if (busy || isEmptyPayload(payload)) return;
    setBusy(true);
    setError('');
    setSummary(null);
    try {
      const form = new FormData();
      if (payload.text) form.append('text', payload.text);
      if (payload.html) form.append('html', payload.html);
      if (payload.url) form.append('url', payload.url);
      if (entityType) form.append('type', entityType);
      payload.files.forEach((file) => form.append('files', file));
      const response = await api.fetch('/api/entities/from-drop/', {
        method: 'POST',
        body: form,
        headers: {},
      });
      const raw = await response.text();
      let data = {};
      if (raw) {
        try {
          data = JSON.parse(raw);
        } catch {
          data = {};
        }
      }
      if (!response.ok) {
        throw new Error(formatDropError(response.status, raw, data));
      }
      const { drop_summary: nextSummary, ...entity } = data;
      setSummary(nextSummary || {
        action: 'created',
        lines: [`Created ${entity.type || 'entity'} “${entity.display || 'Untitled'}”.`],
      });
      onCreated(entity);
    } catch (err) {
      setError(err.message || 'Could not create an entity from that drop.');
    } finally {
      setBusy(false);
      setActive(false);
      dragDepth.current = 0;
    }
  }, [busy, onCreated, entityType]);

  const onDragEnter = (event) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepth.current += 1;
    setActive(true);
  };

  const onDragLeave = (event) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setActive(false);
  };

  const onDrop = (event) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepth.current = 0;
    setActive(false);
    ingest(collectDropPayload(event));
  };

  const onPaste = (event) => {
    ingest(collectDropPayload(event));
  };

  const closeError = () => setError('');
  const closeSummary = () => setSummary(null);

  if (hidden && !summary && !error) return null;

  return (
    <div className="shrink-0">
      {!hidden && (
      <button
        type="button"
        aria-label={label}
        title={label}
        onDragEnter={onDragEnter}
        onDragOver={(event) => {
          event.preventDefault();
          event.stopPropagation();
        }}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onPaste={onPaste}
        className={`${isCompact ? 'w-10 h-10' : 'w-14 h-14'} rounded-full shadow-lg transition-all flex items-center justify-center ${
          active
            ? 'bg-teal-500 text-white scale-110'
            : 'bg-teal-600 text-white hover:bg-teal-700 hover:scale-110'
        } ${busy ? 'opacity-70 pointer-events-none' : 'cursor-copy'}`}
      >
        {busy ? (
          <svg className={isCompact ? 'w-5 h-5 animate-spin' : 'w-6 h-6 animate-spin'} viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : (
          <svg className={isCompact ? 'w-5 h-5' : 'w-6 h-6'} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3.75H6.912a2.25 2.25 0 00-2.15 1.588L2.35 13.177a2.25 2.25 0 00-.1.661V18A2.25 2.25 0 004.5 20.25h15A2.25 2.25 0 0021.75 18v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 00-2.15-1.588H15M12 3v8.25m0 0l-3-3m3 3l3-3" />
          </svg>
        )}
      </button>
      )}
      {summary && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="drop-create-summary-title"
          onClick={closeSummary}
        >
          <div
            className="max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-lg bg-white p-6 shadow-xl dark:bg-gray-800"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="drop-create-summary-title" className="mb-3 text-xl font-semibold text-gray-900 dark:text-gray-100">
              {summary.action === 'reused' ? 'Already in your library' : 'Drop complete'}
            </h2>
            <ul className="list-disc space-y-1 pl-5 text-sm leading-6 text-gray-800 dark:text-gray-200">
              {(summary.lines || []).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            <div className="mt-6 flex justify-end">
              <button
                type="button"
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
                onClick={closeSummary}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
      {error && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="drop-create-error-title"
          onClick={closeError}
        >
          <div
            className="max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-lg bg-white p-6 shadow-xl dark:bg-gray-800"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="drop-create-error-title" className="mb-3 text-xl font-semibold text-gray-900 dark:text-gray-100">
              Could not create entity
            </h2>
            <pre className="whitespace-pre-wrap break-words text-sm leading-6 text-red-700 dark:text-red-400">
              {error}
            </pre>
            <div className="mt-6 flex justify-end">
              <button
                type="button"
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
                onClick={closeError}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
