"""Load config.toml, filling any missing key with a default."""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path

DEFAULTS: dict = {
    "campaign": {
        "name": "Campaign",
        "allowed_platforms": ["tiktok", "instagram", "youtube"],
        "campaign_start": "",
        "required_tags": [],
        "min_duration_sec": 5,
        "max_duration_sec": 180,
        "min_views": 0,
    },
    "fraud": {
        "check_above_views": 10000,
        "min_like_rate": 0.003,
        "zero_comment_views": 50000,
        "same_video_distance": 10,
    },
    "enforcement": {
        "ban_at_points": 3,
        "points": {
            "stolen_clip": 3,
            "account_not_yours": 3,
            "botted_views": 2,
            "missing_tags": 1,
            "posted_before_start": 1,
            "too_short": 1,
            "too_long": 1,
            "platform_not_allowed": 1,
            "below_min_views": 0,
            "duplicate": 0,
            "unavailable": 0,
        },
    },
    "scoring": {
        "min_score": 55,
        "top_n": 10,
        "target_views": 1_000_000,
        "ideal_duration": [12, 60],
    },
    "download": {"workers": 4, "cookies_from_browser": "", "cookies_file": ""},
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: str | Path | None) -> dict:
    if path is None or not Path(path).exists():
        return copy.deepcopy(DEFAULTS)
    with open(path, "rb") as f:
        return _merge(DEFAULTS, tomllib.load(f))
