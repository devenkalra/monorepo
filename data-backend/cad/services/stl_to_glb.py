"""Convert STL to GLB for web visualization. Preserves materials when manifest exists."""

import json
from pathlib import Path


def hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    """Convert #rrggbb to (r, g, b, a)."""
    hex_color = str(hex_color).replace("#", "").ljust(6, "0")[:6]
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b, alpha)


def _apply_color(mesh, hex_color: str):
    """Apply solid color to mesh using face colors."""
    import numpy as np
    import trimesh

    r, g, b, a = hex_to_rgba(hex_color)
    mesh.visual = trimesh.visual.ColorVisuals(
        mesh,
        face_colors=np.tile([r, g, b, a], (len(mesh.faces), 1)).astype(np.uint8),
    )


def stl_to_glb(
    stl_path: str,
    glb_path: str,
    manifest_path: str | None = None,
    default_color: str = "#58a6ff",
    *,
    debug_text: bool = False,
) -> bool:
    """
    Convert STL(s) to GLB. If manifest exists with multiple meshes, merge with materials.
    Returns True on success.
    """
    try:
        import trimesh
    except ImportError:
        return False

    stl_path = Path(stl_path)
    glb_path = Path(glb_path)

    if not stl_path.exists():
        return False

    meshes = []
    colors = []

    if manifest_path and Path(manifest_path).exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
        output_dir = stl_path.parent
        for m in manifest.get("meshes", []):
            part_path = output_dir / m.get("file", "")
            if part_path.exists():
                mesh = trimesh.load(str(part_path), force="mesh")
                if mesh.is_empty:
                    continue
                meshes.append(mesh)
                colors.append(m.get("color", default_color))
    else:
        mesh = trimesh.load(str(stl_path), force="mesh")
        if mesh.is_empty:
            return False
        meshes.append(mesh)
        colors.append(default_color)

    # Build scene - apply colors from manifest so materials show in viewer
    scene = trimesh.Scene()
    for i, mesh in enumerate(meshes):
        _apply_color(mesh, colors[i] if i < len(colors) else default_color)
        scene.add_geometry(mesh)

    if debug_text:
        gltf_path = glb_path.with_suffix(".gltf")
        scene.export(str(gltf_path), file_type="gltf")
        debug_manifest = glb_path.with_suffix(".gltf.debug.json")
        with open(debug_manifest, "w") as f:
            json.dump({"meshes": [{"index": i, "color": c} for i, c in enumerate(colors)]}, f, indent=2)
    # Always write GLB for viewer (debug also gets .gltf for inspection)
    scene.export(str(glb_path), file_type="glb")
    return glb_path.exists()
