/* Harness for the segment path program — see data-backend/flightstudio/SEGMENT_MODEL.md.
 *
 * A development surface, not the stage 7 editor. It exists so each primitive
 * can be pushed around by hand as it lands, which is the kind of checking unit
 * tests are bad at: is the arc on the correct side, does the helix climb, does
 * a cut actually break the line.
 *
 * Adding a primitive means adding one entry to PRIMITIVES in programFields.js.
 * The form, the sliders and the readouts are all generated from it.
 *
 * Stage 1 draws geometry only. There are deliberately no velocity controls:
 * the profile is carried by the schema but nothing integrates it until stage
 * 2, and a control that silently does nothing is worse than no control.
 */

const ENDPOINT = "/api/flightstudio/program/evaluate/";
const COLORS = ["#4ea3f0", "#f05e6a", "#5ad6a0", "#c08ef0", "#f0b84e", "#5ad6d6", "#f08ebe"];
const BERKELEY = { lat: 37.8716, lon: -122.2727, alt_ft_msl: 2000 };

const el = (id) => document.getElementById(id);
const color = (index) => COLORS[index % COLORS.length];

// Field schema lives in programFields.js (shared with the main-app editor).
const {
  get, set, speedCoefficients, SPEED_FIELDS, newVelocity, newBoundary,
  PRIMITIVES, SOLVER_PARAMETERS, readField, writeField, isSolverParameter,
} = ProgramFields;

function motionFields(segment) {
  return ProgramFields.motionFields(segment, speedMode);
}
// ---------------------------------------------------------------- presets

const build = (segments, origin) =>
  ({ schema_version: 1, origin: { ...(origin || BERKELEY) }, segments });

const line = (name, extra) =>
  ({ kind: "LINE_TO", name, heading_deg: 0, climb_deg: 0, distance_m: 1500,
     inherit_direction: false, velocity: newVelocity(), end: newBoundary(), ...extra });
const arc = (name, extra) =>
  ({ kind: "ARC", name, side: "LEFT", radius_m: 800, sweep_deg: 90, tilt_deg: 0,
     rise_per_turn_m: null, velocity: newVelocity(), end: newBoundary(), ...extra });
const hermite = (name, extra) =>
  ({ kind: "HERMITE", name, out: null,
     into: { heading_deg: 90, climb_deg: 0, length_m: 500 },
     velocity: newVelocity(), end: newBoundary(), ...extra });
const cp = (lat, lon, alt = 2000, weight = 1) =>
  ({ lat, lon, alt_ft_msl: alt, weight });

const PRESETS = {
  "figure eight": () => build([
    line("Entry", { distance_m: 1200 }),
    arc("Left loop", { side: "LEFT", radius_m: 700, sweep_deg: 360 }),
    arc("Right loop", { side: "RIGHT", radius_m: 700, sweep_deg: 360 }),
    line("Exit", { distance_m: 1200, inherit_direction: true }),
  ]),
  "circuit": () => build([
    line("North straight", { distance_m: 3000 }),
    arc("North turn", { side: "RIGHT", sweep_deg: 180 }),
    line("South straight", { distance_m: 3000, inherit_direction: true }),
    arc("South turn", { side: "RIGHT", sweep_deg: 180 }),
  ]),
  "helix": () => build([
    line("Climbing entry", { heading_deg: 45, climb_deg: 8, distance_m: 2500 }),
    arc("Three turns up", { radius_m: 900, sweep_deg: 1080 }),
    line("Exit", { distance_m: 2500, inherit_direction: true }),
  ]),
  "banked circle": () => build([
    line("Entry", { distance_m: 1500 }),
    arc("Banked circle", { radius_m: 1200, sweep_deg: 360, tilt_deg: 25 }),
  ]),
  "cut (MoveTo seam)": () => build([
    line("Before the cut", { distance_m: 2500 }),
    { kind: "MOVE_TO", name: "Cut to the far side",
      to: { lat: 37.82, lon: -122.34, alt_ft_msl: 4500 },
      tangent: { heading_deg: 90, climb_deg: 0 }, speed_ms: 100, end: newBoundary() },
    line("After the cut", { distance_m: 2500, inherit_direction: true }),
  ]),
  "hermite S-curve": () => build([
    line("Run-up", { distance_m: 800 }),
    hermite("S-bend", {
      to: { lat: 37.9000, lon: -122.2500, alt_ft_msl: 2500 },
      into: { heading_deg: 120, climb_deg: 0, length_m: 700 },
    }),
    line("Carry on", { distance_m: 1200, inherit_direction: true }),
  ]),
  "fitted spline": () => build([
    // A four-point hull that bows east then north — control points are the
    // representation, so dragging one reshapes only its neighbourhood.
    { kind: "SPLINE", name: "Coast",
      degree: 3,
      control_points: [
        cp(37.8716, -122.2727),
        cp(37.8800, -122.2550, 2200),
        cp(37.8950, -122.2500, 2100),
        cp(37.9100, -122.2600, 2000),
      ],
      velocity: newVelocity(), end: newBoundary(),
      construction: {
        kind: "FIT_POINTS", tolerance_m: 40,
        points: [
          { lat: 37.8716, lon: -122.2727, alt_ft_msl: 2000 },
          { lat: 37.8800, lon: -122.2550, alt_ft_msl: 2200 },
          { lat: 37.8950, lon: -122.2500, alt_ft_msl: 2100 },
          { lat: 37.9100, lon: -122.2600, alt_ft_msl: 2000 },
        ],
        produced: [],
      },
    },
  ]),
  "pinned endpoints": () => build([
    // Stored at 300 m but constrained 2 km away: the solver works the
    // heading and distance backwards until the leg lands on the pin.
    line("Fly to the pin", { distance_m: 300,
      constraints: [constraint(37.8930, -122.2560, 2000)] }),
    // Radius and plane held, so only the sweep is left to find. With one
    // unknown against three equations the target has to sit on the circle,
    // which this one does — drag it off and the card says by how much.
    arc("Round to the next", { side: "RIGHT", radius_m: 900, sweep_deg: 30,
      pinned: ["radius_m", "tilt_deg"],
      constraints: [constraint(37.893779, -122.239231, 2000)] }),
    line("Carry on", { distance_m: 1500, inherit_direction: true }),
  ]),
  "accelerate and hold": () => build([
    line("Slow approach", { distance_m: 2000,
      velocity: { c0: 40, c1: 0, c2: 0, c3: 0, inherit_entry: false },
      end: { dwell_s: 6 } }),
    line("Accelerating away", { distance_m: 4000, inherit_direction: true,
      velocity: speedCoefficientsWith({ entry: 40, exit: 180 }) }),
  ]),
};

