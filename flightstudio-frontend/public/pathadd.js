"use strict";

// Interactive path adders. Draw is still click-to-append. Add segment
// places one authored leg from the selected waypoint. B-spline stays
// active: each click appends a fit point to the same span.

const PATHADD = {
  kind: null,
  arcMode: "center",
  picks: [],
  placedStart: null,
  hover: null,
  layer: null,
  spanStartId: null,
};

const PATHADD_EARTH_M = 6371000;
const PATHADD_STEP_RAD = 15 * Math.PI / 180;
const PATHADD_MAX_NEW = 36;

function pathAddActive() {
  return Boolean(PATHADD.kind);
}

function pathAddStartKey() {
  if (PATHADD.placedStart) return null;
  if (state.track !== "flight" || !state.doc) return null;
  const list = state.doc.flight_keyframes || [];
  if (state.selected != null && list[state.selected]) return list[state.selected];
  return list[list.length - 1] || null;
}

function pathAddKeyframeById(id) {
  return (state.doc?.flight_keyframes || []).find((key) => key.id === id) || null;
}

function pathAddOwningSpan(key) {
  const list = state.doc?.flight_keyframes || [];
  if (PATHADD.spanStartId) {
    const start = pathAddKeyframeById(PATHADD.spanStartId);
    if (start?.path?.kind === "BSPLINE") return start;
  }
  if (key?.path?.kind === "BSPLINE") return key;
  const index = key ? list.indexOf(key) : -1;
  for (let i = 0; i < list.length; i++) {
    const path = list[i].path;
    if (path?.kind !== "BSPLINE") continue;
    const end = list.findIndex((item) => item.id === path.end_id);
    if (end <= i) continue;
    if (index >= i && index <= end) return list[i];
    if (index < 0 && end === list.length - 1) return list[i];
  }
  return null;
}

function pathAddBsplineStart() {
  return pathAddOwningSpan(pathAddStartKey());
}

function pathAddBsplineTip() {
  const start = pathAddBsplineStart();
  if (!start) return null;
  return pathAddKeyframeById(start.path?.end_id) || start;
}

function pathAddStartPoint() {
  if (PATHADD.placedStart) return PATHADD.placedStart;
  if (PATHADD.kind === "bspline") {
    const tip = pathAddBsplineTip();
    if (tip) return { lat: tip.lat, lon: tip.lon };
  }
  const key = pathAddStartKey();
  return key ? { lat: key.lat, lon: key.lon } : null;
}

function pathAddToEn(origin, lat, lon) {
  const north = (lat - origin.lat) * Math.PI / 180 * PATHADD_EARTH_M;
  const east = (lon - origin.lon) * Math.PI / 180 * PATHADD_EARTH_M
    * Math.cos(origin.lat * Math.PI / 180);
  return { east, north };
}

function pathAddFromEn(origin, east, north) {
  if (typeof offsetLatLon === "function") return offsetLatLon(origin.lat, origin.lon, north, east);
  const dLat = (north / PATHADD_EARTH_M) * (180 / Math.PI);
  const dLon = (east / (PATHADD_EARTH_M * Math.cos(origin.lat * Math.PI / 180))) * (180 / Math.PI);
  return { lat: origin.lat + dLat, lon: origin.lon + dLon };
}

function pathAddHypot(a, b) {
  const en = pathAddToEn(a, b.lat, b.lon);
  return Math.hypot(en.east, en.north);
}

function pathAddBearing(from, to) {
  const en = pathAddToEn(from, to.lat, to.lon);
  return Math.atan2(en.east, en.north);
}

function pathAddNormAngle(rad) {
  const tau = Math.PI * 2;
  return ((rad % tau) + tau) % tau;
}

function pathAddCcw(from, to) {
  return pathAddNormAngle(to - from);
}

