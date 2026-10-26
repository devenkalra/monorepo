"use strict";

// The browser never splines anything. Every curve drawn here came back from
// the same solver that flies the aircraft, so the line on the map and the line
// in the simulator cannot drift apart.

const state = {
  doc: null,
  // Segment PathProgram when the open path is kind=program (stage 6).
  // Mutually exclusive with a waypoint doc for editing; preview uses either.
  program: null,
  preview: null,
  diagnostics: [],
  track: "flight",
  selected: null,
  selectedIds: [],
  playback: { state: "IDLE", elapsed: 0, duration: 0 },
  locations: [],
  dirty: false,
  previewing: false,
  drawing: false,
  // Names for the loaded aircraft's cockpit cameras; see loadCockpitViews.
  views: null,
  aircraft: null,
  mapDoc: null,
  uiMode: "2d",
};

function isProgramMode() {
  return Boolean(state.program);
}

function setProgramMode(on) {
  document.body.classList.toggle("program-mode", on);
  const banner = $("program-banner");
  if (banner) banner.hidden = !on;
  if ($("btn-earth-studio")) $("btn-earth-studio").disabled = on;
  if ($("btn-table")) $("btn-table").disabled = on;
  if (typeof showProgramAddBar === "function") showProgramAddBar(on);
  if (!on) {
    if (typeof cancelProgramBuild === "function") cancelProgramBuild();
    const popup = $("program-popup");
    if (popup) popup.hidden = true;
  }
}

const $ = (id) => document.getElementById(id);
const API_ROOT = "/api/flightstudio";

function apiUrl(url) {
  if (!url.startsWith("/api/")) return url;
  const [path, query] = url.slice(4).split("?");
  let next = API_ROOT + path;
  if (!next.endsWith("/")) next += "/";
  return query ? `${next}?${query}` : next;
}

function authHeaders() {
  const headers = { "Content-Type": "application/json" };
  const token = localStorage.getItem("access_token");
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function requireAuth() {
  const next = encodeURIComponent(location.pathname || "/app/flightstudio/");
  const login = `/login/?next=${next}`;
  try {
    const token = localStorage.getItem("access_token");
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const response = await fetch("/api/auth/user/", { credentials: "include", headers });
    if (!response.ok) {
      location.href = login;
      throw new Error("Login required");
    }
    window.FS_USER = await response.json();
    if (typeof renderAppsMenu === "function") renderAppsMenu(window.FS_USER);
  } catch (error) {
    if (error.message !== "Login required") location.href = login;
    throw error;
  }
}

async function api(method, url, body) {
  const options = { method, headers: authHeaders(), credentials: "include" };
  if (body !== undefined) options.body = JSON.stringify(body);
  const response = await fetch(apiUrl(url), options);
  if (!response.ok) {
    let detail = await response.text();
    try { detail = JSON.parse(detail).detail; } catch (_) { /* plain text */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.status === 204 ? null : response.json();
}

// ---------------------------------------------------------------- map

const mapOptions = { zoomControl: true, maxZoom: 22 };
if (typeof L.Map !== "undefined" && L.Map.prototype.setBearing) {
  mapOptions.rotate = true;
  mapOptions.bearing = 0;
}
const map = L.map("map", mapOptions).setView([40.7, -74.0], 12);

// Satellite by default: the simulator renders photogrammetry and satellite
// terrain, so this is the closest match to what the shot will actually show.
// maxNativeZoom is the highest zoom we request from the server. Beyond that
// Leaflet keeps zooming by overscaling those tiles — Esri often answers higher
// zooms with a "data not yet available" placeholder instead of real imagery.
const TILE_LAYER_OPTS = {
  keepBuffer: 8,
  updateWhenZooming: false,
};
const basemaps = {
  Satellite: L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 22, maxNativeZoom: 17, attribution: "Imagery &copy; Esri", ...TILE_LAYER_OPTS }),
  Map: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 22, maxNativeZoom: 19, attribution: "&copy; OpenStreetMap contributors",
      ...TILE_LAYER_OPTS }),
};
basemaps.Satellite.addTo(map);
L.control.layers(basemaps, null, { position: "bottomleft" }).addTo(map);

// Above Leaflet's marker pane (600), so the aircraft and camera are never
// buried under a dense run of waypoints.
// Same parent as the path (rotate pane), above waypoints. norotatePane does
// not receive the live 2D zoom scale, which slides the aircraft off the line.
map.createPane("playhead",
  (map.getPane("overlayPane") && map.getPane("overlayPane").parentElement)
  || map.getPane("markerPane"));
map.getPane("playhead").style.zIndex = 650;
map.getPane("playhead").style.pointerEvents = "none";

const PLANE_SVG = `<svg viewBox="-16 -16 32 32" width="34" height="34">
  <path d="M0,-14 L2.2,-5 L13,1.5 L13,4 L2.2,1 L1.6,9 L5,12 L5,14 L0,12.6 L-5,14 L-5,12 L-1.6,9
           L-2.2,1 L-13,4 L-13,1.5 L-2.2,-5 Z" fill="#ffd84a" stroke="#0b1017" stroke-width="1.6"
        stroke-linejoin="round"/></svg>`;

const layers = {
  // A transparent fat line under the visible track: a 3 px stroke is far too
  // thin to click reliably, and the visible weight should stay thin.
  flightHit: L.polyline([], { color: "#000", weight: 18, opacity: 0 }).addTo(map),
  // One polyline per authored leg so Straight and Smooth can differ in colour.
  flightTrack: L.layerGroup().addTo(map),
  cameraTrack: L.polyline([], { color: "#ffa23e", weight: 2, dashArray: "4 4" }).addTo(map),
  sightLine: L.polyline([], { color: "#ffa23e", weight: 1, opacity: 0.5 }).addTo(map),
  waypoints: L.layerGroup().addTo(map),
  cameras: L.layerGroup().addTo(map),
  aircraft: L.marker([0, 0], {
    pane: "playhead", interactive: false, keyboard: false,
    icon: L.divIcon({ className: "", html: `<div class="plane-icon">${PLANE_SVG}</div>`,
                      iconSize: [34, 34], iconAnchor: [17, 17] }),
  }),
  markers: L.layerGroup().addTo(map),
  camera: L.circleMarker([0, 0], {
    pane: "playhead", interactive: false,
    radius: 6, color: "#0b1017", weight: 2, fillColor: "#ffa23e", fillOpacity: 1,
  }),
};

function attitudeScale(deg) {
  const rad = (Number(deg) || 0) * Math.PI / 180;
  return Math.max(0.18, Math.abs(Math.cos(rad)));
}

function planeIconSize() {
  const raw = parseFloat($("opt-plane-size")?.value);
  return Number.isFinite(raw) ? Math.min(128, Math.max(12, raw)) : 34;
}

function applyPlaneIconSize() {
  const size = planeIconSize();
  const half = size / 2;
  layers.aircraft.setIcon(L.divIcon({
    className: "",
    html: `<div class="plane-icon" style="width:${size}px;height:${size}px">${PLANE_SVG}</div>`,
    iconSize: [size, size],
    iconAnchor: [half, half],
  }));
  const svg = layers.aircraft.getElement()?.querySelector("svg");
  if (svg) {
    svg.setAttribute("width", String(size));
    svg.setAttribute("height", String(size));
  }
  const t = parseFloat($("scrub")?.value);
  if (Number.isFinite(t) && state.preview) showPlayhead(t);
}

function pointAircraft(heading, pitch = 0, bank = 0) {
  const icon = layers.aircraft.getElement()?.querySelector(".plane-icon");
  if (!icon) return;
  const bearing = typeof map.getBearing === "function" ? map.getBearing() : 0;
  const rotate = `rotate(${heading - bearing}deg)`;
  if ($("opt-attitude")?.checked) {
    icon.style.transform = `${rotate} scale(${attitudeScale(bank)}, ${attitudeScale(pitch)})`;
  } else {
    icon.style.transform = rotate;
  }
}

function dotIcon(className) {
  return L.divIcon({
    className: "",
    html: `<div class="handle ${className}"></div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    tooltipAnchor: [0, -14],
  });
}

function waypointIcon(selected, label, color) {
  const tint = color ? ` style="--flight:${color}"` : "";
  const text = label ? `<span class="wp-label">${label.replace(/[<>&]/g, "")}</span>` : "";
  return L.divIcon({
    className: "",
    html: `<div class="handle wp-icon has-label${selected ? " selected" : ""}"${tint}>${text}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    tooltipAnchor: [0, -14],
  });
}

map.on("click", (event) => {
  if (typeof pathAddActive === "function" && pathAddActive()) {
    if (typeof pathAddClick === "function") pathAddClick(event.latlng);
    return;
  }
  // Only appends while drawing. A bare click used to add a waypoint, which
  // made every missed grab of a marker silently extend the path.
  if (!state.doc || !state.drawing) return;
  if (state.track === "marks" && typeof appendMapMarker === "function") {
    appendMapMarker(event.latlng.lat, event.latlng.lng);
    return;
  }
  if (state.track !== "flight") return;
  appendFlightKeyframe(event.latlng.lat, event.latlng.lng);
});

// Clicking the track: program mode selects the nearest segment; waypoint mode
// inserts a keyframe into the middle of the path.
layers.flightHit.on("click", (event) => {
  if (typeof pathAddActive === "function" && pathAddActive()) {
    L.DomEvent.stop(event);
    if (typeof pathAddClick === "function") pathAddClick(event.latlng);
    return;
  }
  if (typeof programBuildActive === "function" && programBuildActive()) return;
  if (isProgramMode()) {
    L.DomEvent.stop(event);
    const index = nearestProgramSegmentIndex(event.latlng);
    if (index != null && typeof selectProgramSegment === "function") {
      selectProgramSegment(index);
    }
    return;
  }
  if (!state.doc || state.drawing) return;
  L.DomEvent.stop(event);
  insertFlightKeyframe(event.latlng);
});
layers.flightHit.on("mouseover", () => {
  if (!state.drawing) layers.flightHit.setStyle({ opacity: 0.25, color: "#fff" });
});
layers.flightHit.on("mouseout", () => layers.flightHit.setStyle({ opacity: 0 }));

// ---------------------------------------------------------------- document

function frames() {
  if (!state.doc) return [];
  if (state.track === "controls") return state.doc.sim_flight?.controls || [];
  if (state.track === "systems") return state.doc.systems || [];
  if (state.track === "map") return state.mapDoc?.map_keyframes || [];
  if (state.track === "marks") return state.mapDoc?.markers || [];
  return state.track === "flight" ? state.doc.flight_keyframes : state.doc.camera_keyframes;
}

function lastTime() {
  if (isProgramMode()) return state.preview?.duration || 0;
  const all = [
    ...(state.doc?.flight_keyframes || []),
    ...(state.doc?.camera_keyframes || []),
    ...(state.doc?.systems || []),
    ...(state.mapDoc?.map_keyframes || []),
  ];
  return all.reduce((most, k) => Math.max(most, k.time_offset), 0);
}

function blankSystemsKeyframe(time) {
  return {
    time_offset: time,
    flaps: null,
    gear_down: null,
    aileron: null,
    elevator: null,
    rudder: null,
    throttle: null,
  };
}

function appendSystemsKeyframe() {
  if (!state.doc.systems) state.doc.systems = [];
  const list = state.doc.systems;
  const at = state.selected === null ? list.length - 1 : state.selected;
  const previous = list[at];
  const next = list[at + 1];
  const time = !previous ? 0
    : next ? (previous.time_offset + next.time_offset) / 2
    : previous.time_offset + 9;
  const keyframe = blankSystemsKeyframe(Math.round(time * 10) / 10);
  // First key is an explicit start; later keys hold until something is typed.
  if (!previous) {
    keyframe.flaps = 0;
    keyframe.gear_down = false;
  }
  list.splice(at + 1, 0, keyframe);
  state.doc.meta.duration_seconds = lastTime();
  state.selected = at + 1;
  touched();
}

function appendFlightKeyframe(lat, lon) {
  const list = state.doc.flight_keyframes;
  const previous = list[list.length - 1];
  // Keep the pace of the leg before it rather than inventing a time.
  const gap = list.length >= 2
    ? list[list.length - 1].time_offset - list[list.length - 2].time_offset
    : 9;
  const keyframe = (typeof blankFlightFields === "function"
    ? blankFlightFields(previous, {
      time_offset: (previous ? previous.time_offset : 0) + gap,
      lat, lon,
      alt_ft_msl: previous ? previous.alt_ft_msl : 2500,
    })
    : {
      time_offset: (previous ? previous.time_offset : 0) + gap,
      time_source: "AUTHORED",
      lat, lon,
      alt_ft_msl: previous ? previous.alt_ft_msl : 2500,
      heading: { mode: "AUTO" },
      pitch: { mode: "AUTO" },
      bank: { mode: "AUTO" },
      easing: { ease_in: 0, ease_out: 0, hold_s: 0 },
      path: { kind: "STRAIGHT" },
      on_ground: Boolean(previous?.on_ground),
    });
  list.push(keyframe);
  state.doc.meta.duration_seconds = lastTime();
  if (previous && typeof syncHermiteJoin === "function") syncHermiteJoin(previous, list);
  if (typeof setFlightSelection === "function") setFlightSelection([keyframe.id], keyframe.id);
  else state.selected = list.length - 1;
  touched();
}

function insertFlightKeyframe(latlng) {
  const list = state.doc.flight_keyframes;
  const samples = state.preview?.samples || [];
  if (!samples.length) return;

  // The solved samples carry their own time, so the point the operator
  // clicked on the track already knows where it belongs in the timeline.
  let nearest = samples[0];
  let best = Infinity;
  for (const sample of samples) {
    const gap = (sample.lat - latlng.lat) ** 2 + (sample.lon - latlng.lng) ** 2;
    if (gap < best) { best = gap; nearest = sample; }
  }

  let index = list.findIndex((k) => k.time_offset > nearest.t);
  if (index <= 0) {
    appendFlightKeyframe(latlng.lat, latlng.lng);
    return;
  }
  // Keep it strictly between its neighbours; equal times are a blocking fault.
  const before = list[index - 1].time_offset;
  const after = list[index].time_offset;
  const time = Math.min(Math.max(nearest.t, before + 0.01), after - 0.01);

  const inserted = typeof blankFlightFields === "function"
    ? blankFlightFields(list[index - 1], {
      time_offset: time,
      lat: latlng.lat,
      lon: latlng.lng,
      alt_ft_msl: Math.round(nearest.alt_ft),
    })
    : {
      time_offset: time,
      time_source: "AUTHORED",
      lat: latlng.lat,
      lon: latlng.lng,
      alt_ft_msl: Math.round(nearest.alt_ft),
      heading: { mode: "AUTO" },
      pitch: { mode: "AUTO" },
      bank: { mode: "AUTO" },
      easing: { ease_in: 0, ease_out: 0, hold_s: 0 },
      path: { kind: "STRAIGHT" },
      on_ground: Boolean(list[index - 1]?.on_ground),
    };
  list.splice(index, 0, inserted);
  if (typeof syncHermiteJoin === "function") syncHermiteJoin(inserted, list);
  if (typeof setFlightSelection === "function") setFlightSelection([inserted.id], inserted.id);
  else state.selected = index;
  touched();
}

function ensureProgramCameras() {
  if (!state.program) return [];
  if (!Array.isArray(state.program.camera_keyframes)) {
    state.program.camera_keyframes = [];
  }
  return state.program.camera_keyframes;
}

function ensureSegmentIds(program) {
  if (!program?.segments) return;
  for (const segment of program.segments) {
    if (!segment.id) {
      segment.id = Math.random().toString(16).slice(2, 14);
    }
  }
}

/** Re-attach camera keys the last preview reported as orphaned. */
function rebindOrphanProgramCameras() {
  if (!isProgramMode() || !state.program || state._rebindCameras) return;
  const report = state.preview?.camera_keys;
  if (!Array.isArray(report) || !report.some((row) => row?.orphan)) return;
  ensureSegmentIds(state.program);
  const segments = state.program.segments || [];
  if (!segments.length) return;
  const ids = new Set(segments.map((seg) => seg.id));
  const fallback = segments[0].id;
  let changed = false;
  for (const key of state.program.camera_keyframes || []) {
    if (!key.anchor) {
      key.anchor = { segment_id: fallback, at: 0 };
      changed = true;
      continue;
    }
    if (!ids.has(key.anchor.segment_id)) {
      key.anchor.segment_id = fallback;
      changed = true;
    }
  }
  if (!changed) return;
  // One more preview with the rebound anchors so camera_track is populated
  // before the operator hits Play. Guard against a rebind↔solve loop.
  state._rebindCameras = true;
  clearTimeout(solveTimer);
  const generation = ++solveGeneration;
  solveTimer = setTimeout(() => {
    solve(generation).finally(() => { state._rebindCameras = false; });
  }, 0);
}