const constraint = (lat, lon, alt_ft_msl, extra) =>
  ({ kind: "POINT", at: 1, lat, lon, alt_ft_msl,
     lock_horizontal: true, lock_vertical: true, ...extra });

function speedCoefficientsWith(handles) {
  return {
    ...speedCoefficients({ entry_slope: 0, exit_slope: 0, ...handles }),
    inherit_entry: false,
  };
}

// ------------------------------------------------------------------ state

let speedMode = "handles";
let program = PRESETS["figure eight"]();
let preview = null;
let failure = null;
let activeIndex = null;
let pendingFit = true;
let playheadS = 0;
let playing = false;
let chart = "altitude";

// --------------------------------------------------------------- requests

function authHeaders() {
  const headers = { "Content-Type": "application/json" };
  const token = localStorage.getItem("access_token");
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

let timer = null;
let inFlight = 0;

function schedule() {
  syncJson();
  clearTimeout(timer);
  timer = setTimeout(() => evaluate(), 80);
}

async function evaluate(extra = {}) {
  const ticket = ++inFlight;
  const body = { program, step_m: Number(el("step").value) || 20, ...extra };
  let response;
  try {
    response = await fetch(ENDPOINT, {
      method: "POST", headers: authHeaders(), credentials: "include",
      body: JSON.stringify(body),
    });
  } catch (error) {
    return showFailure({ detail: `Could not reach the backend: ${error.message}` });
  }
  // A dragged slider fires far faster than the round trip, so drop any reply
  // that has already been overtaken rather than letting them race.
  if (ticket !== inFlight) return;

  const payload = await response.json().catch(() => ({ detail: response.statusText }));
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      return showFailure({ detail: "Not signed in. Open the main app, log in, then reload this page." });
    }
    return showFailure(payload);
  }
  failure = null;
  preview = payload;
  el("error").hidden = true;
  // Solving moves parameters and retiming rescales them, so what came back
  // is not what went out. Adopt it, or the inspector would show numbers the
  // curve does not have.
  if (payload.constrained || extra.fit_duration_s) {
    program = payload.solved_program;
    restoringFocus(() => renderEditor());
    syncJson();
  }
  drawMap();
  refreshReadouts();
  setPlayhead(playheadS);
}

/* Rebuilding the editor under a pointer that is mid-drag drops the control.
 * Put the caret and the focus back where they were, keyed on the card and
 * the field rather than on the node, which no longer exists. */
function restoringFocus(rebuild) {
  const active = document.activeElement;
  const card = active && active.closest && active.closest(".card");
  const path = active && active.dataset && active.dataset.path;
  const where = card ? card.dataset.index : null;
  const caret = active && active.selectionStart;
  rebuild();
  if (!path || where === null) return;
  const restored = document.querySelector(
    `.card[data-index="${where}"] [data-path="${CSS.escape(path)}"]`);
  if (!restored) return;
  restored.focus();
  try { restored.setSelectionRange(caret, caret); } catch { /* not a text input */ }
}

function showFailure(payload) {
  failure = payload;
  preview = null;
  const where = typeof payload.index === "number" ? `<b>segment ${payload.index + 1}</b> — ` : "";
  const detail = payload.errors && payload.errors.length
    ? payload.errors.map((e) => `${(e.loc || []).join(".")}: ${e.msg}`).join("; ")
    : (payload.detail || "Unknown error");
  el("error").innerHTML = where + detail;
  el("error").hidden = false;
  // Clear both views rather than one. Leaving the last good geometry up next
  // to an error reads as though the broken parameters produced it.
  drawn.clearLayers();
  drawChart();
  refreshReadouts();
}

// ------------------------------------------------------------------ forms
//
// Discrete edits — a checkbox, a dropdown, adding or removing a segment —
// rebuild the card, since they can change which fields apply. Continuous ones
// must not: rebuilding mid-drag would drop the slider out from under the
// pointer.

