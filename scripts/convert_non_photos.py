#!/usr/bin/env python3
"""
Traverse a directory tree, convert each .avi and .vob to .mp4 using ffmpeg,
and on success move the source (and optional .xmp sidecar) into a parallel
archive tree.

Example:
  /src/a/b/c/x.avi  -> converts to /src/a/b/c/x.mp4
  then moves:
  /src/a/b/c/x.avi  -> /archive/a/b/c/x.avi
  /src/a/b/c/x.xmp  -> /archive/a/b/c/x.xmp   (if present)

Notes:
- Requires ffmpeg (and ffprobe) installed and on PATH.
- Defaults: x264 CRF 16, preset slow, AAC 320k, faststart.
- Applies deinterlacing (yadif) for .vob by default (DVD content is often interlaced).
"""

from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple
import re


def setup_logging(log_path: Path, verbose: bool = False) -> None:
    log_path = log_path.expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Clear any existing handlers (critical)
    for h in list(root.handlers):
        root.removeHandler(h)

    # File handler
    fh = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    root.addHandler(fh)
    root.addHandler(ch)

    # Sanity: force a write and show where it is
    logging.info(f"Logging to file: {log_path}")


def sanitize_name(name: str) -> str:
    # Keep it conservative: remove characters that often cause trouble in tools/filesystems.
    # You can widen/tighten this set as you like.
    return re.sub(r"[\'\"\:\*\?\<\>\|]", "_", name)


VIDEO_EXTS = {".avi", ".vob"}


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def which_or_die(exe: str) -> None:
    from shutil import which
    if which(exe) is None:
        raise SystemExit(f"ERROR: '{exe}' not found on PATH. Install it first.")


def ffprobe_has_video_stream(path: Path) -> bool:
    # Lightweight sanity check that file is readable and has video.
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_type",
        "-of", "json",
        str(path),
    ]
    cp = run(cmd)
    if cp.returncode != 0:
        return False
    try:
        data = json.loads(cp.stdout or "{}")
        streams = data.get("streams", [])
        return any(s.get("codec_type") == "video" for s in streams)
    except Exception:
        return False


def build_ffmpeg_cmd(
        input_path: Path,
        output_tmp: Path,
        *,
        crf: int,
        preset: str,
        audio_bitrate: str,
        deinterlace_vob: bool,
) -> list[str]:
    # For .vob: yadif is usually the "right" thing; for .avi: leave as-is.
    vf = None
    if input_path.suffix.lower() == ".vob" and deinterlace_vob:
        # Deinterlace only when interlaced frames are detected.
        vf = "yadif=mode=send_frame:parity=auto:deint=interlaced"

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",  # overwrite temp file if it exists

        "-probesize", "100M",
        "-analyzeduration", "100M",
        "-thread_queue_size", "512",

        "-i", str(input_path),
        "-map", "0:v:0",
        "-map", "0:a?",
        "-nostdin",
    ]
    if vf:
        cmd += ["-vf", vf]


    # High quality single output:
    cmd += [
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-movflags", "+faststart",
        str(output_tmp),
    ]

    return cmd


def sidecar_xmp_candidates(media_path: Path) -> list[Path]:
    """
    Common sidecar patterns:
      - x.xmp
      - x.avi.xmp or x.vob.xmp
    """
    candidates = [
        media_path.with_suffix(".xmp"),
        Path(str(media_path) + ".xmp"),
    ]
    # Return only those that exist (dedup by resolved path string)
    seen = set()
    existing = []
    for p in candidates:
        try:
            key = str(p.resolve())
        except Exception:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.exists() and p.is_file():
            existing.append(p)
    return existing


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def move_to_archive(src_root: Path, archive_root: Path, src_file: Path) -> Path:
    rel = src_file.relative_to(src_root)
    dst = archive_root / rel
    ensure_parent(dst)
    shutil.move(str(src_file), str(dst))
    return dst


def safe_replace(tmp_path: Path, final_path: Path) -> None:
    # Atomically replace if possible (same filesystem).
    try:
        os.replace(tmp_path, final_path)
    except OSError:
        # Fallback to copy + replace
        ensure_parent(final_path)
        shutil.move(str(tmp_path), str(final_path))


