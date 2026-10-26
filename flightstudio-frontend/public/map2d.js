"use strict";

// 2D map presentation: one line style, a time-keyed map camera, and markers.
// Stored in `{path_id}.2d.json` beside the path. Play in this mode moves the
// aircraft along the solved path without the simulator.

const MAP2D = {
  playing: false,
  paused: false,
  t: 0,
  from: 0,
  to: 0,
  speed: 1,
  lastMs: 0,
  originMs: 0,
  startT: 0,
  frame: 0,
  raf: 0,
  fps: 0,
  placing: false,
  applyingScale: false,
  projectedShift: null,
};

const MARKER_ICONS = {
  PIN: `<svg viewBox="0 0 24 24" width="22" height="22"><path fill="#ff6b6b" stroke="#0b1017" stroke-width="1.4" d="M12 2c3.3 0 6 2.6 6 5.8 0 4.4-6 13-6 13S6 12.2 6 7.8C6 4.6 8.7 2 12 2z"/><circle cx="12" cy="8" r="2.2" fill="#fff"/></svg>`,
  NOTE: `<svg viewBox="0 0 24 24" width="22" height="22"><path fill="#ffc44d" stroke="#0b1017" stroke-width="1.4" d="M5 3h11l5 5v13H5z"/><path fill="none" stroke="#0b1017" stroke-width="1.2" d="M16 3v5h5"/></svg>`,
  FLAG: `<svg viewBox="0 0 24 24" width="22" height="22"><path fill="#4ea1ff" stroke="#0b1017" stroke-width="1.4" d="M6 3h.2L18 8l-11.8 5H6z"/><path stroke="#0b1017" stroke-width="1.8" d="M6 3v18"/></svg>`,
  AIRPORT: `<svg viewBox="0 0 24 24" width="22" height="22"><path fill="#dfe4ec" stroke="#0b1017" stroke-width="1.2" d="M12 2l2 8 8 2-8 2-2 8-2-8-8-2 8-2z"/></svg>`,
};

function emptyLabelStyle() {
  return { display: "RIGHT", color: "#dfe4ec", size_px: 12, weight: "NORMAL", gap_px: 6 };
}

function emptyMapDoc(pathId) {
  return {
    path_id: pathId || "",
    schema_version: 1,
    line: { color: "#4ea1ff", width_px: 8, opacity: 0.95, dash: "SOLID" },
    map_keyframes: [],
    markers: [],
  };
}

function ensureMapDoc() {
  if (!state.mapDoc) state.mapDoc = emptyMapDoc(state.doc?.meta.path_id || "");
  if (!state.mapDoc.map_keyframes) state.mapDoc.map_keyframes = [];
  if (!state.mapDoc.markers) state.mapDoc.markers = [];
  if (!state.mapDoc.line) state.mapDoc.line = emptyMapDoc().line;
  (state.mapDoc.markers || []).forEach((marker) => {
    if (!marker.label) marker.label = emptyLabelStyle();
    if (marker.label.gap_px == null) marker.label.gap_px = 6;
    if (marker.outline == null) marker.outline = false;
  });
  return state.mapDoc;
}

function map2dMode() {
  return state.uiMode === "2d";
}

function clientPlayLabel(fps) {
  const mode = state.uiMode === "3d" ? "3D" : "2D";
  return fps ? `${mode} · ${fps}` : mode;
}

function map2dTouched() {
  ensureMapDoc();
  touched();
}

function leafletDash(dash) {
  if (dash === "DASH") return "8 6";
  if (dash === "DOT") return "1 6";
  return null;
}

function flightLineStyle() {
  if (!map2dMode()) return null;
  const line = ensureMapDoc().line;
  return {
    color: line.color || "#4ea1ff",
    weight: Number(line.width_px) || 8,
    opacity: line.opacity ?? 0.95,
    dashArray: leafletDash(line.dash) || null,
    lineJoin: "round",
    lineCap: "round",
  };
}

function paintFlightLine() {
  if (!layers?.flightTrack) return;
  const style = flightLineStyle();
  if (!style) return;
  layers.flightTrack.eachLayer((layer) => {
    layer.setStyle(style);
    if (layer.options) layer.options.dashArray = style.dashArray;
  });
}

function lerp(a, b, u) {
  return a + (b - a) * u;
}

function lerpHeading(a, b, u) {
  const delta = ((b - a + 180) % 360 + 360) % 360 - 180;
  return ((a + delta * u) % 360 + 360) % 360;
}

function mapViewAt(t) {
  const keys = [...(ensureMapDoc().map_keyframes || [])]
    .sort((a, b) => a.time_offset - b.time_offset);
  if (!keys.length) return null;
  if (t <= keys[0].time_offset) return keys[0];
  if (t >= keys[keys.length - 1].time_offset) return keys[keys.length - 1];
  for (let i = 0; i < keys.length - 1; i++) {
    const start = keys[i], end = keys[i + 1];
    if (t > end.time_offset) continue;
    const span = end.time_offset - start.time_offset;
    const u = span <= 1e-9 ? 0 : (t - start.time_offset) / span;
    return {
      time_offset: t,
      lat: lerp(start.lat, end.lat, u),
      lon: lerp(start.lon, end.lon, u),
      zoom: lerp(start.zoom, end.zoom, u),
      rotation_deg: lerpHeading(start.rotation_deg || 0, end.rotation_deg || 0, u),
    };
  }
  return keys[keys.length - 1];
}

