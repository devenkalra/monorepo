"use strict";

// Google Photorealistic 3D (gmp-map-3d). The Maps bootstrap, maps3d library,
// and the custom element are created once per page and kept in the DOM when
// the operator leaves 3D mode. Recreating the element reloads tiles and can
// mount a second WebGL context.

const FT_TO_M = 0.3048;
const CHASE_RANGE_M = 220;
const CHASE_TILT_DEG = 72;

const MAP3D = {
  bootstrap: null,
  loading: null,
  map: null,
  line: null,
  status: "idle",
  googleLayer: "HYBRID",
  showPath: true,
  showMini: true,
  mini: null,
};

const MAP3D_LAYERS = new Set(["SATELLITE", "HYBRID"]);
const MAP3D_LAYER_KEY = "flightstudio.map3dLayer";
const MAP3D_PATH_KEY = "flightstudio.map3dPath";
const MAP3D_MINI_KEY = "flightstudio.map3dMini";

function map3dMode() {
  return state.uiMode === "3d";
}

function setMap3dStatus(text, kind) {
  const pill = $("map3d-status");
  if (!pill) return;
  pill.textContent = text;
  pill.className = `pill map3d-only${kind ? ` ${kind}` : ""}`;
  const banner = $("map3d-banner");
  if (banner) {
    banner.hidden = !kind || kind === "ok";
    banner.textContent = kind && kind !== "ok" ? text : "";
  }
}

function mapsApiKey() {
  return (window.FS_CAPABILITIES && window.FS_CAPABILITIES.maps_api_key) || "";
}

function installMapsBootstrap(key) {
  if (window.google?.maps?.importLibrary) return Promise.resolve();
  if (MAP3D.bootstrap) return MAP3D.bootstrap;
  MAP3D.bootstrap = new Promise((resolve, reject) => {
    const googleNs = (window.google = window.google || {});
    const maps = (googleNs.maps = googleNs.maps || {});
    if (typeof maps.importLibrary === "function") {
      resolve();
      return;
    }
    const pending = new Set();
    let ready;
    const start = () => ready || (ready = new Promise(async (ok, fail) => {
      const script = document.createElement("script");
      const params = new URLSearchParams({
        key,
        v: "beta",
        callback: "google.maps.__ib__",
      });
      maps.__ib__ = ok;
      script.src = `https://maps.googleapis.com/maps/api/js?${params}`;
      script.async = true;
      script.onerror = () => fail(new Error("Google Maps JavaScript API could not load."));
      document.head.append(script);
    }));
    maps.importLibrary = (name, ...rest) => {
      pending.add(name);
      return start().then(() => maps.importLibrary(name, ...rest));
    };
    start().then(resolve, reject);
  }).catch((error) => {
    MAP3D.bootstrap = null;
    throw error;
  });
  return MAP3D.bootstrap;
}

function rangeMeters(aLat, aLon, aAlt, bLat, bLon, bAlt) {
  const R = 6371000;
  const p1 = aLat * Math.PI / 180;
  const p2 = bLat * Math.PI / 180;
  const dLat = p2 - p1;
  const dLon = (bLon - aLon) * Math.PI / 180;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLon / 2) ** 2;
  const ground = 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
  return Math.hypot(ground, (bAlt || 0) - (aAlt || 0));
}

function clamp(value, lo, hi) {
  return Math.min(hi, Math.max(lo, value));
}

function restoreMap3dOverlayPrefs() {
  try {
    const layer = localStorage.getItem(MAP3D_LAYER_KEY);
    if (MAP3D_LAYERS.has(layer)) MAP3D.googleLayer = layer;
    const path = localStorage.getItem(MAP3D_PATH_KEY);
    if (path === "0") MAP3D.showPath = false;
    if (path === "1") MAP3D.showPath = true;
    const mini = localStorage.getItem(MAP3D_MINI_KEY);
    if (mini === "0") MAP3D.showMini = false;
    if (mini === "1") MAP3D.showMini = true;
  } catch (_) { /* ignore */ }
  const select = $("map3d-google-layer");
  if (select) select.value = MAP3D.googleLayer;
  const pathBox = $("map3d-path");
  if (pathBox) pathBox.checked = MAP3D.showPath;
  const miniBox = $("map3d-mini-toggle");
  if (miniBox) miniBox.checked = MAP3D.showMini;
}

