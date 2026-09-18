import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { getLoginUrl } from '../utils/apiUrl';
import api from '../services/api';
import AppsMenu from './AppsMenu';

const FONT_STORAGE_KEY = 'productions-font-size';
const FONT_STEPS = [14, 16, 18, 20, 22, 24];
const DEFAULT_FONT_SIZE = 16;

function readFontSize() {
  const raw = Number(localStorage.getItem(FONT_STORAGE_KEY));
  return FONT_STEPS.includes(raw) ? raw : DEFAULT_FONT_SIZE;
}

function applyFontSize(size) {
  document.documentElement.style.fontSize = `${size}px`;
}

const DEFAULT_TYPES = [
  { value: 'short_form_documentary', label: 'Short Form Documentary' },
  { value: 'long_form_documentary', label: 'Long Form Documentary' },
  { value: 'reel', label: 'Reel' },
];
const DEFAULT_SCENE_TYPES = ['Hook', 'Intro', 'Preparation', 'Anticipation', 'Body', 'Outro'];
const ASSET_STATUSES = [
  { value: 'todo', label: 'Todo' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'done', label: 'Done' },
];
const SCENE_VIEW_STORAGE_KEY = 'productions-scene-view';
const SCENE_VIEWS = [
  { value: 'compact', label: 'Compact' },
  { value: 'dialogue', label: 'Dialogue' },
  { value: 'expanded', label: 'Expanded' },
];

function readSceneView() {
  const value = localStorage.getItem(SCENE_VIEW_STORAGE_KEY);
  return SCENE_VIEWS.some((view) => view.value === value) ? value : 'expanded';
}

