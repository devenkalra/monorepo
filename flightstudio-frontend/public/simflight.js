"use strict";

// Sim-flown takes. The operator sets a start state and a schedule of control
// inputs; the simulator flies it and the recording comes back as a track.
// Adopting the recording turns it into ordinary waypoints, which is what makes
// a good take repeatable: the same inputs never fly quite the same path twice.

const SIM = {
  recording: [],
  // AUTOPILOT or SCHEDULE: who was flying the last take.
  kind: null,
  // How far the last finished take strayed from the path it was compared with.
  deviation: null,
  diagnostics: [],
  lastPoll: 0,
  adoptInterval: 1.0,
  keepTiming: true,
};

const simLayers = {
  recorded: L.polyline([], { color: "#e05cff", weight: 3 }).addTo(map),
  heading: L.polyline([], { color: "#7ee29a", weight: 2, dashArray: "6 4" }).addTo(map),
  start: L.layerGroup().addTo(map),
};

const CHANNEL_LABELS = [
  ["aileron", "Aileron", "A"], ["elevator", "Elevator", "E"],
  ["rudder", "Rudder", "R"], ["throttle", "Throttle", "T"],
  ["elevator_trim", "Elevator trim", "ET"],
];

// ---------------------------------------------------------------- document

function blankControlKeyframe(time) {
  return { time_offset: time, aileron: null, elevator: null, rudder: null,
           throttle: null, elevator_trim: null, transition: "RAMP" };
}

/** Start where the drawn path starts, so the two can be compared on the map. */
function createSimFlight() {
  const first = state.preview?.samples?.[0];
  const waypoint = state.doc.flight_keyframes[0];
  state.doc.sim_flight = {
    initial: {
      lat: first?.lat ?? waypoint.lat,
      lon: first?.lon ?? waypoint.lon,
      alt_ft_msl: Math.round(first?.alt_ft ?? waypoint.alt_ft_msl),
      heading_deg_true: Math.round(first?.heading ?? 0),
      pitch_deg: 0,
      bank_deg: 0,
      airspeed_kt: Math.max(120, Math.round(first?.speed_kt ?? 150)),
    },
    controls: [{ ...blankControlKeyframe(0), aileron: 0, elevator: 0, rudder: 0 }],
    duration_s: Math.max(10, Math.round(state.preview?.duration || 30)),
    settle_s: 5,
  };
  state.selected = 0;
  touched();
}

function appendControlKeyframe() {
  if (!state.doc.sim_flight) createSimFlight();
  const list = state.doc.sim_flight.controls;
  const at = state.selected === null ? list.length - 1 : state.selected;
  const previous = list[at];
  const next = list[at + 1];
  const time = !previous ? 0
    : next ? (previous.time_offset + next.time_offset) / 2
    : previous.time_offset + 3;
  // Blank channels: a new keyframe changes nothing until something is typed.
  list.splice(at + 1, 0, blankControlKeyframe(Math.round(time * 10) / 10));
  state.selected = at + 1;
  touched();
}

function describeControls(keyframe) {
  const parts = CHANNEL_LABELS
    .filter(([key]) => keyframe[key] !== null && keyframe[key] !== undefined)
    .map(([key, , short]) => `${short}${keyframe[key] >= 0 && key !== "throttle" ? "+" : ""}`
                             + `${(keyframe[key] * 100).toFixed(key === "throttle" ? 0 : 1)}`);
  if (!parts.length) return "no change";
  return parts.join(" ") + (keyframe.transition === "STEP" ? " · step" : "");
}

// Two decimals of a percent: schedules from the autopilot steer with fractions
// of a percent of aileron, and a copy through the table must not round them off.
function percentText(fraction) {
  return String(Math.round(fraction * 10000) / 100);
}

function recordedAt(t) {
  return nearestByTime(SIM.recording, t);
}

// ---------------------------------------------------------------- map

