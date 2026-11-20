"""Small helpers."""
from __future__ import annotations

import re
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://[^\s<>\"'\]\[)(,|]+", re.I)

PLATFORM_HOSTS = {
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com", "instagr.am"),
    "youtube": ("youtube.com", "youtu.be"),
    "x": ("x.com", "twitter.com"),
    "facebook": ("facebook.com", "fb.watch"),
}


def platform_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for name, hosts in PLATFORM_HOSTS.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return name
    return "other"


def find_urls(text: str) -> list[str]:
    return list(dict.fromkeys(u.rstrip(".,;") for u in URL_RE.findall(text or "")))


def slug(s: str, n: int = 40) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:n].strip("-") or "campaign"
