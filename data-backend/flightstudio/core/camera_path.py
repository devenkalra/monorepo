"""Solve camera keyframes into a pose SimConnect can accept.

Two conversions make this non-obvious:

  * Body-frame keyframes stay attached to the subject as it flies, so their
    world position is recomputed every frame rather than baked at author time.
  * SimConnect positions the camera relative to the USER aircraft, even when
    the subject is a proxy, and takes angles relative to the user aircraft's
    attitude. Both conversions happen here, not at the call site.
"""

from __future__ import annotations

import math

from .curve import Curve, Knot, hermite_ease
from .orientation import (
    aircraft_basis,
    basis_from_angles,
    camera_basis,
    dot,
    normalise,
    relative_angles,
    subtract,
)
from .schema import (
    CameraKeyframe, CameraPose, CameraTransition, CameraType, Pose, camera_sort_key,
)
from .units import feet_to_metres, local_offset, metres_to_feet, offset_latlon

AIRCRAFT_REFERENCE_OFFSETS_M = {
    "CG": (0.0, 0.0, 0.0),
    "NOSE": (0.0, 0.0, 20.0),
    "TAIL": (0.0, 4.0, -25.0),
    "COCKPIT": (0.0, 2.0, 18.0),
}


def level_offset_en(right_m: float, forward_m: float, heading_deg: float) -> tuple[float, float]:
    """East/north metres for a heading-aligned, level-plane offset from the CG.

    Pitch and bank are ignored so the point stays beside the path when the
    aircraft rolls.
    """
    heading = math.radians(heading_deg)
    forward_east, forward_north = math.sin(heading), math.cos(heading)
    right_east, right_north = math.cos(heading), -math.sin(heading)
    return (
        right_m * right_east + forward_m * forward_east,
        right_m * right_north + forward_m * forward_north,
    )


def horizon_offset_en(azimuth_deg: float, radius_m: float, heading_deg: float) -> tuple[float, float]:
    """East/north metres from the CG for a level-plane azimuth.

    0 is aft, 90 the right wing. Heading is degrees true; pitch and bank
    are ignored so a banked aircraft does not drag the drone off level.
    """
    azimuth = math.radians(azimuth_deg)
    return level_offset_en(
        radius_m * math.sin(azimuth),
        -radius_m * math.cos(azimuth),
        heading_deg,
    )


