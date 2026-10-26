/* Shared PathProgram field schema for the harness and the stage-7 editor.
 *
 * PRIMITIVES drives both UIs. Keep make()/fields here so a new segment kind
 * is authored once. See SEGMENT_MODEL.md §10.
 */

(function (global) {
  "use strict";

  const get = (object, path) =>
    path.split(".").reduce((node, key) => (node == null ? node : node[key]), object);

  function set(object, path, value) {
    const keys = path.split(".");
    const last = keys.pop();
    let target = object;
    for (const key of keys) {
      if (target[key] == null || typeof target[key] !== "object") {
        // Creating e.g. Hermite.out when the operator edits out.length_m
        // while the handle was still "from pen".
        target[key] = {};
      }
      target = target[key];
    }
    target[last] = value;
  }

  function speedHandles({ c0, c1, c2, c3 }) {
    return {
      entry: c0,
      exit: c0 + c1 + c2 + c3,
      entry_slope: c1,
      exit_slope: c1 + 2 * c2 + 3 * c3,
    };
  }

  function speedCoefficients({ entry, exit, entry_slope, exit_slope }) {
    return {
      c0: entry,
      c1: entry_slope,
      c2: -3 * entry - 2 * entry_slope + 3 * exit - exit_slope,
      c3: 2 * entry + entry_slope - 2 * exit + exit_slope,
    };
  }

  const readHandle = (name) => (segment) => speedHandles(segment.velocity)[name];
  const writeHandle = (name) => (segment, value) => {
    const handles = speedHandles(segment.velocity);
    handles[name] = value;
    Object.assign(segment.velocity, speedCoefficients(handles));
  };

  const handleField = (name, label, extra) => ({
    key: `velocity.${name}`, label, type: "derived",
    read: readHandle(name), write: writeHandle(name), ...extra,
  });

  const SPEED_FIELDS = {
    handles: [
      { key: "velocity.inherit_entry", label: "inherit entry", type: "bool",
        help: "Enter at the previous segment's exit speed, so the boundary is smooth." },
      handleField("entry", "entry speed", { unit: "m/s", min: 2, max: 350, step: 1,
        disabledWhen: (s) => s.velocity.inherit_entry }),
      handleField("exit", "exit speed", { unit: "m/s", min: 2, max: 350, step: 1 }),
      handleField("entry_slope", "entry slope", { unit: "m/s", min: -400, max: 400, step: 5,
        help: "Rate of change at each end. Both zero eases smoothly between the two speeds." }),
      handleField("exit_slope", "exit slope", { unit: "m/s", min: -400, max: 400, step: 5 }),
    ],
    coefficients: [
      { key: "velocity.inherit_entry", label: "inherit entry", type: "bool",
        help: "Reseats c0 on the previous segment's exit speed." },
      { key: "velocity.c0", label: "c0", unit: "m/s", min: 2, max: 350, step: 1,
        disabledWhen: (s) => s.velocity.inherit_entry },
      { key: "velocity.c1", label: "c1", unit: "m/s", min: -400, max: 400, step: 5 },
      { key: "velocity.c2", label: "c2", unit: "m/s", min: -400, max: 400, step: 5 },
      { key: "velocity.c3", label: "c3", unit: "m/s", min: -400, max: 400, step: 5 },
    ],
  };

  const DWELL_FIELD = {
    key: "end.dwell_s", label: "dwell after", unit: "s", min: 0, max: 120, step: 0.5,
    help: "A hold cannot be a speed of zero — that stops the clock — so it stays explicit.",
  };

  const newVelocity = () => ({ c0: 100, c1: 0, c2: 0, c3: 0, inherit_entry: true });
  const newBoundary = () => ({ dwell_s: 0 });

  const PRIMITIVES = {
    LINE_TO: {
      label: "LineTo",
      make: () => ({
        kind: "LINE_TO", name: "", heading_deg: 0, climb_deg: 0,
        distance_m: 1500, inherit_direction: false,
        velocity: newVelocity(), end: newBoundary(),
      }),
      fields: [
        { key: "inherit_direction", label: "carry on", type: "bool",
          help: "Fly the pen's direction instead of the angles below." },
        { key: "heading_deg", label: "heading", unit: "\u00b0", min: 0, max: 360, step: 1,
          disabledWhen: (s) => s.inherit_direction },
        { key: "climb_deg", label: "climb", unit: "\u00b0", min: -89, max: 89, step: 0.5,
          disabledWhen: (s) => s.inherit_direction },
        { key: "distance_m", label: "distance", unit: "m", min: 10, max: 20000, step: 10 },
      ],
    },

    ARC: {
      label: "Arc",
      make: () => ({
        kind: "ARC", name: "", side: "LEFT", radius_m: 800,
        sweep_deg: 90, tilt_deg: 0, rise_per_turn_m: null,
        velocity: newVelocity(), end: newBoundary(),
      }),
      fields: [
        { key: "side", label: "side", type: "select", options: ["LEFT", "RIGHT"],
          help: "Which side of the entry tangent the centre sits on. Nothing else resolves it." },
        { key: "radius_m", label: "radius", unit: "m", min: 20, max: 10000, step: 10 },
        { key: "sweep_deg", label: "sweep", unit: "\u00b0", min: 0, max: 1440, step: 1,
          help: "Unbounded: past 360 is simply more than one turn." },
        { key: "tilt_deg", label: "tilt", unit: "\u00b0", min: -89, max: 89, step: 1,
          help: "Rolls the circle's plane about the entry tangent, positive toward the right." },
        { key: "rise_per_turn_m", label: "rise / turn", unit: "m", type: "nullable",
          autoLabel: "match the pen's climb", min: -2000, max: 2000, step: 25, fallback: 200,
          help: "Left to match, the join stays smooth. Setting it kinks the vertical only." },
      ],
    },

    MOVE_TO: {
      label: "MoveTo",
      make: (pen) => ({
        kind: "MOVE_TO", name: "",
        to: { lat: Number((pen.lat + 0.02).toFixed(6)), lon: Number((pen.lon + 0.02).toFixed(6)),
              alt_ft_msl: pen.alt_ft_msl },
        tangent: { heading_deg: 90, climb_deg: 0 },
        speed_ms: null, end: newBoundary(),
      }),
      speedFields: [
        { key: "speed_ms", label: "re-seed speed", type: "nullable",
          autoLabel: "let the next segment decide", unit: "m/s",
          min: 2, max: 350, step: 5, fallback: 100,
          help: "A speed carried across a jump describes nothing, so it is dropped unless set here." },
      ],
      fields: [
        { key: "to.lat", label: "latitude", unit: "\u00b0", type: "plain", step: 0.001 },
        { key: "to.lon", label: "longitude", unit: "\u00b0", type: "plain", step: 0.001 },
        { key: "to.alt_ft_msl", label: "altitude", unit: "ft", min: 0, max: 45000, step: 100 },
        { key: "tangent", label: "re-seed", type: "toggleObject", defaults: { heading_deg: 0, climb_deg: 0 },
          help: "A jump leaves no direction behind. Without this the next segment must state its own." },
        { key: "tangent.heading_deg", label: "heading", unit: "\u00b0", min: 0, max: 360, step: 1,
          hiddenWhen: (s) => !s.tangent },
        { key: "tangent.climb_deg", label: "climb", unit: "\u00b0", min: -89, max: 89, step: 0.5,
          hiddenWhen: (s) => !s.tangent },
      ],
    },

    HERMITE: {
      label: "Hermite",
      make: (pen) => ({
        kind: "HERMITE", name: "",
        to: { lat: Number((pen.lat + 0.025).toFixed(6)), lon: Number((pen.lon + 0.02).toFixed(6)),
              alt_ft_msl: pen.alt_ft_msl },
        out: null,
        into: { heading_deg: 90, climb_deg: 0, length_m: 500 },
        velocity: newVelocity(), end: newBoundary(),
      }),
      fields: [
        { key: "to.lat", label: "end lat", unit: "\u00b0", type: "plain", step: 0.001 },
        { key: "to.lon", label: "end lon", unit: "\u00b0", type: "plain", step: 0.001 },
        { key: "to.alt_ft_msl", label: "end alt", unit: "ft", min: 0, max: 45000, step: 100 },
        // Lengths (tangent weights) are always editable. Editing out.* while
        // out is null creates the handle (was "from pen").
        { key: "out.length_m", label: "out length", unit: "m", min: 10, max: 5000, step: 10,
          fallback: 500,
          help: "How hard the curve leaves the start. Creates an explicit out handle if unset." },
        { key: "into.length_m", label: "into length", unit: "m", min: 10, max: 5000, step: 10,
          fallback: 500,
          help: "How hard the curve arrives at the end." },
        { key: "out", label: "out handle angles", type: "toggleObject",
          defaults: { heading_deg: 0, climb_deg: 0, length_m: 500 },
          help: "Off = out direction from the pen (G1). On = set heading/climb below." },
        { key: "out.heading_deg", label: "out hdg", unit: "\u00b0", min: 0, max: 360, step: 1,
          hiddenWhen: (s) => !s.out },
        { key: "out.climb_deg", label: "out climb", unit: "\u00b0", min: -89, max: 89, step: 0.5,
          hiddenWhen: (s) => !s.out },
        { key: "into.heading_deg", label: "into hdg", unit: "\u00b0", min: 0, max: 360, step: 1 },
        { key: "into.climb_deg", label: "into climb", unit: "\u00b0", min: -89, max: 89, step: 0.5 },
      ],
    },

    SPLINE: {
      label: "Spline",
      make: (pen) => ({
        kind: "SPLINE", name: "",
        degree: 3,
        control_points: [
          { lat: pen.lat, lon: pen.lon, alt_ft_msl: pen.alt_ft_msl, weight: 1 },
          { lat: Number((pen.lat + 0.01).toFixed(6)), lon: Number((pen.lon + 0.015).toFixed(6)),
            alt_ft_msl: pen.alt_ft_msl, weight: 1 },
          { lat: Number((pen.lat + 0.02).toFixed(6)), lon: Number((pen.lon + 0.01).toFixed(6)),
            alt_ft_msl: pen.alt_ft_msl + 200, weight: 1 },
          { lat: Number((pen.lat + 0.03).toFixed(6)), lon: Number((pen.lon - 0.005).toFixed(6)),
            alt_ft_msl: pen.alt_ft_msl, weight: 1 },
        ],
        velocity: newVelocity(), end: newBoundary(),
      }),
      fields: [
        { key: "degree", label: "degree", type: "plain", min: 1, max: 3, step: 1,
          help: "Clamped NURBS, cubic max. Needs more than `degree` control points." },
      ],
    },
  };

  // Mirrors SOLVER_PARAMETERS in core/program.py (and the harness pin list).
  const SOLVER_PARAMETERS = {
    MOVE_TO: ["to.lat", "to.lon", "to.alt_ft_msl",
              "tangent.heading_deg", "tangent.climb_deg", "speed_ms"],
    LINE_TO: ["heading_deg", "climb_deg", "distance_m"],
    ARC: ["radius_m", "sweep_deg", "tilt_deg", "rise_per_turn_m", "side"],
    HERMITE: ["to.lat", "to.lon", "to.alt_ft_msl",
              "out.heading_deg", "out.climb_deg", "out.length_m",
              "into.heading_deg", "into.climb_deg", "into.length_m"],
    SPLINE: [],
  };

  const readField = (segment, spec) => {
    if (spec.read) return spec.read(segment);
    const value = get(segment, spec.key);
    if (value == null && spec.fallback != null) return spec.fallback;
    return value;
  };
  const writeField = (segment, spec, value) => {
    if (spec.write) {
      spec.write(segment, value);
      return;
    }
    // Editing Hermite out.* while out is null mints a full handle so the
    // length weight is not written onto a half-empty object.
    if (segment.kind === "HERMITE" && spec.key.startsWith("out.") && !segment.out) {
      segment.out = { heading_deg: 0, climb_deg: 0, length_m: 500 };
    }
    if (segment.kind === "HERMITE" && spec.key.startsWith("into.") && !segment.into) {
      segment.into = { heading_deg: 0, climb_deg: 0, length_m: 500 };
    }
    set(segment, spec.key, value);
  };

  const isSolverParameter = (segment, key) => {
    if (segment.kind === "SPLINE") {
      return /^control_points\.\d+\.(lat|lon|alt_ft_msl|weight)$/.test(key);
    }
    return (SOLVER_PARAMETERS[segment.kind] || []).includes(key);
  };

  function motionFields(segment, speedMode) {
    const mode = speedMode || "handles";
    const speed = PRIMITIVES[segment.kind].speedFields || SPEED_FIELDS[mode];
    return [...speed, DWELL_FIELD];
  }

  const KIND_LABEL = Object.fromEntries(
    Object.entries(PRIMITIVES).map(([kind, spec]) => [kind, spec.label])
  );

  global.ProgramFields = {
    get, set,
    speedHandles, speedCoefficients,
    SPEED_FIELDS, DWELL_FIELD,
    newVelocity, newBoundary,
    PRIMITIVES, SOLVER_PARAMETERS, KIND_LABEL,
    readField, writeField, isSolverParameter, motionFields,
  };
})(typeof window !== "undefined" ? window : globalThis);
