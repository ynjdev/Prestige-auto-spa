import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent))
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


def make_video(path: Path, src: str, w: int, h: int, dur: int):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{src}=size={w}x{h}:rate=30", "-t", str(dur),
         "-f", "lavfi", "-i", f"sine=frequency=330:duration={dur}", "-shortest",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)],
        check=True,
    )
    return path


@pytest.fixture(scope="session")
def landscape_video(tmp_path_factory):
    return make_video(tmp_path_factory.mktemp("v") / "podcast.mp4", "testsrc", 1280, 720, 150)


class FakeClaude:
    """Stands in for anthropic.Anthropic(): returns fixed clips and records the request."""

    def __init__(self, clips):
        self.clips, self.calls = clips, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps({"clips": self.clips}))])


@pytest.fixture
def fake_claude():
    return FakeClaude