function renderSimFlightLayers() {
  simLayers.start.clearLayers();
  simLayers.recorded.setLatLngs(SIM.recording.map((s) => [s.lat, s.lon]));
  const flight = state.doc?.sim_flight;
  if (!flight) {
    simLayers.heading.setLatLngs([]);
    return;
  }
  const start = flight.initial;
  // A heading tick about a kilometre long, so the direction of release reads
  // at any zoom a shot is likely to be framed at.
  const h = start.heading_deg_true * Math.PI / 180;
  const ahead = [start.lat + Math.cos(h) * 0.009,
                 start.lon + Math.sin(h) * 0.009 / Math.cos(start.lat * Math.PI / 180)];
  simLayers.heading.setLatLngs([[start.lat, start.lon], ahead]);

  const marker = L.marker([start.lat, start.lon], {
    icon: dotIcon("start-icon"), draggable: true,
  });
  marker.bindTooltip(`Sim flight start · ${Math.round(start.alt_ft_msl)} ft · `
                     + `${Math.round(start.airspeed_kt)} kt · hdg ${Math.round(start.heading_deg_true)}° `
                     + "— drag to move");
  marker.on("drag", (event) => {
    const { lat, lng } = event.target.getLatLng();
    start.lat = lat;
    start.lon = lng;
  });
  marker.on("dragend", () => { touched(); });
  marker.on("click", () => switchTrack("controls"));
  simLayers.start.addLayer(marker);
}

function switchTrack(track) {
  document.querySelectorAll(".tab").forEach(
    (tab) => tab.classList.toggle("active", tab.dataset.track === track));
  state.track = track;
  state.selected = frames().length ? 0 : null;
  renderKeyframeList();
  renderInspector();
  renderMap();
}

// ---------------------------------------------------------------- inspector

function percentInput(value, onChange, lowest = -100) {
  const input = document.createElement("input");
  input.type = "number";
  input.min = lowest;
  input.max = 100;
  input.step = 0.1;
  input.placeholder = "hold";
  input.value = value === null || value === undefined ? "" : percentText(value);
  if (input.value !== "") input.classList.add("manual");
  input.onchange = () => {
    if (input.value.trim() === "") return onChange(null);
    onChange(Math.min(100, Math.max(lowest, parseFloat(input.value))) / 100);
  };
  return input;
}

function button(label, onClick, className = "") {
  const element = document.createElement("button");
  element.textContent = label;
  element.className = className;
  element.onclick = onClick;
  return element;
}

function describeDeviation(d) {
  return `Stayed within ${Math.round(d.max_cross_track_m)} m of the path `
    + `(${Math.round(d.rms_cross_track_m)} m on average) and ${Math.round(d.max_alt_error_ft)} ft `
    + `of its altitude; finished ${Math.round(d.end_miss_m)} m from its end.`;
}

function renderAutopilotGroup(host, flying) {
  if ((state.doc?.flight_keyframes?.length || 0) < 2) return;
  const group = document.createElement("div");
  group.className = "group";
  const title = document.createElement("h3");
  title.textContent = "Find controls for this path";
  group.appendChild(title);
  const intro = document.createElement("p");
  intro.className = "hint";
  intro.textContent = "The autopilot flies the blue path with stick, pedals and throttle under "
    + "the simulator's own physics, and records what it did. That recording becomes a "
    + "control schedule; Refine flies the schedule with the autopilot correcting it, and "
    + "folds the corrections back in.";
  group.appendChild(intro);

  const timing = document.createElement("label");
  timing.className = "inline";
  const check = document.createElement("input");
  check.type = "checkbox";
  check.checked = SIM.keepTiming;
  check.onchange = () => { SIM.keepTiming = check.checked; };
  timing.append(check, " Keep the path's timing");
  timing.title = "On: throttle chases each waypoint's time. Off: only the shape matters "
    + "and the take ends when the aircraft reaches the end.";
  group.appendChild(timing);

  const row = document.createElement("div");
  row.className = "row";
  const fly = button("Fly path with autopilot", () => flyAutopilot(false), "primary");
  fly.disabled = flying;
  const refine = button("Refine schedule", () => flyAutopilot(true));
  refine.disabled = flying || !state.doc.sim_flight?.controls?.length;
  refine.title = "Fly the current control schedule with the autopilot correcting only what "
    + "it gets wrong";
  row.append(fly, refine);
  group.appendChild(row);

  if (!flying && SIM.deviation && SIM.recording.length > 1) {
    const result = document.createElement("p");
    result.className = "hint";
    const who = SIM.kind === "AUTOPILOT" ? "Autopilot take" : "Schedule flown open loop";
    result.textContent = `${who}: ${describeDeviation(SIM.deviation)}`;
    group.appendChild(result);
    if (SIM.kind === "AUTOPILOT") {
      group.appendChild(button("Use as control schedule", useAutopilotSchedule, "primary"));
    }
  }
  host.appendChild(group);
}

