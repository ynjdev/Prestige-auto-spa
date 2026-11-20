"""HTML pages you open: ranked campaigns, and clips ready to caption."""
from __future__ import annotations

import html
import math
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .campaigns import Verdict
    from .make import Result

e = html.escape

CSS = """
:root { --bg:#fafaf9; --fg:#1c1917; --muted:#78716c; --line:#e7e5e4; --card:#fff; --accent:#4f46e5; --good:#15803d; --bad:#b91c1c; }
@media (prefers-color-scheme: dark) { :root { --bg:#141414; --fg:#f5f5f4; --muted:#a8a29e; --line:#2e2e2e; --card:#1d1d1d; --accent:#818cf8; --good:#4ade80; --bad:#f87171; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif; }
main { max-width:1100px; margin:0 auto; padding:24px 16px 64px; }
h1 { font-size:22px; margin:0 0 4px; } h2 { font-size:17px; margin:32px 0 10px; }
a { color:var(--accent); } .muted { color:var(--muted); } .small { font-size:13px; }
.tw { overflow-x:auto; border:1px solid var(--line); border-radius:10px; background:var(--card); }
table { border-collapse:collapse; width:100%; font-size:14px; }
th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
th { font-weight:600; white-space:nowrap; } td.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.money { color:var(--good); font-weight:700; } .skip { color:var(--bad); font-size:13px; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:14px; }
.card { margin:0; background:var(--card); border:1px solid var(--line); border-radius:12px; overflow:hidden; }
.card video { width:100%; aspect-ratio:9/16; background:#000; display:block; }
.card figcaption { padding:10px 12px; }
.pill { display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 10px; margin:2px 4px 2px 0; font-size:13px; }
ul { padding-left:20px; } li { margin:3px 0; }
button { font:inherit; font-size:13px; padding:4px 10px; border-radius:6px; border:1px solid var(--line); background:var(--bg); color:var(--fg); cursor:pointer; }
"""
JS = """<script>document.addEventListener('click',ev=>{const b=ev.target.closest('button[data-copy]');if(!b)return;
navigator.clipboard.writeText(b.dataset.copy).then(()=>{const t=b.textContent;b.textContent='Copied';setTimeout(()=>b.textContent=t,1200)})});</script>"""


def _page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{e(title)}</title><style>{CSS}</style></head>'
            f"<body><main>{body}</main>{JS}</body></html>")


def _usd(x) -> str:
    return "" if x is None else f"${x:,.2f}" if x < 100 else f"${x:,.0f}"


