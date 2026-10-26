"use strict";

// Table editor. Shares `state` and the solve pipeline with the map editor, so
// an edit here lands on the map and the profile immediately and vice versa.
//
// Rows hold a direct reference to their keyframe rather than an index,
// because solving re-sorts the arrays by time: the moment someone retypes a
// time, an index-keyed row would be pointing at its neighbour.

const TABLE = { track: "flight", rows: [] };

const number = (value, fallback = 0) => {
  const parsed = parseFloat(String(value).trim());
  return Number.isFinite(parsed) ? parsed : fallback;
};

const fixed = (value, places) => (value === null || value === undefined || value === ""
  ? "" : Number(value).toFixed(places));

/** Blank means AUTO, a number pins the angle. Compact enough for a table, and
 *  it survives a round trip through a spreadsheet. */
function angleColumn(label, which) {
  return {
    label,
    title: "Blank derives the angle from the path; a number pins it",
    placeholder: "auto",
    width: "7ch",
    get: (k) => (k[which].mode === "MANUAL" ? String(k[which].deg) : ""),
    set: (k, raw) => {
      k[which] = raw.trim() === ""
        ? { mode: "AUTO" }
        : { mode: "MANUAL", deg: number(raw) };
    },
    classOf: (k) => (k[which].mode === "MANUAL" ? "manual" : ""),
  };
}

function easingColumns() {
  return [
    { label: "Ease in", group: true, width: "7ch", get: (k) => fixed(k.easing.ease_in, 2),
      set: (k, v) => { k.easing.ease_in = Math.min(1, Math.max(0, number(v))); } },
    { label: "Ease out", width: "7ch", get: (k) => fixed(k.easing.ease_out, 2),
      set: (k, v) => { k.easing.ease_out = Math.min(1, Math.max(0, number(v))); } },
    { label: "Hold s", width: "7ch",
      title: "On a Cut row this is how long the cut stays before snapping back",
      get: (k) => fixed(k.easing.hold_s, 2),
      set: (k, v) => { k.easing.hold_s = Math.max(0, number(v)); } },
  ];
}

const FLIGHT_COLUMNS = [
  { label: "Name", width: "12ch", placeholder: "",
    get: (k) => k.name || "",
    set: (k, v) => { k.name = String(v).trim(); } },
  { label: "Group", width: "12ch", placeholder: "",
    title: "Named group. Blank removes this waypoint from its group.",
    get: (k) => (typeof groupOf === "function" ? (groupOf(k.id)?.name || "") : ""),
    set: (k, raw) => {
      const name = String(raw).trim();
      if (typeof setFlightSelection === "function") setFlightSelection([k.id], k.id);
      if (!name) {
        if (typeof dissolveSelectionGroups === "function") dissolveSelectionGroups();
        return;
      }
      const existing = (state.doc.groups || []).find((g) => (g.name || "") === name);
      if (typeof assignSelectionToGroup === "function") {
        assignSelectionToGroup(existing?.id || "", name, existing?.color);
      }
    } },
  { label: "Time s", width: "8ch", get: (k) => fixed(k.time_offset, 2),
    set: (k, v) => { k.time_offset = Math.max(0, number(v)); } },
  { label: "Latitude", group: true, width: "12ch", get: (k) => fixed(k.lat, 6),
    set: (k, v) => { k.lat = Math.min(90, Math.max(-90, number(v, k.lat))); } },
  { label: "Longitude", width: "12ch", get: (k) => fixed(k.lon, 6),
    set: (k, v) => { k.lon = Math.min(180, Math.max(-180, number(v, k.lon))); } },
  { label: "Alt ft", width: "9ch", get: (k) => fixed(k.alt_ft_msl, 0),
    set: (k, v) => { k.alt_ft_msl = number(v, k.alt_ft_msl); } },
  { label: "To next", group: true, width: "10ch",
    title: "Shape of the leg from this waypoint to the next",
    choices: [["STRAIGHT", "Straight"], ["ARC", "Arc"], ["HERMITE", "Hermite"], ["BSPLINE", "B-spline"]],
    get: (k) => k.path?.kind || "STRAIGHT",
    set: (k, v) => {
      if (typeof setPathKind === "function") setPathKind(k, v);
      else k.path = { kind: v };
    } },
  { ...angleColumn("Heading", "heading"), group: true },
  angleColumn("Pitch", "pitch"),
  angleColumn("Bank", "bank"),
  ...easingColumns(),
  // Last of the editable columns, so rows pasted without a header line keep
  // the positions they had before it existed.
  { label: "On ground", group: true, width: "9ch",
    title: "The leg from this waypoint rolls on the surface: playback puts the wheels on "
      + "the sim's terrain instead of using the altitude",
    choices: [["", "—"], ["YES", "Yes"]],
    get: (k) => (k.on_ground ? "YES" : ""),
    set: (k, v) => { k.on_ground = /^(yes|y|true|1|x)$/i.test(String(v).trim()); } },
  // Read-only, straight from the solver, so the consequences of a time edit
  // are visible in the same row that caused them. Copied with the table;
  // paste ignores them (they are not authored).
  { label: "kt", group: true, title: "Solved ground speed at this keyframe",
    derived: (k, solved) => fixed(solved?.speed_kt, 0) },
  { label: "path track°", title: "Solved track from the path (not the pinned Heading)",
    derived: (k, solved) => fixed(solved?.heading, 1) },
  { label: "path bank°", title: "Solved bank from the path (not the pinned Bank)",
    derived: (k, solved) => fixed(solved?.bank, 1) },
];