function renderControlsInspector(host) {
  const flight = state.doc?.sim_flight;
  const flying = state.playback.mode === "SIM_FLOWN" && state.playback.state === "PLAYING";
  renderAutopilotGroup(host, flying);
  renderAutoflyGroup(host);
  if (!flight) {
    // Autopilot takes need no schedule, and are as worth keeping as any.
    if (!flying && SIM.recording.length > 1) renderRecordingSummary(host);
    const intro = document.createElement("p");
    intro.className = "hint";
    intro.textContent = "Let the simulator fly the aircraft. You set where it starts and how fast, "
      + "then what the stick, pedals and throttle do over time. The sim flies it and the "
      + "track it actually took is recorded, ready to adopt as this path's waypoints.";
    host.append(intro, button("Set up a sim flight", createSimFlight, "primary"));
    return;
  }

  const run = document.createElement("div");
  run.className = "row";
  const fly = button(flying ? "Flying…" : "Fly in sim", flySim, "primary");
  fly.disabled = flying || SIM.diagnostics.some((d) => d.severity === "BLOCKING");
  run.appendChild(fly);
  run.appendChild(button("Stop", () => api("POST", "/api/simulation/stop").catch(() => {})));
  host.appendChild(run);
  renderSimDiagnostics(host);
  renderRecordingSummary(host);

  const start = document.createElement("div");
  start.className = "group";
  const heading = document.createElement("h3");
  heading.textContent = "Start";
  start.appendChild(heading);
  const initial = flight.initial;
  const numberField = (label, key, step, target = initial) =>
    start.appendChild(field(label, numberInput(target[key], (v) => {
      if (Number.isFinite(v)) { target[key] = v; touched(); }
    }, step)));
  numberField("Latitude", "lat", 0.0001);
  numberField("Longitude", "lon", 0.0001);
  numberField("Altitude (ft)", "alt_ft_msl", 50);
  numberField("Heading (°)", "heading_deg_true", 1);
  numberField("Pitch (°)", "pitch_deg", 0.5);
  numberField("Bank (°)", "bank_deg", 1);
  numberField("Airspeed (kt)", "airspeed_kt", 5);
  numberField("Take length (s)", "duration_s", 1, flight);
  numberField("Settle (s)", "settle_s", 1, flight);
  start.appendChild(button("Move to the path's first waypoint", () => {
    const first = state.preview?.samples?.[0];
    if (!first) return;
    Object.assign(initial, { lat: first.lat, lon: first.lon, alt_ft_msl: Math.round(first.alt_ft),
                             heading_deg_true: Math.round(first.heading) });
    touched();
  }));
  const note = document.createElement("p");
  note.className = "hint";
  note.textContent = "Settle holds the aircraft frozen at the start so scenery can load "
    + "before it is released. Pitch is nose-up positive, bank right-wing-down positive.";
  start.appendChild(note);
  host.appendChild(start);

  renderControlKeyframe(host, flight);
}

function renderControlKeyframe(host, flight) {
  const keyframe = flight.controls[state.selected];
  const group = document.createElement("div");
  group.className = "group";
  const title = document.createElement("h3");
  group.appendChild(title);
  if (!keyframe) {
    title.textContent = "Controls";
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = flight.controls.length
      ? "Select a control keyframe."
      : "No control keyframes: the aircraft flies hands-off from its start.";
    group.appendChild(hint);
    host.appendChild(group);
    return;
  }
  title.textContent = `Control keyframe ${state.selected + 1} of ${flight.controls.length}`;
  group.appendChild(field("Time (s)", numberInput(keyframe.time_offset, (v) => {
    if (Number.isFinite(v)) { keyframe.time_offset = Math.max(0, v); touched(); }
  }, 0.1)));
  for (const [key, label] of CHANNEL_LABELS) {
    group.appendChild(field(`${label} %`, percentInput(keyframe[key], (v) => {
      keyframe[key] = v; touched();
    }, key === "throttle" ? 0 : -100)));
  }
  group.appendChild(field("Get there by", selectInput(
    [["RAMP", "Ramping from the previous value"], ["STEP", "Jumping at this time"]],
    keyframe.transition, (v) => { keyframe.transition = v; touched(); })));
  const note = document.createElement("p");
  note.className = "hint";
  note.textContent = "+ aileron rolls right, + elevator is back stick (nose up), + rudder "
    + "yaws right, + elevator trim is nose up. Blank keeps the control where it was. A control no keyframe sets is "
    + "left to you and the aircraft.";
  group.appendChild(note);
  host.appendChild(group);
}

function renderSimDiagnostics(host) {
  for (const item of SIM.diagnostics) {
    const box = document.createElement("div");
    box.className = `diag ${item.severity}`;
    box.textContent = item.message;
    host.appendChild(box);
  }
}