function programCameraTime(key) {
  const report = state.preview?.camera_keys;
  if (Array.isArray(report) && state.program?.camera_keyframes) {
    const slot = state.program.camera_keyframes.indexOf(key);
    if (slot >= 0 && report[slot] && report[slot].time_offset != null) {
      return report[slot].time_offset;
    }
  }
  const segments = state.program?.segments || [];
  const index = segments.findIndex((seg) => seg.id === key?.anchor?.segment_id);
  const summary = state.preview?.segments?.[index];
  if (!summary?.timing) return null;
  return summary.timing.start_s + (key.anchor?.at ?? 0) * summary.timing.duration_s;
}

function defaultProgramCameraAnchor() {
  ensureSegmentIds(state.program);
  const segments = state.program.segments || [];
  let segment = null;
  if (typeof state.selected === "number" && state.track === "flight") {
    segment = segments[state.selected];
  }
  if (!segment && segments.length) segment = segments[0];
  if (!segment) return null;
  // Start of the segment so a single key covers the whole flight from t=0
  // rather than only lighting up when the scrubber lands on mid-segment.
  return { segment_id: segment.id, at: 0 };
}

function appendProgramCameraKeyframe() {
  const list = ensureProgramCameras();
  const anchor = defaultProgramCameraAnchor();
  if (!anchor) {
    alert("Add a flight segment before placing a camera key.");
    return;
  }
  const at = state.track === "camera" && typeof state.selected === "number"
    ? state.selected : list.length - 1;
  const previous = at >= 0 ? list[at] : null;
  const key = {
    anchor: previous?.anchor
      ? { ...previous.anchor }
      : { ...anchor },
    camera_type: previous ? previous.camera_type : "CINEMATIC",
    fov_deg: null,
    cockpit: previous?.cockpit
      ? { ...previous.cockpit } : { view: "PILOT", index: 0, zoom_pct: null },
    position: previous?.position
      ? { ...previous.position }
      : { frame: "HORIZON", azimuth_deg: 0, radius_m: 80, height_m: 15 },
    look_at: previous?.look_at
      ? { ...previous.look_at } : { mode: "AIRCRAFT_POINT", ref: "CG" },
    up: { mode: "WORLD_UP", x: 0, y: 1, z: 0 },
    easing: { ease_in: 0, ease_out: 0, hold_s: 0 },
    transition: "BLEND",
  };
  const insertAt = Math.max(0, at + 1);
  list.splice(insertAt, 0, key);
  state.track = "camera";
  state.selected = insertAt;
  // One scrub jump after the upcoming solve so the new key is visible; do not
  // keep re-snapping on every later edit or play never leaves that instant.
  state.scrubToCamera = true;
  document.querySelectorAll(".tab").forEach(
    (tab) => tab.classList.toggle("active", tab.dataset.track === "camera"));
  touched();
}

function appendCameraKeyframe() {
  if (isProgramMode()) {
    appendProgramCameraKeyframe();
    return;
  }
  const list = state.doc.camera_keyframes;
  // Insert after the selection rather than always at the end, so a move can
  // be refined in place instead of only ever extending the shot.
  const at = state.selected === null ? list.length - 1 : state.selected;
  const previous = list[at];
  const next = list[at + 1];
  const time = !previous ? 0
    : next ? (previous.time_offset + next.time_offset) / 2
    : previous.time_offset + 9;

  list.splice(at + 1, 0, {
    time_offset: time,
    camera_type: previous ? previous.camera_type : "CINEMATIC",
    fov_deg: null,
    cockpit: previous && previous.cockpit
      ? { ...previous.cockpit } : { view: "PILOT", index: 0, zoom_pct: null },
    position: previous && previous.position
      ? { ...previous.position }
      : { frame: "BODY", ref: "CG", x_m: -70, y_m: 25, z_m: -130 },
    look_at: previous ? { ...previous.look_at } : { mode: "AIRCRAFT_POINT", ref: "CG" },
    up: { mode: "WORLD_UP", x: 0, y: 1, z: 0 },
    easing: { ease_in: 0, ease_out: 0, hold_s: 0 },
    transition: "BLEND",
  });
  state.doc.meta.duration_seconds = lastTime();
  state.selected = at + 1;
  touched();
}

function removeSelected() {
  if (isProgramMode()) {
    if (state.track === "camera") {
      const list = ensureProgramCameras();
      if (typeof state.selected !== "number" || !list[state.selected]) return;
      list.splice(state.selected, 1);
      state.selected = list.length
        ? Math.min(state.selected, list.length - 1) : null;
      touched();
      return;
    }
    if (typeof removeProgramSegment === "function") removeProgramSegment();
    return;
  }
  const list = frames();
  // A sim flight may legitimately have no control keyframes: it flies hands-off.
  const minimum = (state.track === "controls" || state.track === "systems"
    || state.track === "map" || state.track === "marks") ? 0 : 1;
  if (state.selected === null || list.length <= minimum) return;
  list.splice(state.selected, 1);
  state.selected = list.length ? Math.min(state.selected, list.length - 1) : null;
  state.doc.meta.duration_seconds = lastTime();
  touched();
}

function rescaleDuration(seconds) {
  const current = lastTime();
  if (current <= 0) return;
  const factor = seconds / current;
  for (const list of [state.doc.flight_keyframes, state.doc.camera_keyframes,
                     state.doc.systems || [], state.mapDoc?.map_keyframes || []]) {
    for (const keyframe of list) keyframe.time_offset *= factor;
  }
  state.doc.meta.duration_seconds = seconds;
  touched();
}

// ---------------------------------------------------------------- solving

let solveTimer = null;
let solveGeneration = 0;

function setSolving(active) {
  state.solving = active;
  document.body.classList.toggle("solving", active);
  const pill = $("solve-status");
  const banner = $("map-solving");
  if (pill) pill.hidden = !active;
  if (banner) banner.hidden = !active;
}

function inspectorTextFieldFocused() {
  const active = document.activeElement;
  const host = $("inspector");
  if (!active || !host || !host.contains(active)) return false;
  if (active.tagName === "TEXTAREA") return true;
  if (active.tagName !== "INPUT") return false;
  return active.type === "text" || active.type === "number" || active.type === "";
}

function touched() {
  if (isProgramMode()) {
    // Camera (and other) inspector fields call touched(); program geometry
    // edits use programTouched. Both must re-preview or the orange camera
    // track / 3D view stay on the previous solve.
    if (typeof programTouched === "function") {
      programTouched({ rebuild: false });
    } else {
      state.dirty = true;
      clearTimeout(solveTimer);
      const generation = ++solveGeneration;
      solveTimer = setTimeout(() => solve(generation), 150);
    }
    if (!inspectorTextFieldFocused()) {
      renderKeyframeList();
      renderInspector();
    }
    renderMeta();
    return;
  }
  state.dirty = true;
  setSolving(true);
  // Do not rebuild the inspector while a number/text box has focus — a live
  // solve finishing mid-keystroke was wiping camera (and waypoint) fields
  // after one character.
  if (!inspectorTextFieldFocused()) {
    renderKeyframeList();
    renderInspector();
  }
  renderMeta();
  clearTimeout(solveTimer);
  const generation = ++solveGeneration;
  solveTimer = setTimeout(() => solve(generation), 150);
}

/** A greyed-out Play button with no reason is indistinguishable from a bug,
 *  so say what is blocking it and offer to jump to where it happens. */
function playBlocking() {
  if (clientPlayMode()) {
    if (!state.preview?.samples?.length) {
      return [{ message: "No flight path to play on the map.", at: null }];
    }
    return [];
  }
  return state.diagnostics.filter((d) => d.severity === "BLOCKING");
}

function renderPlayable() {
  const blocking = playBlocking();
  $("btn-play").disabled = blocking.length > 0;
  $("btn-pause").disabled = blocking.length > 0;
  if ($("btn-record")) $("btn-record").disabled = blocking.length > 0 && !map2dMode?.();
  const note = $("play-blocked");
  note.hidden = blocking.length === 0;
  if (!blocking.length) return;
  const first = blocking[0];
  const more = blocking.length > 1 ? ` (+${blocking.length - 1} more below)` : "";
  note.textContent = `Can't play: ${first.message}${more}`;
  note.title = first.at != null ? `Click to scrub to ${first.at.toFixed(1)} s` : "";
  note.onclick = first.at != null ? () => scrubTo(first.at) : null;
}

async function solve(generation = ++solveGeneration) {
  if (!state.doc && !state.program) {
    if (generation === solveGeneration) setSolving(false);
    return;
  }
  setSolving(true);
  try {
    if (isProgramMode()) {
      try {
        // Segment ids must be stable before preview: an empty id is reminted
        // server-side and any camera still pointing at the old string orphans,
        // which empties camera_track and the 3D view falls back to chase as
        // soon as the scrubber leaves the key's time.
        ensureSegmentIds(state.program);
        const preview = await api("POST", "/api/program/preview", {
          program: state.program,
          samples: 240,
        });
        if (generation !== solveGeneration) return;
        state.preview = preview;
        state.diagnostics = [];
        if (typeof adoptSolvedProgram === "function") adoptSolvedProgram(preview);
        rebindOrphanProgramCameras();
      } catch (error) {
        if (generation !== solveGeneration) return;
        state.preview = null;
        state.diagnostics = [{ severity: "BLOCKING", check: "solve", message: String(error.message) }];
      }
    } else {
      // Re-sort so a time edit cannot leave the list out of order mid-edit.
      if (!state.doc.systems) state.doc.systems = [];
      state.doc.flight_keyframes.sort((a, b) => a.time_offset - b.time_offset);
      const joinRank = { BLEND: 0, SHOT: 1, CUT: 2 };
      state.doc.camera_keyframes.sort((a, b) => {
        const dt = a.time_offset - b.time_offset;
        if (dt) return dt;
        return (joinRank[a.transition || "BLEND"] ?? 0) - (joinRank[b.transition || "BLEND"] ?? 0);
      });
      if (state.doc.systems) {
        state.doc.systems.sort((a, b) => a.time_offset - b.time_offset);
      }
      try {
        const [preview, validation] = await Promise.all([
          api("POST", "/api/paths/preview", state.doc),
          api("POST", "/api/paths/validate", state.doc),
        ]);
        if (generation !== solveGeneration) return;
        state.preview = preview;
        state.diagnostics = validation.diagnostics;
      } catch (error) {
        if (generation !== solveGeneration) return;
        state.preview = null;
        state.diagnostics = [{ severity: "BLOCKING", check: "solve", message: String(error.message) }];
      }
    }
    if (generation !== solveGeneration) return;
    $("scrub").max = state.preview?.duration || 1;
    renderPlayable();
    renderMap();
    renderDiagnostics();
    renderProfile();
    if (!inspectorTextFieldFocused()) {
      renderKeyframeList();
      renderInspector();
    }
    // The table editor, when open, redraws its solved columns from here rather
    // than guessing at how long a solve takes.
    if (typeof afterSolve === "function") afterSolve();
    try {
      if (typeof onProgramAfterSolve === "function") onProgramAfterSolve();
    } catch (error) {
      console.error("onProgramAfterSolve", error);
    }
    if (typeof validateSimFlight === "function") validateSimFlight();
    if (typeof onMap3dPreview === "function") onMap3dPreview();
    if (state.previewing && state.preview) pushSimPreview();
    // Refresh the playhead against the new preview so camera edits update the
    // orange mark / 3D view without waiting for a scrub. Only jump the
    // scrubber when a new key was just added (or select() asked for it) —
    // re-snapping on every solve made the shot look locked to one instant
    // and the view fell back to chase as soon as play moved away.
    let scrubT = parseFloat($("scrub")?.value);
    if (state.scrubToCamera && isProgramMode() && state.track === "camera"
        && typeof state.selected === "number") {
      const key = state.program?.camera_keyframes?.[state.selected];
      const time = key ? programCameraTime(key) : null;
      if (Number.isFinite(time)) {
        scrubT = time;
        if ($("scrub")) $("scrub").value = String(time);
      }
      state.scrubToCamera = false;
    }
    if (Number.isFinite(scrubT)) showPlayhead(scrubT);
  } finally {
    // Always clear the busy pill for the active generation — an early return
    // after a superseded solve used to leave "Recomputing…" stuck forever.
    if (generation === solveGeneration) setSolving(false);
  }
}

// ---------------------------------------------------------------- rendering

const FLIGHT_TRACK_COLORS = {
  STRAIGHT: "#3ecf9a",
  ARC: "#ffa23e",
  HERMITE: "#4ea1ff",
  BSPLINE: "#c084fc",
  SMOOTH: "#4ea1ff",
};

// Every kind, B-spline included, is drawn from the solved samples. Refitting
// the spline here instead used to paint a curve the aircraft never flew: the
// two sides decide which waypoints belong to a span by different rules, so
// whichever one you trusted, the other disagreed.
function flightTrackSegments() {
  const samples = state.preview?.samples || [];
  if (samples.length < 2) return [];
  // Prefer the mode stamped on each solved sample so colour always matches
  // the geometry the server actually built (not a stale client flag).
  if (samples[0].path_mode != null) {
    const segments = [];
    let mode = samples[0].path_kind || samples[0].path_mode || "STRAIGHT";
    let segmentIndex = samples[0].segment_index;
    let latlngs = [[samples[0].lat, samples[0].lon]];
    const push = () => {
      if (latlngs.length >= 2) {
        segments.push({ mode, latlngs, segmentIndex });
      }
    };
    for (let i = 1; i < samples.length; i++) {
      const next = samples[i].path_kind || samples[i].path_mode || "STRAIGHT";
      const nextIndex = samples[i].segment_index;
      // A mid-path MoveTo sets break_before: cut the polyline rather than
      // draw a line across the jump. On an ordinary join the first sample of
      // the next segment is also the previous segment's end (right-continuous
      // clock) — share that point so the drawn path has no gap.
      if (samples[i].break_before) {
        push();
        mode = next;
        segmentIndex = nextIndex;
        latlngs = [[samples[i].lat, samples[i].lon]];
      } else if ((nextIndex != null && segmentIndex != null && nextIndex !== segmentIndex)
          || next !== mode) {
        latlngs.push([samples[i].lat, samples[i].lon]);
        push();
        mode = next;
        segmentIndex = nextIndex;
        latlngs = [[samples[i].lat, samples[i].lon]];
      } else {
        latlngs.push([samples[i].lat, samples[i].lon]);
      }
    }
    push();
    return segments;
  }
  const keyframes = state.doc?.flight_keyframes || [];
  if (keyframes.length < 2) {
    return [{ mode: "STRAIGHT", latlngs: samples.map((s) => [s.lat, s.lon]) }];
  }
  const segments = [];
  let sampleIndex = 0;
  for (let i = 0; i < keyframes.length - 1; i++) {
    const startT = keyframes[i].time_offset;
    const endT = keyframes[i + 1].time_offset;
    while (sampleIndex < samples.length && samples[sampleIndex].t < startT - 1e-9) {
      sampleIndex++;
    }
    const latlngs = [];
    let j = sampleIndex;
    while (j < samples.length && samples[j].t <= endT + 1e-9) {
      latlngs.push([samples[j].lat, samples[j].lon]);
      j++;
    }
    if (latlngs.length < 2) {
      latlngs.length = 0;
      latlngs.push([keyframes[i].lat, keyframes[i].lon],
                   [keyframes[i + 1].lat, keyframes[i + 1].lon]);
    }
    segments.push({ mode: keyframes[i].path?.kind || "STRAIGHT", latlngs });
    sampleIndex = Math.max(0, j - 1);
  }
  return segments;
}

/** Nearest authored program segment to a map click (by sample proximity). */
function nearestProgramSegmentIndex(latlng) {
  const drawn = flightTrackSegments();
  let best = null;
  let bestDist = Infinity;
  for (const segment of drawn) {
    if (segment.segmentIndex == null) continue;
    for (const [lat, lon] of segment.latlngs) {
      const dLat = lat - latlng.lat;
      const dLon = lon - latlng.lng;
      const dist = dLat * dLat + dLon * dLon;
      if (dist < bestDist) {
        bestDist = dist;
        best = segment.segmentIndex;
      }
    }
  }
  return best;
}

function bindProgramSegmentClick(layer, segmentIndex) {
  if (!isProgramMode() || segmentIndex == null) return;
  layer.on("click", (event) => {
    if (typeof programBuildActive === "function" && programBuildActive()) return;
    L.DomEvent.stop(event);
    if (typeof selectProgramSegment === "function") selectProgramSegment(segmentIndex);
  });
}

/** Everything the solver draws: the track, its gizmos, and the camera line
 *  that follows it. A waypoint drag redraws this and nothing else, because
 *  rebuilding the marker layer would pull the marker out from under the drag
 *  Leaflet is in the middle of. */
