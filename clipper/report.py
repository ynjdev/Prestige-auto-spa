"""Write the files you act on: what to click in Whop, and the clips to post."""
from __future__ import annotations

import csv
import html
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pipeline import Batch, Result


def _fmt(n) -> str:
    return f"{n:,}" if isinstance(n, int) else ("" if n is None else str(n))


def write(batch: "Batch", cfg: dict) -> None:
    out = batch.out_dir
    res = batch.results

    with open(out / "whop_actions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["action", "clipper", "link", "reason_to_paste_in_whop", "evidence_private", "views", "score", "banned_now"])
        order = {"reject": 0, "manual": 1, "approve": 2}
        for r in sorted(res, key=lambda r: (order.get(r.decision, 3), r.sub.submitter)):
            w.writerow([r.decision.upper(), r.sub.submitter, r.sub.url,
                        r.whop_message if r.decision == "reject" else r.note,
                        r.evidence if r.decision == "reject" else "",
                        _fmt(r.meta.get("views")), "" if r.score is None else r.score,
                        "YES" if r.banned_now else ""])

    with open(out / "bans.txt", "w", encoding="utf-8") as f:
        if not batch.new_bans:
            f.write("No new bans this batch.\n")
        for name, reason in batch.new_bans:
            f.write(f"{name}\t{reason}\n")

    if batch.ready:
        with open(out / "ready_to_post" / "captions.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["file", "your_caption", "original_caption", "clipper", "posted_by", "source", "views", "score"])
            for r in batch.ready:
                w.writerow([r.export.name, "", (r.meta.get("caption") or "")[:500], r.sub.submitter,
                            r.meta.get("account", ""), r.sub.url, _fmt(r.meta.get("views")), r.score])

    (out / "report.html").write_text(_html(batch, cfg), encoding="utf-8")


def _row_links(r: "Result") -> str:
    u = html.escape(r.sub.url)
    return f'<a href="{u}" target="_blank" rel="noopener">{u}</a>'


def _html(batch: "Batch", cfg: dict) -> str:
    e = html.escape
    res = batch.results
    approve = [r for r in res if r.decision == "approve"]
    reject = [r for r in res if r.decision == "reject"]
    manual = [r for r in res if r.decision == "manual"]

    cards = []
    for r in batch.ready:
        rel = os.path.relpath(r.export, batch.out_dir)
        parts = " · ".join(f"{k} {v:g}" for k, v in r.score_parts.items())
        cards.append(f"""
      <figure class="card">
        <video src="{e(rel)}" controls preload="metadata" playsinline></video>
        <figcaption>
          <div class="row"><b>{e(r.export.name)}</b><span class="score">{r.score:g}</span></div>
          <div class="muted">{e(r.sub.submitter)} · {_fmt(r.meta.get('views'))} views · @{e(str(r.meta.get('account') or ''))}</div>
          <div class="muted small">{e(parts)}</div>
          <a class="small" href="{e(r.sub.url)}" target="_blank" rel="noopener">source</a>
        </figcaption>
      </figure>""")

    def table(rows, cols, empty):
        if not rows:
            return f'<p class="muted">{empty}</p>'
        head = "".join(f"<th>{c}</th>" for c in cols)
        return f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'

    ban_rows = [f"<tr><td><b>{e(n)}</b></td><td>{e(reason)}</td>"
                f'<td><button data-copy="{e(n)}">Copy name</button></td></tr>' for n, reason in batch.new_bans]
    def _evidence(r):
        return f'<div class="muted small">Only you see this: {e(r.evidence)}</div>' if r.evidence else ""

    rej_rows = [f"<tr><td>{e(r.sub.submitter)}{' <span class=tag>BANNED</span>' if r.banned_now else ''}</td>"
                f"<td>{_row_links(r)}</td><td>{e(r.whop_message)}{_evidence(r)}</td>"
                f'<td><button data-copy="{e(r.whop_message)}">Copy reason</button></td></tr>' for r in reject]
    app_rows = [f"<tr><td>{e(r.sub.submitter)}</td><td>{_row_links(r)}</td>"
                f"<td>{_fmt(r.meta.get('views'))}</td><td>{r.score:g}</td></tr>" for r in approve]
    man_rows = [f"<tr><td>{e(r.sub.submitter)}</td><td>{_row_links(r)}</td><td>{e(r.note)}</td></tr>" for r in manual]
    ign_rows = [f"<tr><td>{e(u)}</td></tr>" for u in batch.ignored]

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Clip Batch Report</title>
<style>
:root {{ --bg:#fafaf9; --fg:#1c1917; --muted:#78716c; --line:#e7e5e4; --card:#fff; --accent:#4f46e5; --bad:#b91c1c; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141414; --fg:#f5f5f4; --muted:#a8a29e; --line:#2e2e2e; --card:#1d1d1d; --accent:#818cf8; --bad:#f87171; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:24px 16px 64px; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:17px; margin:36px 0 10px; }}
.muted {{ color:var(--muted); }} .small {{ font-size:13px; }}
.stats {{ display:flex; flex-wrap:wrap; gap:10px; margin:16px 0; }}
.stat {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px 14px; min-width:110px; }}
.stat b {{ display:block; font-size:22px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:14px; }}
.card {{ margin:0; background:var(--card); border:1px solid var(--line); border-radius:12px; overflow:hidden; }}
.card video {{ width:100%; aspect-ratio:9/16; background:#000; display:block; }}
.card figcaption {{ padding:10px 12px; }}
.row {{ display:flex; justify-content:space-between; gap:8px; }}
.score {{ color:var(--accent); font-weight:700; }}
.tw {{ overflow-x:auto; border:1px solid var(--line); border-radius:10px; background:var(--card); }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }}
th,td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
a {{ color:var(--accent); }} td a {{ word-break:break-all; }}
.tag {{ color:var(--bad); font-weight:700; font-size:12px; }}
button {{ font:inherit; font-size:13px; padding:4px 10px; border-radius:6px; border:1px solid var(--line); background:var(--bg); color:var(--fg); cursor:pointer; white-space:nowrap; }}
</style></head><body><main>
<h1>{e(cfg['campaign']['name'])}: clip batch</h1>
<div class="muted small">{e(batch.name)} · from {e(batch.doc.name)}</div>
<div class="stats">
  <div class="stat"><b>{len(res)}</b>submissions</div>
  <div class="stat"><b>{len(batch.ready)}</b>ready to post</div>
  <div class="stat"><b>{len(approve)}</b>approve</div>
  <div class="stat"><b>{len(reject)}</b>reject</div>
  <div class="stat"><b>{len(batch.new_bans)}</b>new bans</div>
  <div class="stat"><b>{len(manual)}</b>check by hand</div>
</div>

<h2>Ready to post: caption these</h2>
<p class="muted small">The files are in <code>ready_to_post/</code>, ranked best first, with metadata stripped. Write your captions in <code>ready_to_post/captions.csv</code>.</p>
{'<div class="grid">' + ''.join(cards) + '</div>' if cards else '<p class="muted">No clip met the quality bar this batch.</p>'}

<h2>1 · Ban in Whop</h2>
{table(ban_rows, ['Clipper', 'Why', ''], 'No new bans.')}

<h2>2 · Reject in Whop</h2>
{table(rej_rows, ['Clipper', 'Link', 'Reason', ''], 'Nothing to reject.')}

<h2>3 · Approve in Whop</h2>
{table(app_rows, ['Clipper', 'Link', 'Views', 'Score'], 'Nothing to approve.')}

<h2>Check by hand</h2>
<p class="muted small">These links couldn't be loaded. They are not saved, so the next run tries them again.</p>
{table(man_rows, ['Clipper', 'Link', 'Problem'], 'None.')}

{('<h2>Ignored links (not a video post)</h2>' + table(ign_rows, ['Link'], '')) if ign_rows else ''}
</main>
<script>
document.addEventListener('click', ev => {{
  const b = ev.target.closest('button[data-copy]'); if (!b) return;
  navigator.clipboard.writeText(b.dataset.copy).then(() => {{ const t = b.textContent; b.textContent = 'Copied'; setTimeout(() => b.textContent = t, 1200); }});
}});
</script>
</body></html>
"""