function googleLayerValue() {
  const maps3d = MAP3D.libraries;
  const name = MAP3D_LAYERS.has(MAP3D.googleLayer) ? MAP3D.googleLayer : "HYBRID";
  return maps3d?.MapMode?.[name] || name;
}

function highQualityMode() {
  const maps3d = MAP3D.libraries;
  return maps3d?.QualityMode?.FIDELITY || "FIDELITY";
}

function applyMap3dQuality(map) {
  const target = map || MAP3D.map;
  if (!target) return;
  const quality = highQualityMode();
  try { target.qualityMode = quality; } catch (_) { /* ignore */ }
  try { target.renderingQuality = "high"; } catch (_) { /* ignore */ }
  try {
    if (target.maxMemoryMegabytes == null || target.maxMemoryMegabytes < 2048) {
      target.maxMemoryMegabytes = 2048;
    }
  } catch (_) { /* ignore */ }
}

function applyMap3dOverlays() {
  if (MAP3D.map) {
    try { MAP3D.map.mode = googleLayerValue(); } catch (_) { /* ignore */ }
  }
  if (!MAP3D.line) return;
  try {
    MAP3D.line.strokeWidth = MAP3D.showPath ? 5 : 0;
    MAP3D.line.strokeColor = MAP3D.showPath ? "#4ea1ff" : "rgba(0,0,0,0)";
  } catch (_) { /* ignore */ }
}

function cameraAt(t) {
  return typeof lerpByTime === "function"
    ? lerpByTime(state.preview?.camera_track || [], t)
    : null;
}

function applyMap3dCamera(t) {
  const map = MAP3D.map;
  if (!map) return;
  const pose = typeof poseAt === "function" ? poseAt(t) : null;
  if (!pose) return;
  const lookAlt = (pose.alt_ft || 0) * FT_TO_M;
  const look = { lat: pose.lat, lng: pose.lon, altitude: lookAlt };
  const cam = cameraAt(t);
  try { map.stopCameraAnimation?.(); } catch (_) { /* not ready */ }
  if (cam && Number.isFinite(cam.lat) && Number.isFinite(cam.lon)) {
    const camAlt = (cam.alt_ft || 0) * FT_TO_M;
    const heading = Number.isFinite(cam.heading) ? cam.heading : (pose.heading || 0);
    const pitch = Number.isFinite(cam.pitch) ? cam.pitch : -18;
    const target = {
      lat: Number.isFinite(cam.look_lat) ? cam.look_lat : look.lat,
      lng: Number.isFinite(cam.look_lon) ? cam.look_lon : look.lng,
      altitude: Number.isFinite(cam.look_alt_ft) ? cam.look_alt_ft * FT_TO_M : look.altitude,
    };
    map.center = target;
    map.heading = heading;
    map.tilt = clamp(90 + pitch, 0, 90);
    map.range = Math.max(15, rangeMeters(
      cam.lat, cam.lon, camAlt, target.lat, target.lng, target.altitude));
    map.fov = clamp(Number.isFinite(cam.fov_deg) ? cam.fov_deg : 60, 5, 80);
    map.cameraPosition = { lat: cam.lat, lng: cam.lon, altitude: Math.max(1, camAlt) };
    return;
  }
  // Drop any previous cinematic cameraPosition so it cannot keep the view
  // glued to the key's world point while center/range fall back to chase.
  try { map.cameraPosition = null; } catch (_) { /* optional on older builds */ }
  map.center = look;
  map.heading = pose.heading || 0;
  map.tilt = CHASE_TILT_DEG;
  map.range = CHASE_RANGE_M;
}

function paintMap3dPath() {
  if (!MAP3D.map || !MAP3D.libraries) return;
  const samples = state.preview?.samples || [];
  if (samples.length < 2) return;
  const coordinates = samples.map((row) => ({
    lat: row.lat,
    lng: row.lon,
    altitude: (row.alt_ft || 0) * FT_TO_M,
  }));
  const { Polyline3DElement, AltitudeMode } = MAP3D.libraries;
  if (!Polyline3DElement) return;
  try {
    if (!MAP3D.line) {
      MAP3D.line = new Polyline3DElement({
        strokeColor: MAP3D.showPath ? "#4ea1ff" : "rgba(0,0,0,0)",
        strokeWidth: MAP3D.showPath ? 5 : 0,
        altitudeMode: AltitudeMode?.ABSOLUTE || "ABSOLUTE",
        coordinates,
      });
      MAP3D.map.append(MAP3D.line);
    } else {
      MAP3D.line.coordinates = coordinates;
    }
    applyMap3dOverlays();
  } catch (_) { /* polyline is optional decoration */ }
}