const AIRCRAFT_REFS = [["CG", "CG"], ["NOSE", "Nose"], ["TAIL", "Tail"], ["COCKPIT", "Cockpit"]];

function cameraPosition(keyframe) {
  if (!keyframe.position) {
    keyframe.position = { frame: "BODY", ref: "CG", x_m: 0, y_m: 0, z_m: 0 };
  }
  return keyframe.position;
}

function cockpitOf(keyframe) {
  if (!keyframe.cockpit) keyframe.cockpit = { view: "PILOT", index: 0, zoom_pct: null };
  return keyframe.cockpit;
}

/** One cell whose meaning follows the frame, so the table stays narrow
 *  instead of carrying three body columns and three world columns. */
function positionColumn(label, bodyKey, worldKey, horizonKey, group) {
  return {
    label,
    group,
    width: "11ch",
    title: "Metres from the aircraft, orbit azimuth/radius/height, or a world coordinate",
    get: (k) => {
      const position = cameraPosition(k);
      if (position.frame === "HORIZON") return fixed(position[horizonKey], 1);
      return position.frame === "BODY"
        ? fixed(position[bodyKey], 1) : fixed(position[worldKey], 6);
    },
    set: (k, v) => {
      const position = cameraPosition(k);
      const key = position.frame === "HORIZON" ? horizonKey
        : position.frame === "BODY" ? bodyKey : worldKey;
      position[key] = number(v, position[key]);
    },
    enabled: (k) => k.camera_type !== "COCKPIT",
  };
}

