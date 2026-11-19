"""Campaign rules. Each check returns (code, detail). The code maps to strike
points in config; the detail is the human message you paste into Whop."""
from __future__ import annotations

from datetime import datetime, timezone

MESSAGES = {
    "banned": "You are banned from this campaign.",
    "duplicate": "This video was already submitted.",
    "stolen_clip": "This video was already submitted by another clipper. Reuploads are not allowed.",
    "account_not_yours": "This account is registered to another clipper.",
    "platform_not_allowed": "This platform isn't accepted for this campaign.",
    "unavailable": "The video is private, deleted, or couldn't be loaded.",
    "too_short": "Clip is shorter than the minimum length.",
    "too_long": "Clip is longer than the maximum length.",
    "posted_before_start": "Posted before the campaign started.",
    "missing_tags": "Caption is missing required tags.",
    "below_min_views": "Below the minimum view count.",
    "botted_views": "View activity looks inorganic (engagement far below normal).",
}


# details for these name another clipper, so they stay in your evidence column
# and never go into the text you paste to the clipper
PRIVATE_DETAIL = {"stolen_clip", "account_not_yours"}


def message(code: str, detail: str = "", for_clipper: bool = False) -> str:
    base = MESSAGES.get(code, code)
    if for_clipper and code in PRIVATE_DETAIL:
        return base
    return f"{base} ({detail})" if detail else base


def _posted_at(meta: dict) -> datetime | None:
    if meta.get("posted_at"):
        return datetime.fromtimestamp(float(meta["posted_at"]), tz=timezone.utc)
    if meta.get("upload_date"):
        try:
            return datetime.strptime(str(meta["upload_date"]), "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def check_platform(platform: str, cfg: dict) -> list[tuple[str, str]]:
    allowed = [p.lower() for p in cfg["campaign"]["allowed_platforms"]]
    return [] if platform in allowed else [("platform_not_allowed", platform)]


def check_meta(meta: dict, cfg: dict) -> list[tuple[str, str]]:
    c = cfg["campaign"]
    out: list[tuple[str, str]] = []

    dur = meta.get("duration")
    if dur:
        if c["min_duration_sec"] and dur < c["min_duration_sec"]:
            out.append(("too_short", f"{dur:.0f}s < {c['min_duration_sec']}s"))
        if c["max_duration_sec"] and dur > c["max_duration_sec"]:
            out.append(("too_long", f"{dur:.0f}s > {c['max_duration_sec']}s"))

    if c.get("campaign_start"):
        start = datetime.strptime(c["campaign_start"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        posted = _posted_at(meta)
        if posted and posted < start:
            out.append(("posted_before_start", posted.strftime("%Y-%m-%d")))

    tags = [t.lower() for t in c.get("required_tags") or []]
    if tags:
        cap = (meta.get("caption") or "").lower()
        missing = [t for t in tags if t not in cap]
        if missing:
            out.append(("missing_tags", "missing " + ", ".join(missing)))

    views = meta.get("views")
    if c.get("min_views") and views is not None and views < c["min_views"]:
        out.append(("below_min_views", f"{views:,} < {c['min_views']:,}"))

    out += check_fraud(meta, cfg)
    return out


def check_fraud(meta: dict, cfg: dict) -> list[tuple[str, str]]:
    f = cfg["fraud"]
    views, likes, comments = meta.get("views"), meta.get("likes"), meta.get("comments")
    if not views or views < f["check_above_views"]:
        return []
    if likes is not None:
        rate = likes / views
        if rate < f["min_like_rate"]:
            return [("botted_views", f"{views:,} views but {likes:,} likes = {rate:.2%} like rate")]
    if comments == 0 and f.get("zero_comment_views") and views >= f["zero_comment_views"]:
        return [("botted_views", f"{views:,} views and zero comments")]
    return []