class SolvedCameraPath:
    def __init__(self, keyframes: list[CameraKeyframe], origin_lat: float, origin_lon: float):
        self.keyframes = sorted(keyframes, key=camera_sort_key)
        self.origin_lat = origin_lat
        self.origin_lon = origin_lon
        self.warnings: list[str] = []

    @property
    def duration(self) -> float:
        return self.keyframes[-1].time_offset if self.keyframes else 0.0

    def _is_path_key(self, keyframe: CameraKeyframe) -> bool:
        return keyframe.transition != CameraTransition.CUT

    def _cutaway_at(self, t: float) -> CameraKeyframe | None:
        """Last CUT whose hold window still covers t. The blend path ignores it."""
        active = None
        for keyframe in self.keyframes:
            if keyframe.transition != CameraTransition.CUT:
                continue
            hold = keyframe.easing.hold_s
            if hold <= 0.0:
                continue
            start = keyframe.time_offset
            if start <= t < start + hold:
                active = keyframe
        return active

    def active_index(self, t: float) -> int:
        cutaway = self._cutaway_at(t)
        if cutaway is not None:
            return self.keyframes.index(cutaway)
        last_path = None
        first_path = None
        for position, keyframe in enumerate(self.keyframes):
            if not self._is_path_key(keyframe):
                continue
            if first_path is None:
                first_path = position
            if keyframe.time_offset <= t:
                last_path = position
        if last_path is not None:
            return last_path
        return first_path if first_path is not None else 0

    def _path_runs(self) -> list[list[int]]:
        """Path keys of one interpolate. SHOT starts a new run; CUT is skipped."""
        runs: list[list[int]] = []
        current: list[int] = []
        current_type = None
        for index, keyframe in enumerate(self.keyframes):
            if not self._is_path_key(keyframe):
                continue
            new_run = (
                not current
                or keyframe.camera_type != current_type
                or keyframe.transition == CameraTransition.SHOT
            )
            if new_run:
                if current:
                    runs.append(current)
                current = [index]
                current_type = keyframe.camera_type
            else:
                current.append(index)
        if current:
            runs.append(current)
        return runs

    def _run_for(self, index: int) -> list[int]:
        """BLEND keyframes of the same camera type around this key."""
        for run in self._path_runs():
            if index in run:
                return run
        t = self.keyframes[index].time_offset
        covering = None
        for run in self._path_runs():
            if self.keyframes[run[0]].time_offset <= t:
                covering = run
        return covering or [index]

    def _world_point(self, keyframe: CameraKeyframe, subject: Pose) -> tuple[float, float, float]:
        """Keyframe position as local east/up/north metres about the origin."""
        position = keyframe.position
        if position is None:
            return (0.0, 0.0, 0.0)
        if position.frame == "WORLD":
            north, east = local_offset(
                self.origin_lat, self.origin_lon, position.lat, position.lon
            )
            return (east, feet_to_metres(position.alt_ft_msl), north)
        if position.frame == "HORIZON":
            north, east = local_offset(
                self.origin_lat, self.origin_lon, subject.lat, subject.lon
            )
            offset_east, offset_north = horizon_offset_en(
                position.azimuth_deg, position.radius_m, subject.heading_deg_true
            )
            return (
                east + offset_east,
                feet_to_metres(subject.alt_ft_msl) + position.height_m,
                north + offset_north,
            )

        anchor = AIRCRAFT_REFERENCE_OFFSETS_M.get(position.ref, (0.0, 0.0, 0.0))
        right = position.x_m + anchor[0]
        up = position.y_m + anchor[1]
        forward = position.z_m + anchor[2]
        return self._attached_point(subject, right, up, forward)

    def _attached_point(
        self, subject: Pose, right: float, up: float, forward: float
    ) -> tuple[float, float, float]:
        basis = aircraft_basis(subject.pitch_deg, subject.bank_deg, subject.heading_deg_true)
        world = tuple(
            basis[0][i] * right + basis[1][i] * up + basis[2][i] * forward for i in range(3)
        )
        north, east = local_offset(self.origin_lat, self.origin_lon, subject.lat, subject.lon)
        return (
            east + world[0],
            feet_to_metres(subject.alt_ft_msl) + world[1],
            north + world[2],
        )

    def _target_point(self, keyframe: CameraKeyframe, subject: Pose) -> tuple[float, float, float] | None:
        look_at = keyframe.look_at
        if look_at.mode == "FREE":
            return None
        if look_at.mode == "WORLD_POINT":
            north, east = local_offset(
                self.origin_lat, self.origin_lon, look_at.lat, look_at.lon
            )
            return (east, feet_to_metres(look_at.alt_ft_msl), north)
        north, east = local_offset(
            self.origin_lat, self.origin_lon, subject.lat, subject.lon
        )
        if look_at.mode == "AIRCRAFT_OFFSET":
            offset_east, offset_north = level_offset_en(
                look_at.x_m, look_at.z_m, subject.heading_deg_true
            )
            return (
                east + offset_east,
                feet_to_metres(subject.alt_ft_msl) + look_at.y_m,
                north + offset_north,
            )
        anchor = AIRCRAFT_REFERENCE_OFFSETS_M.get(look_at.ref, (0.0, 0.0, 0.0))
        return self._attached_point(subject, *anchor)

    def _curve_point(self, index: int, t: float, subject: Pose) -> tuple[float, float, float]:
        """Splined camera position as local east/up/north metres."""
        knots = [
            Knot(
                time=self.keyframes[i].time_offset,
                point=self._world_point(self.keyframes[i], subject),
                ease_in=self.keyframes[i].easing.ease_in,
                ease_out=self.keyframes[i].easing.ease_out,
                hold_s=self.keyframes[i].easing.hold_s,
            )
            for i in self._run_for(index)
        ]
        return Curve(knots).point_at(t) if len(knots) > 1 else knots[0].point

    def _target_at(self, index: int, t: float, subject: Pose) -> tuple[float, float, float] | None:
        """Splined look-at point. Named, offset and world targets all become
        world points first, so an Offset-from-aircraft shift eases with the
        drone instead of snapping at the next keyframe.
        """
        active = self.keyframes[index]
        if active.look_at.mode == "FREE":
            return None
        knots = []
        for i in self._run_for(index):
            point = self._target_point(self.keyframes[i], subject)
            if point is None:
                # FREE keys have no target. Skip them so an earlier free look
                # does not freeze Offset-from-aircraft for the rest of the run.
                continue
            knots.append(Knot(
                time=self.keyframes[i].time_offset,
                point=point,
                ease_in=self.keyframes[i].easing.ease_in,
                ease_out=self.keyframes[i].easing.ease_out,
                hold_s=self.keyframes[i].easing.hold_s,
            ))
        if not knots:
            return None
        return Curve(knots).point_at(t) if len(knots) > 1 else knots[0].point

    def _level_from_world(
        self, subject: Pose, east: float, up_m: float, north: float
    ) -> tuple[float, float, float]:
        """Right, forward and world-up metres from the CG in the level plane."""
        ac_north, ac_east = local_offset(
            self.origin_lat, self.origin_lon, subject.lat, subject.lon
        )
        de = east - ac_east
        du = up_m - feet_to_metres(subject.alt_ft_msl)
        dn = north - ac_north
        heading = math.radians(subject.heading_deg_true)
        forward_east, forward_north = math.sin(heading), math.cos(heading)
        right_east, right_north = math.cos(heading), -math.sin(heading)
        right = de * right_east + dn * right_north
        forward = de * forward_east + dn * forward_north
        return right, forward, du

    def _solved_points(
        self, t: float, subject: Pose
    ) -> tuple[CameraKeyframe, tuple[float, float, float], tuple[float, float, float] | None] | None:
        """Active key plus camera/target world points (local E/U/N)."""
        if not self.keyframes:
            return None
        index = self.active_index(t)
        active = self.keyframes[index]
        if active.camera_type is CameraType.COCKPIT:
            return active, (0.0, 0.0, 0.0), None
        if active.transition == CameraTransition.CUT:
            return active, self._world_point(active, subject), self._target_point(active, subject)
        return active, self._curve_point(index, t, subject), self._target_at(index, t, subject)

    def _free_look_at(self, index: int, t: float) -> tuple[float, float]:
        """FREE look (pitch, heading) eased toward the next FREE key in the run.

        Without this a fixed-angle key holds its aim for its whole span and
        snaps at the next key. A following key that aims at a target cannot
        be blended with an angle, so the active key holds until it.
        """
        active = self.keyframes[index]
        pitch, heading = float(active.look_at.pitch_deg), float(active.look_at.heading_deg)
        if active.transition == CameraTransition.CUT:
            return pitch, heading
        run = self._run_for(index)
        if index not in run or run.index(index) + 1 >= len(run):
            return pitch, heading
        following = self.keyframes[run[run.index(index) + 1]]
        if following.look_at.mode != "FREE":
            return pitch, heading
        start = active.time_offset + active.easing.hold_s
        span = following.time_offset - start
        if span <= 1e-9 or t <= start:
            return pitch, heading
        u = hermite_ease(min(1.0, (t - start) / span),
                         active.easing.ease_out, following.easing.ease_in)
        delta = ((float(following.look_at.heading_deg) - heading + 180.0) % 360.0) - 180.0
        return (
            pitch + (float(following.look_at.pitch_deg) - pitch) * u,
            heading + delta * u,
        )

    def framing_at(self, t: float, subject: Pose, user: Pose | None = None) -> dict | None:
        """Commanded camera as live-debug numbers (level-frame + 6DOF)."""
        solved = self._solved_points(t, subject)
        if solved is None:
            return None
        active, camera_point, target = solved
        if active.camera_type is CameraType.COCKPIT:
            cockpit = active.cockpit
            return {
                "type": "COCKPIT",
                "view": cockpit.view.value,
                "index": cockpit.index,
                "zoom_pct": cockpit.zoom_pct,
            }
        right, forward, height = self._level_from_world(subject, *camera_point)
        radius = math.hypot(right, forward)
        azimuth = math.degrees(math.atan2(right, -forward)) % 360.0
        look = active.look_at
        framing: dict = {
            "type": "CINEMATIC",
            "frame": active.position.frame if active.position else None,
            "azimuth_deg": round(azimuth, 2),
            "radius_m": round(radius, 2),
            "height_m": round(height, 2),
            "look_at": look.mode,
            "transition": active.transition.value,
        }
        if target is not None:
            look_right, look_forward, look_height = self._level_from_world(subject, *target)
            framing.update(
                look_right_m=round(look_right, 2),
                look_height_m=round(look_height, 2),
                look_forward_m=round(look_forward, 2),
            )
        elif look.mode == "FREE":
            look_pitch, look_heading = self._free_look_at(self.active_index(t), t)
            framing.update(look_pitch_deg=round(look_pitch, 2),
                           look_heading_deg=round(look_heading, 2))
        pose = self.pose_at(t, subject, user or subject)
        if pose is not None:
            framing.update(
                x_m=round(pose.x_m, 2), y_m=round(pose.y_m, 2), z_m=round(pose.z_m, 2),
                pitch_deg=round(pose.pitch_deg, 2), bank_deg=round(pose.bank_deg, 2),
                heading_deg=round(pose.heading_deg, 2),
            )
        return framing

    def track_point_at(self, t: float, subject: Pose) -> tuple[float, float, float] | None:
        """Where the camera is in the world, for drawing it on the map."""
        view = self.world_view_at(t, subject)
        if view is None:
            return None
        lat, lon, alt_ft, _heading, _pitch = view
        return lat, lon, alt_ft

    def world_view_at(
        self, t: float, subject: Pose
    ) -> tuple[float, float, float, float, float] | None:
        """Cinematic camera as world lat, lon, alt_ft, heading (true), pitch.

        Pitch is nose-up positive, same as the editor. Earth Studio tilt is
        90 + pitch (0 nadir, 90 horizon). Cockpit keys have no world pose.
        """
        solved = self._solved_points(t, subject)
        if solved is None:
            return None
        active, camera_point, target = solved
        if active.camera_type is CameraType.COCKPIT:
            return None
        east, up_m, north = camera_point
        lat, lon = offset_latlon(self.origin_lat, self.origin_lon, north, east)
        alt_ft = metres_to_feet(up_m)
        if target is None:
            pitch, heading = self._free_look_at(self.active_index(t), t)
            # FREE look on a body/horizon rig is authored relative to the
            # aircraft (0 = along the nose). Treat it as true heading so the
            # 3D view and Earth Studio pan turn with the subject.
            frame = getattr(active.position, "frame", None)
            if frame in ("BODY", "HORIZON"):
                heading = (subject.heading_deg_true + heading) % 360.0
        else:
            forward = normalise(subtract(target, camera_point))
            pitch = math.degrees(math.asin(max(-1.0, min(1.0, forward[1]))))
            heading = math.degrees(math.atan2(forward[0], forward[2])) % 360.0
        return lat, lon, alt_ft, heading, pitch

    def look_target_at(self, t: float, subject: Pose) -> tuple[float, float, float] | None:
        """World lat, lon, alt_ft of the point the cinematic camera is aimed at."""
        solved = self._solved_points(t, subject)
        if solved is None:
            return None
        _active, _camera, target = solved
        if target is None:
            return None
        east, up_m, north = target
        lat, lon = offset_latlon(self.origin_lat, self.origin_lon, north, east)
        return lat, lon, metres_to_feet(up_m)

    def fov_at(self, t: float, default: float = 60.0) -> float:
        last: float | None = None
        for key in self.keyframes:
            if key.time_offset > t:
                break
            if key.fov_deg is not None:
                last = float(key.fov_deg)
        if last is not None:
            return last
        for key in self.keyframes:
            if key.fov_deg is not None:
                return float(key.fov_deg)
        return default

    def pose_at(self, t: float, subject: Pose, user: Pose) -> CameraPose | None:
        solved = self._solved_points(t, subject)
        if solved is None:
            return None
        active, camera_point, target = solved
        if active.camera_type is CameraType.COCKPIT:
            return CameraPose(camera_type=CameraType.COCKPIT, fov_deg=active.fov_deg,
                              cockpit=active.cockpit)

        if target is None:
            look_pitch, look_heading = self._free_look_at(self.active_index(t), t)
            forward = basis_from_angles(look_pitch, 0.0, look_heading)[2]
        else:
            forward = subtract(target, camera_point)
            if math.sqrt(sum(c * c for c in forward)) < 1e-6:
                return None

        subject_basis = aircraft_basis(
            subject.pitch_deg, subject.bank_deg, subject.heading_deg_true
        )
        if active.up.mode == "WORLD_UP":
            up_hint = (0.0, 1.0, 0.0)
        elif active.up.mode == "AIRCRAFT_UP":
            up_hint = subject_basis[1]
        else:
            up_hint = normalise((active.up.x, active.up.y, active.up.z))

        basis, warning = camera_basis(forward, up_hint, degenerate_fallback=subject_basis[1])
        if warning and warning not in self.warnings:
            self.warnings.append(warning)

        user_basis = aircraft_basis(user.pitch_deg, user.bank_deg, user.heading_deg_true)
        pitch, bank, heading = relative_angles(user_basis, basis)

        # SimConnect places the camera relative to the user aircraft, so express
        # the solved world point in the user's body frame. That frame is pitched
        # and banked as well as yawed, so project onto the full basis rather
        # than merely rotating by heading.
        user_north, user_east = local_offset(
            self.origin_lat, self.origin_lon, user.lat, user.lon
        )
        offset = (
            camera_point[0] - user_east,
            camera_point[1] - feet_to_metres(user.alt_ft_msl),
            camera_point[2] - user_north,
        )
        right = dot(offset, user_basis[0])
        up = dot(offset, user_basis[1])
        forward_m = dot(offset, user_basis[2])

        return CameraPose(
            camera_type=CameraType.CINEMATIC,
            x_m=right, y_m=up, z_m=forward_m,
            pitch_deg=pitch, bank_deg=bank, heading_deg=heading,
            fov_deg=active.fov_deg,
        )