function commit(rebuild) {
  if (rebuild) renderEditor();
  schedule();
}

function pinButton(segment, key) {
  if (!isSolverParameter(segment, key)) return null;
  const button = document.createElement("button");
  button.className = "pin";
  button.textContent = "\u25c9";
  const held = (segment.pinned || []).includes(key);
  button.classList.toggle("on", held);
  button.title = held
    ? `${key} is pinned — the solver will not move it`
    : `pin ${key} so the solver leaves it alone`;
  button.onclick = () => {
    const pinned = new Set(segment.pinned || []);
    if (held) pinned.delete(key); else pinned.add(key);
    segment.pinned = [...pinned].sort();
    commit(true);
  };
  return button;
}

function numberRow(segment, spec, disabled) {
  const row = document.createElement("div");
  row.className = "row";

  const label = document.createElement("label");
  label.textContent = spec.unit ? `${spec.label} (${spec.unit})` : spec.label;
  row.appendChild(label);

  const slider = spec.type === "plain" ? null : document.createElement("input");
  const box = document.createElement("input");
  box.type = "number";
  box.step = spec.step ?? 1;
  box.value = round(readField(segment, spec));
  box.disabled = disabled;

  if (slider) {
    slider.type = "range";
    slider.min = spec.min;
    slider.max = spec.max;
    slider.step = spec.step ?? 1;
    slider.value = readField(segment, spec);
    slider.disabled = disabled;
    slider.oninput = () => {
      box.value = slider.value;
      writeField(segment, spec, Number(slider.value));
      commit(false);
    };
    row.appendChild(slider);
  } else {
    box.style.gridColumn = "2 / 4";
  }
  box.oninput = () => {
    if (slider) slider.value = box.value;
    writeField(segment, spec, Number(box.value));
    commit(false);
  };
  box.dataset.path = spec.key;
  row.appendChild(box);
  const pin = pinButton(segment, spec.key);
  if (pin) {
    row.appendChild(pin);
    row.classList.toggle("pinned", pin.classList.contains("on"));
  }
  if (disabled) row.style.opacity = 0.4;
  return row;
}

const round = (value) => Math.abs(value % 1) < 1e-9 ? value : Number(value.toFixed(4));

function checkboxRow(segment, spec) {
  const row = document.createElement("div");
  row.className = "row";
  const label = document.createElement("label");
  label.textContent = spec.label;
  const box = document.createElement("input");
  box.type = "checkbox";
  box.style.gridColumn = "2 / 4";
  const value = get(segment, spec.key);
  box.checked = spec.type === "bool" ? !!value : value !== null && value !== undefined;
  box.onchange = () => {
    set(segment, spec.key,
      spec.type === "bool" ? box.checked : (box.checked ? { ...spec.defaults } : null));
    commit(true);
  };
  row.append(label, box);
  return row;
}

function selectRow(segment, spec) {
  const row = document.createElement("div");
  row.className = "row";
  const label = document.createElement("label");
  label.textContent = spec.label;
  const select = document.createElement("select");
  select.style.gridColumn = "2 / 4";
  for (const option of spec.options) {
    const node = document.createElement("option");
    node.value = node.textContent = option;
    select.appendChild(node);
  }
  select.value = get(segment, spec.key);
  select.onchange = () => { set(segment, spec.key, select.value); commit(true); };
  row.append(label, select);
  const pin = pinButton(segment, spec.key);
  if (pin) {
    select.style.gridColumn = "2 / 4";
    row.appendChild(pin);
    row.classList.toggle("pinned", pin.classList.contains("on"));
  }
  return row;
}

/* A value that may be null, where null means "work it out from the pen".
 * Renders as a checkbox plus, when overridden, the usual slider and box. */
function nullableRows(segment, spec) {
  const rows = [];
  const isAuto = get(segment, spec.key) === null || get(segment, spec.key) === undefined;

  const row = document.createElement("div");
  row.className = "row";
  const label = document.createElement("label");
  label.textContent = spec.label;
  const wrap = document.createElement("label");
  wrap.style.cssText = "display:flex;gap:6px;align-items:center;color:var(--dim);font-size:11.5px;grid-column:2/4";
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = isAuto;
  box.onchange = () => {
    set(segment, spec.key, box.checked ? null : (spec.fallback ?? 0));
    commit(true);
  };
  wrap.append(box, spec.autoLabel || "auto");
  row.append(label, wrap);
  rows.push(row);

  if (!isAuto) rows.push(numberRow(segment, { ...spec, type: "number", label: "\u21b3 value" }, false));
  return rows;
}

// --------------------------------------------------------- constraints
//
// Somewhere the curve must pass through. The solver moves whatever is not
// pinned until it does, so these are the other half of the pin buttons:
// pins say what may not move, constraints say where the result must land.

