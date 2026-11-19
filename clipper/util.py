"""URL / name normalisation helpers."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

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


def normalize_url(url: str) -> str:
    """Canonical form used to detect the same link submitted twice."""
    url = url.strip().rstrip(".,;")
    p = urlparse(url)
    host = (p.hostname or "").lower()
    for prefix in ("www.", "m.", "mobile."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    path = re.sub(r"/+$", "", p.path)
    if host in ("youtube.com",) and path == "/watch":
        vid = parse_qs(p.query).get("v", [""])[0]
        return f"youtube.com/shorts/{vid}"
    if host == "youtu.be":
        return f"youtube.com/shorts{path}"
    if host == "youtube.com" and path.startswith("/shorts/"):
        return f"youtube.com{path}"
    # instagram /reels/ and /reel/ and /p/ point at the same media id
    if host == "instagram.com":
        m = re.search(r"/(?:reels?|p|tv)/([A-Za-z0-9_-]+)", path)
        if m:
            return f"instagram.com/reel/{m.group(1)}"
    return f"{host}{path}"


def find_urls(text: str) -> list[str]:
    return [u.rstrip(".,;") for u in URL_RE.findall(text or "")]


def clean_name(name: str | None) -> str:
    name = (name or "").strip().lstrip("@").strip()
    return re.sub(r"\s+", " ", name).lower()
