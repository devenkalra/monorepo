/* Stage 7 — PathProgram editing in the main FlightStudio app.
 *
 * Floating popup + map gizmos for the selected segment. Construction
 * (add/insert/delete) is stage 8. Field schema comes from programFields.js.
 */

(function () {
  "use strict";

  const {
    get, set, PRIMITIVES, KIND_LABEL, readField, writeField,
    isSolverParameter, motionFields,
  } = ProgramFields;

  const PROG = {
    dragging: false,
    popupDrag: null,
    focus: null,
    layer: null,
    rebuildTimer: null,
  };

  function round(value, places = 4) {
    const factor = 10 ** places;
    return Math.round(Number(value) * factor) / factor;
  }

  function ensurePopup() {
    let popup = document.getElementById("program-popup");
    if (popup) return popup;
    popup = document.createElement("div");
    popup.id = "program-popup";
    popup.hidden = true;
    popup.innerHTML = `
      <div class="program-popup-title" id="program-popup-title">
        <span id="program-popup-heading">Segment</span>
        <span class="spacer"></span>
        <button type="button" id="program-popup-close" title="Close">×</button>
      </div>
      <div class="program-popup-body" id="program-popup-body"></div>
      <div class="program-popup-dof" id="program-popup-dof"></div>`;
    const host = document.getElementById("map-wrap") || document.body;
    host.appendChild(popup);
    document.getElementById("program-popup-close").onclick = () => {
      popup.hidden = true;
    };
    wirePopupDrag(popup);
    return popup;
  }

  function wirePopupDrag(popup) {
    const title = document.getElementById("program-popup-title");
    title.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || event.target.closest("button")) return;
      const rect = popup.getBoundingClientRect();
      PROG.popupDrag = {
        x: event.clientX, y: event.clientY,
        left: rect.left, top: rect.top,
      };
      title.setPointerCapture(event.pointerId);
    });
    title.addEventListener("pointermove", (event) => {
      if (!PROG.popupDrag) return;
      const dx = event.clientX - PROG.popupDrag.x;
      const dy = event.clientY - PROG.popupDrag.y;
      popup.style.left = `${PROG.popupDrag.left + dx}px`;
      popup.style.top = `${PROG.popupDrag.top + dy}px`;
      popup.style.right = "auto";
      popup.dataset.anchored = "0";
    });
    title.addEventListener("pointerup", () => { PROG.popupDrag = null; });
    title.addEventListener("pointercancel", () => { PROG.popupDrag = null; });
  }

  function selectedSegment() {
    if (!state.program || state.selected == null || state.selected === "origin") return null;
    return state.program.segments[state.selected] || null;
  }

  function selectedSummary() {
    const segments = state.preview?.segments || [];
    if (state.selected == null || state.selected === "origin") return null;
    return segments[state.selected] || null;
  }

  function originSelected() {
    return isProgramMode() && state.selected === "origin";
  }

  function programTouched(opts = {}) {
    if (!isProgramMode()) return;
    const rebuild = opts.rebuild !== false;
    state.dirty = true;
    if (typeof renderMeta === "function") renderMeta();
    if (rebuild) {
      restoringFocus(() => {
        if (typeof renderKeyframeList === "function") renderKeyframeList();
        renderProgramPopup({ preservePosition: true });
      });
    } else {
      updateDofOnly();
    }
    clearTimeout(PROG.rebuildTimer);
    PROG.rebuildTimer = setTimeout(() => {
      if (typeof solve === "function") solve();
    }, 120);
  }

  function restoringFocus(fn) {
    const active = document.activeElement;
    const id = active?.id || active?.dataset?.field || null;
    const start = active?.selectionStart;
    const end = active?.selectionEnd;
    fn();
    if (!id) return;
    const next = document.getElementById(id)
      || document.querySelector(`[data-field="${CSS.escape(id)}"]`);
    if (!next) return;
    next.focus();
    if (typeof start === "number" && next.setSelectionRange) {
      try { next.setSelectionRange(start, end); } catch (_) { /* not text */ }
    }
  }

  function rebindProgramCameras(cameras, prevSegments, nextSegments) {
    if (!cameras?.length) return cameras || [];
    const idMap = {};
    (prevSegments || []).forEach((seg, index) => {
      const next = nextSegments?.[index];
      if (seg?.id && next?.id && seg.id !== next.id) idMap[seg.id] = next.id;
    });
    const nextIds = new Set((nextSegments || []).map((seg) => seg.id).filter(Boolean));
    const fallback = nextSegments?.[0]?.id || "";
    return cameras.map((key) => {
      const anchor = key.anchor ? { ...key.anchor } : { segment_id: fallback, at: 0.5 };
      if (idMap[anchor.segment_id]) anchor.segment_id = idMap[anchor.segment_id];
      if (anchor.segment_id && !nextIds.has(anchor.segment_id) && fallback) {
        anchor.segment_id = fallback;
      }
      return { ...key, anchor };
    });
  }

  function adoptSolvedProgram(preview) {
    if (!preview?.solved_program || !preview.constrained) return;
    const keep = state.selected;
    const cameras = state.program?.camera_keyframes;
    const prevSegments = state.program?.segments || [];
    state.program = preview.solved_program;
    // Always keep authored cameras. The solve can remint segment ids; rebind
    // anchors so the next preview still produces a camera_track instead of
    // silently falling back to the chase camera once the scrubber moves.
    if (cameras?.length) {
      state.program.camera_keyframes = rebindProgramCameras(
        cameras, prevSegments, state.program.segments);
    }
    state.selected = keep;
  }

  // ---------------------------------------------------------------- popup

  function pinButton(segment, key) {
    if (!isSolverParameter(segment, key)) return null;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pin";
    button.textContent = "◉";
    const held = (segment.pinned || []).includes(key);
    button.classList.toggle("on", held);
    button.title = held
      ? `${key} is pinned — the solver will not move it`
      : `pin ${key} so the solver leaves it alone`;
    button.onclick = () => {
      const pinned = new Set(segment.pinned || []);
      if (held) pinned.delete(key); else pinned.add(key);
      segment.pinned = [...pinned].sort();
      programTouched();
    };
    return button;
  }

  function popupTextFieldFocused() {
    const active = document.activeElement;
    if (!active) return false;
    const popup = document.getElementById("program-popup");
    if (!popup || !popup.contains(active)) return false;
    if (active.tagName === "TEXTAREA") return true;
    if (active.tagName !== "INPUT") return false;
    return active.type === "text" || active.type === "number" || active.type === "";
  }

  function commitNumberBox(box, segment, spec) {
    let value = parseFloat(box.value);
    if (!Number.isFinite(value)) return;
    if (spec.min != null) value = Math.max(spec.min, value);
    if (spec.max != null) value = Math.min(spec.max, value);
    const current = readField(segment, spec);
    if (current === value) return;
    writeField(segment, spec, value);
    programTouched({ rebuild: false });
  }

  function latLonOwner(segment, key) {
    if (key === "lat" || key === "lon") return segment;
    if (/\.(lat|lon)$/.test(key)) {
      const path = key.replace(/\.(lat|lon)$/, "");
      return get(segment, path);
    }
    return null;
  }

  function numberRow(segment, spec, disabled) {
    const row = document.createElement("div");
    row.className = "field";
    const label = document.createElement("label");
    label.textContent = spec.label + (spec.unit ? ` (${spec.unit})` : "");
    const box = document.createElement("input");
    box.type = "number";
    box.step = spec.step ?? 1;
    if (spec.min != null) box.min = spec.min;
    if (spec.max != null) box.max = spec.max;
    box.disabled = disabled;
    box.dataset.field = spec.key;
    box.id = `prog-field-${spec.key.replace(/\./g, "-")}`;
    const raw = readField(segment, spec);
    box.value = round(raw == null ? 0 : raw, spec.type === "plain" ? 6 : 4);
    // Commit on blur or Enter — not each keystroke. A live solve rebuilds the
    // popup and would otherwise drop the caret after every character.
    box.addEventListener("change", () => commitNumberBox(box, segment, spec));
    box.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      box.blur();
    });
    row.append(label, box);
    if (spec.type !== "plain" && !disabled) {
      const slider = document.createElement("input");
      slider.type = "range";
      slider.min = spec.min ?? 0;
      slider.max = spec.max ?? 100;
      slider.step = spec.step ?? 1;
      slider.value = readField(segment, spec);
      slider.disabled = disabled;
      slider.oninput = () => {
        writeField(segment, spec, Number(slider.value));
        box.value = slider.value;
        programTouched({ rebuild: false });
      };
      row.appendChild(slider);
    }
    // Place lookup on latitude only — one icon fills both lat and lon.
    const isLat = spec.key === "lat" || /\.lat$/.test(spec.key);
    const owner = isLat && !disabled ? latLonOwner(segment, spec.key) : null;
    if (owner && typeof geoPickButton === "function") {
      row.appendChild(geoPickButton(owner, () => {
        programTouched();
      }));
    }
    const pin = pinButton(segment, spec.key);
    if (pin) row.appendChild(pin);
    if (spec.help) row.title = spec.help;
    return row;
  }

  function checkboxRow(segment, spec) {
    const row = document.createElement("div");
    row.className = "field inline";
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = Boolean(get(segment, spec.key));
    box.onchange = () => {
      set(segment, spec.key, box.checked);
      programTouched();
    };
    label.append(box, document.createTextNode(" " + spec.label));
    row.appendChild(label);
    if (spec.help) row.title = spec.help;
    return row;
  }

  function selectRow(segment, spec) {
    const row = document.createElement("div");
    row.className = "field";
    const label = document.createElement("label");
    label.textContent = spec.label;
    const select = document.createElement("select");
    for (const option of spec.options) {
      const node = document.createElement("option");
      node.value = option;
      node.textContent = option;
      select.appendChild(node);
    }
    select.value = get(segment, spec.key);
    select.onchange = () => {
      set(segment, spec.key, select.value);
      programTouched();
    };
    row.append(label, select);
    const pin = pinButton(segment, spec.key);
    if (pin) row.appendChild(pin);
    return row;
  }

  function nullableRows(segment, spec) {
    const rows = [];
    const isAuto = get(segment, spec.key) === null || get(segment, spec.key) === undefined;
    const row = document.createElement("div");
    row.className = "field inline";
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = isAuto;
    box.onchange = () => {
      set(segment, spec.key, box.checked ? null : (spec.fallback ?? 0));
      programTouched();
    };
    label.append(box, document.createTextNode(" " + (spec.autoLabel || "auto")));
    row.appendChild(label);
    rows.push(row);
    if (!isAuto) rows.push(numberRow(segment, { ...spec, type: "number" }, false));
    return rows;
  }

  function toggleObjectRow(segment, spec) {
    const row = document.createElement("div");
    row.className = "field inline";
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = Boolean(get(segment, spec.key));
    box.onchange = () => {
      set(segment, spec.key, box.checked ? { ...spec.defaults } : null);
      programTouched();
    };
    label.append(box, document.createTextNode(" " + spec.label));
    row.appendChild(label);
    if (spec.help) row.title = spec.help;
    return row;
  }

  function appendFields(host, segment, specs) {
    for (const spec of specs) {
      if (spec.hiddenWhen && spec.hiddenWhen(segment)) continue;
      const disabled = spec.disabledWhen ? spec.disabledWhen(segment) : false;
      if (spec.type === "bool") host.appendChild(checkboxRow(segment, spec));
      else if (spec.type === "select") host.appendChild(selectRow(segment, spec));
      else if (spec.type === "nullable") {
        for (const row of nullableRows(segment, spec)) host.appendChild(row);
      } else if (spec.type === "toggleObject") {
        host.appendChild(toggleObjectProp(segment, spec));
      } else {
        host.appendChild(numberRow(segment, spec, disabled));
      }
    }
  }

  function splineMinPoints(segment) {
    return Math.max(2, (segment.degree || 3) + 1);
  }

  function clearSplineKnots(segment) {
    // Drop authored knots so evaluation rebuilds a clamped uniform vector
    // for the new control count.
    segment.knots = null;
  }

  function addSplineControlPoint(segment, at) {
    const points = segment.control_points || (segment.control_points = []);
    if (points.length < 2) return;
    // Insert before the end so the joint with the next segment stays put.
    const slot = at != null ? at : Math.max(1, points.length - 1);
    const prev = points[Math.max(0, slot - 1)];
    const next = points[Math.min(points.length - 1, slot)];
    const point = {
      lat: Number(((prev.lat + next.lat) / 2).toFixed(6)),
      lon: Number(((prev.lon + next.lon) / 2).toFixed(6)),
      alt_ft_msl: Math.round((prev.alt_ft_msl + next.alt_ft_msl) / 2),
      weight: 1,
    };
    points.splice(slot, 0, point);
    clearSplineKnots(segment);
    programTouched();
  }

  function removeSplineControlPoint(segment, slot) {
    const points = segment.control_points || [];
    if (points.length <= splineMinPoints(segment)) return;
    points.splice(slot, 1);
    clearSplineKnots(segment);
    programTouched();
  }

  function controlPointRows(segment) {
    const rows = [];
    const minPts = splineMinPoints(segment);
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = "Control points (degree "
      + `${segment.degree || 3}). Drag on the map, or add / remove below.`;
    rows.push(hint);

    (segment.control_points || []).forEach((point, slot) => {
      const row = document.createElement("div");
      row.className = "field";
      const label = document.createElement("label");
      label.textContent = `P${slot}`;
      row.appendChild(label);
      for (const [key, step] of [["lat", 0.0001], ["lon", 0.0001], ["alt_ft_msl", 10], ["weight", 0.1]]) {
        const input = document.createElement("input");
        input.type = "number";
        input.step = step;
        input.value = point[key];
        input.title = key;
        input.style.width = key === "weight" ? "3.5rem" : "5rem";
        input.addEventListener("change", () => {
          const value = parseFloat(input.value);
          if (!Number.isFinite(value) || point[key] === value) return;
          point[key] = value;
          programTouched({ rebuild: false });
        });
        input.addEventListener("keydown", (event) => {
          if (event.key !== "Enter") return;
          event.preventDefault();
          input.blur();
        });
        row.appendChild(input);
        if (key === "lat" && typeof geoPickButton === "function") {
          row.appendChild(geoPickButton(point, () => programTouched()));
        }
      }
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "\u2715";
      remove.className = "small danger";
      remove.title = `Drop P${slot}`;
      remove.disabled = (segment.control_points || []).length <= minPts;
      remove.onclick = () => removeSplineControlPoint(segment, slot);
      row.appendChild(remove);
      rows.push(row);
    });

    const actions = document.createElement("div");
    actions.className = "row";
    const add = document.createElement("button");
    add.type = "button";
    add.textContent = "+ control point";
    add.className = "small";
    add.title = "Insert a point before the end (keeps the end joint)";
    add.onclick = () => addSplineControlPoint(segment);
    const addEnd = document.createElement("button");
    addEnd.type = "button";
    addEnd.textContent = "+ after end";
    addEnd.className = "small";
    addEnd.title = "Append a new end control point";
    addEnd.onclick = () => {
      const points = segment.control_points || [];
      const last = points[points.length - 1];
      if (!last) return;
      points.push({
        lat: Number((last.lat + 0.005).toFixed(6)),
        lon: Number((last.lon + 0.005).toFixed(6)),
        alt_ft_msl: last.alt_ft_msl,
        weight: 1,
      });
      clearSplineKnots(segment);
      programTouched();
    };
    actions.append(add, addEnd);
    rows.push(actions);
    return rows;
  }

  function constraintRows(segment, index) {
    const rows = [];
    const list = document.createElement("div");
    list.className = "program-constraints";
    (segment.constraints || []).forEach((constraint, slot) => {
      const row = document.createElement("div");
      row.className = "field";
      const label = document.createElement("label");
      label.textContent = constraint.at === 1 ? "Pinned end" : `Through @ ${constraint.at}`;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remove";
      remove.className = "small danger";
      remove.onclick = () => {
        segment.constraints.splice(slot, 1);
        programTouched();
      };
      row.append(label, remove);
      list.appendChild(row);
    });
    rows.push(list);
    const add = document.createElement("button");
    add.type = "button";
    add.textContent = "Pin endpoint";
    add.className = "small";
    add.onclick = () => {
      const summary = selectedSummary();
      const end = summary?.end || {};
      segment.constraints = segment.constraints || [];
      segment.constraints.push({
        kind: "POINT", at: 1,
        lat: end.lat ?? state.program.origin.lat,
        lon: end.lon ?? state.program.origin.lon,
        alt_ft_msl: end.alt_ft ?? state.program.origin.alt_ft_msl,
        lock_horizontal: true, lock_vertical: true,
      });
      programTouched();
    };
    rows.push(add);
    return rows;
  }

  function updateDofOnly() {
    const dof = document.getElementById("program-popup-dof");
    if (!dof) return;
    const fit = selectedSummary()?.solvability;
    if (!fit || fit.state === "UNCONSTRAINED") {
      dof.textContent = "";
      dof.className = "program-popup-dof";
      return;
    }
    dof.textContent = `${fit.detail} · ${fit.method}`;
    dof.className = "program-popup-dof"
      + (fit.state === "CONTRADICTORY" ? " bad"
        : fit.state === "UNDER_DETERMINED" ? " short" : "");
  }

  function anchorPopup(popup) {
    // Only the first open places the popup. After that — including after the
    // operator drags it — selection changes must not jump it around.
    if (popup.dataset.anchored === "0" || popup.dataset.placed === "1") return;
    const summary = selectedSummary();
    const mapEl = document.getElementById("map");
    if (!summary || !mapEl || typeof map === "undefined") {
      popup.style.left = "16px";
      popup.style.top = "16px";
      popup.dataset.placed = "1";
      return;
    }
    const mid = summary.start && summary.end
      ? { lat: (summary.start.lat + summary.end.lat) / 2,
          lon: (summary.start.lon + summary.end.lon) / 2 }
      : summary.start || summary.end;
    if (!mid) return;
    const point = map.latLngToContainerPoint([mid.lat, mid.lon]);
    const wrap = mapEl.getBoundingClientRect();
    popup.style.left = `${Math.min(wrap.width - 320, Math.max(8, point.x + 18))}px`;
    popup.style.top = `${Math.min(wrap.height - 80, Math.max(8, point.y - 20))}px`;
    popup.style.right = "auto";
    popup.dataset.placed = "1";
  }

  function bindCommitNumber(input, apply) {
    input.addEventListener("change", apply);
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      input.blur();
    });
  }

  function renderOriginPopup(body) {
    const origin = state.program.origin;
    for (const [key, label, step] of [
      ["lat", "Latitude °", 0.0001],
      ["lon", "Longitude °", 0.0001],
      ["alt_ft_msl", "Altitude ft", 10],
    ]) {
      const row = document.createElement("div");
      row.className = "field";
      const caption = document.createElement("label");
      caption.textContent = label;
      const input = document.createElement("input");
      input.type = "number";
      input.step = step;
      input.id = `prog-field-origin-${key}`;
      input.dataset.field = `origin.${key}`;
      input.value = origin[key];
      bindCommitNumber(input, () => {
        const value = parseFloat(input.value);
        if (!Number.isFinite(value) || origin[key] === value) return;
        origin[key] = value;
        programTouched({ rebuild: false });
      });
      row.append(caption, input);
      if (key === "lat" && typeof geoPickButton === "function") {
        row.appendChild(geoPickButton(origin, () => programTouched()));
      }
      body.appendChild(row);
    }
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = "Or drag the green start marker on the map. "
      + "Relative segments (Line / Arc) move with the origin; absolute "
      + "Hermite / Spline / MoveTo points stay where they are.";
    body.appendChild(hint);
  }

  function renderProgramPopup(opts = {}) {
    const popup = ensurePopup();
    if (!isProgramMode() || state.track !== "flight") {
      popup.hidden = true;
      return;
    }
    const segment = selectedSegment();
    const editingOrigin = originSelected();
    if (!segment && !editingOrigin) {
      popup.hidden = true;
      return;
    }
    // A solve finishing while the operator is mid-type must not wipe the box.
    if (opts.preservePosition && popupTextFieldFocused()) {
      popup.hidden = false;
      updateDofOnly();
      return;
    }
    popup.hidden = false;
    const heading = document.getElementById("program-popup-heading");
    heading.textContent = editingOrigin
      ? "Start (origin)"
      : `${segment.name || KIND_LABEL[segment.kind] || segment.kind}`
        + ` · ${KIND_LABEL[segment.kind] || segment.kind}`;

    const body = document.getElementById("program-popup-body");
    body.innerHTML = "";

    if (editingOrigin) {
      renderOriginPopup(body);
      updateDofOnly();
      anchorPopup(popup);
      return;
    }

    const nameRow = document.createElement("div");
    nameRow.className = "field";
    const nameLabel = document.createElement("label");
    nameLabel.textContent = "Name";
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.value = segment.name || "";
    nameInput.id = "prog-field-name";
    const commitName = () => {
      if (segment.name === nameInput.value) return;
      segment.name = nameInput.value;
      state.dirty = true;
      if (typeof renderMeta === "function") renderMeta();
      if (typeof renderKeyframeList === "function") renderKeyframeList();
    };
    nameInput.addEventListener("change", commitName);
    nameInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      nameInput.blur();
    });
    nameRow.append(nameLabel, nameInput);
    body.appendChild(nameRow);

    const reorder = document.createElement("div");
    reorder.className = "row";
    const up = document.createElement("button");
    up.type = "button";
    up.textContent = "↑";
    up.title = "Move earlier";
    up.disabled = state.selected <= 0;
    up.onclick = () => reorderSegment(-1);
    const down = document.createElement("button");
    down.type = "button";
    down.textContent = "↓";
    down.title = "Move later";
    down.disabled = state.selected >= state.program.segments.length - 1;
    down.onclick = () => reorderSegment(1);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";
    remove.className = "small danger";
    remove.title = "Delete this segment";
    remove.onclick = () => removeProgramSegment();
    reorder.append(up, down, remove);
    body.appendChild(reorder);

    // End point first — editable + geocode; inverse fills the kind's params.
    for (const row of endPointRows(state.selected, segment)) body.appendChild(row);

    const kindFields = (PRIMITIVES[segment.kind].fields || []).filter((spec) =>
      !["to.lat", "to.lon", "to.alt_ft_msl"].includes(spec.key));
    appendFields(body, segment, kindFields);
    if (segment.kind === "SPLINE") {
      for (const row of controlPointRows(segment)) body.appendChild(row);
    }
    appendFields(body, segment, motionFields(segment, "handles"));
    for (const row of constraintRows(segment, state.selected)) body.appendChild(row);

    updateDofOnly();
    anchorPopup(popup);
  }

  function currentEndPoint(index, segment) {
    if ((segment.kind === "MOVE_TO" || segment.kind === "HERMITE") && segment.to) {
      return {
        lat: segment.to.lat,
        lon: segment.to.lon,
        alt_ft_msl: segment.to.alt_ft_msl,
      };
    }
    if (segment.kind === "SPLINE" && segment.control_points?.length) {
      const last = segment.control_points[segment.control_points.length - 1];
      return { lat: last.lat, lon: last.lon, alt_ft_msl: last.alt_ft_msl };
    }
    const summary = summaryAt(index);
    if (summary?.end) {
      return {
        lat: summary.end.lat,
        lon: summary.end.lon,
        alt_ft_msl: pointAlt(summary.end),
      };
    }
    return penContextAt(index);
  }

  function endPointRows(index, segment) {
    const end = currentEndPoint(index, segment);
    const draft = {
      lat: round(Number(end.lat) || 0, 6),
      lon: round(Number(end.lon) || 0, 6),
      alt_ft_msl: Number.isFinite(end.alt_ft_msl) ? end.alt_ft_msl : 0,
    };
    const rows = [];
    const heading = document.createElement("p");
    heading.className = "hint";
    heading.textContent = "End point — edits reshape this segment (and the next).";
    rows.push(heading);

    for (const [key, label, step] of [
      ["lat", "End lat °", 0.0001],
      ["lon", "End lon °", 0.0001],
      ["alt_ft_msl", "End alt ft", 10],
    ]) {
      const row = document.createElement("div");
      row.className = "field";
      const caption = document.createElement("label");
      caption.textContent = label;
      const input = document.createElement("input");
      input.type = "number";
      input.step = step;
      input.id = `prog-field-end-${key}`;
      input.dataset.field = `end.${key}`;
      input.value = draft[key];
      const commit = () => {
        const value = parseFloat(input.value);
        if (!Number.isFinite(value) || draft[key] === value) return;
        draft[key] = value;
        applySegmentEnd(index, draft);
      };
      input.addEventListener("change", commit);
      input.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        input.blur();
      });
      row.append(caption, input);
      if (key === "lat" && typeof geoPickButton === "function") {
        row.appendChild(geoPickButton(draft, () => {
          applySegmentEnd(index, draft);
        }));
      }
      rows.push(row);
    }
    return rows;
  }

  function reorderSegment(delta) {
    const index = state.selected;
    if (typeof index !== "number") return;
    const target = index + delta;
    if (target < 0 || target >= state.program.segments.length) return;
    const [moved] = state.program.segments.splice(index, 1);
    state.program.segments.splice(target, 0, moved);
    state.selected = target;
    programTouched();
  }

  // -------------------------------------------------------- construction
  // Stage 8: add / insert / delete and click-to-place builders.

  const PROG_BUILD = { kind: null, hint: "", insertAt: null };

  function penContextAt(index) {
    // Pen at the end of segment `index`, or at the origin before the first.
    const summaries = state.preview?.segments || [];
    if (index >= 0 && summaries[index]?.end) {
      const end = summaries[index].end;
      return { lat: end.lat, lon: end.lon, alt_ft_msl: end.alt_ft };
    }
    const origin = state.program.origin;
    return { lat: origin.lat, lon: origin.lon, alt_ft_msl: origin.alt_ft_msl };
  }

  // New segments go after the selection (after Start → index 0), not always
  // at the end of the program.
  function insertIndex() {
    if (state.selected === "origin") return 0;
    if (typeof state.selected === "number") return state.selected + 1;
    return state.program.segments.length;
  }

  function bearingDeg(from, to) {
    const toRad = Math.PI / 180;
    const φ1 = from.lat * toRad, φ2 = to.lat * toRad;
    const Δλ = ((to.lon ?? to.lng) - from.lon) * toRad;
    const y = Math.sin(Δλ) * Math.cos(φ2);
    const x = Math.cos(φ1) * Math.sin(φ2)
      - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
    return ((Math.atan2(y, x) * 180 / Math.PI) + 360) % 360;
  }

  function offsetByBearing(from, bearing, distM) {
    const R = 6371000;
    const δ = distM / R;
    const θ = bearing * Math.PI / 180;
    const φ1 = from.lat * Math.PI / 180;
    const λ1 = from.lon * Math.PI / 180;
    const φ2 = Math.asin(Math.sin(φ1) * Math.cos(δ)
      + Math.cos(φ1) * Math.sin(δ) * Math.cos(θ));
    const λ2 = λ1 + Math.atan2(
      Math.sin(θ) * Math.sin(δ) * Math.cos(φ1),
      Math.cos(δ) - Math.sin(φ1) * Math.sin(φ2));
    return { lat: φ2 * 180 / Math.PI, lon: ((λ2 * 180 / Math.PI + 540) % 360) - 180 };
  }

  function projectOntoCircle(center, radiusM, latlng) {
    const toward = { lat: latlng.lat, lon: latlng.lng ?? latlng.lon };
    return offsetByBearing(center, bearingDeg(center, toward), radiusM);
  }

  function addProgramSegment(kind, opts = {}) {
    if (!isProgramMode() || !PRIMITIVES[kind]) return;
    const at = opts.at != null ? opts.at
      : (PROG_BUILD.insertAt != null ? PROG_BUILD.insertAt : insertIndex());
    const pen = penContextAt(at - 1);
    const segment = PRIMITIVES[kind].make(pen);
    if (opts.patch) Object.assign(segment, opts.patch);
    if (opts.to && (kind === "MOVE_TO" || kind === "HERMITE")) {
      segment.to = {
        lat: opts.to.lat, lon: opts.to.lon,
        alt_ft_msl: opts.to.alt_ft_msl ?? pen.alt_ft_msl,
      };
    }
    if (opts.to && kind === "LINE_TO") {
      const dist = Math.max(10, Math.round(metersBetween(pen, opts.to)));
      segment.distance_m = dist;
      segment.heading_deg = round(bearingDeg(pen, opts.to), 2);
      segment.inherit_direction = false;
      segment.climb_deg = 0;
    }
    if (opts.to && kind === "ARC") {
      // One-click arc: radius from pen to click, quarter-turn toward it.
      segment.radius_m = Math.max(20, Math.round(metersBetween(pen, opts.to)));
      segment.sweep_deg = 90;
      segment.side = "LEFT";
    }
    state.program.segments.splice(at, 0, segment);
    state.selected = at;
    cancelProgramBuild();
    programTouched();
    selectProgramSegment(at);
  }

  function removeProgramSegment() {
    if (!isProgramMode()) return false;
    if (typeof state.selected !== "number") return false;
    const list = state.program.segments;
    if (!list.length) return false;
    list.splice(state.selected, 1);
    if (!list.length) state.selected = "origin";
    else state.selected = Math.min(state.selected, list.length - 1);
    cancelProgramBuild();
    programTouched();
    if (state.selected === "origin") selectProgramOrigin();
    else selectProgramSegment(state.selected);
    return true;
  }

  function programBuildActive() {
    return Boolean(PROG_BUILD.kind);
  }

  function cancelProgramBuild() {
    PROG_BUILD.kind = null;
    PROG_BUILD.hint = "";
    PROG_BUILD.insertAt = null;
    document.querySelectorAll("[data-program-add]").forEach(
      (btn) => btn.classList.remove("toggled"));
    if (typeof map !== "undefined" && map) map.getContainer().classList.remove("drawing");
    updateProgramBuildHint();
  }

  function startProgramBuild(kind) {
    if (!isProgramMode() || !PRIMITIVES[kind]) return;
    if (PROG_BUILD.kind === kind) {
      cancelProgramBuild();
      return;
    }
    // Freeze insert slot now so a mid-gesture selection change cannot move
    // the new segment to the end.
    const at = insertIndex();
    // Line / Arc / Hermite / MoveTo place by map click; Spline inserts as-is.
    if (kind === "SPLINE") {
      addProgramSegment("SPLINE", { at });
      return;
    }
    PROG_BUILD.kind = kind;
    PROG_BUILD.insertAt = at;
    const where = at <= 0
      ? "after Start"
      : at >= state.program.segments.length
        ? "at the end"
        : `after #${at}`;
    PROG_BUILD.hint = kind === "ARC"
      ? `Click a point on the circle (sets radius). Inserts ${where}. Esc cancels.`
      : kind === "LINE_TO"
        ? `Click where the line should end. Inserts ${where}. Esc cancels.`
        : kind === "MOVE_TO"
          ? `Click the jump destination. Inserts ${where}. Esc cancels.`
          : `Click the Hermite end point. Inserts ${where}. Esc cancels.`;
    document.querySelectorAll("[data-program-add]").forEach((btn) => {
      btn.classList.toggle("toggled", btn.dataset.programAdd === kind);
    });
    if (typeof map !== "undefined" && map) map.getContainer().classList.add("drawing");
    updateProgramBuildHint();
  }

  function updateProgramBuildHint() {
    const hint = document.getElementById("add-hint");
    if (!hint || !isProgramMode()) return;
    if (PROG_BUILD.hint) {
      hint.textContent = PROG_BUILD.hint;
      return;
    }
    hint.textContent = "Add inserts after the selected segment (after Start "
      + "when Start is selected). Line / Arc / Hermite / MoveTo click the map; "
      + "Spline inserts immediately. Remove deletes the selected segment.";
  }

  function onProgramMapClick(latlng) {
    if (!programBuildActive()) return false;
    const kind = PROG_BUILD.kind;
    const to = { lat: latlng.lat, lon: latlng.lng };
    addProgramSegment(kind, { to, at: PROG_BUILD.insertAt });
    return true;
  }

  function showProgramAddBar(show) {
    const bar = document.getElementById("program-add-bar");
    if (bar) bar.hidden = !show;
    const mapBar = document.getElementById("program-add-map-bar");
    if (mapBar) mapBar.hidden = !show;
  }

  // ---------------------------------------------------------------- gizmos

  function metersBetween(a, b) {
    const toRad = Math.PI / 180;
    const lat1 = a.lat * toRad, lat2 = b.lat * toRad;
    const dLat = (b.lat - a.lat) * toRad;
    const dLon = (b.lon - a.lon) * toRad;
    const h = Math.sin(dLat / 2) ** 2
      + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
    return 2 * 6371000 * Math.asin(Math.min(1, Math.sqrt(h)));
  }

  function summaryAt(index) {
    return (state.preview?.segments || [])[index] || null;
  }

  // Sweep around a centre for the authored side. Bearings increase clockwise;
  // LEFT (centre on the left of travel) orbits counter-clockwise.
  function arcSweepDegrees(center, start, end, side) {
    const b0 = bearingDeg(center, start);
    const b1 = bearingDeg(center, end);
    const cw = (b1 - b0 + 360) % 360;
    const ccw = (b0 - b1 + 360) % 360;
    const sweep = side === "RIGHT" ? cw : ccw;
    return sweep < 1 ? 1 : sweep;
  }

  function pointAlt(point, fallback) {
    if (point && Number.isFinite(point.alt_ft)) return point.alt_ft;
    if (point && Number.isFinite(point.alt_ft_msl)) return point.alt_ft_msl;
    return fallback ?? state.program.origin.alt_ft_msl;
  }

  // Author segment `index` so its end lands at `latlng` (start kept).
  // Inverse: Line → heading+distance; Arc → radius/sweep; absolute kinds → to.
  function setSegmentEnd(index, latlng, opts = {}) {
    const segment = state.program.segments[index];
    const summary = summaryAt(index);
    if (!segment) return null;
    const start = summary?.start || penContextAt(index - 1);
    const to = {
      lat: round(latlng.lat, 6),
      lon: round(latlng.lng ?? latlng.lon, 6),
      alt_ft_msl: Number.isFinite(latlng.alt_ft_msl)
        ? latlng.alt_ft_msl
        : pointAlt(summary?.end, start.alt_ft_msl ?? start.alt_ft),
    };
    if (segment.kind === "MOVE_TO" || segment.kind === "HERMITE") {
      segment.to = { ...segment.to, lat: to.lat, lon: to.lon, alt_ft_msl: to.alt_ft_msl };
      return to;
    }
    if (segment.kind === "LINE_TO") {
      const horiz = Math.max(1, metersBetween(start, to));
      segment.distance_m = Math.max(10, Math.round(horiz));
      segment.heading_deg = round(bearingDeg(start, to), 2);
      segment.inherit_direction = false;
      const startAlt = pointAlt(start);
      if (Number.isFinite(to.alt_ft_msl) && Number.isFinite(startAlt)) {
        const riseM = (to.alt_ft_msl - startAlt) * 0.3048;
        segment.climb_deg = round(
          Math.max(-89, Math.min(89, Math.atan2(riseM, horiz) * 180 / Math.PI)), 2);
      }
      return to;
    }
    if (segment.kind === "ARC" && summary?.start) {
      const startPt = summary.start;
      // Prefer sweep about the solved centre when the pick is still on the
      // circle (map-gizmo drag). Free edits / geocode use a chord inverse so
      // the authored end can leave the old radius.
      const center = summary.arc?.center;
      const chord = metersBetween(startPt, to);
      if (center && opts.onCircle) {
        const onCircle = projectOntoCircle(center, segment.radius_m, to);
        segment.sweep_deg = round(
          arcSweepDegrees(center, startPt, onCircle, segment.side), 1);
        return onCircle;
      }
      if (chord > 2 * segment.radius_m) {
        segment.radius_m = Math.max(20, Math.ceil(chord / 2) + 1);
      }
      const ratio = Math.min(1, chord / (2 * segment.radius_m));
      let sweep = 2 * Math.asin(ratio) * 180 / Math.PI;
      // Keep the major-arc branch if that is what was authored.
      if (segment.sweep_deg > 180 && sweep < 180) sweep = 360 - sweep;
      segment.sweep_deg = Math.max(1, round(sweep, 1));
      return to;
    }
    if (segment.kind === "SPLINE" && segment.control_points?.length) {
      const last = segment.control_points[segment.control_points.length - 1];
      last.lat = to.lat;
      last.lon = to.lon;
      last.alt_ft_msl = to.alt_ft_msl;
      return to;
    }
    return to;
  }

  function applySegmentEnd(index, point, opts = {}) {
    const at = setSegmentEnd(index, point, opts) || point;
    if (state.program.segments[index + 1]) {
      adaptSegmentAfterStartMove(index + 1, at);
    }
    programTouched({ rebuild: opts.rebuild !== false });
    return at;
  }

  // After the joint that starts this segment moved, reshape so the old end
  // stays put when the kind allows it.
  function adaptSegmentAfterStartMove(index, joint) {
    const segment = state.program.segments[index];
    const summary = summaryAt(index);
    if (!segment || !summary?.end) return;
    const end = summary.end;
    const start = {
      lat: joint.lat, lon: joint.lng ?? joint.lon,
      alt_ft_msl: pointAlt(summary.start),
    };
    if (segment.kind === "LINE_TO") {
      segment.distance_m = Math.max(10, Math.round(metersBetween(start, end)));
      segment.heading_deg = round(bearingDeg(start, end), 2);
      segment.inherit_direction = false;
      return;
    }
    if (segment.kind === "ARC") {
      const chord = metersBetween(start, end);
      if (chord > 2 * segment.radius_m) {
        segment.radius_m = Math.max(20, Math.ceil(chord / 2) + 1);
      }
      const ratio = Math.min(1, chord / (2 * segment.radius_m));
      segment.sweep_deg = Math.max(1,
        round(2 * Math.asin(ratio) * 180 / Math.PI, 1));
      return;
    }
    if (segment.kind === "SPLINE" && segment.control_points?.length) {
      segment.control_points[0].lat = round(start.lat, 6);
      segment.control_points[0].lon = round(start.lon, 6);
      return;
    }
    // MOVE_TO / HERMITE keep an absolute end; the new start is just the pen.
  }

  function moveJoint(index, latlng) {
    // Joint `index` is the end of segment index-1 (or the origin when 0) and
    // the start of segment `index`. Both neighbours reshape around it.
    const point = {
      lat: round(latlng.lat, 6),
      lon: round(latlng.lng ?? latlng.lon, 6),
    };
    if (index <= 0) {
      const origin = state.program.origin;
      origin.lat = point.lat;
      origin.lon = point.lon;
      if (state.program.segments[0]) adaptSegmentAfterStartMove(0, point);
      return;
    }
    setSegmentEnd(index - 1, point);
    if (state.program.segments[index]) adaptSegmentAfterStartMove(index, point);
  }

  function setArcCenter(segment, summary, latlng) {
    if (!summary?.start) return null;
    const start = summary.start;
    const want = { lat: latlng.lat, lon: latlng.lng ?? latlng.lon };
    segment.radius_m = Math.max(20, Math.round(metersBetween(start, want)));
    // Which side of the entry heading the centre sits on.
    const entry = summary.entry?.heading ?? 0;
    const toward = bearingDeg(start, want);
    let delta = toward - entry;
    while (delta > 180) delta -= 360;
    while (delta < -180) delta += 360;
    segment.side = delta <= 0 ? "LEFT" : "RIGHT";
    // Snap to the geometric centre (entry ± 90° at radius) — the model only
    // allows centres on that lateral axis.
    const lateral = segment.side === "LEFT"
      ? (entry + 270) % 360
      : (entry + 90) % 360;
    return offsetByBearing(start, lateral, segment.radius_m);
  }

  function clearProgramGizmos() {
    if (!PROG.layer) return;
    for (const layer of PROG.layer.getLayers()) {
      const dragger = layer.dragging && layer.dragging._draggable;
      if (dragger && L.Draggable._dragging === dragger) L.Draggable._dragging = false;
    }
    PROG.layer.clearLayers();
  }

  function addDragMarker(latlng, opts, onMove, onEnd) {
    // Circle markers are not Leaflet-draggable; follow the pointer by hand
    // (same pattern as the harness constraint grips).
    const marker = L.circleMarker(latlng, {
      radius: opts.radius || 7, color: "#fff", weight: 2,
      fillColor: opts.fillColor || "#4ea1ff", fillOpacity: 0.85,
    }).addTo(PROG.layer);
    if (opts.title) marker.bindTooltip(opts.title, { direction: "top", opacity: 0.9 });
    marker.on("mousedown", (down) => {
      map.dragging.disable();
      PROG.dragging = true;
      const move = (event) => {
        const next = onMove(event.latlng) || event.latlng;
        marker.setLatLng(next);
      };
      const up = () => {
        map.dragging.enable();
        map.off("mousemove", move).off("mouseup", up);
        PROG.dragging = false;
        if (onEnd) onEnd();
        else programTouched({ rebuild: true });
      };
      map.on("mousemove", move).on("mouseup", up);
      L.DomEvent.stop(down);
    });
    return marker;
  }

  function renderProgramGizmos() {
    if (!PROG.layer) return;
    if (PROG.dragging) return;
    clearProgramGizmos();
    if (!isProgramMode() || state.track !== "flight") return;

    if (originSelected() && state.program?.origin) {
      const origin = state.program.origin;
      addDragMarker([origin.lat, origin.lon], {
        fillColor: "#5ad6a0", title: "Start (origin)",
      }, (ll) => {
        moveJoint(0, ll);
        programTouched({ rebuild: false });
        return [origin.lat, origin.lon];
      });
      return;
    }

    const segment = selectedSegment();
    const summary = selectedSummary();
    const index = state.selected;
    if (!segment || !summary || typeof index !== "number") return;

    // Shared endpoints — dragging updates this segment and its neighbour.
    // MoveTo is a jump: summary.start/end are both the destination, so the
    // incoming joint is the previous segment's end (or the origin).
    if (segment.kind === "MOVE_TO") {
      const from = index > 0
        ? summaryAt(index - 1)?.end
        : state.program.origin;
      if (from) {
        addDragMarker([from.lat, from.lon], {
          fillColor: "#5ad6a0", title: "From", radius: 8,
        }, (ll) => {
          moveJoint(index, ll);
          programTouched({ rebuild: false });
          return ll;
        });
      }
      if (segment.to) {
        addDragMarker([segment.to.lat, segment.to.lon], {
          fillColor: "#f0a848", title: "Jump to", radius: 8,
        }, (ll) => {
          const at = applySegmentEnd(index, ll, { rebuild: false });
          return at ? [at.lat, at.lon] : ll;
        });
      }
    } else {
      if (summary.start) {
        addDragMarker([summary.start.lat, summary.start.lon], {
          fillColor: "#5ad6a0", title: "Start", radius: 8,
        }, (ll) => {
          moveJoint(index, ll);
          programTouched({ rebuild: false });
          return ll;
        });
      }
      if (summary.end) {
        addDragMarker([summary.end.lat, summary.end.lon], {
          fillColor: "#f0a848", title: "End", radius: 8,
        }, (ll) => {
          const at = applySegmentEnd(index, ll, {
            onCircle: segment.kind === "ARC",
            rebuild: false,
          }) || { lat: round(ll.lat, 6), lon: round(ll.lng, 6) };
          return [at.lat, at.lon];
        });
      }
    }

    if (segment.kind === "ARC" && summary.arc) {
      const center = summary.arc.center;
      L.circle([center.lat, center.lon], {
        radius: segment.radius_m || summary.arc.radius_m,
        color: "#ffa23e", weight: 1, opacity: 0.45,
        dashArray: "3 6", fill: false, interactive: false,
      }).addTo(PROG.layer);
      // Drag the centre: radius (and side) follow; snaps to the lateral axis.
      addDragMarker([center.lat, center.lon], {
        fillColor: "#ffa23e", title: "Centre (radius)", radius: 8,
      }, (ll) => {
        const snapped = setArcCenter(segment, summary, ll);
        programTouched({ rebuild: false });
        return snapped ? [snapped.lat, snapped.lon] : ll;
      });
    }

    if (segment.kind === "HERMITE" && summary.hermite) {
      const h = summary.hermite;
      L.polyline([[summary.start.lat, summary.start.lon], [h.out_tip.lat, h.out_tip.lon]], {
        color: "#7ee29a", weight: 2, dashArray: "4 4", interactive: false,
      }).addTo(PROG.layer);
      L.polyline([[summary.end.lat, summary.end.lon], [h.into_tip.lat, h.into_tip.lon]], {
        color: "#ffa23e", weight: 2, dashArray: "4 4", interactive: false,
      }).addTo(PROG.layer);
      addDragMarker([h.out_tip.lat, h.out_tip.lon], { fillColor: "#7ee29a", title: "Out" }, (ll) => {
        if (!segment.out) {
          segment.out = { heading_deg: 0, climb_deg: 0, length_m: 500 };
        }
        segment.out.length_m = Math.max(10,
          Math.round(metersBetween(summary.start, { lat: ll.lat, lon: ll.lng }) * 3));
        segment.out.heading_deg = round(bearingDeg(summary.start, {
          lat: ll.lat, lon: ll.lng,
        }), 1);
        programTouched({ rebuild: false });
      });
      if (segment.into && summary.end) {
        addDragMarker([h.into_tip.lat, h.into_tip.lon], {
          fillColor: "#ffa23e", title: "Into",
        }, (ll) => {
          segment.into.length_m = Math.max(10,
            Math.round(metersBetween(summary.end, { lat: ll.lat, lon: ll.lng }) * 3));
          segment.into.heading_deg = round(bearingDeg({
            lat: ll.lat, lon: ll.lng,
          }, summary.end), 1);
          programTouched({ rebuild: false });
        });
      }
    }

    if (segment.kind === "SPLINE" && segment.control_points?.length) {
      const hull = segment.control_points.map((p) => [p.lat, p.lon]);
      if (hull.length >= 2) {
        L.polyline(hull, {
          color: "#c084fc", weight: 1, opacity: 0.55,
          dashArray: "4 6", interactive: false,
        }).addTo(PROG.layer);
      }
      segment.control_points.forEach((point, slot) => {
        const isEnd = slot === 0 || slot === segment.control_points.length - 1;
        // Ends already have the green/orange joint grips; mid points are the
        // purple hull handles. Still draw ends lightly so the polygon reads.
        if (isEnd) {
          L.circleMarker([point.lat, point.lon], {
            radius: 4, color: "#c084fc", weight: 1,
            fillColor: "#c084fc", fillOpacity: 0.35, interactive: false,
          }).addTo(PROG.layer);
          return;
        }
        addDragMarker([point.lat, point.lon], {
          fillColor: "#c084fc", title: `P${slot} — drag to move`,
        }, (ll) => {
          point.lat = round(ll.lat, 6);
          point.lon = round(ll.lng, 6);
          programTouched({ rebuild: false });
        });
      });
    }

    (segment.constraints || []).forEach((constraint) => {
      if (!constraint.lock_horizontal) return;
      const missed = summary.solvability?.state === "CONTRADICTORY";
      const marker = L.circleMarker([constraint.lat, constraint.lon], {
        radius: 7, weight: 2, color: missed ? "#f05e6a" : "#fff",
        dashArray: missed ? "3 3" : null,
        fillColor: "#4ea1ff", fillOpacity: 0.35,
      }).addTo(PROG.layer);
      marker.bindTooltip(constraint.at === 1 ? "pinned end" : `through @ ${constraint.at}`);
      marker.on("mousedown", (down) => {
        map.dragging.disable();
        PROG.dragging = true;
        const move = (event) => {
          constraint.lat = round(event.latlng.lat, 6);
          constraint.lon = round(event.latlng.lng, 6);
          marker.setLatLng(event.latlng);
          programTouched({ rebuild: false });
        };
        const up = () => {
          map.dragging.enable();
          map.off("mousemove", move).off("mouseup", up);
          PROG.dragging = false;
          programTouched();
        };
        map.on("mousemove", move).on("mouseup", up);
        L.DomEvent.stop(down);
      });
    });
  }

  function onProgramAfterSolve() {
    if (!isProgramMode()) {
      clearProgramGizmos();
      const popup = document.getElementById("program-popup");
      if (popup) popup.hidden = true;
      return;
    }
    adoptSolvedProgram(state.preview);
    renderProgramPopup({ preservePosition: true });
    renderProgramGizmos();
  }

  function selectProgramSegment(index) {
    state.track = "flight";
    state.selected = index;
    document.querySelectorAll(".tab").forEach(
      (tab) => tab.classList.toggle("active", tab.dataset.track === "flight"));
    if (typeof renderKeyframeList === "function") renderKeyframeList();
    if (typeof renderInspector === "function") renderInspector();
    // Redraw the track so the selected segment gets the highlight colour.
    if (typeof renderSolvedTracks === "function") renderSolvedTracks();
    // Keep the popup where it was — do not re-anchor on selection.
    renderProgramPopup({ preservePosition: true });
    renderProgramGizmos();
  }

  function selectProgramOrigin() {
    state.track = "flight";
    state.selected = "origin";
    document.querySelectorAll(".tab").forEach(
      (tab) => tab.classList.toggle("active", tab.dataset.track === "flight"));
    if (typeof renderKeyframeList === "function") renderKeyframeList();
    if (typeof renderInspector === "function") renderInspector();
    if (typeof renderSolvedTracks === "function") renderSolvedTracks();
    renderProgramPopup({ preservePosition: true });
    renderProgramGizmos();
  }

  function wireProgramEdit() {
    if (typeof map !== "undefined" && map && !PROG.layer) {
      PROG.layer = L.layerGroup().addTo(map);
      map.on("click", (event) => {
        if (!isProgramMode()) return;
        if (onProgramMapClick(event.latlng)) L.DomEvent.stop(event);
      });
    }
    ensurePopup();
    for (const name of ["mouseup", "pointerup", "pointercancel"]) {
      window.addEventListener(name, () => {
        setTimeout(() => { PROG.dragging = false; }, 0);
      }, true);
    }
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && programBuildActive()) {
        cancelProgramBuild();
        event.preventDefault();
      }
    });
    document.querySelectorAll("[data-program-add]").forEach((btn) => {
      btn.onclick = () => startProgramBuild(btn.dataset.programAdd);
    });
  }

  window.PROG = PROG;
  window.programTouched = programTouched;
  window.renderProgramPopup = renderProgramPopup;
  window.renderProgramGizmos = renderProgramGizmos;
  window.onProgramAfterSolve = onProgramAfterSolve;
  window.selectProgramSegment = selectProgramSegment;
  window.selectProgramOrigin = selectProgramOrigin;
  window.adoptSolvedProgram = adoptSolvedProgram;
  window.addProgramSegment = addProgramSegment;
  window.removeProgramSegment = removeProgramSegment;
  window.startProgramBuild = startProgramBuild;
  window.cancelProgramBuild = cancelProgramBuild;
  window.programBuildActive = programBuildActive;
  window.showProgramAddBar = showProgramAddBar;
  window.updateProgramBuildHint = updateProgramBuildHint;
  window.wireProgramEdit = wireProgramEdit;
  wireProgramEdit();
})();