const CAMERA_COLUMNS = [
  { label: "Time s", width: "8ch", get: (k) => fixed(k.time_offset, 2),
    set: (k, v) => { k.time_offset = Math.max(0, number(v)); } },
  { label: "Type", group: true, choices: [["CINEMATIC", "Cinematic"], ["COCKPIT", "Cockpit"]],
    get: (k) => k.camera_type, set: (k, v) => { k.camera_type = v; } },
  { label: "Join",
    title: "Blend continues the interpolate. New shot cuts here and starts a new one. "
      + "Cut jumps here for Hold s, then snaps back.",
    choices: [["BLEND", "Blend"], ["SHOT", "New shot"], ["CUT", "Cutaway"]],
    get: (k) => k.transition || "BLEND",
    set: (k, v) => {
      k.transition = v;
      if (v === "CUT" && !(k.easing.hold_s > 0)) k.easing.hold_s = 3;
    } },
  { label: "View", choicesOf: (k) => cockpitViewOptions(cockpitOf(k)),
    get: (k) => cockpitChoice(cockpitOf(k)),
    set: (k, v) => { applyCockpitChoice(cockpitOf(k), v); },
    enabled: (k) => k.camera_type === "COCKPIT" },
  { label: "View #", width: "6ch", title: "Instrument or quickview number (from 0)",
    get: (k) => String(cockpitOf(k).index ?? 0),
    set: (k, v) => { cockpitOf(k).index = Math.max(0, Math.round(number(v, 0))); },
    enabled: (k) => k.camera_type === "COCKPIT" && isNumberedView(cockpitOf(k).view) },
  { label: "Zoom %", width: "7ch", placeholder: "sim",
    get: (k) => (cockpitOf(k).zoom_pct === null || cockpitOf(k).zoom_pct === undefined
      ? "" : String(cockpitOf(k).zoom_pct)),
    set: (k, v) => { cockpitOf(k).zoom_pct = v.trim() === "" ? null : number(v, 50); },
    enabled: (k) => k.camera_type === "COCKPIT" },
  { label: "Frame", choices: [["BODY", "Aircraft"], ["HORIZON", "Orbit"], ["WORLD", "World"]],
    get: (k) => cameraPosition(k).frame,
    set: (k, v) => {
      k.position = v === "BODY"
        ? { frame: "BODY", ref: "CG", x_m: -70, y_m: 25, z_m: -130 }
        : v === "HORIZON"
          ? { frame: "HORIZON", azimuth_deg: 0, radius_m: 80, height_m: 15 }
          : { frame: "WORLD", lat: state.doc.flight_keyframes[0].lat,
              lon: state.doc.flight_keyframes[0].lon, alt_ft_msl: 2500 };
    },
    enabled: (k) => k.camera_type !== "COCKPIT" },
  { label: "Anchor", choices: AIRCRAFT_REFS,
    get: (k) => cameraPosition(k).ref || "CG",
    set: (k, v) => { cameraPosition(k).ref = v; },
    enabled: (k) => k.camera_type !== "COCKPIT" && cameraPosition(k).frame === "BODY" },
  positionColumn("Right m / lat / az°", "x_m", "lat", "azimuth_deg", true),
  positionColumn("Up m / lon / height m", "y_m", "lon", "height_m"),
  positionColumn("Fwd m / alt / radius m", "z_m", "alt_ft_msl", "radius_m"),
  { label: "Aim", group: true,
    choices: [["AIRCRAFT_POINT", "Aircraft"], ["AIRCRAFT_OFFSET", "Offset"],
              ["WORLD_POINT", "World point"], ["FREE", "Fixed angles"]],
    get: (k) => k.look_at.mode,
    set: (k, v) => {
      if (v === "AIRCRAFT_POINT") k.look_at = { mode: "AIRCRAFT_POINT", ref: "CG" };
      else if (v === "AIRCRAFT_OFFSET") k.look_at = { mode: "AIRCRAFT_OFFSET", x_m: -15, y_m: 0, z_m: 0 };
      else if (v === "WORLD_POINT") k.look_at = {
        mode: "WORLD_POINT", lat: state.doc.flight_keyframes[0].lat,
        lon: state.doc.flight_keyframes[0].lon, alt_ft_msl: 2500 };
      else k.look_at = { mode: "FREE", pitch_deg: 0, heading_deg: 0 };
    },
    enabled: (k) => k.camera_type !== "COCKPIT" },
  { label: "Aim target", width: "18ch",
    title: "Aircraft point, offset right,height,fwd m, or lat,lon,alt, or pitch,heading",
    choicesOf: (k) => (k.look_at.mode === "AIRCRAFT_POINT" ? AIRCRAFT_REFS : null),
    get: (k) => {
      const aim = k.look_at;
      if (aim.mode === "AIRCRAFT_POINT") return aim.ref;
      if (aim.mode === "AIRCRAFT_OFFSET") {
        return `${fixed(aim.x_m, 1)},${fixed(aim.y_m, 1)},${fixed(aim.z_m, 1)}`;
      }
      if (aim.mode === "WORLD_POINT") {
        return `${fixed(aim.lat, 5)},${fixed(aim.lon, 5)},${fixed(aim.alt_ft_msl, 0)}`;
      }
      return `${fixed(aim.pitch_deg, 1)},${fixed(aim.heading_deg, 1)}`;
    },
    set: (k, v) => {
      const aim = k.look_at;
      if (aim.mode === "AIRCRAFT_POINT") { aim.ref = v; return; }
      const parts = v.split(/[,\s]+/).filter(Boolean).map(Number);
      if (aim.mode === "AIRCRAFT_OFFSET") {
        if (parts.length >= 1 && Number.isFinite(parts[0])) aim.x_m = parts[0];
        if (parts.length >= 2 && Number.isFinite(parts[1])) aim.y_m = parts[1];
        if (parts.length >= 3 && Number.isFinite(parts[2])) aim.z_m = parts[2];
      } else if (aim.mode === "WORLD_POINT") {
        if (parts.length >= 1 && Number.isFinite(parts[0])) aim.lat = parts[0];
        if (parts.length >= 2 && Number.isFinite(parts[1])) aim.lon = parts[1];
        if (parts.length >= 3 && Number.isFinite(parts[2])) aim.alt_ft_msl = parts[2];
      } else {
        if (parts.length >= 1 && Number.isFinite(parts[0])) aim.pitch_deg = parts[0];
        if (parts.length >= 2 && Number.isFinite(parts[1])) aim.heading_deg = parts[1];
      }
    },
    enabled: (k) => k.camera_type !== "COCKPIT" },
  { label: "Up", choices: [["WORLD_UP", "World"], ["AIRCRAFT_UP", "Aircraft"]],
    get: (k) => k.up.mode, set: (k, v) => { k.up.mode = v; },
    enabled: (k) => k.camera_type !== "COCKPIT" },
  { label: "FOV", group: true, width: "7ch", placeholder: "sim",
    get: (k) => (k.fov_deg === null || k.fov_deg === undefined ? "" : String(k.fov_deg)),
    set: (k, v) => { k.fov_deg = v.trim() === "" ? null : number(v, 60); } },
  ...easingColumns(),
  { label: "m from aircraft", group: true, derived: (k) => {
      const position = cameraPosition(k);
      if (k.camera_type === "COCKPIT") return "—";
      if (position.frame === "HORIZON") return Math.round(position.radius_m);
      if (position.frame !== "BODY") return "—";
      return Math.round(Math.hypot(position.x_m, position.y_m, position.z_m));
    } },
];

