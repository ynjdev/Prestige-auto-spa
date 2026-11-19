import subprocess
from pathlib import Path

import pytest

from clipper.fetch import Fetched


def _make(path: Path, src: str, w: int, h: int, dur: int, extra: list[str] | None = None):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{src}=size={w}x{h}:rate=30", "-t", str(dur),
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", "-shortest",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", *(extra or []), str(path)],
        check=True,
    )
    return path


@pytest.fixture(scope="session")
def videos(tmp_path_factory):
    d = tmp_path_factory.mktemp("vids")
    v = {
        "A": _make(d / "a.mp4", "testsrc", 1080, 1920, 20),
        "B": _make(d / "b.mp4", "mandelbrot", 540, 960, 25),
        "C": _make(d / "c.mp4", "testsrc2", 720, 1280, 30),
        "D": _make(d / "d.mp4", "rgbtestsrc", 540, 960, 15),
        "E": _make(d / "e.mp4", "gradients", 540, 960, 40),
        "F": _make(d / "f.mp4", "smptehdbars", 540, 960, 20),
    }
    # A, re-encoded smaller and trimmed: what a reupload thief posts
    v["A_copy"] = d / "a_copy.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(v["A"]), "-vf", "scale=720:1280",
                    "-c:v", "libx264", "-crf", "32", "-preset", "ultrafast", "-c:a", "aac", str(v["A_copy"])],
                   check=True)
    return v


class FakeFetcher:
    """Stands in for yt-dlp: url -> (meta overrides, video file) or an error string."""

    def __init__(self, table: dict):
        self.table = table
        self.calls: list[str] = []

    def __call__(self, url, platform):
        self.calls.append(url)
        entry = self.table.get(url)
        if entry is None or isinstance(entry, str):
            return Fetched(error=entry or "not found")
        meta, file = entry
        base = {"id": url.rstrip("/").split("/")[-1], "platform": platform, "account_id": "", "account": "",
                "views": None, "likes": None, "comments": None, "shares": None, "followers": None,
                "duration": None, "width": None, "height": None, "posted_at": None, "upload_date": None,
                "caption": "", "webpage_url": url}
        base.update(meta)
        return Fetched(meta=base, file=Path(file))


@pytest.fixture
def fake_fetcher():
    return FakeFetcher
