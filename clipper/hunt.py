"""Turn whatever campaign links you send into a ranked, profit-first list."""
from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict
from pathlib import Path

from . import campaigns as C
from . import report
from .browser import same_site_links
from .util import find_urls


def _inputs(items: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """-> (urls to open, [(pasted page text, url)])"""
    urls, pasted = [], []
    for it in items:
        p = Path(it).expanduser()
        if it.startswith("http"):
            urls.append(it)
        elif p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
            found = find_urls(text)
            leftover = text
            for u in found:
                leftover = leftover.replace(u, "")
            if found and len(leftover.strip()) < 20 * len(found):  # basically a list of links
                urls += found
            else:  # pasted campaign page text (Ctrl+A, Ctrl+C on the page)
                pasted.append((text, next((u for u in found if "whop.com" in u), str(p))))
        else:
            raise SystemExit(f"not a link or file: {it}")
    return list(dict.fromkeys(urls)), pasted


def gather(items: list[str], cfg: dict, browser_factory, log=print) -> list[C.Campaign]:
    urls, pasted = _inputs(items)
    found = [C.parse_text(text, url=u) for text, u in pasted]
    if not urls:
        return found
    b = browser_factory()
    try:
        for url in urls:
            try:
                page = b.read(url)
            except Exception as e:
                log(f"  ! couldn't open {url}: {str(e).splitlines()[0][:160]}")
                continue
            c = C.parse_text(page["text"], url=page["url"], title=page["title"], links=page["links"])
            if c.parsed_ok:
                log(f"  ✓ {c.title[:60]}")
                found.append(c)
                continue
            # not a campaign page: treat it as a list of campaigns (e.g. the Discover page)
            links = same_site_links(page)[: cfg["campaigns"]["max_links_from_listing"]]
            log(f"  {url} isn't a single campaign; checking {len(links)} links on it...")
            for sub in links:
                try:
                    sp = b.read(sub, wait_ms=1200)
                except Exception:
                    continue
                sc = C.parse_text(sp["text"], url=sp["url"], title=sp["title"], links=sp["links"])
                if sc.parsed_ok:
                    log(f"  ✓ {sc.title[:60]}")
                    found.append(sc)
    finally:
        b.close()
    return found


def _unique(p: Path) -> Path:
    n, q = 1, p
    while q.exists():
        n += 1
        q = p.with_name(f"{p.name}-{n}")
    q.mkdir(parents=True)
    return q


def run(items: list[str], cfg: dict, db, out_root: str | Path, browser_factory, log=print):
    log("reading campaigns...")
    found = gather(items, cfg, browser_factory, log)
    now = time.time()
    for c in found:
        c.checked_at = now
        db.save_campaign(c.url, c.to_dict())
    # one board: everything you've sent recently, refreshed when you send it again
    fresh = {c.url for c in found}
    keep = cfg["campaigns"]["keep_hours"]
    older = [C.Campaign.from_dict(d) for d in db.campaigns(keep) if d["url"] not in fresh] if keep else []
    verdicts = C.rank(found + older, cfg)
    out = _unique(Path(out_root) / "campaigns" / time.strftime("%Y-%m-%d_%H%M%S"))
    with open(out / "campaigns.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "campaign", "url", "avg $ per clip", "$ per day", "best $/1K", "views to min payout",
                    "share of clips paid",
                    "budget left", "budget days left", "platforms", "skip because"])
        for i, v in enumerate(verdicts, 1):
            c = v.campaign
            w.writerow([i if not v.skip else "", c.title, c.url, v.per_clip, v.per_day, v.best_rate,
                        "" if v.easiest_min_views == float("inf") else round(v.easiest_min_views), v.chance_paid,
                        c.budget_left, v.budget_days_left, " ".join(v.platforms), "; ".join(v.skip)])
    (out / "campaigns.json").write_text(json.dumps([{**asdict(v), "campaign": v.campaign.to_dict()} for v in verdicts],
                                                   default=str, indent=1))
    (out / "campaigns.html").write_text(report.campaigns_html(verdicts, cfg), encoding="utf-8")
    return verdicts, out