function controlPointRows(segment) {
  const rows = [];
  (segment.control_points || []).forEach((point, slot) => {
    const row = document.createElement("div");
    row.className = "constraint";
    const number = (key, step, width) => {
      const box = document.createElement("input");
      box.type = "number";
      box.step = step;
      box.value = point[key];
      box.style.flex = width;
      box.title = `control_points.${slot}.${key}`;
      box.dataset.path = `control_points.${slot}.${key}`;
      box.oninput = () => { point[key] = Number(box.value); commit(false); };
      return box;
    };
    const remove = document.createElement("button");
    remove.textContent = "\u2715";
    remove.title = "drop this control point";
    remove.disabled = segment.control_points.length <= segment.degree + 1;
    remove.onclick = () => {
      segment.control_points.splice(slot, 1);
      commit(true);
    };
    row.append(
      number("lat", 0.0001, "1.2"),
      number("lon", 0.0001, "1.2"),
      number("alt_ft_msl", 50, "0.9"),
      number("weight", 0.1, "0.6"),
      remove,
    );
    rows.push(row);
  });
  const add = document.createElement("button");
  add.textContent = "+ control point";
  add.style.gridColumn = "1 / -1";
  add.onclick = () => {
    const last = segment.control_points[segment.control_points.length - 1];
    segment.control_points.push({
      lat: Number((last.lat + 0.005).toFixed(6)),
      lon: Number((last.lon + 0.005).toFixed(6)),
      alt_ft_msl: last.alt_ft_msl,
      weight: 1,
    });
    commit(true);
  };
  rows.push(add);
  return rows;
}

function constraintRows(segment, index) {
  const rows = [];
  (segment.constraints || []).forEach((constraint, slot) => {
    const row = document.createElement("div");
    row.className = "constraint";

    const number = (key, step, width) => {
      const box = document.createElement("input");
      box.type = "number";
      box.step = step;
      box.value = constraint[key];
      box.style.flex = width;
      box.title = key;
      box.dataset.path = `constraints.${slot}.${key}`;
      box.oninput = () => { constraint[key] = Number(box.value); commit(false); };
      return box;
    };
    const lock = (key, label) => {
      const wrap = document.createElement("label");
      wrap.className = "lock";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = constraint[key];
      box.onchange = () => { constraint[key] = box.checked; commit(true); };
      wrap.append(box, label);
      return wrap;
    };

    const remove = document.createElement("button");
    remove.textContent = "\u2715";
    remove.title = "drop this constraint";
    remove.onclick = () => { segment.constraints.splice(slot, 1); commit(true); };

    row.append(number("lat", 0.0001, "1.3"), number("lon", 0.0001, "1.3"));
    if (constraint.lock_vertical) row.append(number("alt_ft_msl", 100, "1"));
    row.append(number("at", 0.05, "0.7"), remove);
    rows.push(row);

    const locks = document.createElement("div");
    locks.className = "constraint";
    locks.style.marginTop = "-2px";
    locks.append(lock("lock_horizontal", "where"), lock("lock_vertical", "altitude"));
    rows.push(locks);
  });

  const add = document.createElement("button");
  add.textContent = "+ constraint";
  add.style.gridColumn = "1 / -1";
  add.title = "require the curve to pass through a point";
  add.onclick = () => {
    // Seed from where the segment currently ends, so adding one changes
    // nothing until it is dragged. A constraint that moves the path the
    // moment it appears would make the gesture unusable.
    const summary = preview && preview.segments[index];
    const end = summary ? summary.end : { lat: program.origin.lat, lon: program.origin.lon, alt_ft: program.origin.alt_ft_msl };
    segment.constraints = segment.constraints || [];
    segment.constraints.push({
      kind: "POINT", at: 1, lat: Number(end.lat.toFixed(6)), lon: Number(end.lon.toFixed(6)),
      alt_ft_msl: Math.round(end.alt_ft), lock_horizontal: true, lock_vertical: true,
    });
    commit(true);
  };
  rows.push(add);
  return rows;
}

function card(segment, index) {
  const node = document.createElement("div");
  node.className = "card";
  node.dataset.index = index;
  node.style.borderLeftColor = color(index);
  node.onmouseenter = () => setActive(index);
  node.onmouseleave = () => setActive(null);

  const head = document.createElement("header");
  head.style.cssText = "display:flex;align-items:center;gap:6px";
  const kind = document.createElement("span");
  kind.className = "kind";
  kind.textContent = PRIMITIVES[segment.kind].label;
  const name = document.createElement("input");
  name.className = "name";
  name.value = segment.name || "";
  name.placeholder = "name";
  name.oninput = () => { segment.name = name.value; syncJson(); };
  const spacer = document.createElement("div");
  spacer.style.flex = "1";
  head.append(kind, name, spacer);

  for (const [glyph, title, action] of [
    ["\u2191", "move up", () => reorder(index, -1)],
    ["\u2193", "move down", () => reorder(index, 1)],
    ["\u2715", "delete", () => remove(index)],
  ]) {
    const button = document.createElement("button");
    button.className = "ghost";
    button.textContent = glyph;
    button.title = title;
    button.onclick = action;
    head.appendChild(button);
  }
  node.appendChild(head);

  const addFields = (specs) => {
    for (const spec of specs) {
      if (spec.hiddenWhen && spec.hiddenWhen(segment)) continue;
      const disabled = spec.disabledWhen ? spec.disabledWhen(segment) : false;
      if (spec.type === "bool" || spec.type === "toggleObject") {
        node.appendChild(checkboxRow(segment, spec));
      } else if (spec.type === "select") {
        node.appendChild(selectRow(segment, spec));
      } else if (spec.type === "nullable") {
        for (const row of nullableRows(segment, spec)) node.appendChild(row);
      } else {
        node.appendChild(numberRow(segment, spec, disabled));
      }
      if (spec.help) {
        const help = document.createElement("div");
        help.className = "help";
        help.textContent = spec.help;
        node.appendChild(help);
      }
    }
  };

  const group = (title) => {
    const rule = document.createElement("div");
    rule.className = "group";
    rule.textContent = title;
    node.appendChild(rule);
  };

  addFields(PRIMITIVES[segment.kind].fields);
  if (segment.kind === "SPLINE") {
    group("control points");
    for (const row of controlPointRows(segment)) node.appendChild(row);
  }
  group("motion");
  addFields(motionFields(segment));
  group("constraints");
  for (const row of constraintRows(segment, index)) node.appendChild(row);

  const readout = document.createElement("div");
  readout.className = "readout";
  node.appendChild(readout);
  return node;
}

