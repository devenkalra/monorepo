# FlightStudio — segment path model

Status: stages 1–8 built (schema through construction tools). Replaces the
waypoint model in `core/schema.py` / `core/flight_path.py` for **authored**
paths; stages 9–10 (import, validation surfacing) remain.

## 1. Why

Today a path is a list of waypoints, each pinned in both space and time, and
the leg shape between two of them is a decoration that has to bend to hit both
ends. Geometry is always the dependent variable, and the editor spends its
time fighting that:

- an arc radius silently clamps to half the chord, because no circle through
  two fixed points can be tighter;
- Hermite tangent lengths fight their endpoints;
- a B-spline needs the `end_id` span machinery to express a curve that spans
  more than one leg;
- a sweep past 180° needs the `major` flag, and a full circle is unreachable
  at any setting because the two endpoints are distinct by construction.

The new model inverts the relationship. A path is a **program** over a pen.
Each segment advances the pen, parameters are primary, and endpoints are
derived — unless the operator chooses to pin them, in which case the solver
works backwards.

## 2. What does not change

The output contract, almost. A solved path is still a list of sampled poses on
a clock, and `preview.py`, the 2D map, the 3D view, sim pose injection, the
Earth Studio export and the camera solver all keep consuming exactly that.
Everything in this document sits upstream of `preview()`.

The one addition is a per-sample break flag, needed because a mid-path
`MoveTo` makes position discontinuous while the clock stays continuous
(§5.1). Consumers that draw continuous geometry have to honour it; consumers
that only read a pose at an instant are unaffected.

Recorded data also does not change. Flown takes and imported tracks remain
dense sample lists; they reach the designer only after the existing cleanup
pass has sparsified them, at which point they enter as fitted spline segments
(§7.3).

## 3. The pen

A program is an origin plus an ordered list of segments. Evaluating it walks
the segments in order, carrying pen state:

| Carried | Why |
| --- | --- |
| position | the obvious one — where the next segment starts |
| tangent (unit, 3D) | an arc's start tangent and a Hermite's out-handle default from it, so smooth joins are free rather than hand-maintained |
| speed | otherwise every segment boundary is a speed discontinuity to fix by hand |

Pen state is runtime only. It is never stored; it is recomputed on every
evaluation.

```python
class PathProgram(BaseModel):
    origin: GeoPoint                 # lat, lon, alt_ft_msl
    segments: list[Segment]
```

## 4. Parameters, pinning and the solver

### 4.1 Values are always stored

Every parameter of every segment always has a stored value, and a separate
`pinned` set names the ones the solver may not move:

```python
class SegmentBase(BaseModel):
    id: str
    name: str = ""
    pinned: set[str] = set()          # parameter names the solver must not touch
    constraints: list[Constraint] = []
    velocity: VelocityProfile
    on_ground: bool = False
    end: Boundary = Boundary()        # dwell and angle pins at this segment's end
    construction: Construction | None = None
```

Two reasons for storing values rather than making free parameters `None`:

1. The document is evaluable without running a solve, so loading and drawing
   a path never depends on solver convergence.
2. The stored values are the numeric solver's **seed**. For a non-linear
   system with multiple solutions, seeding from where the operator last left
   it is what makes the result predictable instead of jumping between
   branches mid-drag.

### 4.2 Constraints

Pinning a point is a constraint, not a stored coordinate. The same form covers
a pinned endpoint and a through-point on a spline:

```python
class Constraint(BaseModel):
    kind: Literal["POINT"] = "POINT"
    at: float                         # parameter along the segment, 0..1
    lat: float
    lon: float
    alt_ft_msl: float
    lock_horizontal: bool = True      # so altitude alone can be constrained
    lock_vertical: bool = True
```

A pinned endpoint is `at = 1.0`. A spline that must cross a landmark is the
same object at some interior `at`. This is why there is one spline primitive
rather than two (§7).

### 4.3 Degrees of freedom

Each `POINT` constraint contributes up to three equations. Parameters per
segment type, split by kind — the distinction matters to the solver (§4.4):