def convert_one(
        src_root: Path,
        archive_root: Path,
        media_path: Path,
        *,
        crf: int,
        preset: str,
        audio_bitrate: str,
        deinterlace_vob: bool,
        overwrite_mp4: bool,
        dry_run: bool,
) -> Tuple[bool, str]:
    if not media_path.exists():
        return False, "missing"

    if not ffprobe_has_video_stream(media_path):
        return False, "ffprobe: no readable video stream"

    # out_mp4 = media_path.with_suffix(".mp4")

    out_mp4 = media_path.with_suffix(".mp4")
    safe_name = sanitize_name(out_mp4.name)
    out_mp4 = out_mp4.with_name(safe_name)

    if out_mp4.exists() and not overwrite_mp4:
        return False, f"mp4 exists (skip): {out_mp4.name}"

    # tmp_out = out_mp4.with_suffix(out_mp4.suffix + ".tmp")
    tmp_out = out_mp4.with_suffix(".tmp.mp4")

    cmd = build_ffmpeg_cmd(
        media_path,
        tmp_out,
        crf=crf,
        preset=preset,
        audio_bitrate=audio_bitrate,
        deinterlace_vob=deinterlace_vob,
    )

    if dry_run:
        return True, "dry-run"

    # Run conversion
    cp = run(cmd)
    if cp.returncode != 0:
        # Cleanup tmp if created
        if tmp_out.exists():
            try:
                tmp_out.unlink()
            except Exception:
                pass
        msg = cp.stderr.strip().splitlines()[-1] if cp.stderr else "ffmpeg failed"
        return False, f"ffmpeg failed: {msg}"

    # Verify output is readable before moving originals
    if not out_mp4.parent.exists():
        ensure_parent(out_mp4)

    # Place output in final location
    safe_replace(tmp_out, out_mp4)

    if not ffprobe_has_video_stream(out_mp4):
        # Output invalid; keep original in place
        try:
            out_mp4.unlink()
        except Exception:
            pass
        print(" ".join(cmd))
        return False, "output mp4 not readable (aborted)"

    # Move original media + xmp sidecars into archive tree
    try:
        move_to_archive(src_root, archive_root, media_path)
        for xmp in sidecar_xmp_candidates(media_path):
            # If xmp was already moved by previous step (rare), skip
            if xmp.exists():
                move_to_archive(src_root, archive_root, xmp)
    except Exception as e:
        return False, f"converted, but move-to-archive failed: {e!r}"

    return True, "ok"


def iter_media_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            files.append(p)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert AVI/VOB to MP4 (high quality) and archive originals in a parallel tree."
    )
    parser.add_argument("--src", required=True, type=Path, help="Source root directory to traverse")
    parser.add_argument("--archive", required=True, type=Path, help="Archive root directory (parallel tree)")
    parser.add_argument("--crf", type=int, default=16, help="x264 CRF (lower=better, larger files). Default 16")
    parser.add_argument("--preset", default="slow", help="x264 preset (slower=smaller). Default slow")
    parser.add_argument("--audio-bitrate", default="320k", help="AAC audio bitrate. Default 320k")
    parser.add_argument("--no-deinterlace-vob", action="store_true", help="Do not apply yadif to VOB files")
    parser.add_argument("--overwrite-mp4", action="store_true", help="Overwrite existing .mp4 outputs")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen, but do nothing")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N files (0 = no limit)")
    parser.add_argument("--log", type=Path, default=Path("/tmp/convert.log"),
                        help="Path to log file (default: /tmp/convert.log)")
    parser.add_argument("--verbose", action="store_true",
                        help="Verbose console output")
    args = parser.parse_args()

    src_root: Path = args.src.resolve()
    archive_root: Path = args.archive.resolve()
    setup_logging(args.log, args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=== Conversion run started ===")
    logger.info(f"Source root   : {src_root}")
    logger.info(f"Archive root  : {archive_root}")
    logger.info(f"CRF={args.crf}, preset={args.preset}, audio={args.audio_bitrate}")
    if args.dry_run:
        logger.info("DRY RUN enabled")

    if not src_root.exists() or not src_root.is_dir():
        logger.error(f"ERROR: --src is not a directory: {src_root}", file=sys.stderr)
        return 2

    which_or_die("ffmpeg")
    which_or_die("ffprobe")

    files = iter_media_files(src_root)
    files.sort()

    if args.limit and args.limit > 0:
        files = files[: args.limit]

    total = len(files)
    ok = 0
    skipped = 0
    failed = 0
    logger = logging.getLogger(__name__)
    logger.info(f"Found {total} file(s) under {src_root}")
    if args.dry_run:
        logger.info("DRY RUN mode: no files will be converted or moved.")

    for i, media in enumerate(files, start=1):
        rel = media.relative_to(src_root)
        logger.info(f"[{i}/{total}] Processing: {rel}")

        success, msg = convert_one(
            src_root,
            archive_root,
            media,
            crf=args.crf,
            preset=args.preset,
            audio_bitrate=args.audio_bitrate,
            deinterlace_vob=not args.no_deinterlace_vob,
            overwrite_mp4=args.overwrite_mp4,
            dry_run=args.dry_run,
        )

        if success and msg == "dry-run":
            ok += 1
            continue

        if success:
            ok += 1
            logger.info("  ✓ converted + archived")
        else:
            # Treat "mp4 exists (skip)" as skipped rather than failed
            if msg.startswith("mp4 exists (skip)"):
                skipped += 1
                logger.info(f"  ↷ {msg}")
            else:
                failed += 1
                logger.info(f"  ✗ {msg}")
            exit(-1)

    logger.info("\nSummary:")
    logger.info(f"  converted: {ok}")
    logger.info(f"  skipped:   {skipped}")
    logger.info(f"  failed:    {failed}")
    logger.info(f"Archive root: {archive_root}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