function renderEditor() {
  const host = el("segments");
  host.textContent = "";
  program.segments.forEach((segment, index) => host.appendChild(card(segment, index)));
  refreshReadouts();
}

function refreshReadouts() {
  document.querySelectorAll("#segments .card").forEach((node) => {
    const index = Number(node.dataset.index);
    const summary = preview && preview.segments[index];
    const readout = node.querySelector(".readout");
    node.classList.toggle("bad", !!failure && failure.index === index);
    if (!summary) { readout.textContent = ""; return; }
    const timing = summary.timing;
    const parts = [
      ["length", `${summary.length_m.toFixed(0)} m`],
      ["duration", `${timing.duration_s.toFixed(2)} s`],
      ["exit heading", `${summary.exit.heading.toFixed(1)}\u00b0`],
      ["ends at", `${summary.end.alt_ft.toFixed(0)} ft`],
    ];
    if (timing.entry_speed_ms !== null) {
      parts.push(["speed in / out",
        `${timing.entry_speed_ms.toFixed(0)} \u2192 ${timing.exit_speed_ms.toFixed(0)} m/s`]);
    }
    if (timing.dwell_s > 0) parts.push(["then holds", `${timing.dwell_s.toFixed(1)} s`]);
    if (summary.arc) {
      parts.push(["turns", summary.arc.turns.toFixed(2)]);
      parts.push([
        summary.arc.rise_is_default ? "rise / turn (matched)" : "rise / turn",
        `${summary.arc.rise_per_turn_m.toFixed(0)} m`,
      ]);
    }
    const notes = [];
    if (summary.seam) notes.push('<div class="seam-note" style="grid-column:1/-1">starts after a cut</div>');
    for (const issue of (preview.issues || []).filter((i) => i.id === summary.id || i.index === index)) {
      notes.push(`<div class="seam-note" style="grid-column:1/-1">${issue.detail}</div>`);
    }
    const fit = summary.solvability;
    if (fit && fit.state !== "UNCONSTRAINED") {
      const tone = fit.state === "CONTRADICTORY" ? "bad"
        : fit.state === "UNDER_DETERMINED" ? "short" : "";
      notes.push(`<div class="dof ${tone}">${fit.detail} · ${fit.method}</div>`);
    }
    readout.innerHTML = parts.map(([k, v]) => `<div>${k} <b>${v}</b></div>`).join("") + notes.join("");
  });

  const summary = el("summary");
  if (!preview) { summary.textContent = failure ? "\u2014" : "evaluating\u2026"; return; }
  const dwell = preview.dwell_total_s > 0
    ? ` (${preview.flying_s.toFixed(1)} flying + ${preview.dwell_total_s.toFixed(1)} held)` : "";
  summary.innerHTML = `<b>${preview.segments.length}</b> segments &middot; `
    + `<b>${(preview.length_m / 1000).toFixed(2)}</b> km &middot; `
    + `<b>${preview.duration_s.toFixed(1)}</b> s${dwell}`;
}

// -------------------------------------------------------------- transport

function sampleAtTime(seconds) {
  // The last sample at or before the instant: the state currently being
  // held, not the one coming up. Two rows share an instant wherever the path
  // is discontinuous — either side of a cut, either end of a hold — and
  // taking the last of them is what makes the readout right-continuous,
  // agreeing with the model about which side of a cut an instant falls on.
  const rows = preview.samples;
  let low = 0;
  let high = rows.length - 1;
  while (low < high) {
    const middle = (low + high + 1) >> 1;
    if (rows[middle].t <= seconds) low = middle; else high = middle - 1;
  }
  return rows[low];
}

function setPlayhead(seconds) {
  if (!preview) return;
  playheadS = Math.min(preview.duration_s, Math.max(0, seconds));
  const slider = el("playhead");
  slider.max = preview.duration_s || 1;
  slider.value = playheadS;
  el("clock").textContent = `${playheadS.toFixed(2)} s`;
  const row = sampleAtTime(playheadS);
  el("pose").innerHTML = row
    ? `hdg <b>${row.heading.toFixed(0)}\u00b0</b> &middot; pitch <b>${row.climb.toFixed(1)}\u00b0</b>`
      + ` &middot; bank <b>${row.bank.toFixed(1)}\u00b0</b> &middot; <b>${row.speed_ms.toFixed(0)}</b> m/s`
      + ` &middot; <b>${row.alt_ft.toFixed(0)}</b> ft`
    : "";
  drawPlayhead(row);
  drawChart();
}