/** Percent in the cell, -1..1 in the document. Blank holds the last value. */
function percentColumn(label, key, lowest = -100) {
  return {
    label,
    width: "7ch",
    placeholder: "hold",
    title: "Percent of full travel. Blank keeps whatever the control was doing.",
    get: (k) => (k[key] === null || k[key] === undefined ? "" : percentText(k[key])),
    set: (k, raw) => {
      k[key] = raw.trim() === ""
        ? null : Math.min(100, Math.max(lowest, number(raw))) / 100;
    },
    classOf: (k) => (k[key] === null || k[key] === undefined ? "" : "manual"),
  };
}

const SYSTEMS_COLUMNS = [
  { label: "Time s", width: "8ch", get: (k) => fixed(k.time_offset, 2),
    set: (k, v) => { k.time_offset = Math.max(0, number(v)); } },
  { label: "Flaps", group: true, width: "7ch", placeholder: "hold",
    title: "Handle detent, 0 = up. Blank keeps the last value.",
    get: (k) => (k.flaps == null ? "" : String(k.flaps)),
    set: (k, v) => {
      k.flaps = v.trim() === "" ? null : Math.max(0, Math.round(number(v)));
    } },
  { label: "Gear", width: "8ch",
    title: "Hold keeps the last value until the next keyframe.",
    choices: [["", "Hold"], ["UP", "Up"], ["DOWN", "Down"]],
    get: (k) => (k.gear_down === true ? "DOWN" : k.gear_down === false ? "UP" : ""),
    set: (k, v) => {
      const raw = String(v).trim().toLowerCase();
      k.gear_down = raw === "" || raw === "hold" ? null
        : /^(down|yes|true|1)$/.test(raw) ? true : false;
    } },
  { ...percentColumn("Aileron %", "aileron"), group: true },
  percentColumn("Elevator %", "elevator"),
  percentColumn("Rudder %", "rudder"),
  percentColumn("Throttle %", "throttle", 0),
];