| Segment | Continuous free parameters | Count | Discrete |
| --- | --- | --- | --- |
| MoveTo | position (3), outgoing tangent (2), speed (1) | 3–6 | — |
| LineTo | heading, climb, distance | 3 | — |
| Arc | radius, sweep, tilt, rise per turn | 4 | side |
| Hermite | end point (3), out handle (3), in handle (3) | 9 | — |
| Spline | 3 per control point, plus one weight each | 3n + n | — |

So a fully pinned endpoint determines a polar `LineTo` exactly, and leaves an
`Arc` under-determined by one — the operator must pin one more, typically the
radius. That is not an error, it is a state, and the editor shows it (§9).

The `Arc` plane contributes one continuous parameter, not two. The normal has
two degrees of freedom, but requiring G1 continuity ties the component of the
entry tangent along the normal to the rise rate (§5.3), so the normal's two
angles and the pair {tilt, rise per turn} are two views of the same thing.

### 4.4 Solver

Hybrid, as agreed:

- **Closed form** for the common single-unknown cases — pinned endpoint on a
  `LineTo`, sweep from a pinned endpoint on an `Arc` with radius and plane
  held, and so on. Exact, instant, no convergence risk. These are the cases
  that run under the operator's hand during a drag, so they must not iterate.
- **Numeric fallback** for arbitrary pin combinations: Levenberg–Marquardt on
  the residual vector, warm-started from the stored values. Rank of the
  Jacobian distinguishes genuinely under-determined from locally degenerate.
- **Discrete parameters are enumerated, not optimised.** `Arc.side` is a
  branch, not a direction LM can descend. Where it is unpinned the solver
  tries both and keeps the lower residual, preferring the branch matching the
  stored value on a tie so the shape does not flip under the operator's hand.

### 4.5 Cascade

A segment solves locally, then the pen advances and the next segment is
evaluated forward. If a downstream segment carries its own constraints, it
re-solves when the pen reaches it. So an upstream edit can cascade — which is
the point of pinning, but worth being clear about: it is a chain of local
solves, one per segment, not a global system. Cost is linear in segment count
and every link is either closed form or a small warm-started LM.

## 5. Segments

### 5.1 MoveTo

Jumps the pen without flying the gap. Used to start the path, and **mid-path
to skip a stretch** — a hand-drawn tour that cuts between locations, or a
flown track with an uninteresting middle removed.

**Time stays continuous; only position jumps.** Cutting ten minutes out of a
flown track should make the take ten minutes shorter, not leave a ten-minute
hole in the clock. So a `MoveTo` has zero duration and the clock simply
carries on, which keeps one timeline for camera keys, systems and controls.

The pen's tangent and speed are meaningless across a jump, so a `MoveTo`
re-seeds them. It may state an outgoing tangent and speed; if it does not, the
following segment must supply its own start direction — a polar `LineTo` does,
an `Arc` would need an explicit entry tangent.

A seam has consequences that need handling rather than discovering:

| Area | Handling |
| --- | --- |
| `pose_at(t)` at the seam | right-continuous — the post-jump pose wins, with the pre-jump pose available as the left limit for the camera's last frame before the cut |
| bank, pitch rate, ground speed | all differenced over `RATE_WINDOW_S`; across a seam that window reads a near-infinite turn rate and yields a wild bank spike, so rates are computed one-sided and never across a seam |
| track rendering | samples carry a break marker so `flightTrackSegments()` splits the polyline instead of drawing a line across the gap |
| playhead | jumps rather than sliding |
| camera anchors | a `MoveTo` has zero length, so `at` is degenerate; keys anchor to the seam itself |
| pose injection | fine — setting a position is already what it does |
| `SIM_FLOWN` playback | not fine; the sim cannot teleport an aircraft it is flying. Validation rejects a mid-path `MoveTo` on a sim-flown path, alongside the existing playback-mode checks in `core/validate.py` |

The break marker is the one change to the output contract in §2: samples gain
a flag, and consumers that draw continuous geometry must honour it.

### 5.2 LineTo

