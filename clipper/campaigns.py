"""Read Whop Content Rewards campaign pages and rank them by what they'd pay YOU.

The ranking follows the checklist from the tutorial you sent:
  - pay per 1K views on the platforms you post to
  - a LOW minimum payout, so you don't need huge views just to get paid
  - plenty of budget left (and how fast it's being spent)
  - accepting clips right now
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from statistics import NormalDist

PLATFORM_WORDS = {
    "tiktok": "tiktok", "instagram": "instagram", "youtube": "youtube", "youtube shorts": "youtube",
    "x": "x", "twitter": "x", "x (twitter)": "x", "facebook": "facebook", "snapchat": "snapchat",
}
MONEY = r"\$ ?([\d,]*\d(?:\.\d+)?)(?: ?([kKmM])(?![A-Za-z]))?"
LABELS = {
    "rate": r"per\s*1\s*k(?:\s*views)?|per\s*1,?000\s*views|\bcpm\b",
    "min": r"min(?:imum)?\.?\s*payout",
    "max": r"max(?:imum)?\.?\s*payout",
}


def money(num: str, suffix: str | None = None) -> float:
    v = float(num.replace(",", ""))
    return v * {"k": 1e3, "m": 1e6}.get((suffix or "").lower(), 1)


@dataclass
class PlatformPay:
    rate: float | None = None       # $ per 1,000 views
    min_payout: float | None = None
    max_payout: float | None = None


@dataclass
class Campaign:
    url: str
    title: str = ""
    accepting: bool | None = None
    launched_days: float | None = None
    pay: dict[str, PlatformPay] = field(default_factory=dict)
    budget_spent: float | None = None
    budget_total: float | None = None
    budget_left: float | None = None
    brief_links: list[str] = field(default_factory=list)
    files_locked: bool = False
    parse_warnings: list[str] = field(default_factory=list)
    checked_at: float = 0.0

    @property
    def parsed_ok(self) -> bool:
        return any(p.rate for p in self.pay.values())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Campaign":
        d = dict(d)
        d["pay"] = {k: PlatformPay(**v) for k, v in d.get("pay", {}).items()}
        return cls(**d)


# ── parsing ──────────────────────────────────────────────────────────────────
def _platform_heading(line: str) -> str | None:
    s = line.strip().lower().rstrip(":")
    return PLATFORM_WORDS.get(s)


def _parse_block(block: str) -> PlatformPay:
    """Labels and amounts may be interleaved (label, $) or grouped (labels..., $...).
    Either way the n-th label goes with the n-th amount."""
    found = []
    for key, rx in LABELS.items():
        for m in re.finditer(rx, block, re.I):
            found.append((m.start(), key))
    found.sort()
    labels = []
    for _, k in found:
        if k not in labels:
            labels.append(k)
    amounts = [money(n, s) for n, s in re.findall(MONEY, block)]
    pp = PlatformPay()
    for k, v in zip(labels, amounts):
        setattr(pp, {"rate": "rate", "min": "min_payout", "max": "max_payout"}[k], v)
    return pp


def parse_text(text: str, url: str = "", title: str = "", links: list[str] | None = None) -> Campaign:
    c = Campaign(url=url, title=title.strip())
    t = text.replace("\xa0", " ")
    lines = [ln.strip() for ln in t.splitlines()]

    if re.search(r"not\s+accepting\s+clips", t, re.I):
        c.accepting = False
    elif re.search(r"accepting\s+clips|submit\s+(?:a\s+)?clip", t, re.I):
        c.accepting = True

    m = re.search(r"launched\s+(\d+|an?|one)\s+(minute|hour|day|week|month)s?\s+ago", t, re.I)
    if m:
        n = 1 if m.group(1).lower() in ("a", "an", "one") else int(m.group(1))
        c.launched_days = n * {"minute": 1 / 1440, "hour": 1 / 24, "day": 1, "week": 7, "month": 30}[m.group(2).lower()]
    elif re.search(r"launched\s+(today|just now)", t, re.I):
        c.launched_days = 0.5

    # per-platform pay blocks: from each platform heading to the next heading / Budget
    heads = [(i, p) for i, ln in enumerate(lines) if (p := _platform_heading(ln))]
    for n, (i, p) in enumerate(heads):
        stop = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        block_lines = []
        for ln in lines[i + 1:stop]:
            if re.match(r"budget\b", ln, re.I):
                break
            block_lines.append(ln)
        pp = _parse_block("\n".join(block_lines))
        if pp.rate and p not in c.pay:
            c.pay[p] = pp
    if not c.pay:  # single rate for the whole campaign
        pp = _parse_block(t)
        if pp.rate:
            c.pay["any"] = pp
            c.parse_warnings.append("no per-platform pay found; using one rate for all platforms")

    # budget "$1,488 / $2,500" = spent / total, and "$1,012 remaining"
    bm = re.search(r"budget[\s\S]{0,80}?" + MONEY + r"\s*/\s*" + MONEY, t, re.I) or re.search(MONEY + r"\s*/\s*" + MONEY, t)
    if bm:
        g = bm.groups()
        c.budget_spent, c.budget_total = money(g[0], g[1]), money(g[2], g[3])
    rm = re.search(MONEY + r"\s+(?:left|remaining)", t, re.I)
    if rm:
        c.budget_left = money(*rm.groups())
    elif c.budget_total is not None and c.budget_spent is not None:
        c.budget_left = max(0.0, c.budget_total - c.budget_spent)
    if c.budget_left is None:
        c.parse_warnings.append("budget not found")

    c.files_locked = bool(re.search(r"join\s+to\s+unlock", t, re.I))
    for u in links or []:
        if re.search(r"docs\.google\.com|drive\.google\.com|notion\.(so|site)|dropbox\.com", u):
            if u not in c.brief_links:
                c.brief_links.append(u)
    if not c.title:
        ui = re.compile(r"^(not )?accepting clips|^launched|^content rewards|^back$|^discover|^whop$", re.I)
        c.title = next((ln for ln in lines if len(ln) > 8 and not ui.search(ln) and not ln.startswith("http")), url)[:120]
    return c


# ── profit model ─────────────────────────────────────────────────────────────
def payout(views: float, p: PlatformPay) -> float:
    """What one clip with `views` views earns: nothing below the min payout,
    then rate per 1K, capped at the max payout."""
    if not p.rate:
        return 0.0
    earned = views / 1000 * p.rate
    if p.min_payout and earned < p.min_payout:
        return 0.0
    if p.max_payout:
        earned = min(earned, p.max_payout)
    return earned


def views_to_min(p: PlatformPay) -> float:
    if not p.rate:
        return math.inf
    return (p.min_payout or 0) / p.rate * 1000


# Views per clip vary a lot: most clips land near your usual number, a few pop off.
# Model that as log-normal around your typical views and average over it.
_Q = 400
_Z = [NormalDist().inv_cdf((i + 0.5) / _Q) for i in range(_Q)]


def expected_payout(p: PlatformPay, typical_views: float, spread: float) -> float:
    return sum(payout(typical_views * math.exp(spread * z), p) for z in _Z) / _Q


def chance_to_clear_min(p: PlatformPay, typical_views: float, spread: float) -> float:
    need = views_to_min(p)
    if need <= 0:
        return 1.0
    if math.isinf(need) or typical_views <= 0:
        return 0.0
    return 1 - NormalDist().cdf(math.log(need / typical_views) / max(spread, 1e-6))


@dataclass
class Verdict:
    campaign: Campaign
    skip: list[str]
    platforms: list[str]            # your platforms this campaign pays on
    per_clip: float                 # average $ per clip (cross-posted), over your usual spread of views
    chance_paid: float              # share of your clips expected to clear the min payout somewhere
    per_day: float                  # per_clip * clips_per_day
    easiest_min_views: float        # fewest views to clear a min payout on your platforms
    best_rate: float
    budget_days_left: float | None  # at the current spend rate
    budget_factor: float
    score: float
    ladder: dict[int, float]        # $ per clip at 1k/5k/10k/50k views


def evaluate(c: Campaign, cfg: dict) -> Verdict:
    you, rules = cfg["you"], cfg["campaigns"]
    mine = [p.lower() for p in you["platforms"]]
    pays = {p: pp for p, pp in c.pay.items() if p in mine or p == "any"}
    if "any" in pays:
        pays = {p: pays["any"] for p in mine}
    skip: list[str] = []

    if not c.parsed_ok:
        skip.append("couldn't read pay rates from the page")
    if c.accepting is False and rules["skip_not_accepting"]:
        skip.append("not accepting clips right now")
    if c.parsed_ok and not pays:
        skip.append("doesn't pay on your platforms (" + ", ".join(c.pay) + ")")

    views = float(you["typical_views"])
    spread = float(you.get("views_spread", 1.0))
    if not you.get("cross_post", True) and pays:
        best = max(pays, key=lambda p: expected_payout(pays[p], views, spread))
        pays = {best: pays[best]}
    per_clip = sum(expected_payout(pp, views, spread) for pp in pays.values())
    chance = max((chance_to_clear_min(pp, views, spread) for pp in pays.values()), default=0.0)
    ladder = {v: round(sum(payout(v, pp) for pp in pays.values()), 2) for v in (1_000, 5_000, 10_000, 50_000)}
    easiest = min((views_to_min(pp) for pp in pays.values()), default=math.inf)
    best_rate = max((pp.rate or 0 for pp in pays.values()), default=0)

    if pays and best_rate < rules["min_rate_per_1k"]:
        skip.append(f"rate ${best_rate:.2f}/1K is under your ${rules['min_rate_per_1k']:.2f} minimum")
    if pays and chance < rules["min_chance_paid"]:
        skip.append(f"needs {easiest:,.0f} views to reach the min payout; only ~{chance:.0%} of your clips "
                    f"would (you usually get {views:,.0f})")
    if c.budget_left is not None and c.budget_left < rules["min_budget_left"]:
        skip.append(f"only ${c.budget_left:,.0f} budget left")

    days_left = None
    if c.budget_left is not None and c.budget_spent and c.launched_days:
        burn = c.budget_spent / max(c.launched_days, 0.5)
        days_left = c.budget_left / burn if burn > 0 else None
    factor = 1.0
    if c.budget_left is not None:
        factor = min(factor, c.budget_left / max(1.0, rules["comfortable_budget"]))
    if days_left is not None:
        factor = min(factor, days_left / max(0.5, rules["comfortable_days"]))
    factor = max(0.0, min(1.0, factor))

    per_day = per_clip * you["clips_per_day"]
    score = round(per_clip * factor, 2) if not skip else 0.0
    return Verdict(c, skip, sorted(pays), round(per_clip, 2), round(chance, 2), round(per_day, 2), easiest, best_rate,
                   None if days_left is None else round(days_left, 1), round(factor, 2), score, ladder)


def rank(campaigns: list[Campaign], cfg: dict) -> list[Verdict]:
    vs = [evaluate(c, cfg) for c in campaigns]
    return sorted(vs, key=lambda v: (not v.skip, v.score, v.per_clip), reverse=True)
