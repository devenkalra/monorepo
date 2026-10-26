// Floating live readout of the user aircraft: where it is and what its controls
// are doing, refreshed from every telemetry message.

const LIVE_STORE = "flightstudio.live";
const LIVE_CSV_EVERY_STORE = "flightstudio.live.csvEvery";

const LIVE_FIELDS = [
  ["Latitude", (r) => r.lat.toFixed(6)],
  ["Longitude", (r) => r.lon.toFixed(6)],
  ["Altitude", (r) => `${Math.round(r.alt_ft_msl).toLocaleString()} ft MSL`],
  ["Above ground", (r) => `${Math.round(r.alt_ft_agl).toLocaleString()} ft`],
  ["Heading", (r) => `${r.heading_deg_true.toFixed(1)}° T`],
  ["Pitch", (r) => `${signed(r.pitch_deg, 1)}°`],
  ["Bank", (r) => `${signed(r.bank_deg, 1)}°`],
  ["Airspeed", (r) => `${Math.round(r.ias_kt)} kt IAS · ${Math.round(r.tas_kt)} TAS`],
  ["Ground speed", (r) => `${Math.round(r.ground_speed_kt)} kt`],
  ["Vertical speed", (r) => `${signed(Math.round(r.vertical_speed_fpm), 0)} fpm`],
];

const LIVE_CONTROLS = [
  ["aileron", "Aileron", true],
  ["elevator", "Elevator", true],
  ["rudder", "Rudder", true],
  ["throttle", "Throttle", false],
  ["elevator_trim", "Elev trim", true],
];

const LIVE = {
  built: false, values: {}, bars: {}, open: false, reached: 0, flashTimer: null,
  lastReading: null, recenter: false,
};

function signed(value, places) {
  const text = value.toFixed(places);
  return value > 0 ? `+${text}` : text;
}

