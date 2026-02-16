import React, { useState, useEffect, useCallback } from 'react';
import { Link, useLocation } from 'react-router-dom';
import ThemeToggle from './ThemeToggle';
import UserMenu from './UserMenu';
import api from '../services/api';
import CadViewer from './cad/CadViewer';
import CadScriptEditor from './cad/CadScriptEditor';
import CadParamsForm from './cad/CadParamsForm';
import CadDocsPanel from './cad/CadDocsPanel';

const API_BASE = '/api/cad';

const NEW_MODEL_TEMPLATE = (name) => `"""
${name} - parameterized model.
Define PARAMETERS dict and build(params) that returns ThAssembly.
"""
from cadlib import ThBody, ThAssembly

PARAMETERS = {
    "width": 10,
    "height": 10,
    "depth": 10,
}


def build(params):
    w = params.get("width", 10)
    h = params.get("height", 10)
    d = params.get("depth", 10)
    box = ThBody.box(w, h, d)
    assembly = ThAssembly("${name.replace(/"/g, '')}")
    assembly.add(box)
    return assembly
`;

export default function CadApp() {
  const location = useLocation();
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState(null);
  const [script, setScript] = useState('');
  const [params, setParams] = useState({});
  const [paramValues, setParamValues] = useState({});
  const [documentation, setDocumentation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [rendering, setRendering] = useState(false);
  const [geometryUrl, setGeometryUrl] = useState(null);
  const [geometryFormat, setGeometryFormat] = useState(null);
  const [activeTab, setActiveTab] = useState('params');
  const [showAxes, setShowAxes] = useState(true);
  const [centerModel, setCenterModel] = useState(true);
  const [debugMode, setDebugMode] = useState(false);
  const [sceneConfigs, setSceneConfigs] = useState([]);
  const [sceneConfig, setSceneConfig] = useState(null);
  const [showNewModal, setShowNewModal] = useState(false);
  const [newModelName, setNewModelName] = useState('');
  const [showSaveSceneModal, setShowSaveSceneModal] = useState(false);
  const [saveSceneName, setSaveSceneName] = useState('');
  const [selectedSceneId, setSelectedSceneId] = useState('');
  const [lightsState, setLightsState] = useState(null);

  const loadModels = useCallback(async () => {
    try {
      const res = await api.fetch(`${API_BASE}/models/`);
      const data = await res.json();
      const list = Array.isArray(data) ? data : data.results || [];
      setModels(list);
    } catch (err) {
      console.error('Failed to load CAD models', err);
      setModels([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadScenes = useCallback(async () => {
    try {
      const res = await api.fetch(`${API_BASE}/scenes/`);
      const data = await res.json();
      setSceneConfigs(data.scenes || []);
    } catch {
      setSceneConfigs([]);
    }
  }, []);

  useEffect(() => {
    loadModels();
    loadScenes();
  }, [loadModels, loadScenes]);

  useEffect(() => {
    if (sceneConfigs.length > 0 && !selectedSceneId) {
      setSelectedSceneId(sceneConfigs[0].id);
    }
  }, [sceneConfigs]);

  const selectModel = useCallback(
    async (model) => {
      if (!model) {
        setSelectedModel(null);
        setScript('');
        setParams({});
        setParamValues({});
        setDocumentation(null);
        setGeometryUrl(null);
        return;
      }
      try {
        const res = await api.fetch(`${API_BASE}/models/${model.id}/`);
        const data = await res.json();
        setSelectedModel(data);
        setScript(data.script || '');
        setParams(data.parameters || {});
        setParamValues(data.parameters || {});
        const metaRes = await api.fetch(`${API_BASE}/models/${model.id}/meta/`);
        if (metaRes.ok) {
          const meta = await metaRes.json();
          setDocumentation(meta.documentation);
        } else {
          setDocumentation(null);
        }
        setGeometryUrl(null);
      } catch (err) {
        console.error('Failed to load model', err);
      }
    },
    []
  );

  const handleSave = async () => {
    if (!selectedModel) return;
    try {
      const res = await api.fetch(`${API_BASE}/models/${selectedModel.id}/`, {
        method: 'PUT',
        body: JSON.stringify({ script }),
      });
      if (!res.ok) {
        const err = await res.json();
        alert(err.script || err.detail || 'Save failed');
        return;
      }
      await loadModels();
      await handleRender();
    } catch (err) {
      alert('Save failed: ' + err.message);
    }
  };

  const handleRender = async () => {
    if (!selectedModel) return;
    setRendering(true);
    try {
      const url = `${API_BASE}/models/${selectedModel.id}/render${debugMode ? '?debug=1' : ''}`;
      const res = await api.fetch(url, {
        method: 'POST',
        body: JSON.stringify({ parameters: paramValues }),
      });
      const data = await res.json();
      if (!res.ok) {
        const msg = data.error || data.detail || 'Render failed';
        alert(Array.isArray(msg) ? msg[0]?.msg : msg);
        return;
      }
      const geomUrl = data.url || `${API_BASE}/models/${selectedModel.id}/geometry/`;
      setGeometryUrl(geomUrl + '?t=' + Date.now());
      setGeometryFormat(data.format || 'glb');
      if (data.documentation) setDocumentation(data.documentation);
    } catch (err) {
      alert('Render failed: ' + err.message);
    } finally {
      setRendering(false);
    }
  };

  const handleCreateModel = async () => {
    const name = newModelName.trim();
    if (!name) return;
    try {
      const res = await api.fetch(`${API_BASE}/models/`, {
        method: 'POST',
        body: JSON.stringify({ name, script: NEW_MODEL_TEMPLATE(name) }),
      });
      if (!res.ok) {
        const err = await res.json();
        alert(err.script || err.detail || 'Create failed');
        return;
      }
      const data = await res.json();
      setShowNewModal(false);
      setNewModelName('');
      await loadModels();
      selectModel(data);
    } catch (err) {
      alert('Create failed: ' + err.message);
    }
  };

  const handleLoadScene = async () => {
    const id = selectedSceneId;
    if (!id) return;
    try {
      const res = await api.fetch(`${API_BASE}/scenes/${id}/`);
      if (res.ok) {
        const config = await res.json();
        setSceneConfig(config);
      }
    } catch (err) {
      console.error('Failed to load scene', err);
    }
  };

  const handleSaveScene = async () => {
    const name = saveSceneName.trim();
    if (!name) return;
    const sceneId = name.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '') || 'scene';
    const existing = sceneConfigs.find((s) => s.id === sceneId);
    const config = sceneConfig || {
      name,
      camera: { position: [50, 50, 50], target: [0, 0, 0] },
      background: '#1a1a2e',
      lights: [],
    };
    config.name = name;
    try {
      const url = existing ? `${API_BASE}/scenes/${sceneId}/` : `${API_BASE}/scenes/`;
      const method = existing ? 'PUT' : 'POST';
      const body = existing ? JSON.stringify({ name, config }) : JSON.stringify({ name, config });
      const res = await api.fetch(url, { method, body });
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || err.error || 'Save failed');
        return;
      }
      setShowSaveSceneModal(false);
      setSaveSceneName('');
      await loadScenes();
    } catch (err) {
      alert('Save failed: ' + err.message);
    }
  };

  const handleDeleteModel = async () => {
    if (!selectedModel || !confirm(`Delete model "${selectedModel.name}"?`)) return;
    try {
      await api.fetch(`${API_BASE}/models/${selectedModel.id}/`, { method: 'DELETE' });
      setSelectedModel(null);
      setScript('');
      setGeometryUrl(null);
      await loadModels();
    } catch (err) {
      alert('Delete failed: ' + err.message);
    }
  };

  const handleDownloadStl = async () => {
    if (!selectedModel) return;
    try {
      const res = await api.fetch(`${API_BASE}/models/${selectedModel.id}/export/stl/`);
      if (!res.ok) throw new Error('Download failed');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${selectedModel.name}.stl`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      alert('Download failed: ' + err.message);
    }
  };

  return (
    <div className="min-h-screen bg-[#0d1117] text-[#e6edf3] flex flex-col">
      <header className="flex items-center justify-between gap-3 p-4 border-b border-[#30363d] bg-[#161b22]">
        <nav className="flex items-center gap-4">
          <Link
            to="/"
            className={`text-sm font-medium ${location.pathname === '/' ? 'text-[#58a6ff]' : 'text-[#8b949e] hover:text-[#e6edf3]'}`}
          >
            People
          </Link>
          <Link
            to="/cad"
            className={`text-sm font-medium ${location.pathname.startsWith('/cad') ? 'text-[#58a6ff]' : 'text-[#8b949e] hover:text-[#e6edf3]'}`}
          >
            CAD
          </Link>
        </nav>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <UserMenu />
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-[260px] border-r border-[#30363d] bg-[#161b22] p-4 overflow-y-auto">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[#8b949e] mb-3">Models</h2>
          <div className="flex flex-col gap-1 mb-4">
            {loading ? (
              <p className="text-sm text-[#8b949e]">Loading...</p>
            ) : (
              models.map((m) => (
                <button
                  key={m.id}
                  onClick={() => selectModel(m)}
                  className={`text-left px-3 py-2 rounded-md text-sm transition-colors ${
                    selectedModel?.id === m.id
                      ? 'bg-[#58a6ff] text-white'
                      : 'hover:bg-[#21262d] text-[#e6edf3]'
                  }`}
                >
                  {m.name}
                </button>
              ))
            )}
          </div>
          <button
            onClick={() => setShowNewModal(true)}
            className="w-full py-2 px-3 rounded-md bg-[#58a6ff] hover:bg-[#79b8ff] text-white text-sm font-medium"
          >
            + New Model
          </button>
        </aside>

        <main className="flex-1 flex overflow-hidden">
          <div className="flex-1 flex flex-col min-w-0" style={{ width: '40%', maxWidth: '70%' }}>
            <div className="flex-shrink-0 border-b border-[#30363d] bg-[#161b22] flex flex-col" style={{ minHeight: '100px', height: '220px' }}>
              <div className="flex border-b border-[#30363d] bg-[#21262d]">
                <button
                  onClick={() => setActiveTab('params')}
                  className={`px-4 py-2 text-sm font-medium ${activeTab === 'params' ? 'text-[#58a6ff] border-b-2 border-[#58a6ff] bg-[#161b22]' : 'text-[#8b949e] border-b-2 border-transparent'}`}
                >
                  Parameters
                </button>
                <button
                  onClick={() => setActiveTab('docs')}
                  className={`px-4 py-2 text-sm font-medium ${activeTab === 'docs' ? 'text-[#58a6ff] border-b-2 border-[#58a6ff] bg-[#161b22]' : 'text-[#8b949e] border-b-2 border-transparent'}`}
                >
                  Documentation
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4">
                {activeTab === 'params' && (
                  <>
                    <CadParamsForm parameters={params} values={paramValues} onChange={setParamValues} />
                    <label className="flex items-center gap-2 mt-3 text-xs text-[#8b949e] cursor-pointer">
                      <input
                        type="checkbox"
                        checked={debugMode}
                        onChange={(e) => setDebugMode(e.target.checked)}
                      />
                      Debug: export text (ASCII STL, GLTF JSON) for inspection
                    </label>
                    <button
                      onClick={handleRender}
                      disabled={rendering || !selectedModel}
                      className="mt-3 px-4 py-2 rounded-md bg-[#58a6ff] hover:bg-[#79b8ff] text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {rendering ? 'Rendering...' : 'Render'}
                    </button>
                  </>
                )}
                {activeTab === 'docs' && <CadDocsPanel documentation={documentation} />}
              </div>
            </div>

            <div className="flex-1 flex flex-col min-h-0 border-t border-[#30363d]">
              <div className="flex items-center justify-between px-4 py-2 bg-[#21262d] border-b border-[#30363d]">
                <span className="text-sm font-medium">{selectedModel?.name || 'Select a model'}</span>
                <div className="flex gap-2">
                  {selectedModel && (
                    <>
                      <button
                        onClick={handleSave}
                        className="px-3 py-1 text-sm rounded border border-[#30363d] hover:bg-[#30363d]"
                      >
                        Save
                      </button>
                      <button
                        onClick={handleDeleteModel}
                        className="px-3 py-1 text-sm rounded border border-red-900/50 text-red-400 hover:bg-red-900/20"
                      >
                        Delete
                      </button>
                    </>
                  )}
                </div>
              </div>
              <div className="flex-1 min-h-[120px]">
                <CadScriptEditor value={script} onChange={setScript} />
              </div>
            </div>
          </div>

          <div className="flex-1 flex flex-col min-w-[300px] border-l border-[#30363d]">
            <div className="flex items-center gap-2 p-2 bg-[#21262d] border-b border-[#30363d] flex-wrap">
              {selectedModel && geometryUrl && (
                <button
                  onClick={handleDownloadStl}
                  className="px-3 py-1 text-sm rounded border border-[#30363d] hover:bg-[#30363d]"
                >
                  Download STL (3D Print)
                </button>
              )}
              <div className="flex items-center gap-2">
                <label className="text-xs text-[#8b949e]">Scene:</label>
                <select
                  value={selectedSceneId}
                  onChange={(e) => setSelectedSceneId(e.target.value)}
                  className="px-2 py-1 rounded border border-[#30363d] bg-[#21262d] text-sm min-w-[100px]"
                >
                  <option value="">Select...</option>
                  {sceneConfigs.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
                <button
                  onClick={handleLoadScene}
                  className="px-2 py-1 text-sm rounded border border-[#30363d] hover:bg-[#30363d]"
                >
                  Load
                </button>
                <button
                  onClick={() => {
                    setShowSaveSceneModal(true);
                    setSaveSceneName('');
                  }}
                  className="px-2 py-1 text-sm rounded border border-[#30363d] hover:bg-[#30363d]"
                >
                  Save current
                </button>
              </div>
              <label className="flex items-center gap-1 text-sm text-[#8b949e] cursor-pointer">
                <input type="checkbox" checked={showAxes} onChange={(e) => setShowAxes(e.target.checked)} />
                Axes
              </label>
              <label className="flex items-center gap-1 text-sm text-[#8b949e] cursor-pointer">
                <input type="checkbox" checked={centerModel} onChange={(e) => setCenterModel(e.target.checked)} />
                Center model
              </label>
            </div>

            <div className="flex-1 relative min-h-[400px]">
              <CadViewer
                geometryUrl={geometryUrl}
                format={geometryFormat}
                sceneConfig={sceneConfig}
                showAxes={showAxes}
                centerModel={centerModel}
                lightsState={lightsState}
                onLightsChange={(s) => setLightsState(s)}
              />
              {!geometryUrl && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/50 text-[#8b949e]">
                  <p>Render a model to view geometry</p>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>

      {showNewModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#161b22] p-6 rounded-lg border border-[#30363d] min-w-[320px]">
            <h3 className="text-lg font-semibold mb-4">New Model</h3>
            <input
              type="text"
              value={newModelName}
              onChange={(e) => setNewModelName(e.target.value)}
              placeholder="Model name"
              className="w-full px-3 py-2 rounded border border-[#30363d] bg-[#21262d] text-[#e6edf3] mb-4"
              onKeyDown={(e) => e.key === 'Enter' && handleCreateModel()}
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => {
                  setShowNewModal(false);
                  setNewModelName('');
                }}
                className="px-4 py-2 rounded border border-[#30363d] hover:bg-[#30363d]"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateModel}
                className="px-4 py-2 rounded bg-[#58a6ff] hover:bg-[#79b8ff] text-white"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {showSaveSceneModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#161b22] p-6 rounded-lg border border-[#30363d] min-w-[320px]">
            <h3 className="text-lg font-semibold mb-4">Save Scene Config</h3>
            <input
              type="text"
              value={saveSceneName}
              onChange={(e) => setSaveSceneName(e.target.value)}
              placeholder="Scene name (e.g. Studio)"
              className="w-full px-3 py-2 rounded border border-[#30363d] bg-[#21262d] text-[#e6edf3] mb-4"
              onKeyDown={(e) => e.key === 'Enter' && handleSaveScene()}
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => {
                  setShowSaveSceneModal(false);
                  setSaveSceneName('');
                }}
                className="px-4 py-2 rounded border border-[#30363d] hover:bg-[#30363d]"
              >
                Cancel
              </button>
              <button onClick={handleSaveScene} className="px-4 py-2 rounded bg-[#58a6ff] hover:bg-[#79b8ff] text-white">
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
