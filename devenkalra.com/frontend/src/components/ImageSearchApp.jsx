import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';

const PAGE = 35;
const STORE_KEY = 'bing-image-search:v2';
const SAVED_KEY = 'bing-image-search:saved';
const LB_MIN_ZOOM = 1;
const LB_MAX_ZOOM = 8;

const EMPTY_FILTERS = {
  query: '',
  bingSize: '',
  aspect: '',
  bingDate: '',
  safeSearch: 'moderate',
  minW: '',
  minH: '',
  maxW: '',
  maxH: '',
  minKb: '',
  maxKb: '',
  minMatches: '24',
  maxLoadMore: '5',
  minQuality: '',
  minSharp: '',
  minContrast: '',
  minExposure: '',
  criteriaOpen: true,
  savesOpen: false,
  gridFit: false,
};

async function api(path, { token, method = 'GET', body, json = true } = {}) {
  const headers = { Accept: json ? 'application/json' : '*/*' };
  if (token) headers.Authorization = `Token ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(`/api/images/${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!json) {
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || err.detail || `Request failed (${res.status})`);
    }
    return res;
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || data.detail || `Request failed (${res.status})`);
  }
  return data;
}

function loadJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return parsed ?? fallback;
  } catch {
    return fallback;
  }
}

function saveJson(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore quota */
  }
}

function num(value) {
  if (value === '' || value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function intParam(value, fallback, min) {
  const n = num(value);
  if (n == null) return fallback;
  return Math.max(min, Math.floor(n));
}

function itemKey(item) {
  return (item && (item.image_url || item.cdn_url || '')) || '';
}

function itemKeys(item) {
  const keys = [];
  if (item.md5) keys.push(`md5:${String(item.md5).toLowerCase()}`);
  if (item.mid) keys.push(`mid:${String(item.mid).toLowerCase()}`);
  if (item.cid) keys.push(`cid:${String(item.cid).toLowerCase()}`);
  const thumb = String(item.thumb_url || '').match(/[?&]id=([^&]+)/i);
  if (thumb) keys.push(`th:${decodeURIComponent(thumb[1]).toLowerCase()}`);
  try {
    const parsed = new URL(item.image_url || item.cdn_url || '', 'https://placeholder.invalid');
    let host = parsed.hostname.replace(/^www\./i, '').toLowerCase();
    let path = decodeURIComponent(parsed.pathname).replace(/\/$/, '').toLowerCase();
    path = path.replace(/[-_]\d{2,5}x\d{2,5}(?=\.[a-z0-9]{3,4}$)/i, '');
    if (host && path) keys.push(`url:${host}${path}`);
  } catch {
    /* ignore */
  }
  return keys;
}

function takeUnique(batch, seen) {
  const unique = [];
  for (const item of batch) {
    const keys = itemKeys(item);
    if (keys.some((key) => seen.has(key))) continue;
    keys.forEach((key) => seen.add(key));
    unique.push(item);
  }
  return unique;
}

function matches(item, f) {
  if (f.minW != null && item.width < f.minW) return false;
  if (f.minH != null && item.height < f.minH) return false;
  if (f.maxW != null && item.width > f.maxW) return false;
  if (f.maxH != null && item.height > f.maxH) return false;
  const sizeFilter = f.minKb != null || f.maxKb != null;
  if (sizeFilter) {
    if (!(item.bytes > 0)) return false;
    const kb = item.bytes / 1024;
    if (f.minKb != null && kb < f.minKb) return false;
    if (f.maxKb != null && kb > f.maxKb) return false;
  }
  const qualityFilter =
    f.minQuality != null || f.minSharp != null || f.minContrast != null || f.minExposure != null;
  if (qualityFilter) {
    const q = item.quality;
    if (!q || !(q.score >= 0)) return false;
    if (f.minQuality != null && q.score < f.minQuality) return false;
    if (f.minSharp != null && q.sharpness < f.minSharp) return false;
    if (f.minContrast != null && q.contrast < f.minContrast) return false;
    if (f.minExposure != null && q.exposure < f.minExposure) return false;
  }
  return true;
}

function formatBytes(bytes) {
  if (bytes == null) return 'checking size';
  if (bytes < 0) return 'size unknown';
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(kb < 10 ? 1 : 0)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function formatQuality(q) {
  if (q == null) return 'checking quality';
  if (!(q.score >= 0)) return 'quality n/a';
  return `Q${q.score} · sharp ${q.sharpness} · con ${q.contrast}`;
}

function formatQualityDetail(q) {
  if (q == null) return 'checking quality';
  if (!(q.score >= 0)) return 'quality n/a';
  const bits = [
    `Q${q.score}`,
    `sharp ${q.sharpness}`,
    `contrast ${q.contrast}`,
    `exposure ${q.exposure}`,
    `compression ${q.compression}`,
  ];
  if (q.format) bits.push(q.format);
  if (q.width && q.height) bits.push(`${q.width}×${q.height} decoded`);
  return bits.join(' · ');
}

function filenameFromHeader(header, fallback) {
  if (!header) return fallback;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star) {
    try { return decodeURIComponent(star[1]); } catch { /* ignore */ }
  }
  const quoted = /filename="([^"]+)"/i.exec(header);
  if (quoted) return quoted[1];
  const plain = /filename=([^;]+)/i.exec(header);
  if (plain) return plain[1].trim();
  return fallback;
}

