"""CAD API views - models CRUD, render, geometry, scene configs."""

import json
from django.http import FileResponse, Http404
import logging
import re
import tempfile
from pathlib import Path

from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import CADModel
from .serializers import CADModelSerializer
from .permissions import IsCADModelOwner
from .utils import extract_parameters
from .services.renderer import render_model

logger = logging.getLogger(__name__)

RENDER_CACHE = Path(getattr(settings, "CAD_RENDER_CACHE", settings.BASE_DIR / "cad" / "render_cache"))
TEXTURES_DIR = Path(getattr(settings, "CAD_TEXTURES_DIR", settings.BASE_DIR / "cad" / "textures"))
SCENE_CONFIGS_DIR = Path(getattr(settings, "CAD_SCENE_CONFIGS_DIR", settings.BASE_DIR / "cad" / "scene_configs"))
ENV_DIR = Path(getattr(settings, "CAD_ENV_DIR", settings.BASE_DIR / "cad" / "env"))

for d in (RENDER_CACHE, TEXTURES_DIR, SCENE_CONFIGS_DIR, ENV_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _model_id_from_name(name: str) -> str:
    """Generate slug-like id from name."""
    sid = name.lower().replace(" ", "_").replace("-", "_")
    return re.sub(r"[^a-z0-9_]", "", sid) or "model"


def _extract_depends_on(script: str) -> list[str]:
    """Parse DEPENDS_ON = [...] from script. Returns empty list if absent."""
    m = re.search(r"DEPENDS_ON\s*=\s*\[(.*?)\]", script, re.DOTALL)
    if not m:
        return []
    inner = m.group(1)
    names = re.findall(r'["\']([^"\']+)["\']', inner)
    return [n.strip() for n in names if n.strip()]


def _resolve_dependencies(dep_names: list[str], user) -> dict[str, str]:
    """Resolve DEPENDS_ON names to {name: script_path}. Writes temp files."""
    deps = {}
    temp_files = []
    for name in dep_names:
        dep_model = CADModel.objects.filter(user=user, name=name).first()
        if not dep_model:
            logger.warning("Dependency model '%s' not found for user", name)
            continue
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
        tf.write(dep_model.script)
        tf.close()
        temp_files.append(tf.name)
        deps[name] = tf.name
    return deps, temp_files


class CADModelViewSet(viewsets.ModelViewSet):
    serializer_class = CADModelSerializer
    permission_classes = [IsAuthenticated, IsCADModelOwner]

    def get_queryset(self):
        return CADModel.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def _validate_build(self, script: str) -> bool:
        if "def build(params):" not in script and "def build(params ):" not in script:
            return False
        return True

    def create(self, request, *args, **kwargs):
        script = request.data.get("script", "")
        if not self._validate_build(script):
            return Response(
                {"script": "Script must define build(params) function that returns ThAssembly"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        script = request.data.get("script")
        if script is not None and not self._validate_build(script):
            return Response(
                {"script": "Script must define build(params) function that returns ThAssembly"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, partial=partial, **kwargs)

    def _cache_path(self, pk, suffix=""):
        return RENDER_CACHE / f"cad_{pk}{suffix}"

    def _clear_render_cache(self, pk):
        base = f"cad_{pk}"
        for f in RENDER_CACHE.glob(f"{base}*"):
            try:
                f.unlink()
            except OSError:
                pass

    @action(detail=True, methods=["post"])
    def render(self, request, pk=None):
        """Render the model with given parameters. Returns geometry URL."""
        model = self.get_object()
        params = request.data.get("parameters", {})

        self._clear_render_cache(model.pk)
        output_path = self._cache_path(model.pk, ".stl")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as tf:
            tf.write(model.script)
            script_path = tf.name

        dep_names = _extract_depends_on(model.script)
        dependencies, dep_temp_files = _resolve_dependencies(dep_names, model.user)

        try:
            success, error_msg = render_model(
                script_path,
                params,
                str(output_path),
                debug_text=request.query_params.get("debug", "").lower() in ("1", "true", "yes"),
                dependencies=dependencies if dependencies else None,
            )
        finally:
            try:
                Path(script_path).unlink()
            except OSError:
                pass
            for p in dep_temp_files:
                try:
                    Path(p).unlink()
                except OSError:
                    pass

        if not success:
            return Response(
                {"error": error_msg or "Render failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        output_base = output_path.with_suffix("")
        manifest_path = Path(str(output_base) + "_manifest.json")
        glb_path = Path(str(output_base) + ".glb")

        def _response(url: str, fmt: str):
            out = {"url": url, "format": fmt}
            meta_path = Path(str(output_base) + "_meta.json")
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                if meta.get("documentation"):
                    out["documentation"] = meta["documentation"]
            return out

        if manifest_path.exists() and glb_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if len(manifest.get("meshes", [])) > 1:
                return Response(_response(
                    f"/api/cad/models/{model.pk}/geometry/",
                    "glb",
                ))
        if glb_path.exists():
            return Response(_response(
                f"/api/cad/models/{model.pk}/geometry/",
                "glb",
            ))
        return Response(_response(
            f"/api/cad/models/{model.pk}/geometry/",
            "stl",
        ))

    @action(detail=True, methods=["get"], url_path="meta")
    def get_meta(self, request, pk=None):
        """Return metadata (documentation) from last render."""
        model = self.get_object()
        meta_path = self._cache_path(model.pk, "_meta.json")
        if not meta_path.exists():
            return Response({"documentation": None})
        return Response(json.loads(meta_path.read_text()))

    @action(detail=True, methods=["get"], url_path="geometry")
    def get_geometry(self, request, pk=None):
        """Serve GLB or STL for web visualization."""
        model = self.get_object()
        glb_path = self._cache_path(model.pk, ".glb")
        if glb_path.exists():
            from django.http import FileResponse
            return FileResponse(open(glb_path, "rb"), content_type="model/gltf-binary")
        stl_path = self._cache_path(model.pk, ".stl")
        if stl_path.exists():
            from django.http import FileResponse
            return FileResponse(open(stl_path, "rb"), content_type="model/stl")
        return Response(
            {"error": "Geometry not rendered yet - call POST /render first"},
            status=status.HTTP_404_NOT_FOUND,
        )

    @action(detail=True, methods=["get"], url_path="export/stl")
    def export_stl(self, request, pk=None):
        """Download STL for 3D printing."""
        model = self.get_object()
        stl_path = self._cache_path(model.pk, ".stl")
        if not stl_path.exists():
            return Response(
                {"error": "Geometry not rendered yet - call POST /render first"},
                status=status.HTTP_404_NOT_FOUND,
            )
        from django.http import FileResponse
        return FileResponse(
            open(stl_path, "rb"),
            content_type="model/stl",
            as_attachment=True,
            filename=f"{model.name}.stl",
        )

    @action(detail=True, methods=["get"], url_path="geometry-part/<int:index>")
    def get_geometry_part(self, request, pk=None, index=None):
        """Serve individual STL part for multi-mesh models."""
        model = self.get_object()
        part_path = self._cache_path(model.pk, f"_{index}.stl")
        if not part_path.exists():
            return Response(
                {"error": "Geometry part not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        from django.http import FileResponse
        return FileResponse(open(part_path, "rb"), content_type="model/stl")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self._clear_render_cache(instance.pk)
        return super().destroy(request, *args, **kwargs)


def _scene_id(name: str) -> str:
    sid = name.lower().replace(" ", "_").replace("-", "_")
    return re.sub(r"[^a-z0-9_]", "", sid) or "scene"


class SceneConfigViewSet(viewsets.ViewSet):
    """File-based scene configs (lights, camera, env map). Read-only for now."""
    permission_classes = [IsAuthenticated]

    def list(self, request):
        scenes = []
        for f in SCENE_CONFIGS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                scenes.append({"id": f.stem, "name": data.get("name", f.stem)})
            except Exception:
                scenes.append({"id": f.stem, "name": f.stem})
        return Response({"scenes": scenes})

    def retrieve(self, request, pk=None):
        path = SCENE_CONFIGS_DIR / f"{pk}.json"
        if not path.exists():
            return Response(
                {"error": "Scene config not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(json.loads(path.read_text()))

    def create(self, request):
        name = request.data.get("name", "")
        config = request.data.get("config", {})
        scene_id = _scene_id(name)
        path = SCENE_CONFIGS_DIR / f"{scene_id}.json"
        if path.exists():
            return Response(
                {"error": f"Scene '{scene_id}' already exists"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = {**config, "name": name}
        path.write_text(json.dumps(data, indent=2))
        return Response({"id": scene_id, "name": name})

    def update(self, request, pk=None):
        path = SCENE_CONFIGS_DIR / f"{pk}.json"
        if not path.exists():
            return Response(
                {"error": "Scene config not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        data = json.loads(path.read_text())
        if request.data.get("name") is not None:
            data["name"] = request.data["name"]
        if request.data.get("config") is not None:
            data.update(request.data["config"])
        path.write_text(json.dumps(data, indent=2))
        return Response({"id": pk, "name": data.get("name", pk)})

    def destroy(self, request, pk=None):
        path = SCENE_CONFIGS_DIR / f"{pk}.json"
        if not path.exists():
            return Response(
                {"error": "Scene config not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        path.unlink()
        return Response({"deleted": pk})


def serve_texture(request, filename):
    """Serve texture files for model materials (requires auth)."""
    from django.conf import settings
    base = Path(getattr(settings, "CAD_TEXTURES_DIR", settings.BASE_DIR / "cad" / "textures"))
    path = base / filename
    if not path.exists() or not path.is_file():
        raise Http404("Texture not found")
    return FileResponse(open(path, "rb"), content_type="image/png")


def serve_env(request, filename):
    """Serve environment map files (requires auth)."""
    from django.conf import settings
    base = Path(getattr(settings, "CAD_ENV_DIR", settings.BASE_DIR / "cad" / "env"))
    path = base / filename
    if not path.exists() or not path.is_file():
        raise Http404("File not found")
    return FileResponse(open(path, "rb"), content_type="application/octet-stream")
