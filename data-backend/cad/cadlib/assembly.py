"""ThBody and ThAssembly - hierarchical model building for FreeCAD."""

import FreeCAD as App
import Part

from .materials import get_material


class ThBody:
    def __init__(self, shape=None):
        self.shape = shape
        self._material = None  # {"color": "#58a6ff", "name": "steel"}

    @staticmethod
    def box(l, w, h):
        return ThBody(Part.makeBox(l, w, h))

    @staticmethod
    def cylinder(radius, height):
        return ThBody(Part.makeCylinder(radius, height))

    @staticmethod
    def sphere(radius):
        return ThBody(Part.makeSphere(radius))

    def set_material(
        self,
        color=None,
        name=None,
        specular=None,
        shininess=None,
        roughness=None,
        metalness=None,
        texture=None,
    ):
        """Set material properties for visualization.

        Use name to apply a predefined material from the library, e.g.:
            body.set_material(name="walnut")
            body.set_material(name="steel")
            body.set_material(name="plastic_red")

        Available: pine, cherry, walnut, oak, maple, birch, mahogany, ebony,
        steel, aluminum, brass, copper, bronze, chrome, gold, iron,
        plastic_white, plastic_black, plastic_red, plastic_blue, plastic_green,
        plastic_yellow, plastic_orange, plastic_gray, plastic_clear.

        You can override library values with explicit color, specular, shininess.
        """
        if self._material is None:
            self._material = {}
        if name is not None:
            self._material["name"] = str(name)
            lib = get_material(name)
            if lib:
                if "color" not in self._material:
                    self._material["color"] = lib["color"]
                if "specular" not in self._material:
                    self._material["specular"] = lib.get("specular", "#111111")
                if "shininess" not in self._material:
                    self._material["shininess"] = lib.get("shininess", 100)
        if color is not None:
            if isinstance(color, int):
                self._material["color"] = "#{:06x}".format(color)
            else:
                self._material["color"] = str(color)
        if specular is not None:
            if isinstance(specular, int):
                self._material["specular"] = "#{:06x}".format(specular)
            else:
                self._material["specular"] = str(specular)
        if shininess is not None:
            self._material["shininess"] = float(shininess)
        if roughness is not None:
            self._material["roughness"] = float(roughness)
        if metalness is not None:
            self._material["metalness"] = float(metalness)
        if texture is not None:
            self._material["texture"] = str(texture)
        return self

    @property
    def material(self):
        return self._material

    def move(self, x=0, y=0, z=0):
        if self.shape:
            self.shape.translate(App.Vector(x, y, z))
        return self

    def rotate(self, axis_vec, angle, center=None):
        if self.shape:
            center = center or App.Vector(0, 0, 0)
            self.shape.rotate(center, axis_vec, angle)
        return self

    def cut(self, other):
        """Boolean cut: subtract other from self. other can be ThBody or ThAssembly."""
        cutter = other.shape if hasattr(other, "shape") and other.shape else None
        if cutter is None and hasattr(other, "render_to_shape"):
            cutter = other.render_to_shape()
        if self.shape and cutter:
            self.shape = self.shape.cut(cutter)
        return self

    def common(self, other_body):
        if self.shape and other_body.shape:
            self.shape = self.shape.common(other_body.shape)
        return self

    def fuse(self, other_body):
        if self.shape and other_body.shape:
            self.shape = self.shape.fuse(other_body.shape)
        return self

    def copy(self):
        other = ThBody(self.shape.copy())
        if self._material:
            other._material = dict(self._material)
        return other

    def saw_cut(self, start, end, axis, side, saw=None):
        from .saw import saw_cut
        return saw_cut(self, start, end, axis, side, saw)

    @staticmethod
    def sweep(profile, path, fillet_radius=0):
        """Sweep a profile along a path. Returns a new ThBody.

        Profile is aligned so its plane is normal to the path's tangent at the start.
        Sections stay parallel along the path (fixed trihedron).

        fillet_radius: if > 0, smooth transitions at path segment junctions.
        """
        from .profile import ThProfile
        from .path import ThPath

        if not isinstance(profile, ThProfile):
            raise TypeError("profile must be a ThProfile")
        if not isinstance(path, ThPath):
            raise TypeError("path must be a ThPath")

        spine = path._to_wire(fillet_radius=fillet_radius)
        prof_wire = profile._to_wire()

        # Tangent at path start: profile plane normal aligns with this
        first_edge = spine.Edges[0]
        try:
            tangent = first_edge.tangentAt(first_edge.FirstParameter)
        except Exception:
            tangent = first_edge.Vertexes[1].Point.sub(first_edge.Vertexes[0].Point)
        if tangent.Length < 1e-10:
            tangent = App.Vector(0, 0, 1)
        tangent = tangent.normalize()
        start_point = first_edge.Vertexes[0].Point

        # Translate profile to path start (profile is built at origin by default)
        prof_wire = prof_wire.copy()
        prof_wire.translate(start_point)

        try:
            pipe = Part.BRepOffsetAPI_MakePipeShell(spine)
            pipe.setTrihedronMode(start_point, tangent)
            pipe.add(prof_wire)
            pipe.Build()
            shape = pipe.Shape()
        except Exception:
            try:
                shape = spine.makePipeShell([prof_wire], True, False)
            except Exception as e:
                raise RuntimeError(f"sweep failed: {e}") from e

        # MakePipeShell often returns a Shell (not Solid). Always convert to solid
        # for proper CSG operations.
        if shape and not shape.isNull() and shape.ShapeType != "Solid":
            if spine.isClosed():
                try:
                    from Part import ShapeFix
                    fix = ShapeFix.Shape(shape)
                    fix.Perform()
                    shape = fix.Shape()
                except (ImportError, AttributeError, Exception):
                    pass
            if shape.ShapeType == "Shell" and shape.isClosed():
                try:
                    shape = Part.Solid(shape)
                except Exception:
                    pass
            elif shape.ShapeType == "Compound":
                for s in shape.Shells:
                    if s.isClosed():
                        try:
                            shape = Part.Solid(s)
                            break
                        except Exception:
                            continue

        return ThBody(shape)


