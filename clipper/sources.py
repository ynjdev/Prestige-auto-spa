"""Download the brand's source videos (YouTube, Drive, Twitch VODs, ...) with yt-dlp."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


@dataclass
class Source:
    key: str
    url: str
    file: Path
    title: str


def download(url_or_path: str, dest: str | Path, cookies_from_browser: str = "", cookies_file: str = "",
             max_items: int = 10, log=print) -> list[Source]:
    p = Path(url_or_path).expanduser()
    if p.exists():
        files = [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.suffix.lower() in VIDEO_EXT)
        return [Source(key=f"file:{f.resolve()}", url=str(f), file=f, title=f.stem) for f in files[:max_items]]

    import yt_dlp

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    opts = {
        "quiet": True, "no_warnings": True,
        "outtmpl": str(dest / "%(extractor)s_%(id)s.%(ext)s"),
        "format": "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4", "retries": 3, "playlistend": max_items,
    }
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if cookies_file:
        opts["cookiefile"] = cookies_file
    log(f"downloading {url_or_path} ...")
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url_or_path, download=True)
        entries = [e for e in (info.get("entries") or [info]) if e] if info else []
        out = []
        for e in entries:
            stem = Path(ydl.prepare_filename(e)).stem
            files = [f for f in dest.glob(stem + ".*") if f.suffix.lower() in VIDEO_EXT]
            if files:
                key = f"{e.get('extractor_key', 'web')}:{e.get('id') or hashlib.sha1(url_or_path.encode()).hexdigest()[:12]}"
                out.append(Source(key=key, url=e.get("webpage_url") or url_or_path, file=files[0],
                                  title=e.get("title") or stem))
    return out