// The 3D camera sits on the aircraft, so there is no sense of where along the
// route it is. The minimap answers that with a plan view of the whole track.
function ensureMiniMap() {
  if (MAP3D.mini) return MAP3D.mini;
  const host = $("map3d-mini-map");
  if (!host || typeof L === "undefined") return null;
  const mini = L.map(host, {
    attributionControl: false,
    zoomControl: false,
    // leaflet-rotate adds its compass to every map it sees; the inset has no
    // room for it and nothing here rotates.
    rotate: false,
    rotateControl: false,
    dragging: false,
    scrollWheelZoom: false,
    doubleClickZoom: false,
    boxZoom: false,
    keyboard: false,
    touchZoom: false,
    trackResize: false,
  }).setView([40.7, -74.0], 11);
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 19, maxNativeZoom: 17 }).addTo(mini);
  MAP3D.miniTrack = L.polyline([], { color: "#4ea1ff", weight: 2, interactive: false }).addTo(mini);
  MAP3D.miniPlane = L.marker([0, 0], {
    interactive: false,
    icon: L.divIcon({
      className: "",
      html: `<div class="map3d-mini-plane">${PLANE_SVG}</div>`,
      iconSize: [18, 18],
      iconAnchor: [9, 9],
    }),
  }).addTo(mini);
  MAP3D.mini = mini;
  return mini;
}

function paintMiniPath() {
  if (!MAP3D.mini) return;
  const points = (state.preview?.samples || []).map((row) => [row.lat, row.lon]);
  MAP3D.miniTrack.setLatLngs(points);
  if (points.length < 2) return;
  MAP3D.mini.fitBounds(MAP3D.miniTrack.getBounds(), { padding: [14, 14], animate: false });
}

function updateMiniPlayhead(t) {
  if (!MAP3D.mini || !MAP3D.showMini) return;
  const pose = typeof poseAt === "function" ? poseAt(t) : null;
  if (!pose) return;
  MAP3D.miniPlane.setLatLng([pose.lat, pose.lon]);
  const icon = MAP3D.miniPlane.getElement()?.querySelector(".map3d-mini-plane");
  if (icon) icon.style.transform = `rotate(${pose.heading || 0}deg)`;
}

function applyMiniMap() {
  const panel = $("map3d-mini");
  if (!panel) return;
  const on = MAP3D.showMini && map3dMode();
  panel.hidden = !on;
  if (!on) return;
  const mini = ensureMiniMap();
  if (!mini) return;
  // Leaflet sizes the container when the map is made, and that happens while
  // the panel is still hidden on the first toggle or the first entry into 3D.
  mini.invalidateSize(false);
  paintMiniPath();
  updateMiniPlayhead(parseFloat($("scrub")?.value) || 0);
}

async function ensureMap3d() {
  if (MAP3D.map) return MAP3D.map;
  if (MAP3D.loading) return MAP3D.loading;
  const key = mapsApiKey();
  if (!key) {
    setMap3dStatus("Add GOOGLE_MAPS_API_KEY to the backend .env to use 3D.", "bad");
    return Promise.reject(new Error("Google Maps API key is not configured."));
  }
  const host = $("map3d-host");
  if (!host) return Promise.reject(new Error("3D map host is missing."));
  setMap3dStatus("Loading Google 3D…", "busy");
  MAP3D.loading = (async () => {
    await installMapsBootstrap(key);
    const maps3d = await google.maps.importLibrary("maps3d");
    MAP3D.libraries = maps3d;
    if (MAP3D.map) return MAP3D.map;
    const existing = host.querySelector("gmp-map-3d");
    if (existing) {
      MAP3D.map = existing;
      MAP3D.status = "ready";
      setMap3dStatus("Google 3D", "ok");
      restoreMap3dOverlayPrefs();
      applyMap3dQuality(existing);
      paintMap3dPath();
      applyMap3dOverlays();
      applyMap3dCamera(parseFloat($("scrub")?.value) || 0);
      return existing;
    }
    const Map3DElement = maps3d.Map3DElement;
    restoreMap3dOverlayPrefs();
    const map = new Map3DElement({
      mode: googleLayerValue(),
      defaultUIHidden: true,
      gestureHandling: maps3d.GestureHandling?.GREEDY || "GREEDY",
      qualityMode: highQualityMode(),
      maxMemoryMegabytes: 2048,
    });
    applyMap3dQuality(map);
    map.id = "gmp-map-3d";
    host.append(map);
    MAP3D.map = map;
    MAP3D.status = "ready";
    setMap3dStatus("Google 3D", "ok");
    paintMap3dPath();
    applyMap3dOverlays();
    const t = parseFloat($("scrub")?.value) || 0;
    applyMap3dCamera(t);
    return map;
  })().catch((error) => {
    MAP3D.loading = null;
    MAP3D.status = "error";
    setMap3dStatus(error.message || "Could not load Google 3D.", "bad");
    throw error;
  });
  return MAP3D.loading;
}

