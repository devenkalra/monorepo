"use strict";

// Authored legs on the departing waypoint: straight, planar arc, cubic
// Hermite, or a multi-waypoint B-spline span. The solver evaluates them;
// this file is the inspector, table helpers and map gizmos.

const PATHLEGS = { layer: null };

const PATH_KIND_LABELS = [
  ["STRAIGHT", "Straight"],
  ["ARC", "Arc"],
  ["HERMITE", "Hermite"],
  ["BSPLINE", "B-spline"],
];

function defaultPlane() {
  return { normal_east: 0, normal_up: 1, normal_north: 0 };
}

function pathKind(keyframe) {
  return keyframe?.path?.kind || "STRAIGHT";
}

function pathChord(a, b) {
  const en = typeof pathAddToEn === "function"
    ? pathAddToEn(a, b.lat, b.lon)
    : { east: 0, north: 0 };
  const up = ((b.alt_ft_msl ?? 0) - (a.alt_ft_msl ?? 0)) * 0.3048;
  const horiz = Math.hypot(en.east, en.north);
  const len = Math.hypot(en.east, en.north, up);
  return {
    east: en.east, north: en.north, up, len, horiz,
    heading: Math.atan2(en.east, en.north) * 180 / Math.PI,
    climb: Math.atan2(up, horiz || 1e-9) * 180 / Math.PI,
  };
}

function handleFromDelta(east, up, north, lengthM) {
  const horiz = Math.hypot(east, north);
  const len = Math.hypot(east, up, north);
  if (len < 1e-9) return null;
  return {
    heading_deg: Math.atan2(east, north) * 180 / Math.PI,
    climb_deg: Math.atan2(up, horiz || 1e-9) * 180 / Math.PI,
    length_m: Math.max(lengthM, 1),
  };
}

function handleFromChord(a, b, lengthM) {
  const chord = pathChord(a, b);
  if (chord.len < 1e-6) return null;
  return {
    heading_deg: chord.heading,
    climb_deg: chord.climb,
    length_m: Math.max(lengthM ?? chord.len / 3, 1),
  };
}

function handleFromCopy(handle, lengthM) {
  if (!handle) return null;
  return {
    heading_deg: handle.heading_deg || 0,
    climb_deg: handle.climb_deg || 0,
    length_m: Math.max(lengthM, 1),
  };
}

function pathOwningSpan(key, list, side) {
  const index = list.indexOf(key);
  if (index < 0) return null;
  if (side === "arrive") {
    if (index <= 0) return null;
    for (let i = 0; i < index; i++) {
      const path = list[i].path;
      if (path?.kind !== "BSPLINE") continue;
      const end = list.findIndex((item) => item.id === path.end_id);
      if (end >= index) {
        return { from: list[i], to: list[end], path, keys: list.slice(i, end + 1), at: key };
      }
    }
    return { from: list[index - 1], to: key, path: list[index - 1].path, keys: [list[index - 1], key], at: key };
  }
  if (index >= list.length - 1) return null;
  for (let i = 0; i <= index; i++) {
    const path = list[i].path;
    if (path?.kind !== "BSPLINE") continue;
    const end = list.findIndex((item) => item.id === path.end_id);
    if (end > index) {
      return { from: list[i], to: list[end], path, keys: list.slice(i, end + 1), at: key };
    }
  }
  return { from: key, to: list[index + 1], path: key.path, keys: [key, list[index + 1]], at: key };
}

