"use strict";

// Flight-waypoint identity, multi-select, groups and bulk edits. The solver
// still sees a time-sorted list; this file is editor metadata on top of it.

const EARTH_RADIUS_M = 6371000;
const GROUP_COLORS = ["#4ea1ff", "#3ecf9a", "#ffa23e", "#c084fc", "#f472b6", "#22d3ee"];
const SHOT_STORE = "flightstudio.shotOpen";
const DOCK_STORE = "flightstudio.dock";

function mintWaypointId() {
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function ensureFlightPaths(doc) {
  for (const key of doc?.flight_keyframes || []) {
    if (!key.path || !key.path.kind) key.path = { kind: "STRAIGHT" };
    delete key.path_mode;
  }
}

function ensureWaypointIds(doc) {
  if (!doc) return;
  if (!Array.isArray(doc.groups)) doc.groups = [];
  const seen = new Set();
  for (const key of doc.flight_keyframes || []) {
    if (!key.id || seen.has(key.id)) key.id = mintWaypointId();
    if (typeof key.name !== "string") key.name = "";
    seen.add(key.id);
  }
  const known = new Set((doc.flight_keyframes || []).map((k) => k.id));
  const claimed = new Set();
  for (const group of doc.groups) {
    group.member_ids = (group.member_ids || []).filter((id) => {
      if (!known.has(id) || claimed.has(id)) return false;
      claimed.add(id);
      return true;
    });
  }
}

function blankFlightFields(previous, extras) {
  return {
    id: mintWaypointId(),
    name: "",
    time_source: "AUTHORED",
    heading: { mode: "AUTO" },
    pitch: { mode: "AUTO" },
    bank: { mode: "AUTO" },
    easing: { ease_in: 0, ease_out: 0, hold_s: 0 },
    path: { kind: "STRAIGHT" },
    on_ground: Boolean(previous?.on_ground),
    ...extras,
  };
}

function selectedIds() {
  if (!Array.isArray(state.selectedIds)) state.selectedIds = [];
  return state.selectedIds;
}

function flightSelectedCount() {
  return state.track === "flight" ? selectedIds().length : 0;
}

function isFlightIndexSelected(index) {
  const key = state.doc?.flight_keyframes?.[index];
  return Boolean(key && selectedIds().includes(key.id));
}

function selectedFlightKeyframes() {
  if (state.track !== "flight" || !state.doc) return [];
  const want = new Set(selectedIds());
  return (state.doc.flight_keyframes || []).filter((k) => want.has(k.id));
}

function setFlightSelection(ids, primaryId) {
  const list = state.doc?.flight_keyframes || [];
  const known = new Set(list.map((k) => k.id));
  state.selectedIds = (ids || []).filter((id) => known.has(id));
  const primary = primaryId && known.has(primaryId)
    ? primaryId
    : state.selectedIds[state.selectedIds.length - 1] || null;
  state.selected = primary ? list.findIndex((k) => k.id === primary) : null;
  if (state.selected < 0) state.selected = state.selectedIds.length ? 0 : null;
}

function selectFlight(index, event) {
  const list = state.doc?.flight_keyframes || [];
  const key = list[index];
  if (!key) return;
  state.track = "flight";
  const ids = selectedIds();
  if (event && event.shiftKey && state.selected != null) {
    const lo = Math.min(state.selected, index);
    const hi = Math.max(state.selected, index);
    setFlightSelection(list.slice(lo, hi + 1).map((k) => k.id), key.id);
  } else if (event && (event.ctrlKey || event.metaKey)) {
    if (ids.includes(key.id)) {
      setFlightSelection(ids.filter((id) => id !== key.id), ids.filter((id) => id !== key.id).at(-1));
    } else {
      setFlightSelection([...ids, key.id], key.id);
    }
  } else {
    setFlightSelection([key.id], key.id);
  }
  renderAfterSelect();
}

function select(index) {
  if (state.track === "flight") {
    selectFlight(index);
    return;
  }
  state.selected = index;
  state.selectedIds = [];
  renderAfterSelect();
}

function renderAfterSelect() {
  renderKeyframeList();
  renderInspector();
  renderMap();
  if (typeof onMap2dSelect === "function") onMap2dSelect(state.selected);
  if (typeof markSelectedRow === "function") markSelectedRow();
}

function groupOf(id) {
  return (state.doc?.groups || []).find((g) => (g.member_ids || []).includes(id)) || null;
}

function nextGroupColor() {
  const used = new Set((state.doc?.groups || []).map((g) => g.color));
  return GROUP_COLORS.find((c) => !used.has(c)) || GROUP_COLORS[(state.doc.groups.length) % GROUP_COLORS.length];
}

function offsetLatLon(lat, lon, northM, eastM) {
  const dLat = (northM / EARTH_RADIUS_M) * (180 / Math.PI);
  const dLon = (eastM / (EARTH_RADIUS_M * Math.cos(lat * Math.PI / 180))) * (180 / Math.PI);
  return {
    lat: Math.min(90, Math.max(-90, lat + dLat)),
    lon: Math.min(180, Math.max(-180, lon + dLon)),
  };
}

function lerp(a, b, u) {
  return a + (b - a) * u;
}

function dropEmptyGroups() {
  if (!state.doc) return;
  state.doc.groups = (state.doc.groups || []).filter((g) => (g.member_ids || []).length);
}

function removeSelected() {
  // waypoints.js loads after app.js and owns this button — still honour
  // program-mode deletes here or Remove silently no-ops on segments.
  if (typeof isProgramMode === "function" && isProgramMode()) {
    if (state.track === "camera") {
      const list = state.program?.camera_keyframes;
      if (!Array.isArray(list) || typeof state.selected !== "number") return;
      if (!list[state.selected]) return;
      list.splice(state.selected, 1);
      state.selected = list.length
        ? Math.min(state.selected, list.length - 1) : null;
      if (typeof touched === "function") touched();
      return;
    }
    if (typeof removeProgramSegment === "function") removeProgramSegment();
    return;
  }
  const list = frames();
  const minimum = (state.track === "controls" || state.track === "systems"
    || state.track === "map" || state.track === "marks") ? 0 : 1;
  if (state.track === "flight") {
    const ids = new Set(selectedIds());
    if (!ids.size) return;
    const keep = list.filter((k) => !ids.has(k.id));
    if (keep.length < minimum) return;
    list.splice(0, list.length, ...keep);
    for (const group of state.doc.groups || []) {
      group.member_ids = (group.member_ids || []).filter((id) => !ids.has(id));
    }
    dropEmptyGroups();
    const next = keep[Math.min(state.selected ?? 0, keep.length - 1)];
    setFlightSelection(next ? [next.id] : [], next?.id);
    state.doc.meta.duration_seconds = lastTime();
    touched();
    return;
  }
  if (state.selected === null || list.length <= minimum) return;
  list.splice(state.selected, 1);
  state.selected = list.length ? Math.min(state.selected, list.length - 1) : null;
  state.doc.meta.duration_seconds = lastTime();
  touched();
}

function moveSelectedBy(northM, eastM, altFt) {
  const keys = selectedFlightKeyframes();
  if (!keys.length) return;
  for (const key of keys) {
    const next = offsetLatLon(key.lat, key.lon, northM, eastM);
    key.lat = next.lat;
    key.lon = next.lon;
    key.alt_ft_msl += altFt;
  }
  touched();
}

function moveSelectedTo({ lat, lon, altFt, applyLat, applyLon, applyAlt }) {
  const keys = selectedFlightKeyframes();
  if (!keys.length) return;
  const nextLat = Number(lat);
  const nextLon = Number(lon);
  const nextAlt = Number(altFt);
  for (const key of keys) {
    if (applyLat && Number.isFinite(nextLat)) key.lat = Math.min(90, Math.max(-90, nextLat));
    if (applyLon && Number.isFinite(nextLon)) key.lon = Math.min(180, Math.max(-180, nextLon));
    if (applyAlt && Number.isFinite(nextAlt)) key.alt_ft_msl = nextAlt;
  }
  touched();
}

function moveDialogMode() {
  return document.querySelector("input[name=move-mode]:checked")?.value || "relative";
}

function syncMoveIgnoreInputs() {
  const lat = $("move-lat");
  const lon = $("move-lon");
  const alt = $("move-abs-alt");
  if (lat) lat.disabled = Boolean($("move-ignore-lat")?.checked);
  if (lon) lon.disabled = Boolean($("move-ignore-lon")?.checked);
  if (alt) alt.disabled = Boolean($("move-ignore-alt")?.checked);
}

function syncMoveDialogMode() {
  const abs = moveDialogMode() === "absolute";
  if ($("move-relative-fields")) $("move-relative-fields").hidden = abs;
  if ($("move-absolute-fields")) $("move-absolute-fields").hidden = !abs;
  if ($("move-relative-hint")) $("move-relative-hint").hidden = abs;
  if ($("move-absolute-hint")) $("move-absolute-hint").hidden = !abs;
  syncMoveIgnoreInputs();
}

function openMoveDialog() {
  const key = (typeof frames === "function" ? frames()[state.selected] : null)
    || selectedFlightKeyframes()[0];
  if (key) {
    if ($("move-lat")) $("move-lat").value = key.lat;
    if ($("move-lon")) $("move-lon").value = key.lon;
    if ($("move-abs-alt")) $("move-abs-alt").value = key.alt_ft_msl;
  }
  const ignoreLat = $("move-ignore-lat");
  const ignoreLon = $("move-ignore-lon");
  const ignoreAlt = $("move-ignore-alt");
  if (ignoreLat) ignoreLat.checked = true;
  if (ignoreLon) ignoreLon.checked = true;
  if (ignoreAlt) ignoreAlt.checked = false;
  syncMoveDialogMode();
  $("move-dialog").showModal();
}

function applyMoveDialog() {
  if (moveDialogMode() === "absolute") {
    moveSelectedTo({
      lat: parseFloat($("move-lat")?.value),
      lon: parseFloat($("move-lon")?.value),
      altFt: parseFloat($("move-abs-alt")?.value),
      applyLat: !$("move-ignore-lat")?.checked,
      applyLon: !$("move-ignore-lon")?.checked,
      applyAlt: !$("move-ignore-alt")?.checked,
    });
  } else {
    moveSelectedBy(
      parseFloat($("move-north").value) || 0,
      parseFloat($("move-east").value) || 0,
      parseFloat($("move-rel-alt").value) || 0,
    );
  }
  $("move-dialog").close();
}

function retimeSelected(mode, seconds) {
  const keys = selectedFlightKeyframes().slice().sort((a, b) => a.time_offset - b.time_offset);
  if (!keys.length) return "";
  const dt = mode === "to" ? seconds - keys[0].time_offset : seconds;
  const floor = Math.min(...keys.map((k) => k.time_offset + dt));
  const shift = floor < 0 ? dt - floor : dt;
  for (const key of keys) key.time_offset = Math.max(0, key.time_offset + shift);
  const minT = Math.min(...keys.map((k) => k.time_offset));
  const maxT = Math.max(...keys.map((k) => k.time_offset));
  const selected = new Set(keys.map((k) => k.id));
  const outsiders = (state.doc.flight_keyframes || []).filter((k) => !selected.has(k.id)
    && k.time_offset > minT + 1e-6 && k.time_offset < maxT - 1e-6);
  state.doc.meta.duration_seconds = lastTime();
  touched();
  if (!outsiders.length) return "";
  return `${outsiders.length} unselected waypoint${outsiders.length === 1 ? "" : "s"} now sit inside this run.`;
}

function redistributeSelected(mode) {
  const keys = selectedFlightKeyframes().slice().sort((a, b) => a.time_offset - b.time_offset);
  if (keys.length < 2) return;
  const first = keys[0];
  const last = keys[keys.length - 1];
  const spanT = last.time_offset - first.time_offset;
  keys.forEach((key, i) => {
    if (i === 0 || i === keys.length - 1) return;
    const u = mode === "keep-times" && spanT > 1e-6
      ? (key.time_offset - first.time_offset) / spanT
      : i / (keys.length - 1);
    const northEast = (() => {
      const north = (last.lat - first.lat) * Math.PI / 180 * EARTH_RADIUS_M;
      const east = (last.lon - first.lon) * Math.PI / 180 * EARTH_RADIUS_M
        * Math.cos(first.lat * Math.PI / 180);
      return offsetLatLon(first.lat, first.lon, north * u, east * u);
    })();
    key.lat = northEast.lat;
    key.lon = northEast.lon;
    key.alt_ft_msl = lerp(first.alt_ft_msl, last.alt_ft_msl, u);
    if (mode === "even-time") {
      key.time_offset = first.time_offset + spanT * (i / (keys.length - 1));
    }
  });
  if (mode === "even-time") state.doc.meta.duration_seconds = lastTime();
  touched();
}

function assignSelectionToGroup(groupId, name, color) {
  const ids = selectedIds();
  if (!ids.length || !state.doc) return;
  if (!state.doc.groups) state.doc.groups = [];
  for (const group of state.doc.groups) {
    group.member_ids = (group.member_ids || []).filter((id) => !ids.includes(id));
  }
  if (!groupId) {
    const group = {
      id: mintWaypointId(),
      name: (name || "").trim() || "Group",
      color: color || nextGroupColor(),
      member_ids: [...ids],
    };
    state.doc.groups.push(group);
  } else {
    const group = state.doc.groups.find((g) => g.id === groupId);
    if (group) {
      if (name) group.name = name;
      if (color) group.color = color;
      group.member_ids = [...new Set([...(group.member_ids || []), ...ids])];
    }
  }
  dropEmptyGroups();
  touched();
}

function dissolveSelectionGroups() {
  const ids = new Set(selectedIds());
  if (!ids.size || !state.doc) return;
  for (const group of state.doc.groups || []) {
    group.member_ids = (group.member_ids || []).filter((id) => !ids.has(id));
  }
  dropEmptyGroups();
  touched();
}

function renderGroupChips() {
  const host = $("group-chips");
  if (!host) return;
  host.innerHTML = "";
  const groups = state.doc?.groups || [];
  const show = state.track === "flight" && groups.length;
  host.hidden = !show;
  if (!show) return;
  for (const group of groups) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "group-chip";
    const selected = selectedFlightKeyframes();
    if (selected.length && selected.every((k) => (group.member_ids || []).includes(k.id))) {
      chip.classList.add("active");
    }
    chip.innerHTML = `<span class="swatch" style="background:${group.color}"></span>${group.name || "Group"}`;
    chip.title = "Select every waypoint in this group";
    chip.onclick = () => {
      const members = (state.doc.flight_keyframes || [])
        .filter((k) => (group.member_ids || []).includes(k.id));
      if (!members.length) return;
      state.track = "flight";
      setFlightSelection(members.map((k) => k.id), members[0].id);
      renderAfterSelect();
    };
    host.appendChild(chip);
  }
}

