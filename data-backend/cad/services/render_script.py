"""
Runs inside FreeCAD headless (freecadcmd).
Receives paths via env: REMOTECAD_MODEL, REMOTECAD_PARAMS, REMOTECAD_OUTPUT
Optional: REMOTECAD_DEPENDENCIES = path to JSON {model_name: script_path} for use_model()
"""
import sys
import json
import os
import traceback

def log(msg):
    print(msg, flush=True)
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()

log("REMOTECAD: script starting")

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

model_path = os.environ.get("REMOTECAD_MODEL")
params_path = os.environ.get("REMOTECAD_PARAMS")
output_path = os.environ.get("REMOTECAD_OUTPUT")

if not all([model_path, params_path, output_path]):
    log("ERROR: Missing REMOTECAD_MODEL, REMOTECAD_PARAMS, or REMOTECAD_OUTPUT env vars")
    sys.exit(1)

log(f"REMOTECAD: model={model_path} output={output_path}")

model_path = os.path.abspath(model_path)
output_path = os.path.abspath(output_path)
debug_text = os.environ.get("REMOTECAD_DEBUG_TEXT", "").lower() in ("1", "true", "yes")

os.makedirs(os.path.dirname(output_path), exist_ok=True)

with open(params_path) as f:
    params = json.load(f)

# Load dependencies for use_model (optional)
dependencies = {}
deps_path = os.environ.get("REMOTECAD_DEPENDENCIES")
if deps_path and os.path.exists(deps_path):
    try:
        with open(deps_path) as f:
            dependencies = json.load(f)
        log(f"REMOTECAD: dependencies={list(dependencies.keys())}")
    except Exception as e:
        log(f"REMOTECAD: failed to load dependencies: {e}")

def _make_use_model(deps):
    _cache = {}
    def use_model(name, dep_params=None):
        if name not in deps:
            raise ValueError(f"Unknown model: {name}. Available: {list(deps.keys())}")
        dep_params = dep_params if dep_params is not None else params
        # Cache key includes params so same model with different params gets rebuilt
        cache_key = (name, json.dumps(dep_params, sort_keys=True))
        if cache_key not in _cache:
            dep_path = deps[name]
            ns = {"__name__": name, "__file__": dep_path, "__builtins__": __builtins__}
            with open(dep_path) as f:
                exec(f.read(), ns)
            _cache[cache_key] = ns["build"](dep_params)
        return _cache[cache_key]
    return use_model

# Always inject use_model so scripts with DEPENDS_ON never get "use_model not defined"
use_model = _make_use_model(dependencies)
model_globals = {
    "__name__": "model",
    "__file__": model_path,
    "__builtins__": __builtins__,
    "use_model": use_model,
}
try:
    with open(model_path) as f:
        exec(f.read(), model_globals)
    model = type(sys)("model")
    model.__dict__.update(model_globals)
except Exception as e:
    log(f"ERROR loading model: {e}")
    traceback.print_exc(file=sys.stderr)
    sys.stderr.flush()
    sys.exit(1)

try:
    assembly = model.build(params)
except Exception as e:
    log(f"ERROR in build(): {e}")
    traceback.print_exc(file=sys.stderr)
    sys.stderr.flush()
    sys.exit(1)

if assembly is None:
    log("ERROR: build() returned None")
    sys.exit(1)

log("REMOTECAD: build() ok, exporting...")

try:
    import Mesh
    import MeshPart

    output_base = os.path.splitext(output_path)[0]
    bodies = list(assembly.collect_bodies_with_materials())
    has_materials = any(m and m.get("color") for _, m in bodies)

    def write_mesh(m, path, as_ascii=False):
        ext = ".ast" if as_ascii else ".stl"
        p = path.replace(".stl", ext) if path.endswith(".stl") else path + ext
        Mesh.export([m], p)

    def mesh_shape(shape, linear_deflection=0.1):
        def try_mesh(s, ld):
            return MeshPart.meshFromShape(
                Shape=s,
                LinearDeflection=ld,
                AngularDeflection=0.5,
                Relative=False,
            )
        for ld in (linear_deflection, 0.5, 1.0, 2.0):
            try:
                return try_mesh(shape, ld)
            except Exception:
                if ld >= 2.0:
                    try:
                        if hasattr(Part, "ShapeFix") and hasattr(Part.ShapeFix, "Shape"):
                            fix = Part.ShapeFix.Shape(shape)
                            fix.perform()
                            fixed = fix.shape
                            if fixed and not fixed.isNull():
                                return try_mesh(fixed, 2.0)
                    except Exception:
                        pass
                    raise
                continue

    if has_materials:
        manifest = {"meshes": [], "debug_text": debug_text}
        for i, (shape, mat) in enumerate(bodies):
            mesh = mesh_shape(shape)
            part_path = f"{output_base}_{i}.stl"
            mesh.write(part_path)
            if debug_text:
                write_mesh(mesh, part_path, as_ascii=True)
            m = mat or {}
            entry = {
                "file": os.path.basename(part_path),
                "color": m.get("color", "#58a6ff"),
            }
            if "specular" in m:
                entry["specular"] = m["specular"]
            if "shininess" in m:
                entry["shininess"] = m["shininess"]
            if "roughness" in m:
                entry["roughness"] = m["roughness"]
            if "metalness" in m:
                entry["metalness"] = m["metalness"]
            if "texture" in m:
                entry["texture"] = m["texture"]
            manifest["meshes"].append(entry)
        manifest_path = f"{output_base}_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        shape = assembly.render_to_shape()
        mesh = mesh_shape(shape)
        mesh.write(output_path)
        if debug_text:
            write_mesh(mesh, output_path, as_ascii=True)
    else:
        shape = assembly.render_to_shape()
        if shape is None:
            log("ERROR: Model returned empty assembly")
            sys.exit(1)
        mesh = mesh_shape(shape)
        mesh.write(output_path)
        if debug_text:
            write_mesh(mesh, output_path, as_ascii=True)
except Exception as e:
    try:
        shape = assembly.render_to_shape()
        if shape:
            shape.exportStl(output_path)
        else:
            raise
    except Exception:
        log(f"ERROR exporting STL: {e}")
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        sys.exit(1)

if not os.path.exists(output_path):
    log(f"ERROR: STL file was not written to {output_path}")
    sys.exit(1)

output_base = os.path.splitext(output_path)[0]
docs = getattr(model, "DOCUMENTATION", None)
if docs is not None and str(docs).strip():
    meta_path = f"{output_base}_meta.json"
    meta = {"documentation": str(docs).strip()}
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

log(f"REMOTECAD: Exported to {output_path} (debug_text={debug_text})")
