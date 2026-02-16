"""FreeCAD render service - executes models, exports STL and GLB."""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from .stl_to_glb import stl_to_glb

logger = logging.getLogger(__name__)


def _clean_error_message(err: str) -> str:
    """Extract meaningful error from FreeCAD output, stripping boot banner."""
    if not err:
        return ""
    lines = err.strip().split("\n")
    error_markers = ("ERROR:", "Error", "Traceback", "Exception", 'File "', "  ")
    meaningful = []
    in_traceback = False
    for line in lines:
        if any(m in line for m in error_markers):
            meaningful.append(line)
            in_traceback = True
        elif in_traceback and (line.startswith("  ") or not line.strip()):
            meaningful.append(line)
        elif in_traceback and line.strip() and not line.strip().startswith("#"):
            meaningful.append(line)
        elif any(x in line for x in ("FreeCAD", "Libs:", "#####", "LGPL", "Juergen")):
            in_traceback = False
    result = "\n".join(meaningful).strip()
    if not result:
        non_empty = [l for l in lines if l.strip() and "FreeCAD" not in l and "#####" not in l]
        result = "\n".join(non_empty[-8:]) if non_empty else err[:500]
    return result[:2000]


def render_model(
    model_path: str,
    params: dict,
    output_path: str,
    *,
    debug_text: bool = False,
    dependencies: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """
    Run the model script in FreeCAD headless.
    Exports STL (for 3D printing) and GLB (for web visualization).
    dependencies: optional {model_name: script_path} for use_model()
    Returns (success: bool, error_message: str).
    """
    logger.info("Render start: model=%s output=%s", model_path, output_path)

    script_dir = Path(__file__).parent
    render_script = script_dir / "render_script.py"
    project_root = script_dir.parent
    model_path_abs = str(Path(model_path).resolve())
    output_path_resolved = str(Path(output_path).resolve())

    Path(output_path_resolved).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as pf:
        json.dump(params, pf)
        params_path = pf.name

    deps_path = None
    if dependencies is not None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as df:
            json.dump(dependencies, df)
            deps_path = df.name

    env = os.environ.copy()
    env["REMOTECAD_MODEL"] = model_path_abs
    env["REMOTECAD_PARAMS"] = params_path
    env["REMOTECAD_OUTPUT"] = output_path_resolved
    if deps_path is not None:
        env["REMOTECAD_DEPENDENCIES"] = deps_path
    env["PYTHONUNBUFFERED"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["REMOTECAD_SAW_DEBUG"] = "1"
    if debug_text:
        env["REMOTECAD_DEBUG_TEXT"] = "1"

    # Prefer explicit path - freecadcmd may not be in PATH inside Docker
    freecad_cmd = (
        "/usr/bin/freecadcmd"
        if Path("/usr/bin/freecadcmd").exists()
        else "freecadcmd"
    )

    try:
        result = subprocess.run(
            [freecad_cmd, str(render_script.resolve())],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(project_root),
            env=env,
        )

        if debug_text and (result.stdout or result.stderr):
            for line in (result.stdout or "").splitlines():
                s = line.strip()
                if s and "#####" not in s and "FreeCAD 0." not in s[:15]:
                    logger.info("FreeCAD: %s", line.rstrip())
            for line in (result.stderr or "").splitlines():
                if line.strip():
                    logger.info("FreeCAD stderr: %s", line.rstrip())

        if result.returncode != 0:
            raw_stdout = (result.stdout or "").strip()
            raw_stderr = (result.stderr or "").strip()
            raw = raw_stderr or raw_stdout
            logger.error(
                "FreeCAD failed (rc=%s). stdout last 500: %s | stderr last 500: %s",
                result.returncode,
                raw_stdout[-500:] if raw_stdout else "(empty)",
                raw_stderr[-500:] if raw_stderr else "(empty)",
            )
            debug_path = Path(output_path_resolved).parent / "_render_debug.txt"
            try:
                with open(debug_path, "w") as f:
                    f.write("=== STDOUT ===\n")
                    f.write(result.stdout or "(empty)\n")
                    f.write("\n=== STERR ===\n")
                    f.write(result.stderr or "(empty)\n")
            except OSError:
                pass
            err = _clean_error_message(raw) or raw[:500] or "FreeCAD render failed"
            return False, err

        if not os.path.exists(output_path_resolved):
            logger.error("STL not created at %s", output_path_resolved)
            return False, "STL file was not created"

        logger.info("FreeCAD succeeded, converting to GLB")
        output_base = Path(output_path_resolved).with_suffix("")
        glb_path = str(output_base) + ".glb"
        manifest_path = str(output_base) + "_manifest.json"
        stl_to_glb(output_path_resolved, glb_path, manifest_path, debug_text=debug_text)
        logger.info("Render success: %s", output_path_resolved)
        return True, ""
    except subprocess.TimeoutExpired:
        logger.error("Render timeout")
        return False, "Render timeout (120s)"
    except FileNotFoundError:
        try:
            result = subprocess.run(
                ["/usr/bin/freecadcmd", str(render_script.resolve())],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(project_root),
                env=env,
            )
            if result.returncode != 0:
                raw = (result.stderr or "").strip() or (result.stdout or "").strip()
                err = _clean_error_message(raw) or raw[:500] or "FreeCAD render failed"
                return False, err
            return os.path.exists(output_path_resolved), ""
        except FileNotFoundError:
            return False, "FreeCAD not found. Install FreeCAD (apt install freecad) and ensure freecadcmd is in PATH. Rebuild the Docker image if needed."
    except Exception as e:
        logger.exception("Render unexpected error: %s", e)
        return False, f"Render error: {e!s}"
    finally:
        try:
            os.unlink(params_path)
        except OSError:
            pass
        if deps_path is not None:
            try:
                os.unlink(deps_path)
            except OSError:
                pass