function renderBulkBar() {
  const bar = $("bulk-bar");
  if (!bar) return;
  const many = state.track === "flight" && selectedIds().length > 1;
  bar.hidden = !many;
}

function waypointLabel(keyframe, index) {
  const name = (keyframe.name || "").trim();
  return name || `#${index + 1}`;
}

function fillGroupSelect(select, currentId) {
  select.innerHTML = "";
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "None";
  select.appendChild(none);
  for (const group of state.doc?.groups || []) {
    const option = document.createElement("option");
    option.value = group.id;
    option.textContent = group.name || "Group";
    select.appendChild(option);
  }
  const fresh = document.createElement("option");
  fresh.value = "__new__";
  fresh.textContent = "New group…";
  select.appendChild(fresh);
  select.value = currentId || "";
}

function renderFlightIdentity(host, keyframe, index) {
  host.appendChild(field("Name", (() => {
    const input = document.createElement("input");
    input.type = "text";
    input.value = keyframe.name || "";
    input.placeholder = `#${index + 1}`;
    input.onchange = () => { keyframe.name = input.value.trim(); touched(); };
    return input;
  })()));
  const current = groupOf(keyframe.id);
  host.appendChild(field("Group", (() => {
    const select = document.createElement("select");
    fillGroupSelect(select, current?.id || "");
    select.onchange = () => {
      setFlightSelection([keyframe.id], keyframe.id);
      if (select.value === "__new__") {
        openGroupDialog();
        return;
      }
      if (!select.value) dissolveSelectionGroups();
      else assignSelectionToGroup(select.value);
    };
    return select;
  })()));
}

