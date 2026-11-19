import csv

from clipper import config, media
from clipper.db import DB
from clipper.pipeline import run

T = "https://www.tiktok.com"


def _cfg():
    c = config.load(None)
    c["campaign"]["required_tags"] = []
    c["scoring"]["min_score"] = 40
    return c


def _good(acct, views=200_000, likes=18_000, comments=600, **kw):
    return {"account_id": acct, "account": acct, "views": views, "likes": likes, "comments": comments, "shares": 900, **kw}


def test_fingerprint_matches_reupload_not_other_videos(videos):
    fp = {k: media.fingerprint(p, media.probe(p)["duration"]) for k, p in videos.items()}
    assert all(len(v) >= 3 for v in fp.values()), fp
    assert media.distance(fp["A"], fp["A_copy"]) <= 10
    for other in ("B", "C", "D", "E", "F"):
        assert media.distance(fp["A"], fp[other]) > 10, other


def test_full_batch_then_followup(tmp_path, videos, fake_fetcher):
    doc = tmp_path / "week1.csv"
    rows = [
        ("alice", f"{T}/@alice/video/1"),            # good -> approve + ready
        ("bob", f"{T}/@bob/video/2"),                # reupload of alice's video -> stolen -> ban
        ("bob", f"{T}/@bob/video/3"),                # bob's legit clip -> flipped to reject because bob got banned
        ("carol", f"{T}/@carol/video/4"),            # botted -> reject, 2 pts
        ("alice", f"{T}/@alice/video/1?lang=en"),    # same link again -> duplicate
        ("dave", f"{T}/@alice/video/5"),             # alice's account -> account_not_yours -> ban
        ("erin", "https://x.com/erin/status/6"),     # platform not allowed -> 1 pt
        ("frank", f"{T}/@frank/video/7"),            # can't load -> manual
        ("gina", f"{T}/@gina/video/8"),              # good -> approve
        ("hank", f"{T}/@hank/video/9"),              # good but too long -> reject
    ]
    with open(doc, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Username", "Link"])
        w.writerows(rows)
    f = fake_fetcher({
        f"{T}/@alice/video/1": (_good("alice"), videos["A"]),
        f"{T}/@bob/video/2": (_good("bob", views=90_000, likes=7_000), videos["A_copy"]),
        f"{T}/@bob/video/3": (_good("bob"), videos["B"]),
        f"{T}/@carol/video/4": (_good("carol", views=120_000, likes=40, comments=0), videos["C"]),
        f"{T}/@alice/video/5": (_good("alice"), videos["D"]),
        f"{T}/@frank/video/7": "HTTP Error 403: Forbidden",
        f"{T}/@gina/video/8": (_good("gina", views=40_000, likes=3_000), videos["D"]),
        f"{T}/@hank/video/9": (_good("hank", duration=400), videos["E"]),
    })
    db = DB(tmp_path / "data" / "c.db")
    b = run(doc, _cfg(), db, tmp_path / "out", fetcher=f, batch_name="w1", log=lambda *_: None)

    got = {(r.sub.submitter, r.sub.url): (r.decision, [c for c, _ in r.reasons]) for r in b.results}
    assert got[("alice", f"{T}/@alice/video/1")] == ("approve", [])
    assert got[("bob", f"{T}/@bob/video/2")] == ("reject", ["stolen_clip"])
    assert got[("bob", f"{T}/@bob/video/3")] == ("reject", ["banned"])
    assert got[("carol", f"{T}/@carol/video/4")] == ("reject", ["botted_views"])
    assert got[("alice", f"{T}/@alice/video/1?lang=en")] == ("reject", ["duplicate"])
    assert got[("dave", f"{T}/@alice/video/5")] == ("reject", ["account_not_yours"])
    assert got[("erin", "https://x.com/erin/status/6")] == ("reject", ["platform_not_allowed"])
    assert got[("frank", f"{T}/@frank/video/7")][0] == "manual"
    assert got[("gina", f"{T}/@gina/video/8")] == ("approve", [])
    assert got[("hank", f"{T}/@hank/video/9")] == ("reject", ["too_long"])

    # duplicates and x.com links are never downloaded
    assert f"{T}/@alice/video/1?lang=en" not in f.calls and "https://x.com/erin/status/6" not in f.calls

    assert sorted(n for n, _ in b.new_bans) == ["bob", "dave"]
    assert db.is_banned("bob") and db.is_banned("dave") and not db.is_banned("carol")
    assert db.clipper("carol")["points"] == 2 and db.clipper("erin")["points"] == 1

    # ready_to_post: alice (A) and gina (D), best first, real playable files
    assert [r.sub.submitter for r in b.ready] == ["alice", "gina"]
    for r in b.ready:
        assert r.export.exists() and media.probe(r.export)["duration"] > 5
    assert (b.out_dir / "report.html").read_text().count("<video") == 2
    actions = list(csv.DictReader(open(b.out_dir / "whop_actions.csv")))
    assert {a["action"] for a in actions} == {"APPROVE", "REJECT", "MANUAL"}
    assert "bob" in (b.out_dir / "bans.txt").read_text()
    caps = list(csv.DictReader(open(b.out_dir / "ready_to_post" / "captions.csv")))
    assert [c["clipper"] for c in caps] == ["alice", "gina"] and caps[0]["your_caption"] == ""

    # ── week 2: memory across batches ────────────────────────────────────
    doc2 = tmp_path / "week2.txt"
    doc2.write_text(
        f"alice {T}/@alice/video/1\n"          # resubmitting last week's clip
        f"bob {T}/@bob/video/20\n"             # banned
        f"carol {T}/@carol/video/21\n"         # botted again -> 4 pts -> ban
        f"frank {T}/@frank/video/7\n"          # retried; loads now
        f"ivan {T}/@ivan/video/22\n"           # reupload of gina's approved clip from last week
    )
    f2 = fake_fetcher({
        f"{T}/@carol/video/21": (_good("carol", views=300_000, likes=100), videos["E"]),
        f"{T}/@frank/video/7": (_good("frank"), videos["F"]),
        f"{T}/@ivan/video/22": (_good("ivan"), videos["D"]),
    })
    b2 = run(doc2, _cfg(), db, tmp_path / "out", fetcher=f2, batch_name="w2", log=lambda *_: None)
    got2 = {r.sub.submitter: (r.decision, [c for c, _ in r.reasons]) for r in b2.results}
    assert got2["alice"] == ("reject", ["duplicate"])
    assert got2["bob"] == ("reject", ["banned"])
    assert got2["carol"] == ("reject", ["botted_views"]) and db.is_banned("carol")
    assert got2["frank"] == ("approve", [])
    assert got2["ivan"] == ("reject", ["stolen_clip"])
    assert f2.calls == [f"{T}/@carol/video/21", f"{T}/@frank/video/7", f"{T}/@ivan/video/22"]


def test_required_tags_and_campaign_start(tmp_path, videos, fake_fetcher):
    cfg = _cfg()
    cfg["campaign"]["required_tags"] = ["#brand"]
    cfg["campaign"]["campaign_start"] = "2026-11-01"
    doc = tmp_path / "d.txt"
    doc.write_text(f"a {T}/@a/video/1\nb {T}/@b/video/2\nc {T}/@c/video/3\n")
    f = fake_fetcher({
        f"{T}/@a/video/1": (_good("a", caption="love this #Brand", upload_date="20261105"), videos["A"]),
        f"{T}/@b/video/2": (_good("b", caption="no tag", upload_date="20261105"), videos["B"]),
        f"{T}/@c/video/3": (_good("c", caption="#brand", upload_date="20261020"), videos["C"]),
    })
    b = run(doc, cfg, DB(tmp_path / "c.db"), tmp_path / "out", fetcher=f, batch_name="t", log=lambda *_: None)
    got = {r.sub.submitter: [c for c, _ in r.reasons] for r in b.results}
    assert got == {"a": [], "b": ["missing_tags"], "c": ["posted_before_start"]}