function currentMapView() {
  const centre = map.getCenter();
  const bearing = typeof map.getBearing === "function" ? map.getBearing() : 0;
  return {
    lat: centre.lat,
    lon: centre.lng,
    zoom: map.getZoom(),
    rotation_deg: bearing,
  };
}

function applyMapView(view, instant) {
  if (!view) return;
  const lat = Number(view.lat), lon = Number(view.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
  driveMapView(lat, lon, Number(view.zoom), Number(view.rotation_deg) || 0);
}

const TILE_CACHE = { pending: [], queued: new Set(), loaded: new Set(), inflight: 0, max: 8 };

function activeBasemap() {
  let found = null;
  map.eachLayer((layer) => {
    if (layer instanceof L.TileLayer) found = layer;
  });
  return found;
}

function tileUrlAt(layer, x, y, z) {
  const wrap = 2 ** z;
  if (y < 0 || y >= wrap) return "";
  x = ((x % wrap) + wrap) % wrap;
  if (typeof layer._getSubdomain === "function" && z === layer._tileZoom
      && typeof layer.getTileUrl === "function") {
    return layer.getTileUrl({ x, y, z });
  }
  return L.Util.template(layer._url, {
    s: typeof layer._getSubdomain === "function" ? layer._getSubdomain({ x, y, z }) : "",
    x, y, z, r: "",
  });
}

function viewTileUrls(lat, lon, zoom, buffer = 2) {
  const layer = activeBasemap();
  if (!layer || !map._loaded) return [];
  const native = layer.options.maxNativeZoom ?? layer.options.maxZoom ?? 22;
  const minZ = layer.options.minZoom ?? 0;
  const z = Math.min(native, Math.max(minZ, Math.round(zoom)));
  const ts = layer.getTileSize();
  const half = map.getSize().divideBy(2).multiplyBy(1.5);
  const center = map.project(L.latLng(lat, lon), z);
  const minPx = center.subtract(half).subtract(ts.multiplyBy(buffer));
  const maxPx = center.add(half).add(ts.multiplyBy(buffer));
  const minTile = minPx.unscaleBy(ts).floor();
  const maxTile = maxPx.unscaleBy(ts).ceil();
  const urls = [];
  for (let x = minTile.x; x <= maxTile.x; x++) {
    for (let y = minTile.y; y <= maxTile.y; y++) {
      const url = tileUrlAt(layer, x, y, z);
      if (url) urls.push(url);
    }
  }
  return urls;
}

function rememberTile(url) {
  TILE_CACHE.loaded.add(url);
  if (TILE_CACHE.loaded.size > 2500) {
    const first = TILE_CACHE.loaded.values().next().value;
    TILE_CACHE.loaded.delete(first);
  }
}

function requestTile(url) {
  if (!url || TILE_CACHE.queued.has(url) || TILE_CACHE.loaded.has(url)) return;
  TILE_CACHE.queued.add(url);
  TILE_CACHE.pending.push(url);
  pumpTiles();
}

function pumpTiles() {
  while (TILE_CACHE.inflight < TILE_CACHE.max && TILE_CACHE.pending.length) {
    const url = TILE_CACHE.pending.shift();
    TILE_CACHE.inflight += 1;
    const img = new Image();
    img.decoding = "async";
    img.onload = img.onerror = () => {
      TILE_CACHE.inflight = Math.max(0, TILE_CACHE.inflight - 1);
      rememberTile(url);
      pumpTiles();
    };
    img.src = url;
  }
}

function prefetchView(lat, lon, zoom, opts = {}) {
  const neighbor = opts.neighborZooms !== false;
  const buffer = opts.buffer ?? 2;
  const z = Number(zoom);
  const levels = neighbor ? [z - 1, z, z + 1] : [z];
  for (const level of levels) {
    for (const url of viewTileUrls(lat, lon, level, buffer)) requestTile(url);
  }
}

function tilesReady(lat, lon, zoom, buffer = 1) {
  const urls = viewTileUrls(lat, lon, zoom, buffer);
  if (!urls.length) return false;
  return urls.every((url) => TILE_CACHE.loaded.has(url));
}

function zoomWaitExpired() {
  return MAP2D.zoomWaitFrom && performance.now() - MAP2D.zoomWaitFrom > 1500;
}

function prefetchAhead(fromT) {
  const horizon = 24;
  const step = 0.5;
  const start = Number.isFinite(fromT) ? fromT : 0;
  const end = Math.min(start + horizon, MAP2D.to || start + horizon);
  const hasCam = (ensureMapDoc().map_keyframes || []).length > 0;
  for (let t = start; t <= end + 1e-6; t += step) {
    if (hasCam) {
      const view = mapViewAt(t);
      if (view) prefetchView(view.lat, view.lon, view.zoom, { buffer: 3 });
    } else {
      const pose = poseAt(t);
      if (pose) prefetchView(pose.lat, pose.lon, map.getZoom(), { neighborZooms: false, buffer: 3 });
    }
  }
}

function mapPaneShift() {
  return typeof map._getMapPanePos === "function" ? map._getMapPanePos() : L.point(0, 0);
}

function tileZoomFor(zoom) {
  if (!Number.isFinite(zoom)) return map.getZoom();
  return Math.floor(zoom + 1e-9);
}

function rebaseView(target, zoom) {
  const z = tileZoomFor(zoom);
  MAP2D.programmaticView = true;
  try {
    map.setView(target, z, { animate: false });
  } finally {
    queueMicrotask(() => { MAP2D.programmaticView = false; });
  }
  resetDrivenOverlayPanes();
  eachMapRenderer((renderer) => {
    if (renderer._container) L.DomUtil.setTransform(renderer._container, L.point(0, 0), 1);
  });
  MAP2D.zoomWaitFrom = 0;
  MAP2D.projectedShift = null;
}

function refreshTiles() {
  map.eachLayer((layer) => {
    if (layer._tiles && typeof layer._onMoveEnd === "function") layer._onMoveEnd();
  });
}

/**
 * Pan the map pane so tiles and the path move together. `_move` + reproject
 * slides the line across a still basemap; `viewreset` drops the tiles.
 */
function driveMapView(lat, lon, zoom, bearing) {
  const target = L.latLng(lat, lon);
  const z = Number.isFinite(zoom) ? zoom : map.getZoom();
  MAP2D.driven = { center: target, zoom: z, bearing };
  MAP2D.programmaticView = true;
  try {
  if (!map._loaded) {
    rebaseView(target, z);
    MAP2D.driven = null;
  } else {
    const tileZ = tileZoomFor(z);
    const shift = mapPaneShift();
    const drifted = Math.hypot(shift.x, shift.y) > 160;
    const zoomJump = tileZ !== Math.round(map.getZoom());
    const playing = MAP2D.playing && !MAP2D.paused;
    prefetchView(target.lat, target.lng, tileZ, { buffer: 3, neighborZooms: true });
    const canRebase = tilesReady(target.lat, target.lng, tileZ) || zoomWaitExpired();
    // setView fires viewreset and flashes a blank frame. During play keep the
    // current tiles and scale them; rebase only when scrubbing or the next
    // camera is a whole viewport away.
    if (!playing && (zoomJump || drifted) && canRebase) {
      rebaseView(target, tileZ);
      MAP2D.driven = { center: target, zoom: map.getZoom(), bearing };
    } else {
      if ((zoomJump || drifted) && !MAP2D.zoomWaitFrom) MAP2D.zoomWaitFrom = performance.now();
      const from = map.latLngToContainerPoint(map.getCenter());
      const to = map.latLngToContainerPoint(target);
      const offset = to.subtract(from);
      if (offset.x || offset.y) {
        const size = map.getSize();
        if (Math.abs(offset.x) < size.x && Math.abs(offset.y) < size.y) {
          map.panBy(offset, { animate: false, noMoveStart: true });
        } else {
          rebaseView(target, map.getZoom());
        }
      }
      // panBy already fires moveend. A second _onMoveEnd here reloads tiles
      // and clears the live zoom transform for a frame.
    }
  }
  if (typeof map.setBearing === "function" && bearing != null) {
    const prev = typeof map.getBearing === "function" ? map.getBearing() : 0;
    const delta = ((bearing - prev + 180) % 360 + 360) % 360 - 180;
    if (Math.abs(delta) > 0.05) map.setBearing(bearing);
  }
  } finally {
    queueMicrotask(() => { MAP2D.programmaticView = false; });
  }
}

/** Keep markers on the path after a live pan/zoom that has not been committed. */
function placeOnDrivenMap(marker, lat, lon) {
  if (!marker) return;
  marker.setLatLng([lat, lon]);
}

function eachMapRenderer(fn) {
  const seen = new Set();
  if (map._renderer) seen.add(map._renderer);
  map.eachLayer((layer) => {
    if (layer._renderer) seen.add(layer._renderer);
    if (typeof layer.eachLayer === "function") {
      layer.eachLayer((child) => { if (child._renderer) seen.add(child._renderer); });
    }
  });
  seen.forEach(fn);
}

function drivenOverlayPanes() {
  return ["overlayPane", "markerPane", "shadowPane", "playhead"]
    .map((name) => map.getPane(name))
    .filter(Boolean);
}

function resetDrivenOverlayPanes() {
  drivenOverlayPanes().forEach((pane) => L.DomUtil.setTransform(pane, L.point(0, 0), 1));
}

/** Same CSS transform GridLayer applies to a tile zoom level. */
function applyTileZoomTransform(el, center, zoom) {
  const origin = map.getPixelOrigin();
  const scale = map.getZoomScale(zoom, map.getZoom());
  const translate = origin.multiplyBy(scale)
    .subtract(map._getNewPixelOrigin(center, zoom))
    .round();
  L.DomUtil.setTransform(el, translate, scale);
}

function drivenView() {
  const driven = MAP2D.driven;
  if (!driven) return null;
  const live = Math.abs(driven.zoom - map.getZoom()) > 1e-4;
  return {
    live,
    center: live ? driven.center : map.getCenter(),
    zoom: live ? driven.zoom : map.getZoom(),
  };
}

/** CSS scale only — no SVG rebuild, so it is safe after Leaflet moveend. */
function applyDrivenTransforms() {
  const view = drivenView();
  if (!view || MAP2D.applyingScale) return;
  MAP2D.applyingScale = true;
  try {
    map.eachLayer((layer) => {
      if (typeof layer._setZoomTransforms === "function") {
        layer._setZoomTransforms(view.center, view.zoom);
      }
    });
    if (view.live) {
      drivenOverlayPanes().forEach((pane) => applyTileZoomTransform(pane, view.center, view.zoom));
    } else {
      resetDrivenOverlayPanes();
    }
  } finally {
    MAP2D.applyingScale = false;
  }
}

/** Scale tiles and the path with the same live zoom as the camera. */
function applyDrivenScale() {
  const view = drivenView();
  if (!view) return;
  const shift = mapPaneShift();
  const last = MAP2D.projectedShift;
  const moved = !last || Math.hypot(shift.x - last.x, shift.y - last.y) > 32;
  if (moved) {
    eachMapRenderer((renderer) => {
      if (typeof renderer._update === "function") renderer._update();
    });
    MAP2D.projectedShift = shift;
  }
  applyDrivenTransforms();
}

/** Drop a leftover live CSS scale so Leaflet scroll-zoom can move the view. */
function releaseIdleDrivenView() {
  if (MAP2D.playing) return;
  const driven = MAP2D.driven;
  if (driven && Math.abs(driven.zoom - map.getZoom()) > 1e-4) {
    rebaseView(driven.center, driven.zoom);
  }
  MAP2D.driven = null;
  MAP2D.projectedShift = null;
  resetDrivenOverlayPanes();
}

function userOwnsMapView() {
  if (!map2dMode() || MAP2D.playing || MAP2D.programmaticView || MAP2D.applyingScale) return;
  if (!MAP2D.driven) return;
  MAP2D.driven = null;
  MAP2D.projectedShift = null;
  resetDrivenOverlayPanes();
}

function syncDrivenZoom() {
  applyDrivenScale();
}

function ownMapCamera() {
  if ($("opt-follow")) $("opt-follow").checked = false;
  if ($("opt-lock-map")) $("opt-lock-map").checked = false;
  if (typeof saveMapOverlay === "function") saveMapOverlay();
}

function markerVisible(marker, t) {
  if (marker.time_offset == null || marker.time_offset === "") return true;
  return t >= marker.time_offset;
}

function escapeHtml(text) {
  return String(text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function labelStyleOf(marker) {
  return marker.label || emptyLabelStyle();
}

function labelVisible(marker) {
  const text = (marker.text || "").trim();
  if (!text) return false;
  return (labelStyleOf(marker).display || "RIGHT") !== "HIDDEN";
}

function markerLabelHtml(marker) {
  if (!labelVisible(marker)) return "";
  const style = labelStyleOf(marker);
  const side = style.display || "RIGHT";
  const size = Number(style.size_px) || 12;
  const weight = style.weight === "BOLD" ? "700" : "400";
  const color = style.color || "#dfe4ec";
  const text = escapeHtml((marker.text || "").trim()).replace(/\n/g, "<br>");
  const gapRaw = Number(style.gap_px);
  const gap = Math.min(48, Math.max(0, Number.isFinite(gapRaw) ? gapRaw : 6));
  return `<div class="map-mark-label map-mark-label-${side}" style="color:${color};font-size:${size}px;font-weight:${weight};--mark-gap:${gap}px">${text}</div>`;
}

function markerIcon(marker, selected) {
  const glyph = MARKER_ICONS[marker.icon] || MARKER_ICONS.PIN;
  const box = marker.outline ? " boxed" : "";
  return L.divIcon({
    className: "map-mark-icon",
    html: `<div class="map-mark-wrap"><div class="map-mark${selected ? " selected" : ""}${box}">${glyph}</div>${markerLabelHtml(marker)}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 24],
    tooltipAnchor: [0, -20],
  });
}

function markerPopup(marker) {
  const text = escapeHtml(marker.text || "");
  const picture = marker.picture
    ? `<img class="map-mark-pic" alt="" src="${marker.picture}">` : "";
  return `${picture}<div class="map-mark-text">${text || "Marker"}</div>`;
}

function renderMapMarkers() {
  if (!layers.markers) {
    layers.markers = L.layerGroup().addTo(map);
  }
  layers.markers.clearLayers();
  if (!map2dMode()) return;
  const t = parseFloat($("scrub").value) || 0;
  const selected = state.track === "marks" ? state.selected : null;
  ensureMapDoc().markers.forEach((marker, index) => {
    if (!markerVisible(marker, MAP2D.playing ? MAP2D.t : t)) return;
    const pin = L.marker([marker.lat, marker.lon], {
      icon: markerIcon(marker, index === selected),
      draggable: true,
    });
    pin.bindPopup(markerPopup(marker), { maxWidth: 220 });
    pin.on("click", () => { state.track = "marks"; select(index); });
    pin.on("dragend", (event) => {
      const at = event.target.getLatLng();
      marker.lat = at.lat;
      marker.lon = at.lng;
      state.track = "marks";
      select(index);
      map2dTouched();
    });
    layers.markers.addLayer(pin);
  });
}

function describeMapCamera(keyframe) {
  return `z${Number(keyframe.zoom).toFixed(1)} · ${Math.round(keyframe.rotation_deg || 0)}°`;
}

function describeMarker(marker) {
  const label = (marker.text || "").trim() || marker.icon || "pin";
  const hidden = labelStyleOf(marker).display === "HIDDEN" ? " · hidden" : "";
  return (marker.picture ? `${label} · photo` : label) + hidden;
}

function appendMapCameraKeyframe() {
  const doc = ensureMapDoc();
  const view = currentMapView();
  const list = doc.map_keyframes;
  const at = state.selected === null ? list.length - 1 : state.selected;
  const previous = list[at];
  const next = list[at + 1];
  const time = !previous ? (parseFloat($("scrub").value) || 0)
    : next ? (previous.time_offset + next.time_offset) / 2
    : previous.time_offset + 5;
  const key = {
    time_offset: Math.max(0, time),
    lat: view.lat,
    lon: view.lon,
    zoom: view.zoom,
    rotation_deg: view.rotation_deg || 0,
  };
  list.splice(at + 1, 0, key);
  list.sort((a, b) => a.time_offset - b.time_offset);
  state.selected = list.indexOf(key);
  ownMapCamera();
  map2dTouched();
}

function captureMapCamera() {
  const doc = ensureMapDoc();
  const view = currentMapView();
  const time = parseFloat($("scrub").value) || 0;
  const existing = doc.map_keyframes.find((k) => Math.abs(k.time_offset - time) < 1e-6);
  if (existing) {
    Object.assign(existing, view);
  } else {
    doc.map_keyframes.push({ time_offset: time, ...view });
    doc.map_keyframes.sort((a, b) => a.time_offset - b.time_offset);
  }
  state.track = "map";
  state.selected = doc.map_keyframes.findIndex((k) => Math.abs(k.time_offset - time) < 1e-6);
  ownMapCamera();
  map2dTouched();
  renderKeyframeList();
  renderInspector();
}

function newMarkerId() {
  return `m${Date.now().toString(36)}${Math.floor(Math.random() * 36).toString(36)}`;
}

function appendMapMarker(lat, lon) {
  const doc = ensureMapDoc();
  doc.markers.push({
    id: newMarkerId(),
    lat, lon,
    text: "",
    icon: "PIN",
    outline: false,
    label: emptyLabelStyle(),
    picture: null,
    time_offset: null,
  });
  state.track = "marks";
  state.selected = doc.markers.length - 1;
  MAP2D.placing = false;
  $("btn-draw")?.classList.remove("toggled");
  map2dTouched();
  renderKeyframeList();
  renderInspector();
  renderMap();
}

function renderMapCameraInspector(host, keyframe) {
  const title = host.querySelector("h3");
  if (title) title.textContent = `Map camera ${state.selected + 1} of ${ensureMapDoc().map_keyframes.length}`;
  fieldLatLon(host, keyframe, {
    onChange: () => {
      keyframe.lat = Math.min(90, Math.max(-90, keyframe.lat));
      keyframe.lon = Math.min(180, Math.max(-180, keyframe.lon));
      map2dTouched();
      applyMapView(keyframe, true);
    },
  });
  host.appendChild(field("Zoom", numberInput(keyframe.zoom, (v) => {
    keyframe.zoom = Math.min(22, Math.max(2, v)); map2dTouched(); applyMapView(keyframe, true);
  }, 0.1)));
  host.appendChild(field("Rotation (°)", numberInput(keyframe.rotation_deg, (v) => {
    keyframe.rotation_deg = v; map2dTouched(); applyMapView(keyframe, true);
  }, 1)));
  const go = document.createElement("button");
  go.type = "button";
  go.textContent = "Show on map";
  go.onclick = () => applyMapView(keyframe, true);
  host.appendChild(field("View", go));
  const cap = document.createElement("button");
  cap.type = "button";
  cap.textContent = "Capture current view";
  cap.onclick = () => {
    Object.assign(keyframe, currentMapView());
    map2dTouched();
    renderInspector();
  };
  host.appendChild(field("From map", cap));
  const hint = document.createElement("p");
  hint.className = "hint";
  hint.textContent = "These keys drive the map during 2D Play. Straight and "
    + "smooth path legs share the line style above. Rotation needs the rotate plugin.";
  host.appendChild(hint);
}

function readPicture(file, done) {
  if (!file) { done(null); return; }
  if (file.size > 1_500_000) {
    alert("Pictures over 1.5 MB make the overlay file heavy. Choose a smaller image.");
    done(null);
    return;
  }
  const reader = new FileReader();
  reader.onload = () => done(reader.result);
  reader.readAsDataURL(file);
}

function renderMarkerInspector(host, marker) {
  const title = host.querySelector("h3");
  if (title) title.textContent = `Marker ${state.selected + 1} of ${ensureMapDoc().markers.length}`;
  const text = document.createElement("textarea");
  text.rows = 3;
  text.value = marker.text || "";
  text.onchange = () => { marker.text = text.value; map2dTouched(); renderMap(); };
  host.appendChild(field("Text", text));
  const style = labelStyleOf(marker);
  marker.label = style;
  host.appendChild(field("Label", selectInput(
    [["HIDDEN", "Do not display"], ["RIGHT", "Right of pin"], ["LEFT", "Left of pin"],
     ["ABOVE", "Above pin"], ["BELOW", "Below pin"]],
    style.display || "RIGHT", (v) => { style.display = v; map2dTouched(); renderMap(); })));
  const color = document.createElement("input");
  color.type = "color";
  color.value = style.color || "#dfe4ec";
  color.oninput = () => { style.color = color.value; map2dTouched(); renderMap(); };
  host.appendChild(field("Label colour", color));
  host.appendChild(field("Label size", numberInput(style.size_px ?? 12, (v) => {
    style.size_px = Math.min(32, Math.max(8, v)); map2dTouched(); renderMap();
  }, 1)));
  host.appendChild(field("Label weight", selectInput(
    [["NORMAL", "Regular"], ["BOLD", "Bold"]],
    style.weight || "NORMAL", (v) => { style.weight = v; map2dTouched(); renderMap(); })));
  host.appendChild(field("Label gap (px)", numberInput(style.gap_px ?? 6, (v) => {
    style.gap_px = Math.min(48, Math.max(0, v)); map2dTouched(); renderMap();
  }, 1)));
  host.appendChild(field("Icon", selectInput(
    [["PIN", "Pin"], ["NOTE", "Note"], ["FLAG", "Flag"], ["AIRPORT", "Airport"]],
    marker.icon || "PIN", (v) => { marker.icon = v; map2dTouched(); renderMap(); })));
  const outline = document.createElement("input");
  outline.type = "checkbox";
  outline.checked = Boolean(marker.outline);
  outline.onchange = () => { marker.outline = outline.checked; map2dTouched(); renderMap(); };
  host.appendChild(field("Outline", outline));
  fieldLatLon(host, marker, {
    onChange: () => {
      marker.lat = Math.min(90, Math.max(-90, marker.lat));
      marker.lon = Math.min(180, Math.max(-180, marker.lon));
      map2dTouched();
      renderMap();
    },
  });
  const appear = document.createElement("input");
  appear.type = "number";
  appear.step = 0.1;
  appear.min = 0;
  appear.placeholder = "always";
  appear.value = marker.time_offset ?? "";
  appear.onchange = () => {
    marker.time_offset = appear.value === "" ? null : Math.max(0, parseFloat(appear.value));
    map2dTouched();
  };
  host.appendChild(field("From (s)", appear));
  const pick = document.createElement("input");
  pick.type = "file";
  pick.accept = "image/png,image/jpeg,image/webp";
  pick.onchange = () => readPicture(pick.files[0], (data) => {
    marker.picture = data;
    map2dTouched();
    renderInspector();
    renderMap();
  });
  host.appendChild(field("Picture", pick));
  if (marker.picture) {
    const clear = document.createElement("button");
    clear.type = "button";
    clear.textContent = "Remove picture";
    clear.onclick = () => { marker.picture = null; map2dTouched(); renderInspector(); renderMap(); };
    host.appendChild(field("", clear));
  }
  const hint = document.createElement("p");
  hint.className = "hint";
  hint.textContent = "Drag the pin on the map. From (s) hides it until that time during 2D Play.";
  host.appendChild(hint);
}

function renderLineStyle() {
  const host = $("map2d-style");
  if (!host) return;
  host.hidden = false;
  const line = ensureMapDoc().line;
  const color = $("map2d-color");
  const width = $("map2d-width");
  const opacity = $("map2d-opacity");
  const dash = $("map2d-dash");
  if (document.activeElement !== color) color.value = line.color || "#4ea1ff";
  if (document.activeElement !== width) width.value = line.width_px ?? 8;
  if (document.activeElement !== opacity) opacity.value = Math.round((line.opacity ?? 0.95) * 100);
  if (document.activeElement !== dash) dash.value = line.dash || "SOLID";
}

function applyLineStyleInputs() {
  const line = ensureMapDoc().line;
  line.color = $("map2d-color").value || "#4ea1ff";
  line.width_px = Math.min(20, Math.max(0.5, parseFloat($("map2d-width").value) || 8));
  line.opacity = Math.min(1, Math.max(0.05, (parseFloat($("map2d-opacity").value) || 95) / 100));
  line.dash = $("map2d-dash").value || "SOLID";
  state.dirty = true;
  paintFlightLine();
}

function setUiMode(mode, opts = {}) {
  const next = mode === "2d" || mode === "3d" ? mode : "sim";
  const prev = state.uiMode || "sim";
  state.uiMode = next;
  document.body.classList.toggle("mode-2d", next === "2d");
  document.body.classList.toggle("mode-sim", next === "sim");
  document.body.classList.toggle("mode-3d", next === "3d");
  $("mode-2d")?.classList.toggle("active", next === "2d");
  $("mode-sim")?.classList.toggle("active", next === "sim");
  $("mode-3d")?.classList.toggle("active", next === "3d");
  try { localStorage.setItem("fs-ui-mode", next); } catch (_) { /* ignore */ }

  if (!opts.init && prev !== next) {
    if (next === "2d") {
      state.previewing = false;
      previewStartPending = false;
      if (typeof renderPreviewButton === "function") renderPreviewButton();
      if (prev === "sim") api("POST", "/api/simulation/stop").catch(() => {});
      if (typeof setLiveOpen === "function") setLiveOpen(false);
      if (state.track === "camera" || state.track === "systems" || state.track === "controls") {
        state.track = "flight";
        state.selected = frames().length ? 0 : null;
      }
      if (ensureMapDoc().map_keyframes.length) ownMapCamera();
      else $("opt-follow").checked = true;
      $("opt-lock-map").checked = false;
    } else if (next === "3d") {
      state.previewing = false;
      previewStartPending = false;
      if (typeof renderPreviewButton === "function") renderPreviewButton();
      if (prev === "sim") api("POST", "/api/simulation/stop").catch(() => {});
      if (typeof setLiveOpen === "function") setLiveOpen(false);
      if (state.track === "map" || state.track === "marks" || state.track === "systems" || state.track === "controls") {
        state.track = "flight";
        state.selected = frames().length ? 0 : null;
      }
    } else {
      stopMapPlay();
      if (state.track === "map" || state.track === "marks") {
        state.track = "flight";
        state.selected = frames().length ? 0 : null;
      }
    }
  }

  map.options.zoomSnap = next === "2d" ? 0 : 1;
  document.querySelectorAll(".tab").forEach(
    (tab) => tab.classList.toggle("active", tab.dataset.track === state.track));
  renderLineStyle();
  renderKeyframeList();
  renderInspector();
  renderMap();
  renderPlayable();
  if (prev === "3d" && next !== "3d" && typeof leaveMap3d === "function") leaveMap3d();
  if (next === "2d") {
    if (prev === "3d") {
      MAP2D.driven = null;
      MAP2D.projectedShift = null;
      resetDrivenOverlayPanes();
    }
    const t = parseFloat($("scrub")?.value) || 0;
    showPlayhead(t);
    if (!MAP2D.playing) releaseIdleDrivenView();
    requestAnimationFrame(() => {
      try { map.invalidateSize({ animate: false, pan: false }); } catch (_) { /* ignore */ }
      if (map.scrollWheelZoom && !map.scrollWheelZoom.enabled()) {
        map.scrollWheelZoom.enable();
      }
    });
  }
  if (next === "3d" && typeof enterMap3d === "function") enterMap3d();
}

function setMap2dMode(on) {
  setUiMode(on ? "2d" : "sim");
}

function syncPlayheadMarkers(t) {
  if (!MAP2D.playing) {
    renderMapMarkers();
    return;
  }
  const wanted = ensureMapDoc().markers.filter((marker) => markerVisible(marker, t)).length;
  const have = layers.markers ? layers.markers.getLayers().length : 0;
  if (wanted !== have) renderMapMarkers();
}

function onMap2dPlayhead(t) {
  if (!map2dMode()) return;
  syncPlayheadMarkers(t);
  const view = mapViewAt(t);
  if (view) {
    applyMapView(view, true);
    return;
  }
  if (mapFollowsAircraft()) {
    const pose = poseAt(t);
    if (pose) driveMapView(pose.lat, pose.lon, map.getZoom(), null);
  }
}

function onMap2dSelect(index) {
  if (!map2dMode() || state.track !== "map") return;
  const key = ensureMapDoc().map_keyframes[index];
  if (!key) return;
  if (Number.isFinite(key.time_offset)) {
    $("scrub").value = key.time_offset;
    if (typeof MAP2D !== "undefined") MAP2D.t = key.time_offset;
    showPlayhead(key.time_offset);
    return;
  }
  applyMapView(key, true);
}

function stopMapPlay() {
  if (MAP2D.raf) cancelAnimationFrame(MAP2D.raf);
  MAP2D.raf = 0;
  MAP2D.playing = false;
  MAP2D.paused = false;
  state.playback = { ...state.playback, state: "IDLE", preview: false, recording: false };
  renderPauseButton();
  $("playback-state").textContent = "IDLE";
  if ($("playback-fps")) $("playback-fps").textContent = "";
}

function mapPlayFps() {
  const fps = parseFloat($("map2d-fps")?.value);
  return Number.isFinite(fps) && fps > 0 ? fps : 0;
}

function tickMapPlay(now) {
  if (!MAP2D.playing || MAP2D.paused) return;
  const fps = MAP2D.fps;
  if (fps) {
    const due = Math.floor((now - MAP2D.originMs) / (1000 / fps));
    if (due <= MAP2D.frame) {
      applyDrivenTransforms();
      MAP2D.raf = requestAnimationFrame(tickMapPlay);
      return;
    }
    MAP2D.frame += 1;
    MAP2D.t = MAP2D.startT + MAP2D.frame * (1 / fps) * MAP2D.speed;
  } else {
    const dt = (now - MAP2D.lastMs) / 1000 * MAP2D.speed;
    MAP2D.lastMs = now;
    MAP2D.t += dt;
  }
  if (MAP2D.t >= MAP2D.to) {
    if ($("opt-loop").checked) {
      MAP2D.t = MAP2D.from;
    } else {
      MAP2D.t = MAP2D.to;
      showPlayhead(MAP2D.t);
      stopMapPlay();
      $("playback-state").textContent = "FINISHED";
      return;
    }
  }
  $("scrub").value = MAP2D.t;
  showPlayhead(MAP2D.t);
  if (!MAP2D.lastPrefetchT || MAP2D.t - MAP2D.lastPrefetchT >= 2) {
    MAP2D.lastPrefetchT = MAP2D.t;
    prefetchAhead(MAP2D.t);
  }
  state.playback = {
    ...state.playback, state: "PLAYING", elapsed: MAP2D.t,
    duration: state.preview?.duration || MAP2D.to, preview: false, mode: "MAP2D",
  };
  $("playback-state").textContent = clientPlayLabel(fps);
  $("playback-fps").textContent = fps ? ` · ${fps} fps` : "";
  MAP2D.raf = requestAnimationFrame(tickMapPlay);
}

function startMapPlay(paused) {
  const segment = playSegment();
  const duration = state.preview?.duration || lastTime() || 1;
  MAP2D.from = segment.from_s ?? 0;
  MAP2D.to = segment.to_s ?? duration;
  MAP2D.speed = segment.speed || 1;
  MAP2D.fps = mapPlayFps();
  MAP2D.t = Math.max(MAP2D.from, parseFloat($("scrub").value) || MAP2D.from);
  if (MAP2D.t >= MAP2D.to) MAP2D.t = MAP2D.from;
  MAP2D.playing = true;
  MAP2D.paused = Boolean(paused);
  MAP2D.lastMs = performance.now();
  MAP2D.originMs = MAP2D.lastMs;
  MAP2D.startT = MAP2D.t;
  MAP2D.frame = 0;
  state.playback = {
    state: paused ? "PAUSED" : "PLAYING", elapsed: MAP2D.t, duration,
    preview: false, mode: "MAP2D", recording: false,
  };
  renderPauseButton();
  $("playback-state").textContent = paused ? "PAUSED" : clientPlayLabel(MAP2D.fps);
  MAP2D.lastPrefetchT = MAP2D.t;
  prefetchAhead(MAP2D.t);
  showPlayhead(MAP2D.t);
  if (!paused) MAP2D.raf = requestAnimationFrame(tickMapPlay);
}

function pauseMapPlay() {
  if (!MAP2D.playing) {
    startMapPlay(true);
    return;
  }
  if (MAP2D.paused) {
    MAP2D.paused = false;
    MAP2D.lastMs = performance.now();
    MAP2D.originMs = MAP2D.lastMs - MAP2D.frame * (MAP2D.fps ? 1000 / MAP2D.fps : 0);
    state.playback.state = "PLAYING";
    renderPauseButton();
    $("playback-state").textContent = clientPlayLabel(MAP2D.fps);
    MAP2D.raf = requestAnimationFrame(tickMapPlay);
    return;
  }
  MAP2D.paused = true;
  if (MAP2D.raf) cancelAnimationFrame(MAP2D.raf);
  MAP2D.raf = 0;
  state.playback.state = "PAUSED";
  renderPauseButton();
  $("playback-state").textContent = "PAUSED";
}

async function loadMapDocument(pathId) {
  try {
    state.mapDoc = await api("GET", `/api/paths/${pathId}/map`);
  } catch (_) {
    state.mapDoc = emptyMapDoc(pathId);
  }
  ensureMapDoc().path_id = pathId;
  renderLineStyle();
  renderMap();
}

async function saveMapDocument() {
  if (!state.mapDoc) return;
  const pathId = state.doc?.meta?.path_id
    || state.mapDoc.path_id
    || document.getElementById("path-select")?.value;
  if (!pathId) return;
  state.mapDoc.path_id = pathId;
  await api("PUT", `/api/paths/${pathId}/map`, state.mapDoc);
}

function wireMap2d() {
  if (MAP2D.wired) return;
  MAP2D.wired = true;
  $("mode-2d").onclick = () => setUiMode("2d");
  $("mode-sim").onclick = () => setUiMode("sim");
  ["map2d-color", "map2d-width", "map2d-opacity", "map2d-dash"].forEach((id) => {
    $(id).onchange = applyLineStyleInputs;
    $(id).oninput = applyLineStyleInputs;
  });
  $("map2d-capture").onclick = captureMapCamera;
  const fps = $("map2d-fps");
  if (fps) {
    try {
      const saved = localStorage.getItem("flightstudio.map2dFps");
      if (saved != null && [...fps.options].some((opt) => opt.value === saved)) {
        fps.value = saved;
      }
    } catch (_) { /* ignore */ }
    fps.onchange = () => {
      try { localStorage.setItem("flightstudio.map2dFps", fps.value); } catch (_) { /* ignore */ }
    };
  }

  map.on("moveend", () => {
    if (MAP2D.driven) applyDrivenTransforms();
  });
  map.on("zoomstart", userOwnsMapView);
  map.getContainer().addEventListener("wheel", userOwnsMapView, { capture: true, passive: true });
  map.on("click", (event) => {
    if (!state.doc || !map2dMode()) return;
    if (state.track === "marks" && (state.drawing || MAP2D.placing)) {
      appendMapMarker(event.latlng.lat, event.latlng.lng);
    }
  });

  let saved = "2d";
  try { saved = localStorage.getItem("fs-ui-mode") || "2d"; } catch (_) { /* ignore */ }
  setUiMode(saved, { init: true });
  renderLineStyle();
}

window.MAP2D = MAP2D;
window.ensureMapDoc = ensureMapDoc;
window.map2dMode = map2dMode;
window.flightLineStyle = flightLineStyle;
window.renderMapMarkers = renderMapMarkers;
window.describeMapCamera = describeMapCamera;
window.describeMarker = describeMarker;
window.appendMapCameraKeyframe = appendMapCameraKeyframe;
window.appendMapMarker = appendMapMarker;
window.renderMapCameraInspector = renderMapCameraInspector;
window.renderMarkerInspector = renderMarkerInspector;
window.loadMapDocument = loadMapDocument;
window.saveMapDocument = saveMapDocument;
window.onMap2dPlayhead = onMap2dPlayhead;
window.onMap2dSelect = onMap2dSelect;
window.applyMapView = applyMapView;
window.driveMapView = driveMapView;
window.placeOnDrivenMap = placeOnDrivenMap;
window.applyDrivenScale = applyDrivenScale;
window.syncDrivenZoom = syncDrivenZoom;
window.stopMapPlay = stopMapPlay;
window.captureMapCamera = captureMapCamera;
window.setUiMode = setUiMode;
window.setMap2dMode = setMap2dMode;
window.wireMap2d = wireMap2d;
wireMap2d();