function renderSolvedTracks() {
  const preview = state.preview;
  const line = (preview?.samples || []).map((s) => [s.lat, s.lon]);
  layers.flightTrack.clearLayers();
  const drawn = flightTrackSegments();
  const hit = [];
  for (const segment of drawn) {
    for (const latlng of segment.latlngs) hit.push(latlng);
  }
  const selectedProgram = isProgramMode() && typeof state.selected === "number"
    ? state.selected : null;
  for (const segment of drawn) {
    const selected = selectedProgram != null && segment.segmentIndex === selectedProgram;
    const base = (typeof flightLineStyle === "function" && flightLineStyle()) || {
      color: FLIGHT_TRACK_COLORS[segment.mode] || FLIGHT_TRACK_COLORS.STRAIGHT,
      weight: 8,
      lineJoin: "round",
      lineCap: "round",
    };
    // Whole path shares one stroke weight + white outline; selection is colour.
    const weight = Math.max(6, base.weight || 8);
    const outline = L.polyline(segment.latlngs, {
      ...base, color: "#ffffff", weight: weight + 4, opacity: 0.95,
    });
    const stroke = L.polyline(segment.latlngs, {
      ...base,
      color: selected ? "#ffe566" : (base.color || FLIGHT_TRACK_COLORS.STRAIGHT),
      weight,
      opacity: 1,
    });
    bindProgramSegmentClick(outline, segment.segmentIndex);
    bindProgramSegmentClick(stroke, segment.segmentIndex);
    layers.flightTrack.addLayer(outline);
    layers.flightTrack.addLayer(stroke);
  }
  if (typeof renderPathGizmos === "function") renderPathGizmos();
  layers.flightHit.setLatLngs(hit.length >= 2 ? hit : line);
  layers.cameraTrack.setLatLngs(showMapCamera()
    ? (preview?.camera_track || []).map((s) => [s.lat, s.lon]) : []);
}

let dragSolveBusy = false;
let dragSolveAgain = false;

/** Live curve under a dragged waypoint. The server owns the geometry, so ask
 *  it rather than approximating the legs here — what you watch mid-drag is
 *  then exactly what you get on drop. Keep one request in flight and chase it
 *  with one more if the pointer moved while it was out, which tracks the
 *  pointer as closely as the solve allows without flooding the backend. */
async function solveWhileDragging() {
  if (!state.doc) return;
  if (dragSolveBusy) { dragSolveAgain = true; return; }
  dragSolveBusy = true;
  const generation = solveGeneration;
  try {
    const preview = await api("POST", "/api/paths/preview", state.doc);
    // A drop lands a full solve and bumps the generation; don't paint over it.
    if (generation !== solveGeneration) return;
    state.preview = preview;
    renderSolvedTracks();
  } catch {
    // A mid-drag failure isn't worth a banner. The drop re-solves and reports.
  } finally {
    dragSolveBusy = false;
    if (dragSolveAgain) {
      dragSolveAgain = false;
      solveWhileDragging();
    }
  }
}

function renderMap() {
  const preview = state.preview;
  renderSolvedTracks();

  layers.waypoints.clearLayers();
  if (showMapWaypoints()) {
    (state.doc?.flight_keyframes || []).forEach((keyframe, index) => {
      const chosen = state.track === "flight" && (typeof isFlightIndexSelected === "function"
        ? isFlightIndexSelected(index) : index === state.selected);
      const label = typeof waypointLabel === "function" ? waypointLabel(keyframe, index) : `${index + 1}`;
      const group = typeof groupOf === "function" ? groupOf(keyframe.id) : null;
      const marker = L.marker([keyframe.lat, keyframe.lon], {
        icon: waypointIcon(chosen, label, group?.color),
        draggable: true,
      });
      marker.bindTooltip(`${label} · ${keyframe.time_offset.toFixed(1)}s · ` +
                         `${Math.round(keyframe.alt_ft_msl)} ft — drag to move, ` +
                         `right-click to delete`);
      marker.on("click", (event) => {
        L.DomEvent.stop(event);
        if (typeof pathAddActive === "function" && pathAddActive()) {
          if (typeof pathAddClick === "function") pathAddClick(keyframe);
          return;
        }
        if (typeof selectFlight === "function") selectFlight(index, event.originalEvent);
        else { state.track = "flight"; select(index); }
      });
      marker.on("contextmenu", (event) => {
        L.DomEvent.stop(event);
        state.track = "flight";
        if (typeof setFlightSelection === "function") setFlightSelection([keyframe.id], keyframe.id);
        else state.selected = index;
        removeSelected();
      });
      marker.on("dragstart", () => {
        const moving = (typeof selectedFlightKeyframes === "function" && isFlightIndexSelected(index)
          ? selectedFlightKeyframes() : [keyframe]);
        marker._fsOrigin = moving.map((k) => ({ key: k, lat: k.lat, lon: k.lon }));
        marker._fsStart = { lat: keyframe.lat, lon: keyframe.lon };
        dragSolveAgain = false;
      });
      marker.on("drag", (event) => {
        // Move the keyframes and redraw the track only. A full render would
        // rebuild the marker layer and destroy the marker being dragged.
        const { lat, lng } = event.target.getLatLng();
        const origins = marker._fsOrigin;
        const start = marker._fsStart;
        if (origins && origins.length > 1 && start && typeof offsetLatLon === "function") {
          const north = (lat - start.lat) * Math.PI / 180 * 6371000;
          const east = (lng - start.lon) * Math.PI / 180 * 6371000
            * Math.cos(start.lat * Math.PI / 180);
          for (const { key, lat: oLat, lon: oLon } of origins) {
            const next = offsetLatLon(oLat, oLon, north, east);
            key.lat = next.lat;
            key.lon = next.lon;
          }
        } else {
          keyframe.lat = lat;
          keyframe.lon = lng;
        }
        solveWhileDragging();
      });
      marker.on("dragend", () => {
        state.track = "flight";
        if (typeof selectFlight === "function" && !isFlightIndexSelected(index)) selectFlight(index);
        else if (typeof setFlightSelection === "function") setFlightSelection(state.selectedIds, keyframe.id);
        else select(index);
        touched();
      });
      layers.waypoints.addLayer(marker);
    });
  }

  // Camera keyframes live in the aircraft's body frame, so they have no fixed
  // place on the map. Draw them where the solved path puts them at their own
  // time, which is where they will actually be.
  layers.cameras.clearLayers();
  if (showMapCamera()) {
    const track = preview?.camera_track || [];
    const cameraKeys = isProgramMode()
      ? (state.program?.camera_keyframes || [])
      : (state.doc?.camera_keyframes || []);
    cameraKeys.forEach((keyframe, index) => {
      const time = isProgramMode()
        ? programCameraTime(keyframe)
        : keyframe.time_offset;
      if (!Number.isFinite(time)) return;
      const point = nearestByTime(track, time);
      if (!point) return;
      const chosen = state.track === "camera" && index === state.selected;
      const marker = L.marker([point.lat, point.lon], {
        icon: dotIcon(`cam-icon${chosen ? " selected" : ""}`),
      });
      const label = isProgramMode() && keyframe.anchor
        ? `Camera ${index + 1} · at ${Number(keyframe.anchor.at).toFixed(2)}`
          + ` · ${time.toFixed(1)}s`
        : `Camera ${index + 1} · ${time.toFixed(1)}s`;
      marker.bindTooltip(label);
      marker.on("click", () => { state.track = "camera"; select(index); });
      layers.cameras.addLayer(marker);
    });
  } else {
    hideCameraPlayhead();
  }

  if (typeof renderSimFlightLayers === "function") renderSimFlightLayers();
  if (typeof renderMapMarkers === "function") renderMapMarkers();
  if (typeof renderProgramGizmos === "function") renderProgramGizmos();
}

function showMapWaypoints() {
  return $("opt-waypoints")?.checked !== false;
}

function showMapCamera() {
  // Cinematic path + orange playhead. 2D used to hide these so only map-viewport
  // keys showed; program cameras then looked like a single stuck handle.
  return $("opt-camera")?.checked !== false;
}

function mapIsLocked() {
  if (typeof map2dMode === "function" && map2dMode()) return false;
  return Boolean($("opt-lock-map")?.checked);
}

function mapFollowsAircraft() {
  return Boolean($("opt-follow")?.checked) && !mapIsLocked();
}

function hideCameraPlayhead() {
  if (map.hasLayer(layers.camera)) map.removeLayer(layers.camera);
  layers.sightLine.setLatLngs([]);
}

function nearestByTime(rows, t) {
  let best = null;
  let bestGap = Infinity;
  for (const row of rows) {
    const gap = Math.abs(row.t - t);
    if (gap < bestGap) { bestGap = gap; best = row; }
  }
  return best;
}

function lerpAngleDeg(a, b, u, signed = false) {
  const delta = ((b - a + 180) % 360 + 360) % 360 - 180;
  const wrapped = ((a + delta * u) % 360 + 360) % 360;
  // Pitch and bank are signed: -11 must stay -11, not become 349, or the 3D
  // view clamps tilt to 90 and the cinematic camera stares at the horizon.
  return signed && wrapped > 180 ? wrapped - 360 : wrapped;
}

const POSE_ANGLE_KEYS = new Set(["heading", "bank", "pitch"]);
const SIGNED_ANGLE_KEYS = new Set(["bank", "pitch"]);

/** Pose at an exact clock time, lerped between the solved samples. */
function lerpByTime(rows, t) {
  if (!rows.length) return null;
  if (t <= rows[0].t) return { ...rows[0], t };
  const last = rows[rows.length - 1];
  if (t >= last.t) return { ...last, t };
  let lo = 0, hi = rows.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].t <= t) lo = mid;
    else hi = mid;
  }
  const start = rows[lo], end = rows[hi];
  const span = end.t - start.t;
  const u = span <= 1e-9 ? 0 : (t - start.t) / span;
  const out = { ...start, t };
  for (const key of Object.keys(start)) {
    if (key === "t" || key === "path_mode" || key === "path_kind") continue;
    const a = start[key], b = end[key];
    if (typeof a !== "number" || typeof b !== "number") continue;
    out[key] = POSE_ANGLE_KEYS.has(key)
      ? lerpAngleDeg(a, b, u, SIGNED_ANGLE_KEYS.has(key))
      : a + (b - a) * u;
  }
  return out;
}

function describeFlight(keyframe) {
  const solved = poseAt(keyframe.time_offset);
  const alt = `${Math.round(keyframe.alt_ft_msl)} ft`;
  if (!solved) return alt;
  const speed = Number.isFinite(solved.speed_kt) ? `${Math.round(solved.speed_kt)} kt` : "";
  const track = Number.isFinite(solved.heading) ? `${solved.heading.toFixed(0)}°` : "";
  const bank = Number.isFinite(solved.bank) ? `bank ${solved.bank.toFixed(0)}°` : "";
  return [alt, speed, track, bank].filter(Boolean).join(" · ");
}

function renderKeyframeList() {
  const host = $("keyframe-list");
  host.innerHTML = "";
  if (isProgramMode()) {
    if (state.track === "camera") {
      renderProgramCameraList(host);
    } else {
      renderProgramSegmentList(host);
    }
    $("btn-add").textContent = state.track === "camera"
      ? "Add camera keyframe" : "Add line";
    $("btn-add").disabled = false;
    $("btn-orbit").hidden = true;
    $("btn-draw").hidden = true;
    $("btn-remove").disabled = state.track === "camera"
      ? typeof state.selected !== "number"
      : typeof state.selected !== "number";
    if (typeof showProgramAddBar === "function") {
      showProgramAddBar(state.track === "flight");
    }
    if (state.track === "camera") {
      $("add-hint").textContent = "Camera keys anchor to a segment fraction "
        + "(0 = start, 1 = end). Absolute time is derived when the path solves, "
        + "so reshaping a segment keeps the shot framed.";
    }
    return;
  }
  frames().forEach((keyframe, index) => {
    const row = document.createElement("div");
    const chosen = state.track === "flight" && typeof isFlightIndexSelected === "function"
      ? isFlightIndexSelected(index) : index === state.selected;
    row.className = `kf${chosen ? " selected" : ""}`;
    const detail = state.track === "flight" ? describeFlight(keyframe)
      : state.track === "controls" ? describeControls(keyframe)
      : state.track === "systems" ? describeSystems(keyframe)
      : state.track === "map" ? describeMapCamera(keyframe)
      : state.track === "marks" ? describeMarker(keyframe)
      : describeCamera(keyframe);
    const time = Number.isFinite(keyframe.time_offset) ? `${keyframe.time_offset.toFixed(1)}s` : "—";
    const group = state.track === "flight" && typeof groupOf === "function" ? groupOf(keyframe.id) : null;
    const title = state.track === "flight" && typeof waypointLabel === "function"
      ? waypointLabel(keyframe, index) : String(index + 1);
    const swatch = group ? `<span class="swatch" style="background:${group.color}"></span>` : "";
    row.innerHTML = `${swatch}<span class="t">${time}</span>` +
                    `<span class="n">${title}</span><span>${detail}</span>`;
    row.onclick = (event) => {
      if (state.track === "flight" && typeof selectFlight === "function") selectFlight(index, event);
      else select(index);
    };
    host.appendChild(row);
  });
  if (typeof renderGroupChips === "function") renderGroupChips();
  if (typeof renderBulkBar === "function") renderBulkBar();
  $("btn-add").textContent = state.track === "flight" ? "Add waypoint"
    : state.track === "controls" ? "Add control keyframe"
    : state.track === "systems" ? "Add systems keyframe"
    : state.track === "map" ? "Add map camera"
    : state.track === "marks" ? "Add marker"
    : "Add camera keyframe";
  $("btn-add").disabled = state.track === "controls" && !state.doc?.sim_flight;
  $("btn-orbit").hidden = state.track !== "camera";
  $("btn-draw").hidden = state.track !== "flight" && state.track !== "marks";
  if ($("pathadd-seg-bar")) $("pathadd-seg-bar").hidden = state.track !== "flight";
  if ($("pathadd-map-bar")) $("pathadd-map-bar").hidden = state.track !== "flight";
  if ($("btn-arc")) $("btn-arc").hidden = true;
  if (state.track !== "flight" && typeof cancelPathAdd === "function" && typeof pathAddActive === "function"
      && pathAddActive()) {
    cancelPathAdd();
  }
  $("smooth-timing-row").hidden = state.track !== "flight";
  if ($("map2d-capture")) $("map2d-capture").hidden = state.track !== "map";
  if (state.track === "controls") {
    $("add-hint").textContent = state.doc?.sim_flight
      ? "Each keyframe sets controls from its time on. Leave a control blank to keep "
        + "whatever it was doing. Add inserts after the selected keyframe."
      : "";
    return;
  }
  if (state.track === "systems") {
    $("add-hint").textContent = "Each keyframe sets flaps, gear, surfaces and throttle "
      + "from its time on. Leave a field blank to keep whatever it was. An empty list "
      + "leaves the sim as the last take left it. Add inserts after the selected keyframe.";
    return;
  }
  if (state.track === "map") {
    $("add-hint").textContent = "Map camera keys set centre, zoom and rotation at a time. "
      + "Capture view stores the map as it is now at the slider’s time. 2D Play interpolates them.";
    return;
  }
  if (state.track === "marks") {
    $("add-hint").textContent = state.drawing
      ? "Click the map to drop a marker. Click Draw again to stop."
      : "Add a marker or click Draw and click the map. Drag a pin to move it.";
    return;
  }
  if (state.track === "flight" && typeof pathAddHint === "function") {
    const arcHint = pathAddHint();
    if (arcHint) {
      $("add-hint").textContent = arcHint;
      return;
    }
  }
  $("add-hint").textContent = state.track === "flight"
    ? (state.drawing
        ? "Drawing: each click on the map appends a waypoint. Click Draw again to stop."
        : "Drag a waypoint to move it, right-click one to delete it, or click the "
          + "track to insert a waypoint between two others. Add segment places a "
          + "straight, arc, Hermite or B-spline from the selected waypoint.")
    : "Camera positions are relative to the aircraft, so edit them below. "
      + "Add inserts after the selected keyframe. Orbit… writes a level drone "
      + "circle as cinematic keyframes.";
}

const PROGRAM_KIND_LABEL = {
  MOVE_TO: "MoveTo",
  LINE_TO: "Line",
  ARC: "Arc",
  HERMITE: "Hermite",
  SPLINE: "Spline",
};