function pathTangentHandle(span, atEnd, lengthM) {
  const path = span?.path;
  const from = span.from, to = span.to;
  if (!from || !to) return null;
  const kind = path?.kind || "STRAIGHT";
  if (kind === "HERMITE") {
    return handleFromCopy(atEnd ? path.into : path.out, lengthM);
  }
  if (kind === "ARC" && typeof sampleArcLatLngs === "function") {
    const ring = sampleArcLatLngs(from, to, path);
    if (ring.length >= 2) {
      const a = atEnd ? ring[ring.length - 2] : ring[0];
      const b = atEnd ? ring[ring.length - 1] : ring[1];
      return handleFromChord(
        { lat: a[0], lon: a[1], alt_ft_msl: from.alt_ft_msl },
        { lat: b[0], lon: b[1], alt_ft_msl: to.alt_ft_msl },
        lengthM,
      );
    }
  }
  if (kind === "BSPLINE" && span.keys?.length >= 2) {
    const origin = span.keys[0];
    const points = span.keys.map((key) => {
      const en = pathAddToEn(origin, key.lat, key.lon);
      const up = ((key.alt_ft_msl ?? origin.alt_ft_msl) - origin.alt_ft_msl) * 0.3048;
      return [en.east, up, en.north];
    });
    const fit = _bsFitEnu(points, path.tolerance_m ?? 50);
    if (fit) {
      const params = _bsChordParams(points);
      const index = Math.max(0, span.keys.indexOf(span.at));
      const u = params[index] ?? (atEnd ? 1 : 0);
      const p0 = _bsPoint(fit, Math.max(0, u - 0.02));
      const p1 = _bsPoint(fit, Math.min(1, u + 0.02));
      return handleFromDelta(p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2], lengthM);
    }
  }
  return handleFromChord(from, to, lengthM);
}

function defaultHermitePath(a, b, list) {
  const chord = pathChord(a, b);
  const length = Math.max(chord.len / 3, 1);
  const keys = list || state.doc?.flight_keyframes || [];
  const fallback = { heading_deg: chord.heading, climb_deg: chord.climb, length_m: length };
  const arrive = pathOwningSpan(a, keys, "arrive");
  const leave = pathOwningSpan(b, keys, "leave");
  const out = (arrive && pathTangentHandle(arrive, true, length)) || fallback;
  const into = (leave && pathTangentHandle(leave, false, length)) || fallback;
  return { kind: "HERMITE", out, into };
}

// A Hermite ends where the next leg begins. When that next leg appears or
// changes kind, re-aim the Hermite's In handle along it so the join stays
// smooth instead of kinking at the shared waypoint.
function syncHermiteJoin(key, list) {
  const keys = list || state.doc?.flight_keyframes || [];
  const index = keys.indexOf(key);
  if (index <= 0 || index >= keys.length - 1) return;
  const previous = keys[index - 1];
  if (previous.path?.kind !== "HERMITE") return;
  const length = previous.path.into?.length_m
    || Math.max(pathChord(previous, key).len / 3, 1);
  const leave = pathOwningSpan(key, keys, "leave");
  const handle = leave && pathTangentHandle(leave, false, length);
  if (handle) previous.path.into = handle;
}

function defaultArcPath(a, b) {
  const chord = pathChord(a, b);
  return {
    kind: "ARC",
    side: "LEFT",
    radius_m: Math.max(chord.len * 0.6, 1),
    major: false,
    plane: defaultPlane(),
  };
}

function defaultBsplinePath(keyframe, list) {
  const index = list.indexOf(keyframe);
  let endIndex = list.length - 1;
  const selected = typeof selectedFlightKeyframes === "function" ? selectedFlightKeyframes() : [];
  if (selected.length > 1) {
    const lastSel = selected.reduce((best, key) => (
      list.indexOf(key) > list.indexOf(best) ? key : best
    ), selected[0]);
    endIndex = list.indexOf(lastSel);
  }
  endIndex = Math.max(index + 1, endIndex);
  const end = list[endIndex] || list[list.length - 1];
  return { kind: "BSPLINE", end_id: end?.id || "", tolerance_m: 50 };
}