def campaigns_html(vs: list["Verdict"], cfg: dict) -> str:
    you = cfg["you"]
    good = [v for v in vs if not v.skip]
    bad = [v for v in vs if v.skip]
    rows = []
    for i, v in enumerate(good, 1):
        c = v.campaign
        pay = "<br>".join(f"{e(p)}: {_usd(pp.rate)}/1K · min {_usd(pp.min_payout)} · max {_usd(pp.max_payout)}"
                          for p, pp in c.pay.items())
        budget = f"{_usd(c.budget_left)} of {_usd(c.budget_total)}" if c.budget_left is not None else "?"
        days = f"~{v.budget_days_left:g} days left" if v.budget_days_left is not None else ""
        age = (time.time() - c.checked_at) / 3600 if c.checked_at else 0
        if age >= 1:
            days += f"<br>checked {age:.0f}h ago"
        ladder = " · ".join(f"{k // 1000}k: {_usd(x)}" for k, x in v.ladder.items())
        rows.append(
            f"<tr><td class=num>{i}</td><td><a href='{e(c.url)}' target=_blank rel=noopener>{e(c.title)}</a>"
            f"<div class='muted small'>{pay}</div><div class='muted small'>per clip at {ladder}</div></td>"
            f"<td class='num money'>{_usd(v.per_clip)}</td><td class='num money'>{_usd(v.per_day)}</td>"
            f"<td class=num>{'' if math.isinf(v.easiest_min_views) else f'{v.easiest_min_views:,.0f}'}"
            f"<div class='muted small'>~{v.chance_paid:.0%} of your clips</div></td>"
            f"<td class=num>{budget}<div class='muted small'>{days}</div></td></tr>")
    skip_rows = [f"<tr><td><a href='{e(v.campaign.url)}' target=_blank rel=noopener>{e(v.campaign.title)}</a></td>"
                 f"<td class=skip>{e('; '.join(v.skip))}</td></tr>" for v in bad]
    body = f"""
<h1>Best campaigns for you</h1>
<p class="muted small">Ranked by average $ per clip for someone whose clips usually get {you['typical_views']:,} views
(cross-posted to {', '.join(you['platforms'])}). Clips that miss a minimum payout count as $0, so a low minimum payout
ranks higher. The score drops when the budget is small or running out fast.
Change your numbers in <code>config.toml</code>. Budgets move fast: re-check before you start.</p>
<h2>Join these, best first</h2>
{('<div class=tw><table><thead><tr><th>#</th><th>Campaign</th><th>Avg $ / clip</th><th>$ / day*</th>'
  '<th>Views to min payout</th><th>Budget left</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
  f'<p class="muted small">* {you["clips_per_day"]} clips a day at your usual views. Estimates, not guarantees.</p>')
 if rows else '<p class=muted>None of these pass your filters.</p>'}
{('<h2>Skipped</h2><div class=tw><table><thead><tr><th>Campaign</th><th>Why</th></tr></thead><tbody>'
  + ''.join(skip_rows) + '</tbody></table></div>') if skip_rows else ''}
<h2>Next</h2>
<p class="small">Join a campaign on Whop, open its brief (the Google Doc), and send it to clipper:
<code>clipper make &lt;doc link or file&gt;</code>, or drop it into the <code>inbox/</code> folder.</p>"""
    return _page("Campaign Ranking", body)


def write_clips(res: "Result") -> None:
    br = res.brief
    cards = []
    for c in res.clips:
        rel = os.path.relpath(c.file, res.out_dir)
        m = c.moment
        cards.append(f"""<figure class=card><video src="{e(rel)}" controls preload=metadata playsinline></video>
<figcaption><b>{e(c.file.name)}</b><div class="muted small">{m.length:.0f}s · from {e(c.source_title[:60])}
 @ {int(m.start // 60)}:{int(m.start % 60):02d}</div>
{f'<div class=small>Hook idea: {e(m.hook)} <button data-copy="{e(m.hook)}">Copy</button></div>' if m.hook else ''}
<div class="muted small">{e(m.why)}</div></figcaption></figure>""")
    tags = " ".join(f"<span class=pill>{e(' / '.join(g))}</span>" for g in br.tag_groups)
    li = lambda xs: "<ul>" + "".join(f"<li>{e(x)}</li>" for x in xs[:40]) + "</ul>" if xs else "<p class=muted>None found.</p>"
    probs = ("<h2>Problems</h2><ul>" + "".join(f"<li>{e(p)}</li>" for p in res.problems) + "</ul>") if res.problems else ""
    body = f"""
<h1>{e(res.name)}: clips ready to post</h1>
<p class="muted small">{len(res.clips)} clips · {res.min_sec:.0f}-{res.max_sec:.0f}s each · moments picked by {e(res.picker)} ·
files in <code>ready_to_post/</code> (an .srt subtitle file sits next to each clip)</p>
<h2>Put these in every caption</h2>
<p>{tags or '<span class=muted>No required tags found in the brief. Check it yourself.</span>'}
{f'<button data-copy="{e(br.tags_line())}">Copy tags</button>' if br.tag_groups else ''}</p>
<p class="muted small">Where a tag shows "a / b", any one of them is enough.</p>
<h2>Clips</h2>
{'<div class=grid>' + ''.join(cards) + '</div>' if cards else '<p class=muted>No clips were made. See problems below.</p>'}
{probs}
<h2>Brief: don't</h2>{li(br.donts)}
<h2>Brief: do</h2>{li(br.dos)}
<p class="muted small">Pulled from the brief automatically. Skim the real brief once: the tutorial is right that
breaking a rule gets clips rejected.</p>"""
    (res.out_dir / "clips.html").write_text(_page("Clips Ready", body), encoding="utf-8")
