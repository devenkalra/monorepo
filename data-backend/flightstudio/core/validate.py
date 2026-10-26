"""Design section 7 checks, run in the editor on change and again before playback.

Most of these faults only exist after splining: a camera can pass through the
aircraft between two keyframes that are each perfectly placed. So the checks
run against one sampled solve of the whole path rather than the raw keyframes.
"""

from __future__ import annotations

import math

from .camera_path import SolvedCameraPath
from .controls import CHANNELS, HOLD_AFTER_LAST_S
from .flight_path import SolvedFlightPath
from .schema import CameraTransition, CameraType, Entity, PathDocument
from .units import CAMERA_UNITS_PER_METRE, heading_delta, local_offset

# Design section 3.8. Bracketed at roughly 1.1 km; warn early so a marginal
# shot degrades visibly in the editor rather than silently in the sim.
MAX_CAMERA_OFFSET_M = 1100.0
CAMERA_OFFSET_WARN_M = 900.0

# A camera closer than this to the subject's centre is inside the aeroplane.
MIN_SUBJECT_CLEARANCE_M = 25.0

# Faster than any airliner, slow enough that a near-stationary subject is obvious.
MAX_PLAUSIBLE_SPEED_MS = 350.0
MIN_PLAUSIBLE_SPEED_MS = 15.0

# A manual heading this far off the direction of travel means the aircraft is
# flying sideways. Legitimate for some shots, so it only warns.
MAX_CRAB_DEG = 25.0

# Segment speed is its length over its time, so unevenly timed keyframes make
# the aircraft lurch at the knot between them. Bank scales with speed squared,
# so even a modest jump shows up as a roll.
SPEED_JUMP_RATIO = 1.3
SPEED_JUMP_PROBE_S = 0.1

SAMPLES = 200


class Severity:
    BLOCKING = "BLOCKING"
    WARNING = "WARNING"
    NOTICE = "NOTICE"


def diagnostic(severity: str, check: str, message: str, at: float | None = None) -> dict:
    """A plain dict so it serialises straight to JSON for the editor."""
    return {"severity": severity, "check": check, "message": message, "at": at}


def _camera_same_time_ok(earlier, later) -> bool:
    """A Blend end and a Shot start may share a time; so may a cutaway on a path key."""
    if later.transition == CameraTransition.SHOT:
        return earlier.transition == CameraTransition.BLEND
    return later.transition == CameraTransition.CUT and earlier.transition != CameraTransition.CUT


def _check_times(document: PathDocument) -> list[dict]:
    found: list[dict] = []
    times = [k.time_offset for k in document.flight_keyframes]
    for earlier, later in zip(times, times[1:]):
        if later <= earlier:
            found.append(diagnostic(
                Severity.BLOCKING, "keyframe_times",
                f"Two flight keyframes share or reverse time {later:.2f}s.", later,
            ))
            break
    frames = document.camera_keyframes
    for earlier, later in zip(frames, frames[1:]):
        if later.time_offset < earlier.time_offset:
            found.append(diagnostic(
                Severity.BLOCKING, "keyframe_times",
                f"Two camera keyframes reverse time {later.time_offset:.2f}s.",
                later.time_offset,
            ))
            break
        if later.time_offset == earlier.time_offset and not _camera_same_time_ok(earlier, later):
            found.append(diagnostic(
                Severity.BLOCKING, "keyframe_times",
                f"Two camera keyframes share time {later.time_offset:.2f}s. "
                "A Blend end and a New shot start may share an instant; "
                "two Blend keys may not.",
                later.time_offset,
            ))
            break
    return found


def _check_camera_constraints(document: PathDocument) -> list[dict]:
    """Section 3.2: a cinematic keyframe must at least say where the camera is."""
    return [
        diagnostic(
            Severity.BLOCKING, "camera_underdetermined",
            "Camera keyframe has no position, so its pose is under-determined.",
            keyframe.time_offset,
        )
        for keyframe in document.camera_keyframes
        if keyframe.camera_type is not CameraType.COCKPIT and keyframe.position is None
    ]