function drawPlayhead(row) {
  if (!row) return;
  if (!drawPlayhead.marker) {
    drawPlayhead.marker = L.circleMarker([row.lat, row.lon], {
      radius: 6, color: "#fff", weight: 2, fillColor: "#f0b84e", fillOpacity: 1,
    });
  }
  drawPlayhead.marker.setLatLng([row.lat, row.lon]);
  if (!map.hasLayer(drawPlayhead.marker)) drawPlayhead.marker.addTo(map);
}

function tick(now) {
  if (!playing) return;
  const elapsed = (now - tick.last) / 1000;
  tick.last = now;
  // Loop rather than stop, so a short seam can be watched over and over.
  setPlayhead(playheadS + elapsed >= preview.duration_s ? 0 : playheadS + elapsed);
  requestAnimationFrame(tick);
}

function setPlaying(next) {
  playing = next && !!preview;
  el("play").innerHTML = playing ? "&#10073;&#10073;" : "&#9654;";
  if (playing) {
    tick.last = performance.now();
    requestAnimationFrame(tick);
  }
}

function setActive(index) {
  activeIndex = index;
  document.querySelectorAll("#segments .card").forEach((node) => {
    node.classList.toggle("active", Number(node.dataset.index) === index);
  });
  drawMap();
  drawChart();
}

// ------------------------------------------------------------------- edit

function penContext() {
  const last = preview && preview.segments[preview.segments.length - 1];
  return last
    ? { lat: last.end.lat, lon: last.end.lon, alt_ft_msl: last.end.alt_ft }
    : { ...program.origin };
}

function add(kind) {
  program.segments.push(PRIMITIVES[kind].make(penContext()));
  commit(true);
}

function remove(index) {
  program.segments.splice(index, 1);
  commit(true);
}

function reorder(index, delta) {
  const target = index + delta;
  if (target < 0 || target >= program.segments.length) return;
  const [moved] = program.segments.splice(index, 1);
  program.segments.splice(target, 0, moved);
  commit(true);
}

function load(next, fit = true) {
  program = next;
  pendingFit = fit;
  el("origin-lat").value = program.origin.lat;
  el("origin-lon").value = program.origin.lon;
  el("origin-alt").value = program.origin.alt_ft_msl;
  commit(true);
}

function syncJson() {
  const box = el("json");
  if (document.activeElement !== box) box.value = JSON.stringify(program, null, 2);
}

// -------------------------------------------------------------------- map

const map = L.map("map", { zoomControl: true, maxZoom: 20, rotate: false, rotateControl: false });
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  { maxZoom: 20, attribution: "\u00a9 OpenStreetMap" }).addTo(map);
map.setView([BERKELEY.lat, BERKELEY.lon], 13);
const drawn = L.layerGroup().addTo(map);

function strokes() {
  // Split the samples wherever a row says the pen jumped. This is the same
  // contract the real renderer has to honour, so the harness honours it too:
  // if the break flag stops arriving, a line appears across the gap.
  const out = [];
  let current = null;
  for (const row of preview.samples) {
    // A hold sits still, so its rows repeat a point already drawn.
    if (row.hold) continue;
    if (!current || row.break_before || row.segment_id !== current.id) {
      const previous = out[out.length - 1];
      current = { id: row.segment_id, points: [] };
      out.push(current);
      if (!row.break_before && previous && previous.points.length) {
        current.points.push(previous.points[previous.points.length - 1]);
      }
    }
    current.points.push([row.lat, row.lon]);
  }
  return out;
}

