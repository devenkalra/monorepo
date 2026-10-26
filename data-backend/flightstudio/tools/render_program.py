"""Draw a PathProgram on a map, as a standalone HTML file.

A development aid for the stages before the preview endpoint and the frontend
exist. Stage 1 has geometry but no clock, so this plots shape and altitude
only; there is nothing to play yet.

    python -m flightstudio.tools.render_program --sample figure_eight
    python -m flightstudio.tools.render_program --program my_path.json

Run it from /app inside the backend container. The repo is bind-mounted
there, so the file it writes shows up on the host.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flightstudio.core.program import (
    ArcSegment,
    Direction,
    GeoPoint,
    LineToSegment,
    MoveToSegment,
    PathProgram,
)
from flightstudio.core.program_geom import ProgramError
from flightstudio.program_preview import program_preview

BERKELEY = GeoPoint(lat=37.8716, lon=-122.2727, alt_ft_msl=2000.0)


def sample_circuit() -> PathProgram:
    """A racetrack. Two straights joined by half circles; it should close."""
    return PathProgram(origin=BERKELEY, segments=[
        LineToSegment(name="North straight", heading_deg=0.0, distance_m=3000.0),
        ArcSegment(name="North turn", side="RIGHT", radius_m=800.0, sweep_deg=180.0),
        LineToSegment(name="South straight", distance_m=3000.0, inherit_direction=True),
        ArcSegment(name="South turn", side="RIGHT", radius_m=800.0, sweep_deg=180.0),
    ])


def sample_figure_eight() -> PathProgram:
    """The handedness check: one full turn each way from the same tangent.

    The left loop must sit west of the entry and the right loop east of it.
    If `side` were wrong, or the cross products were mirrored, this draws as
    two loops on the same side instead of a figure eight.
    """
    return PathProgram(origin=BERKELEY, segments=[
        LineToSegment(name="Entry", heading_deg=0.0, distance_m=1200.0),
        ArcSegment(name="Left loop", side="LEFT", radius_m=700.0, sweep_deg=360.0),
        ArcSegment(name="Right loop", side="RIGHT", radius_m=700.0, sweep_deg=360.0),
        LineToSegment(name="Exit", distance_m=1200.0, inherit_direction=True),
    ])


def sample_helix() -> PathProgram:
    """Three turns of a climbing helix, the shape the waypoint model could not hold.

    The arc states no rise, so it inherits the entry's 8 degree climb and
    keeps it the whole way up.
    """
    return PathProgram(origin=BERKELEY, segments=[
        LineToSegment(name="Climbing entry", heading_deg=45.0, climb_deg=8.0,
                      distance_m=2500.0),
        ArcSegment(name="Three turns up", side="LEFT", radius_m=900.0, sweep_deg=1080.0),
        LineToSegment(name="Exit", distance_m=2500.0, inherit_direction=True),
    ])


def sample_tilted() -> PathProgram:
    """A banked full circle: flat on the map, but a sine wave in altitude."""
    return PathProgram(origin=BERKELEY, segments=[
        LineToSegment(name="Entry", heading_deg=0.0, distance_m=1500.0),
        ArcSegment(name="Banked circle", side="LEFT", radius_m=1200.0,
                   sweep_deg=360.0, tilt_deg=25.0),
    ])


def sample_seam() -> PathProgram:
    """A tour with the boring middle cut out.

    The two legs must draw as separate lines. A line joining them means the
    break flag is not reaching the renderer.
    """
    return PathProgram(origin=BERKELEY, segments=[
        LineToSegment(name="Before the cut", heading_deg=0.0, distance_m=2500.0),
        MoveToSegment(name="Cut to the far side",
                      to=GeoPoint(lat=37.8200, lon=-122.3400, alt_ft_msl=4500.0),
                      tangent=Direction(heading_deg=90.0, climb_deg=0.0)),
        LineToSegment(name="After the cut", distance_m=2500.0, inherit_direction=True),
    ])


SAMPLES = {
    "circuit": sample_circuit,
    "figure_eight": sample_figure_eight,
    "helix": sample_helix,
    "tilted": sample_tilted,
    "seam": sample_seam,
}


def build_payload(name: str, program: PathProgram, step_m: float) -> dict:
    payload = program_preview(program, step_m=step_m)
    payload["name"] = name
    for source, summary in zip(program.segments, payload["segments"]):
        summary["name"] = source.name or summary["kind"]
        summary["params"] = source.model_dump(
            exclude={"id", "name", "velocity", "end", "on_ground"}
        )
    return payload


HTML = """<!doctype html>
<meta charset="utf-8">
<title>flight program — __NAME__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  body { margin: 0; font: 13px/1.5 system-ui, sans-serif; background: #11151c; color: #dde3ec; }
  #map { height: 62vh; }
  .panel { padding: 10px 14px; }
  h1 { font-size: 15px; margin: 0 0 8px; font-weight: 600; }
  h1 span { color: #8b96a8; font-weight: 400; }
  table { border-collapse: collapse; width: 100%; font-size: 12px; }
  th, td { text-align: left; padding: 3px 10px 3px 0; border-bottom: 1px solid #222a35; }
  th { color: #8b96a8; font-weight: 500; }
  .swatch { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; }
  .seam { color: #f0a848; }
  #profile { width: 100%; height: 130px; display: block; }
  code { color: #9fd0a8; }
</style>
<div id="map"></div>
<div class="panel">
  <h1>__NAME__ <span id="summary"></span></h1>
  <svg id="profile"></svg>
  <table id="legend"></table>
</div>
<script>
const DATA = __DATA__;
const COLORS = ["#4ea3f0","#f05e6a","#5ad6a0","#c08ef0","#f0b84e","#5ad6d6"];
const color = id => COLORS[DATA.segments.findIndex(s => s.id === id) % COLORS.length];

const map = L.map("map", { rotate: false, rotateControl: false });
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);

// Split the samples into strokes wherever a row says the pen jumped. This is
// exactly the contract the real renderer has to honour.
const strokes = [];
let current = null;
for (const row of DATA.samples) {
  if (!current || row.break_before || row.segment_id !== current.id) {
    current = { id: row.segment_id, cut: !!row.break_before, points: [] };
    strokes.push(current);
    // Carry one point over so consecutive segments join, unless this is a cut.
    if (!row.break_before && strokes.length > 1) {
      const previous = strokes[strokes.length - 2].points;
      if (previous.length) current.points.push(previous[previous.length - 1]);
    }
  }
  current.points.push([row.lat, row.lon]);
}
for (const stroke of strokes) {
  L.polyline(stroke.points, { color: color(stroke.id), weight: 3 }).addTo(map);
}

// Draw the jump itself as a dashed line: it shows where the cut is without
// pretending it was flown.
for (const segment of DATA.segments.filter(s => s.seam)) {
  const index = DATA.segments.findIndex(s => s.id === segment.id);
  const before = DATA.segments.slice(0, index).reverse().find(s => s.length_m > 0);
  if (before) {
    L.polyline([[before.end.lat, before.end.lon], [segment.start.lat, segment.start.lon]],
      { color: "#f0a848", weight: 2, dashArray: "6 7", opacity: 0.8 }).addTo(map);
  }
}

const first = DATA.samples[0], last = DATA.samples[DATA.samples.length - 1];
L.circleMarker([first.lat, first.lon], { radius: 6, color: "#fff", fillColor: "#5ad6a0",
  fillOpacity: 1 }).addTo(map).bindTooltip("start");
L.circleMarker([last.lat, last.lon], { radius: 6, color: "#fff", fillColor: "#f05e6a",
  fillOpacity: 1 }).addTo(map).bindTooltip("end");
map.fitBounds(L.latLngBounds(DATA.samples.map(r => [r.lat, r.lon])), { padding: [30, 30] });

const km = (DATA.length_m / 1000).toFixed(2);
document.getElementById("summary").textContent =
  `— ${DATA.segments.length} segments, ${km} km, ${DATA.duration_s.toFixed(1)} s`;

// Altitude against distance along the path. Rows are evenly spaced by
// distance within a segment, so index is a fair enough x axis here.
const svg = document.getElementById("profile");
const W = svg.clientWidth || 900, H = 130, PAD = 24;
const alts = DATA.samples.map(r => r.alt_ft);
const lo = Math.min(...alts), hi = Math.max(...alts), span = (hi - lo) || 1;
const x = i => PAD + (i / (DATA.samples.length - 1)) * (W - 2 * PAD);
const y = a => H - PAD - ((a - lo) / span) * (H - 2 * PAD);
let parts = [`<line x1="${PAD}" y1="${H - PAD}" x2="${W - PAD}" y2="${H - PAD}" stroke="#2a3340"/>`];
let path = "", previous = null;
DATA.samples.forEach((row, i) => {
  const cut = row.break_before && previous !== null;
  path += `${(i === 0 || cut) ? "M" : "L"}${x(i).toFixed(1)},${y(row.alt_ft).toFixed(1)}`;
  previous = row;
});
parts.push(`<path d="${path}" fill="none" stroke="#4ea3f0" stroke-width="1.8"/>`);
parts.push(`<text x="${PAD}" y="14" fill="#8b96a8" font-size="11">${hi.toFixed(0)} ft</text>`);
parts.push(`<text x="${PAD}" y="${H - 6}" fill="#8b96a8" font-size="11">${lo.toFixed(0)} ft</text>`);
svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
svg.innerHTML = parts.join("");

document.getElementById("legend").innerHTML =
  "<tr><th>segment</th><th>kind</th><th>length</th><th>duration</th><th>speed</th>"
  + "<th>exit hdg</th><th>exit climb</th><th>end alt</th><th>parameters</th></tr>"
  + DATA.segments.map(s => `<tr>
      <td><span class="swatch" style="background:${color(s.id)}"></span>${s.name}
        ${s.seam ? '<span class="seam"> after a cut</span>' : ""}</td>
      <td>${s.kind}</td>
      <td>${s.length_m.toFixed(0)} m</td>
      <td>${s.timing.duration_s.toFixed(1)} s${
        s.timing.dwell_s > 0 ? ` + ${s.timing.dwell_s.toFixed(1)} held` : ""}</td>
      <td>${s.timing.entry_speed_ms === null ? "—"
        : `${s.timing.entry_speed_ms.toFixed(0)} → ${s.timing.exit_speed_ms.toFixed(0)} m/s`}</td>
      <td>${s.exit.heading.toFixed(1)}°</td>
      <td>${s.exit.climb.toFixed(1)}°</td>
      <td>${s.end.alt_ft.toFixed(0)} ft</td>
      <td><code>${JSON.stringify(s.params)}</code></td>
    </tr>`).join("");
</script>
"""


def render(payload: dict) -> str:
    return HTML.replace("__DATA__", json.dumps(payload)).replace("__NAME__", payload["name"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--sample", choices=sorted(SAMPLES), default="figure_eight")
    source.add_argument("--program", type=Path, help="a PathProgram as JSON")
    parser.add_argument("--out", type=Path, help="defaults to flightstudio/tools/out/<name>.html")
    parser.add_argument("--step-m", type=float, default=20.0, help="sample spacing")
    args = parser.parse_args(argv)

    if args.program:
        name = args.program.stem
        program = PathProgram.model_validate_json(args.program.read_text())
    else:
        name = args.sample
        program = SAMPLES[args.sample]()

    try:
        payload = build_payload(name, program, args.step_m)
    except ProgramError as error:
        parser.error(f"segment {error.index} ({error.segment_id}): {error}")

    out = args.out or Path(__file__).parent / "out" / f"{name}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(payload))
    print(f"{name}: {len(payload['segments'])} segments, "
          f"{payload['length_m'] / 1000:.2f} km, {payload['duration_s']:.1f} s -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
