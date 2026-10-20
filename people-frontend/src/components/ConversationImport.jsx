import React, { useRef, useState } from 'react';
import api from '../services/api';

const ENTITY_TYPES = ['Note', 'Person', 'Location', 'Movie', 'Book', 'Container', 'Asset', 'Org'];

function descriptionText(html) {
  return String(html || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function DescriptionPreview({ label, html }) {
  const text = descriptionText(html);
  if (!text) return null;
  return (
    <div className="mt-1 text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap max-h-28 overflow-y-auto">
      {label ? <div className="font-medium text-gray-700 dark:text-gray-300 mb-0.5">{label}</div> : null}
      {text}
    </div>
  );
}

function isVcfSource(source) {
  return source === 'vcf';
}

function isTextSource(source) {
  return source === 'text';
}

function fileMatchesSource(file, vcf) {
  const name = (file?.name || '').toLowerCase();
  if (vcf) return name.endsWith('.vcf') || name.endsWith('.vcard');
  return name.endsWith('.json');
}

export default function ConversationImport({ onClose, onImportComplete }) {
  const [source, setSource] = useState('chatgpt');
  const [file, setFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState(null);
  const [text, setText] = useState('');
  const [entityType, setEntityType] = useState('Note');
  const [isDragging, setIsDragging] = useState(false);
  const [confirmations, setConfirmations] = useState(null);
  const [preview, setPreview] = useState(null);
  const [draft, setDraft] = useState(null);
  const [choices, setChoices] = useState({});
  const [extraTag, setExtraTag] = useState('');
  const dragDepth = useRef(0);

  const vcf = isVcfSource(source);
  const textMode = isTextSource(source);
  const confirming = Boolean(preview);
  const accept = vcf ? '.vcf,.vcard' : '.json';
  const canImport = confirming
    ? (confirmations || []).every((item) => choices[item.key]?.action)
    : textMode
      ? Boolean(text.trim())
      : Boolean(file);

  const resetPreview = () => {
    setPreview(null);
    setDraft(null);
    setConfirmations(null);
    setChoices({});
    setExtraTag('');
  };

  const handleSourceChange = (nextSource) => {
    setSource(nextSource);
    setFile(null);
    setError(null);
  };

  const applySelectedFile = (selectedFile) => {
    if (!selectedFile) return;
    if (!fileMatchesSource(selectedFile, vcf)) {
      setError(vcf ? 'Please select a .vcf or .vcard file' : 'Please select a JSON file');
      setFile(null);
      return;
    }
    setFile(selectedFile);
    setError(null);
  };

  const handleFileChange = (e) => {
    applySelectedFile(e.target.files?.[0]);
    e.target.value = '';
  };

  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current += 1;
    setIsDragging(true);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = 0;
    setIsDragging(false);
    applySelectedFile(e.dataTransfer?.files?.[0]);
  };

  const handleImport = async () => {
    if (textMode && !text.trim()) {
      setError('Enter at least one line of text');
      return;
    }
    if (!textMode && !file) {
      setError('Please select a file');
      return;
    }

    setImporting(true);
    setError(null);

    try {
      let response;
      if (textMode) {
        const body = confirming
          ? {
              text,
              type: entityType,
              draft,
              confirmations: choices,
              confirm: true,
              extra_tag: extraTag.trim(),
            }
          : { text, type: entityType };
        response = await api.fetch('/api/entities/import_text/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
      } else {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('source', source);
        const url = vcf ? '/api/people/import_file/' : '/api/notes/import_file/';
        response = await api.fetch(url, {
          method: 'POST',
          body: formData,
          headers: {},
        });
      }

      const data = await response.json();

      if (response.ok && data.needs_confirmation) {
        setPreview(data.preview || { create: [], found: [], ambiguities: data.confirmations || [] });
        setConfirmations(data.confirmations || []);
        setDraft(data.draft || null);
        setChoices(Object.fromEntries((data.confirmations || []).map((item) => [
          item.key,
          item.candidates?.[0]
            ? { action: 'use', id: item.candidates[0].id }
            : { action: 'create' },
        ])));
        return;
      }
      if (response.ok) {
        if (onImportComplete) onImportComplete(data);
        onClose();
        return;
      } else {
        setError(data.error || 'Import failed');
      }
    } catch (err) {
      setError(err.message || 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
      onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
        applySelectedFile(e.dataTransfer?.files?.[0]);
      }}
    >
      <div className={`bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-h-[90vh] overflow-y-auto ${confirming ? 'max-w-3xl' : 'max-w-2xl'}`}>
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
            Import Data
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            aria-label="Close import"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6 space-y-6">
          {importing ? (
            <div className="flex flex-col items-center justify-center py-12">
              <svg className="animate-spin h-16 w-16 text-indigo-600 mb-4" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                {textMode ? (confirming ? 'Saving relations...' : 'Importing with AI...') : vcf ? 'Importing contacts...' : 'Importing conversations...'}
              </h3>
              <p className="text-gray-600 dark:text-gray-400">
                {textMode ? 'Please wait while we extract and create entities' : 'Please wait while we process your file'}
              </p>
            </div>
          ) : confirming ? (
            <div className="space-y-5">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Review import
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  Nothing has been saved yet. Confirm creates, updates, existing matches, and any ambiguous names.
                </p>
              </div>

              {(preview.update || []).length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                    Will update ({preview.update.length})
                  </h4>
                  <ul className="space-y-1 text-sm text-gray-800 dark:text-gray-200">
                    {preview.update.map((item) => (
                      <li key={`${item.id || item.import_ref}-${item.display}`}>
                        <span className="font-medium">{item.type}</span>: {item.display}
                        <span className="text-gray-500 dark:text-gray-400">
                          {' '}— merge the new description into the existing record
                        </span>
                        <DescriptionPreview label="Merged proposal" html={item.description} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div>
                <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                  Will create ({preview.create?.length || 0})
                </h4>
                {(preview.create || []).length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">No new entities.</p>
                ) : (
                  <ul className="space-y-1 text-sm text-gray-800 dark:text-gray-200">
                    {(preview.create || []).map((item, index) => (
                      <li key={`${item.type}-${item.display}-${index}`}>
                        <span className="font-medium">{item.type}</span>: {item.display}
                        {item.role && item.role !== 'Imported item' ? (
                          <span className="text-gray-500 dark:text-gray-400">
                            {' '}({item.role}{item.from_display ? ` of ${item.from_display}` : ''})
                          </span>
                        ) : null}
                        <DescriptionPreview
                          label={item.role === 'Imported item' ? 'From AI' : null}
                          html={item.description}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                  Already in the system ({preview.found?.length || 0})
                </h4>
                {(preview.found || []).length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">No existing matches to reuse.</p>
                ) : (
                  <ul className="space-y-1 text-sm text-gray-800 dark:text-gray-200">
                    {(preview.found || []).map((item) => (
                      <li key={`${item.id}-${item.role}`}>
                        <span className="font-medium">{item.display}</span>
                        <span className="text-gray-500 dark:text-gray-400">
                          {' '}({item.type}{item.role ? ` · ${item.role}` : ''}{item.from_display ? ` of ${item.from_display}` : ''})
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {(confirmations || []).length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
                    Needs a choice ({confirmations.length})
                  </h4>
                  {confirmations.map((item) => {
                    const choice = choices[item.key] || {};
                    return (
                      <div
                        key={item.key}
                        className="border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 rounded-lg p-4 space-y-3"
                      >
                        <div>
                          <p className="text-sm font-medium text-gray-900 dark:text-white">
                            {item.kind === 'main'
                              ? `${item.query} already exists`
                              : `${item.from_display} → ${item.relation_name}`}
                          </p>
                          <p className="text-sm text-gray-600 dark:text-gray-400">
                            {item.kind === 'main'
                              ? `Merge into the existing ${item.target_type}, or create a new one.`
                              : `Looking for ${item.target_type}: ${item.query}`}
                          </p>
                          {item.kind === 'main' ? (
                            <DescriptionPreview label="From AI" html={item.incoming_description} />
                          ) : null}
                        </div>
                        <div className="space-y-3">
                          {(item.candidates || []).map((candidate) => (
                            <label
                              key={candidate.id}
                              className="flex items-start gap-2 text-sm text-gray-800 dark:text-gray-200"
                            >
                              <input
                                type="radio"
                                name={item.key}
                                className="mt-1"
                                checked={choice.action === 'use' && choice.id === candidate.id}
                                onChange={() => setChoices((current) => ({
                                  ...current,
                                  [item.key]: { action: 'use', id: candidate.id },
                                }))}
                              />
                              <span className="min-w-0">
                                <span className="block">
                                  {item.kind === 'main' ? 'Merge into' : 'Use existing'} {candidate.display}
                                  {candidate.profession ? ` (${candidate.profession})` : ''}
                                  {candidate.year ? ` (${candidate.year})` : ''}
                                </span>
                                {item.kind === 'main' ? (
                                  <DescriptionPreview
                                    label="Merged proposal"
                                    html={candidate.merged_description || candidate.description}
                                  />
                                ) : null}
                              </span>
                            </label>
                          ))}
                          <label className="flex items-start gap-2 text-sm text-gray-800 dark:text-gray-200">
                            <input
                              type="radio"
                              name={item.key}
                              className="mt-1"
                              checked={choice.action === 'create'}
                              onChange={() => setChoices((current) => ({
                                ...current,
                                [item.key]: { action: 'create' },
                              }))}
                            />
                            <span className="min-w-0">
                              <span className="block">
                                {item.kind === 'main'
                                  ? `Create a new ${item.target_type}: ${item.query}`
                                  : `Create new ${item.target_type}: ${item.query}`}
                              </span>
                              {item.kind === 'main' ? (
                                <DescriptionPreview label="From AI" html={item.incoming_description} />
                              ) : null}
                            </span>
                          </label>
                          <label className="flex items-start gap-2 text-sm text-gray-800 dark:text-gray-200">
                            <input
                              type="radio"
                              name={item.key}
                              className="mt-1"
                              checked={choice.action === 'skip'}
                              onChange={() => setChoices((current) => ({
                                ...current,
                                [item.key]: { action: 'skip' },
                              }))}
                            />
                            <span>{item.kind === 'main' ? 'Skip this item' : 'Skip this relation'}</span>
                          </label>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Extra tag for new entities
                </label>
                <input
                  type="text"
                  value={extraTag}
                  onChange={(e) => setExtraTag(e.target.value)}
                  placeholder="Optional, e.g. nolan-films"
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  New entities always get <span className="font-mono">imported/text</span>. Existing matches are not tagged.
                </p>
              </div>

              {error && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
                  {error}
                </div>
              )}
            </div>
          ) : (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Source type
                </label>
                <select
                  value={source}
                  onChange={(e) => handleSourceChange(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  disabled={importing}
                >
                  <optgroup label="Conversations">
                    <option value="chatgpt">ChatGPT</option>
                    <option value="gemini">Google Gemini</option>
                    <option value="claude">Claude</option>
                    <option value="other">Other</option>
                  </optgroup>
                  <optgroup label="Contacts">
                    <option value="vcf">vCard (VCF)</option>
                  </optgroup>
                  <optgroup label="AI">
                    <option value="text">Text</option>
                  </optgroup>
                </select>
              </div>

              {textMode && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Entity type
                  </label>
                  <select
                    value={entityType}
                    onChange={(e) => setEntityType(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                    disabled={importing}
                  >
                    {ENTITY_TYPES.map((type) => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {textMode ? 'Text' : vcf ? 'vCard file' : 'JSON export file'}
                </label>
                {textMode ? (
                <textarea
                  value={text}
                  onChange={(e) => { setText(e.target.value); setError(null); }}
                  rows={10}
                  placeholder="One item per line"
                  className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 font-mono text-sm"
                  disabled={importing}
                />
                ) : (
                <div
                  className={`mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-dashed rounded-lg transition-colors ${
                    isDragging
                      ? 'border-indigo-500 bg-indigo-50 dark:border-indigo-400 dark:bg-indigo-900/20'
                      : 'border-gray-300 dark:border-gray-600 hover:border-indigo-500 dark:hover:border-indigo-400'
                  }`}
                  onDragEnter={handleDragEnter}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  data-testid="import-dropzone"
                >
                  <div className="space-y-1 text-center">
                    <svg
                      className="mx-auto h-12 w-12 text-gray-400"
                      stroke="currentColor"
                      fill="none"
                      viewBox="0 0 48 48"
                    >
                      <path
                        d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                        strokeWidth={2}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                    <div className="flex text-sm text-gray-600 dark:text-gray-400">
                      <label className="relative cursor-pointer bg-white dark:bg-gray-700 rounded-md font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 focus-within:outline-none focus-within:ring-2 focus-within:ring-offset-2 focus-within:ring-indigo-500">
                        <span>Upload a file</span>
                        <input
                          type="file"
                          className="sr-only"
                          accept={accept}
                          onChange={handleFileChange}
                          disabled={importing}
                        />
                      </label>
                      <p className="pl-1">or drag and drop</p>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {vcf ? 'VCF / vCard files' : 'JSON files only'}
                    </p>
                    {file && (
                      <p className="text-sm text-green-600 dark:text-green-400 font-medium mt-2">
                        ✓ {file.name}
                      </p>
                    )}
                  </div>
                </div>
                )}
              </div>

              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                {textMode ? (
                  <>
                    <h3 className="text-sm font-medium text-blue-900 dark:text-blue-300 mb-2">
                      How text import works:
                    </h3>
                    <ul className="text-sm text-blue-800 dark:text-blue-400 space-y-1 list-disc list-inside">
                      <li>Paste one item per line</li>
                      <li>AI writes a detailed description and fills fields for the selected type</li>
                      <li>Related people are linked if they already exist, or created</li>
                      <li>Existing items are updated by merging the new description; you confirm first</li>
                      <li>You review creates, updates, existing matches, and ambiguities before anything is saved</li>
                      <li>You can add an extra tag to new entities</li>
                      <li>Each line becomes one {entityType}</li>
                    </ul>
                  </>
                ) : vcf ? (
                  <>
                    <h3 className="text-sm font-medium text-blue-900 dark:text-blue-300 mb-2">
                      How to export contacts:
                    </h3>
                    <ul className="text-sm text-blue-800 dark:text-blue-400 space-y-1 list-disc list-inside">
                      <li><strong>iPhone:</strong> Contacts → select contact → Share Contact → Save to Files</li>
                      <li><strong>Google:</strong> Contacts → Export → vCard</li>
                      <li><strong>Outlook:</strong> People → Manage → Export contacts → vCard</li>
                    </ul>
                    <p className="text-sm text-blue-800 dark:text-blue-400 mt-2">
                      Each contact becomes a Person entity.
                    </p>
                  </>
                ) : (
                  <>
                    <h3 className="text-sm font-medium text-blue-900 dark:text-blue-300 mb-2">
                      How to export conversations:
                    </h3>
                    <ul className="text-sm text-blue-800 dark:text-blue-400 space-y-1 list-disc list-inside">
                      <li><strong>ChatGPT:</strong> Settings → Data controls → Export data</li>
                      <li><strong>Gemini:</strong> Activity → Download your data</li>
                      <li><strong>Claude:</strong> Settings → Export conversations</li>
                    </ul>
                  </>
                )}
              </div>

              {error && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
                  {error}
                </div>
              )}

            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200 dark:border-gray-700">
          {confirming && (
            <button
              onClick={resetPreview}
              className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors mr-auto"
              disabled={importing}
            >
              Back
            </button>
          )}
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            disabled={importing}
          >
            Cancel
          </button>
          <button
            onClick={handleImport}
            disabled={!canImport || importing}
            className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {importing ? (
              <>
                <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Importing...
              </>
            ) : (
              confirming ? 'Confirm and import' : 'Import'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