def _check_solved_path(document: PathDocument) -> list[dict]:
    """One sampled solve; every geometric and timing check reads from it."""
    found: list[dict] = []
    flight = SolvedFlightPath.from_document(document)
    camera = SolvedCameraPath(
        document.camera_keyframes, flight.origin_lat, flight.origin_lon
    )
    duration = max(document.duration, 1e-6)
    start = flight.pose_at(0.0)

    fastest = (0.0, 0.0)
    slowest = (0.0, math.inf)
    worst_crab = (0.0, 0.0)
    furthest_camera = (0.0, 0.0)
    closest_camera = (0.0, math.inf)
    furthest_subject = (0.0, 0.0)

    for index in range(SAMPLES + 1):
        t = duration * index / SAMPLES
        subject = flight.pose_at(t)

        speed = flight.ground_speed_ms(t)
        if speed > fastest[1]:
            fastest = (t, speed)
        if speed < slowest[1]:
            slowest = (t, speed)

        crab = abs(heading_delta(flight.track_heading_at(t), subject.heading_deg_true))
        if crab > worst_crab[1]:
            worst_crab = (t, crab)

        north, east = local_offset(start.lat, start.lon, subject.lat, subject.lon)
        travelled = math.hypot(north, east)
        if travelled > furthest_subject[1]:
            furthest_subject = (t, travelled)

        # Solving with the subject as its own observer makes the returned
        # offset subject-relative, which is what both camera checks want.
        pose = camera.pose_at(t, subject, subject)
        if pose is None or pose.camera_type is CameraType.COCKPIT:
            continue
        offset = math.sqrt(pose.x_m ** 2 + pose.y_m ** 2 + pose.z_m ** 2)
        if offset > furthest_camera[1]:
            furthest_camera = (t, offset)
        if offset < closest_camera[1]:
            closest_camera = (t, offset)

    if len(document.flight_keyframes) >= 2:
        if fastest[1] > MAX_PLAUSIBLE_SPEED_MS:
            found.append(diagnostic(
                Severity.WARNING, "implausible_speed",
                f"Authored times imply {fastest[1] * 1.944:.0f} kt at {fastest[0]:.1f}s. "
                f"Playing as authored.", fastest[0],
            ))
        if slowest[1] < MIN_PLAUSIBLE_SPEED_MS:
            found.append(diagnostic(
                Severity.WARNING, "implausible_speed",
                f"Authored times imply only {slowest[1] * 1.944:.0f} kt at "
                f"{slowest[0]:.1f}s. Playing as authored.", slowest[0],
            ))
        found += _check_speed_jumps(flight)

    if worst_crab[1] > MAX_CRAB_DEG:
        t, crab = worst_crab
        found.append(diagnostic(
            Severity.WARNING, "heading_fights_track",
            f"The nose is {crab:.0f} degrees off the direction of travel at {t:.1f}s, "
            f"so the aircraft flies sideways. Intentional for some shots; if not, "
            f"set the heading on the surrounding keyframes back to Auto.", t,
        ))

    if document.camera_keyframes:
        t, offset = furthest_camera
        if document.meta.entity is Entity.USER_AIRCRAFT and offset > CAMERA_OFFSET_WARN_M:
            found.append(diagnostic(
                Severity.BLOCKING if offset > MAX_CAMERA_OFFSET_M else Severity.WARNING,
                "camera_offset_clamp",
                f"Camera reaches {offset:.0f} m from the aircraft at {t:.1f}s "
                f"({offset * CAMERA_UNITS_PER_METRE:.0f} units). The simulator clamps "
                f"near {MAX_CAMERA_OFFSET_M:.0f} m and reports nothing when it does "
                f"(design section 3.8).", t,
            ))

        t, clearance = closest_camera
        if clearance < MIN_SUBJECT_CLEARANCE_M:
            found.append(diagnostic(
                Severity.WARNING, "camera_through_subject",
                f"Camera passes {clearance:.0f} m from the aircraft centre at {t:.1f}s, "
                f"so the shot flies through the airframe. Walk the camera keyframes "
                f"one way around the subject rather than doubling back.", t,
            ))

        found += [
            diagnostic(Severity.WARNING, "camera_up_degenerate", message)
            for message in camera.warnings
        ]

    if document.meta.entity is Entity.AI_PROXY and furthest_subject[1] > CAMERA_OFFSET_WARN_M:
        t, travelled = furthest_subject
        found.append(diagnostic(
            Severity.WARNING, "proxy_out_of_camera_range",
            f"The proxy travels {travelled / 1000:.1f} km from its start by {t:.1f}s, "
            f"but the camera is anchored to the user aircraft and clamps near "
            f"{MAX_CAMERA_OFFSET_M / 1000:.1f} km. Use USER_AIRCRAFT as the entity, "
            f"or keep the proxy close (design section 3.8).", t,
        ))

    return found


