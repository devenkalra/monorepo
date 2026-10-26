"""Control schedule for sim-flown takes: what the stick, pedals and throttle do when.

Each channel is independent. A keyframe that leaves a channel blank says
nothing about it, so the channel carries on from its own previous keyframe.
A channel no keyframe ever sets is not driven at all, and stays with the pilot,
the joystick or the aircraft's own systems.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import ControlKeyframe

CHANNELS = ("aileron", "elevator", "rudder", "throttle", "elevator_trim")

# Changes made by hand during a take land on this grid in the schedule.
NUDGE_SLOT_S = 0.1


@dataclass(frozen=True)
class Nudge:
    """A control changed by hand mid-take: from time t, hold this value."""
    t: float
    channel: str
    value: float

    def as_dict(self) -> dict:
        return {"t": round(self.t, 2), "channel": self.channel, "value": round(self.value, 4)}


def apply_nudges(keyframes: list[ControlKeyframe], nudges: list[Nudge],
                 start_values: dict[str, float] | None = None) -> list[ControlKeyframe]:
    """The schedule with each hand change written in as a STEP at its time.

    The take applies hand changes through this same function, so the schedule
    it returns replays what the take did. A change never alters a RAMP
    keyframe already in the slot (that would turn the jump into a ramp); it
    moves to the next free slot instead.

    A channel the schedule never drove was free until the change. A schedule
    holds a channel's first value from the start, so it is pinned there to
    where it was when the take began (start_values).
    """
    result = sorted((k.model_copy() for k in keyframes), key=lambda k: k.time_offset)
    driven = {c for c in CHANNELS if any(getattr(k, c) is not None for k in result)}
    for nudge in nudges:
        if nudge.channel not in driven:
            driven.add(nudge.channel)
            start = (start_values or {}).get(nudge.channel)
            if start is not None and nudge.t >= NUDGE_SLOT_S:
                _set_at(result, 0.0, nudge.channel, start)
        _set_at(result, nudge.t, nudge.channel, nudge.value)
    return sorted(result, key=lambda k: k.time_offset)


def _set_at(keyframes: list[ControlKeyframe], t: float, channel: str, value: float) -> None:
    slot = round(round(t / NUDGE_SLOT_S) * NUDGE_SLOT_S, 1)
    while True:
        existing = next((k for k in keyframes if abs(k.time_offset - slot) < 1e-6), None)
        if existing is None:
            keyframes.append(ControlKeyframe(time_offset=slot, transition="STEP",
                                             **{channel: value}))
            return
        # A first keyframe's transition never applies, so any will do there.
        if existing.transition == "STEP" or slot == 0.0:
            setattr(existing, channel, value)
            return
        slot = round(slot + NUDGE_SLOT_S, 1)


# A take lasts at least this long past its last control keyframe, so the last
# change has time to show.
HOLD_AFTER_LAST_S = 2.0


class ControlSchedule:
    def __init__(self, keyframes: list[ControlKeyframe]):
        ordered = sorted(keyframes, key=lambda k: k.time_offset)
        self.times = [k.time_offset for k in ordered]
        self._points: dict[str, list[tuple[float, float, str]]] = {
            channel: [
                (k.time_offset, getattr(k, channel), k.transition)
                for k in ordered if getattr(k, channel) is not None
            ]
            for channel in CHANNELS
        }

    @property
    def driven(self) -> tuple[str, ...]:
        return tuple(channel for channel in CHANNELS if self._points[channel])

    def value_at(self, channel: str, t: float) -> float | None:
        points = self._points[channel]
        if not points:
            return None
        # Before its first keyframe a channel already holds that value, so a
        # take starts in the configuration it was authored with.
        if t <= points[0][0]:
            return points[0][1]
        for (t0, v0, _), (t1, v1, transition) in zip(points, points[1:]):
            if t < t1:
                if transition == "STEP" or t1 - t0 < 1e-9:
                    return v0
                return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
        return points[-1][1]

    @property
    def end(self) -> float:
        return self.times[-1] if self.times else 0.0

    def reached(self, t: float) -> int:
        """How many keyframes (in time order) have come due by time t."""
        return sum(1 for k in self.times if k <= t + 1e-9)

    def at(self, t: float) -> dict[str, float]:
        return {channel: self.value_at(channel, t) for channel in self.driven}