function renderRecordingSummary(host) {
  const box = document.createElement("div");
  box.className = "group";
  const samples = SIM.recording;
  if (samples.length < 2) {
    box.innerHTML = "<p class='hint'>No recording yet. Fly in sim to make one; it is drawn "
      + "in magenta on the map.</p>";
    host.appendChild(box);
    return;
  }
  const range = (key) => {
    const values = samples.map((s) => s[key]);
    return `${Math.round(Math.min(...values))}–${Math.round(Math.max(...values))}`;
  };
  const summary = document.createElement("p");
  summary.className = "hint";
  summary.textContent = `Recorded ${samples[samples.length - 1].t.toFixed(1)} s: `
    + `${range("airspeed_kt")} kt, ${range("alt_ft_msl")} ft, bank ${range("bank_deg")}°.`;
  box.appendChild(summary);

  const row = document.createElement("div");
  row.className = "row";
  row.appendChild(selectInput(
    [["0.5", "every 0.5 s"], ["1", "every 1 s"], ["2", "every 2 s"], ["5", "every 5 s"]],
    String(SIM.adoptInterval), (v) => { SIM.adoptInterval = parseFloat(v); }));
  row.appendChild(button("Save as new path…", saveRecordingAsPath));
  row.appendChild(button("Use as flight path", adoptRecording));
  box.appendChild(row);
  const hint = document.createElement("p");
  hint.className = "hint";
  hint.textContent = "Save as new path keeps this path as it is and saves the recorded "
    + "track, attitude included, as a path of its own. Use as flight path replaces this "
    + "path's waypoints instead. Either way, Play then repeats exactly this flight with "
    + "your cameras.";
  box.appendChild(hint);
  host.appendChild(box);
}

// ---------------------------------------------------------------- server

let simValidateToken = 0;

async function validateSimFlight() {
  if (!state.doc?.sim_flight) {
    SIM.diagnostics = [];
    return;
  }
  const token = ++simValidateToken;
  try {
    const result = await api("POST", "/api/simflight/validate", state.doc);
    if (token !== simValidateToken) return;
    SIM.diagnostics = result.diagnostics;
  } catch (error) {
    SIM.diagnostics = [{ severity: "BLOCKING", check: "solve", message: String(error.message) }];
  }
  if (state.track === "controls") renderInspector();
}

async function flySim() {
  try {
    SIM.recording = [];
    SIM.deviation = null;
    renderMap();
    await api("POST", "/api/simflight/start", { document: state.doc });
  } catch (error) {
    alert(`Could not start the sim flight: ${error.message}`);
  }
}

async function flyAutopilot(refine) {
  try {
    SIM.recording = [];
    SIM.deviation = null;
    renderMap();
    // The playback From/To fly just that stretch, released at the path's state there.
    await api("POST", "/api/autopilot/start",
              { document: state.doc, keep_timing: SIM.keepTiming, refine, ...playSegment() });
  } catch (error) {
    alert(`Could not start the autopilot: ${error.message}`);
  }
}

async function useAutopilotSchedule() {
  const existing = state.doc.sim_flight?.controls?.length || 0;
  if (existing && !confirm(`Replace the ${existing} control keyframes with the ones the `
                           + "autopilot used?")) return;
  try {
    const result = await api("POST", "/api/autopilot/schedule", {});
    state.doc.sim_flight = result.sim_flight;
    state.selected = 0;
    touched();
  } catch (error) {
    alert(`Could not convert the autopilot take: ${error.message}`);
  }
}

async function fetchRecording(every) {
  try {
    const result = await api("GET", `/api/simflight/recording?every=${every}`);
    SIM.recording = result.samples;
    SIM.kind = result.kind;
    SIM.deviation = result.deviation;
    SIM.segment = result.segment;
    renderMap();
  } catch (_) { /* the next poll will try again */ }
}

