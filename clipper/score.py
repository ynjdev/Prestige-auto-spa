"""0-100 quality score used to pick which approved clips are worth reposting."""
from __future__ import annotations

import math

WEIGHTS = {"views": 35, "engagement": 30, "duration": 10, "resolution": 10, "vertical": 10, "audio": 5}


def score(meta: dict, probe: dict, cfg: dict) -> tuple[float, dict]:
    s = cfg["scoring"]
    parts: dict[str, float] = {}

    views = meta.get("views")
    if views is None:
        parts["views"] = 0.5  # platform didn't expose it (common on Instagram)
    else:
        parts["views"] = min(1.0, math.log10(views + 1) / math.log10(max(10, s["target_views"])))

    if views:
        eng = sum(x or 0 for x in (meta.get("likes"), meta.get("comments"), meta.get("shares"))) / views
        parts["engagement"] = min(1.0, eng / 0.10)  # 10%+ engagement = full marks
    else:
        parts["engagement"] = 0.5

    dur = probe.get("duration") or meta.get("duration") or 0
    lo, hi = s["ideal_duration"]
    if lo <= dur <= hi:
        parts["duration"] = 1.0
    elif dur <= 0:
        parts["duration"] = 0.5
    else:
        gap = (lo - dur) if dur < lo else (dur - hi)
        parts["duration"] = max(0.0, 1 - gap / max(lo, 1))

    w = probe.get("width") or meta.get("width") or 0
    h = probe.get("height") or meta.get("height") or 0
    short_side = min(w, h) if w and h else 0
    parts["resolution"] = 1.0 if short_side >= 1080 else 0.7 if short_side >= 720 else 0.3 if short_side else 0.5
    parts["vertical"] = (1.0 if h > w * 1.5 else 0.5 if h > w else 0.0) if w and h else 0.5
    parts["audio"] = 1.0 if probe.get("has_audio", True) else 0.0

    total = sum(WEIGHTS[k] * v for k, v in parts.items())
    return round(total, 1), {k: round(v * WEIGHTS[k], 1) for k, v in parts.items()}
