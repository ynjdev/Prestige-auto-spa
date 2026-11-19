"""Pull metadata + the video file for a submitted link using yt-dlp."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Fetched:
    meta: dict | None = None
    file: Path | None = None
    error: str | None = None


def _norm_meta(info: dict, platform: str) -> dict:
    def first(*keys):
        for k in keys:
            v = info.get(k)
            if v not in (None, ""):
                return v
        return None

    caption = " ".join(str(x) for x in (info.get("title"), info.get("description")) if x)
    tags = info.get("tags") or []
    if tags:
        caption += " " + " ".join("#" + t.lstrip("#") for t in tags)
    return {
        "id": str(first("id", "display_id") or ""),
        "platform": platform,
        "account_id": str(first("uploader_id", "channel_id", "uploader") or "").lower(),
        "account": str(first("uploader", "channel", "uploader_id") or ""),
        "views": first("view_count", "play_count"),
        "likes": info.get("like_count"),
        "comments": info.get("comment_count"),
        "shares": info.get("repost_count"),
        "followers": first("channel_follower_count", "uploader_follower_count"),
        "duration": info.get("duration"),
        "width": info.get("width"),
        "height": info.get("height"),
        "posted_at": first("timestamp", "release_timestamp"),
        "upload_date": info.get("upload_date"),
        "caption": caption,
        "webpage_url": info.get("webpage_url") or info.get("original_url"),
    }


class YtDlpFetcher:
    def __init__(self, clip_dir: str | Path, cookies_from_browser: str = "", cookies_file: str = ""):
        self.clip_dir = Path(clip_dir)
        self.clip_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_from_browser = cookies_from_browser
        self.cookies_file = cookies_file

    def __call__(self, url: str, platform: str) -> Fetched:
        try:
            import yt_dlp
        except ImportError:
            return Fetched(error="yt-dlp is not installed (pip install yt-dlp)")
        stem = hashlib.sha1(url.encode()).hexdigest()[:16]
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "outtmpl": str(self.clip_dir / f"{stem}.%(ext)s"),
            # prefer h264 mp4 so the file plays everywhere and posts cleanly
            "format": "bv*[vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
            "merge_output_format": "mp4",
            "retries": 3,
            "socket_timeout": 30,
        }
        if self.cookies_from_browser:
            opts["cookiesfrombrowser"] = (self.cookies_from_browser,)
        if self.cookies_file:
            opts["cookiefile"] = self.cookies_file
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as e:  # yt-dlp raises many types; we only need the message
            msg = str(e).replace("\n", " ")
            return Fetched(error=msg[:300])
        if info is None:
            return Fetched(error="no video found at link")
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                return Fetched(error="link is a playlist/profile with no video")
            info = entries[0]
        files = sorted(self.clip_dir.glob(stem + ".*"), key=lambda p: p.stat().st_size, reverse=True)
        files = [f for f in files if f.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv")]
        return Fetched(meta=_norm_meta(info, platform), file=files[0] if files else None)
