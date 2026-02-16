"""ThPath - 3D paths for sweeping. Hides FreeCAD Wire/Edge details."""

import math
import FreeCAD as App
import Part


def _vec(p):
    """Convert (x,y,z) or (x,y) to App.Vector. (x,y) becomes (x,y,0)."""
    if len(p) >= 3:
        return App.Vector(float(p[0]), float(p[1]), float(p[2]))
    return App.Vector(float(p[0]), float(p[1]), 0.0)


def _make_tanarc_edge(start, tangent, angle, radius):
    """Create arc edge from start, tangent, angle (degrees), radius. Returns (edge, end_point)."""
    P = _vec(start)
    T = _vec(tangent)
    if T.Length < 1e-10:
        raise ValueError("tangent must be non-zero")
    T = T.normalize()
    r = float(radius)
    if r <= 0:
        raise ValueError("radius must be positive")
    theta_rad = math.radians(float(angle))
    up = App.Vector(0, 0, 1) if abs(T.z) < 0.9 else App.Vector(1, 0, 0)
    B = T.cross(up).normalize()
    sign = 1 if angle >= 0 else -1
    C = P - sign * r * B
    u = (P - C).normalize()
    Q = C + r * (math.cos(theta_rad) * u + math.sin(theta_rad) * T)
    M = C + r * (math.cos(theta_rad / 2) * u + math.sin(theta_rad / 2) * T)
    arc = Part.Arc(P, M, Q)
    return arc.toShape(), Q


class ThPath:
    """3D path for sweeping. API operates at path level; no Wire/Edge exposure."""

    def __init__(self, wire=None):
        self._wire = wire

    def _to_wire(self, fillet_radius=0):
        """Return the path wire. If fillet_radius > 0, smooth segment junctions."""
        wire = self._wire
        if fillet_radius <= 0 or len(wire.Edges) < 2:
            return wire
        # B-spline interpolation through vertices gives smooth transitions
        try:
            pts = [v.Point for v in wire.Vertexes]
            if len(pts) >= 2:
                bs = Part.BSplineCurve()
                bs.interpolate(pts)
                return Part.Wire([bs.toShape()])
        except Exception:
            pass
        return wire

    def move(self, offset):
        """Translate the path by offset (x,y,z). Use to start from a different point than origin."""
        v = _vec(offset)
        moved = self._wire.copy()
        moved.translate(v)
        return ThPath(moved)

    @staticmethod
    def line(start, end):
        """Line from start to end. start, end: (x,y,z)."""
        s, e = _vec(start), _vec(end)
        edge = Part.makeLine(s, e)
        return ThPath(Part.Wire([edge]))

    @staticmethod
    def arc(start, middle, end):
        """Arc through three 3D points: start, middle, end."""
        s, m, e = _vec(start), _vec(middle), _vec(end)
        arc = Part.Arc(s, m, e)
        return ThPath(Part.Wire([arc.toShape()]))

    @staticmethod
    def tanarc(start, tangent, angle, radius):
        """Arc from start point with given tangent and sweep angle.

        start: (x,y,z) - start point
        tangent: (x,y,z) - direction at start (normalized)
        angle: degrees, +ve = curve left of tangent, -ve = curve right
        radius: arc radius
        """
        edge, _ = _make_tanarc_edge(start, tangent, angle, radius)
        return ThPath(Part.Wire([edge]))

    @staticmethod
    def polyline(points):
        """Polyline through 3D points. points: [(x,y,z), ...]."""
        if len(points) < 2:
            raise ValueError("polyline needs at least 2 points")
        pts = [_vec(p) for p in points]
        wire = Part.makePolygon(pts)
        return ThPath(wire)

    @staticmethod
    def bezier(points):
        """Bezier curve through 3D control points. points: [(x,y,z), ...]."""
        if len(points) < 2:
            raise ValueError("bezier needs at least 2 control points")
        poles = [_vec(p) for p in points]
        bz = Part.BezierCurve()
        bz.setPoles(poles)
        return ThPath(Part.Wire([bz.toShape()]))

    @staticmethod
    def compose(segments):
        """Complex path from line, arc, tanarc, and bezier segments.
        Use {"type": "move", "to": (x,y,z)} as first segment to start from a different point.
        tanarc: {"type": "tanarc", "tangent": (x,y,z), "angle": degrees, "radius": r}
        """
        edges = []
        current = None

        for seg in segments:
            stype = seg.get("type", "line")
            if stype == "move":
                current = _vec(seg["to"])
            elif stype == "line":
                to_pt = _vec(seg["to"])
                if current is None:
                    current = _vec(seg.get("from", (0, 0, 0)))
                if seg.get("relative"):
                    to_pt = App.Vector(
                        current.x + to_pt.x,
                        current.y + to_pt.y,
                        current.z + to_pt.z,
                    )
                e = Part.makeLine(current, to_pt)
                edges.append(e)
                current = to_pt
            elif stype == "arc":
                mid = _vec(seg["middle"])
                to_pt = _vec(seg["to"])
                if current is None:
                    current = _vec(seg.get("from", (0, 0, 0)))
                arc = Part.Arc(current, mid, to_pt)
                edges.append(arc.toShape())
                current = to_pt
            elif stype == "tanarc":
                tangent = _vec(seg["tangent"])
                angle = seg["angle"]
                radius = seg["radius"]
                if current is None:
                    current = _vec(seg.get("from", (0, 0, 0)))
                edge, end_pt = _make_tanarc_edge(current, tangent, angle, radius)
                edges.append(edge)
                current = end_pt
            elif stype == "bezier":
                controls = seg.get("controls", seg.get("points", []))
                if not controls:
                    raise ValueError("bezier segment requires 'controls' or 'points'")
                if current is None:
                    current = _vec(seg.get("from", (0, 0, 0)))
                poles = [current] + [_vec(p) for p in controls]
                bz = Part.BezierCurve()
                bz.setPoles(poles)
                edges.append(bz.toShape())
                current = poles[-1]
            else:
                raise ValueError(f"unknown segment type: {stype}")

        if not edges:
            raise ValueError("compose requires at least one segment")

        wire = Part.Wire(edges)
        return ThPath(wire)
