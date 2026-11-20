"""Pick the best moments in a source video.

With Claude (ANTHROPIC_API_KEY set, or `ant auth login`): Claude reads the
timestamped transcript plus the brief and picks self-contained moments with a
strong hook. Without it: a simple heuristic (loud + talk-dense windows).
Either way, cuts are snapped to sentence boundaries.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from .transcribe import Segment


@dataclass
class Moment:
    start: float
    end: float
    title: str = ""
    hook: str = ""
    why: str = ""
    score: float = 0.0

    @property
    def length(self) -> float:
        return self.end - self.start


SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number", "description": "seconds"},
                    "end": {"type": "number", "description": "seconds"},
                    "title": {"type": "string", "description": "short internal name for the clip"},
                    "hook": {"type": "string", "description": "on-screen hook text / caption idea, under 12 words"},
                    "why": {"type": "string", "description": "one sentence: why this will perform"},
                    "score": {"type": "integer", "description": "0-100 predicted performance"},
                },
                "required": ["start", "end", "title", "hook", "why", "score"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}

SYSTEM = """You are a top short-form video editor who clips long videos for paid "content rewards" \
campaigns, where the clipper is paid per 1,000 views. You pick moments that will get the most views \
on TikTok, Reels and Shorts while following the brand's brief exactly.

A great moment:
- hooks in the first 2 seconds (a bold claim, a question, conflict, a surprising number, a punchline setup)
- is self-contained: makes sense with no context, has a payoff, doesn't end mid-thought
- has energy: emotion, laughter, a heated exchange, a story with a twist, a quotable line
- fits what the brief asks to promote, and breaks none of its rules

Use only the timestamps given in the transcript. Start a clip at the start of a line and end it at the \
end of a line. Never overlap two clips."""


def transcript_lines(segs: list[Segment]) -> str:
    return "\n".join(f"[{s.start:.1f}-{s.end:.1f}] {s.text}" for s in segs)


def pick_with_claude(segs: list[Segment], brief_text: str, title: str, n: int, min_sec: float, max_sec: float,
                     model: str = "claude-opus-5-5", client=None) -> list[Moment]:
    import anthropic

    client = client or anthropic.Anthropic()
    user = (
        f"<brief>\n{brief_text.strip()[:30000]}\n</brief>\n\n"
        f"<video title=\"{title}\">\n{transcript_lines(segs)}\n</video>\n\n"
        f"Pick the {n} best clips. Each must be between {min_sec:.0f} and {max_sec:.0f} seconds long. "
        f"Best first."
    )
    resp = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined to pick clips for this video")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    data = json.loads(text)
    return [Moment(float(c["start"]), float(c["end"]), c["title"], c["hook"], c["why"], float(c["score"]))
            for c in data["clips"]]


def pick_heuristic(segs: list[Segment], rms_per_sec: list[float], duration: float, n: int,
                   min_sec: float, max_sec: float) -> list[Moment]:
    """Windows where people talk a lot and loudly. Crude, but better than random."""
    target = max(min_sec, min(max_sec, (min_sec + max_sec) / 2))
    secs = int(duration)
    if secs <= 0:
        return []
    talk = [0.0] * (secs + 1)
    for s in segs:
        words = len(s.text.split())
        span = max(1, int(s.end) - int(s.start) + 1)
        for t in range(int(s.start), min(secs, int(s.end)) + 1):
            talk[t] += words / span
    loud = list(rms_per_sec[: secs + 1]) + [0.0] * max(0, secs + 1 - len(rms_per_sec))
    lmax = max(loud) or 1.0
    tmax = max(talk) or 1.0
    per_sec = [0.5 * loud[i] / lmax + 0.5 * talk[i] / tmax for i in range(secs + 1)]
    w = int(min(target, duration))
    if w <= 0:
        return []
    windows = sorted(((sum(per_sec[i:i + w]) / w, i) for i in range(0, max(1, secs - w + 1))), reverse=True)
    out: list[Moment] = []
    for val, i in windows:
        if all(i + w <= m.start or i >= m.end for m in out):
            out.append(Moment(float(i), float(i + w), "", "", "loud, talk-dense stretch",
                              round(val * 100)))
        if len(out) >= n:
            break
    return out


def rms_per_second(samples, sr: int = 16000) -> list[float]:
    import numpy as np

    n = len(samples) // sr
    if n == 0:
        return []
    a = samples[: n * sr].reshape(n, sr)
    return [float(x) for x in np.sqrt((a ** 2).mean(axis=1))]


def snap(m: Moment, segs: list[Segment], duration: float, min_sec: float, max_sec: float) -> Moment | None:
    """Move cuts to sentence boundaries, then make the length legal."""
    start, end = max(0.0, m.start), min(duration, m.end)
    if segs:
        starts = [s.start for s in segs if s.start <= start + 0.5]
        if starts:
            start = max(starts)
        ends = [s.end for s in segs if s.end >= end - 0.5]
        if ends:
            end = min(ends)
        # too long: drop whole sentences from the end while we can
        while end - start > max_sec:
            earlier = [s.end for s in segs if start + min_sec <= s.end < end]
            if not earlier:
                break
            end = max(earlier)
        # too short: add sentences to the end
        while end - start < min_sec:
            later = [s.end for s in segs if s.end > end]
            if not later or min(later) - start > max_sec:
                break
            end = min(later)
    start = max(0.0, start - 0.15)  # a breath of lead-in
    end = min(duration, end + 0.35)
    if end - start > max_sec:
        end = start + max_sec
    if end - start < min_sec:
        end = min(duration, start + min_sec)
    if end - start < min_sec * 0.9:
        return None
    return Moment(round(start, 2), round(end, 2), m.title, m.hook, m.why, m.score)


def no_overlap(ms: list[Moment], taken: list[tuple[float, float]]) -> list[Moment]:
    out: list[Moment] = []
    for m in ms:
        spans = taken + [(o.start, o.end) for o in out]
        if all(_overlap(m.start, m.end, a, b) < 0.3 * m.length for a, b in spans):
            out.append(m)
    return out


def _overlap(a1, a2, b1, b2) -> float:
    return max(0.0, min(a2, b2) - max(a1, b1))