function renderProgramCameraList(host) {
  const keys = ensureProgramCameras();
  const segments = state.program?.segments || [];
  const kindLabel = (typeof ProgramFields !== "undefined" && ProgramFields.KIND_LABEL)
    || PROGRAM_KIND_LABEL;
  if (!keys.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = segments.length
      ? "No camera keys yet. Add camera keyframe anchors to a segment."
      : "Add a flight segment first, then place camera keys on it.";
    host.appendChild(empty);
    return;
  }
  keys.forEach((keyframe, index) => {
    const row = document.createElement("div");
    row.className = `kf${index === state.selected ? " selected" : ""}`;
    const seg = segments.find((s) => s.id === keyframe.anchor?.segment_id);
    const segLabel = seg
      ? (seg.name || kindLabel[seg.kind] || seg.kind)
      : "(missing segment)";
    const time = programCameraTime(keyframe);
    const timeLabel = Number.isFinite(time) ? `${time.toFixed(1)}s` : "—";
    const at = Number(keyframe.anchor?.at ?? 0);
    row.innerHTML = `<span class="t">${timeLabel}</span>`
      + `<span class="n">${index + 1}</span>`
      + `<span>${describeCamera(keyframe)} · ${segLabel} @ ${at.toFixed(2)}</span>`;
    row.onclick = () => {
      state.track = "camera";
      select(index);
    };
    host.appendChild(row);
  });
}

function renderProgramSegmentList(host) {
  const segments = state.program?.segments || [];
  const kindLabel = (typeof ProgramFields !== "undefined" && ProgramFields.KIND_LABEL)
    || PROGRAM_KIND_LABEL;
  // Origin is the pen's start — first row so it is obvious how to move the path.
  const originRow = document.createElement("div");
  originRow.className = `kf${state.selected === "origin" ? " selected" : ""}`;
  const origin = state.program?.origin;
  originRow.innerHTML = `<span class="t">◉</span>`
    + `<span class="n">Start</span>`
    + `<span>${origin ? `${origin.lat.toFixed(4)}, ${origin.lon.toFixed(4)}` : "origin"}</span>`;
  originRow.onclick = () => {
    if (typeof selectProgramOrigin === "function") selectProgramOrigin();
    else {
      state.selected = "origin";
      renderKeyframeList();
      renderInspector();
    }
  };
  host.appendChild(originRow);

  segments.forEach((segment, index) => {
    const row = document.createElement("div");
    row.className = `kf${index === state.selected ? " selected" : ""}`;
    const kind = kindLabel[segment.kind] || segment.kind;
    const title = segment.name || kind;
    row.innerHTML = `<span class="t">${index + 1}</span>` +
                    `<span class="n">${title}</span><span>${kind}</span>`;
    row.onclick = () => {
      if (typeof selectProgramSegment === "function") selectProgramSegment(index);
      else {
        state.selected = index;
        renderKeyframeList();
        renderInspector();
      }
    };
    host.appendChild(row);
  });
  $("btn-add").textContent = "Add line";
  $("btn-add").disabled = false;
  $("btn-remove").disabled = typeof state.selected !== "number";
  $("btn-orbit").hidden = true;
  $("btn-draw").hidden = true;
  if ($("pathadd-seg-bar")) $("pathadd-seg-bar").hidden = true;
  if ($("pathadd-map-bar")) $("pathadd-map-bar").hidden = true;
  if (typeof showProgramAddBar === "function") showProgramAddBar(true);
  $("smooth-timing-row").hidden = true;
  if ($("map2d-capture")) $("map2d-capture").hidden = true;
  if (typeof updateProgramBuildHint === "function") updateProgramBuildHint();
  else {
    $("add-hint").textContent = "Start moves the origin. Use Add for a new segment "
      + "(map click for Line / Arc / Hermite / MoveTo). Remove deletes the selection.";
  }
}

const SYSTEMS_CHANNELS = [
  ["aileron", "Aileron", "A"], ["elevator", "Elevator", "E"],
  ["rudder", "Rudder", "R"], ["throttle", "Throttle", "T"],
];

function describeSystems(keyframe) {
  const parts = [];
  if (keyframe.flaps != null) parts.push(`flaps ${keyframe.flaps}`);
  if (keyframe.gear_down === true) parts.push("gear down");
  else if (keyframe.gear_down === false) parts.push("gear up");
  for (const [key, , short] of SYSTEMS_CHANNELS) {
    const value = keyframe[key];
    if (value == null) continue;
    const signed = key !== "throttle" && value >= 0 ? "+" : "";
    parts.push(`${short}${signed}${(value * 100).toFixed(key === "throttle" ? 0 : 1)}`);
  }
  return parts.length ? parts.join(" · ") : "no change";
}

function describeCamera(keyframe) {
  const join = keyframe.transition || "BLEND";
  const cut = join === "CUT" ? `cut ${keyframe.easing?.hold_s || 0}s · `
    : join === "SHOT" ? "new shot · " : "";
  if (keyframe.camera_type === "COCKPIT") {
    return `${cut}cockpit · ${describeCockpitView(keyframe.cockpit).toLowerCase()}`;
  }
  const position = keyframe.position;
  if (!position) return `${cut}no position`;
  if (position.frame === "WORLD") return `${cut}world point`;
  if (position.frame === "HORIZON") {
    const height = position.height_m === 0 ? "level"
      : `${position.height_m > 0 ? "+" : ""}${Math.round(position.height_m)} m`;
    return `${cut}orbit ${Math.round(position.radius_m)} m · az ${Math.round(position.azimuth_deg)}° · ${height}`;
  }
  const distance = Math.hypot(position.x_m, position.y_m, position.z_m);
  return `${cut}${Math.round(distance)} m from ${position.ref}`;
}

function select(index) {
  state.selected = index;
  // Jump the scrubber to a program camera key so the map/3D view shows it.
  if (isProgramMode() && state.track === "camera") {
    const key = state.program?.camera_keyframes?.[index];
    const time = key ? programCameraTime(key) : null;
    if (Number.isFinite(time)) {
      const scrub = $("scrub");
      if (scrub) scrub.value = String(time);
      showPlayhead(time);
    } else {
      // Time not solved yet — jump once the upcoming preview lands.
      state.scrubToCamera = true;
    }
  }
  renderKeyframeList();
  renderInspector();
  renderMap();
  if (typeof onMap2dSelect === "function") onMap2dSelect(index);
}

function field(label, control) {
  const row = document.createElement("div");
  row.className = "field";
  const caption = document.createElement("label");
  caption.textContent = label;
  row.append(caption, control);
  return row;
}

/** Read-only inspector value (solved path quantities, not authored). */
function plainValue(text) {
  const value = document.createElement("span");
  value.className = "plain";
  value.textContent = text;
  return value;
}

function renderProgramInspector(host) {
  if (state.selected === "origin") {
    const origin = state.program?.origin;
    const title = document.createElement("h3");
    title.textContent = "Start (origin)";
    host.appendChild(title);
    if (origin) {
      host.appendChild(field("Latitude", plainValue(origin.lat.toFixed(6))));
      host.appendChild(field("Longitude", plainValue(origin.lon.toFixed(6))));
      host.appendChild(field("Altitude", plainValue(`${Math.round(origin.alt_ft_msl)} ft`)));
    }
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = "Edit the start in the map popup, or drag the green start marker.";
    host.appendChild(note);
    return;
  }
  const segments = state.program?.segments || [];
  if (state.selected === null || !segments[state.selected]) {
    host.innerHTML = "<p class='hint'>Select Start or a segment.</p>";
    return;
  }
  const segment = segments[state.selected];
  const title = document.createElement("h3");
  title.textContent = `${segment.name || PROGRAM_KIND_LABEL[segment.kind] || segment.kind} `
    + `(${state.selected + 1} of ${segments.length})`;
  host.appendChild(title);
  host.appendChild(field("Kind", plainValue(PROGRAM_KIND_LABEL[segment.kind] || segment.kind)));
  if (segment.kind === "LINE_TO") {
    host.appendChild(field("Distance", plainValue(`${Math.round(segment.distance_m)} m`)));
    if (segment.heading_deg != null && !segment.inherit_direction) {
      host.appendChild(field("Heading", plainValue(`${segment.heading_deg.toFixed(1)}°`)));
    }
  } else if (segment.kind === "ARC") {
    host.appendChild(field("Side", plainValue(segment.side)));
    host.appendChild(field("Radius", plainValue(`${Math.round(segment.radius_m)} m`)));
    host.appendChild(field("Sweep", plainValue(`${segment.sweep_deg.toFixed(1)}°`)));
  } else if (segment.kind === "MOVE_TO") {
    host.appendChild(field("To", plainValue(
      `${segment.to.lat.toFixed(5)}, ${segment.to.lon.toFixed(5)}`)));
  } else if (segment.kind === "HERMITE") {
    host.appendChild(field("To", plainValue(
      `${segment.to.lat.toFixed(5)}, ${segment.to.lon.toFixed(5)}`)));
  } else if (segment.kind === "SPLINE") {
    host.appendChild(field("Control points",
      plainValue(String((segment.control_points || []).length))));
  }
  const note = document.createElement("p");
  note.className = "hint";
  note.textContent = "Edit this segment in the floating popup on the map.";
  host.appendChild(note);
}

function numberInput(value, onChange, step = 1) {
  const input = document.createElement("input");
  input.type = "number";
  input.step = step;
  // Not toFixed(2): that showed latitude as 40.70, and saving the field moved
  // the point by up to half a kilometre.
  input.value = String(Math.round(Number(value ?? 0) * 1e6) / 1e6);
  // Commit on blur/Enter only. A mid-solve inspector rebuild must not race
  // the caret (camera and waypoint fields share this control).
  const commit = () => {
    const next = parseFloat(input.value);
    if (!Number.isFinite(next)) return;
    onChange(next);
  };
  input.addEventListener("change", commit);
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    input.blur();
  });
  return input;
}

function selectInput(options, value, onChange) {
  const element = document.createElement("select");
  for (const [key, label] of options) {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = label;
    element.appendChild(option);
  }
  element.value = value;
  element.onchange = () => onChange(element.value);
  return element;
}

function optionalNumberInput(value, onChange, step = 1, placeholder = "hold") {
  const input = document.createElement("input");
  input.type = "number";
  input.step = step;
  input.placeholder = placeholder;
  input.value = value === null || value === undefined || Number.isNaN(Number(value))
    ? "" : String(value);
  input.onchange = () => {
    const raw = input.value.trim();
    onChange(raw === "" ? null : parseFloat(input.value));
  };
  return input;
}

function renderInspector() {
  const host = $("inspector");
  host.innerHTML = "";
  if (isProgramMode()) {
    if (state.track === "camera") {
      const keys = ensureProgramCameras();
      if (state.selected === null || !keys[state.selected]) {
        host.innerHTML = "<p class='hint'>Select a camera keyframe, or add one.</p>";
        return;
      }
      const title = document.createElement("h3");
      title.textContent = `Camera keyframe ${state.selected + 1} of ${keys.length}`;
      host.appendChild(title);
      renderProgramCameraAnchor(host, keys[state.selected]);
      renderCameraInspector(host, keys[state.selected]);
      return;
    }
    renderProgramInspector(host);
    return;
  }
  if (state.track === "controls") {
    renderControlsInspector(host);
    return;
  }
  if (state.track === "systems") {
    renderSystemsInspector(host);
    return;
  }
  if (state.track === "marks") {
    const marks = state.mapDoc?.markers || [];
    if (state.selected === null || !marks[state.selected]) {
      host.innerHTML = "<p class='hint'>Add a marker, or click Draw and click the map.</p>";
      return;
    }
    const title = document.createElement("h3");
    title.textContent = `Marker ${state.selected + 1} of ${marks.length}`;
    host.appendChild(title);
    renderMarkerInspector(host, marks[state.selected]);
    return;
  }
  const list = frames();
  if (state.track === "flight" && typeof flightSelectedCount === "function"
      && flightSelectedCount() > 1 && typeof renderBulkInspector === "function") {
    renderBulkInspector(host);
    return;
  }
  if (state.selected === null || !list[state.selected]) {
    host.innerHTML = "<p class='hint'>Select a keyframe.</p>";
    return;
  }
  const keyframe = list[state.selected];

  const title = document.createElement("h3");
  title.textContent = `${state.track === "flight" ? "Waypoint"
                      : state.track === "map" ? "Map camera"
                      : "Camera keyframe"} ` +
                      `${state.selected + 1} of ${list.length}`;
  host.appendChild(title);
  if (state.track === "flight" && typeof renderFlightIdentity === "function") {
    renderFlightIdentity(host, keyframe, state.selected);
  }

  host.appendChild(field("Time (s)", numberInput(keyframe.time_offset, (v) => {
    keyframe.time_offset = Math.max(0, v);
    state.doc.meta.duration_seconds = lastTime();
    touched();
  }, 0.1)));

  if (state.track === "flight") {
    const position = document.createElement("details");
    position.open = true;
    position.appendChild(Object.assign(document.createElement("summary"), { textContent: "Position" }));
    renderFlightInspector(position, keyframe);
    host.appendChild(position);
  } else if (state.track === "map") {
    renderMapCameraInspector(host, keyframe);
  } else {
    renderCameraInspector(host, keyframe);
  }

  if (state.track === "map") return;

  const easing = document.createElement("details");
  easing.appendChild(Object.assign(document.createElement("summary"), { textContent: "Easing" }));
  easing.appendChild(field("Ease in", numberInput(keyframe.easing.ease_in, (v) => {
    keyframe.easing.ease_in = Math.min(1, Math.max(0, v)); touched();
  }, 0.1)));
  easing.appendChild(field("Ease out", numberInput(keyframe.easing.ease_out, (v) => {
    keyframe.easing.ease_out = Math.min(1, Math.max(0, v)); touched();
  }, 0.1)));
  if (!(state.track === "camera" && (keyframe.transition || "BLEND") === "CUT")) {
    easing.appendChild(field("Hold (s)", numberInput(keyframe.easing.hold_s, (v) => {
      keyframe.easing.hold_s = Math.max(0, v); touched();
    }, 0.1)));
  }
  const note = document.createElement("p");
  note.className = "hint";
  note.textContent = "0 passes through at constant rate, 1 comes to a full stop.";
  easing.appendChild(note);
  host.appendChild(easing);
}

function renderSystemsInspector(host) {
  if (!state.doc.systems) state.doc.systems = [];
  const list = state.doc.systems;
  if (!list.length) {
    host.innerHTML = "<p class='hint'>No systems keyframes. Add one to set flaps, gear, "
      + "surfaces and throttle; otherwise the simulator keeps whatever the last take left.</p>";
    return;
  }
  if (state.selected === null || !list[state.selected]) {
    host.innerHTML = "<p class='hint'>Select a keyframe.</p>";
    return;
  }
  const keyframe = list[state.selected];
  const title = document.createElement("h3");
  title.textContent = `Systems keyframe ${state.selected + 1} of ${list.length}`;
  host.appendChild(title);

  host.appendChild(field("Time (s)", numberInput(keyframe.time_offset, (v) => {
    keyframe.time_offset = Math.max(0, v);
    state.doc.meta.duration_seconds = lastTime();
    touched();
  }, 0.1)));
  host.appendChild(field("Flaps", optionalNumberInput(keyframe.flaps, (v) => {
    keyframe.flaps = v === null ? null : Math.max(0, Math.round(v));
    touched();
  }, 1, "hold")));
  const gear = keyframe.gear_down === true ? "DOWN"
    : keyframe.gear_down === false ? "UP" : "";
  host.appendChild(field("Gear", selectInput(
    [["", "Hold"], ["UP", "Up"], ["DOWN", "Down"]],
    gear, (v) => {
      keyframe.gear_down = v === "DOWN" ? true : v === "UP" ? false : null;
      touched();
    })));
  for (const [key, label] of SYSTEMS_CHANNELS) {
    host.appendChild(field(`${label} %`, percentInput(keyframe[key], (v) => {
      keyframe[key] = v;
      touched();
    }, key === "throttle" ? 0 : -100)));
  }
  const note = document.createElement("p");
  note.className = "hint";
  note.textContent = "Playback holds flaps and gear until the next keyframe. Flaps is the "
    + "handle detent (0 = up). Surfaces and throttle are a record of a flown take; "
    + "blank keeps the last value. + aileron rolls right, + elevator is back stick, "
    + "+ rudder yaws right.";
  host.appendChild(note);
}

let geoLookupToken = 0;

// Every edit re-renders the inspector, so a slow answer for the coordinates
// the operator has already moved off must not land in the new panel.
function showPlaceLabel(target, lat, lon) {
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    target.textContent = "";
    return;
  }
  const token = ++geoLookupToken;
  api("GET", `/api/geocode/reverse?lat=${lat}&lon=${lon}`)
    .then((hit) => {
      if (token !== geoLookupToken) return;
      if (hit && hit.label) target.textContent = hit.label;
    })
    .catch(() => { /* a name is a convenience; the coordinates still stand */ });
}

