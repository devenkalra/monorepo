"""ThProfile - 2D profiles for sweeping. Hides FreeCAD Wire/Edge details."""

import FreeCAD as App
import Part


def _vec(p, z=0):
    """Convert (x,y) or (x,y,z) to App.Vector."""
    if len(p) >= 3:
        return App.Vector(float(p[0]), float(p[1]), float(p[2]))
    return App.Vector(float(p[0]), float(p[1]), float(z))


def _plane_from_spec(plane):
    """Convert plane spec to (origin, normal, x_dir). Default XY."""
    if plane is None:
        return (App.Vector(0, 0, 0), App.Vector(0, 0, 1), App.Vector(1, 0, 0))
    if isinstance(plane, str) and plane.upper() == "XY":
        return (App.Vector(0, 0, 0), App.Vector(0, 0, 1), App.Vector(1, 0, 0))
    if isinstance(plane, str) and plane.upper() == "XZ":
        return (App.Vector(0, 0, 0), App.Vector(0, 1, 0), App.Vector(1, 0, 0))
    if isinstance(plane, str) and plane.upper() == "YZ":
        return (App.Vector(0, 0, 0), App.Vector(1, 0, 0), App.Vector(0, 1, 0))
    if isinstance(plane, (tuple, list)):
        origin = _vec(plane[0])
        normal = App.Vector(plane[1][0], plane[1][1], plane[1][2]).normalize()
        if len(plane) >= 3:
            x_dir = App.Vector(plane[2][0], plane[2][1], plane[2][2]).normalize()
        else:
            if abs(normal.z) < 0.9:
                x_dir = App.Vector(0, 0, 1).cross(normal).normalize()
            else:
                x_dir = App.Vector(1, 0, 0).cross(normal).normalize()
        return (origin, normal, x_dir)
    return (App.Vector(0, 0, 0), App.Vector(0, 0, 1), App.Vector(1, 0, 0))


def _to_3d(p2, origin, normal, x_dir):
    """Map 2D point (x,y) to 3D in the profile plane."""
    y_dir = normal.cross(x_dir).normalize()
    return origin + x_dir * p2[0] + y_dir * p2[1]


class ThProfile:
    """2D profile for sweeping. API operates at profile level; no Wire/Edge exposure."""

    def __init__(self, wire=None, plane=None):
        self._wire = wire
        self._plane = _plane_from_spec(plane)

    def _to_wire(self):
        return self._wire

    @staticmethod
    def rect(w, h, plane=None):
        """Rectangle profile centered at origin."""
        origin, normal, x_dir = _plane_from_spec(plane)
        hw, hh = w / 2, h / 2
        pts = [
            _to_3d((-hw, -hh), origin, normal, x_dir),
            _to_3d((hw, -hh), origin, normal, x_dir),
            _to_3d((hw, hh), origin, normal, x_dir),
            _to_3d((-hw, hh), origin, normal, x_dir),
        ]
        wire = Part.makePolygon(pts + [pts[0]])
        return ThProfile(wire, plane)

    @staticmethod
    def circle(radius, plane=None):
        """Circular profile centered at origin."""
        origin, normal, x_dir = _plane_from_spec(plane)
        circle = Part.makeCircle(radius, origin, normal)
        wire = Part.Wire([circle])
        return ThProfile(wire, plane)

    @staticmethod
    def polygon(points, plane=None):
        """Polygon from list of (x,y) or (x,y,z) points. Auto-closes if not closed."""
        origin, normal, x_dir = _plane_from_spec(plane)
        pts = [_to_3d((p[0], p[1]), origin, normal, x_dir) for p in points]
        if pts and len(pts) > 1:
            p0, pn = pts[0], pts[-1]
            if (p0 - pn).Length > 1e-10:
                pts.append(pts[0])
        wire = Part.makePolygon(pts)
        return ThProfile(wire, plane)

    @staticmethod
    def compose(segments, start=(0, 0), plane=None):
        """Complex profile from line, arc, and bezier segments. Auto-closes if not closed."""
        origin, normal, x_dir = _plane_from_spec(plane)

        def to3(p):
            return _to_3d((float(p[0]), float(p[1])), origin, normal, x_dir)

        edges = []
        current = to3(start)

        for seg in segments:
            stype = seg.get("type", "line")
            if stype == "line":
                to_pt = to3(seg["to"])
                if current is not None:
                    e = Part.makeLine(current, to_pt)
                    edges.append(e)
                current = to_pt
            elif stype == "arc":
                mid = to3(seg["middle"])
                to_pt = to3(seg["to"])
                if current is not None:
                    arc = Part.Arc(current, mid, to_pt)
                    edges.append(arc.toShape())
                current = to_pt
            elif stype == "bezier":
                controls = seg.get("controls", seg.get("points", []))
                if not controls:
                    raise ValueError("bezier segment requires 'controls' or 'points'")
                poles = [current] if current is not None else []
                poles.extend([to3(p) for p in controls])
                if len(poles) < 2:
                    raise ValueError("bezier needs at least 2 points (current + controls)")
                bz = Part.BezierCurve()
                bz.setPoles(poles)
                edges.append(bz.toShape())
                current = poles[-1]
            else:
                raise ValueError(f"unknown segment type: {stype}")

        if not edges:
            raise ValueError("compose requires at least one segment")

        wire = Part.Wire(edges)
        if not wire.isClosed():
            first = edges[0].Vertexes[0].Point
            last = edges[-1].Vertexes[1].Point
            if (first - last).Length > 1e-10:
                close_edge = Part.makeLine(last, first)
                wire = Part.Wire(edges + [close_edge])

        return ThProfile(wire, plane)