function renderBulkInspector(host) {
  const keys = selectedFlightKeyframes();
  const title = document.createElement("h3");
  const groups = [...new Set(keys.map((k) => groupOf(k.id)?.name).filter(Boolean))];
  title.textContent = `${keys.length} waypoints`
    + (groups.length === 1 ? ` · ${groups[0]}` : groups.length > 1 ? " · multiple groups" : "");
  host.appendChild(title);
  const note = document.createElement("p");
  note.className = "hint";
  note.textContent = "Shift-click a range, Ctrl-click to toggle. Use the buttons above to move, retime, group or straighten.";
  host.appendChild(note);
}

function openGroupDialog() {
  const keys = selectedFlightKeyframes();
  if (!keys.length) return;
  $("group-count").textContent = `${keys.length} waypoint${keys.length === 1 ? "" : "s"} selected.`;
  const select = $("group-existing");
  select.innerHTML = `<option value="">New group</option>`;
  for (const group of state.doc?.groups || []) {
    const option = document.createElement("option");
    option.value = group.id;
    option.textContent = group.name || "Group";
    select.appendChild(option);
  }
  const shared = groupOf(keys[0].id);
  const allSame = shared && keys.every((k) => groupOf(k.id)?.id === shared.id);
  select.value = allSame ? shared.id : "";
  $("group-name").value = allSame ? (shared.name || "") : "";
  $("group-color").value = allSame ? shared.color : nextGroupColor();
  $("group-dialog").showModal();
}