Straight. Parameterised polar — heading, climb angle, distance — which is the
generative form. Absolute and relative targets are expressed as a `POINT`
constraint at `at = 1.0`, not as a second representation.

### 5.3 Arc

Helical. The start tangent comes from the pen, which is what makes it
generative and continuous.

| Parameter | Kind | Notes |
| --- | --- | --- |
| `side` | discrete | which side of the entry tangent the centre sits on |
| `radius_m` | continuous | no chord/2 floor — no endpoint is fixed by construction |
| `sweep_deg` | continuous | ≥ 0, unbounded above, so multiple turns are ordinary |
| `tilt_deg` | continuous | roll of the circle's plane about the entry tangent, positive toward the right of travel; 0 is a horizontal circle |
| `rise_per_turn_m` | continuous | per turn rather than total, so it composes with a sweep still being adjusted |

Unbounded sweep retires the `major` flag and the chord/2 radius clamp
together: both existed only because the two endpoints were fixed.

**`side` stays, and is not redundant.** Given the pen position, the entry
tangent and the plane, the centre can sit on either side at distance
`radius_m`, and no other parameter resolves that. It is the same two-fold
ambiguity `arc_frame` settles today with
`sign = 1.0 if path.side == "LEFT" else -1.0`, just measured against the entry
tangent instead of the chord.

Folding it into the sign of `sweep_deg` does work mathematically — place the
centre so that positive sweep leaves along the tangent, and let the sign pick
the side — but it costs more than it saves. It makes the plane normal's
orientation redundant with the sweep's sign, so one curve gets two encodings;
"RIGHT, 270°" reads better than "−270°"; and a discrete branch hidden inside a
continuous parameter is the wrong shape for the solver (§4.4). So the sign
lives in exactly one readable place, `sweep_deg` stays non-negative, and the
plane normal is canonicalised to remove the remaining redundancy.

**Rise and tangent continuity are coupled.** A helix's tangent is not in the
circle's plane — it carries a component along the normal equal to the rise
rate. For G1 continuity that component must match the pen's incoming climb,
so `rise_per_turn_m` *defaults* to whatever value does so. A level pen gives a
flat circle. Overriding the default is allowed and produces a kink in the
vertical profile only; validation flags it rather than forbidding it. This is
the same arrangement as a Hermite's out-handle defaulting from the pen.

### 5.4 Hermite

End point with in and out handles. The out handle defaults to the pen tangent,
so G1 continuity with the previous segment is the default rather than
something to maintain.

### 5.5 Spline

One primitive. See §7.

## 6. Timing

### 6.1 Velocity profile

Each segment carries a cubic velocity profile in **normalised** arc length
`σ = s / L`, stored as raw coefficients, in m/s:

```python
class VelocityProfile(BaseModel):
    """v(σ) = c0 + c1·σ + c2·σ² + c3·σ³, for σ in [0, 1]."""
    c0: float
    c1: float = 0.0
    c2: float = 0.0
    c3: float = 0.0
    inherit_entry: bool = True        # c0 taken from the previous segment's exit
```

Normalised, not absolute, because endpoints are solved and so `L` changes
constantly. In absolute arc length the exit speed `v(L)` would drift every
time a radius was nudged, silently breaking continuity with the next segment.
In normalised form the entry and exit speeds are `c0` and `c0+c1+c2+c3`,
invariant under geometry edits.

Segment duration:

```
T = L · ∫₀¹ dσ / v(σ)
```

evaluated by fixed-order Gauss–Legendre quadrature. Time scales linearly with
length, which is the physically right behaviour.

### 6.2 Fitting a duration

Scaling all four coefficients by `k` scales `T` by exactly `1/k`. So fitting a
segment — or a whole program — to a target duration is a division, not a
search. It only becomes a 1-D root find when part of the profile is pinned,
for instance holding entry speed for continuity and solving the rest; that
case is well behaved and bisects reliably.

### 6.3 Positivity