function pathAddSweepThrough(start, through, end) {
  if (pathAddCcw(start, through) <= pathAddCcw(start, end) + 1e-9) {
    return { start, delta: pathAddCcw(start, end) };
  }
  return { start, delta: -pathAddCcw(end, start) };
}

function pathAddCircumcenter(a, b, c) {
  const pb = pathAddToEn(a, b.lat, b.lon);
  const pc = pathAddToEn(a, c.lat, c.lon);
  const d = 2 * (pb.east * pc.north - pc.east * pb.north);
  if (Math.abs(d) < 1) return null;
  const b2 = pb.east * pb.east + pb.north * pb.north;
  const c2 = pc.east * pc.east + pc.north * pc.north;
  const east = (b2 * pc.north - c2 * pb.north) / d;
  const north = (c2 * pb.east - b2 * pc.east) / d;
  return pathAddFromEn(a, east, north);
}

function pathAddSampleArc(center, radiusM, startAng, delta, count) {
  const points = [];
  const n = Math.max(1, count);
  for (let i = 1; i <= n; i++) {
    const ang = startAng + delta * (i / n);
    points.push(pathAddFromEn(center, radiusM * Math.sin(ang), radiusM * Math.cos(ang)));
  }
  return points;
}

function pathAddArcFromCenter(start, center, rim) {
  const radius = pathAddHypot(center, start);
  if (radius < 2) return { error: "Centre is too close to the start point." };
  const a0 = pathAddBearing(center, start);
  const a1 = pathAddBearing(center, rim);
  let delta = a1 - a0;
  while (delta > Math.PI) delta -= Math.PI * 2;
  while (delta < -Math.PI) delta += Math.PI * 2;
  if (Math.abs(delta) < 1e-3) return { error: "Pick a circumference point away from the start." };
  const steps = Math.max(1, Math.min(PATHADD_MAX_NEW, Math.round(Math.abs(delta) / PATHADD_STEP_RAD)));
  return { center, radius, start: a0, delta, points: pathAddSampleArc(center, radius, a0, delta, steps) };
}

function pathAddPicksNeeded() {
  return PATHADD.kind === "arc" ? 2 : 1;
}

function pathAddIncomingTangent(start) {
  const key = pathAddStartKey();
  const list = state.doc?.flight_keyframes || [];
  const index = key ? list.indexOf(key) : -1;
  const prev = index > 0 ? list[index - 1] : null;
  if (prev && start) {
    const en = pathAddToEn(prev, start.lat, start.lon);
    const len = Math.hypot(en.east, en.north);
    if (len > 2) return { east: en.east / len, north: en.north / len };
  }
  const t = key?.time_offset;
  const samples = state.preview?.samples || [];
  if (Number.isFinite(t) && samples.length) {
    let best = samples[0];
    let gap = Infinity;
    for (const sample of samples) {
      const d = Math.abs(sample.t - t);
      if (d < gap) { gap = d; best = sample; }
    }
    if (Number.isFinite(best.heading)) {
      const rad = best.heading * Math.PI / 180;
      return { east: Math.sin(rad), north: Math.cos(rad) };
    }
  }
  return null;
}

function pathAddPointOnCircle(center, radius, toward) {
  const ang = pathAddBearing(center, toward);
  return pathAddFromEn(center, radius * Math.sin(ang), radius * Math.cos(ang));
}

function pathAddTangentCircle(start, through, tangent) {
  if (!tangent) return { error: "Select a waypoint that has a previous segment so the incoming tangent is known." };
  const ab = pathAddToEn(start, through.lat, through.lon);
  const chord = Math.hypot(ab.east, ab.north);
  if (chord < 2) return { error: "Pick a point on the circle away from the start." };
  const left = { east: -tangent.north, north: tangent.east };
  const denom = 2 * (left.east * ab.east + left.north * ab.north);
  if (Math.abs(denom) < 1) {
    return { error: "That point is along the incoming track. Pick a point off to one side." };
  }
  const k = (chord * chord) / denom;
  const radius = Math.abs(k);
  if (radius < 2) return { error: "The turn is too tight. Pick a point farther from the start." };
  const center = pathAddFromEn(start, left.east * k, left.north * k);
  return { center, radius, k, tangent, startAng: pathAddBearing(center, start) };
}