function coalesceBsplines(list) {
  const indexOf = new Map((list || []).map((key, index) => [key.id, index]));
  let index = 0;
  while (index < list.length - 1) {
    const path = list[index].path;
    if (path?.kind !== "BSPLINE") {
      index += 1;
      continue;
    }
    let farthest = indexOf.get(path.end_id);
    if (farthest == null || farthest <= index) {
      index += 1;
      continue;
    }
    let scan = index + 1;
    while (scan < list.length - 1 && list[scan].path?.kind === "BSPLINE") {
      const other = indexOf.get(list[scan].path.end_id);
      farthest = Math.max(farthest, other ?? scan + 1, scan + 1);
      scan += 1;
    }
    farthest = Math.min(farthest, list.length - 1);
    path.end_id = list[farthest].id;
    for (let inner = index + 1; inner < farthest; inner++) {
      list[inner].path = { kind: "STRAIGHT" };
    }
    index = farthest;
  }
}

function setPathKind(keyframe, kind) {
  const list = state.doc?.flight_keyframes || [];
  const index = list.indexOf(keyframe);
  const next = list[index + 1] || keyframe;
  if (kind === "ARC") keyframe.path = defaultArcPath(keyframe, next);
  else if (kind === "HERMITE") keyframe.path = defaultHermitePath(keyframe, next, list);
  else if (kind === "BSPLINE") keyframe.path = defaultBsplinePath(keyframe, list);
  else keyframe.path = { kind: "STRAIGHT" };
  if (kind === "BSPLINE") coalesceBsplines(list);
  syncHermiteJoin(keyframe, list);
}

function planeFromTilt(a, b, tiltDeg) {
  const chord = pathChord(a, b);
  const axis = Math.hypot(chord.east, chord.north);
  const ae = axis > 1e-6 ? chord.east / axis : 1;
  const an = axis > 1e-6 ? chord.north / axis : 0;
  const t = (tiltDeg || 0) * Math.PI / 180;
  return {
    normal_east: -an * Math.sin(t),
    normal_up: Math.cos(t),
    normal_north: ae * Math.sin(t),
  };
}

function tiltFromPlane(plane) {
  const up = plane?.normal_up ?? 1;
  const horiz = Math.hypot(plane?.normal_east || 0, plane?.normal_north || 0);
  return Math.atan2(horiz, up) * 180 / Math.PI;
}

function handleTip(origin, handle) {
  const heading = (handle.heading_deg || 0) * Math.PI / 180;
  const climb = (handle.climb_deg || 0) * Math.PI / 180;
  const length = handle.length_m || 1;
  const east = Math.sin(heading) * Math.cos(climb) * length;
  const north = Math.cos(heading) * Math.cos(climb) * length;
  return typeof pathAddFromEn === "function"
    ? pathAddFromEn(origin, east, north)
    : origin;
}