// Place-search popup used by every lat/lon control. Picking one result calls
// onPick; Cancel / Escape selects none and leaves coordinates alone.
function openGeoPlacePicker({ onPick } = {}) {
  const dialog = document.getElementById("geo-picker-dialog");
  const form = document.getElementById("geo-picker-form");
  const input = document.getElementById("geo-picker-q");
  const find = document.getElementById("geo-picker-find");
  const status = document.getElementById("geo-picker-status");
  const hits = document.getElementById("geo-picker-hits");
  if (!dialog || !input || !find) return;

  input.value = "";
  status.textContent = "";
  hits.innerHTML = "";
  hits.hidden = true;

  async function runSearch(event) {
    if (event) event.preventDefault();
    const q = input.value.trim();
    if (q.length < 2) {
      status.textContent = "Type a place name or address.";
      return;
    }
    status.textContent = "Looking up…";
    hits.hidden = true;
    hits.innerHTML = "";
    try {
      let viewbox = "";
      if (typeof map !== "undefined" && map?.getBounds) {
        const bounds = map.getBounds();
        viewbox = [
          bounds.getWest(), bounds.getNorth(), bounds.getEast(), bounds.getSouth(),
        ].join(",");
      }
      const data = await api(
        "GET",
        `/api/geocode?q=${encodeURIComponent(q)}`
          + (viewbox ? `&viewbox=${encodeURIComponent(viewbox)}` : ""),
      );
      const results = data.results || [];
      if (!results.length) {
        status.textContent = "No places found.";
        return;
      }
      status.textContent = `${results.length} place${results.length === 1 ? "" : "s"} — pick one`;
      for (const hit of results) {
        const pick = document.createElement("button");
        pick.type = "button";
        pick.textContent = hit.label;
        pick.onclick = () => {
          dialog.close();
          if (typeof onPick === "function") onPick(hit);
        };
        hits.appendChild(pick);
      }
      hits.hidden = false;
    } catch (error) {
      status.textContent = error.message || "Lookup failed.";
    }
  }

  find.onclick = runSearch;
  form.onsubmit = runSearch;
  const cancel = document.getElementById("geo-picker-cancel");
  if (cancel) cancel.onclick = () => dialog.close();
  if (!dialog.open) dialog.showModal();
  input.focus();
}

// Small ⌖ control next to a lat (or lat/lon pair) that opens the place picker.
// `target` must expose writable `.lat` / `.lon`. Optional `afterPick(hit)`.
function geoPickButton(target, afterPick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "geo-pick";
  button.textContent = "\u2316";
  button.title = "Look up a place and set latitude / longitude";
  button.setAttribute("aria-label", "Look up a place");
  button.onclick = (event) => {
    event.preventDefault();
    event.stopPropagation();
    openGeoPlacePicker({
      onPick: (hit) => {
        target.lat = hit.lat;
        target.lon = hit.lon;
        if (typeof map !== "undefined" && map?.setView) {
          map.setView([hit.lat, hit.lon], Math.max(map.getZoom(), 13), { animate: false });
        }
        if (typeof afterPick === "function") afterPick(hit);
      },
    });
  };
  return button;
}

// Latitude row with a place-lookup icon; Longitude stays a plain field.
function fieldLatLon(host, target, { onChange, latLabel = "Latitude", lonLabel = "Longitude" } = {}) {
  const latControl = document.createElement("div");
  latControl.style.display = "flex";
  latControl.style.gap = "6px";
  latControl.style.alignItems = "center";
  latControl.style.flex = "1";
  latControl.style.minWidth = "0";
  const latInput = numberInput(target.lat, (v) => {
    target.lat = v;
    if (onChange) onChange();
  }, 0.0001);
  latInput.style.flex = "1";
  latInput.style.minWidth = "0";
  latControl.append(latInput, geoPickButton(target, () => {
    if (onChange) onChange();
  }));
  host.appendChild(field(latLabel, latControl));
  host.appendChild(field(lonLabel, numberInput(target.lon, (v) => {
    target.lon = v;
    if (onChange) onChange();
  }, 0.0001)));
}

// Kept for call sites that still want the old inline block; prefer fieldLatLon.
function renderPlaceSearch(host, target) {
  const row = document.createElement("div");
  row.className = "geo-search";
  const status = document.createElement("p");
  status.className = "hint geo-place";
  row.appendChild(field("Place", geoPickButton(target, () => {
    showPlaceLabel(status, target.lat, target.lon);
    touched();
  })));
  row.appendChild(status);
  host.appendChild(row);
  showPlaceLabel(status, target.lat, target.lon);
}

window.openGeoPlacePicker = openGeoPlacePicker;
window.geoPickButton = geoPickButton;
window.fieldLatLon = fieldLatLon;

function renderFlightInspector(host, keyframe) {
  if (typeof renderPathInspector === "function") renderPathInspector(host, keyframe);
  host.appendChild(field("Altitude (ft)", numberInput(keyframe.alt_ft_msl, (v) => {
    keyframe.alt_ft_msl = v; touched();
  }, 10)));
  fieldLatLon(host, keyframe, { onChange: () => touched() });
  host.appendChild(field("On ground", selectInput(
    [["NO", "No"], ["YES", "Yes"]],
    keyframe.on_ground ? "YES" : "NO", (v) => { keyframe.on_ground = v === "YES"; touched(); })));
  const groundNote = document.createElement("p");
  groundNote.className = "hint";
  groundNote.textContent = "Yes puts the wheels on the simulator's own terrain for the leg "
    + "after this waypoint, whatever the altitude above says. Use it from touchdown to "
    + "lift-off; the clamp blends in over the second before a Yes and out after the last one.";
  host.appendChild(groundNote);

  // Switching to Manual seeds the solved value at this instant, so the angle
  // does not jump the moment the operator takes control of it.
  const solved = poseAt(keyframe.time_offset);
  const seed = { heading: solved?.heading ?? 0, pitch: solved?.pitch ?? 0,
                 bank: solved?.bank ?? 0 };

  const solvedGroup = document.createElement("div");
  solvedGroup.className = "group";
  solvedGroup.appendChild(field("Speed", plainValue(
    solved && Number.isFinite(solved.speed_kt) ? `${Math.round(solved.speed_kt)} kt` : "—")));
  solvedGroup.appendChild(field("Track", plainValue(
    solved && Number.isFinite(solved.heading) ? `${solved.heading.toFixed(1)}°` : "—")));
  solvedGroup.appendChild(field("Bank", plainValue(
    solved && Number.isFinite(solved.bank) ? `${solved.bank.toFixed(1)}°` : "—")));
  const solvedNote = document.createElement("p");
  solvedNote.className = "hint";
  solvedNote.textContent = "From the path at this waypoint (distance ÷ time, and the "
    + "solver’s track and bank). Not editable — change times or positions to change them.";
  solvedGroup.appendChild(solvedNote);
  host.appendChild(solvedGroup);

  const group = document.createElement("div");
  group.className = "group";
  for (const which of ["heading", "pitch", "bank"]) {
    group.appendChild(field(`${which[0].toUpperCase()}${which.slice(1)} pin`,
      selectInput([["AUTO", "Auto"], ["MANUAL", "Manual"]], keyframe[which].mode, (mode) => {
        keyframe[which] = mode === "AUTO"
          ? { mode: "AUTO" }
          : { mode: "MANUAL", deg: Math.round(seed[which] * 10) / 10 };
        touched();
      })));
    if (keyframe[which].mode === "MANUAL") {
      group.appendChild(field("degrees", numberInput(keyframe[which].deg, (v) => {
        keyframe[which].deg = v; touched();
      }, 0.5)));
    }
  }
  const note = document.createElement("p");
  note.className = "hint";
  note.textContent = "Auto uses the solved angles above. Manual pins a value here "
    + "and the solver splines smoothly through every keyframe.";
  group.appendChild(note);
  host.appendChild(group);
}

// ---------------------------------------------------------------- cockpit views

// The sim's four pilot presets. Instrument and quickview cameras are numbered
// per aircraft; the operator names them once (state.views) and the editor
// shows those names.
const COCKPIT_PRESETS = [
  ["PILOT", "Pilot"], ["CLOSE", "Close"], ["LANDING", "Landing"], ["COPILOT", "Copilot"],
];
const NUMBERED_VIEWS = [["INSTRUMENT", "Instrument"], ["QUICKVIEW", "Quickview"],
                        ["CUSTOM", "Custom"]];

function isNumberedView(view) {
  return NUMBERED_VIEWS.some(([value]) => value === view);
}

/** What the sim saved in a custom slot (seat, direction), if we could read it. */
function customCameraInfo(index) {
  return (state.views?.custom_cameras || []).find((camera) => camera.slot === index) || null;
}

/** The select's value: "PILOT", or "INSTRUMENT:3" for a numbered camera. */
function cockpitChoice(cockpit) {
  const view = cockpit?.view || "PILOT";
  return isNumberedView(view) ? `${view}:${cockpit.index ?? 0}` : view;
}

function applyCockpitChoice(cockpit, choice) {
  const [view, index] = choice.split(":");
  cockpit.view = view;
  cockpit.index = index === undefined ? 0 : parseInt(index, 10);
}

function cockpitViewName(view, index) {
  const names = state.views?.[view.toLowerCase()] || {};
  const base = NUMBERED_VIEWS.find(([value]) => value === view)[1];
  const name = names[String(index)];
  if (name) return `${base} ${index} · ${name}`;
  const saved = view === "CUSTOM" ? customCameraInfo(index) : null;
  return saved ? `${base} ${index} · ${saved.label}` : `${base} ${index}`;
}

/** Every view the dropdown offers: the presets, then each numbered camera
 *  the aircraft has (or has a name for), plus whatever this keyframe uses. */
function cockpitViewOptions(current) {
  const options = [...COCKPIT_PRESETS];
  for (const [view] of NUMBERED_VIEWS) {
    const names = state.views?.[view.toLowerCase()] || {};
    const indices = new Set(Object.keys(names).map(Number));
    const count = state.views?.[`${view.toLowerCase()}_count`];
    if (Number.isFinite(count)) for (let i = 0; i < count; i++) indices.add(i);
    // Custom 0–9 are the sim's Alt+n slots, even when this aircraft has none
    // saved yet. Listing only cameras.cfg hid 1–9 on planes with no file.
    if (view === "CUSTOM") for (let i = 0; i < 10; i++) indices.add(i);
    if (current?.view === view) indices.add(current.index ?? 0);
    if (!indices.size && view !== "CUSTOM") indices.add(0);
    for (const i of [...indices].sort((a, b) => a - b)) {
      options.push([`${view}:${i}`, cockpitViewName(view, i)]);
    }
  }
  return options;
}

function describeCockpitView(cockpit) {
  const view = cockpit?.view || "PILOT";
  const label = isNumberedView(view) ? cockpitViewName(view, cockpit.index ?? 0)
    : (COCKPIT_PRESETS.find(([value]) => value === view) || [view, view])[1];
  const zoom = cockpit?.zoom_pct === null || cockpit?.zoom_pct === undefined
    ? "" : ` · zoom ${cockpit.zoom_pct}%`;
  return label + zoom;
}

async function loadCockpitViews(refresh = false) {
  try {
    state.views = await api("GET", `/api/cockpit-views${refresh ? "?refresh=1" : ""}`);
  } catch (_) {
    state.views = null;
  }
  if (state.track === "camera") {
    renderKeyframeList();
    renderInspector();
  }
  return state.views;
}

function renderViewsDialog() {
  const views = state.views;
  const dialog = $("views-dialog");
  const known = Boolean(views && views.aircraft);
  $("views-aircraft").textContent = known ? views.aircraft
    : "No aircraft known. Connect to the simulator with the aircraft loaded.";
  $("views-live").textContent = views?.live
    ? "" : known ? "Counts shown are from the saved names; the sim is not reporting this aircraft now." : "";
  dialog.querySelector("button[value=save]").disabled = !known;
  for (const [view, base] of NUMBERED_VIEWS) {
    const kind = view.toLowerCase();
    const host = $(`views-${kind}`);
    host.innerHTML = "";
    const names = views?.[kind] || {};
    const custom = view === "CUSTOM";
    // Custom slots are fixed at 0..9 by the sim; the others grow as needed.
    const count = custom ? 10 : views?.[`${kind}_count`];
    const highest = Math.max(Number.isFinite(count) ? count - 1 : -1,
                             ...Object.keys(names).map(Number), 1);
    const rows = parseInt(host.dataset.rows || "0", 10);
    const total = custom ? 10 : Math.max(highest + 1, rows);
    host.dataset.rows = String(total);
    for (let i = 0; i < total; i++) {
      const row = document.createElement("label");
      row.innerHTML = `<span class="views-index">${base} ${i}</span>`;
      const input = document.createElement("input");
      input.type = "text";
      input.dataset.index = String(i);
      input.value = names[String(i)] || "";
      const saved = custom ? customCameraInfo(i) : null;
      input.placeholder = saved ? saved.label
        : custom ? "empty slot"
        : Number.isFinite(count) && i >= count ? "beyond what the sim reports" : "name";
      row.appendChild(input);
      host.appendChild(row);
    }
  }
}

function collectViewNames(kind) {
  const names = {};
  for (const input of $(`views-${kind}`).querySelectorAll("input")) {
    if (input.value.trim()) names[input.dataset.index] = input.value.trim();
  }
  return names;
}

async function openViewsDialog() {
  const dialog = $("views-dialog");
  for (const [view] of NUMBERED_VIEWS) $(`views-${view.toLowerCase()}`).dataset.rows = "0";
  $("views-aircraft").textContent = "Reading the aircraft…";
  dialog.showModal();
  await loadCockpitViews(true);
  renderViewsDialog();
}

function defaultWorldPoint() {
  if (isProgramMode() && state.program?.origin) {
    return {
      lat: state.program.origin.lat,
      lon: state.program.origin.lon,
      alt_ft_msl: state.program.origin.alt_ft_msl ?? 2500,
    };
  }
  const key = state.doc?.flight_keyframes?.[0];
  if (key) {
    return { lat: key.lat, lon: key.lon, alt_ft_msl: key.alt_ft_msl ?? 2500 };
  }
  return { lat: 0, lon: 0, alt_ft_msl: 2500 };
}

function renderProgramCameraAnchor(host, keyframe) {
  ensureSegmentIds(state.program);
  if (!keyframe.anchor) {
    keyframe.anchor = defaultProgramCameraAnchor() || { segment_id: "", at: 0.5 };
  }
  const segments = state.program.segments || [];
  const kindLabel = (typeof ProgramFields !== "undefined" && ProgramFields.KIND_LABEL)
    || PROGRAM_KIND_LABEL;
  const options = segments.map((seg, index) => [
    seg.id,
    `${index + 1}. ${seg.name || kindLabel[seg.kind] || seg.kind}`,
  ]);
  if (!options.length) {
    host.appendChild(Object.assign(document.createElement("p"), {
      className: "hint",
      textContent: "No segments to anchor to.",
    }));
    return;
  }
  if (!options.some(([id]) => id === keyframe.anchor.segment_id)) {
    keyframe.anchor.segment_id = options[0][0];
  }
  host.appendChild(field("Segment", selectInput(options, keyframe.anchor.segment_id, (v) => {
    keyframe.anchor.segment_id = v;
    state.scrubToCamera = true;
    touched();
  })));
  host.appendChild(field("Along segment", numberInput(keyframe.anchor.at, (v) => {
    keyframe.anchor.at = Math.min(1, Math.max(0, v));
    state.scrubToCamera = true;
    touched();
  }, 0.01)));
  const time = programCameraTime(keyframe);
  host.appendChild(field("Time (derived)", plainValue(
    Number.isFinite(time) ? `${time.toFixed(2)} s` : "—")));
  const hint = document.createElement("p");
  hint.className = "hint";
  hint.textContent = "0 is the segment start, 1 is its end. One key applies for "
    + "the whole flight (Horizon/Body follow the aircraft). Time is derived "
    + "from the solved path, so it moves if you retime the segment.";
  host.appendChild(hint);
}