function buildLivePanel() {
  const body = $("live-body");
  body.innerHTML = "";
  const clock = document.createElement("div");
  clock.className = "live-clock";
  LIVE.time = document.createElement("span");
  LIVE.time.className = "live-time";
  LIVE.change = document.createElement("span");
  LIVE.change.className = "live-change";
  clock.append(LIVE.time, LIVE.change);
  body.appendChild(clock);

  const grid = document.createElement("dl");
  grid.className = "live-grid";
  for (const [label] of LIVE_FIELDS) {
    const name = document.createElement("dt");
    name.textContent = label;
    const value = document.createElement("dd");
    value.textContent = "–";
    grid.append(name, value);
    LIVE.values[label] = value;
  }
  body.appendChild(grid);

  const cameraHeading = document.createElement("h4");
  cameraHeading.textContent = "Camera";
  body.appendChild(cameraHeading);
  LIVE.cameraNote = document.createElement("p");
  LIVE.cameraNote.className = "hint";
  LIVE.cameraNote.textContent = "–";
  body.appendChild(LIVE.cameraNote);
  const cameraGrid = document.createElement("dl");
  cameraGrid.className = "live-grid";
  LIVE.cameraValues = {};
  for (const label of [
    "Type", "Frame", "Azimuth", "Radius", "Height",
    "Look at", "Look right", "Look height", "Look forward",
    "6DOF x/y/z", "6DOF pitch/bank/hdg",
  ]) {
    const name = document.createElement("dt");
    name.textContent = label;
    const value = document.createElement("dd");
    value.textContent = "–";
    cameraGrid.append(name, value);
    LIVE.cameraValues[label] = value;
  }
  body.appendChild(cameraGrid);

  const heading = document.createElement("h4");
  heading.textContent = "Controls";
  body.appendChild(heading);
  for (const [key, label, centred] of LIVE_CONTROLS) {
    const row = document.createElement("div");
    row.className = "live-control";
    const name = document.createElement("span");
    name.textContent = label;
    const track = document.createElement("div");
    track.className = centred ? "live-track centred" : "live-track";
    const fill = document.createElement("div");
    fill.className = "live-fill";
    const target = document.createElement("div");
    target.className = "live-target";
    target.hidden = true;
    track.append(fill, target);
    const value = document.createElement("span");
    value.className = "live-value";
    value.textContent = "–";
    const buttons = [
      nudgeButton("−", key, label, -0.05, true),
      nudgeButton("−", key, label, -0.01, false),
      nudgeButton("+", key, label, 0.01, false),
      nudgeButton("+", key, label, 0.05, true),
    ];
    row.append(name, buttons[0], buttons[1], track, buttons[2], buttons[3], value);
    body.appendChild(row);
    LIVE.bars[key] = { fill, target, value, centred, buttons };
  }
  const legend = document.createElement("p");
  legend.className = "hint";
  legend.textContent = "Bars are the surface and lever positions the sim reports; + is right "
    + "roll, nose up, right yaw, nose-up trim. The white tick is what a sim-flown take is commanding. "
    + "During a take, the red − and + change a control by 5% and the white ones by 1%, "
    + "from that moment on.";
  body.appendChild(legend);

  LIVE.export = document.createElement("div");
  LIVE.export.className = "live-export";
  LIVE.export.hidden = true;
  const save = document.createElement("button");
  save.textContent = "Save run as CSV";
  save.title = "Every frame of the last run: position, attitude, speeds, and reported and "
    + "commanded controls in percent";
  save.onclick = saveLiveCsv;
  LIVE.exportEvery = document.createElement("select");
  LIVE.exportEvery.title = "Sample time: one row per this much run time";
  for (const [value, text] of [["0", "every frame"], ["0.1", "0.1 s"], ["0.25", "0.25 s"],
                               ["0.5", "0.5 s"], ["1", "1 s"], ["2", "2 s"], ["5", "5 s"]]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    LIVE.exportEvery.appendChild(option);
  }
  LIVE.exportEvery.value = localStorage.getItem(LIVE_CSV_EVERY_STORE) || "0";
  LIVE.exportEvery.onchange = () => {
    localStorage.setItem(LIVE_CSV_EVERY_STORE, LIVE.exportEvery.value);
  };
  LIVE.exportNote = document.createElement("span");
  LIVE.exportNote.className = "hint";
  LIVE.export.append(save, LIVE.exportEvery, LIVE.exportNote);
  body.appendChild(LIVE.export);

  LIVE.changes = document.createElement("div");
  LIVE.changes.className = "live-changes";
  LIVE.changes.hidden = true;
  body.appendChild(LIVE.changes);
  LIVE.built = true;
}

function nudgeButton(text, channel, label, delta, coarse) {
  const button = document.createElement("button");
  button.className = coarse ? "live-nudge coarse" : "live-nudge";
  button.textContent = text;
  button.title = `${delta > 0 ? "Increase" : "Decrease"} ${label.toLowerCase()} by `
    + `${Math.round(Math.abs(delta) * 100)}% from now on`;
  button.disabled = true;
  button.onclick = async () => {
    try {
      await api("POST", "/api/simflight/nudge", { channel, delta });
    } catch (error) {
      $("live-source").textContent = error.message;
    }
  };
  return button;
}

const LIVE_CHANNEL_NAMES = Object.fromEntries(LIVE_CONTROLS.map(([key, label]) => [key, label]));

function nudgeText(nudge) {
  const percent = Math.round(nudge.value * 100);
  const shown = nudge.channel === "throttle" ? `${percent}%` : `${percent > 0 ? "+" : ""}${percent}%`;
  return `${nudge.t.toFixed(1)} s · ${LIVE_CHANNEL_NAMES[nudge.channel]} → ${shown}`;
}