function asList(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

function tagsToText(tags) {
  return Array.isArray(tags) ? tags.join(', ') : '';
}

function textToTags(text) {
  return text.split(',').map((part) => part.trim()).filter(Boolean);
}

function downloadFile(filename, text, mime = 'text/plain;charset=utf-8') {
  const blob = new Blob([text || ''], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function downloadText(filename, text) {
  downloadFile(filename, text);
}

function downloadJson(filename, data) {
  downloadFile(filename, JSON.stringify(data, null, 2), 'application/json;charset=utf-8');
}

function fileStem(title) {
  const slug = String(title || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug || 'production';
}

function fitTextarea(el) {
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = `${el.scrollHeight}px`;
}

function Icon({ name }) {
  const paths = {
    up: 'M6 14L12 8l6 6',
    down: 'M6 10l6 6 6-6',
    add: 'M12 5v14M5 12h14',
    del: 'M6 7h12M9 7V5h6v2M9 11v6M12 11v6M15 11v6M8 7l1 12h6l1-12',
  };
  return (
    <svg className="prod-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d={paths[name]} />
    </svg>
  );
}

function sameSceneValue(left, right) {
  if (Array.isArray(left) || Array.isArray(right)) {
    return JSON.stringify(left || []) === JSON.stringify(right || []);
  }
  return String(left ?? '') === String(right ?? '');
}

function mergeSceneDraft(prev, incoming, previousServer) {
  if (!prev || prev.id !== incoming.id) return incoming;
  const next = { ...incoming };
  Object.keys(incoming).forEach((key) => {
    if (!sameSceneValue(prev[key], previousServer?.[key])) {
      next[key] = prev[key];
    }
  });
  return next;
}

function extraSummary(scene) {
  const parts = [];
  if ((scene.music || '').trim()) parts.push('music');
  if ((scene.fx_cues || '').trim()) parts.push('FX');
  if ((scene.notes || '').trim()) parts.push('notes');
  const assetCount = (scene.assets || []).length;
  if (assetCount) parts.push(`${assetCount} asset${assetCount === 1 ? '' : 's'}`);
  return parts.length ? parts.join(' · ') : 'Music, FX, notes, assets';
}

function SceneCard({ scene, viewMode, onPatch, onMove, onInsertAfter, onDelete, onDragStart, onDragEnd, onDrop, dragging }) {
  const [draft, setDraft] = useState(scene);
  const [assetDraft, setAssetDraft] = useState('');
  const [moreOpen, setMoreOpen] = useState(false);
  const visualsRef = useRef(null);
  const voiceoverRef = useRef(null);
  const serverSceneRef = useRef(scene);

  useEffect(() => {
    setDraft((prev) => mergeSceneDraft(prev, scene, serverSceneRef.current));
    serverSceneRef.current = scene;
  }, [scene]);

  useLayoutEffect(() => {
    const resize = () => {
      fitTextarea(visualsRef.current);
      fitTextarea(voiceoverRef.current);
    };
    resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, [draft.visuals, draft.voiceover]);

  const saveField = async (field, value) => {
    if ((scene[field] || '') === (value || '')) return;
    await onPatch(scene.id, { [field]: value });
  };

  const addAsset = async () => {
    const name = assetDraft.trim();
    if (!name) return;
    const assets = [...(scene.assets || []), name];
    setAssetDraft('');
    await onPatch(scene.id, { assets });
  };

  const removeAsset = async (name) => {
    await onPatch(scene.id, { assets: (scene.assets || []).filter((item) => item !== name) });
  };

  return (
    <article
      className={`prod-scene prod-scene-${viewMode}${dragging ? ' is-dragging' : ''}`}
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
    >
      <div className="prod-scene-top">
        <button
          type="button"
          className="prod-drag"
          draggable
          title="Drag to reorder"
          aria-label="Drag to reorder"
          onDragStart={onDragStart}
        >
          ⋮⋮
        </button>
        <label className="prod-scene-title">
          Title
          <input
            className="prod-field"
            autoComplete="off"
            name={`scene-title-${scene.id}`}
            placeholder={scene.scene_type || `Scene ${scene.sort_order + 1}`}
            value={draft.title || ''}
            onChange={(event) => setDraft((prev) => ({ ...prev, title: event.target.value }))}
            onBlur={(event) => saveField('title', event.target.value)}
          />
        </label>
        {viewMode === 'expanded' && (
          <label className="prod-scene-type">
            Type
            <input
              className="prod-field"
              list="scene-type-presets"
              autoComplete="off"
              name={`scene-type-${scene.id}`}
              value={draft.scene_type || ''}
              onChange={(event) => setDraft((prev) => ({ ...prev, scene_type: event.target.value }))}
              onBlur={(event) => saveField('scene_type', event.target.value)}
            />
          </label>
        )}
        <div className="prod-times" role="group" aria-label="Scene timing">
          <label>
            Start
            <input className="prod-field" value={scene.start} readOnly tabIndex={-1} />
          </label>
          <label>
            Dur
            <input
              className="prod-field"
              autoComplete="off"
              name={`scene-duration-${scene.id}`}
              value={draft.duration || ''}
              onChange={(event) => setDraft((prev) => ({ ...prev, duration: event.target.value }))}
              onBlur={(event) => saveField('duration', event.target.value)}
            />
          </label>
          {viewMode === 'expanded' && (
            <label>
              End
              <input
                className="prod-field"
                autoComplete="off"
                name={`scene-end-${scene.id}`}
                value={draft.end || ''}
                onChange={(event) => setDraft((prev) => ({ ...prev, end: event.target.value }))}
                onBlur={(event) => saveField('end', event.target.value)}
              />
            </label>
          )}
        </div>
        <div className="prod-scene-actions">
          <button type="button" className="prod-icon-btn" title="Move up" aria-label="Move up" onClick={() => onMove(scene, 'up')}>
            <Icon name="up" />
          </button>
          <button type="button" className="prod-icon-btn" title="Move down" aria-label="Move down" onClick={() => onMove(scene, 'down')}>
            <Icon name="down" />
          </button>
          <button type="button" className="prod-icon-btn" title="Add scene after" aria-label="Add scene after" onClick={() => onInsertAfter(scene)}>
            <Icon name="add" />
          </button>
          <button type="button" className="prod-icon-btn" title="Delete scene" aria-label="Delete scene" onClick={() => onDelete(scene)}>
            <Icon name="del" />
          </button>
        </div>
      </div>
      {viewMode === 'dialogue' && (
        <div className="prod-read-cues">
          <section>
            <h3>Visuals &amp; B-Roll</h3>
            <p>{(scene.visuals || '').trim() || '—'}</p>
          </section>
          <section>
            <h3>Voiceover &amp; Dialogue</h3>
            <p>{(scene.voiceover || '').trim() || '—'}</p>
          </section>
        </div>
      )}
      {viewMode === 'expanded' && (
        <div className="prod-cues prod-cues-script">
          <label>
            Visuals &amp; B-Roll
            <textarea
              ref={visualsRef}
              className="prod-grow"
              autoComplete="off"
              name={`scene-visuals-${scene.id}`}
              value={draft.visuals || ''}
              onChange={(event) => {
                setDraft((prev) => ({ ...prev, visuals: event.target.value }));
                fitTextarea(event.target);
              }}
              onBlur={(event) => saveField('visuals', event.target.value)}
            />
          </label>
          <label>
            Voiceover &amp; Dialogue
            <textarea
              ref={voiceoverRef}
              className="prod-grow"
              autoComplete="off"
              name={`scene-voiceover-${scene.id}`}
              value={draft.voiceover || ''}
              onChange={(event) => {
                setDraft((prev) => ({ ...prev, voiceover: event.target.value }));
                fitTextarea(event.target);
              }}
              onBlur={(event) => saveField('voiceover', event.target.value)}
            />
          </label>
        </div>
      )}
      {viewMode === 'expanded' && (
      <button
        type="button"
        className={`prod-more${moreOpen ? ' is-open' : ''}`}
        aria-expanded={moreOpen}
        onClick={() => setMoreOpen((open) => !open)}
      >
        <span className="prod-more-caret" aria-hidden="true">{moreOpen ? '▾' : '▸'}</span>
        {moreOpen ? 'Hide extras' : extraSummary(scene)}
      </button>
      )}
      {viewMode === 'expanded' && moreOpen && (
        <div className="prod-scene-more">
          <div className="prod-cues">
            <label>
              Music / Sound
              <textarea
                value={draft.music || ''}
                onChange={(event) => setDraft((prev) => ({ ...prev, music: event.target.value }))}
                onBlur={(event) => saveField('music', event.target.value)}
              />
            </label>
            <label>
              FX Cues
              <textarea
                value={draft.fx_cues || ''}
                onChange={(event) => setDraft((prev) => ({ ...prev, fx_cues: event.target.value }))}
                onBlur={(event) => saveField('fx_cues', event.target.value)}
              />
            </label>
          </div>
          <label className="prod-notes-label">
            Notes
            <textarea
              className="prod-notes"
              value={draft.notes || ''}
              onChange={(event) => setDraft((prev) => ({ ...prev, notes: event.target.value }))}
              onBlur={(event) => saveField('notes', event.target.value)}
            />
          </label>
          <div>
            <div className="prod-notes-label">Assets</div>
            <div className="prod-asset-row">
              {(scene.assets || []).map((name) => (
                <button key={name} type="button" className="prod-chip" onClick={() => removeAsset(name)}>
                  {name} ×
                </button>
              ))}
            </div>
            <div className="prod-asset-add">
              <input
                className="prod-field"
                placeholder="Asset name for this scene"
                value={assetDraft}
                onChange={(event) => setAssetDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    addAsset();
                  }
                }}
              />
              <button type="button" className="prod-ghost" onClick={addAsset}>Add</button>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

function ProductionDetail({ production, types, sceneTypes, fontSize, onFontSize, onBack, onReload, onDeleted }) {
  const [header, setHeader] = useState(production);
  const [tagText, setTagText] = useState(tagsToText(production.tags));
  const [panel, setPanel] = useState('script');
  const [sceneView, setSceneView] = useState(readSceneView);
  const [dragId, setDragId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setHeader(production);
    setTagText(tagsToText(production.tags));
  }, [production]);

  const saveHeader = async (patch) => {
    setError('');
    try {
      await api.json(`/api/productions/productions/${production.id}/`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      });
      await onReload();
    } catch (err) {
      setError(err.message);
    }
  };

  const patchScene = async (id, payload) => {
    setError('');
    try {
      await api.json(`/api/productions/scenes/${id}/`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
      await onReload();
    } catch (err) {
      setError(err.message);
    }
  };

  const addScene = async (afterScene) => {
    setBusy(true);
    setError('');
    try {
      await api.json('/api/productions/scenes/', {
        method: 'POST',
        body: JSON.stringify({
          production_id: production.id,
          scene_type: sceneTypes[0] || 'Hook',
          duration: '10',
          ...(afterScene ? { after_id: afterScene.id } : {}),
        }),
      });
      await onReload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const moveScene = async (scene, direction) => {
    await api.json(`/api/productions/scenes/${scene.id}/move/`, {
      method: 'POST',
      body: JSON.stringify({ direction }),
    });
    await onReload();
  };

  const dropScene = async (targetId) => {
    if (!dragId || dragId === targetId) return;
    const scenes = production.scenes || [];
    const from = scenes.findIndex((scene) => scene.id === dragId);
    const to = scenes.findIndex((scene) => scene.id === targetId);
    if (from < 0 || to < 0) return;
    const steps = to - from;
    const direction = steps > 0 ? 'down' : 'up';
    for (let i = 0; i < Math.abs(steps); i += 1) {
      await api.json(`/api/productions/scenes/${dragId}/move/`, {
        method: 'POST',
        body: JSON.stringify({ direction }),
      });
    }
    setDragId(null);
    await onReload();
  };

  const deleteScene = async (scene) => {
    if (!window.confirm(`Delete ${scene.scene_type || 'this scene'}?`)) return;
    await api.json(`/api/productions/scenes/${scene.id}/`, { method: 'DELETE' });
    await onReload();
  };

  const setAssetStatus = async (name, status) => {
    await api.json(`/api/productions/productions/${production.id}/assets/`, {
      method: 'PATCH',
      body: JSON.stringify({ name, status }),
    });
    await onReload();
  };

  const archiveOrRestore = async () => {
    const action = production.is_archived ? 'unarchive' : 'archive';
    await api.json(`/api/productions/productions/${production.id}/${action}/`, { method: 'POST', body: '{}' });
    await onReload();
  };

  const duplicate = async () => {
    const copy = await api.json(`/api/productions/productions/${production.id}/duplicate/`, {
      method: 'POST',
      body: '{}',
    });
    await onReload(copy.id);
  };

  const exportProduction = async () => {
    setError('');
    try {
      const data = await api.json(`/api/productions/productions/${production.id}/export/`);
      downloadJson(`${fileStem(production.title)}.json`, data);
    } catch (err) {
      setError(err.message);
    }
  };

  const remove = async () => {
    if (!window.confirm('Delete this production? This cannot be undone.')) return;
    await api.json(`/api/productions/productions/${production.id}/`, { method: 'DELETE' });
    onDeleted();
  };

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button type="button" className="prod-ghost" onClick={onBack}>All productions</button>
        <button type="button" className={`prod-ghost${panel === 'script' ? ' is-active' : ''}`} onClick={() => setPanel('script')}>Script</button>
        <button type="button" className={`prod-ghost${panel === 'teleprompter' ? ' is-active' : ''}`} onClick={() => setPanel('teleprompter')}>Teleprompter</button>
        <button type="button" className={`prod-ghost${panel === 'assets' ? ' is-active' : ''}`} onClick={() => setPanel('assets')}>Assets</button>
        <FontSizeControls size={fontSize} onChange={onFontSize} />
        <div className="ml-auto flex flex-wrap gap-2">
          <button type="button" className="prod-ghost" onClick={archiveOrRestore}>
            {production.is_archived ? 'Unarchive' : 'Archive'}
          </button>
          <button type="button" className="prod-ghost" onClick={duplicate}>Duplicate</button>
          <button type="button" className="prod-ghost" onClick={exportProduction}>Export</button>
          <button type="button" className="prod-ghost" onClick={remove}>Delete</button>
        </div>
      </div>
      {error && <p className="prod-error">{error}</p>}
      <section className="prod-panel mb-4">
        <div className="prod-header-grid">
          <label>
            Title
            <input
              className="prod-field"
              value={header.title || ''}
              onChange={(event) => setHeader((prev) => ({ ...prev, title: event.target.value }))}
              onBlur={(event) => saveHeader({ title: event.target.value })}
            />
          </label>
          <label>
            Subtitle
            <input
              className="prod-field"
              value={header.subtitle || ''}
              onChange={(event) => setHeader((prev) => ({ ...prev, subtitle: event.target.value }))}
              onBlur={(event) => saveHeader({ subtitle: event.target.value })}
            />
          </label>
          <label>
            Type
            <select
              className="prod-field"
              value={header.type || ''}
              onChange={(event) => {
                setHeader((prev) => ({ ...prev, type: event.target.value }));
                saveHeader({ type: event.target.value });
              }}
            >
              {types.map((type) => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
          </label>
          <label>
            Tags
            <input
              className="prod-field"
              value={tagText}
              onChange={(event) => setTagText(event.target.value)}
              onBlur={() => saveHeader({ tags: textToTags(tagText) })}
              placeholder="comma separated"
            />
          </label>
        </div>
        <label className="prod-notes-label">
          Description
          <textarea
            className="prod-notes mt-1"
            value={header.description || ''}
            onChange={(event) => setHeader((prev) => ({ ...prev, description: event.target.value }))}
            onBlur={(event) => saveHeader({ description: event.target.value })}
          />
        </label>
        <p className="mt-2 text-sm text-[var(--text-color)]">
          Runtime {production.total_duration || '0:00'} · {production.scenes?.length || 0} scenes
          {production.is_archived ? ' · Archived' : ''}
        </p>
      </section>

      {panel === 'teleprompter' && (
        <section className="prod-panel">
          <div className="mb-3 flex gap-2">
            <button
              type="button"
              className="prod-ghost"
              onClick={() => navigator.clipboard.writeText(production.teleprompter || '')}
            >
              Copy
            </button>
            <button
              type="button"
              className="prod-ghost"
              onClick={() => downloadText(`${production.title || 'script'}.txt`, production.teleprompter || '')}
            >
              Download
            </button>
          </div>
          <pre className="whitespace-pre-wrap text-sm leading-6">{production.teleprompter || 'No voiceover yet.'}</pre>
        </section>
      )}

      {panel === 'assets' && (
        <section className="prod-panel">
          {(production.asset_todos || []).length === 0 && (
            <p className="prod-empty">No named assets yet. Add them on scenes.</p>
          )}
          {(production.asset_todos || []).map((row) => (
            <div key={row.name_key} className="prod-todo">
              <div className="flex-1">
                <strong>{row.name}</strong>
                <div className="text-xs text-[var(--text-color)]">
                  {row.scenes.map((scene) => scene.title || scene.scene_type || `Scene ${scene.sort_order + 1}`).join(', ')}
                </div>
              </div>
              <select
                className="prod-field"
                style={{ width: 'auto' }}
                value={row.status}
                onChange={(event) => setAssetStatus(row.name, event.target.value)}
              >
                {ASSET_STATUSES.map((status) => (
                  <option key={status.value} value={status.value}>{status.label}</option>
                ))}
              </select>
            </div>
          ))}
        </section>
      )}

      {panel === 'script' && (
        <section>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <button type="button" className="prod-primary" onClick={() => addScene()} disabled={busy}>Add scene</button>
            <div className="prod-view-toggle" role="group" aria-label="Scene view">
              {SCENE_VIEWS.map((view) => (
                <button
                  key={view.value}
                  type="button"
                  className={`prod-ghost${sceneView === view.value ? ' is-active' : ''}`}
                  onClick={() => {
                    setSceneView(view.value);
                    localStorage.setItem(SCENE_VIEW_STORAGE_KEY, view.value);
                  }}
                >
                  {view.label}
                </button>
              ))}
            </div>
            <span className="text-sm text-[var(--text-color)]">Drag the handle or use Up/Down to reorder.</span>
          </div>
          <datalist id="scene-type-presets">
            {sceneTypes.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <div className="prod-timeline">
            {(production.scenes || []).map((scene) => (
              <SceneCard
                key={scene.id}
                scene={scene}
                viewMode={sceneView}
                onPatch={patchScene}
                onMove={moveScene}
                onInsertAfter={addScene}
                onDelete={deleteScene}
                onDragStart={() => setDragId(scene.id)}
                onDragEnd={() => setDragId(null)}
                onDrop={() => dropScene(scene.id)}
                dragging={dragId === scene.id}
              />
            ))}
          </div>
          {(production.scenes || []).length === 0 && (
            <p className="prod-empty">No scenes yet. Add the first one — it starts at 0:00.</p>
          )}
        </section>
      )}
    </div>
  );
}

function CreateWithAiModal({ types, defaultType, busy, error, onClose, onGenerate }) {
  const [prompt, setPrompt] = useState('');
  const [kind, setKind] = useState(defaultType);
  return (
    <div className="prod-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="prod-modal"
        role="dialog"
        aria-labelledby="prod-ai-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="prod-ai-title">Create with AI</h2>
        <p className="prod-modal-copy">
          Describe the video. The model writes a first-draft rundown: scenes, voiceover, visuals/b-roll, and durations.
        </p>
        <label>
          Type
          <select className="prod-field" value={kind} onChange={(event) => setKind(event.target.value)}>
            {types.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>
        <label>
          Brief
          <textarea
            className="prod-notes"
            rows={8}
            autoFocus
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Example: 45-second reel about a dawn hike to a windy summit, first-person, dry humor, end on the view."
          />
        </label>
        {error && <p className="prod-error">{error}</p>}
        <div className="prod-modal-actions">
          <button type="button" className="prod-ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button
            type="button"
            className="prod-primary"
            disabled={busy || !prompt.trim()}
            onClick={() => onGenerate({ prompt: prompt.trim(), type: kind })}
          >
            {busy ? 'Generating…' : 'Generate rundown'}
          </button>
        </div>
      </div>
    </div>
  );
}

function FontSizeControls({ size, onChange }) {
  const smaller = FONT_STEPS[Math.max(0, FONT_STEPS.indexOf(size) - 1)];
  const larger = FONT_STEPS[Math.min(FONT_STEPS.length - 1, FONT_STEPS.indexOf(size) + 1)];
  return (
    <div className="prod-font-size" role="group" aria-label="Font size">
      <button
        type="button"
        className="prod-ghost"
        disabled={size === FONT_STEPS[0]}
        onClick={() => onChange(smaller)}
        aria-label="Decrease font size"
      >
        A−
      </button>
      <span>{size}px</span>
      <button
        type="button"
        className="prod-ghost"
        disabled={size === FONT_STEPS[FONT_STEPS.length - 1]}
        onClick={() => onChange(larger)}
        aria-label="Increase font size"
      >
        A+
      </button>
    </div>
  );
}

export default function ProductionsApp() {
  const { user, loading, logout, isAuthenticated } = useAuth();
  const [fontSize, setFontSize] = useState(DEFAULT_FONT_SIZE);
  const [productions, setProductions] = useState([]);
  const [selected, setSelected] = useState(null);
  const [meta, setMeta] = useState({ types: DEFAULT_TYPES, scene_types: DEFAULT_SCENE_TYPES });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState('');
  const importRef = useRef(null);
  const [title, setTitle] = useState('');
  const [type, setType] = useState('short_form_documentary');
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [showArchived, setShowArchived] = useState(false);

  useEffect(() => {
    const size = readFontSize();
    setFontSize(size);
    applyFontSize(size);
    return () => {
      document.documentElement.style.fontSize = '';
    };
  }, []);

  const changeFontSize = (size) => {
    setFontSize(size);
    localStorage.setItem(FONT_STORAGE_KEY, String(size));
    applyFontSize(size);
    window.dispatchEvent(new Event('resize'));
  };

  const types = meta.types?.length ? meta.types : DEFAULT_TYPES;
  const sceneTypes = meta.scene_types?.length ? meta.scene_types : DEFAULT_SCENE_TYPES;

  const loadList = useCallback(async () => {
    const params = new URLSearchParams();
    if (query.trim()) params.set('q', query.trim());
    if (typeFilter) params.set('type', typeFilter);
    if (showArchived) params.set('archived', '1');
    const suffix = params.toString() ? `?${params}` : '';
    const data = await api.json(`/api/productions/productions/${suffix}`);
    setProductions(asList(data));
  }, [query, typeFilter, showArchived]);

  const loadSelected = useCallback(async (id) => {
    const data = await api.json(`/api/productions/productions/${id}/`);
    setSelected(data);
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    api.json('/api/productions/productions/meta/').then(setMeta).catch(() => {});
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) return;
    loadList().catch((err) => setError(err.message));
  }, [isAuthenticated, loadList]);

  const createProduction = async (event) => {
    event.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError('');
    try {
      const created = await api.json('/api/productions/productions/', {
        method: 'POST',
        body: JSON.stringify({ title: title.trim(), type }),
      });
      setTitle('');
      await loadList();
      await loadSelected(created.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const exportAll = async () => {
    setBusy(true);
    setError('');
    try {
      const data = await api.json('/api/productions/productions/export/');
      downloadJson('productions.json', data);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const importFromFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      const text = await file.text();
      let payload;
      try {
        payload = JSON.parse(text);
      } catch {
        throw new Error('That file is not valid JSON.');
      }
      const result = await api.json('/api/productions/productions/import/', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      await loadList();
      if (result.count === 1 && result.productions?.[0]?.id) {
        await loadSelected(result.productions[0].id);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const createWithAi = async ({ prompt, type: kind }) => {
    setAiBusy(true);
    setAiError('');
    try {
      const created = await api.json('/api/productions/productions/generate/', {
        method: 'POST',
        body: JSON.stringify({ prompt, type: kind }),
      });
      setAiOpen(false);
      await loadList();
      await loadSelected(created.id);
    } catch (err) {
      setAiError(err.message);
    } finally {
      setAiBusy(false);
    }
  };

  const filteredHint = useMemo(() => {
    if (!showArchived && !query && !typeFilter) return '';
    return `${productions.length} shown`;
  }, [productions.length, query, showArchived, typeFilter]);

  if (loading) return <div className="p-8 text-center text-stone-800">Loading…</div>;
  if (!user) {
    window.location.replace(getLoginUrl('/app/productions/'));
    return null;
  }

  return (
    <div className="min-h-screen bg-[#f4f1ea] text-[#2a241f]">
      <header className="sticky top-0 z-20 border-b border-stone-200 bg-[#fffdf8]/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
          <AppsMenu current="productions" />
          <span className="text-sm font-semibold">Productions</span>
          <div className="ml-auto flex items-center gap-3 text-sm text-stone-800">
            <span className="hidden sm:inline">{user.displayname || user.email}</span>
            <button type="button" className="hover:text-stone-950" onClick={logout}>Log out</button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        {error && <p className="prod-error">{error}</p>}
        {selected ? (
          <ProductionDetail
            production={selected}
            types={types}
            sceneTypes={sceneTypes}
            fontSize={fontSize}
            onFontSize={changeFontSize}
            onBack={() => setSelected(null)}
            onReload={async (id) => {
              await loadList();
              await loadSelected(id || selected.id);
            }}
            onDeleted={() => {
              setSelected(null);
              loadList();
            }}
          />
        ) : (
          <div>
            <form onSubmit={createProduction} className="prod-create mb-4">
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="New production title"
                required
              />
              <select value={type} onChange={(event) => setType(event.target.value)}>
                {types.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
              <button type="submit" className="prod-primary" disabled={busy}>Create</button>
              <button type="button" className="prod-ghost" onClick={() => { setAiError(''); setAiOpen(true); }}>
                Create with AI
              </button>
              <button type="button" className="prod-ghost" disabled={busy} onClick={() => importRef.current?.click()}>
                Import
              </button>
              <button type="button" className="prod-ghost" disabled={busy} onClick={exportAll}>
                Export all
              </button>
              <input
                ref={importRef}
                type="file"
                accept="application/json,.json"
                className="hidden"
                onChange={importFromFile}
              />
            </form>
            <div className="prod-filters mb-4 flex flex-wrap gap-2">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search title or tags"
              />
              <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
                <option value="">All types</option>
                {types.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
              <label className="flex items-center gap-2 text-sm text-[var(--text-color)]">
                <input
                  type="checkbox"
                  checked={showArchived}
                  onChange={(event) => setShowArchived(event.target.checked)}
                />
                Show archived
              </label>
              {filteredHint && <span className="self-center text-sm text-[var(--text-color)]">{filteredHint}</span>}
            </div>
            <ul className="prod-list">
              {productions.map((item) => (
                <li key={item.id}>
                  <button type="button" className="prod-card" onClick={() => loadSelected(item.id)}>
                    <strong>{item.title}</strong>
                    <span>
                      {item.type_label}
                      {item.subtitle ? ` · ${item.subtitle}` : ''}
                      {item.total_duration ? ` · ${item.total_duration}` : ''}
                      {item.scene_count != null ? ` · ${item.scene_count} scenes` : ''}
                      {item.is_archived ? ' · Archived' : ''}
                    </span>
                  </button>
                </li>
              ))}
              {productions.length === 0 && (
                <li className="prod-empty">No productions yet. Create one to start a rundown.</li>
              )}
            </ul>
          </div>
        )}
      </main>
      {aiOpen && (
        <CreateWithAiModal
          types={types}
          defaultType={type}
          busy={aiBusy}
          error={aiError}
          onClose={() => { if (!aiBusy) setAiOpen(false); }}
          onGenerate={createWithAi}
        />
      )}
    </div>
  );
}