function pathAddArcFromTangent(start, through, end, tangent) {
  const circle = pathAddTangentCircle(start, through, tangent);
  if (circle.error) return circle;
  const toward = end || through;
  const aEnd = pathAddBearing(circle.center, toward);
  const delta = circle.k > 0
    ? -pathAddCcw(aEnd, circle.startAng)
    : pathAddCcw(circle.startAng, aEnd);
  if (Math.abs(delta) < 1e-3) return { error: "Pick where the arc should end, away from the start." };
  const steps = Math.max(1, Math.min(PATHADD_MAX_NEW, Math.round(Math.abs(delta) / PATHADD_STEP_RAD)));
  const points = pathAddSampleArc(circle.center, circle.radius, circle.startAng, delta, steps);
  points[points.length - 1] = pathAddPointOnCircle(circle.center, circle.radius, toward);
  return {
    center: circle.center,
    radius: circle.radius,
    start: circle.startAng,
    delta,
    tangent: circle.tangent,
    snap: points[points.length - 1],
    points,
  };
}

function pathAddArcThrough(a, b, c) {
  const center = pathAddCircumcenter(a, b, c);
  if (!center) return { error: "Those three points are in a line. Pick a different through or end point." };
  const radius = pathAddHypot(center, a);
  if (radius < 2) return { error: "The three points are too close to make an arc." };
  const a0 = pathAddBearing(center, a);
  const aB = pathAddBearing(center, b);
  const aC = pathAddBearing(center, c);
  const sweep = pathAddSweepThrough(a0, aB, aC);
  if (Math.abs(sweep.delta) < 1e-3) return { error: "Pick an end point away from the start." };
  const steps = Math.max(2, Math.min(PATHADD_MAX_NEW, Math.round(Math.abs(sweep.delta) / PATHADD_STEP_RAD)));
  const points = pathAddSampleArc(center, radius, sweep.start, sweep.delta, steps);
  const uB = sweep.delta >= 0
    ? pathAddCcw(sweep.start, aB) / sweep.delta
    : pathAddCcw(aB, sweep.start) / (-sweep.delta);
  const near = Math.max(0, Math.min(points.length - 1, Math.round(uB * steps) - 1));
  if (pathAddHypot(points[near], b) > 8) {
    points.splice(Math.max(0, Math.min(points.length, Math.round(uB * steps))), 0, {
      lat: b.lat, lon: b.lon,
    });
  }
  return { center, radius, start: sweep.start, delta: sweep.delta, points };
}

function pathAddPreviewArc(hover) {
  const start = pathAddStartPoint();
  const picks = PATHADD.picks;
  if (!start) return null;
  if (PATHADD.kind !== "arc") {
    const end = picks[0] || hover;
    if (!end) return { points: [] };
    return { points: [end] };
  }
  if (PATHADD.arcMode === "center") {
    if (!picks.length) return null;
    const rim = picks[1] || hover;
    if (!rim) {
      return { center: picks[0], radius: pathAddHypot(picks[0], start), points: [] };
    }
    return pathAddArcFromCenter(start, picks[0], rim);
  }
  if (PATHADD.arcMode === "tangent") {
    const tangent = pathAddIncomingTangent(start);
    const through = picks[0] || hover;
    if (!through) return { tangent, points: [] };
    return pathAddArcFromTangent(start, through, picks[1] || (picks[0] ? hover : null), tangent);
  }
  if (!picks.length) return null;
  const end = picks[1] || hover;
  if (!end) return { points: [picks[0]] };
  return pathAddArcThrough(start, picks[0], end);
}