// Changes made with − and + during the take: listed as they happen, and once
// the take is over, offered for the control table.
function renderLiveChanges(playback) {
  const nudges = playback?.nudges || [];
  const flying = playback?.state === "PLAYING";
  const key = `${playback?.path_id}|${JSON.stringify(nudges)}`;
  const box = LIVE.changes;
  box.hidden = !nudges.length || LIVE.handled === key;
  if (box.hidden) return;
  const view = `${key}|${flying}|${state.doc?.meta.path_id}`;
  if (box.dataset.view === view) return;
  box.dataset.view = view;
  box.innerHTML = "";

  const heading = document.createElement("h4");
  heading.textContent = `Changes this take (${nudges.length})`;
  const list = document.createElement("ol");
  for (const nudge of nudges) {
    const item = document.createElement("li");
    item.textContent = nudgeText(nudge);
    list.appendChild(item);
  }
  box.append(heading, list);
  list.scrollTop = list.scrollHeight;
  if (flying) return;

  const forOtherPath = state.doc?.meta.path_id !== playback.path_id;
  const actions = document.createElement("div");
  actions.className = "live-change-actions";
  const apply = document.createElement("button");
  apply.className = "primary";
  apply.textContent = "Update control table";
  apply.disabled = forOtherPath || !state.doc?.sim_flight;
  apply.onclick = () => applyLiveChanges(key);
  const discard = document.createElement("button");
  discard.textContent = "Discard";
  discard.onclick = () => { LIVE.handled = key; box.hidden = true; };
  actions.append(apply, discard);
  box.appendChild(actions);
  if (forOtherPath) {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = `These changes were made flying ${playback.path_id}; open it to add them.`;
    box.appendChild(note);
  }
}

async function applyLiveChanges(key) {
  try {
    const result = await api("POST", "/api/simflight/nudges/merge",
                             { controls: state.doc.sim_flight.controls });
    state.doc.sim_flight.controls = result.controls;
    LIVE.handled = key;
    LIVE.changes.hidden = true;
    touched();
  } catch (error) {
    alert(`Could not add the changes: ${error.message}`);
  }
}

// Every frame of the last run, as the window showed it, once the run is over.
function renderLiveExport(status) {
  const log = status.live_log;
  const over = status.playback?.state !== "PLAYING";
  LIVE.export.hidden = !log?.rows || !over;
  if (LIVE.export.hidden) return;
  const seconds = status.playback?.path_id === log.path_id ? status.playback.elapsed : null;
  LIVE.exportNote.textContent = `${log.path_id} · ${log.rows.toLocaleString()} frames`
    + (seconds ? ` · ${seconds.toFixed(1)} s` : "");
}

async function saveLiveCsv() {
  try {
    const response = await fetch(`/api/run/live.csv?every_s=${LIVE.exportEvery.value}`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || response.statusText);
    }
    const disposition = response.headers.get("Content-Disposition") || "";
    const name = /filename="([^"]+)"/.exec(disposition)?.[1] || "run.csv";
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    alert(`Could not save the run: ${error.message}`);
  }
}

// Where a value sits along a bar, as left and width percentages.
function barSpan(value, centred) {
  if (!centred) return { left: 0, width: Math.max(0, Math.min(1, value)) * 100 };
  const half = Math.max(-1, Math.min(1, value)) * 50;
  return half >= 0 ? { left: 50, width: half } : { left: 50 + half, width: -half };
}

function showLiveOnMap() {
  if (!LIVE.open) return;
  if (playbackActive() || state.previewing) return;
  const reading = LIVE.lastReading;
  if (!reading || !Number.isFinite(reading.lat) || !Number.isFinite(reading.lon)) return;
  layers.aircraft.setLatLng([reading.lat, reading.lon]).addTo(map);
  pointAircraft(reading.heading_deg_true ?? 0);
  if (mapFollowsAircraft()) {
    map.panTo([reading.lat, reading.lon], { animate: false });
    LIVE.recenter = false;
  }
}

