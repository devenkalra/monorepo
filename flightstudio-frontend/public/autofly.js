"use strict";

// Unattended flying of a whole path. The run is a background process on the
// server (flightstudio.tools.autofly): it flies the path in segments, tunes
// the pilot where a take misses the limits, joins the best-fitting takes and
// re-flies whatever the check fails. This panel starts, pauses, stops and
// restarts it, and shows its progress.

const AUTO = {
  host: null,
  pathId: null,
  status: null,
  timer: null,
  wasRunning: false,
  options: { flights: 16, rounds: 3, rms_cross_track_m: 30, rms_alt_ft: 75, max_alt_ft: 200 },
};

const AUTO_OPTION_LABELS = [
  ["flights", "Flights per segment", 1],
  ["rounds", "Check rounds", 1],
  ["rms_cross_track_m", "Average off track (m)", 5],
  ["rms_alt_ft", "Average altitude error (ft)", 5],
  ["max_alt_ft", "Worst altitude error (ft)", 10],
];

const SEGMENT_STATUS = {
  pending: "to fly", accepted: "within limits", "best-effort": "best effort",
  failed: "no take", split: "split",
};

function renderAutoflyGroup(host) {
  if (typeof map2dMode === "function" && map2dMode()) return;
  if ((state.doc?.flight_keyframes?.length || 0) < 2) return;
  const group = document.createElement("div");
  group.className = "group";
  const title = document.createElement("h3");
  title.textContent = "Fly the whole path automatically";
  const intro = document.createElement("p");
  intro.className = "hint";
  intro.textContent = "Flies the path in overlapping segments, tunes the pilot on any segment "
    + "that misses the limits, joins the best-fitting takes and flies again whatever the "
    + "check fails. Takes hours: set calm wind, engines running, and leave the sim alone. "
    + "The result is saved as a new path; this one is not changed.";
  group.append(title, intro);
  for (const [key, label, step] of AUTO_OPTION_LABELS) {
    group.appendChild(field(label, numberInput(AUTO.options[key], (v) => {
      if (Number.isFinite(v) && v > 0) AUTO.options[key] = v;
    }, step)));
  }
  const body = document.createElement("div");
  group.appendChild(body);
  host.appendChild(group);
  AUTO.host = body;
  AUTO.pathId = state.doc.meta.path_id;
  if (AUTO.status && AUTO.status.out === `${AUTO.pathId}-auto`) drawAutofly();
  else body.innerHTML = "<p class='hint'>Checking…</p>";
  pollAutofly();
}

async function pollAutofly() {
  clearTimeout(AUTO.timer);
  if (!AUTO.pathId || !AUTO.host?.isConnected) return;
  const pathId = AUTO.pathId;
  try {
    const status = await api("GET", `/api/autofly/${encodeURIComponent(pathId)}`);
    if (pathId !== AUTO.pathId) return;
    AUTO.status = status;
    if (AUTO.wasRunning && !status.running) refreshPathList(state.doc?.meta?.path_id);
    AUTO.wasRunning = status.running;
    drawAutofly();
  } catch (error) {
    AUTO.host.innerHTML = "";
    AUTO.host.appendChild(hintLine(`Could not read the run: ${error.message}`));
  }
  AUTO.timer = setTimeout(pollAutofly, AUTO.status?.running ? 3000 : 15000);
}

function hintLine(text, className = "hint") {
  const p = document.createElement("p");
  p.className = className;
  p.textContent = text;
  return p;
}

async function autoflyAction(action) {
  const pathId = AUTO.pathId;
  try {
    if (action === "start" || action === "restart") {
      if (state.dirty && !confirm("This path has unsaved changes; the run flies the saved "
                                  + "version. Start anyway?")) return;
      AUTO.status = await api("POST", "/api/autofly/start", {
        path_id: pathId, restart: action === "restart", options: AUTO.options,
      });
    } else {
      AUTO.status = await api("POST", `/api/autofly/${encodeURIComponent(pathId)}/${action}`);
    }
    AUTO.wasRunning = AUTO.status.running;
    drawAutofly();
  } catch (error) {
    alert(`Could not ${action} the run: ${error.message}`);
  }
  pollAutofly();
}

function describeRun(status) {
  const run = status.state;
  if (status.running) {
    if (status.pausing) return "Pausing after the flight in progress…";
    return run?.message || "Starting…";
  }
  if (!run) {
    return status.exit_code ? "The run stopped before it began; see the log below."
      : "Not run yet.";
  }
  if (run.phase === "done") return run.message;
  if (run.phase === "paused") return run.message || "Paused.";
  return status.exit_code ? "The run stopped with an error; see the log below. Resume to carry on."
    : "Not running. Resume to carry on.";
}