function pathAddClearPreview() {
  PATHADD.layer?.clearLayers();
}

function pathAddPaintPreview() {
  if (!PATHADD.layer) return;
  PATHADD.layer.clearLayers();
  if (!pathAddActive()) return;
  const start = pathAddStartPoint();
  const draft = pathAddPreviewArc(PATHADD.hover);
  if (start) {
    L.circleMarker([start.lat, start.lon], {
      radius: 7, color: "#4ea1ff", weight: 2, fillColor: "#0b1017", fillOpacity: 1,
    }).addTo(PATHADD.layer);
  }
  for (const pick of PATHADD.picks) {
    L.circleMarker([pick.lat, pick.lon], {
      radius: 6, color: "#ffa23e", weight: 2, fillColor: "#ffa23e", fillOpacity: 0.9,
    }).addTo(PATHADD.layer);
  }
  const tangent = draft?.tangent || (PATHADD.arcMode === "tangent" && start
    ? pathAddIncomingTangent(start) : null);
  if (start && tangent) {
    const tip = pathAddFromEn(start, tangent.east * 240, tangent.north * 240);
    L.polyline([[start.lat, start.lon], [tip.lat, tip.lon]], {
      color: "#7ee29a", weight: 2, interactive: false,
    }).addTo(PATHADD.layer);
  }
  if (draft?.center && Number.isFinite(draft.radius)) {
    L.circle([draft.center.lat, draft.center.lon], {
      radius: draft.radius, color: "#ffa23e", weight: 1, dashArray: "5 6",
      fill: false, interactive: false,
    }).addTo(PATHADD.layer);
    L.circleMarker([draft.center.lat, draft.center.lon], {
      radius: 4, color: "#ffa23e", weight: 2, fillOpacity: 0,
    }).addTo(PATHADD.layer);
  }
  if (draft?.snap && PATHADD.arcMode === "tangent" && PATHADD.picks.length) {
    const hover = PATHADD.hover;
    if (hover && pathAddHypot(hover, draft.snap) > 12) {
      L.polyline([[hover.lat, hover.lon], [draft.snap.lat, draft.snap.lon]], {
        color: "#7ee29a", weight: 1, dashArray: "3 5", interactive: false,
      }).addTo(PATHADD.layer);
    }
    L.circleMarker([draft.snap.lat, draft.snap.lon], {
      radius: 7, color: "#7ee29a", weight: 2, fillColor: "#7ee29a", fillOpacity: 0.85,
    }).addTo(PATHADD.layer);
  }
  if (draft?.points?.length && start) {
    L.polyline(
      [[start.lat, start.lon], ...draft.points.map((p) => [p.lat, p.lon])],
      { color: "#4ea1ff", weight: 3, dashArray: "8 6", interactive: false },
    ).addTo(PATHADD.layer);
  } else if (draft?.points?.length) {
    L.polyline(draft.points.map((p) => [p.lat, p.lon]), {
      color: "#4ea1ff", weight: 3, dashArray: "8 6", interactive: false,
    }).addTo(PATHADD.layer);
  }
}

