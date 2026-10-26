"""Start points for demos and for seeding a new path in the editor.

Chosen so a shot has dense, recognisable scenery behind the aircraft: open
water reads as a flat blue field and makes it impossible to judge motion or
framing. Altitudes are MSL and clear the local terrain and towers with room
for a climb.
"""

from __future__ import annotations

from typing import NamedTuple


class Location(NamedTuple):
    lat: float
    lon: float
    alt_ft_msl: float
    heading_deg_true: float
    label: str


LOCATIONS: dict[str, Location] = {
    "manhattan":   Location(40.7000,  -74.0150,  2200.0,  25.0, "Manhattan"),
    "goldengate":  Location(37.7950, -122.4900,  2000.0, 320.0, "Golden Gate"),
    "london":      Location(51.4950,   -0.1400,  2200.0,  70.0, "London"),
    "paris":       Location(48.8450,    2.3050,  2200.0, 300.0, "Paris"),
    "dubai":       Location(25.1800,   55.2450,  2600.0,  50.0, "Dubai"),
    "hongkong":    Location(22.2700,  114.1450,  2400.0,  55.0, "Hong Kong"),
    "rio":         Location(-22.9750, -43.2300,  2600.0,  35.0, "Rio de Janeiro"),
    "sydney":      Location(-33.8750, 151.1950,  2200.0,  55.0, "Sydney"),
    "seattle":     Location(47.5950, -122.3450,  2200.0, 355.0, "Seattle"),
    "grandcanyon": Location(36.0500, -112.1300,  9000.0, 280.0, "Grand Canyon"),
}