function onMap3dPlayhead(t) {
  if (!map3dMode()) return;
  applyMap3dCamera(t);
  updateMiniPlayhead(t);
}

function onMap3dPreview() {
  if (map3dMode()) applyMiniMap();
  if (!MAP3D.map) return;
  paintMap3dPath();
  if (map3dMode()) applyMap3dCamera(parseFloat($("scrub")?.value) || 0);
}

function setMap3dInteractive(on) {
  const wrap = $("map3d-wrap");
  if (wrap) {
    wrap.inert = !on;
    wrap.setAttribute("aria-hidden", on ? "false" : "true");
  }
  const map = MAP3D.map;
  if (!map) return;
  const maps3d = MAP3D.libraries;
  try {
    map.gestureHandling = on
      ? (maps3d?.GestureHandling?.GREEDY || "GREEDY")
      : (maps3d?.GestureHandling?.COOPERATIVE || "COOPERATIVE");
  } catch (_) { /* attribute is optional on older builds */ }
  if (!on) {
    try { map.stopCameraAnimation?.(); } catch (_) { /* not ready */ }
  }
}

function enterMap3d() {
  setMap3dInteractive(true);
  // Independent of the Google load: the minimap is useful even if 3D fails.
  applyMiniMap();
  setMap3dStatus(MAP3D.map ? "Google 3D" : "Loading Google 3D…", MAP3D.map ? "ok" : "busy");
  ensureMap3d()
    .then(() => {
      setMap3dInteractive(true);
      paintMap3dPath();
      applyMap3dOverlays();
      applyMap3dCamera(parseFloat($("scrub")?.value) || 0);
    })
    .catch(() => { /* status already set */ });
}

function leaveMap3d() {
  setMap3dInteractive(false);
  applyMiniMap();
}

function wireMap3d() {
  restoreMap3dOverlayPrefs();
  $("mode-3d")?.addEventListener("click", () => {
    if (typeof setUiMode === "function") setUiMode("3d");
  });
  $("map3d-google-layer")?.addEventListener("change", (event) => {
    const next = event.target.value;
    if (!MAP3D_LAYERS.has(next)) return;
    MAP3D.googleLayer = next;
    try { localStorage.setItem(MAP3D_LAYER_KEY, next); } catch (_) { /* ignore */ }
    applyMap3dOverlays();
  });
  $("map3d-path")?.addEventListener("change", (event) => {
    MAP3D.showPath = Boolean(event.target.checked);
    try { localStorage.setItem(MAP3D_PATH_KEY, MAP3D.showPath ? "1" : "0"); } catch (_) { /* ignore */ }
    applyMap3dOverlays();
  });
  $("map3d-mini-toggle")?.addEventListener("change", (event) => {
    MAP3D.showMini = Boolean(event.target.checked);
    try { localStorage.setItem(MAP3D_MINI_KEY, MAP3D.showMini ? "1" : "0"); } catch (_) { /* ignore */ }
    applyMiniMap();
  });
  if (state.uiMode === "3d") enterMap3d();
}

window.MAP3D = MAP3D;
window.map3dMode = map3dMode;
window.ensureMap3d = ensureMap3d;
window.enterMap3d = enterMap3d;
window.leaveMap3d = leaveMap3d;
window.onMap3dPlayhead = onMap3dPlayhead;
window.onMap3dPreview = onMap3dPreview;
window.wireMap3d = wireMap3d;
window.applyMap3dCamera = applyMap3dCamera;
window.applyMiniMap = applyMiniMap;