function renderLive(status) {
  LIVE.lastReading = status.live || null;
  if (!LIVE.open) return;
  if (!LIVE.built) buildLivePanel();
  const reading = status.live;
  const commanded = status.playback?.commanded || null;
  $("live-source").textContent = !status.connected ? "not connected"
    : !reading ? "waiting for the sim"
    : commanded ? "sim-flown take" : status.playback?.state === "PLAYING" ? "playback"
    : status.playback?.state === "PAUSED" ? "playback paused" : "";
  $("live-panel").classList.toggle("stale", !reading);
  renderLiveClock(status.playback);
  renderLiveCamera(status.playback);
  renderLiveChanges(status.playback);
  renderLiveExport(status);
  const canNudge = status.playback?.nudgeable && status.playback.state === "PLAYING"
    && status.playback.phase === "FLYING";
  for (const [key] of LIVE_CONTROLS) {
    for (const button of LIVE.bars[key].buttons) button.disabled = !canNudge;
  }
  if (!reading) return;

  for (const [label, format] of LIVE_FIELDS) LIVE.values[label].textContent = format(reading);
  for (const [key, , centred] of LIVE_CONTROLS) {
    const bar = LIVE.bars[key];
    const value = reading[key];
    const span = barSpan(value, centred);
    bar.fill.style.left = `${span.left}%`;
    bar.fill.style.width = `${span.width}%`;
    bar.value.textContent = centred ? `${signed(Math.round(value * 100), 0)}%`
                                    : `${Math.round(value * 100)}%`;
    const wanted = commanded?.[key];
    bar.target.hidden = wanted == null;
    if (wanted != null) {
      bar.target.style.left = `${centred ? 50 + Math.max(-1, Math.min(1, wanted)) * 50
                                         : Math.max(0, Math.min(1, wanted)) * 100}%`;
      bar.target.title = `Commanded ${Math.round(wanted * 100)}%`;
    }
  }
}

// The take's clock, and which control keyframe is in effect. The badge
// flashes for a moment each time a new keyframe comes due.
function renderLiveClock(playback) {
  const running = playback && ["PLAYING", "PAUSED", "FINISHED"].includes(playback.state);
  if (!running) {
    LIVE.time.textContent = "No take running";
    LIVE.change.textContent = "";
    LIVE.change.classList.remove("flash");
    LIVE.reached = 0;
    return;
  }
  const settling = playback.phase === "SETTLING" && playback.state === "PLAYING";
  LIVE.time.textContent = settling ? "Holding at start"
    : `t = ${playback.elapsed.toFixed(1)} s / ${playback.duration.toFixed(1)} s`;

  const total = playback.keyframes_total || 0;
  const reached = playback.keyframes_reached || 0;
  LIVE.change.hidden = !total;
  if (!total) return;
  LIVE.change.textContent = reached ? `Keyframe ${reached} of ${total} applied`
                                    : `${total} keyframes waiting`;
  if (reached > LIVE.reached && !settling) {
    LIVE.change.classList.remove("flash");
    void LIVE.change.offsetWidth;  // restart the animation for back-to-back keyframes
    LIVE.change.classList.add("flash");
    clearTimeout(LIVE.flashTimer);
    LIVE.flashTimer = setTimeout(() => LIVE.change.classList.remove("flash"), 1500);
  }
  LIVE.reached = reached;
}

function dash(value, suffix) {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  if (typeof value === "number") return `${value}${suffix || ""}`;
  return String(value);
}