async function saveRecordingAsPath() {
  const source = state.doc;
  const [from, to] = SIM.segment || [0, null];
  const suggested = SIM.segment
    ? `${source.meta.path_id}-${Math.round(from)}-${Math.round(to)}`
    : `${source.meta.path_id}-flown`;
  const pathId = prompt("Save the recorded flight as a new path called:", suggested);
  if (!pathId) return;
  try {
    const existing = await api("GET", "/api/paths");
    if (existing.some((p) => p.path_id === pathId)
        && !confirm(`${pathId} already exists. Replace it?`)) return;
    const result = await api("POST", "/api/simflight/keyframes",
                             { interval_s: SIM.adoptInterval });
    // A segment's recording starts at 0; its cameras come from the same
    // stretch of the source, shifted to match.
    const cameras = source.camera_keyframes
      .filter((k) => k.time_offset >= from && k.time_offset <= from + result.duration)
      .map((k) => ({ ...k, time_offset: Math.round((k.time_offset - from) * 100) / 100 }));
    if (!cameras.length && source.camera_keyframes.length) {
      cameras.push({ ...source.camera_keyframes[0], time_offset: 0 });
    }
    const doc = {
      meta: { ...source.meta, path_id: pathId, duration_seconds: result.duration,
              entity: "USER_AIRCRAFT",
              flown_from: source.meta.flown_from || source.meta.path_id,
              flown_from_s: (source.meta.flown_from_s || 0) + from },
      flight_keyframes: result.flight_keyframes,
      camera_keyframes: cameras,
      sim_flight: null,
      systems: result.systems || [],
    };
    await api("PUT", `/api/paths/${pathId}`, doc);
    await refreshPathList(source.meta.path_id);
    alert(`Saved ${pathId}: ${result.flight_keyframes.length} waypoints, `
          + `${result.duration.toFixed(1)} s. ${source.meta.path_id} is unchanged.`);
  } catch (error) {
    alert(`Could not save the recording: ${error.message}`);
  }
}

async function adoptRecording() {
  const recorded = SIM.recording.length ? SIM.recording[SIM.recording.length - 1].t : 0;
  const cameras = state.doc.camera_keyframes;
  const cameraEnd = cameras.reduce((most, k) => Math.max(most, k.time_offset), 0);
  // Cameras timed for the old path would otherwise run on past the end of the
  // new one, holding the aircraft still while they finish.
  const rescale = cameraEnd > recorded + 0.5;
  const question = `Replace the ${state.doc.flight_keyframes.length} waypoints of `
    + `${state.doc.meta.path_id} with the recorded flight?`
    + (rescale ? `\n\nThe camera keyframes run to ${cameraEnd.toFixed(0)} s, so their times `
                 + `will be scaled to fit the ${recorded.toFixed(0)} s recording.` : "");
  if (!confirm(question)) return;
  try {
    const result = await api("POST", "/api/simflight/keyframes",
                             { interval_s: SIM.adoptInterval });
    if (rescale && cameraEnd > 0) {
      const factor = result.duration / cameraEnd;
      for (const keyframe of cameras) {
        keyframe.time_offset = Math.round(keyframe.time_offset * factor * 100) / 100;
      }
    }
    state.doc.flight_keyframes = result.flight_keyframes;
    state.doc.systems = result.systems || [];
    state.doc.meta.duration_seconds = result.duration;
    state.doc.meta.entity = "USER_AIRCRAFT";
    switchTrack("flight");
    touched();
  } catch (error) {
    alert(`Could not convert the recording: ${error.message}`);
  }
}

/** Telemetry for a sim-flown take; replaces the pose-injection handling. */
function onSimFlightStatus(playback, wasPlaying) {
  const playing = playback.state === "PLAYING";
  $("playback-state").textContent = playing ? `SIM ${playback.phase}` : `SIM ${playback.state}`;
  $("playback-fps").textContent = playing ? ` · ${playback.frame_rate.toFixed(0)} Hz` : "";

  const subject = playback.subject;
  if (subject) {
    layers.aircraft.setLatLng([subject.lat, subject.lon]).addTo(map);
    pointAircraft(subject.heading_deg_true ?? 0);
    if (playing && mapFollowsAircraft()) map.panTo([subject.lat, subject.lon], { animate: false });
  }
  if (playing) {
    $("clock").textContent = playback.phase === "SETTLING"
      ? (playback.message || "Holding at the start")
      : `${playback.elapsed.toFixed(1)} / ${playback.duration.toFixed(1)} s · `
        + (playback.message || `${playback.samples} samples`
                               + (subject ? ` · ${Math.round(subject.alt_ft_msl)} ft` : ""));
    const now = performance.now();
    if (playback.phase === "FLYING" && now - SIM.lastPoll > 1000) {
      SIM.lastPoll = now;
      fetchRecording(5);
    }
  }
  if (wasPlaying && !playing) {
    // A thinned copy is plenty to draw, and the full one stays on the server
    // for conversion.
    fetchRecording(2).then(() => {
      $("clock").textContent = playback.message || `Sim flight ${playback.state.toLowerCase()}`;
      if (state.track === "controls") renderInspector();
    });
  }
  if (wasPlaying !== playing && state.track === "controls") renderInspector();
}

// The server keeps the last recording across page reloads; show it.
fetchRecording(2);
