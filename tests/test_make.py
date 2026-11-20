import csv

from clipper import config, media, moments
from clipper import make as M
from clipper.db import DB
from clipper.transcribe import Segment

# fake transcript for a 150s video: a sentence every 5 seconds
SEGS = [Segment(float(t), float(t + 4.6), f"sentence number {t // 5} with some words in it") for t in range(0, 150, 5)]


def _cfg():
    c = config.load(None)
    c["clips"]["per_campaign"] = 3
    return c


def _brief(tmp_path, video):
    p = tmp_path / "brief.txt"
    p.write_text("Clips must be 15-30 seconds\nInclude #ad and @brand\nNo AI voices\n")
    return p


def test_make_with_claude(tmp_path, landscape_video, fake_claude):
    fc = fake_claude([
        {"start": 10.2, "end": 33.0, "title": "Big reveal", "hook": "He did WHAT?", "why": "surprise", "score": 90},
        {"start": 60.0, "end": 82.0, "title": "Second", "hook": "Wait for it", "why": "payoff", "score": 80},
        {"start": 61.0, "end": 80.0, "title": "Overlaps second", "hook": "", "why": "", "score": 70},
        {"start": 100.0, "end": 140.0, "title": "Too long", "hook": "", "why": "", "score": 60},
    ])
    db = DB(tmp_path / "c.db")
    res = M.run(str(_brief(tmp_path, landscape_video)), _cfg(), db, tmp_path / "out", tmp_path / "data", [str(landscape_video)],
                name="Test Campaign", log=lambda *_: None, transcriber=lambda f: SEGS, claude_client=fc)
    assert res.picker == "Claude" and not res.problems
    assert [c.moment.title for c in res.clips] == ["Big reveal", "Second", "Too long"]
    req = fc.calls[0]
    assert req["model"] == "claude-opus-5-5" and req["output_config"]["format"]["type"] == "json_schema"
    assert "No AI voices" in req["messages"][0]["content"] and "between 15 and 30 seconds" in req["messages"][0]["content"]
    for c in res.clips:
        info = media.probe(c.file)
        assert (info["width"], info["height"]) == (1080, 1920) and info["has_audio"]
        assert 15 * 0.9 <= info["duration"] <= 30.5, (c.moment, info)
        assert c.srt.read_text().startswith("1\n00:00:00")
    # starts snapped to the start of a sentence (minus a short lead-in)
    assert res.clips[0].moment.start == 9.85
    rows = list(csv.DictReader(open(res.out_dir / "ready_to_post" / "captions.csv")))
    assert rows[0]["required_tags"] == "#ad @brand" and rows[0]["hook_idea"] == "He did WHAT?"
    assert (res.out_dir / "clips.html").read_text().count("<video") == 3

    # second run on the same brief: the same moments are never clipped twice
    res2 = M.run(str(_brief(tmp_path, landscape_video)), _cfg(), db, tmp_path / "out", tmp_path / "data", [str(landscape_video)],
                 name="Test Campaign", log=lambda *_: None, transcriber=lambda f: SEGS, claude_client=fc)
    assert res2.clips == []


def test_make_heuristic_without_claude(tmp_path, landscape_video):
    cfg = _cfg()
    cfg["ai"]["use_claude"] = False
    res = M.run(str(_brief(tmp_path, landscape_video)), cfg, DB(tmp_path / "c.db"), tmp_path / "out",
                tmp_path / "data", [str(landscape_video)], log=lambda *_: None, transcriber=lambda f: SEGS)
    assert res.picker == "heuristic" and len(res.clips) == 3
    spans = sorted((c.moment.start, c.moment.end) for c in res.clips)
    assert all(a[1] <= b[0] + 0.5 for a, b in zip(spans, spans[1:]))  # no overlaps


def test_snap_respects_limits():
    m = moments.snap(moments.Moment(12.0, 70.0), SEGS, 150, 15, 30)
    assert 15 <= m.length <= 30 and m.start == 9.85
    assert moments.snap(moments.Moment(148.0, 150.0), SEGS, 150, 15, 30) is None