class ThAssembly:
    def __init__(self, name="Assembly"):
        self.name = name
        self.bodies = []

    def add(self, th_body):
        self.bodies.append(th_body)
        return self

    def move(self, x=0, y=0, z=0):
        for body in self.bodies:
            if hasattr(body, "shape"):
                body.move(x, y, z)
            elif hasattr(body, "move"):
                body.move(x, y, z)
        return self

    def rotate(self, axis_vec, angle, center=None):
        rotation_center = center if center is not None else self.get_center()
        for body in self.bodies:
            if hasattr(body, "shape"):
                body.rotate(axis_vec, angle, rotation_center)
            elif hasattr(body, "rotate"):
                body.rotate(axis_vec, angle, rotation_center)
        return self

    def cut(self, other):
        """Boolean cut: subtract other from each body. other can be ThBody or ThAssembly."""
        for body in self.bodies:
            if hasattr(body, "shape") and body.shape:
                body.cut(other)
            elif hasattr(body, "cut"):
                body.cut(other)
        return self

    def common(self, other_body):
        for body in self.bodies:
            if hasattr(body, "shape") and body.shape:
                body.common(other_body)
            elif hasattr(body, "common"):
                body.common(other_body)
        return self

    def saw_cut(self, start, end, axis, side, saw=None):
        """Cut each body in the assembly with a plane along a path. Keeps left or right part per body."""
        from .saw import saw_cut as _saw_cut
        new_bodies = []
        for body in self.bodies:
            if hasattr(body, "shape") and body.shape:
                result = _saw_cut(body, start, end, axis, side, saw)
                if result is not None:
                    new_bodies.append(result)
            elif hasattr(body, "saw_cut"):
                body.saw_cut(start, end, axis, side, saw)
                new_bodies.append(body)
        self.bodies = new_bodies
        return self

    def copy(self):
        """Return a copy of the assembly with each body copied."""
        other = ThAssembly(self.name)
        for body in self.bodies:
            if hasattr(body, "copy"):
                other.add(body.copy())
            else:
                other.add(body)
        return other

    def get_center(self):
        shapes = []
        for b in self.bodies:
            if hasattr(b, "shape") and b.shape:
                shapes.append(b.shape)
            elif hasattr(b, "render_to_shape"):
                s = b.render_to_shape()
                if s:
                    shapes.append(s)
        if not shapes:
            return App.Vector(0, 0, 0)
        return Part.makeCompound(shapes).BoundBox.Center

    def render_to_shape(self):
        all_shapes = []
        for b in self.bodies:
            if hasattr(b, "shape") and b.shape:
                all_shapes.append(b.shape)
            elif hasattr(b, "render_to_shape"):
                s = b.render_to_shape()
                if s:
                    all_shapes.append(s)
        if not all_shapes:
            return None
        return Part.makeCompound(all_shapes)

    def collect_bodies_with_materials(self):
        for b in self.bodies:
            if hasattr(b, "shape") and b.shape:
                mat = getattr(b, "material", None)
                yield b.shape, mat
            elif hasattr(b, "collect_bodies_with_materials"):
                for s, m in b.collect_bodies_with_materials():
                    yield s, m