function drawAutofly() {
  const body = AUTO.host;
  const status = AUTO.status;
  if (!body || !status) return;
  body.innerHTML = "";
  const run = status.state;
  body.appendChild(hintLine(describeRun(status), status.running ? "hint autofly-live" : "hint"));

  const row = document.createElement("div");
  row.className = "row";
  if (status.running) {
    const pause = button("Pause", () => autoflyAction("pause"));
    pause.disabled = status.pausing;
    pause.title = "Stop cleanly once the flight in progress has finished";
    const stop = button("Stop now", () => {
      if (confirm("Stop now? The flight in progress is lost; everything before it is kept.")) {
        autoflyAction("stop");
      }
    });
    row.append(pause, stop);
  } else {
    const label = !run ? "Start" : run.phase === "done" ? "Continue" : "Resume";
    const start = button(label, () => autoflyAction("start"), "primary");
    start.title = run?.phase === "done"
      ? "Run the check again; with more rounds or looser limits it carries on"
      : "Carry on from where it stopped";
    row.appendChild(start);
    if (run) {
      row.appendChild(button("Restart", () => {
        if (confirm("Throw away this run's takes and progress and start again from scratch?")) {
          autoflyAction("restart");
        }
      }));
    }
  }
  if (run?.result) {
    row.appendChild(button("Open result", async () => {
      if (state.dirty && !confirm("Discard unsaved changes to this path?")) return;
      await refreshPathList(status.out);
      await loadPath(status.out);
    }));
  }
  body.appendChild(row);

  if (run) {
    body.appendChild(hintLine(`Round ${run.round} of ${run.rounds}`
      + (run.updated ? ` · updated ${run.updated.slice(11)}` : "")));
    const table = document.createElement("table");
    table.className = "autofly-table";
    table.innerHTML = "<tr><th>Segment (s)</th><th>Status</th><th>Flights</th>"
      + "<th>Best: track / alt</th></tr>";
    for (const segment of run.segments.filter((s) => s.status !== "split")) {
      const best = segment.takes?.[0]?.score;
      const tr = document.createElement("tr");
      const current = status.running && run.current
        && run.current.segment[0] === segment.from && run.current.segment[1] === segment.to;
      tr.className = `autofly-${segment.status}${current ? " autofly-current" : ""}`;
      for (const text of [
        `${segment.from}–${segment.to}`,
        SEGMENT_STATUS[segment.status] || segment.status,
        `${segment.flights}/${segment.budget}`,
        best ? `${best.rms_cross_track_m.toFixed(0)} m / ${best.rms_alt_ft.toFixed(0)} ft` : "–",
      ]) {
        const td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      }
      table.appendChild(tr);
    }
    body.appendChild(table);
    for (const seam of run.seams || []) {
      body.appendChild(hintLine(
        `Seam ${seam.between[0]} / ${seam.between[1]}: `
        + (seam.failed ? seam.failed
          : `${Math.round(seam.alt_ft)} ft, ${Math.round(seam.track_m)} m, `
            + `${seam.attitude_deg.toFixed(1)}° apart`),
        seam.misses?.length ? "hint blocked" : "hint"));
    }
    if (run.result) {
      const r = run.result;
      body.appendChild(hintLine(`Joined ${status.out} (${r.from}–${r.to} s): `
        + `${r.rms_cross_track_m.toFixed(0)} m off track on average (worst `
        + `${r.max_cross_track_m.toFixed(0)}), altitude ${r.rms_alt_ft.toFixed(0)} ft on `
        + `average (worst ${r.max_alt_ft.toFixed(0)}), timing ${r.rms_timing_s.toFixed(1)} s.`));
    }
    for (const issue of run.issues || []) body.appendChild(hintLine(`Still wrong: ${issue}`));
  }

  if (status.log?.length) {
    const details = document.createElement("details");
    details.open = AUTO.logOpen ?? false;
    details.ontoggle = () => { AUTO.logOpen = details.open; };
    const summary = document.createElement("summary");
    summary.textContent = "Log";
    const pre = document.createElement("pre");
    pre.className = "autofly-log";
    pre.textContent = status.log.join("\n");
    details.append(summary, pre);
    body.appendChild(details);
    pre.scrollTop = pre.scrollHeight;
  }
}
