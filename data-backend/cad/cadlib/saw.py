"""Hand saw and saw_cut for planar cuts along a path."""

import FreeCAD as App
import Part

from .assembly import ThBody


def _debug_enabled():
    import os
    return os.environ.get("REMOTECAD_SAW_DEBUG", "").lower() in ("1", "true", "yes")


def _log(msg):
    if _debug_enabled():
        import sys
        sys.stderr.write(f"[saw_cut] {msg}\n")
        sys.stderr.flush()


def hand_saw(radius, thickness):
    """Define a hand saw by blade radius and thickness."""
    return {"radius": float(radius), "thickness": float(thickness)}


def saw_cut(body_or_assembly, start, end, axis, side, saw=None):
    """Cut a body or assembly with a plane along a path, return left or right part(s)."""
    if hasattr(body_or_assembly, "saw_cut") and not hasattr(body_or_assembly, "shape"):
        return body_or_assembly.saw_cut(start, end, axis, side, saw)
    body = body_or_assembly
    start = App.Vector(start[0], start[1], start[2]) if not isinstance(start, App.Vector) else start
    end = App.Vector(end[0], end[1], end[2]) if not isinstance(end, App.Vector) else end
    axis_vec = App.Vector(axis[0], axis[1], axis[2]) if not isinstance(axis, App.Vector) else axis

    path = end - start
    path_len = path.Length
    if path_len < 1e-10:
        raise ValueError("start and end must be distinct points")

    path_norm = path.normalize()
    axis_norm = axis_vec.normalize()

    # axis lies in the cut plane (with the path). plane_normal = path × axis.
    plane_normal = path_norm.cross(axis_norm)
    if plane_normal.Length < 1e-10:
        plane_normal = axis_norm.cross(path_norm)
    if plane_normal.Length < 1e-10:
        raise ValueError("axis must not be parallel to the path")

    plane_normal = plane_normal.normalize()
    plane_point = start

    size = 1e6
    if abs(plane_normal.z) < 0.9:
        dir_x = App.Vector(0, 0, 1).cross(plane_normal).normalize()
    else:
        dir_x = App.Vector(1, 0, 0).cross(plane_normal).normalize()
    origin = plane_point - dir_x * (size / 2) - plane_normal.cross(dir_x).normalize() * (size / 2)
    plane_face = Part.makePlane(size, size, origin, plane_normal, dir_x)

    shape = body.shape
    center = shape.CenterOfMass
    _log(f"Center Before Cut: {center}")

    if not shape or not shape.isValid():
        _log("body has no valid shape")
        return None

    try:
        import BOPTools.SplitAPI
        slice_result = BOPTools.SplitAPI.slice(
            shape, [plane_face], "Split", 0.0
        )
        solids = slice_result.Solids if hasattr(slice_result, "Solids") else []
        if not solids and hasattr(slice_result, "childShapes"):
            solids = [s for s in slice_result.childShapes() if s.ShapeType == "Solid"]
    except Exception as e:
        _log(f"slice failed: {e}")
        return None

    solids = list(solids) if solids else []

    want_positive = side.lower() == "right"

    if len(solids) < 2:
        if len(solids) == 1:
            orig_vol = shape.Volume
            piece_vol = solids[0].Volume
            if abs(piece_vol - orig_vol) < 1e-6:
                _log("only 1 solid with same volume - plane did not bisect")
                sol = solids[0]
                dist = (sol.CenterOfMass - plane_point).dot(plane_normal)
                on_positive = dist > 0
                if on_positive != want_positive:
                    _log("solid on wrong side of plane for requested side, returning None")
                    return None
                best_solid = sol
            else:
                _log("only 1 solid (different volume) - check side")
                sol = solids[0]
                dist = (sol.CenterOfMass - plane_point).dot(plane_normal)
                on_positive = dist > 0
                if on_positive != want_positive:
                    _log("piece on wrong side for requested side, returning None")
                    return None
                best_solid = sol
        else:
            _log("no solids - plane may not have intersected, check if body is on requested side")
            dist = (shape.CenterOfMass - plane_point).dot(plane_normal)
            on_positive = dist > 0
            if on_positive != want_positive:
                _log("body on wrong side of plane for requested side, returning None")
                return None
            _log("body on correct side, returning original (cut had no impact)")
            result = ThBody(shape.copy())
            if body._material:
                result._material = dict(body._material)
            return result
    else:
        best_solid = None
        for sol in solids:
            try:
                center = sol.CenterOfMass
                to_center = center - plane_point
                dist = to_center.dot(plane_normal)
                on_positive_side = dist > 0
                if on_positive_side == want_positive:
                    best_solid = sol
                    break
            except Exception:
                _log("Exception")
                continue

        if best_solid is None:
            def key(s):
                d = (s.CenterOfMass - plane_point).dot(plane_normal)
                return d if want_positive else -d
            best_solid = max(solids, key=key)

    result = ThBody(best_solid.copy())
    if body._material:
        result._material = dict(body._material)
    return result