function renderLiveCamera(playback) {
  const values = LIVE.cameraValues;
  if (!values) return;
  const camera = playback?.camera;
  if (!camera) {
    LIVE.cameraNote.textContent = "No take, or this path has no camera keyframes.";
    for (const node of Object.values(values)) node.textContent = "–";
    return;
  }
  LIVE.cameraNote.textContent = camera.type === "COCKPIT"
    ? "Cockpit view is selected, not the cinematic drone."
    : "Commanded cinematic pose (level-frame numbers from the interpolated path).";
  if (camera.type === "COCKPIT") {
    values["Type"].textContent = `Cockpit · ${camera.view || ""} ${camera.index ?? ""}`.trim();
    values["Frame"].textContent = "–";
    values["Azimuth"].textContent = "–";
    values["Radius"].textContent = "–";
    values["Height"].textContent = "–";
    values["Look at"].textContent = "–";
    values["Look right"].textContent = "–";
    values["Look height"].textContent = "–";
    values["Look forward"].textContent = "–";
    values["6DOF x/y/z"].textContent = camera.zoom_pct == null ? "zoom sim default"
      : `zoom ${camera.zoom_pct}%`;
    values["6DOF pitch/bank/hdg"].textContent = "–";
    return;
  }
  values["Type"].textContent = "Cinematic";
  values["Frame"].textContent = camera.frame || "–";
  values["Azimuth"].textContent = dash(camera.azimuth_deg, "°");
  values["Radius"].textContent = dash(camera.radius_m, " m");
  values["Height"].textContent = dash(camera.height_m, " m");
  values["Look at"].textContent = camera.look_at || "–";
  values["Look right"].textContent = dash(camera.look_right_m, " m");
  values["Look height"].textContent = dash(camera.look_height_m, " m");
  values["Look forward"].textContent = dash(camera.look_forward_m, " m");
  values["6DOF x/y/z"].textContent = camera.x_m == null ? "–"
    : `${camera.x_m} / ${camera.y_m} / ${camera.z_m} m`;
  values["6DOF pitch/bank/hdg"].textContent = camera.pitch_deg == null ? "–"
    : `${camera.pitch_deg}° / ${camera.bank_deg}° / ${camera.heading_deg}°`;
}

function saveLivePlacement() {
  const panel = $("live-panel");
  localStorage.setItem(LIVE_STORE, JSON.stringify({
    open: LIVE.open, left: panel.offsetLeft, top: panel.offsetTop,
  }));
}

// Keep the title bar reachable after the window shrinks or a stale position loads.
function placeLivePanel(left, top) {
  const panel = $("live-panel");
  const view = document.documentElement;
  const maxLeft = Math.max(0, view.clientWidth - panel.offsetWidth);
  const maxTop = Math.max(0, view.clientHeight - $("live-head").offsetHeight);
  panel.style.left = `${Math.max(0, Math.min(maxLeft, left))}px`;
  panel.style.top = `${Math.max(0, Math.min(maxTop, top))}px`;
}

function setLiveOpen(open) {
  LIVE.open = open;
  $("live-panel").hidden = !open;
  $("btn-live").classList.toggle("toggled", open);
  if (open) {
    const panel = $("live-panel");
    placeLivePanel(panel.offsetLeft, panel.offsetTop);
    LIVE.recenter = true;
    showLiveOnMap();
  }
  saveLivePlacement();
}

(function initLivePanel() {
  const panel = $("live-panel");
  const head = $("live-head");
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(LIVE_STORE)) || {}; } catch { /* ignore */ }
  panel.style.left = `${saved.left ?? 80}px`;
  panel.style.top = `${saved.top ?? 90}px`;

  $("btn-live").onclick = () => setLiveOpen(!LIVE.open);
  $("live-close").onclick = () => setLiveOpen(false);

  head.addEventListener("pointerdown", (event) => {
    if (event.target.closest("button")) return;
    const startX = event.clientX - panel.offsetLeft;
    const startY = event.clientY - panel.offsetTop;
    try { head.setPointerCapture(event.pointerId); } catch { /* drag still works uncaptured */ }
    const move = (e) => placeLivePanel(e.clientX - startX, e.clientY - startY);
    const up = () => {
      head.removeEventListener("pointermove", move);
      head.removeEventListener("pointerup", up);
      head.removeEventListener("pointercancel", up);
      saveLivePlacement();
    };
    head.addEventListener("pointermove", move);
    head.addEventListener("pointerup", up);
    head.addEventListener("pointercancel", up);
  });
  window.addEventListener("resize", () => {
    if (LIVE.open) placeLivePanel(panel.offsetLeft, panel.offsetTop);
  });

  if (saved.open) setLiveOpen(true);
})();
