import math

from clipper import campaigns as C
from clipper import config

# What the campaign page in the tutorial video shows (visible text, interleaved layout)
VIDEO_PAGE = """Dennis Spends $100k On Diamond Grillz
Not accepting clips
Launched 6 days ago
Celebrity
213
Not accepting clips while the brand reviews earlier ones or adds budget. Your drafts are safe.
TikTok
Per 1K views
$1.50
Min payout
$3.00
Max payout
$200.00
Instagram
Per 1K views
$1.50
Min payout
$3.00
Max payout
$200.00
Budget
$1,488 / $2,500
$1,012 remaining in the campaign budget.
Reference materials
3 files
Join to unlock 1 requirement and 3 files
"""

# Same kind of page, grouped layout (labels first, then amounts), accepting clips
GROUPED = """Gaming Highlights Clipping
Accepting clips
Launched 2 days ago
TikTok
Per 1K views
Min payout
Max payout
$2.00
$1.00
$500.00
YouTube Shorts
Per 1K views
Min payout
Max payout
$1.00
$5.00
$300.00
Budget
$1.2k / $20k
"""


def cfg(**you):
    c = config.load(None)
    c["you"].update(you)
    return c


def test_parse_video_campaign():
    c = C.parse_text(VIDEO_PAGE, url="https://whop.com/x")
    assert c.title == "Dennis Spends $100k On Diamond Grillz"
    assert c.accepting is False and c.launched_days == 6
    assert c.pay["tiktok"] == C.PlatformPay(1.5, 3.0, 200.0)
    assert c.pay["instagram"] == C.PlatformPay(1.5, 3.0, 200.0)
    assert (c.budget_spent, c.budget_total, c.budget_left) == (1488, 2500, 1012)
    assert c.files_locked


def test_parse_grouped_layout_and_k_amounts():
    c = C.parse_text(GROUPED)
    assert c.accepting is True and c.launched_days == 2
    assert c.pay["tiktok"] == C.PlatformPay(2.0, 1.0, 500.0)
    assert c.pay["youtube"] == C.PlatformPay(1.0, 5.0, 300.0)
    assert (c.budget_spent, c.budget_total, c.budget_left) == (1200, 20000, 18800)


def test_payout_rules_from_video():
    p = C.PlatformPay(1.5, 3.0, 200.0)
    assert C.views_to_min(p) == 2000           # "$3 min payout = about 2-3k views"
    assert C.payout(1999, p) == 0              # below min payout: nothing
    assert C.payout(2000, p) == 3.0
    assert C.payout(10_000, p) == 15.0
    assert C.payout(1_000_000, p) == 200.0     # capped at max payout


def test_video_campaign_skipped_because_not_accepting():
    v = C.evaluate(C.parse_text(VIDEO_PAGE), cfg(typical_views=3000))
    assert v.skip == ["not accepting clips right now"]
    one = C.expected_payout(C.PlatformPay(1.5, 3.0, 200.0), 3000, 1.0)
    assert v.per_clip == round(2 * one, 2)     # TikTok + Instagram
    assert v.chance_paid == 0.66               # 2,000 views needed vs a usual 3,000
    assert v.budget_days_left == round(1012 / (1488 / 6), 1)  # ~4 days at the current spend


def test_ranking_prefers_profit_low_min_and_budget():
    small_budget = C.parse_text(GROUPED.replace("$1.2k / $20k", "$1.9k / $2k"), url="small")
    big_budget = C.parse_text(GROUPED, url="big")
    high_min = C.parse_text(GROUPED.replace("$1.00\n$500.00", "$40.00\n$500.00"), url="highmin")
    tiktok_only_you = cfg(typical_views=3000, platforms=["tiktok"])
    vs = C.rank([small_budget, high_min, big_budget], tiktok_only_you)
    assert [v.campaign.url for v in vs] == ["big", "small", "highmin"]
    assert vs[0].per_clip > 0 and vs[0].budget_factor == 1.0
    assert vs[1].skip == ["only $100 budget left"]
    assert vs[2].skip and "needs 20,000 views" in vs[2].skip[0]
    assert vs[0].ladder[1000] == 2.0 and vs[0].ladder[50_000] == 100.0


def test_platform_mismatch_and_unreadable():
    c = C.parse_text(GROUPED)
    v = C.evaluate(c, cfg(platforms=["instagram"]))
    assert v.skip and "doesn't pay on your platforms" in v.skip[0]
    v2 = C.evaluate(C.parse_text("Some random page"), cfg())
    assert v2.skip[0] == "couldn't read pay rates from the page" and math.isinf(v2.easiest_min_views)


def test_lower_min_payout_ranks_higher_at_same_rate():
    low = C.PlatformPay(1.5, 1.0, 200.0)
    high = C.PlatformPay(1.5, 10.0, 200.0)
    assert C.expected_payout(low, 3000, 1.0) > C.expected_payout(high, 3000, 1.0)
    assert C.chance_to_clear_min(low, 3000, 1.0) > C.chance_to_clear_min(high, 3000, 1.0)
    # with no spread it collapses to the plain point estimate
    assert round(C.expected_payout(low, 3000, 1e-9), 2) == 4.5