function renderPathInspector(host, keyframe) {
  const list = state.doc.flight_keyframes || [];
  const last = list[list.length - 1] === keyframe;
  const next = list[list.indexOf(keyframe) + 1];
  if (!keyframe.path) keyframe.path = { kind: "STRAIGHT" };
  host.appendChild(field("To next", selectInput(PATH_KIND_LABELS, pathKind(keyframe), (value) => {
    setPathKind(keyframe, value);
    touched();
  })));
  const note = document.createElement("p");
  note.className = "hint";
  if (last) {
    note.textContent = "No segment after the last waypoint; To next has no effect here.";
  } else if (pathKind(keyframe) === "STRAIGHT") {
    note.textContent = "Straight (mint) is the 3D chord to the next waypoint.";
  } else if (pathKind(keyframe) === "ARC") {
    note.textContent = "Arc is a circle in a plane. Default plane is horizontal; tilt it to climb.";
  } else if (pathKind(keyframe) === "HERMITE") {
    note.textContent = "Hermite is a cubic. Out is seeded from the previous curve, In from the next. "
      + "Drag the dot at the end of either handle on the map to change its pull; it slides along the "
      + "handle so the direction, and the smooth join, stay put.";
  } else {
    note.textContent = "B-spline: first and last stay on the curve. Interiors pull it; they are not interpolation points. Add B-spline keeps accepting clicks until Esc.";
  }
  host.appendChild(note);
  if (last) return;

  const path = keyframe.path;
  if (path.kind === "ARC") {
    if (!path.plane) path.plane = defaultPlane();
    host.appendChild(field("Turn", selectInput(
      [["LEFT", "Left"], ["RIGHT", "Right"]],
      path.side || "LEFT", (value) => { path.side = value; touched(); })));
    // A circle through two points cannot be tighter than half their spacing.
    // Snapping to that floor on entry makes the limit visible; the field used
    // to keep a smaller number that the solver silently ignored.
    const floor = Math.max(1, pathChord(keyframe, next).len / 2);
    const radius = numberInput(path.radius_m, (value) => {
      path.radius_m = Math.max(floor, value); touched();
    }, 10);
    radius.min = Math.ceil(floor);
    host.appendChild(field("Radius m", radius));
    const radiusNote = document.createElement("p");
    radiusNote.className = "hint";
    radiusNote.textContent = `Smallest here is ${Math.round(floor)} m, half the `
      + `${Math.round(floor * 2)} m between these two waypoints. At that radius the arc `
      + "is a half circle; larger radii flatten it toward the straight line.";
    host.appendChild(radiusNote);
    host.appendChild(field("Way", selectInput(
      [["MINOR", "Shorter"], ["MAJOR", "Longer"]],
      path.major ? "MAJOR" : "MINOR",
      (value) => { path.major = value === "MAJOR"; touched(); })));
    const tilt = tiltFromPlane(path.plane);
    host.appendChild(field("Plane", selectInput(
      [["H", "Horizontal"], ["T", "Tilted"]],
      Math.abs(tilt) < 0.5 ? "H" : "T",
      (value) => {
        path.plane = value === "H" ? defaultPlane() : planeFromTilt(keyframe, next, 15);
        touched();
      })));
    if (Math.abs(tilt) >= 0.5) {
      host.appendChild(field("Tilt °", numberInput(tilt, (value) => {
        path.plane = planeFromTilt(keyframe, next, value);
        touched();
      }, 1)));
    }
  } else if (path.kind === "HERMITE") {
    if (!path.out) path.out = defaultHermitePath(keyframe, next).out;
    if (!path.into) path.into = defaultHermitePath(keyframe, next).into;
    host.appendChild(field("Out heading °", numberInput(path.out.heading_deg, (value) => {
      path.out.heading_deg = value; touched();
    }, 1)));
    host.appendChild(field("Out climb °", numberInput(path.out.climb_deg || 0, (value) => {
      path.out.climb_deg = value; touched();
    }, 1)));
    host.appendChild(field("Out length m", numberInput(path.out.length_m, (value) => {
      path.out.length_m = Math.max(1, value); touched();
    }, 5)));
    host.appendChild(field("In heading °", numberInput(path.into.heading_deg, (value) => {
      path.into.heading_deg = value; touched();
    }, 1)));
    host.appendChild(field("In climb °", numberInput(path.into.climb_deg || 0, (value) => {
      path.into.climb_deg = value; touched();
    }, 1)));
    host.appendChild(field("In length m", numberInput(path.into.length_m, (value) => {
      path.into.length_m = Math.max(1, value); touched();
    }, 5)));
  } else if (path.kind === "BSPLINE") {
    const index = list.indexOf(keyframe);
    const later = list.slice(index + 1).map((key, i) => {
      const label = (typeof waypointLabel === "function"
        ? waypointLabel(key, index + 1 + i) : `#${index + 2 + i}`);
      return [key.id, label];
    });
    if (!later.length) {
      const warn = document.createElement("p");
      warn.className = "hint";
      warn.textContent = "B-spline needs a later waypoint to end on.";
      host.appendChild(warn);
      return;
    }
    if (!later.some((row) => row[0] === path.end_id)) path.end_id = later[later.length - 1][0];
    host.appendChild(field("Through to", selectInput(later, path.end_id, (value) => {
      path.end_id = value; touched();
    })));
    host.appendChild(field("Tolerance m", numberInput(path.tolerance_m ?? 50, (value) => {
      path.tolerance_m = Math.max(0, value); touched();
    }, 5)));
    const pull = document.createElement("p");
    pull.className = "hint";
    pull.textContent = "How far interiors may pull the curve. Larger = smoother and more miss; smaller = closer to the points.";
    host.appendChild(pull);
  }
}