function triggerBrowserDownload(blob, filename) {
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 4000);
}

function beginImageUrlDrag(e, url) {
  if (!url) {
    e.preventDefault();
    return;
  }
  e.stopPropagation();
  e.dataTransfer.effectAllowed = 'copy';
  e.dataTransfer.setData('text/uri-list', `${url}\r\n`);
  e.dataTransfer.setData('text/plain', url);
  const safe = String(url).replace(/"/g, '&quot;');
  e.dataTransfer.setData('text/html', `<img src="${safe}"><a href="${safe}">${safe}</a>`);
}

function Thumb({ item }) {
  const sources = [item.image_url, item.cdn_url, item.thumb_url].filter(Boolean);
  const [src, setSrc] = useState(sources[0] || '');
  return (
    <img
      alt=""
      loading="lazy"
      src={src}
      onError={() => {
        const idx = sources.indexOf(src);
        if (idx >= 0 && sources[idx + 1]) setSrc(sources[idx + 1]);
      }}
    />
  );
}

export function ImageSearchApp() {
  const { token, isAuthenticated, openSocialLoginModal } = useAuth();
  const [form, setForm] = useState(() => ({ ...EMPTY_FILTERS, ...loadJson(STORE_KEY, {}) }));
  const [items, setItems] = useState([]);
  const [offset, setOffset] = useState(0);
  const [extraLoads, setExtraLoads] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [downloading, setDownloading] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [savedList, setSavedList] = useState(() => loadJson(SAVED_KEY, []));
  const [savedId, setSavedId] = useState('');
  const [lbIndex, setLbIndex] = useState(-1);
  const [lbInfoOn, setLbInfoOn] = useState(false);
  const [lbZoom, setLbZoom] = useState(1);
  const [lbPan, setLbPan] = useState({ x: 0, y: 0 });
  const [lbPanning, setLbPanning] = useState(false);
  const searchGen = useRef(0);
  const lbStageRef = useRef(null);
  const lbDrag = useRef(null);
  const itemsRef = useRef(items);
  itemsRef.current = items;

  const currentFilters = useMemo(() => ({
    minW: num(form.minW),
    minH: num(form.minH),
    maxW: num(form.maxW),
    maxH: num(form.maxH),
    minKb: num(form.minKb),
    maxKb: num(form.maxKb),
    minQuality: num(form.minQuality),
    minSharp: num(form.minSharp),
    minContrast: num(form.minContrast),
    minExposure: num(form.minExposure),
  }), [form]);

  const needsSizes = currentFilters.minKb != null || currentFilters.maxKb != null;
  const needsQuality =
    currentFilters.minQuality != null
    || currentFilters.minSharp != null
    || currentFilters.minContrast != null
    || currentFilters.minExposure != null;

  const shownItems = useMemo(
    () => items.filter((item) => matches(item, currentFilters)),
    [items, currentFilters],
  );

  const persistForm = useCallback((next) => {
    saveJson(STORE_KEY, next);
  }, []);

  const updateForm = (patch) => {
    setForm((prev) => {
      const next = { ...prev, ...patch };
      persistForm(next);
      return next;
    });
  };

  const setSelectedOn = (item, on) => {
    const key = itemKey(item);
    if (!key) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });
  };

  const fetchPage = useCallback(async (startOffset, currentItems, formState = form) => {
    const query = formState.query.trim();
    if (!query) return { batch: [], nextOffset: startOffset, more: false };
    const params = new URLSearchParams({
      q: query,
      offset: String(startOffset),
      count: String(PAGE),
    });
    if (formState.bingSize) params.set('size', formState.bingSize);
    if (formState.aspect) params.set('aspect', formState.aspect);
    if (formState.bingDate) params.set('date', formState.bingDate);
    if (formState.safeSearch) params.set('safe', formState.safeSearch);
    const minW = num(formState.minW);
    const minH = num(formState.minH);
    if (minW) params.set('min_width', String(minW));
    if (minH) params.set('min_height', String(minH));
    const data = await api(`search/?${params.toString()}`, { token });
    const seen = new Set();
    currentItems.forEach((item) => itemKeys(item).forEach((key) => seen.add(key)));
    const raw = data.images || [];
    const batch = takeUnique(raw, seen);
    return {
      batch,
      nextOffset: Number(data.next_offset != null ? data.next_offset : startOffset + PAGE),
      more: raw.length > 0,
    };
  }, [form, token]);

  const ingest = useCallback(async (batch, gen, opts = {}) => {
    if (!batch.length) return;
    const waitSizes = opts.needsSizes ?? needsSizes;
    const waitQuality = opts.needsQuality ?? needsQuality;
    const sizeP = (async () => {
      const urls = batch.map((item) => item.image_url || item.cdn_url).filter(Boolean);
      if (!urls.length) return;
      try {
        const data = await api('sizes/', { token, method: 'POST', body: { urls } });
        const sizes = data.sizes || {};
        if (gen !== searchGen.current) return;
        setItems((prev) => prev.map((item) => {
          if (!batch.some((b) => itemKey(b) === itemKey(item))) return item;
          const key = item.image_url || item.cdn_url;
          if (key && sizes[key] != null) return { ...item, bytes: sizes[key] };
          if (item.bytes == null) return { ...item, bytes: -1 };
          return item;
        }));
      } catch {
        if (gen !== searchGen.current) return;
        setItems((prev) => prev.map((item) => (
          batch.some((b) => itemKey(b) === itemKey(item)) && item.bytes == null
            ? { ...item, bytes: -1 }
            : item
        )));
      }
    })();
    const qualityP = (async () => {
      const payload = {
        items: batch.map((item) => ({
          url: item.image_url || item.cdn_url,
          bytes: item.bytes > 0 ? item.bytes : null,
          width: item.width,
          height: item.height,
        })).filter((row) => row.url),
      };
      if (!payload.items.length) return;
      try {
        const data = await api('quality/', { token, method: 'POST', body: payload });
        const quality = data.quality || {};
        if (gen !== searchGen.current) return;
        setItems((prev) => prev.map((item) => {
          const key = item.image_url || item.cdn_url;
          if (!batch.some((b) => itemKey(b) === itemKey(item))) return item;
          if (key && quality[key]) return { ...item, quality: quality[key] };
          if (item.quality == null) return { ...item, quality: { score: -1 } };
          return item;
        }));
      } catch {
        if (gen !== searchGen.current) return;
        setItems((prev) => prev.map((item) => (
          batch.some((b) => itemKey(b) === itemKey(item)) && item.quality == null
            ? { ...item, quality: { score: -1 } }
            : item
        )));
      }
    })();
    if (waitSizes) await sizeP;
    else sizeP.catch(() => {});
    if (waitQuality) await qualityP;
    else qualityP.catch(() => {});
  }, [needsQuality, needsSizes, token]);

  const fill = useCallback(async (reset, formOverride) => {
    const f = formOverride || form;
    const query = f.query.trim();
    if (!query || !token) return;
    const gen = ++searchGen.current;
    const n = intParam(f.minMatches, 24, 1);
    const m = intParam(f.maxLoadMore, 5, 0);
    const filters = {
      minW: num(f.minW),
      minH: num(f.minH),
      maxW: num(f.maxW),
      maxH: num(f.maxH),
      minKb: num(f.minKb),
      maxKb: num(f.maxKb),
      minQuality: num(f.minQuality),
      minSharp: num(f.minSharp),
      minContrast: num(f.minContrast),
      minExposure: num(f.minExposure),
    };
    const ingestOpts = {
      needsSizes: filters.minKb != null || filters.maxKb != null,
      needsQuality:
        filters.minQuality != null
        || filters.minSharp != null
        || filters.minContrast != null
        || filters.minExposure != null,
    };
    setLoading(true);
    setError('');
    persistForm(f);
    try {
      let current = itemsRef.current;
      let nextOffset = offset;
      let more = hasMore;
      let extras = 0;
      if (reset) {
        current = [];
        nextOffset = 0;
        more = true;
        setItems([]);
        setSelected(new Set());
        setOffset(0);
        setHasMore(true);
        setExtraLoads(0);
        setProgress('Searching Bing…');
        const page = await fetchPage(0, [], f);
        if (gen !== searchGen.current) return;
        current = page.batch;
        nextOffset = page.nextOffset;
        more = page.more;
        setItems(current);
        setOffset(nextOffset);
        setHasMore(more);
        await ingest(page.batch, gen, ingestOpts);
      } else {
        setProgress('Loading more from Bing…');
      }

      const matchN = () => current.filter((item) => matches(item, filters)).length;

      while (more && extras < m && matchN() < n) {
        if (gen !== searchGen.current) return;
        extras += 1;
        setExtraLoads(extras);
        setProgress(`Loading extra page ${extras}/${m} to reach ${n} matches…`);
        const page = await fetchPage(nextOffset, current, f);
        if (gen !== searchGen.current) return;
        current = current.concat(page.batch);
        nextOffset = page.nextOffset;
        more = page.more;
        setItems(current);
        setOffset(nextOffset);
        setHasMore(more);
        await ingest(page.batch, gen, ingestOpts);
        if (!page.batch.length) break;
      }

      if (!reset && extras === 0 && more) {
        extras = 1;
        setExtraLoads(extras);
        setProgress('Loading more from Bing…');
        const page = await fetchPage(nextOffset, current, f);
        if (gen !== searchGen.current) return;
        current = current.concat(page.batch);
        setItems(current);
        setOffset(page.nextOffset);
        setHasMore(page.more);
        await ingest(page.batch, gen, ingestOpts);
      }
      setProgress('');
    } catch (err) {
      if (gen === searchGen.current) setError(err.message || String(err));
    } finally {
      if (gen === searchGen.current) {
        setLoading(false);
        setProgress('');
      }
    }
  }, [fetchPage, form, hasMore, ingest, offset, persistForm, token]);

  const saveCurrentSearch = () => {
    const name = saveName.trim() || form.query.trim() || 'Untitled search';
    if (!form.query.trim()) {
      setError('Enter a query before saving a search.');
      return;
    }
    const list = [...savedList];
    const existing = list.findIndex((item) => item.name.toLowerCase() === name.toLowerCase());
    const entry = {
      id: existing >= 0 ? list[existing].id : String(Date.now()),
      name,
      savedAt: Date.now(),
      ...form,
    };
    if (existing >= 0) list[existing] = entry;
    else list.unshift(entry);
    setSavedList(list);
    saveJson(SAVED_KEY, list);
    setSaveName(name);
    setSavedId(entry.id);
    setError('');
  };

  const loadSelectedSearch = () => {
    const entry = savedList.find((item) => item.id === savedId);
    if (!entry) return;
    const next = { ...EMPTY_FILTERS, ...entry };
    setForm(next);
    persistForm(next);
    setSaveName(entry.name || '');
    fill(true, next);
  };

  const deleteSelectedSearch = () => {
    if (!savedId) return;
    const list = savedList.filter((item) => item.id !== savedId);
    setSavedList(list);
    saveJson(SAVED_KEY, list);
    setSavedId('');
  };

  const downloadSelected = async () => {
    const chosen = items.filter((item) => selected.has(itemKey(item)));
    if (!chosen.length || downloading) return;
    const asZip = chosen.length > 1;
    setDownloading(true);
    setError('');
    try {
      const res = await api('download/', {
        token,
        method: 'POST',
        json: false,
        body: {
          items: chosen.map((item) => ({
            url: item.image_url || item.cdn_url,
            title: item.title || '',
          })),
        },
      });
      const blob = await res.blob();
      const fallback = asZip
        ? 'bing-images.zip'
        : `${(chosen[0].title || 'image').replace(/[\\/:*?"<>|]+/g, '-').slice(0, 80) || 'image'}.jpg`;
      triggerBrowserDownload(blob, filenameFromHeader(res.headers.get('Content-Disposition'), fallback));
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setDownloading(false);
    }
  };

  const resetView = () => {
    setLbZoom(1);
    setLbPan({ x: 0, y: 0 });
  };

  const setZoom = (nextZoom, originX, originY) => {
    const zoom = Math.min(LB_MAX_ZOOM, Math.max(LB_MIN_ZOOM, nextZoom));
    setLbZoom((prev) => {
      if (zoom === prev) {
        if (zoom === 1) setLbPan({ x: 0, y: 0 });
        return prev;
      }
      const rect = lbStageRef.current?.getBoundingClientRect();
      if (rect && originX != null) {
        const mx = originX - rect.left - rect.width / 2;
        const my = originY - rect.top - rect.height / 2;
        const k = zoom / prev;
        setLbPan((pan) => (
          zoom === 1
            ? { x: 0, y: 0 }
            : { x: mx - (mx - pan.x) * k, y: my - (my - pan.y) * k }
        ));
      } else if (zoom === 1) {
        setLbPan({ x: 0, y: 0 });
      }
      return zoom;
    });
  };

  const closeLightbox = useCallback(() => {
    setLbIndex(-1);
    resetView();
  }, []);

  useEffect(() => {
    if (lbIndex < 0) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') closeLightbox();
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setLbIndex((i) => (shownItems.length ? (i - 1 + shownItems.length) % shownItems.length : i));
        resetView();
      }
      if (e.key === 'ArrowRight') {
        e.preventDefault();
        setLbIndex((i) => (shownItems.length ? (i + 1) % shownItems.length : i));
        resetView();
      }
      if (e.key === '+' || e.key === '=') {
        e.preventDefault();
        setZoom(lbZoom * 1.25);
      }
      if (e.key === '-' || e.key === '_') {
        e.preventDefault();
        setZoom(lbZoom / 1.25);
      }
      if (e.key === '0') {
        e.preventDefault();
        resetView();
      }
      if (e.key === 'i' || e.key === 'I') setLbInfoOn((on) => !on);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [closeLightbox, lbIndex, lbZoom, shownItems.length]);

  if (!isAuthenticated) {
    return (
      <div className="imgsearch-app">
        <p className="imgsearch-muted">Sign in to search images.</p>
        <button type="button" className="editorial-button" onClick={() => openSocialLoginModal()}>
          Sign in
        </button>
      </div>
    );
  }

  const n = intParam(form.minMatches, 24, 1);
  const m = intParam(form.maxLoadMore, 5, 0);
  const pendingSizes = needsSizes ? items.filter((item) => item.bytes == null).length : 0;
  const pendingQuality = needsQuality ? items.filter((item) => item.quality == null).length : 0;
  const allShownSelected = shownItems.length > 0 && shownItems.every((item) => selected.has(itemKey(item)));
  const lbItem = lbIndex >= 0 ? shownItems[lbIndex] : null;
  const lbSources = lbItem
    ? [lbItem.image_url, lbItem.cdn_url, lbItem.thumb_url].filter(Boolean)
    : [];

  return (
    <div className={`imgsearch-app${selectMode ? ' is-selecting' : ''}${form.gridFit ? ' is-fit' : ''}`}>
      <p className="imgsearch-muted">
        Search Bing, then keep only images that match size and quality. Auto-loads until n matches or m extra pages.
      </p>
      <form
        className="imgsearch-panel"
        onSubmit={(e) => {
          e.preventDefault();
          fill(true);
        }}
      >
        <div className="imgsearch-search-row">
          <label>
            Query
            <input
              type="search"
              value={form.query}
              onChange={(e) => updateForm({ query: e.target.value })}
              placeholder="e.g. mountain lake wallpaper"
              required
            />
          </label>
          <button type="submit" className="editorial-button" disabled={loading}>
            {loading ? 'Searching…' : 'Search'}
          </button>
        </div>
        <details
          className="imgsearch-criteria"
          open={form.criteriaOpen}
          onToggle={(e) => updateForm({ criteriaOpen: e.currentTarget.open })}
        >
          <summary>Search criteria</summary>
          <div className="imgsearch-filters">
            <label>
              Bing size
              <select value={form.bingSize} onChange={(e) => updateForm({ bingSize: e.target.value })}>
                <option value="">Any</option>
                <option value="small">Small</option>
                <option value="medium">Medium</option>
                <option value="large">Large</option>
                <option value="wallpaper">Extra large</option>
              </select>
            </label>
            <label>
              Aspect
              <select value={form.aspect} onChange={(e) => updateForm({ aspect: e.target.value })}>
                <option value="">Any</option>
                <option value="square">Square</option>
                <option value="wide">Wide</option>
                <option value="tall">Tall</option>
              </select>
            </label>
            <label>
              Date
              <select value={form.bingDate} onChange={(e) => updateForm({ bingDate: e.target.value })}>
                <option value="">Any</option>
                <option value="day">Past day</option>
                <option value="week">Past week</option>
                <option value="month">Past month</option>
                <option value="year">Past year</option>
              </select>
            </label>
            <label>
              Safe search
              <select value={form.safeSearch} onChange={(e) => updateForm({ safeSearch: e.target.value })}>
                <option value="off">Off</option>
                <option value="moderate">Moderate</option>
                <option value="strict">Strict</option>
              </select>
            </label>
            <label>
              Min width
              <input type="number" min="0" placeholder="px" value={form.minW} onChange={(e) => updateForm({ minW: e.target.value })} />
            </label>
            <label>
              Min height
              <input type="number" min="0" placeholder="px" value={form.minH} onChange={(e) => updateForm({ minH: e.target.value })} />
            </label>
            <label>
              Max width
              <input type="number" min="0" placeholder="px" value={form.maxW} onChange={(e) => updateForm({ maxW: e.target.value })} />
            </label>
            <label>
              Max height
              <input type="number" min="0" placeholder="px" value={form.maxH} onChange={(e) => updateForm({ maxH: e.target.value })} />
            </label>
            <label>
              Min size (KB)
              <input type="number" min="0" placeholder="KB" value={form.minKb} onChange={(e) => updateForm({ minKb: e.target.value })} />
            </label>
            <label>
              Max size (KB)
              <input type="number" min="0" placeholder="KB" value={form.maxKb} onChange={(e) => updateForm({ maxKb: e.target.value })} />
            </label>
            <label>
              Min matches (n)
              <input type="number" min="1" value={form.minMatches} onChange={(e) => updateForm({ minMatches: e.target.value })} />
            </label>
            <label>
              Max load more (m)
              <input type="number" min="0" value={form.maxLoadMore} onChange={(e) => updateForm({ maxLoadMore: e.target.value })} />
            </label>
            <label>
              Min quality
              <input type="number" min="0" max="100" placeholder="0-100" value={form.minQuality} onChange={(e) => updateForm({ minQuality: e.target.value })} />
            </label>
            <label>
              Min sharpness
              <input type="number" min="0" max="100" placeholder="0-100" value={form.minSharp} onChange={(e) => updateForm({ minSharp: e.target.value })} />
            </label>
            <label>
              Min contrast
              <input type="number" min="0" max="100" placeholder="0-100" value={form.minContrast} onChange={(e) => updateForm({ minContrast: e.target.value })} />
            </label>
            <label>
              Min exposure
              <input type="number" min="0" max="100" placeholder="0-100" value={form.minExposure} onChange={(e) => updateForm({ minExposure: e.target.value })} />
            </label>
          </div>
        </details>
        <details
          className="imgsearch-criteria"
          open={form.savesOpen}
          onToggle={(e) => updateForm({ savesOpen: e.currentTarget.open })}
        >
          <summary>Saved searches</summary>
          <div className="imgsearch-search-row">
            <label>
              Save as
              <input
                type="text"
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
                placeholder="Name this search"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    saveCurrentSearch();
                  }
                }}
              />
            </label>
            <button type="button" className="editorial-button secondary" onClick={saveCurrentSearch}>
              Save search
            </button>
          </div>
          <div className="imgsearch-search-row">
            <label>
              Saved searches
              <select value={savedId} onChange={(e) => setSavedId(e.target.value)}>
                <option value="">{savedList.length ? 'Select a saved search' : 'No saved searches'}</option>
                {savedList.map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
            </label>
            <div className="imgsearch-saved-actions">
              <button type="button" className="editorial-button" onClick={loadSelectedSearch} disabled={!savedId}>
                Load
              </button>
              <button type="button" className="editorial-button secondary" onClick={deleteSelectedSearch} disabled={!savedId}>
                Delete
              </button>
            </div>
          </div>
        </details>
      </form>

      <div className="imgsearch-status">
        <div>
          {error ? (
            <span className="imgsearch-error">{error}</span>
          ) : items.length ? (
            <>
              <b>{shownItems.length}</b> of <b>{items.length}</b> images match the current filters.
              {' '}Target <b>{n}</b> matches · extra pages <b>{extraLoads}</b>/<b>{m}</b>.
              {progress ? ` ${progress}` : ''}
              {pendingSizes ? ` Checking file size on ${pendingSizes} more…` : ''}
              {pendingQuality ? ` Scoring quality on ${pendingQuality} more…` : ''}
            </>
          ) : (
            progress || 'Enter a query to search Bing images.'
          )}
        </div>
        <div className="imgsearch-status-actions">
          <button
            type="button"
            className={`editorial-button secondary${form.gridFit ? ' is-active' : ''}`}
            onClick={() => updateForm({ gridFit: !form.gridFit })}
            title={form.gridFit
              ? 'Showing the full image; the longer side fills the cell'
              : 'Crop thumbnails to fill the cell'}
          >
            {form.gridFit ? 'Fitting full' : 'Fit full'}
          </button>
          <button
            type="button"
            className={`editorial-button secondary${selectMode ? ' is-active' : ''}`}
            onClick={() => setSelectMode((v) => !v)}
          >
            {selectMode ? 'Selecting' : 'Select'}
          </button>
          {selectMode && (
            <button
              type="button"
              className="editorial-button secondary"
              onClick={() => {
                const next = new Set(selected);
                if (allShownSelected) shownItems.forEach((item) => next.delete(itemKey(item)));
                else shownItems.forEach((item) => next.add(itemKey(item)));
                setSelected(next);
              }}
            >
              {allShownSelected ? 'Clear' : 'Select all'}
            </button>
          )}
          <button
            type="button"
            className="editorial-button"
            disabled={selected.size === 0 || downloading}
            onClick={downloadSelected}
          >
            {downloading
              ? 'Preparing…'
              : selected.size
                ? `Download selected (${selected.size})`
                : 'Download selected'}
          </button>
        </div>
      </div>

      {!shownItems.length ? (
        <div className="imgsearch-empty">
          {items.length
            ? 'No images match the current dimension/size filters.'
            : 'Results will show up here as a filterable grid.'}
        </div>
      ) : (
        <div className="imgsearch-grid">
          {shownItems.map((item, i) => {
            const key = itemKey(item);
            const isSelected = selected.has(key);
            return (
              <article
                key={key || i}
                className={`imgsearch-card${isSelected ? ' is-selected' : ''}`}
                onClick={() => {
                  if (selectMode) setSelectedOn(item, !isSelected);
                  else {
                    setLbIndex(i);
                    resetView();
                  }
                }}
              >
                <label className="imgsearch-card-select" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={(e) => setSelectedOn(item, e.target.checked)}
                  />
                </label>
                <div className="imgsearch-thumb"><Thumb item={item} /></div>
                <div className="imgsearch-meta">
                  <div>{item.width} × {item.height} · {formatBytes(item.bytes)}</div>
                  <div>{formatQuality(item.quality)}</div>
                  <div className="imgsearch-title">{item.title || item.source_url || 'Untitled'}</div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {hasMore && (
        <div className="imgsearch-more">
          <button type="button" className="editorial-button secondary" disabled={loading} onClick={() => fill(false)}>
            Load more
          </button>
        </div>
      )}

      {lbItem && (
        <div className="imgsearch-lightbox" onClick={(e) => { if (e.target === e.currentTarget) closeLightbox(); }}>
          <button type="button" className="imgsearch-lb-nav prev" aria-label="Previous image" disabled={shownItems.length < 2} onClick={(e) => { e.stopPropagation(); setLbIndex((i) => (i - 1 + shownItems.length) % shownItems.length); resetView(); }}>‹</button>
          <div
            className="imgsearch-lb-stage"
            ref={lbStageRef}
            onWheel={(e) => {
              e.preventDefault();
              setZoom(lbZoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12), e.clientX, e.clientY);
            }}
            onPointerDown={(e) => {
              if (e.button !== 0) return;
              // At 1x, dragging the photo itself is a native drag (same as the grid).
              if (lbZoom <= 1 && e.target.tagName === 'IMG') return;
              e.preventDefault();
              lbDrag.current = { x: e.clientX, y: e.clientY, tx: lbPan.x, ty: lbPan.y, moved: false };
              lbStageRef.current?.setPointerCapture(e.pointerId);
              setLbPanning(true);
            }}
            onPointerMove={(e) => {
              if (!lbDrag.current) return;
              const dx = e.clientX - lbDrag.current.x;
              const dy = e.clientY - lbDrag.current.y;
              if (Math.abs(dx) > 2 || Math.abs(dy) > 2) lbDrag.current.moved = true;
              setLbPan({ x: lbDrag.current.tx + dx, y: lbDrag.current.ty + dy });
            }}
            onPointerUp={(e) => {
              const moved = lbDrag.current?.moved;
              lbDrag.current = null;
              setLbPanning(false);
              if (!moved && e.target === e.currentTarget) closeLightbox();
            }}
            onPointerCancel={() => {
              lbDrag.current = null;
              setLbPanning(false);
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <img
              alt=""
              draggable={lbZoom <= 1}
              src={lbSources[0] || ''}
              onDragStart={(e) => beginImageUrlDrag(e, lbItem.image_url || lbItem.cdn_url || lbSources[0])}
              onError={(e) => {
                const img = e.currentTarget;
                const idx = lbSources.indexOf(img.src);
                if (idx >= 0 && lbSources[idx + 1]) img.src = lbSources[idx + 1];
              }}
              onDoubleClick={(e) => {
                e.preventDefault();
                if (lbZoom > 1) resetView();
                else setZoom(2.5, e.clientX, e.clientY);
              }}
              style={{
                transform: `translate(${lbPan.x}px, ${lbPan.y}px) scale(${lbZoom})`,
                cursor: lbPanning ? 'grabbing' : 'grab',
              }}
            />
          </div>
          <button type="button" className="imgsearch-lb-nav next" aria-label="Next image" disabled={shownItems.length < 2} onClick={(e) => { e.stopPropagation(); setLbIndex((i) => (i + 1) % shownItems.length); resetView(); }}>›</button>
          <div className="imgsearch-lb-toolbar imgsearch-lb-zoom">
            <button type="button" onClick={() => setZoom(lbZoom / 1.25)}>−</button>
            <button type="button" onClick={resetView}>{Math.round(lbZoom * 100)}%</button>
            <button type="button" onClick={() => setZoom(lbZoom * 1.25)}>+</button>
          </div>
          <div className="imgsearch-lb-toolbar">
            <span>{lbIndex + 1} / {shownItems.length}</span>
            <label>
              <input
                type="checkbox"
                checked={selected.has(itemKey(lbItem))}
                onChange={(e) => setSelectedOn(lbItem, e.target.checked)}
              />
              Select
            </label>
            <button type="button" className={lbInfoOn ? 'is-active' : ''} onClick={() => setLbInfoOn((on) => !on)}>Info</button>
            <button type="button" onClick={closeLightbox}>Close</button>
          </div>
          {lbInfoOn && (
            <aside className="imgsearch-lb-info">
              <dl>
                <dt>Dimensions</dt>
                <dd>{lbItem.width} × {lbItem.height}</dd>
                <dt>Size</dt>
                <dd>{formatBytes(lbItem.bytes)}</dd>
                <dt>Quality</dt>
                <dd>{formatQualityDetail(lbItem.quality)}</dd>
                <dt>URL</dt>
                <dd>
                  <a href={lbItem.image_url || lbItem.cdn_url || '#'} target="_blank" rel="noreferrer">
                    {lbItem.image_url || lbItem.cdn_url || '—'}
                  </a>
                </dd>
              </dl>
            </aside>
          )}
        </div>
      )}
    </div>
  );
}