def _check_speed_jumps(flight: SolvedFlightPath) -> list[dict]:
    jumps = []
    for keyframe in flight.keyframes[1:-1]:
        easing = keyframe.easing
        # Easing or holding at a keyframe is a deliberate change of pace.
        if easing.ease_in > 0.0 or easing.ease_out > 0.0 or easing.hold_s > 0.0:
            continue
        t = keyframe.time_offset
        before = flight.ground_speed_ms(t - SPEED_JUMP_PROBE_S)
        after = flight.ground_speed_ms(t + SPEED_JUMP_PROBE_S)
        if min(before, after) < 1.0:
            continue
        ratio = max(before, after) / min(before, after)
        if ratio > SPEED_JUMP_RATIO:
            jumps.append((ratio, t, before, after))
    if not jumps:
        return []
    ratio, t, before, after = max(jumps)
    others = f" ({len(jumps) - 1} more keyframes do the same)" if len(jumps) > 1 else ""
    return [diagnostic(
        Severity.WARNING, "speed_jump",
        f"Speed jumps from {before * 1.944:.0f} to {after * 1.944:.0f} kt at the {t:.1f}s "
        f"keyframe{others}, so the aircraft lurches and rolls there. Retime the keyframes "
        f"either side so their segments fly at similar speeds, or add easing.", t,
    )]


def validate(document: PathDocument) -> dict:
    """All section 7 checks. Returns diagnostics plus whether playback may start."""
    if not document.flight_keyframes:
        return {
            "diagnostics": [diagnostic(
                Severity.BLOCKING, "empty_path", "The path has no flight keyframes."
            )],
            "playable": False,
        }

    found = _check_times(document) + _check_camera_constraints(document)
    # The solved checks assume a sane time base, so only run them once the
    # structural checks pass.
    if not any(d["severity"] == Severity.BLOCKING for d in found):
        found += _check_solved_path(document)

    return {
        "diagnostics": found,
        "playable": not any(d["severity"] == Severity.BLOCKING for d in found),
    }


# Slower than this and most aircraft are released into a stall.
MIN_RELEASE_SPEED_KT = 60.0


def validate_sim_flight(document: PathDocument) -> dict:
    """Checks for a sim-flown take.

    Most path checks cannot apply: the path does not exist until the sim has
    flown it. What can be checked is the schedule itself, and cameras whose
    distance from the aircraft nobody can predict in advance.
    """
    flight = document.sim_flight
    if flight is None:
        return {"diagnostics": [diagnostic(
            Severity.BLOCKING, "no_sim_flight", "The path has no sim flight set up."
        )], "playable": False}

    found = _check_camera_constraints(document)
    times = [k.time_offset for k in flight.controls]
    for earlier, later in zip(times, times[1:]):
        if later <= earlier:
            found.append(diagnostic(
                Severity.BLOCKING, "control_times",
                f"Two control keyframes share time {later:.2f}s.", later,
            ))
            break
    if times and times[-1] + HOLD_AFTER_LAST_S > flight.duration_s:
        found.append(diagnostic(
            Severity.NOTICE, "control_after_end",
            f"The take runs to {times[-1] + HOLD_AFTER_LAST_S:.1f}s, past its "
            f"{flight.duration_s:g}s length, so the last control keyframe ({times[-1]:.1f}s) "
            f"has {HOLD_AFTER_LAST_S:g}s to act.", times[-1],
        ))
    if not any(getattr(k, channel) is not None for k in flight.controls
               for channel in CHANNELS):
        found.append(diagnostic(
            Severity.NOTICE, "hands_off",
            "No control is set, so the aircraft flies hands-off from its initial state.",
        ))
    if flight.initial.airspeed_kt < MIN_RELEASE_SPEED_KT:
        found.append(diagnostic(
            Severity.WARNING, "release_speed",
            f"Released at {flight.initial.airspeed_kt:.0f} kt, most aircraft will stall.", 0.0,
        ))
    if any(k.position is not None and k.position.frame == "WORLD"
           for k in document.camera_keyframes):
        found.append(diagnostic(
            Severity.WARNING, "world_camera_unpredictable",
            "A world-fixed camera may end up beyond the sim's 1.1 km camera limit, because "
            "where the aircraft goes is not known until it has flown (design section 3.8).",
        ))
    return {
        "diagnostics": found,
        "playable": not any(d["severity"] == Severity.BLOCKING for d in found),
    }