const CONTROL_COLUMNS = [
  { label: "Time s", width: "8ch", get: (k) => fixed(k.time_offset, 2),
    set: (k, v) => { k.time_offset = Math.max(0, number(v)); } },
  { ...percentColumn("Aileron %", "aileron"), group: true },
  percentColumn("Elevator %", "elevator"),
  percentColumn("Rudder %", "rudder"),
  percentColumn("Throttle %", "throttle", 0),
  percentColumn("Trim %", "elevator_trim"),
  { label: "Transition", group: true, choices: [["RAMP", "Ramp"], ["STEP", "Step"]],
    get: (k) => k.transition, set: (k, v) => { k.transition = v; } },
  // What the last take actually did at this moment, so an input can be judged
  // by its effect without leaving the table.
  { label: "rec kt", group: true, derived: (k) => fixed(recordedAt(k.time_offset)?.airspeed_kt, 0) },
  { label: "rec ft", derived: (k) => fixed(recordedAt(k.time_offset)?.alt_ft_msl, 0) },
  { label: "rec bank°", derived: (k) => fixed(recordedAt(k.time_offset)?.bank_deg, 1) },
];

const columnsFor = (track) => (track === "flight" ? FLIGHT_COLUMNS
  : track === "controls" ? CONTROL_COLUMNS
  : track === "systems" ? SYSTEMS_COLUMNS : CAMERA_COLUMNS);
const listFor = (track) => {
  if (track === "flight") return state.doc.flight_keyframes;
  if (track === "controls") return state.doc.sim_flight?.controls || [];
  if (track === "systems") {
    if (!state.doc.systems) state.doc.systems = [];
    return state.doc.systems;
  }
  return state.doc.camera_keyframes;
};

function solvedAtTime(t) {
  return nearestByTime(state.preview?.samples || [], t);
}

function renderTable() {
  const table = $("tbl");
  const columns = columnsFor(TABLE.track);
  const list = listFor(TABLE.track);
  table.innerHTML = "";
  TABLE.rows = [];

  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  headRow.appendChild(document.createElement("th"));
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.textContent = column.label;
    if (column.title) cell.title = column.title;
    if (column.group) cell.className = "group-start";
    headRow.appendChild(cell);
  }
  headRow.appendChild(document.createElement("th"));
  head.appendChild(headRow);
  table.appendChild(head);

  const body = document.createElement("tbody");
  list.forEach((keyframe) => body.appendChild(buildRow(keyframe, columns)));
  table.appendChild(body);

  refreshDerived();
  renderTableDiagnostics();
  $("tbl-orbit").hidden = TABLE.track !== "camera";
  $("tbl-hint").textContent = TABLE.track === "flight"
    ? "To next: Straight for runways/finals, Smooth for curves. Leave Heading/Pitch/Bank "
      + "blank to derive them, or type degrees to pin them. Grey kt / path track° / path "
      + "bank° are solved (copied with the table, not pasted back)."
    : TABLE.track === "controls"
    ? "Percent of full travel: + rolls right, + is back stick (nose up), + yaws right. "
      + "Blank keeps the last value. Grey columns are what the last take recorded."
    : TABLE.track === "systems"
    ? "Each row holds flaps and gear from that time until the next. Blank keeps the last "
      + "value. Surfaces are a record of a flown take; playback writes flaps and gear."
    : "Join Blend to shape the current interpolate. New shot cuts to this row and "
      + "starts a fresh interpolate. Cutaway jumps here for Hold s and snaps back. "
      + "Orbit is a level circle (azimuth / height / radius).";
}