function renderCameraInspector(host, keyframe) {
  host.appendChild(field("Type", selectInput(
    [["CINEMATIC", "Cinematic"], ["COCKPIT", "Cockpit"]],
    keyframe.camera_type, (v) => { keyframe.camera_type = v; touched(); })));
  if (!keyframe.transition) keyframe.transition = "BLEND";
  host.appendChild(field("Join", selectInput(
    [["BLEND", "Blend into path"],
     ["SHOT", "Cut to new shot"],
     ["CUT", "Cut away, then snap back"]],
    keyframe.transition, (v) => {
      keyframe.transition = v;
      if (v === "CUT" && !(keyframe.easing.hold_s > 0)) keyframe.easing.hold_s = 3;
      touched();
    })));
  if (keyframe.transition === "CUT") {
    host.appendChild(field("Cut for (s)", numberInput(keyframe.easing.hold_s, (v) => {
      keyframe.easing.hold_s = Math.max(0, v); touched();
    }, 0.1)));
    const cutHint = document.createElement("p");
    cutHint.className = "hint";
    cutHint.textContent = "Jumps here at Time, stays this long, then snaps back to the "
      + "Blend path at Time + Cut for. Neighbouring Blend keys keep interpolating "
      + "underneath. A Blend key in between still pulls the path.";
    host.appendChild(cutHint);
  } else if (keyframe.transition === "SHOT") {
    const shotHint = document.createElement("p");
    shotHint.className = "hint";
    shotHint.textContent = "Hard cut to this pose, then Blend keys after it interpolate "
      + "from here. Use the same Time as the previous shot’s last Blend key — at "
      + "that instant the new shot wins, so there is no hold on the old end.";
    host.appendChild(shotHint);
  }

  if (keyframe.camera_type === "CINEMATIC") {
    const position = keyframe.position || { frame: "BODY", ref: "CG", x_m: 0, y_m: 0, z_m: 0 };
    keyframe.position = position;
    host.appendChild(field("Frame", selectInput(
      [["BODY", "Relative to aircraft"], ["HORIZON", "Level orbit"],
       ["WORLD", "Fixed world point"]],
      position.frame, (v) => {
        keyframe.position = v === "BODY"
          ? { frame: "BODY", ref: "CG", x_m: -70, y_m: 25, z_m: -130 }
          : v === "HORIZON"
            ? { frame: "HORIZON", azimuth_deg: 0, radius_m: 80, height_m: 15 }
            : { frame: "WORLD", ...defaultWorldPoint() };
        touched();
      })));

    if (position.frame === "BODY") {
      host.appendChild(field("Anchor", selectInput(
        [["CG", "Centre of gravity"], ["NOSE", "Nose"], ["TAIL", "Tail"], ["COCKPIT", "Cockpit"]],
        position.ref, (v) => { position.ref = v; touched(); })));
      host.appendChild(field("Right (m)", numberInput(position.x_m, (v) => {
        position.x_m = v; touched(); }, 5)));
      host.appendChild(field("Up (m)", numberInput(position.y_m, (v) => {
        position.y_m = v; touched(); }, 5)));
      host.appendChild(field("Forward (m)", numberInput(position.z_m, (v) => {
        position.z_m = v; touched(); }, 5)));
    } else if (position.frame === "HORIZON") {
      host.appendChild(field("Azimuth (°)", numberInput(position.azimuth_deg, (v) => {
        position.azimuth_deg = v; touched(); }, 5)));
      host.appendChild(field("Radius (m)", numberInput(position.radius_m, (v) => {
        position.radius_m = Math.max(0.1, v); touched(); }, 5)));
      host.appendChild(field("Height (m)", numberInput(position.height_m, (v) => {
        position.height_m = v; touched(); }, 1)));
    } else {
      fieldLatLon(host, position, { onChange: () => touched() });
      host.appendChild(field("Altitude (ft)", numberInput(position.alt_ft_msl, (v) => {
        position.alt_ft_msl = v; touched(); }, 10)));
    }

    const aim = document.createElement("div");
    aim.className = "group";
    aim.appendChild(field("Look at", selectInput(
      [["AIRCRAFT_POINT", "The aircraft"], ["AIRCRAFT_OFFSET", "Offset from aircraft"],
       ["WORLD_POINT", "A world point"], ["FREE", "Fixed angles"]],
      keyframe.look_at.mode, (v) => {
        if (v === "AIRCRAFT_POINT") keyframe.look_at = { mode: "AIRCRAFT_POINT", ref: "CG" };
        else if (v === "AIRCRAFT_OFFSET") keyframe.look_at = {
          mode: "AIRCRAFT_OFFSET", x_m: -15, y_m: 0, z_m: 0 };
        else if (v === "WORLD_POINT") keyframe.look_at = {
          mode: "WORLD_POINT", ...defaultWorldPoint() };
        else keyframe.look_at = { mode: "FREE", pitch_deg: 0, heading_deg: 0 };
        touched();
      })));
    if (keyframe.look_at.mode === "AIRCRAFT_POINT") {
      aim.appendChild(field("Point", selectInput(
        [["CG", "Centre of gravity"], ["NOSE", "Nose"], ["TAIL", "Tail"], ["COCKPIT", "Cockpit"]],
        keyframe.look_at.ref, (v) => { keyframe.look_at.ref = v; touched(); })));
    } else if (keyframe.look_at.mode === "AIRCRAFT_OFFSET") {
      aim.appendChild(field("Right (m)", numberInput(keyframe.look_at.x_m, (v) => {
        keyframe.look_at.x_m = v; touched(); }, 1)));
      aim.appendChild(field("Height (m)", numberInput(keyframe.look_at.y_m, (v) => {
        keyframe.look_at.y_m = v; touched(); }, 1)));
      aim.appendChild(field("Forward (m)", numberInput(keyframe.look_at.z_m, (v) => {
        keyframe.look_at.z_m = v; touched(); }, 1)));
    } else if (keyframe.look_at.mode === "WORLD_POINT") {
      fieldLatLon(aim, keyframe.look_at, { onChange: () => touched() });
      aim.appendChild(field("Altitude (ft)", numberInput(keyframe.look_at.alt_ft_msl, (v) => {
        keyframe.look_at.alt_ft_msl = v; touched(); }, 10)));
    } else {
      aim.appendChild(field("Pitch (deg)", numberInput(keyframe.look_at.pitch_deg, (v) => {
        keyframe.look_at.pitch_deg = v; touched(); }, 1)));
      aim.appendChild(field("Heading (deg)", numberInput(keyframe.look_at.heading_deg, (v) => {
        keyframe.look_at.heading_deg = v; touched(); }, 1)));
    }
    aim.appendChild(field("Up vector", selectInput(
      [["WORLD_UP", "World up"], ["AIRCRAFT_UP", "Aircraft up"]],
      keyframe.up.mode, (v) => { keyframe.up.mode = v; touched(); })));
    host.appendChild(aim);
    const cineHint = document.createElement("p");
    cineHint.className = "hint";
    cineHint.textContent = keyframe.look_at.mode === "FREE"
      ? "Fixed angles aim the camera in those pitch/heading degrees (any heading, "
        + "including 180 and negatives); they do not point it at the aircraft. "
        + "Use “The aircraft” if you want the airframe in frame."
      : keyframe.look_at.mode === "AIRCRAFT_OFFSET"
        ? "Aims at a ghost point that rides beside the aircraft in the level plane "
          + "(right / forward follow heading, height is world-up). Negative right is "
          + "left of the jet. About 15 m left at 80 m and 60° FOV sits near a third."
      : position.frame === "HORIZON"
        ? "Level orbit: azimuth 0 is aft, 90 the right wing. Height is world-up "
          + "from the CG and does not roll with the aircraft."
        : "Position is metres from the anchor (right / up / forward). Look-at aims the camera.";
    host.appendChild(cineHint);
  } else {
    const cockpit = keyframe.cockpit || { view: "PILOT", index: 0, zoom_pct: null };
    keyframe.cockpit = cockpit;
    const view = document.createElement("div");
    view.className = "group";
    view.appendChild(field("View", selectInput(cockpitViewOptions(cockpit), cockpitChoice(cockpit),
      (v) => { applyCockpitChoice(cockpit, v); touched(); })));
    const countKnown = Number.isFinite(state.views?.[`${cockpit.view.toLowerCase()}_count`]);
    if (isNumberedView(cockpit.view) && !countKnown) {
      // Without the sim to say how many there are, the number can be typed.
      view.appendChild(field("Number", numberInput(cockpit.index, (v) => {
        cockpit.index = Math.max(0, Math.round(v)); touched();
      }, 1)));
    }
    const nameButton = document.createElement("button");
    nameButton.type = "button";
    nameButton.textContent = "Name views…";
    nameButton.title = "Give this aircraft's instrument and quickview cameras names";
    nameButton.onclick = openViewsDialog;
    const aircraft = state.views?.aircraft;
    view.appendChild(field(aircraft ? aircraft.slice(0, 28) : "Aircraft", nameButton));
    const zoom = document.createElement("input");
    zoom.type = "number";
    zoom.step = 5;
    zoom.min = 0;
    zoom.max = 100;
    zoom.placeholder = "sim default";
    zoom.value = cockpit.zoom_pct ?? "";
    zoom.onchange = () => {
      cockpit.zoom_pct = zoom.value === "" ? null : parseFloat(zoom.value);
      touched();
    };
    view.appendChild(field("Zoom (%)", zoom));
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = cockpit.view === "CUSTOM"
      ? "Custom cameras are the views you saved in the sim with Ctrl+Alt+0–9, on this "
        + "aircraft only: changing planes (or never saving on this one) leaves the slot "
        + "empty, and Alt+n then keeps whatever view is already showing. Seat, head "
        + "direction and zoom all come from the save. The simulator must be the active "
        + "window when the keyframe is reached."
      : "The sim's cockpit presets: Landing is the one pitched down over the nose. "
        + "Instrument and Quickview cameras are the aircraft's own, numbered from 0. "
        + "For any other angle, save a Custom camera in the sim and pick it here.";
    view.appendChild(note);
    host.appendChild(view);
    return;
  }

  const fov = document.createElement("input");
  fov.type = "number";
  fov.step = 1;
  fov.placeholder = "sim default";
  fov.value = keyframe.fov_deg ?? "";
  fov.onchange = () => {
    keyframe.fov_deg = fov.value === "" ? null : parseFloat(fov.value);
    touched();
  };
  host.appendChild(field("Field of view", fov));
}

function renderDiagnostics() {
  const host = $("diagnostics");
  host.innerHTML = "";
  if (!state.diagnostics.length) {
    host.innerHTML = "<p class='hint'>No problems found.</p>";
    return;
  }
  for (const item of state.diagnostics) {
    const box = document.createElement("div");
    box.className = `diag ${item.severity}`;
    box.textContent = item.message;
    if (item.at !== null && item.at !== undefined) {
      const link = document.createElement("span");
      link.className = "where";
      link.textContent = ` at ${item.at.toFixed(1)}s`;
      link.onclick = () => scrubTo(item.at);
      box.appendChild(link);
    }
    host.appendChild(box);
  }
}

const AUTO_BANK_DEFAULTS = { max_deg: 30, roll_rate_deg_s: 5, smoothing_s: 6 };

function autoBank() {
  const have = state.doc?.meta.auto_bank || {};
  return {
    max_deg: have.max_deg ?? AUTO_BANK_DEFAULTS.max_deg,
    roll_rate_deg_s: have.roll_rate_deg_s ?? AUTO_BANK_DEFAULTS.roll_rate_deg_s,
    smoothing_s: have.smoothing_s ?? AUTO_BANK_DEFAULTS.smoothing_s,
  };
}

function writeAutoBank(patch) {
  state.doc.meta.auto_bank = { ...autoBank(), ...patch };
  touched();
}

function renderMeta() {
  if (!state.doc && !state.program) return;
  if ($("meta-entity") && state.doc?.meta) $("meta-entity").value = state.doc.meta.entity;
  const duration = $("meta-duration");
  if (document.activeElement !== duration) duration.value = Math.round(lastTime());
  if (duration) duration.disabled = isProgramMode();
  const clock = $("meta-time-of-day");
  if (clock && document.activeElement !== clock) {
    clock.value = state.doc?.meta?.time_of_day || "";
  }
  if (!isProgramMode()) {
    const law = autoBank();
    const fields = [
      ["auto-bank-max", law.max_deg],
      ["auto-bank-roll", law.roll_rate_deg_s],
      ["auto-bank-smooth", law.smoothing_s],
    ];
    for (const [id, value] of fields) {
      const input = $(id);
      if (input && document.activeElement !== input) input.value = value;
    }
  }
  $("btn-save").textContent = state.dirty ? "Save *" : "Save";
}

// ---------------------------------------------------------------- profile

// `span` is the smallest range each trace is allowed to fill. Without it a
// four-knot speed variation autoscales into a rollercoaster and the operator
// reads a steady cruise as a problem.
const SERIES = [
  { key: "alt_ft", label: "altitude ft", colour: "#4ea1ff", span: 500 },
  { key: "speed_kt", label: "speed kt", colour: "#7ee29a", span: 60 },
  { key: "bank", label: "bank deg", colour: "#ffa23e", span: 30 },
];

const PROFILE = { start: 0, end: null, drag: null };
const PROFILE_PAD = { left: 8, right: 8, top: 14, bottom: 16 };
const PROFILE_MIN_SPAN = 2;

function profileDuration() {
  return state.preview?.duration || lastTime() || 1;
}

function profileWindow() {
  const duration = profileDuration();
  const start = Math.max(0, PROFILE.start);
  const end = PROFILE.end == null ? duration : Math.min(duration, Math.max(start, PROFILE.end));
  if (end - start < 1e-6) return { start: 0, end: duration, duration, full: true };
  const full = start <= 1e-6 && end >= duration - 1e-3;
  return { start, end, duration, full };
}

function setProfileWindow(start, end) {
  const duration = profileDuration();
  let left = Math.max(0, Math.min(start, end));
  let right = Math.min(duration, Math.max(start, end));
  const minSpan = Math.min(PROFILE_MIN_SPAN, duration);
  if (right - left < minSpan) {
    const mid = (left + right) / 2;
    left = Math.max(0, mid - minSpan / 2);
    right = Math.min(duration, left + minSpan);
    left = Math.max(0, right - minSpan);
  }
  const full = left <= 1e-6 && right >= duration - 1e-3;
  PROFILE.start = full ? 0 : left;
  PROFILE.end = full ? null : right;
  renderProfileTools();
  renderProfile();
}

function resetProfileWindow() {
  PROFILE.start = 0;
  PROFILE.end = null;
  PROFILE.drag = null;
  renderProfileTools();
}

function zoomProfile(factor, around) {
  const { start, end } = profileWindow();
  const span = end - start;
  const pivot = Number.isFinite(around) ? around : start + span / 2;
  const next = span / factor;
  const left = span > 1e-9 ? (pivot - start) / span : 0.5;
  setProfileWindow(pivot - next * left, pivot + next * (1 - left));
}

function profileLayout() {
  const canvas = $("profile");
  const width = canvas.clientWidth;
  const height = 150;
  const pad = PROFILE_PAD;
  return {
    canvas, width, height, pad,
    plotWidth: width - pad.left - pad.right,
    plotHeight: height - pad.top - pad.bottom,
  };
}

function timeFromProfileX(clientX) {
  const { canvas, pad, plotWidth } = profileLayout();
  const rect = canvas.getBoundingClientRect();
  const { start, end } = profileWindow();
  const u = (clientX - rect.left - pad.left) / Math.max(1, plotWidth);
  return start + Math.min(1, Math.max(0, u)) * (end - start);
}

function renderProfileTools() {
  const range = $("profile-range");
  const { start, end, duration, full } = profileWindow();
  if (range) {
    range.textContent = full
      ? `0–${duration.toFixed(0)} s`
      : `${start.toFixed(1)}–${end.toFixed(1)} s`;
  }
  if ($("profile-out")) $("profile-out").disabled = full;
  if ($("profile-fit")) $("profile-fit").disabled = full;
  const { from_s, to_s } = playSegment();
  if ($("profile-seg")) {
    $("profile-seg").disabled = from_s == null && to_s == null;
  }
  const canvas = $("profile");
  if (canvas) canvas.classList.toggle("zoomed", !full);
}

