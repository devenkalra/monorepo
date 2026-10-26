"""What a hand-flying pilot adds to path following: configuration and hands.

guidance.PathFollower decides where the controls should be. A pilot also
configures the aircraft for the speed it is about to fly, extending flaps as
it slows and the gear before landing, and moves the controls at the rate a
hand moves them, not to wherever the last frame's arithmetic said.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Lowest selectable speed above the stall, as on an Airbus VLS.
VLS_FACTOR = 1.23
# Flaps go out once the speed ahead is within this of the clean minimum, the
# way a crew configures before slowing, not when the stall warning sounds.
CONFIG_MARGIN_KT = 10.0
RETRACT_HYSTERESIS_KT = 10.0
MIN_CONFIG_CHANGE_S = 8.0
LIMIT_MARGIN_KT = 5.0
# Gear goes down this long before touchdown, if the speed allows.
GEAR_LEAD_S = 100.0
TOUCHDOWN_HEIGHT_FT = 30.0
LANDING_DROP_FT = 300.0


@dataclass(frozen=True)
class AircraftProfile:
    name: str
    # Normal-law sidestick: stick commands roll rate and load factor, and
    # neutral holds the current bank and flight path.
    fly_by_wire: bool = False
    # Highest speed per flap handle position, index 0 the clean limit.
    flap_vfe_kt: tuple[float, ...] = ()
    gear_vlo_kt: float = 0.0
    max_lever: float = 1.0

    @property
    def manages_flaps(self) -> bool:
        return len(self.flap_vfe_kt) > 1


GENERIC = AircraftProfile(name="generic")
# A320 family, FCOM limits: VMO 350, CONF 1 230, 2 200, 3 185, FULL 177; VLO 250.
# The lever stops at MCT: TOGA is for go-arounds, not path following.
A320_FAMILY = AircraftProfile(name="A320 family", fly_by_wire=True,
                              flap_vfe_kt=(350.0, 230.0, 200.0, 185.0, 177.0),
                              gear_vlo_kt=250.0, max_lever=0.7)

_A320_MARKERS = ("A318", "A319", "A320", "A321", "A19N", "A20N", "A21N")


def profile_for(*names: str | None) -> AircraftProfile:
    text = " ".join(n for n in names if n).upper()
    return A320_FAMILY if any(m in text for m in _A320_MARKERS) else GENERIC


@dataclass(frozen=True)
class Speeds:
    """Stall speeds from the sim's design speeds, scaled to the actual weight."""

    vs0_kt: float
    vs1_kt: float
    weight_ratio: float = 1.0
    positions: int = 0

    def stall_kt(self, index: int) -> float:
        fraction = index / self.positions if self.positions else 0.0
        clean_to_full = self.vs1_kt + (self.vs0_kt - self.vs1_kt) * fraction
        return clean_to_full * math.sqrt(max(0.3, min(1.0, self.weight_ratio)))

    def vls_kt(self, index: int) -> float:
        return self.stall_kt(index) * VLS_FACTOR


@dataclass
class Config:
    flaps: int
    gear_down: bool
    min_ias_kt: float
    max_ias_kt: float


