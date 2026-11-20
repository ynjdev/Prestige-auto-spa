"""Brief in -> ready-to-post clips out."""
from __future__ import annotations

import csv
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import brief as B
from . import editor, media, moments, report, sources, transcribe
from .util import slug


@dataclass
class Clip:
    file: Path
    srt: Path
    moment: moments.Moment
    source_title: str
    source_url: str


@dataclass
class Result:
    name: str
    out_dir: Path
    brief: B.Brief
    min_sec: float
    max_sec: float
    clips: list[Clip] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    picker: str = ""
    campaign: dict | None = None


def _claude_ok() -> bool:
    import importlib.util
    import os
    import shutil

    if importlib.util.find_spec("anthropic") is None:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or shutil.which("ant"))


def run(brief_src: str, cfg: dict, db, out_root: str | Path, data_dir: str | Path, extra_sources=(),
        count: int | None = None, name: str | None = None, browser_factory=None, log=print,
        transcriber=None, claude_client=None) -> Result:
    data_dir = Path(data_dir)
    text = B.load_text(brief_src, browser_factory)
    br = B.parse(text)
    ccfg = cfg["clips"]
    min_sec = br.min_sec or ccfg["min_sec"]
    max_sec = br.max_sec or ccfg["max_sec"]
    if min_sec >= max_sec:
        min_sec, max_sec = min(min_sec, max_sec) * 0.8, max(min_sec, max_sec)
    count = count or ccfg["per_campaign"]

    campaign = None
    known = {c["url"]: c for c in db.campaigns()}
    for u in br.whop_links:
        if u in known:
            campaign = known[u]
    name = name or (campaign or {}).get("title") or (Path(brief_src).stem if not str(brief_src).startswith("http") else "campaign")
    from .hunt import _unique

    out = _unique(Path(out_root) / slug(name) / time.strftime("%Y-%m-%d_%H%M%S"))
    ready = out / "ready_to_post"
    ready.mkdir(parents=True, exist_ok=True)
    res = Result(name, out, br, min_sec, max_sec, campaign=campaign)

    links = list(dict.fromkeys(list(br.sources) + list(extra_sources)))
    if not links:
        raise SystemExit("No source videos found in the brief. Add them with --source <link or file>.")
    log(f"brief: {len(links)} source link(s), clips {min_sec:.0f}-{max_sec:.0f}s, "
        f"tags: {br.tags_line() or 'none found'}")

    srcs: list[sources.Source] = []
    for link in links:
        try:
            srcs += sources.download(link, data_dir / "sources", cfg["download"]["cookies_from_browser"],
                                     cfg["download"]["cookies_file"], cfg["download"]["max_videos_per_link"], log)
        except Exception as e:
            res.problems.append(f"couldn't download {link}: {str(e)[:200]}")
            log(f"  ! {res.problems[-1]}")
    if not srcs:
        report.write_clips(res)
        return res

    transcriber = transcriber or (lambda f: transcribe.transcribe(
        f, data_dir / "models", cfg["ai"]["whisper"], cfg["ai"]["threads"], log))
    use_claude = cfg["ai"]["use_claude"] and (claude_client is not None or _claude_ok())
    res.picker = "Claude" if use_claude else "heuristic"
    total = sum(max(1.0, media.probe(s.file).get("duration") or 0) for s in srcs)

    candidates: list[tuple[sources.Source, dict, list, moments.Moment]] = []
    for s in srcs:
        info = media.probe(s.file)
        dur = info.get("duration") or 0
        if dur < min_sec:
            res.problems.append(f"{s.title}: shorter than the minimum clip length")
            continue
        log(f"transcribing {s.title[:60]} ({dur / 60:.0f} min)...")
        segs = transcriber(s.file) if info.get("has_audio") else []
        want = max(2, math.ceil(count * dur / total) + 2)
        picked: list[moments.Moment] = []
        if use_claude and segs:
            try:
                picked = moments.pick_with_claude(segs, br.text, s.title, want, min_sec, max_sec,
                                                  cfg["ai"]["model"], claude_client)
            except Exception as e:
                res.problems.append(f"Claude couldn't pick moments for {s.title} ({str(e)[:150]}); used heuristic")
                log(f"  ! {res.problems[-1]}")
        if not picked:
            rms = moments.rms_per_second(transcribe.load_audio(s.file)) if info.get("has_audio") else []
            picked = moments.pick_heuristic(segs, rms, dur, want, min_sec, max_sec)
        snapped = [m2 for m in picked if (m2 := moments.snap(m, segs, dur, min_sec, max_sec))]
        for m in moments.no_overlap(snapped, db.used(s.key)):
            candidates.append((s, info, segs, m))

    candidates.sort(key=lambda c: c[3].score, reverse=True)
    for i, (s, info, segs, m) in enumerate(candidates[:count], 1):
        label = m.title or f"{s.title[:24]} {int(m.start // 60)}m{int(m.start % 60):02d}s"
        base = f"{i:02d}_{slug(label, 36)}"
        mp4, srt = ready / f"{base}.mp4", ready / f"{base}.srt"
        log(f"cutting {mp4.name} ({m.length:.0f}s)")
        editor.write_srt(segs, m.start, m.end, srt)
        try:
            editor.cut(s.file, m.start, m.end, mp4, ccfg["reframe"], info.get("width"), info.get("height"),
                       info.get("has_audio", True), srt if ccfg["burn_subtitles"] and srt.stat().st_size else None)
        except RuntimeError as e:
            res.problems.append(f"{base}: {e}")
            continue
        db.add_moment(s.key, m.start, m.end, name, str(mp4))
        res.clips.append(Clip(mp4, srt, m, s.title, s.url))

    with open(ready / "captions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "your_caption", "hook_idea", "required_tags", "length_sec", "source"])
        for c in res.clips:
            w.writerow([c.file.name, "", c.moment.hook, br.tags_line(), round(c.moment.length), c.source_url])
    report.write_clips(res)
    return res