function buildRow(keyframe, columns) {
  const row = document.createElement("tr");
  const entry = { keyframe, row, derived: [] };

  // Working in a row selects its keyframe, so the map and the sidebar
  // inspector stay on whatever the operator is editing.
  const reveal = () => {
    const index = listFor(TABLE.track).indexOf(keyframe);
    if (state.track === TABLE.track && state.selected === index) return;
    state.track = TABLE.track;
    if (TABLE.track === "flight" && typeof selectFlight === "function") selectFlight(index);
    else select(index);
    markSelectedRow();
  };
  row.addEventListener("focusin", reveal);

  const index = document.createElement("td");
  index.className = "index";
  index.title = "Select this keyframe on the map";
  index.onclick = reveal;
  row.appendChild(index);

  for (const column of columns) {
    const cell = document.createElement("td");
    if (column.group) cell.className = "group-start";
    if (column.derived) {
      cell.classList.add("derived");
      entry.derived.push({ cell, column });
    } else {
      cell.appendChild(buildControl(keyframe, column));
    }
    row.appendChild(cell);
  }

  const drop = document.createElement("td");
  drop.className = "drop";
  const remove = document.createElement("button");
  remove.textContent = "✕";
  remove.title = "Delete this keyframe";
  remove.onclick = () => removeRow(keyframe);
  drop.appendChild(remove);
  row.appendChild(drop);

  TABLE.rows.push(entry);
  return row;
}

function buildControl(keyframe, column) {
  const choices = column.choicesOf ? column.choicesOf(keyframe) : column.choices;
  if (choices) {
    const element = document.createElement("select");
    for (const [value, label] of choices) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      element.appendChild(option);
    }
    element.value = column.get(keyframe);
    element.disabled = column.enabled ? !column.enabled(keyframe) : false;
    // A mode change swaps which controls belong in the row, so rebuild.
    element.onchange = () => {
      column.set(keyframe, element.value);
      commit(Boolean(column.choices || column.choicesOf), { keyframe });
    };
    return element;
  }

  const input = document.createElement("input");
  input.type = "text";
  input.value = column.get(keyframe);
  input.placeholder = column.placeholder || "";
  input.disabled = column.enabled ? !column.enabled(keyframe) : false;
  if (column.width) input.style.width = column.width;
  if (column.classOf) input.className = column.classOf(keyframe);
  input.onchange = () => {
    column.set(keyframe, input.value);
    input.value = column.get(keyframe);
    if (column.classOf) input.className = column.classOf(keyframe);
    // A time edit re-sorts the list, so the rows have to be rebuilt. Anything
    // else edits in place and leaves the caret alone.
    commit(column.label === "Time s", { keyframe });
  };
  input.onkeydown = (event) => {
    if (event.key === "Enter") input.blur();
  };
  return input;
}

/** Push the edit through the normal pipeline. `afterSolve` picks it up when
 *  the solver has caught up. */
function commit(rebuild, focusHint) {
  TABLE.rebuild = TABLE.rebuild || rebuild;
  TABLE.focus = focusHint || null;
  touched();
}