`v → 0` makes the integral diverge, so the profile needs a floor and a cubic
can dip below it. The minimum of a cubic on a closed interval is at the
endpoints or at a root of its quadratic derivative, so validation is exact and
closed form rather than sampled.

### 6.4 Dwells

A hold cannot be expressed as a speed, for the reason above. It stays an
explicit dwell at a segment boundary:

```python
class Boundary(BaseModel):
    dwell_s: float = 0.0
    heading: Angle = AutoAngle()      # MANUAL pins, as today
    pitch: Angle = AutoAngle()
    bank: Angle = AutoAngle()
```

### 6.5 Sampling

The sampler needs `σ(t)`. From `dt = L·dσ / v(σ)` build a monotone `t(σ)`
table per segment at solve time and invert by binary search with local
interpolation. Same shape as the existing arc-length table in `curve.py`.

### 6.6 Retired

`Easing` goes away. `ease_in` and `ease_out` were a crude way to shape pace and
are fully subsumed by the profile; `hold_s` becomes `Boundary.dwell_s`.

## 7. Splines

### 7.1 One primitive, authored

A spline segment stores a NURBS control polygon — control points and per-point
weights — and that is authoritative. Evaluation reads only those. Control
points are authored directly, so there is no solve on edit, the response to a
drag is continuous, and support is local: moving one control point provably
cannot disturb the far end.

This is the opposite of the current `fit_bspline`, where control points are
least-squares output, the control count steps as the tolerance is crossed
mid-drag, and `chord_params` re-parameterises every point when any one moves.

### 7.2 Provenance

The fitter survives as a **constructor**, not as the representation. Its
inputs are retained alongside the control polygon as inert provenance:

```python
class Construction(BaseModel):
    """How this segment was originally built. Never read during evaluation."""
    kind: Literal["FIT_POINTS", "ARC_THREE_POINT", ...]
    points: list[GeoPoint] = []
    tolerance_m: float | None = None
    produced: list[Vec3] = []         # the hull the fit produced, for change detection
```

Re-opening the construction lets the operator add or move a target point and
regenerate the hull. Because `produced` records what the fit originally
returned, the editor can tell whether the current hull still matches it and
therefore whether a re-fit would discard anything.

**A re-fit discards direct control-point edits and per-point weights**, with a
warning naming how many. It does not attempt to preserve them as offsets: the
fitter varies its control count, so after a re-fit there is often no
correspondence to re-apply them to.

The field is deliberately general rather than spline-specific, so an arc built
from a three-point tool can retain its picks the same way later.

### 7.3 Through-points

Approximate fitting is a construction-time operation. Exact "the curve passes
through here" is a `POINT` constraint (§4.2) satisfied by the solver moving
control points. Between the two, the operator gets both interactions on one
object: drag a control point for free local shaping, or drop a through-point
where the path must cross a landmark and drag that, on the curve.

## 8. Camera binding

Camera keyframes anchor to a segment and a fraction along it, not to absolute
time:

```python
class CameraAnchor(BaseModel):
    segment_id: str
    at: float                          # 0..1 along that segment
```

Absolute time is derived at solve time. Reshaping or retiming a segment keeps
the shot framed as authored instead of sliding every later key out of sync.

A key whose `segment_id` no longer exists is retained and reported by
validation rather than silently dropped — deleting a segment should not
quietly destroy camera work.

## 9. Solvability in the editor

Rather than failing mysteriously, the popup carries a live readout derived
from §4.3 — *5 free, 3 constrained, under-determined by 2* — plus the
Jacobian rank check to distinguish "needs more pins" from "these pins are
contradictory". Under-determined is a normal working state, not an error; the
solver simply takes the nearest solution to the stored seed.

## 10. Editor

- **Segment list** replaces the waypoint table. Ordered, like a layer stack,
  since order is now load-bearing in a way waypoint order never quite was.
- **Non-modal popup** per selected segment, anchored near it, draggable. It
  must stay open while the operator drags map gizmos, so the existing tangent
  grips and radius handles keep working. This is the requirement that makes it
  more than a cosmetic change from the tall right panel.
