"""Load config.toml, filling any missing key with a default."""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path

DEFAULTS: dict = {
    "you": {
        "platforms": ["tiktok", "instagram", "youtube"],
        "typical_views": 3000,
        "clips_per_day": 10,
        "cross_post": True,
        "views_spread": 1.0,
    },
    "campaigns": {
        "min_rate_per_1k": 0.5,
        "min_budget_left": 300,
        "min_chance_paid": 0.4,
        "comfortable_budget": 2000,
        "comfortable_days": 7,
        "skip_not_accepting": True,
        "max_links_from_listing": 40,
        "keep_hours": 24,
    },
    "clips": {
        "per_campaign": 10,
        "min_sec": 15,
        "max_sec": 60,
        "reframe": "blur",
        "burn_subtitles": False,
    },
    "ai": {"use_claude": True, "model": "claude-opus-5-5", "whisper": "base.en", "threads": 4},
    "download": {"cookies_from_browser": "", "cookies_file": "", "max_videos_per_link": 10},
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(path: str | Path | None) -> dict:
    if path is None or not Path(path).exists():
        return copy.deepcopy(DEFAULTS)
    with open(path, "rb") as f:
        return _merge(DEFAULTS, tomllib.load(f))