function _unit3(v) {
  const n = Math.hypot(v[0], v[1], v[2]);
  return n < 1e-12 ? [0, 0, 0] : [v[0] / n, v[1] / n, v[2] / n];
}

function _cross3(a, b) {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

function sampleArcLatLngs(start, end, path) {
  if (typeof pathAddToEn !== "function" || typeof pathAddFromEn !== "function") return [];
  const b = pathAddToEn(start, end.lat, end.lon);
  const up = ((end.alt_ft_msl ?? start.alt_ft_msl) - start.alt_ft_msl) * 0.3048;
  const a = [0, 0, 0];
  const p1 = [b.east, up, b.north];
  const chord = [p1[0] - a[0], p1[1] - a[1], p1[2] - a[2]];
  const length = Math.hypot(chord[0], chord[1], chord[2]);
  if (length < 1e-6) return [];
  const preferred = [
    path.plane?.normal_east || 0, path.plane?.normal_up ?? 1, path.plane?.normal_north || 0,
  ];
  const along = _unit3(chord);
  const prefDot = preferred[0] * along[0] + preferred[1] * along[1] + preferred[2] * along[2];
  let normal = _unit3([
    preferred[0] - along[0] * prefDot,
    preferred[1] - along[1] * prefDot,
    preferred[2] - along[2] * prefDot,
  ]);
  if (Math.hypot(...normal) < 0.5) normal = _unit3(_cross3(along, [0, 1, 0]));
  const half = length / 2;
  const radius = Math.max(path.radius_m || half, half);
  const height = Math.sqrt(Math.max(0, radius * radius - half * half));
  const left = _unit3(_cross3(along, normal));
  const sign = path.side === "RIGHT" ? -1 : 1;
  const center = [chord[0] / 2 + left[0] * sign * height, chord[1] / 2 + left[1] * sign * height,
    chord[2] / 2 + left[2] * sign * height];
  const radial = _unit3([-center[0], -center[1], -center[2]]);
  const around = _cross3(normal, radial);
  const toEnd = [p1[0] - center[0], p1[1] - center[1], p1[2] - center[2]];
  let sweep = Math.atan2(
    around[0] * toEnd[0] + around[1] * toEnd[1] + around[2] * toEnd[2],
    radial[0] * toEnd[0] + radial[1] * toEnd[1] + radial[2] * toEnd[2],
  );
  if (path.major) sweep = sweep >= 0 ? sweep - Math.PI * 2 : sweep + Math.PI * 2;
  const points = [];
  for (let i = 0; i <= 48; i++) {
    const theta = sweep * (i / 48);
    const east = center[0] + radial[0] * radius * Math.cos(theta) + around[0] * radius * Math.sin(theta);
    const north = center[2] + radial[2] * radius * Math.cos(theta) + around[2] * radius * Math.sin(theta);
    const ll = pathAddFromEn(start, east, north);
    points.push([ll.lat, ll.lon]);
  }
  return points;
}

function _bsChordParams(points) {
  const params = [0];
  for (let i = 1; i < points.length; i++) {
    params.push(params[i - 1] + Math.hypot(
      points[i][0] - points[i - 1][0],
      points[i][1] - points[i - 1][1],
      points[i][2] - points[i - 1][2],
    ));
  }
  const total = params[params.length - 1];
  if (total < 1e-9) return points.map((_, i) => i / Math.max(1, points.length - 1));
  return params.map((value) => value / total);
}

function _bsClampedKnots(nCtrl) {
  return [0, 0, 0, 0, 1, 1, 1, 1];
}

function _bsFindSpan(nCtrl, u, knots) {
  if (u >= knots[nCtrl]) return nCtrl - 1;
  if (u <= knots[3]) return 3;
  let low = 3, high = nCtrl, mid = (low + high) >> 1;
  while (u < knots[mid] || u >= knots[mid + 1]) {
    if (u < knots[mid]) high = mid;
    else low = mid;
    mid = (low + high) >> 1;
  }
  return mid;
}

function _bsBasis(span, u, knots) {
  const left = [0, 0, 0, 0], right = [0, 0, 0, 0], n = [1, 0, 0, 0];
  for (let j = 1; j <= 3; j++) {
    left[j] = u - knots[span + 1 - j];
    right[j] = knots[span + j] - u;
    let saved = 0;
    for (let r = 0; r < j; r++) {
      const denom = right[r + 1] + left[j - r];
      const temp = Math.abs(denom) > 1e-15 ? n[r] / denom : 0;
      n[r] = saved + right[r + 1] * temp;
      saved = left[j - r] * temp;
    }
    n[j] = saved;
  }
  return n;
}

function _bsSmoothWeight(points, toleranceM) {
  if (!(toleranceM > 0)) return 0;
  let span = 0;
  for (let i = 1; i < points.length; i++) {
    span += Math.hypot(
      points[i][0] - points[i - 1][0],
      points[i][1] - points[i - 1][1],
      points[i][2] - points[i - 1][2],
    );
  }
  return Math.min(2, Math.max(0.05, 2 * toleranceM / Math.max(span, 1)));
}

function _bsSolve2(a00, a01, a10, a11, b0, b1) {
  const det = a00 * a11 - a01 * a10;
  if (Math.abs(det) < 1e-12) return [0, 0];
  return [(b0 * a11 - a01 * b1) / det, (a00 * b1 - b0 * a10) / det];
}

function _bsFitEnu(points, toleranceM) {
  const n = points.length;
  if (n < 2) return null;
  const params = _bsChordParams(points);
  if (n === 2) {
    const a = points[0], b = points[1];
    const d = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    return {
      ctrl: [a, [a[0] + d[0] / 3, a[1] + d[1] / 3, a[2] + d[2] / 3],
        [a[0] + 2 * d[0] / 3, a[1] + 2 * d[1] / 3, a[2] + 2 * d[2] / 3], b],
      knots: _bsClampedKnots(4),
    };
  }
  const knots = _bsClampedKnots(4);
  const matrix = points.map((point, j) => {
    const span = _bsFindSpan(4, params[j], knots);
    const basis = _bsBasis(span, params[j], knots);
    const row = [0, 0, 0, 0];
    for (let i = 0; i < 4; i++) row[span - 3 + i] = basis[i];
    return row;
  });
  const first = points[0], last = points[n - 1];
  const rhs = points.map((point, j) => [
    point[0] - matrix[j][0] * first[0] - matrix[j][3] * last[0],
    point[1] - matrix[j][0] * first[1] - matrix[j][3] * last[1],
    point[2] - matrix[j][0] * first[2] - matrix[j][3] * last[2],
  ]);
  let a00 = 0, a01 = 0, a11 = 0;
  const b = [[0, 0, 0], [0, 0, 0]];
  for (let j = 0; j < n; j++) {
    const u = matrix[j][1], v = matrix[j][2];
    a00 += u * u; a01 += u * v; a11 += v * v;
    for (let k = 0; k < 3; k++) {
      b[0][k] += u * rhs[j][k];
      b[1][k] += v * rhs[j][k];
    }
  }
  const smooth = _bsSmoothWeight(points, toleranceM);
  if (smooth > 0) {
    const s2 = smooth * smooth;
    a00 += 5 * s2; a01 += -4 * s2; a11 += 5 * s2;
    for (let k = 0; k < 3; k++) {
      b[0][k] += s2 * (2 * first[k] - last[k]);
      b[1][k] += s2 * (2 * last[k] - first[k]);
    }
  }
  const c1 = [0, 0, 0], c2 = [0, 0, 0];
  for (let k = 0; k < 3; k++) {
    const pair = _bsSolve2(a00, a01, a01, a11, b[0][k], b[1][k]);
    c1[k] = pair[0]; c2[k] = pair[1];
  }
  return { ctrl: [first, c1, c2, last], knots };
}

function _bsPoint(fit, u) {
  u = Math.min(1, Math.max(0, u));
  const span = _bsFindSpan(4, u, fit.knots);
  const basis = _bsBasis(span, u, fit.knots);
  const point = [0, 0, 0];
  for (let i = 0; i < 4; i++) {
    const ctrl = fit.ctrl[span - 3 + i];
    point[0] += basis[i] * ctrl[0];
    point[1] += basis[i] * ctrl[1];
    point[2] += basis[i] * ctrl[2];
  }
  return point;
}

/** The tangent tip as a grip you can slide. It stays on the tangent ray and
 *  only changes that handle's length: the direction is taken from the
 *  neighbouring leg so the join stays smooth, and letting a drag re-aim it
 *  would undo that. Length is the curve's pull, which is the part that is
 *  hard to dial in by typing a number. */
function addTangentGrip(which, anchor, path, drawn, line) {
  const handle = path[which];
  if (!handle || typeof pathAddToEn !== "function" || typeof dotIcon !== "function") return;
  const label = which === "out" ? "Out" : "In";
  const say = () => `${label} tangent · ${Math.round(handle.length_m || 0)} m`
    + " — drag along the line to change its pull";
  const tip = handleTip(anchor, drawn);
  const grip = L.marker([tip.lat, tip.lon], {
    icon: dotIcon(`tangent-icon tangent-${which.toLowerCase()}`),
    draggable: true,
    zIndexOffset: 600,
  });
  grip.bindTooltip(say());
  const east = Math.sin((drawn.heading_deg || 0) * Math.PI / 180);
  const north = Math.cos((drawn.heading_deg || 0) * Math.PI / 180);
  // handleTip foreshortens the ground distance by the climb angle; undo that
  // to get back to the 3D length the solver wants.
  const squash = Math.max(0.05, Math.abs(Math.cos((drawn.climb_deg || 0) * Math.PI / 180)));
  grip.on("dragstart", () => { PATHLEGS.dragging = true; });
  grip.on("drag", (event) => {
    const at = event.target.getLatLng();
    const en = pathAddToEn(anchor, at.lat, at.lng);
    // Only the component along the tangent counts, so the grip slides on the
    // line rather than wandering off it.
    const along = Math.max(1, en.east * east + en.north * north);
    handle.length_m = Math.max(1, Math.round(along / squash));
    const snapped = handleTip(anchor, { ...drawn, length_m: handle.length_m });
    event.target.setLatLng([snapped.lat, snapped.lon]);
    line.setLatLngs([[anchor.lat, anchor.lon], [snapped.lat, snapped.lon]]);
    grip.setTooltipContent(say());
    if (typeof solveWhileDragging === "function") solveWhileDragging();
  });
  grip.on("dragend", () => { PATHLEGS.dragging = false; touched(); });
  grip.addTo(PATHLEGS.layer);
}

/** Leaflet tracks one global "currently dragging" handle. Removing a grip
 *  that still holds that slot runs the drag-finish path mid-removal, which
 *  throws and aborts the whole render, stranding dead gizmos on the map. A
 *  release outside the window leaves a grip stuck exactly that way, so hand
 *  the slot back before clearing. */
function clearPathGizmos() {
  for (const layer of PATHLEGS.layer.getLayers()) {
    const dragger = layer.dragging && layer.dragging._draggable;
    if (dragger && L.Draggable._dragging === dragger) L.Draggable._dragging = false;
  }
  PATHLEGS.layer.clearLayers();
}

function renderPathGizmos() {
  if (!PATHLEGS.layer) return;
  // A live solve redraws the track mid-drag; rebuilding the gizmos here would
  // destroy the grip the pointer is holding.
  if (PATHLEGS.dragging) return;
  clearPathGizmos();
  if (state.track !== "flight" || !state.doc) return;
  const list = state.doc.flight_keyframes || [];
  const keyframe = state.selected != null ? list[state.selected] : null;
  if (!keyframe || !keyframe.path || keyframe === list[list.length - 1]) return;
  const next = list[list.indexOf(keyframe) + 1];
  if (!next) return;
  const path = keyframe.path;
  if (path.kind === "ARC") {
    const ring = sampleArcLatLngs(keyframe, next, path);
    if (ring.length) {
      L.polyline(ring, { color: "#ffa23e", weight: 2, dashArray: "5 6", interactive: false })
        .addTo(PATHLEGS.layer);
    }
  } else if (path.kind === "HERMITE") {
    const outDrawn = { ...(path.out || {}) };
    // The In handle points back down the arriving tangent, so it is drawn
    // reversed from the waypoint it belongs to.
    const intoDrawn = {
      heading_deg: (path.into?.heading_deg || 0) + 180,
      climb_deg: -(path.into?.climb_deg || 0),
      length_m: path.into?.length_m || 1,
    };
    const out = handleTip(keyframe, outDrawn);
    const into = handleTip(next, intoDrawn);
    const outLine = L.polyline([[keyframe.lat, keyframe.lon], [out.lat, out.lon]], {
      color: "#7ee29a", weight: 2, interactive: false,
    }).addTo(PATHLEGS.layer);
    const intoLine = L.polyline([[next.lat, next.lon], [into.lat, into.lon]], {
      color: "#ffa23e", weight: 2, interactive: false,
    }).addTo(PATHLEGS.layer);
    addTangentGrip("out", keyframe, path, outDrawn, outLine);
    addTangentGrip("into", next, path, intoDrawn, intoLine);
  } else if (path.kind === "BSPLINE") {
    const endIndex = list.findIndex((key) => key.id === path.end_id);
    const startIndex = list.indexOf(keyframe);
    if (endIndex > startIndex) {
      // No curve of our own here: the track already draws the solved span, and
      // a second one fitted client-side would only disagree with it.
      for (let i = startIndex + 1; i < endIndex; i++) {
        L.circleMarker([list[i].lat, list[i].lon], {
          radius: 5, color: "#c084fc", weight: 2, fillOpacity: 0.3,
        }).addTo(PATHLEGS.layer);
      }
    }
  }
}

function wirePathLegs() {
  if (typeof map !== "undefined" && map) {
    PATHLEGS.layer = L.layerGroup().addTo(map);
  }
  // A grip drag that is cancelled outright never fires dragend. Release the
  // rebuild lock on any pointer release so a lost drag cannot freeze the
  // gizmos until the next reload. Deferred, so that on an ordinary drop
  // dragend still gets to finish Leaflet's teardown before anything can
  // clear the layer out from under it.
  for (const name of ["mouseup", "pointerup", "pointercancel"]) {
    window.addEventListener(name, () => {
      setTimeout(() => { PATHLEGS.dragging = false; }, 0);
    }, true);
  }
}

window.PATHLEGS = PATHLEGS;
window.pathKind = pathKind;
window.setPathKind = setPathKind;
window.defaultArcPath = defaultArcPath;
window.defaultHermitePath = defaultHermitePath;
window.syncHermiteJoin = syncHermiteJoin;
window.defaultBsplinePath = defaultBsplinePath;
window.coalesceBsplines = coalesceBsplines;
window.renderPathInspector = renderPathInspector;
window.renderPathGizmos = renderPathGizmos;
window.wirePathLegs = wirePathLegs;
wirePathLegs();
