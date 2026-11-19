"""ffprobe info and a perceptual fingerprint so re-uploads of the same video are
caught even when the link, account, caption and encoding differ."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

FRAME_POINTS = (0.08, 0.2, 0.32, 0.44, 0.56, 0.68, 0.8, 0.92)


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def probe(path: str | Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        return {}
    data = json.loads(out.stdout or "{}")
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    a = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    width, height = v.get("width"), v.get("height")
    # phones store portrait video as landscape + a rotation flag
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = abs(int(sd["rotation"]))
    if rot in (90, 270) and width and height:
        width, height = height, width
    try:
        duration = float(data.get("format", {}).get("duration") or v.get("duration") or 0)
    except ValueError:
        duration = 0.0
    return {"width": width, "height": height, "duration": duration, "has_audio": a}


def _frame_hash(path: Path, t: float) -> int | None:
    """128-bit difference hash: 64 bits of left/right gradients + 64 of up/down."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
         "-vf", "scale=9:9:flags=area,format=gray", "-f", "rawvideo", "-"],
        capture_output=True, timeout=60,
    )
    px = out.stdout
    if len(px) < 81:
        return None
    mean = sum(px[:81]) / 81
    if sum((p - mean) ** 2 for p in px[:81]) / 81 < 9:  # flat/black frame tells us nothing
        return None
    bits = 0
    for r in range(8):
        for c in range(8):
            bits = (bits << 1) | (px[r * 9 + c] > px[r * 9 + c + 1])
    for r in range(8):
        for c in range(8):
            bits = (bits << 1) | (px[r * 9 + c] > px[(r + 1) * 9 + c])
    if bin(bits).count("1") < 6:  # almost no structure (e.g. plain gradient): would match anything
        return None
    return bits


def fingerprint(path: str | Path, duration: float) -> list[int]:
    if not duration or duration <= 0:
        return []
    hashes = [_frame_hash(Path(path), duration * p) for p in FRAME_POINTS]
    return [h for h in hashes if h is not None]


def distance(a: list[int], b: list[int]) -> float:
    """Mean distance from each frame of the shorter clip to its closest frame in
    the other. Tolerates trims and different start points. 0 = identical, 64 = opposite."""
    if len(a) < 3 or len(b) < 3:
        return 64.0
    if len(a) > len(b):
        a, b = b, a
    # 128-bit hashes, reported on a 0-64 scale
    return sum(min(bin(x ^ y).count("1") for y in b) for x in a) / len(a) / 2


def export_clean(src: str | Path, dst: str | Path) -> None:
    """Copy without the source's metadata (uploader tags, encoder strings) so the
    file is clean to post. Falls back to a plain copy if ffmpeg can't remux it."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-map", "0", "-map_metadata", "-1",
         "-c", "copy", "-movflags", "+faststart", str(dst)],
        capture_output=True, timeout=300,
    )
    if r.returncode != 0 or not Path(dst).exists():
        shutil.copyfile(src, dst)