function pathAddHint() {
  if (!pathAddActive()) return "";
  if (typeof map3dMode === "function" && map3dMode()) {
    return "Switch to 2D to click the segment on the map. Esc or the same kind again cancels.";
  }
  const start = pathAddStartPoint();
  if (PATHADD.kind === "straight") {
    if (!start) return "Click the map to place the start, then the end of the straight.";
    return "Click the end of the straight segment.";
  }
  if (PATHADD.kind === "hermite") {
    if (!start) return "Click the map to place the start, then the end of the Hermite.";
    return "Click the end. Out follows the previous curve, In the next; edit the handles after.";
  }
  if (PATHADD.kind === "bspline") {
    if (!start) return "Click the map to place the start, then each fit point.";
    if (pathAddBsplineStart()) {
      return "Click to add another fit point. Esc or B-spline again finishes the span.";
    }
    return "Click the next fit point. Keep clicking; Esc finishes.";
  }
  if (PATHADD.arcMode === "center") {
    if (!start) return "Click the map to place the start of the arc.";
    if (!PATHADD.picks.length) return "Click the centre of the arc.";
    if (PATHADD.picks.length === 1) {
      return "Click a point on the circumference. The arc runs from the start around that centre.";
    }
  } else if (PATHADD.arcMode === "tangent") {
    if (!start) return "Select a waypoint that follows another, then click Arc again.";
    if (!pathAddIncomingTangent(start)) {
      return "Start-tangent needs a previous waypoint. Select one that is not the first.";
    }
    if (!PATHADD.picks.length) {
      return "Click a point on the intended circle, off to one side of the incoming track.";
    }
    if (PATHADD.picks.length === 1) {
      return "Click where the arc should end. That point is snapped onto the circle; it does not change the radius.";
    }
  } else {
    if (!start) return "Click the map to place the start of the arc.";
    if (!PATHADD.picks.length) return "Click the point the arc should pass through.";
    if (PATHADD.picks.length === 1) return "Click the end of the arc. It will pass through the three points.";
  }
  return "Click the same kind again or press Esc to cancel.";
}

function pathAddSyncChrome() {
  const on = pathAddActive();
  $("map")?.classList.toggle("drawing", on || state.drawing);
  const showSeg = state.track === "flight";
  if ($("pathadd-seg-bar")) $("pathadd-seg-bar").hidden = !showSeg;
  if ($("pathadd-map-bar")) $("pathadd-map-bar").hidden = !showSeg;
  if ($("pathadd-arc-bar")) $("pathadd-arc-bar").hidden = !(on && PATHADD.kind === "arc");
  document.querySelectorAll("[data-pathadd]").forEach((btn) => {
    btn.classList.toggle("toggled", on && btn.dataset.pathadd === PATHADD.kind);
  });
  document.querySelectorAll("input[name=pathadd-arc-mode]").forEach((input) => {
    input.checked = input.value === PATHADD.arcMode;
  });
  if (typeof renderKeyframeList === "function") renderKeyframeList();
  pathAddPaintPreview();
}

function cancelPathAdd() {
  PATHADD.kind = null;
  PATHADD.picks = [];
  PATHADD.placedStart = null;
  PATHADD.hover = null;
  PATHADD.spanStartId = null;
  pathAddClearPreview();
  pathAddSyncChrome();
}

function setPathAddKind(kind) {
  if (PATHADD.kind === kind) {
    cancelPathAdd();
    return;
  }
  if (kind !== "straight" && kind !== "arc" && kind !== "hermite" && kind !== "bspline") {
    cancelPathAdd();
    return;
  }
  state.drawing = false;
  $("btn-draw")?.classList.remove("toggled");
  PATHADD.kind = kind;
  PATHADD.picks = [];
  PATHADD.placedStart = null;
  PATHADD.hover = null;
  PATHADD.spanStartId = kind === "bspline" ? pathAddOwningSpan(pathAddStartKey())?.id || null : null;
  state.track = "flight";
  pathAddSyncChrome();
}

function pathAddArcSpec(start, end, draft) {
  const center = draft.center;
  const ac = pathAddToEn(start, center.lat, center.lon);
  const ab = pathAddToEn(start, end.lat, end.lon);
  const left = { east: -ab.north, north: ab.east };
  const side = left.east * ac.east + left.north * ac.north >= 0 ? "LEFT" : "RIGHT";
  return {
    kind: "ARC",
    side,
    radius_m: Math.max(draft.radius || pathAddHypot(center, start), 1),
    major: Math.abs(draft.delta || 0) > Math.PI + 1e-6,
    plane: { normal_east: 0, normal_up: 1, normal_north: 0 },
  };
}