function renderProfile(playhead = null) {
  const canvas = $("profile");
  const ratio = window.devicePixelRatio || 1;
  const { width, height, pad, plotWidth, plotHeight } = profileLayout();
  if (canvas.width !== width * ratio) {
    canvas.width = width * ratio;
    canvas.height = height * ratio;
  }
  const g = canvas.getContext("2d");
  g.setTransform(ratio, 0, 0, ratio, 0, 0);
  g.clearRect(0, 0, width, height);

  const rows = state.preview?.samples || [];
  if (rows.length < 2) {
    renderProfileTools();
    return;
  }
  const { start, end, duration } = profileWindow();
  const span = Math.max(1e-6, end - start);
  const x = (t) => pad.left + ((t - start) / span) * plotWidth;
  const visible = rows.filter((row) => row.t >= start && row.t <= end);

  g.save();
  g.beginPath();
  g.rect(pad.left, pad.top, plotWidth, plotHeight);
  g.clip();

  g.strokeStyle = "#2a303c";
  g.lineWidth = 1;
  // Program paths have no waypoint doc; tick marks come from samples only.
  for (const keyframe of state.doc?.flight_keyframes || []) {
    if (keyframe.time_offset < start || keyframe.time_offset > end) continue;
    g.beginPath();
    g.moveTo(x(keyframe.time_offset), pad.top);
    g.lineTo(x(keyframe.time_offset), pad.top + plotHeight);
    g.stroke();
  }
  g.strokeStyle = "#7ee29a";
  g.setLineDash([2, 3]);
  for (const keyframe of state.doc?.systems || []) {
    if (keyframe.time_offset < start || keyframe.time_offset > end) continue;
    g.beginPath();
    g.moveTo(x(keyframe.time_offset), pad.top);
    g.lineTo(x(keyframe.time_offset), pad.top + plotHeight);
    g.stroke();
  }
  g.setLineDash([]);

  const captions = [];
  SERIES.forEach((series, index) => {
    const source = visible.length ? visible : rows;
    const values = source.map((row) => row[series.key]);
    let low = Math.min(...values);
    let high = Math.max(...values);
    if (high - low < series.span) {
      const middle = (low + high) / 2;
      low = middle - series.span / 2;
      high = middle + series.span / 2;
    }
    g.strokeStyle = series.colour;
    g.lineWidth = 1.5;
    g.beginPath();
    rows.forEach((row, i) => {
      const py = pad.top + plotHeight - ((row[series.key] - low) / (high - low)) * plotHeight;
      i === 0 ? g.moveTo(x(row.t), py) : g.lineTo(x(row.t), py);
    });
    g.stroke();
    captions.push({
      colour: series.colour,
      text: `${series.label}  ${Math.min(...values).toFixed(0)}–${Math.max(...values).toFixed(0)}`,
      x: pad.left + index * 150,
    });
  });

  const { from_s, to_s } = playSegment();
  if (from_s !== null || to_s !== null) {
    const first = Math.max(start, from_s ?? 0);
    const last = Math.min(end, to_s ?? duration);
    g.fillStyle = "rgba(11, 16, 23, 0.6)";
    g.fillRect(pad.left, pad.top, Math.max(0, x(first) - pad.left), plotHeight);
    g.fillRect(x(last), pad.top, Math.max(0, pad.left + plotWidth - x(last)), plotHeight);
  }

  const at = playhead ?? (state.playback.state === "PLAYING" ? state.playback.elapsed
    : state.playback.state === "PAUSED" ? parseFloat($("scrub").value) : null);
  if (at !== null && at >= start && at <= end) {
    g.strokeStyle = "#fff";
    g.lineWidth = 1;
    g.beginPath();
    g.moveTo(x(at), pad.top - 4);
    g.lineTo(x(at), pad.top + plotHeight);
    g.stroke();
  }
  g.restore();

  g.font = "11px system-ui";
  for (const caption of captions) {
    g.fillStyle = caption.colour;
    g.fillText(caption.text, caption.x, 11);
  }

  g.fillStyle = "#8b93a3";
  g.font = "10px system-ui";
  const leftLabel = start < 10 || !profileWindow().full ? `${start.toFixed(1)}s` : `${start.toFixed(0)}s`;
  const rightLabel = `${end.toFixed(profileWindow().full ? 0 : 1)}s`;
  g.fillText(leftLabel, pad.left, height - 4);
  g.fillText(rightLabel, width - pad.right - g.measureText(rightLabel).width, height - 4);
  renderProfileTools();
}

// ---------------------------------------------------------------- transport

function poseAt(t) {
  return lerpByTime(state.preview?.samples || [], t);
}

function playbackActive() {
  return state.playback.state === "PLAYING" || state.playback.state === "PAUSED";
}

function clientPlayMode() {
  return state.uiMode === "2d" || state.uiMode === "3d";
}

function map2dClockRunning() {
  return clientPlayMode()
    && typeof MAP2D !== "undefined" && MAP2D.playing;
}

function selectedKeyframeTime() {
  const list = frames();
  const keyframe = state.selected != null ? list[state.selected] : null;
  return keyframe != null && Number.isFinite(keyframe.time_offset) ? keyframe.time_offset : null;
}

function renderPreviewButton() {
  const button = $("btn-preview");
  if (!button) return;
  button.classList.toggle("toggled", state.previewing);
  button.textContent = state.previewing ? "Previewing" : "Preview";
}

function renderRecordButton() {
  const button = $("btn-record");
  if (!button) return;
  const on = Boolean(state.playback.recording);
  button.classList.toggle("toggled", on);
  button.textContent = on ? "Recording" : "Record";
}

function renderPauseButton() {
  const button = $("btn-pause");
  if (!button) return;
  const paused = state.playback.state === "PAUSED" && !state.playback.preview;
  button.classList.toggle("toggled", paused);
  button.textContent = paused ? "Resume" : "Pause";
  button.title = paused
    ? "Continue the take from here"
    : "Hold the take. Click again to continue from here.";
}

let previewStartPending = false;

async function pushSimPreview(seconds) {
  if (clientPlayMode()) return;
  if (!state.previewing || !state.doc) return;
  const at = seconds ?? selectedKeyframeTime() ?? (parseFloat($("scrub").value) || 0);
  try {
    await api("POST", "/api/simulation/preview", { document: state.doc, seconds: at });
    if (seconds === undefined) {
      $("scrub").value = at;
      showPlayhead(at);
    }
  } catch (error) {
    previewStartPending = false;
    state.previewing = false;
    renderPreviewButton();
    alert(`Could not preview: ${error.message}`);
  }
}

function scrubTo(t) {
  $("scrub").value = t;
  showPlayhead(t);
  if (clientPlayMode()) {
    if (typeof MAP2D !== "undefined") MAP2D.t = t;
    return;
  }
  if (state.previewing) {
    pushSimPreview(t);
  } else if (playbackActive()) {
    api("POST", "/api/simulation/seek", { seconds: t }).catch(() => {});
  }
}

function showPlayhead(t) {
  const pose = poseAt(t);
  if (!pose) return;
  if (typeof onMap3dPlayhead === "function" && typeof map3dMode === "function" && map3dMode()) {
    onMap3dPlayhead(t);
  } else if (typeof onMap2dPlayhead === "function" && map2dMode()) {
    onMap2dPlayhead(t);
  } else if (mapFollowsAircraft() && playbackActive()) {
    if (typeof driveMapView === "function") driveMapView(pose.lat, pose.lon, map.getZoom(), null);
    else map.panTo([pose.lat, pose.lon], { animate: false });
  }
  if (typeof map3dMode !== "function" || !map3dMode()) {
    if (typeof applyDrivenScale === "function") applyDrivenScale();
    else if (typeof syncDrivenZoom === "function") syncDrivenZoom();
  }
  layers.aircraft.addTo(map);
  if (typeof placeOnDrivenMap === "function") placeOnDrivenMap(layers.aircraft, pose.lat, pose.lon);
  else layers.aircraft.setLatLng([pose.lat, pose.lon]);
  pointAircraft(pose.heading ?? 0, pose.pitch ?? 0, pose.bank ?? 0);
  const camera = showMapCamera() ? lerpByTime(state.preview?.camera_track || [], t) : null;
  if (camera) {
    layers.camera.addTo(map);
    if (typeof placeOnDrivenMap === "function") placeOnDrivenMap(layers.camera, camera.lat, camera.lon);
    else layers.camera.setLatLng([camera.lat, camera.lon]);
    layers.sightLine.setLatLngs([[camera.lat, camera.lon], [pose.lat, pose.lon]]);
  } else {
    hideCameraPlayhead();
  }
  $("clock").textContent = `${t.toFixed(1)} / ${(state.preview?.duration || 0).toFixed(1)} s · ` +
                           `${Math.round(pose.alt_ft)} ft · ${Math.round(pose.speed_kt)} kt · ` +
                           `bank ${pose.bank.toFixed(0)}°`;
  renderProfile(t);
}

// ---------------------------------------------------------------- telemetry

function connectTelemetry() {
  if (!window.FS_CAPABILITIES?.sim) {
    $("sim-status").textContent = "2D only";
    $("sim-status").className = "pill sim-only";
    return;
  }
  const socket = new WebSocket(`ws://${location.host}/ws/telemetry`);
  socket.onmessage = (event) => applyStatus(JSON.parse(event.data));
  socket.onclose = () => {
    $("sim-status").textContent = "Server disconnected";
    $("sim-status").className = "pill bad sim-only";
    setTimeout(connectTelemetry, 2000);
  };
}

function applyStatus(status) {
  const pill = $("sim-status");
  if (status.connected && status.paused) {
    // The World Map counts as paused: nothing plays until the flight starts.
    pill.textContent = `${status.application} · paused (World Map or pause menu)`;
    pill.title = "Press Start flight in the simulator, or unpause it, before playing.";
    pill.className = "pill warn sim-only";
  } else if (status.connected) {
    pill.textContent = `${status.application} · ${status.frame_rate.toFixed(0)} fps`;
    pill.title = "";
    pill.className = "pill ok sim-only";
  } else {
    pill.textContent = status.error || "Not connected";
    pill.className = "pill bad sim-only";
  }
  renderLive(status);
  if ((status.aircraft || null) !== state.aircraft) {
    // A different aircraft has its own cameras and names.
    state.aircraft = status.aircraft || null;
    loadCockpitViews();
  }

  if (clientPlayMode()) return;

  const playback = status.playback;
  const wasPlaying = playbackActive();
  state.playback = playback;
  renderPauseButton();
  if (playback.mode === "SIM_FLOWN") {
    onSimFlightStatus(playback, wasPlaying);
    showLiveOnMap();
    return;
  }
  if (playback.preview) {
    state.previewing = true;
    previewStartPending = false;
  } else if (!previewStartPending && (playback.state === "IDLE" || playback.state === "FINISHED"
             || playback.state === "ERROR" || playback.state === "PLAYING")) {
    state.previewing = false;
  }
  if (playback.state === "ERROR" && playback.message) {
    previewStartPending = false;
    if (!playback.preview) state.previewing = false;
  }
  renderPreviewButton();
  renderRecordButton();
  const rate = playback.speed && playback.speed !== 1 ? ` · ${playback.speed}×` : "";
  $("playback-state").textContent = playback.recording ? "RECORDING" : playback.preview ? "PREVIEW" : `${playback.state}${rate}`;
  $("playback-fps").textContent = playback.state === "PLAYING"
    ? ` · ${playback.frame_rate.toFixed(0)} Hz · ${playback.writes} writes` : "";

  if (playback.state === "PLAYING") {
    $("scrub").value = playback.elapsed;
    showPlayhead(playback.elapsed);
  } else {
    if (wasPlaying) {
      // Surface whatever the run ended with; notices are the usual case.
      const ending = [playback.message, ...playback.notices].filter(Boolean);
      if (ending.length) {
        state.diagnostics = [
          ...ending.map((message) => ({
            severity: playback.state === "ERROR" ? "BLOCKING" : "NOTICE",
            check: "playback", message, at: null,
          })),
          ...state.diagnostics.filter((d) => d.check !== "playback"),
        ];
        renderDiagnostics();
      }
    }
    showLiveOnMap();
  }
}

// ---------------------------------------------------------------- paths

async function refreshPathList(selectId) {
  const paths = await api("GET", "/api/paths");
  const select = $("path-select");
  select.innerHTML = "";
  for (const summary of paths) {
    const option = document.createElement("option");
    option.value = summary.path_id;
    const tag = summary.kind === "program" ? " · program" : "";
    option.textContent = summary.broken
      ? `${summary.path_id} (unreadable)`
      : summary.kind === "program"
        ? `${summary.path_id}${tag} · ${summary.flight_keyframes} seg`
        : `${summary.path_id}${tag} · ${Math.round(summary.duration)}s`;
    select.appendChild(option);
  }
  if (selectId) select.value = selectId;
  return paths;
}

const LAST_PATH_STORE = "flightstudio.lastPath";

function rememberPath(pathId) {
  if (!pathId) return;
  try { localStorage.setItem(LAST_PATH_STORE, pathId); } catch (_) { /* ignore */ }
}

function lastPathId() {
  try { return localStorage.getItem(LAST_PATH_STORE) || ""; } catch (_) { return ""; }
}

function pickPathId(paths) {
  const remembered = lastPathId();
  if (remembered && paths.some((item) => item.path_id === remembered)) return remembered;
  return paths[0]?.path_id || "";
}

async function loadPath(pathId) {
  const payload = await api("GET", `/api/paths/${pathId}`);
  rememberPath(pathId);
  if (payload.kind === "program") {
    state.program = payload.program;
    state.doc = null;
    setProgramMode(true);
  } else {
    state.program = null;
    state.doc = payload;
    setProgramMode(false);
    if (typeof ensureWaypointIds === "function") ensureWaypointIds(state.doc);
    if (typeof ensureFlightPaths === "function") ensureFlightPaths(state.doc);
    if (!state.doc.systems) state.doc.systems = [];
  }
  if (typeof loadMapDocument === "function") await loadMapDocument(pathId);
  else state.mapDoc = { path_id: pathId, line: { color: "#4ea1ff", width_px: 8, opacity: 0.95, dash: "SOLID" }, map_keyframes: [], markers: [] };
  state.selected = 0;
  state.selectedIds = [];
  if (!isProgramMode() && typeof setFlightSelection === "function" && state.doc.flight_keyframes[0]) {
    setFlightSelection([state.doc.flight_keyframes[0].id], state.doc.flight_keyframes[0].id);
  }
  state.dirty = false;
  state.track = "flight";
  document.querySelectorAll(".tab").forEach(
    (tab) => tab.classList.toggle("active", tab.dataset.track === "flight"));
  renderKeyframeList();
  renderInspector();
  renderMeta();
  await solve();
  const points = (state.preview?.samples || []).map((s) => [s.lat, s.lon]);
  if (typeof MAP2D !== "undefined") {
    MAP2D.driven = null;
    MAP2D.projectedShift = null;
    if (typeof resetDrivenOverlayPanes === "function") resetDrivenOverlayPanes();
  }
  if (points.length) {
    map.fitBounds(L.latLngBounds(points).pad(0.3), { animate: false });
    if (typeof map2dMode === "function" && map2dMode() && typeof tileZoomFor === "function") {
      map.setView(map.getCenter(), tileZoomFor(map.getZoom()), { animate: false });
    }
  }
  const scrub = $("scrub");
  scrub.step = 0.1;
  scrub.value = 0;
  $("seg-from").value = "";
  $("seg-to").value = "";
  $("seg-to").classList.remove("invalid");
  resetProfileWindow();
  showPlayhead(0);
  if (isProgramMode() && typeof selectProgramSegment === "function") {
    selectProgramSegment(state.selected ?? 0);
  }
}

async function savePath() {
  try {
    if (isProgramMode()) {
      const pathId = $("path-select")?.value;
      if (!pathId || !state.program) throw new Error("No program path loaded.");
      await api("PUT", `/api/paths/${pathId}`, {
        kind: "program",
        program: state.program,
      });
      if (typeof saveMapDocument === "function") await saveMapDocument();
      state.dirty = false;
      renderMeta();
      await refreshPathList(pathId);
      return;
    }
    if (typeof ensureWaypointIds === "function") ensureWaypointIds(state.doc);
    if (typeof ensureFlightPaths === "function") ensureFlightPaths(state.doc);
    await api("PUT", `/api/paths/${state.doc.meta.path_id}`, state.doc);
    if (typeof saveMapDocument === "function") await saveMapDocument();
    state.dirty = false;
    renderMeta();
    await refreshPathList(state.doc.meta.path_id);
  } catch (error) {
    alert(`Could not save: ${error.message}`);
  }
}

// ---------------------------------------------------------------- wiring

document.querySelectorAll(".tab").forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    state.track = tab.dataset.track;
    if (isProgramMode()) {
      if (state.track === "flight") {
        state.selected = typeof state.selected === "number" ? state.selected : 0;
      } else if (state.track === "camera") {
        const cams = state.program?.camera_keyframes || [];
        state.selected = cams.length ? 0 : null;
      } else {
        state.selected = null;
      }
      state.selectedIds = [];
      if (typeof renderProgramPopup === "function") renderProgramPopup();
      if (typeof renderProgramGizmos === "function") renderProgramGizmos();
    } else {
      state.selected = frames().length ? 0 : null;
      if (state.track === "flight" && typeof setFlightSelection === "function" && frames()[0]) {
        setFlightSelection([frames()[0].id], frames()[0].id);
      } else {
        state.selectedIds = [];
      }
    }
    renderKeyframeList();
    renderInspector();
    renderMap();
    if (typeof onMap2dSelect === "function") onMap2dSelect(state.selected);
  };
});

function openOrbitDialog() {
  if (!state.doc) return;
  const from = parseFloat($("seg-from").value);
  const to = parseFloat($("seg-to").value);
  $("orbit-from").value = Number.isFinite(from) ? from : 0;
  $("orbit-to").value = Number.isFinite(to) ? to : Math.round(lastTime() * 10) / 10;
  $("orbit-error").hidden = true;
  $("orbit-dialog").showModal();
}

