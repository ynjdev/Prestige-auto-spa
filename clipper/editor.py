"""Cut a moment into a vertical 1080x1920 clip ready to post."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .transcribe import Segment

W, H = 1080, 1920


def _vf(mode: str, src_w: int | None, src_h: int | None) -> str:
    if src_w and src_h and src_h / src_w >= 1.7:  # already vertical
        return f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1[v]"
    if mode == "crop":
        return f"[0:v]scale=-2:{H},crop={W}:{H},setsar=1[v]"
    # "blur": whole frame visible, blurred zoomed copy fills the background
    return (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:2[bg];"
            f"[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]")


def cut(src: str | Path, start: float, end: float, dst: str | Path, mode: str = "blur",
        src_w: int | None = None, src_h: int | None = None, has_audio: bool = True,
        subtitles: Path | None = None) -> None:
    vf = _vf(mode, src_w, src_h)
    if subtitles:
        p = str(subtitles).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        vf = vf[:-3] + f",subtitles='{p}':force_style='Fontsize=13,Bold=1,Outline=2,MarginV=70,Alignment=2'[v]"
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-i", str(src), "-t", f"{end - start:.2f}",
           "-filter_complex", vf, "-map", "[v]"]
    if has_audio:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
            "-map_metadata", "-1", "-movflags", "+faststart", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr.strip()[-400:]}")


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)) % 1000:03d}"


def write_srt(segs: list[Segment], start: float, end: float, dst: str | Path, max_words: int = 7) -> int:
    """Subtitles for the clip, timed from 0, split into short phone-friendly lines."""
    cues = []
    for s in segs:
        if s.end <= start or s.start >= end:
            continue
        words = s.text.split()
        if not words:
            continue
        a, b = max(s.start, start), min(s.end, end)
        chunks = [words[i:i + max_words] for i in range(0, len(words), max_words)]
        step = (b - a) / len(chunks)
        for i, ch in enumerate(chunks):
            cues.append((a + i * step - start, a + (i + 1) * step - start, " ".join(ch)))
    Path(dst).write_text("".join(f"{i}\n{_ts(a)} --> {_ts(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(cues, 1)),
                         encoding="utf-8")
    return len(cues)