function pathAddInsertEnd(end, after) {
  if (!state.doc || !end) return null;
  if (typeof ensureWaypointIds === "function") ensureWaypointIds(state.doc);
  const list = state.doc.flight_keyframes;
  if (!after && !pathAddStartKey() && PATHADD.placedStart && typeof appendFlightKeyframe === "function") {
    appendFlightKeyframe(PATHADD.placedStart.lat, PATHADD.placedStart.lon);
  }
  const from = (after && pathAddKeyframeById(after.id)) || after
    || pathAddStartKey() || list[list.length - 1];
  if (!from) return null;
  const startIndex = list.indexOf(from);
  const insertAt = startIndex + 1;
  const prev = list[startIndex - 1];
  const next = list[insertAt];
  const gap = prev ? Math.max(0.5, from.time_offset - prev.time_offset)
    : next ? Math.max(0.5, next.time_offset - from.time_offset)
    : 9;
  for (let i = insertAt; i < list.length; i++) list[i].time_offset += gap;
  const keyframe = typeof blankFlightFields === "function"
    ? blankFlightFields(from, {
      time_offset: from.time_offset + gap,
      lat: end.lat,
      lon: end.lon,
      alt_ft_msl: from.alt_ft_msl,
      path: { kind: "STRAIGHT" },
    })
    : {
      time_offset: from.time_offset + gap,
      time_source: "AUTHORED",
      lat: end.lat,
      lon: end.lon,
      alt_ft_msl: from.alt_ft_msl,
      heading: { mode: "AUTO" },
      pitch: { mode: "AUTO" },
      bank: { mode: "AUTO" },
      easing: { ease_in: 0, ease_out: 0, hold_s: 0 },
      path: { kind: "STRAIGHT" },
      on_ground: Boolean(from.on_ground),
    };
  list.splice(insertAt, 0, keyframe);
  state.doc.meta.duration_seconds = lastTime();
  if (typeof setFlightSelection === "function") setFlightSelection([from.id], from.id);
  return { from, keyframe };
}

function pathAddCommit(draft) {
  const end = draft.snap || draft.points?.[draft.points.length - 1];
  if (!end || !draft.center) return;
  const made = pathAddInsertEnd(end);
  if (!made) return;
  made.from.path = pathAddArcSpec(made.from, end, draft);
  if (typeof syncHermiteJoin === "function") syncHermiteJoin(made.from);
  cancelPathAdd();
  touched();
}

function pathAddCommitBspline(end) {
  const owner = pathAddOwningSpan(pathAddStartKey());
  if (owner?.path?.kind === "BSPLINE" && owner.path.end_id) {
    const tip = pathAddKeyframeById(owner.path.end_id) || owner;
    const made = pathAddInsertEnd(end, tip);
    if (!made) return;
    owner.path.end_id = made.keyframe.id;
    owner.path.kind = "BSPLINE";
    if (typeof coalesceBsplines === "function") coalesceBsplines(state.doc.flight_keyframes);
    PATHADD.spanStartId = owner.id;
    if (typeof setFlightSelection === "function") setFlightSelection([owner.id], owner.id);
  } else {
    const made = pathAddInsertEnd(end);
    if (!made) return;
    const start = owner || made.from;
    if (start !== made.from && start?.path?.kind === "BSPLINE") {
      start.path.end_id = made.keyframe.id;
    } else {
      made.from.path = {
        kind: "BSPLINE",
        end_id: made.keyframe.id,
        tolerance_m: made.from.path?.tolerance_m ?? 50,
      };
    }
    PATHADD.spanStartId = (start || made.from).id;
    if (typeof setFlightSelection === "function") {
      setFlightSelection([PATHADD.spanStartId], PATHADD.spanStartId);
    }
  }
  const spanStart = pathAddKeyframeById(PATHADD.spanStartId);
  if (spanStart && typeof syncHermiteJoin === "function") syncHermiteJoin(spanStart);
  PATHADD.picks = [];
  PATHADD.hover = null;
  PATHADD.placedStart = null;
  pathAddSyncChrome();
  touched();
}

