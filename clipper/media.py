"""ffprobe helpers."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


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
    for sd in v.get("side_data_list", []) or []:  # phones store portrait as landscape + rotation
        if abs(int(sd.get("rotation", 0) or 0)) in (90, 270) and width and height:
            width, height = height, width
    try:
        duration = float(data.get("format", {}).get("duration") or v.get("duration") or 0)
    except ValueError:
        duration = 0.0
    return {"width": width, "height": height, "duration": duration, "has_audio": a}