function afterSolve() {
  // Waypoint-only editor; a program path has no state.doc to tabulate.
  if (!state.doc) return;
  if (typeof tableDockOpen === "function" ? !tableDockOpen() : !$("table-dock") || $("table-dock").hidden) return;
  if (TABLE.rebuild) {
    TABLE.rebuild = false;
    renderTable();
    restoreFocus();
  } else {
    refreshDerived();
    renderTableDiagnostics();
  }
  markSelectedRow();
}

/** Re-sorting rebuilds every control, so put the caret back on the cell the
 *  operator was working in — which may now be in a different row. */
function restoreFocus() {
  if (!TABLE.focus) return;
  const entry = TABLE.rows.find((r) => r.keyframe === TABLE.focus.keyframe);
  TABLE.focus = null;
  if (!entry) return;
  const control = entry.row.querySelectorAll("input, select")[0];
  if (control) control.focus();
}

function refreshDerived() {
  for (const entry of TABLE.rows) {
    const solved = solvedAtTime(entry.keyframe.time_offset);
    for (const { cell, column } of entry.derived) {
      cell.textContent = column.derived(entry.keyframe, solved);
    }
  }
  TABLE.rows.forEach((entry, index) => {
    entry.row.firstChild.textContent = index + 1;
  });
}

function markSelectedRow() {
  const list = listFor(TABLE.track);
  for (const entry of TABLE.rows) {
    const chosen = TABLE.track === "flight" && typeof isFlightIndexSelected === "function"
      ? state.track === "flight" && isFlightIndexSelected(list.indexOf(entry.keyframe))
      : state.track === TABLE.track && list[state.selected] === entry.keyframe;
    entry.row.classList.toggle("selected", chosen);
  }
}

function renderTableDiagnostics() {
  const host = $("tbl-diagnostics");
  host.innerHTML = "";
  for (const item of state.diagnostics) {
    const box = document.createElement("div");
    box.className = `diag ${item.severity}`;
    box.textContent = item.message + (item.at != null ? ` (at ${item.at.toFixed(1)}s)` : "");
    host.appendChild(box);
  }
}

function removeRow(keyframe) {
  const list = listFor(TABLE.track);
  if (list.length <= (TABLE.track === "controls" || TABLE.track === "systems" ? 0 : 1)) return;
  list.splice(list.indexOf(keyframe), 1);
  state.selected = list.length ? Math.min(state.selected ?? 0, list.length - 1) : null;
  state.doc.meta.duration_seconds = lastTime();
  commit(true);
}

function addRow() {
  if (TABLE.track === "flight") {
    const list = state.doc.flight_keyframes;
    const last = list[list.length - 1];
    appendFlightKeyframe(last ? last.lat + 0.005 : 0, last ? last.lon + 0.005 : 0);
  } else if (TABLE.track === "controls") {
    state.track = "controls";
    state.selected = (state.doc.sim_flight?.controls.length || 0) - 1;
    appendControlKeyframe();
  } else if (TABLE.track === "systems") {
    state.track = "systems";
    state.selected = (state.doc.systems?.length || 0) - 1;
    appendSystemsKeyframe();
  } else {
    state.selected = state.doc.camera_keyframes.length - 1;
    appendCameraKeyframe();
  }
  commit(true);
}

// -------------------------------------------------------------- clipboard

function cellText(column, keyframe) {
  if (column.derived) {
    return column.derived(keyframe, solvedAtTime(keyframe.time_offset)) ?? "";
  }
  return column.get(keyframe);
}

function tableToText() {
  // Include solved (grey) columns so a spreadsheet sees speed, track and bank.
  const columns = columnsFor(TABLE.track);
  const lines = [columns.map((c) => c.label).join("\t")];
  for (const keyframe of listFor(TABLE.track)) {
    lines.push(columns.map((c) => cellText(c, keyframe)).join("\t"));
  }
  return lines.join("\n");
}