- Per-type map gizmos, as today but keyed on segment rather than waypoint.
- Multi-select shows common fields.

## 11. Build order

Each stage is independently testable; the frontend only starts once the solver
is trustworthy.

1. **Schema and evaluator** — *done*. `PathProgram`, `MoveTo`, `LineTo`,
   `Arc`, free parameters only, no solver. Geometry only: no time, so
   sampling is by distance. Covers the seam handling from §5.1 that does not
   need a clock — the break flag and the right-continuous lookup at a jump.
   Unit tests against known geometry in `tests/test_program.py`.
2. **Timing** — *done*. Velocity profile, `σ(t)` inversion, duration fit,
   positivity validation, in `core/program_time.py`. Covers the rest of §5.1,
   since attitude rates need a clock to exist: one-sided differencing, and a
   test that a seam produces no bank spike. The MANUAL boundary angles of
   §6.4 are stored but not yet applied — attitude is still derived from the
   path, and `validate_timing()` reports a pin that is being ignored.
3. **Solver** — *done*. `core/program_solve.py`: `pinned` and `POINT`
   constraints, closed-form cases first, the LM fallback, `Arc.side`
   enumerated rather than descended, and the DOF / rank reporting of §9.
   Constraints apply to `MoveTo`, `LineTo` and `Arc`; the spline cases of
   §7.3 wait on stage 4 for something to constrain.
4. **Hermite and Spline** — *done*. `HermiteSegment` with out-handle
   defaulting from the pen; `SplineSegment` as an authored NURBS control
   polygon with per-point weights; `Construction` provenance; the fitter
   demoted to `fit_spline_from_points` in `core/program_construct.py`.
   Through-points on a spline are ordinary `POINT` constraints (§7.3).
5. **Preview endpoint** — *done*. `preview_program()` in `preview.py` emits
   the same `{duration, samples, camera_track}` shape as the waypoint
   preview, with `break_before` at a mid-path MoveTo. Served at
   `POST /api/flightstudio/program/preview/`. `flightTrackSegments()`
   honours the break flag so a cut is not drawn as a line across the gap.
   Camera track is empty until §8 anchors are wired.
6. **Frontend read-only** — *done*. `FlightPath.program` JSONField; create
   with `kind=program` + a demo from `core/program_demos.py`; GET returns
   `{kind, path_id, program}`. The main app loads it, calls
   `program/preview/`, draws and plays on the 2D/3D map like a waypoint
   path. Editing is disabled (banner + harness link). Switch paths in the
   dropdown to compare side by side.
7. **Frontend editing** — *done*. Main app: floating `#program-popup`,
   pin/solvability readout, reorder ↑↓, and per-type map gizmos
   (`programEdit.js` + shared `programFields.js`). `preview_program`
   returns `segments` tips so one round-trip drives the map and the
   popup. Save PUTs `{kind, program}`. Add/insert/delete wait on stage 8.
8. **Construction tools** — *done*. Main app: Add bar (Line / Arc / Hermite /
   MoveTo / Spline), insert after the selection, Remove, Esc cancels place
   mode. Click builders set Line heading+distance, Arc radius, Hermite /
   MoveTo `to`; Spline appends a default hull from the pen.
9. **Import** — cleaned flown track to fitted spline segments.
10. **Validation surfacing** and export checks.

## 12. Open items

- **Groups.** `WaypointGroup` references waypoint ids. Segment-level grouping
  is probably the analogue but nothing depends on it yet.
- **Solver jitter during drags.** The mitigation is closed-form fast paths
  plus warm-starting, but it needs measuring on a real path before stage 7.
- **Seam-adjacent camera framing.** A key anchored to a seam has a pose on
  either side of it. Which one a cinematic camera should use, and whether the
  operator should be able to choose, is not settled.
- **Plane normal canonicalisation.** §5.3 requires one, but the exact rule —
  and what it does when the entry tangent is vertical — needs writing down
  with the stage 1 evaluator.

## 13. Not migrated

Existing authored paths stay on the waypoint model and are not converted. The
two document types coexist at rest; the program model is what new paths use.