async function applyOrbitDialog() {
  const error = $("orbit-error");
  error.hidden = true;
  const fov = $("orbit-fov").value;
  try {
    const fromS = parseFloat($("orbit-from").value);
    const result = await api("POST", "/api/camera-orbit", {
      camera_keyframes: state.doc.camera_keyframes,
      from_s: fromS,
      to_s: parseFloat($("orbit-to").value),
      radius_m: parseFloat($("orbit-radius").value),
      height_m: parseFloat($("orbit-height").value),
      look_at: $("orbit-look").value,
      speed_deg_s: parseFloat($("orbit-speed").value),
      direction: $("orbit-dir").value,
      start_azimuth_deg: parseFloat($("orbit-az").value),
      fov_deg: fov === "" ? null : parseFloat(fov),
    });
    state.doc.camera_keyframes = result.camera_keyframes;
    const first = state.doc.camera_keyframes.findIndex((k) => k.time_offset >= fromS);
    state.selected = first >= 0 ? first : 0;
    state.doc.meta.duration_seconds = lastTime();
    $("orbit-dialog").close();
    touched();
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  }
}

$("btn-orbit").onclick = openOrbitDialog;
$("orbit-apply").onclick = applyOrbitDialog;

$("btn-add").onclick = () => {
  if (isProgramMode()) {
    if (state.track === "camera") {
      appendProgramCameraKeyframe();
      return;
    }
    // Default quick-add: start a Line place, same as the Line chip.
    if (typeof startProgramBuild === "function") startProgramBuild("LINE_TO");
    return;
  }
  if (state.track === "flight") {
    const centre = map.getCenter();
    appendFlightKeyframe(centre.lat, centre.lng);
  } else if (state.track === "controls") {
    appendControlKeyframe();
  } else if (state.track === "systems") {
    appendSystemsKeyframe();
  } else if (state.track === "map") {
    appendMapCameraKeyframe();
  } else if (state.track === "marks") {
    const centre = map.getCenter();
    appendMapMarker(centre.lat, centre.lng);
  } else {
    appendCameraKeyframe();
  }
};

$("btn-draw").onclick = () => {
  if (typeof cancelPathAdd === "function") cancelPathAdd();
  state.drawing = !state.drawing;
  $("btn-draw").classList.toggle("toggled", state.drawing);
  $("map").classList.toggle("drawing", state.drawing);
  renderKeyframeList();
};

$("btn-remove").onclick = removeSelected;

$("btn-smooth-timing").onclick = async () => {
  if (!state.doc) return;
  try {
    const result = await api("POST", "/api/paths/smooth-timing", {
      document: state.doc, window_s: parseFloat($("smooth-window").value),
    });
    state.doc.flight_keyframes = result.flight_keyframes;
    touched();
    $("add-hint").textContent = `Timing smoothed: the biggest speed jump between segments went from `
      + `×${result.worst_jump_before} to ×${result.worst_jump_after}, moving waypoints by up to `
      + `${result.largest_move_s} s. Camera keyframes keep their times. Save to keep it, or `
      + `reload the path to undo.`;
  } catch (error) {
    alert(`Could not smooth the timing: ${error.message}`);
  }
};
$("btn-save").onclick = savePath;

$("btn-earth-studio").onclick = async () => {
  if (!state.doc || (state.doc.flight_keyframes || []).length < 2) {
    alert("Load a flight path with at least two waypoints first.");
    return;
  }
  try {
    const payload = await api("POST", "/api/earth-studio", state.doc);
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${state.doc.meta.path_id}.esp`;
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (error) {
    alert(`Could not export Earth Studio project: ${error.message}`);
  }
};

$("btn-delete").onclick = async () => {
  const pathId = state.doc?.meta?.path_id || $("path-select")?.value;
  if (!pathId || !confirm(`Delete ${pathId}?`)) return;
  await api("DELETE", `/api/paths/${pathId}`);
  state.program = null;
  state.doc = null;
  setProgramMode(false);
  const paths = await refreshPathList();
  if (paths.length) await loadPath(paths[0].path_id);
};

$("path-select").onchange = (event) => loadPath(event.target.value);

$("meta-entity").onchange = (event) => {
  state.doc.meta.entity = event.target.value;
  touched();
};

$("meta-duration").onchange = (event) => rescaleDuration(parseFloat(event.target.value));

$("meta-time-of-day").onchange = (event) => {
  state.doc.meta.time_of_day = event.target.value || null;
  touched();
};

$("auto-bank-max").onchange = (event) => {
  writeAutoBank({ max_deg: parseFloat(event.target.value) });
};
$("auto-bank-roll").onchange = (event) => {
  writeAutoBank({ roll_rate_deg_s: parseFloat(event.target.value) });
};
$("auto-bank-smooth").onchange = (event) => {
  writeAutoBank({ smoothing_s: parseFloat(event.target.value) });
};

$("scrub").oninput = (event) => scrubTo(parseFloat(event.target.value));

// From, To and Speed, as sent to the server; a blank end stays open.
function playSegment() {
  const read = (id) => {
    const value = parseFloat($(id).value);
    return Number.isFinite(value) ? value : null;
  };
  const speed = parseFloat($("play-speed").value);
  return {
    from_s: read("seg-from"),
    to_s: read("seg-to"),
    speed: Number.isFinite(speed) && speed > 0 ? speed : 1,
  };
}

function renderSegment() {
  const { from_s, to_s } = playSegment();
  const backwards = from_s !== null && to_s !== null && to_s <= from_s;
  $("seg-to").classList.toggle("invalid", backwards);
  $("seg-to").title = backwards ? "To must be after From" : "";
  renderProfile();
}

$("btn-preview").onclick = async () => {
  if (state.previewing) {
    state.previewing = false;
    previewStartPending = false;
    renderPreviewButton();
    await api("POST", "/api/simulation/stop").catch(() => {});
    return;
  }
  const blocking = state.diagnostics.filter((d) => d.severity === "BLOCKING");
  if (blocking.length) {
    alert(`Can't preview: ${blocking[0].message}`);
    return;
  }
  state.previewing = true;
  previewStartPending = true;
  renderPreviewButton();
  await pushSimPreview();
};

$("btn-record").onclick = async () => {
  if (state.playback.recording) {
    await api("POST", "/api/simulation/stop").catch(() => {});
    return;
  }
  const blocking = state.diagnostics.filter((d) => d.severity === "BLOCKING");
  if (blocking.length) {
    alert(`Can't record: ${blocking[0].message}`);
    return;
  }
  try {
    state.previewing = false;
    previewStartPending = false;
    renderPreviewButton();
    await api("POST", "/api/simulation/start", {
      document: state.doc, loop: false, record: true, ...playSegment(),
    });
  } catch (error) {
    alert(`Could not record: ${error.message}`);
  }
};

$("btn-play").onclick = async () => {
  if (clientPlayMode()) {
    if (MAP2D.playing && MAP2D.paused) { pauseMapPlay(); return; }
    startMapPlay(false);
    return;
  }
  try {
    state.previewing = false;
    previewStartPending = false;
    renderPreviewButton();
    if (state.playback.state === "PAUSED" && state.playback.mode === "POSE_INJECTION"
        && !state.playback.preview) {
      await api("POST", "/api/simulation/resume");
      return;
    }
    await api("POST", "/api/simulation/start", {
      document: state.doc, loop: $("opt-loop").checked, ...playSegment(),
    });
  } catch (error) {
    alert(`Could not start: ${error.message}`);
  }
};

// Pause holds a running take. Click again (Resume) to continue from there.
// With nothing running, it puts the aircraft at the slider and holds it.
$("btn-pause").onclick = async () => {
  if (clientPlayMode()) {
    pauseMapPlay();
    return;
  }
  try {
    const playback = state.playback;
    if (playback.state === "PAUSED" && playback.mode === "POSE_INJECTION"
        && !playback.preview) {
      state.previewing = false;
      previewStartPending = false;
      renderPreviewButton();
      await api("POST", "/api/simulation/resume");
      return;
    }
    if (playback.state === "PLAYING" && playback.mode === "POSE_INJECTION") {
      await api("POST", "/api/simulation/pause");
      return;
    }
    await api("POST", "/api/simulation/start", {
      document: state.doc, loop: $("opt-loop").checked, ...playSegment(),
      paused: true, start_at: parseFloat($("scrub").value) || 0,
    });
  } catch (error) {
    alert(`Could not pause: ${error.message}`);
  }
};

$("seg-from").oninput = renderSegment;
$("seg-to").oninput = renderSegment;
$("seg-from-set").onclick = () => {
  $("seg-from").value = parseFloat($("scrub").value).toFixed(1);
  renderSegment();
};
$("seg-to-set").onclick = () => {
  $("seg-to").value = parseFloat($("scrub").value).toFixed(1);
  renderSegment();
};
$("seg-clear").onclick = () => {
  $("seg-from").value = "";
  $("seg-to").value = "";
  renderSegment();
};

$("btn-stop").onclick = () => {
  if (clientPlayMode()) {
    stopMapPlay();
    showPlayhead(parseFloat($("scrub").value) || 0);
    return;
  }
  state.previewing = false;
  previewStartPending = false;
  renderPreviewButton();
  api("POST", "/api/simulation/stop").catch(() => {});
};

$("btn-new").onclick = () => {
  syncNewDialogKind();
  $("new-dialog").showModal();
};

function addViewRow(kind) {
  const host = $(`views-${kind}`);
  host.dataset.rows = String(parseInt(host.dataset.rows, 10) + 1);
  // Keep what has been typed so far across the re-render.
  state.views = { ...state.views, instrument: collectViewNames("instrument"),
                  quickview: collectViewNames("quickview"), custom: collectViewNames("custom") };
  renderViewsDialog();
}
$("views-add-instrument").onclick = () => addViewRow("instrument");
$("views-add-quickview").onclick = () => addViewRow("quickview");

$("views-dialog").addEventListener("close", async () => {
  const dialog = $("views-dialog");
  if (dialog.returnValue !== "save" || !state.views?.key) return;
  try {
    state.views = await api("PUT", `/api/cockpit-views/${state.views.key}`, {
      aircraft: state.views.aircraft,
      instrument: collectViewNames("instrument"),
      quickview: collectViewNames("quickview"),
      custom: collectViewNames("custom"),
    });
    renderKeyframeList();
    renderInspector();
  } catch (error) {
    alert(`Could not save the view names: ${error.message}`);
  }
});

function syncNewDialogKind() {
  const program = $("new-kind")?.value === "program";
  const demoRow = $("new-demo-row");
  if (demoRow) demoRow.hidden = !program;
  const duration = $("new-duration");
  if (duration) duration.closest("label").hidden = false;
}

$("new-kind")?.addEventListener("change", syncNewDialogKind);

$("new-dialog").addEventListener("close", async (event) => {
  const dialog = $("new-dialog");
  if (dialog.returnValue !== "create") return;
  try {
    const kind = $("new-kind")?.value || "waypoint";
    const body = {
      path_id: $("new-id").value,
      location: $("new-location").value,
      duration: parseFloat($("new-duration").value),
      kind,
    };
    if (kind === "program") body.demo = $("new-demo")?.value || "figure-eight";
    const created = await api("POST", "/api/paths/new", body);
    const pathId = created.path_id || created.meta?.path_id;
    await refreshPathList(pathId);
    await loadPath(pathId);
  } catch (error) {
    alert(`Could not create: ${error.message}`);
  }
});

$("profile-in").onclick = () => {
  const t = parseFloat($("scrub").value);
  zoomProfile(2, Number.isFinite(t) ? t : undefined);
};
$("profile-out").onclick = () => zoomProfile(0.5);
$("profile-fit").onclick = () => setProfileWindow(0, profileDuration());
$("profile-seg").onclick = () => {
  const { from_s, to_s } = playSegment();
  setProfileWindow(from_s ?? 0, to_s ?? profileDuration());
};

{
  const canvas = $("profile");
  canvas.addEventListener("wheel", (event) => {
    if ((state.preview?.samples || []).length < 2) return;
    event.preventDefault();
    zoomProfile(event.deltaY < 0 ? 1.25 : 0.8, timeFromProfileX(event.clientX));
  }, { passive: false });
  canvas.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    const view = profileWindow();
    PROFILE.drag = {
      x: event.clientX, start: view.start, end: view.end, moved: false,
    };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    const drag = PROFILE.drag;
    if (!drag) return;
    const dx = event.clientX - drag.x;
    if (!drag.moved && Math.abs(dx) < 4) return;
    drag.moved = true;
    canvas.classList.add("panning");
    const { plotWidth } = profileLayout();
    const dt = -(dx / Math.max(1, plotWidth)) * (drag.end - drag.start);
    setProfileWindow(drag.start + dt, drag.end + dt);
  });
  const endDrag = (event) => {
    const drag = PROFILE.drag;
    canvas.classList.remove("panning");
    PROFILE.drag = null;
    if (drag && !drag.moved) scrubTo(timeFromProfileX(event.clientX));
  };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", () => {
    PROFILE.drag = null;
    canvas.classList.remove("panning");
  });
}

const MAP_OVERLAY_STORE = "flightstudio.mapOverlay";

function saveMapOverlay() {
  localStorage.setItem(MAP_OVERLAY_STORE, JSON.stringify({
    waypoints: showMapWaypoints(), camera: showMapCamera(),
    follow: Boolean($("opt-follow")?.checked),
    lock: mapIsLocked(),
    attitude: Boolean($("opt-attitude")?.checked),
    planeSize: planeIconSize(),
  }));
}

function restoreMapOverlay() {
  try {
    const saved = JSON.parse(localStorage.getItem(MAP_OVERLAY_STORE) || "null");
    if (!saved || typeof saved !== "object") return;
    if (saved.waypoints === false) $("opt-waypoints").checked = false;
    if (saved.camera === false) $("opt-camera").checked = false;
    if (saved.follow === false) $("opt-follow").checked = false;
    if (saved.lock === true) $("opt-lock-map").checked = true;
    if (saved.attitude === true && $("opt-attitude")) $("opt-attitude").checked = true;
    if (Number.isFinite(saved.planeSize) && $("opt-plane-size")) {
      $("opt-plane-size").value = String(Math.min(128, Math.max(12, saved.planeSize)));
    }
  } catch (_) { /* ignore */ }
}

$("opt-waypoints").onchange = () => { saveMapOverlay(); renderMap(); };
$("opt-attitude").onchange = () => {
  saveMapOverlay();
  const t = parseFloat($("scrub")?.value);
  if (Number.isFinite(t)) showPlayhead(t);
};
$("opt-plane-size").onchange = () => {
  saveMapOverlay();
  applyPlaneIconSize();
};
$("opt-camera").onchange = () => { saveMapOverlay(); renderMap(); };
$("opt-follow").onchange = () => {
  if ($("opt-follow").checked) $("opt-lock-map").checked = false;
  saveMapOverlay();
};
$("opt-lock-map").onchange = () => {
  if ($("opt-lock-map").checked) $("opt-follow").checked = false;
  saveMapOverlay();
};

window.addEventListener("resize", () => {
  map.invalidateSize();
  renderProfile();
});

window.addEventListener("beforeunload", (event) => {
  if (state.dirty) event.preventDefault();
});

// ---------------------------------------------------------------- start

// Leaflet measures its container once at construction, which in a grid layout
// happens before the grid has resolved, leaving the lower map blank.
new ResizeObserver(() => map.invalidateSize()).observe($("map"));

(async function start() {
  await requireAuth();
  restoreMapOverlay();
  applyPlaneIconSize();
  if (typeof wireMap2d === "function") wireMap2d();
  try {
    window.FS_CAPABILITIES = await api("GET", "/api/capabilities");
  } catch (_) {
    window.FS_CAPABILITIES = { sim: false, map2d: true, map3d: true };
  }
  if (typeof wireMap3d === "function") wireMap3d();
  connectTelemetry();
  try {
    state.locations = await api("GET", "/api/locations");
    const select = $("new-location");
    for (const place of state.locations) {
      const option = document.createElement("option");
      option.value = place.key;
      option.textContent = place.label;
      select.appendChild(option);
    }

    let paths = await refreshPathList();
    if (!paths.length) {
      const created = await api("POST", "/api/paths/new",
                                { path_id: "shot-1", location: "manhattan", duration: 36 });
      paths = await refreshPathList(created.meta.path_id);
    }
    const pathId = pickPathId(paths);
    await refreshPathList(pathId);
    await loadPath(pathId);
    if (window.FS_CAPABILITIES?.sim) await loadCockpitViews();
  } catch (error) {
    $("sim-status").textContent = `Could not load: ${error.message}`;
    $("sim-status").className = "pill bad sim-only";
  }
})();