function textToTable(text, replace) {
  const all = columnsFor(TABLE.track);
  const editable = all.filter((c) => c.set);
  const rows = text.trim().split(/\r?\n/)
    .map((line) => line.split(line.includes("\t") ? "\t" : ","))
    .filter((cells) => cells.length > 1);
  if (!rows.length) return 0;
  // Tolerate a header line, so a round trip through a spreadsheet just works.
  // Prefer matching by label when the header is ours (derived columns included).
  let columns = editable;
  if (!Number.isFinite(parseFloat(rows[0][0]))) {
    const headers = rows.shift().map((h) => h.trim());
    const byLabel = headers.map((label) => all.find((c) => c.label === label) || null);
    if (byLabel.some((c) => c && c.set)) columns = byLabel;
  }
  if (!rows.length) return 0;

  if (TABLE.track === "controls" && !state.doc.sim_flight) createSimFlight();
  // Controls can legitimately start empty, so they need a template of their own.
  const template = () => JSON.parse(JSON.stringify(
    listFor(TABLE.track)[0]
      ?? (TABLE.track === "controls" ? blankControlKeyframe(0)
        : TABLE.track === "systems" ? blankSystemsKeyframe(0) : null)));
  const built = [];
  for (const cells of rows) {
    const keyframe = template();
    if (!keyframe) break;
    if (TABLE.track === "flight" && typeof mintWaypointId === "function") {
      keyframe.id = mintWaypointId();
    }
    cells.forEach((value, index) => {
      const column = columns[index];
      if (column?.set) column.set(keyframe, String(value).trim());
    });
    built.push(keyframe);
  }
  if (!built.length) return 0;

  const list = listFor(TABLE.track);
  if (replace) list.splice(0, list.length, ...built);
  else list.push(...built);
  state.selected = 0;
  state.doc.meta.duration_seconds = lastTime();
  commit(true);
  return built.length;
}

// ---------------------------------------------------------------- wiring

document.querySelectorAll(".table-tab").forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll(".table-tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    TABLE.track = tab.dataset.track;
    renderTable();
  };
});

$("btn-table").onclick = () => {
  if (!state.doc) return;
  TABLE.track = state.track;
  if (typeof map2dMode === "function" && map2dMode() && TABLE.track !== "flight") {
    TABLE.track = "flight";
  }
  document.querySelectorAll(".table-tab").forEach(
    (tab) => tab.classList.toggle("active", tab.dataset.track === TABLE.track));
  if (typeof setDock === "function") setDock("table");
  else renderTable();
};
$("tbl-add").onclick = addRow;
$("tbl-orbit").onclick = openOrbitDialog;

$("tbl-copy").onclick = async () => {
  const text = tableToText();
  try {
    await navigator.clipboard.writeText(text);
    $("tbl-hint").textContent = `Copied ${listFor(TABLE.track).length} rows.`;
  } catch (_) {
    // Clipboard writes need a permission the page may not have; fall back to
    // the paste box so the text is still reachable.
    $("paste-text").value = text;
    $("paste-dialog").showModal();
  }
};

$("tbl-paste").onclick = () => {
  const columns = columnsFor(TABLE.track).filter((c) => c.set);
  $("paste-hint").textContent =
    `Tab- or comma-separated, one row per keyframe, in this column order: `
    + columns.map((c) => c.label).join(", ")
    + ". A header line is used when present (grey/solved columns are skipped). "
    + "Short rows leave the remaining columns alone.";
  $("paste-text").value = "";
  $("paste-dialog").showModal();
};

$("paste-dialog").addEventListener("close", () => {
  if ($("paste-dialog").returnValue !== "apply") return;
  const added = textToTable($("paste-text").value, $("paste-replace").checked);
  $("tbl-hint").textContent = added
    ? `Applied ${added} rows.`
    : "Nothing recognisable in that text.";
});