function drawMap() {
  drawn.clearLayers();
  if (!preview || !preview.samples.length) return;
  const indexOf = Object.fromEntries(preview.segments.map((s, i) => [s.id, i]));

  for (const segment of preview.segments) {
    const index = indexOf[segment.id];
    if (segment.arc) {
      // The whole circle the arc is a piece of, so a partial sweep still shows
      // what it belongs to and where the centre ended up.
      L.circle([segment.arc.center.lat, segment.arc.center.lon], {
        radius: segment.arc.radius_m, color: color(index),
        weight: 1, opacity: 0.35, dashArray: "3 6", fill: false, interactive: false,
      }).addTo(drawn);
    }
    if (segment.hermite) {
      const h = segment.hermite;
      L.polyline([[segment.start.lat, segment.start.lon],
                  [h.out_tip.lat, h.out_tip.lon]], {
        color: color(index), weight: 1, dashArray: "4 4", opacity: 0.7,
      }).addTo(drawn);
      L.polyline([[segment.end.lat, segment.end.lon],
                  [h.into_tip.lat, h.into_tip.lon]], {
        color: color(index), weight: 1, dashArray: "4 4", opacity: 0.7,
      }).addTo(drawn);
      L.circleMarker([h.out_tip.lat, h.out_tip.lon], {
        radius: 4, color: color(index), weight: 1, fillColor: "#fff", fillOpacity: 0.9,
      }).addTo(drawn).bindTooltip(h.out_default ? "out (from pen)" : "out handle");
      L.circleMarker([h.into_tip.lat, h.into_tip.lon], {
        radius: 4, color: color(index), weight: 1, fillColor: "#fff", fillOpacity: 0.9,
      }).addTo(drawn).bindTooltip("into handle");
    }
    if (segment.spline) {
      const hull = segment.spline.controls.map((p) => [p.lat, p.lon]);
      L.polyline(hull, {
        color: color(index), weight: 1, dashArray: "2 6", opacity: 0.55,
      }).addTo(drawn);
      segment.spline.controls.forEach((point, slot) => {
        const marker = L.circleMarker([point.lat, point.lon], {
          radius: slot === 0 || slot === segment.spline.controls.length - 1 ? 5 : 4,
          color: color(index), weight: 2, fillColor: "#0f141b", fillOpacity: 0.9,
        }).addTo(drawn);
        marker.bindTooltip(`P${slot} · w=${segment.spline.weights[slot]}`);
        // Drag a control point: the hull is authoritative, so this is the
        // free local shaping §7.1 promises — no solve, continuous response.
        marker.on("mousedown", (down) => {
          const authored = program.segments[index];
          if (!authored || !authored.control_points) return;
          map.dragging.disable();
          const move = (event) => {
            authored.control_points[slot].lat = Number(event.latlng.lat.toFixed(6));
            authored.control_points[slot].lon = Number(event.latlng.lng.toFixed(6));
            marker.setLatLng(event.latlng);
            schedule();
          };
          const up = () => {
            map.dragging.enable();
            map.off("mousemove", move).off("mouseup", up);
            renderEditor();
          };
          map.on("mousemove", move).on("mouseup", up);
          L.DomEvent.stop(down);
        });
      });
    }
  }

  for (const segment of preview.segments.filter((s) => s.seam)) {
    const index = indexOf[segment.id];
    const before = preview.segments.slice(0, index).reverse().find((s) => s.length_m > 0);
    if (!before) continue;
    L.polyline([[before.end.lat, before.end.lon], [segment.start.lat, segment.start.lon]],
      { color: "#f0a848", weight: 2, dashArray: "6 7", opacity: 0.85 })
      .addTo(drawn).bindTooltip("cut \u2014 not flown");
  }

  for (const stroke of strokes()) {
    const index = indexOf[stroke.id];
    L.polyline(stroke.points, {
      color: color(index),
      weight: index === activeIndex ? 6 : 3,
      opacity: activeIndex === null || index === activeIndex ? 1 : 0.45,
    }).addTo(drawn);
  }

  const first = preview.samples[0];
  const last = preview.samples[preview.samples.length - 1];
  L.circleMarker([first.lat, first.lon], { radius: 5, color: "#fff", weight: 2,
    fillColor: "#5ad6a0", fillOpacity: 1 }).addTo(drawn).bindTooltip("start");
  L.circleMarker([last.lat, last.lon], { radius: 5, color: "#fff", weight: 2,
    fillColor: "#f05e6a", fillOpacity: 1 }).addTo(drawn).bindTooltip("end");

  drawConstraints(indexOf);

  if (pendingFit) {
    map.fitBounds(L.latLngBounds(preview.samples.map((r) => [r.lat, r.lon])), { padding: [40, 40] });
    pendingFit = false;
  }
}

/* Constraints are draggable, because dragging one is the whole gesture the
 * solver exists for: say where the curve must go and let it work the
 * parameters backwards. A hollow marker so it reads as a demand on the path
 * rather than a point on it. */
function drawConstraints(indexOf) {
  program.segments.forEach((segment, index) => {
    (segment.constraints || []).forEach((constraint, slot) => {
      if (!constraint.lock_horizontal) return;
      const fit = preview.segments[index] && preview.segments[index].solvability;
      const missed = fit && fit.state === "CONTRADICTORY";
      const marker = L.circleMarker([constraint.lat, constraint.lon], {
        radius: 7, weight: 2, color: missed ? "#f05e6a" : "#fff",
        dashArray: missed ? "3 3" : null,
        fillColor: color(index), fillOpacity: 0.35,
      }).addTo(drawn);
      marker.bindTooltip(constraint.at === 1
        ? "pinned end \u2014 drag me" : `through-point at ${constraint.at} \u2014 drag me`);

      // Leaflet only drags markers, not circle markers, so follow the mouse
      // by hand. Suppressing the map's own drag is what keeps the canvas
      // still while the point moves.
      marker.on("mousedown", (down) => {
        map.dragging.disable();
        const move = (event) => {
          constraint.lat = Number(event.latlng.lat.toFixed(6));
          constraint.lon = Number(event.latlng.lng.toFixed(6));
          marker.setLatLng(event.latlng);
          schedule();
        };
        const up = () => {
          map.dragging.enable();
          map.off("mousemove", move).off("mouseup", up);
          renderEditor();
        };
        map.on("mousemove", move).on("mouseup", up);
        L.DomEvent.stop(down);
      });
    });
  });
}

// ------------------------------------------------------------------ chart

const SERIES = {
  altitude: { label: "altitude", field: "alt_ft", unit: "ft", color: "#4ea3f0" },
  speed: { label: "speed", field: "speed_ms", unit: "m/s", color: "#5ad6a0" },
  bank: { label: "bank", field: "bank", unit: "\u00b0", color: "#c08ef0", signed: true },
};