function pathAddCommitEnd(end) {
  if (PATHADD.kind === "bspline") {
    pathAddCommitBspline(end);
    return;
  }
  const made = pathAddInsertEnd(end);
  if (!made) return;
  if (PATHADD.kind === "hermite" && typeof defaultHermitePath === "function") {
    made.from.path = defaultHermitePath(made.from, made.keyframe);
  } else {
    made.from.path = { kind: "STRAIGHT" };
  }
  if (typeof syncHermiteJoin === "function") syncHermiteJoin(made.from);
  cancelPathAdd();
  touched();
}

function pathAddClick(latlng) {
  if (!pathAddActive() || !state.doc) return;
  state.track = "flight";
  const point = { lat: latlng.lat, lon: latlng.lng ?? latlng.lon };
  if (!pathAddStartPoint()) {
    PATHADD.placedStart = point;
    pathAddPaintPreview();
    if (typeof renderKeyframeList === "function") renderKeyframeList();
    return;
  }
  if (PATHADD.kind === "arc" && PATHADD.arcMode === "tangent" && !pathAddIncomingTangent(pathAddStartPoint())) {
    if ($("add-hint")) {
      $("add-hint").textContent = "Start-tangent needs a previous waypoint. Select one that is not the first.";
    }
    return;
  }
  PATHADD.picks.push(point);
  if (PATHADD.picks.length < pathAddPicksNeeded()) {
    pathAddPaintPreview();
    if (typeof renderKeyframeList === "function") renderKeyframeList();
    return;
  }
  if (PATHADD.kind !== "arc") {
    pathAddCommitEnd(point);
    return;
  }
  const start = pathAddStartPoint();
  const draft = PATHADD.arcMode === "center"
    ? pathAddArcFromCenter(start, PATHADD.picks[0], PATHADD.picks[1])
    : PATHADD.arcMode === "tangent"
      ? pathAddArcFromTangent(start, PATHADD.picks[0], PATHADD.picks[1], pathAddIncomingTangent(start))
      : pathAddArcThrough(start, PATHADD.picks[0], PATHADD.picks[1]);
  if (draft.error) {
    PATHADD.picks.pop();
    pathAddPaintPreview();
    if ($("add-hint")) $("add-hint").textContent = draft.error;
    return;
  }
  pathAddCommit(draft);
}

function pathAddHover(latlng) {
  if (!pathAddActive()) return;
  PATHADD.hover = { lat: latlng.lat, lon: latlng.lng ?? latlng.lon };
  pathAddPaintPreview();
}

function wirePathAdd() {
  PATHADD.layer = L.layerGroup().addTo(map);
  $("btn-arc")?.addEventListener("click", () => setPathAddKind("arc"));
  document.querySelectorAll("[data-pathadd]").forEach((btn) => {
    btn.addEventListener("click", () => setPathAddKind(btn.dataset.pathadd));
  });
  document.querySelectorAll("input[name=pathadd-arc-mode]").forEach((input) => {
    input.addEventListener("change", () => {
      if (!input.checked) return;
      PATHADD.arcMode = input.value === "through" || input.value === "tangent"
        ? input.value : "center";
      PATHADD.picks = [];
      PATHADD.hover = null;
      pathAddSyncChrome();
    });
  });
  map.on("mousemove", (event) => pathAddHover(event.latlng));
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && pathAddActive()) {
      event.preventDefault();
      cancelPathAdd();
    }
  });
}

window.PATHADD = PATHADD;
window.pathAddActive = pathAddActive;
window.pathAddHint = pathAddHint;
window.pathAddClick = pathAddClick;
window.cancelPathAdd = cancelPathAdd;
window.setPathAddKind = setPathAddKind;
window.wirePathAdd = wirePathAdd;
wirePathAdd();