@dataclass
class ConfigPlanner:
    """Picks flaps and gear for the speed ahead, as a crew would."""

    profile: AircraftProfile
    speeds: Speeds
    touchdown_s: float | None = None
    flaps: int = 0
    gear_down: bool = False
    _last_change: float = field(default=-1e9)

    @property
    def positions(self) -> int:
        return len(self.profile.flap_vfe_kt) - 1

    def wanted_flaps(self, target_ias: float) -> int:
        for index in range(self.positions + 1):
            if target_ias >= self.speeds.vls_kt(index) + CONFIG_MARGIN_KT:
                return index
        return self.positions

    def initial(self, t: float, target_ias: float) -> Config:
        """Configuration to be released in, before the aircraft is moving."""
        if self.profile.manages_flaps:
            self.flaps = self.wanted_flaps(target_ias)
            while self.flaps > 0 and target_ias > self.profile.flap_vfe_kt[self.flaps] - LIMIT_MARGIN_KT:
                self.flaps -= 1
        self.gear_down = self._gear_due(t)
        return self._config()

    def update(self, t: float, ias: float, target_ias: float, need_drag: bool = False) -> Config:
        """`need_drag`: at idle and still too fast, so the next stage goes out
        early for its drag, as on a steep approach, if its limit allows."""
        if self.profile.manages_flaps and t - self._last_change >= MIN_CONFIG_CHANGE_S:
            wanted = self.wanted_flaps(target_ias)
            if need_drag and self.flaps < self.positions and (
                    ias <= self.profile.flap_vfe_kt[self.flaps + 1] - LIMIT_MARGIN_KT):
                wanted = max(wanted, self.flaps + 1)
            landing_soon = self.touchdown_s is not None and t > self.touchdown_s - 2 * GEAR_LEAD_S
            if wanted > self.flaps and ias <= self.profile.flap_vfe_kt[self.flaps + 1]:
                self.flaps += 1
                self._last_change = t
            # Flaps out for drag stay out until the path itself is too fast
            # for them; retracting and re-extending in turn is a surge.
            elif (wanted < self.flaps and not landing_soon and not need_drag
                  and target_ias >= self.speeds.vls_kt(self.flaps - 1) + CONFIG_MARGIN_KT
                  + RETRACT_HYSTERESIS_KT
                  and target_ias > self.profile.flap_vfe_kt[self.flaps] - LIMIT_MARGIN_KT):
                self.flaps -= 1
                self._last_change = t
        if not self.gear_down and self._gear_due(t) and (
                not self.profile.gear_vlo_kt or ias <= self.profile.gear_vlo_kt):
            self.gear_down = True
        return self._config()

    def _gear_due(self, t: float) -> bool:
        return self.touchdown_s is not None and t >= self.touchdown_s - GEAR_LEAD_S

    def _config(self) -> Config:
        vfe = self.profile.flap_vfe_kt
        ceiling = vfe[self.flaps] if vfe else math.inf
        if self.gear_down and self.profile.gear_vlo_kt:
            ceiling = min(ceiling, self.profile.gear_vlo_kt)
        return Config(flaps=self.flaps, gear_down=self.gear_down,
                      min_ias_kt=self.speeds.vls_kt(self.flaps) + LIMIT_MARGIN_KT,
                      max_ias_kt=ceiling - LIMIT_MARGIN_KT)


def touchdown_time(times: list[float], alts_ft: list[float]) -> float | None:
    """When a path that ends on the ground first gets down to it, if it does."""
    if len(alts_ft) < 2 or max(alts_ft) - alts_ft[-1] < LANDING_DROP_FT:
        return None
    ground = alts_ft[-1]
    for i, alt in enumerate(alts_ft):
        if alt - ground <= TOUCHDOWN_HEIGHT_FT and all(
                a - ground <= TOUCHDOWN_HEIGHT_FT for a in alts_ft[i:]):
            return times[i]
    return None


# Full travel per second. A hand on a sidestick or yoke reverses in about half
# a second; thrust levers are moved deliberately, a couple of seconds idle to climb.
HAND_RATES = {"aileron": 2.0, "elevator": 1.5, "rudder": 1.0, "throttle": 0.2}


@dataclass
class Hands:
    rates: dict[str, float] = field(default_factory=lambda: dict(HAND_RATES))
    _last: dict[str, float] = field(default_factory=dict)

    def move(self, wanted: dict[str, float], dt: float) -> dict[str, float]:
        moved = {}
        for channel, value in wanted.items():
            last = self._last.get(channel)
            rate = self.rates.get(channel)
            if last is not None and rate is not None and dt > 0.0:
                step = rate * dt
                value = max(last - step, min(last + step, value))
            moved[channel] = value
            self._last[channel] = value
        return moved