function drawChart() {
  const svg = el("profile");
  svg.innerHTML = "";
  if (!preview || preview.samples.length < 2) return;

  const series = SERIES[chart];
  const total = preview.duration_s || 1;
  const values = preview.samples.map((row) => row[series.field]);
  let low = Math.min(...values);
  let high = Math.max(...values);
  // A signed quantity reads better about zero: a bank chart that autoscales
  // to a tenth of a degree makes level flight look like a rollercoaster.
  if (series.signed) {
    const reach = Math.max(1, Math.abs(low), Math.abs(high));
    low = -reach;
    high = reach;
  }
  const flat = high - low < 1e-6;
  const W = svg.clientWidth || 800;
  const H = svg.clientHeight || 150;
  const PAD = { l: 52, r: 14, t: 12, b: 18 };
  const sx = (t) => PAD.l + (t / total) * (W - PAD.l - PAD.r);
  const sy = (value) => flat
    ? (PAD.t + H - PAD.b) / 2
    : H - PAD.b - ((value - low) / (high - low)) * (H - PAD.t - PAD.b);

  const parts = [
    `<line x1="${PAD.l}" y1="${H - PAD.b}" x2="${W - PAD.r}" y2="${H - PAD.b}" stroke="#273040"/>`,
    `<text x="${W - PAD.r}" y="${H - 4}" fill="#8b96a8" font-size="10" text-anchor="end">${total.toFixed(1)} s</text>`,
  ];
  const mark = (value) => parts.push(
    `<text x="4" y="${sy(value) + 4}" fill="#8b96a8" font-size="10">${value.toFixed(series.signed ? 1 : 0)} ${series.unit}</text>`);
  mark(low);
  if (!flat) mark(high);
  if (series.signed) {
    parts.push(`<line x1="${PAD.l}" y1="${sy(0)}" x2="${W - PAD.r}" y2="${sy(0)}" stroke="#273040" stroke-dasharray="2 4"/>`);
  }

  // A cut is a hole in the geometry, not in the clock, so the line breaks
  // while the time axis carries straight on.
  for (const seam of preview.seam_times) {
    parts.push(`<line x1="${sx(seam).toFixed(1)}" y1="${PAD.t}" x2="${sx(seam).toFixed(1)}" y2="${H - PAD.b}" stroke="#f0a848" stroke-dasharray="3 4" opacity="0.7"/>`);
  }

  const indexOf = Object.fromEntries(preview.segments.map((s, i) => [s.id, i]));
  let path = "";
  preview.samples.forEach((row, index) => {
    const jump = index > 0 && row.break_before;
    path += `${index === 0 || jump ? "M" : "L"}${sx(row.t).toFixed(1)},${sy(row[series.field]).toFixed(1)}`;
  });
  parts.push(`<path d="${path}" fill="none" stroke="${series.color}" stroke-width="1.8"/>`);

  if (activeIndex !== null) {
    const active = preview.samples.filter((row) => indexOf[row.segment_id] === activeIndex);
    if (active.length > 1) {
      const highlight = active
        .map((row, i) => `${i ? "L" : "M"}${sx(row.t).toFixed(1)},${sy(row[series.field]).toFixed(1)}`)
        .join("");
      parts.push(`<path d="${highlight}" fill="none" stroke="${color(activeIndex)}" stroke-width="3.5"/>`);
    }
  }
  const head = sx(playheadS).toFixed(1);
  parts.push(`<line x1="${head}" y1="${PAD.t - 6}" x2="${head}" y2="${H - PAD.b}" stroke="#f0b84e" stroke-width="1.5"/>`);

  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.innerHTML = parts.join("");
}


// ------------------------------------------------------------------- wire

for (const kind of Object.keys(PRIMITIVES)) {
  const button = document.createElement("button");
  button.textContent = `+ ${PRIMITIVES[kind].label}`;
  button.onclick = () => add(kind);
  el("add").appendChild(button);
}

const preset = el("preset");
for (const name of Object.keys(PRESETS)) {
  const option = document.createElement("option");
  option.value = option.textContent = name;
  preset.appendChild(option);
}
preset.value = "figure eight";
preset.onchange = () => { if (preset.value) load(PRESETS[preset.value]()); };

for (const [id, key] of [["origin-lat", "lat"], ["origin-lon", "lon"], ["origin-alt", "alt_ft_msl"]]) {
  el(id).oninput = () => { program.origin[key] = Number(el(id).value); pendingFit = true; schedule(); };
}
el("step").oninput = schedule;

el("speed-mode").onchange = () => { speedMode = el("speed-mode").value; renderEditor(); };

for (const name of Object.keys(SERIES)) {
  const button = document.createElement("button");
  button.textContent = SERIES[name].label;
  button.onclick = () => {
    chart = name;
    for (const other of el("chart-tabs").children) other.classList.toggle("on", other === button);
    drawChart();
  };
  button.classList.toggle("on", name === chart);
  el("chart-tabs").appendChild(button);
}

el("play").onclick = () => setPlaying(!playing);
el("playhead").oninput = () => { setPlaying(false); setPlayhead(Number(el("playhead").value)); };

el("fit-apply").onclick = () => {
  const target = Number(el("fit").value);
  if (target > 0) evaluate({ fit_duration_s: target });
};

el("json-apply").onclick = () => {
  try {
    load(JSON.parse(el("json").value));
  } catch (error) {
    showFailure({ detail: `That is not valid JSON: ${error.message}` });
  }
};
el("json-copy").onclick = () => navigator.clipboard.writeText(el("json").value);
window.addEventListener("resize", drawChart);

load(program);