function wireShotChrome() {
  const section = $("shot-section");
  const toggle = $("shot-toggle");
  if (!section || !toggle) return;
  const apply = (open) => {
    section.classList.toggle("collapsed", !open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    try { localStorage.setItem(SHOT_STORE, open ? "1" : "0"); } catch (_) { /* ignore */ }
  };
  let open = false;
  try { open = localStorage.getItem(SHOT_STORE) === "1"; } catch (_) { /* ignore */ }
  apply(open);
  toggle.onclick = () => apply(section.classList.contains("collapsed"));
}

function setDock(which) {
  const table = which === "table";
  document.body.classList.toggle("dock-table", table);
  document.body.classList.toggle("dock-profile", !table);
  $("dock-table")?.classList.toggle("active", table);
  $("dock-profile")?.classList.toggle("active", !table);
  $("btn-table")?.classList.toggle("toggled", table);
  const dock = $("table-dock");
  const tools = $("table-tools");
  if (dock) dock.hidden = !table;
  if (tools) tools.hidden = !table;
  try { localStorage.setItem(DOCK_STORE, table ? "table" : "profile"); } catch (_) { /* ignore */ }
  if (table && typeof renderTable === "function" && state.doc) renderTable();
}

function tableDockOpen() {
  return document.body.classList.contains("dock-table");
}

function wireDock() {
  let saved = "profile";
  try { saved = localStorage.getItem(DOCK_STORE) || "profile"; } catch (_) { /* ignore */ }
  setDock(saved === "table" ? "table" : "profile");
  $("dock-profile")?.addEventListener("click", () => setDock("profile"));
  $("dock-table")?.addEventListener("click", () => setDock("table"));
}

function wireInspectorSplit() {
  const handle = $("inspector-split");
  const inspector = $("inspector");
  const aside = inspector?.closest("aside");
  if (!handle || !inspector || !aside) return;
  let drag = null;
  handle.onmousedown = (event) => {
    event.preventDefault();
    drag = { startY: event.clientY, startH: inspector.getBoundingClientRect().height };
    document.body.style.cursor = "ns-resize";
  };
  window.addEventListener("mousemove", (event) => {
    if (!drag) return;
    const next = Math.min(
      aside.getBoundingClientRect().height - 180,
      Math.max(120, drag.startH - (event.clientY - drag.startY)),
    );
    inspector.style.flex = `0 0 ${next}px`;
  });
  window.addEventListener("mouseup", () => {
    if (!drag) return;
    drag = null;
    document.body.style.cursor = "";
  });
}

function wireWaypointDialogs() {
  $("btn-group")?.addEventListener("click", openGroupDialog);
  $("group-apply")?.addEventListener("click", () => {
    const existing = $("group-existing").value;
    assignSelectionToGroup(existing || "", $("group-name").value, $("group-color").value);
    $("group-dialog").close();
  });
  $("group-dissolve")?.addEventListener("click", () => {
    dissolveSelectionGroups();
    $("group-dialog").close();
  });
  $("btn-move")?.addEventListener("click", openMoveDialog);
  $("move-apply")?.addEventListener("click", applyMoveDialog);
  document.querySelectorAll("input[name=move-mode]").forEach((input) => {
    input.addEventListener("change", syncMoveDialogMode);
  });
  ["move-ignore-lat", "move-ignore-lon", "move-ignore-alt"].forEach((id) => {
    $(id)?.addEventListener("change", syncMoveIgnoreInputs);
  });
  $("btn-retime")?.addEventListener("click", () => {
    $("retime-warn").hidden = true;
    $("retime-dialog").showModal();
  });
  $("retime-apply")?.addEventListener("click", () => {
    const mode = document.querySelector("input[name=retime-mode]:checked")?.value || "by";
    const warn = retimeSelected(mode, parseFloat($("retime-seconds").value) || 0);
    const box = $("retime-warn");
    if (warn) {
      box.textContent = warn;
      box.hidden = false;
    } else {
      $("retime-dialog").close();
    }
  });
  $("btn-redistribute")?.addEventListener("click", () => $("redistribute-dialog").showModal());
  $("redistribute-apply")?.addEventListener("click", () => {
    redistributeSelected($("redistribute-mode").value);
    $("redistribute-dialog").close();
  });
}

wireShotChrome();
wireDock();
wireInspectorSplit();
wireWaypointDialogs();
if ($("btn-remove")) $("btn-remove").onclick = removeSelected;

window.mintWaypointId = mintWaypointId;
window.ensureWaypointIds = ensureWaypointIds;
window.ensureFlightPaths = ensureFlightPaths;
window.blankFlightFields = blankFlightFields;
window.selectedIds = selectedIds;
window.flightSelectedCount = flightSelectedCount;
window.isFlightIndexSelected = isFlightIndexSelected;
window.selectedFlightKeyframes = selectedFlightKeyframes;
window.setFlightSelection = setFlightSelection;
window.selectFlight = selectFlight;
window.select = select;
window.groupOf = groupOf;
window.removeSelected = removeSelected;
window.renderGroupChips = renderGroupChips;
window.renderBulkBar = renderBulkBar;
window.waypointLabel = waypointLabel;
window.renderFlightIdentity = renderFlightIdentity;
window.renderBulkInspector = renderBulkInspector;
window.setDock = setDock;
window.tableDockOpen = tableDockOpen;
window.offsetLatLon = offsetLatLon;
window.moveSelectedBy = moveSelectedBy;
window.moveSelectedTo = moveSelectedTo;
window.assignSelectionToGroup = assignSelectionToGroup;
window.dissolveSelectionGroups = dissolveSelectionGroups;
