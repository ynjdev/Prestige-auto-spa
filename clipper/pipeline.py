"""One batch = one doc. Ingest -> enforce -> fetch -> verify -> score -> collect -> report."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import ingest, media, report, rules
from .db import DB
from .fetch import Fetched, YtDlpFetcher
from .ingest import Submission
from .score import score as score_clip
from .util import normalize_url


@dataclass
class Result:
    sub: Submission
    key: str
    decision: str = "pending"            # approve / reject / manual
    reasons: list[tuple[str, str]] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    probe: dict = field(default_factory=dict)
    file: Path | None = None
    fp: list[int] = field(default_factory=list)
    score: float | None = None
    score_parts: dict = field(default_factory=dict)
    banned_now: bool = False
    note: str = ""
    export: Path | None = None

    @property
    def whop_message(self) -> str:
        """Safe to paste to the clipper."""
        return " ".join(rules.message(c, d, for_clipper=True) for c, d in self.reasons)

    @property
    def evidence(self) -> str:
        """For you only: full detail including which clipper/link it matched."""
        return "; ".join(f"{c}: {d}" for c, d in self.reasons if d)


@dataclass
class Batch:
    name: str
    doc: Path
    out_dir: Path
    results: list[Result]
    ignored: list[str]
    new_bans: list[tuple[str, str]]
    ready: list[Result]


def run(doc: str | Path, cfg: dict, db: DB, out_root: str | Path, fetcher=None,
        batch_name: str | None = None, log=print, clip_dir: str | Path = "data/clips") -> Batch:
    doc = Path(doc)
    batch_name = batch_name or time.strftime("%Y-%m-%d_%H%M%S") + "_" + doc.stem[:40]
    out_dir = Path(out_root) / batch_name
    out_dir.mkdir(parents=True, exist_ok=True)
    fetcher = fetcher or YtDlpFetcher(
        clip_dir, cfg["download"]["cookies_from_browser"], cfg["download"]["cookies_file"],
    )
    points_cfg = cfg["enforcement"]["points"]
    ban_at = cfg["enforcement"]["ban_at_points"]

    subs, ignored = ingest.load(doc)
    log(f"[{batch_name}] {len(subs)} submissions found in {doc.name}"
        + (f" ({len(ignored)} non-video links ignored)" if ignored else ""))

    results = [Result(sub=s, key=normalize_url(s.url)) for s in subs]
    new_bans: list[tuple[str, str]] = []

    # ── 1. cheap checks before downloading anything ─────────────────────
    seen_keys: dict[str, Result] = {}
    for r in results:
        if db.is_banned(r.sub.submitter):
            r.reasons.append(("banned", ""))
        elif r.key in seen_keys:
            first = seen_keys[r.key]
            r.reasons.append(("duplicate" if first.sub.submitter == r.sub.submitter else "stolen_clip",
                              "same link earlier in this doc"))
        elif (prior := db.clip(r.key)) is not None:
            r.reasons.append(("duplicate" if prior["submitter"] == r.sub.submitter else "stolen_clip",
                              f"first submitted in batch {prior['batch']}"))
        else:
            r.reasons += rules.check_platform(r.sub.platform, cfg)
        seen_keys.setdefault(r.key, r)
        if r.reasons:
            r.decision = "reject"

    # ── 2. download the rest in parallel ────────────────────────────────
    todo = [r for r in results if r.decision == "pending"]
    log(f"[{batch_name}] downloading {len(todo)} clips...")
    with ThreadPoolExecutor(max(1, int(cfg["download"]["workers"]))) as pool:
        fetched: list[Fetched] = list(pool.map(lambda r: fetcher(r.sub.url, r.sub.platform), todo))
    for r, f in zip(todo, fetched):
        if f.error or not f.meta:
            r.decision, r.note = "manual", f"couldn't load: {f.error or 'no metadata'}"
            continue
        r.meta, r.file = f.meta, f.file
        if r.meta.get("views") is None and r.sub.doc_views is not None:
            r.meta["views"] = r.sub.doc_views

    # ── 3. full checks, in doc order so the FIRST submitter of a video wins ─
    batch_fps: list[tuple[str, str, list[int]]] = []
    batch_video_keys: dict[str, Result] = {}
    have_ff = media.have_ffmpeg()
    for r in todo:
        if r.decision != "pending":
            continue
        m, who = r.meta, r.sub.submitter
        if db.is_banned(who):  # banned earlier in this same batch
            r.reasons.append(("banned", ""))
        video_key = f"{m['platform']}:{m['id']}" if m.get("id") else None
        if not r.reasons and video_key:
            first = batch_video_keys.get(video_key)
            prior = db.clip_by_video(video_key)
            owner = first.sub.submitter if first else (prior["submitter"] if prior else None)
            if owner is not None:
                r.reasons.append(("duplicate" if owner == who else "stolen_clip", "same video, different link"))
            batch_video_keys.setdefault(video_key, r)
        r.meta["video_key"] = video_key

        if not r.reasons and m.get("account_id") and who != "unknown":
            owner = db.account_owner(m["platform"], m["account_id"])
            if owner and owner != who:
                r.reasons.append(("account_not_yours", f"@{m.get('account') or m['account_id']} belongs to {owner}"))
            elif not owner:
                db.claim_account(m["platform"], m["account_id"], who)

        if have_ff and r.file and r.file.exists():
            r.probe = media.probe(r.file)
            if r.probe.get("duration") and not m.get("duration"):
                m["duration"] = r.probe["duration"]
            r.fp = media.fingerprint(r.file, r.probe.get("duration") or m.get("duration") or 0)

        if not r.reasons:
            r.reasons += rules.check_meta(m, cfg)

        if not r.reasons and r.fp:
            thresh = cfg["fraud"]["same_video_distance"]
            for other, other_url, ofp in db.fingerprints() + batch_fps:
                if other != who and media.distance(r.fp, ofp) <= thresh:
                    r.reasons.append(("stolen_clip", f"matches {other_url} from {other}"))
                    break
        if r.fp and not _is_theft(r):
            batch_fps.append((who, r.sub.url, r.fp))

        r.decision = "reject" if r.reasons else "approve"
        if r.decision == "approve":
            r.score, r.score_parts = score_clip(m, r.probe, cfg)

    # ── 4. strikes and bans ─────────────────────────────────────────────
    for r in results:
        if r.decision != "reject":
            continue
        who = r.sub.submitter
        if who == "unknown" or db.is_banned(who):
            continue
        pts = sum(int(points_cfg.get(code, 1)) for code in {c for c, _ in r.reasons})
        total = db.add_points(who, pts, ",".join(c for c, _ in r.reasons), r.sub.url, batch_name)
        if pts and total >= ban_at:
            reason = "; ".join(rules.message(c, d) for c, d in r.reasons)
            db.ban(who, reason)
            r.banned_now = True
            new_bans.append((who, reason))
            log(f"[{batch_name}] BANNED {who}: {reason}")

    # a clipper banned in this batch gets all their other clips in it rejected
    banned_names = {n for n, _ in new_bans}
    for r in results:
        if r.sub.submitter in banned_names and r.decision == "approve":
            r.decision, r.reasons, r.score = "reject", [("banned", "")], None

    # ── 5. remember everything (manual ones get retried next time) ───────
    for r in results:
        if r.decision == "manual":
            continue
        if db.clip(r.key):
            continue  # never overwrite the first submitter's record
        db.save_clip(
            key=r.key, video_key=r.meta.get("video_key"), url=r.sub.url, submitter=r.sub.submitter,
            platform=r.sub.platform, account=r.meta.get("account_id"), decision=r.decision,
            reasons=[c for c, _ in r.reasons], score=r.score, views=r.meta.get("views"),
            fingerprint=(r.fp or None) if not _is_theft(r) else None, file=str(r.file) if r.file else None, batch=batch_name,
        )
    db.commit()

    # ── 6. collect the best clips ───────────────────────────────────────
    ready = collect(results, cfg, out_dir / "ready_to_post")
    batch = Batch(batch_name, doc, out_dir, results, ignored, new_bans, ready)
    report.write(batch, cfg)
    return batch


def _is_theft(r: Result) -> bool:
    # a thief's copy must never become the "original" that the real owner is matched against
    return any(c in ("stolen_clip", "account_not_yours", "banned") for c, _ in r.reasons)


def collect(results: list[Result], cfg: dict, dest: Path) -> list[Result]:
    s = cfg["scoring"]
    pool = sorted(
        (r for r in results if r.decision == "approve" and r.score is not None and r.score >= s["min_score"]
         and r.file and r.file.exists()),
        key=lambda r: r.score, reverse=True,
    )
    picked: list[Result] = []
    for r in pool:
        # the same clip cross-posted to TikTok + IG + YT only needs collecting once
        if r.fp and any(p.fp and media.distance(r.fp, p.fp) <= cfg["fraud"]["same_video_distance"] for p in picked):
            continue
        picked.append(r)
        if len(picked) >= s["top_n"]:
            break
    if picked:
        dest.mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(picked, 1):
        safe = "".join(ch if ch.isalnum() else "_" for ch in r.sub.submitter)[:24]
        out = dest / f"{i:02d}_{safe}_{int(r.score)}.mp4"
        if media.have_ffmpeg():
            media.export_clean(r.file, out)
        else:
            import shutil
            shutil.copyfile(r.file, out)
        r.export = out
    return picked

