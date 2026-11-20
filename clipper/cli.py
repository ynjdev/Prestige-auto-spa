"""clipper: find the most profitable Whop campaigns, then turn their briefs into ready-to-post clips."""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from . import config as config_mod
from .db import DB
from .util import find_urls

DOC_EXTS = {".txt", ".md", ".docx", ".pdf", ".html", ".htm"}


def _ctx(a):
    cfg = config_mod.load(a.config)
    data = Path(a.data)
    return cfg, DB(data / "clipper.db"), data


def _browser_factory(data: Path, headless: bool = True):
    def make():
        from .browser import Browser
        return Browser(data / "browser", headless=headless)
    return make


def cmd_login(a):
    _, _, data = _ctx(a)
    b = _browser_factory(data, headless=False)()
    b.login()
    b.close()
    print("Saved. clipper can now read campaign pages as you.")


def cmd_find(a):
    from . import hunt

    cfg, db, data = _ctx(a)
    vs, out = hunt.run(a.links, cfg, db, a.out, _browser_factory(data))
    good = [v for v in vs if not v.skip]
    print(f"\n{len(good)} worth joining, {len(vs) - len(good)} skipped.")
    for i, v in enumerate(good[:10], 1):
        note = f"  (budget gone in ~{v.budget_days_left:g} days)" if v.budget_days_left is not None and v.budget_days_left < 3 else ""
        print(f" {i:>2}. avg ${v.per_clip:>6,.2f}/clip  {v.campaign.title[:55]}{note}")
    print(f"Open: {out / 'campaigns.html'}")


def cmd_make(a):
    from . import make

    cfg, db, data = _ctx(a)
    res = make.run(a.brief, cfg, db, a.out, data, a.source or [], a.count, a.name, _browser_factory(data))
    print(f"\n{len(res.clips)} clips ready ({res.picker} picked the moments).")
    for p in res.problems:
        print(f"  ! {p}")
    print(f"Open:  {res.out_dir / 'clips.html'}")


def _is_campaign_list(p: Path) -> bool:
    if p.suffix.lower() not in (".txt", ".md"):
        return False
    text = p.read_text(encoding="utf-8", errors="replace")
    urls = find_urls(text)
    return bool(urls) and all("whop.com" in u for u in urls)


def cmd_watch(a):
    inbox = Path(a.inbox)
    done = inbox / "done"
    done.mkdir(parents=True, exist_ok=True)
    print(f"Watching {inbox.resolve()}\n"
          "  - a .txt of Whop campaign links -> ranks them\n"
          "  - a brief (.docx/.pdf/.txt, or a .txt with a Google Doc link) -> makes clips\nCtrl+C to stop.")
    sizes: dict[Path, int] = {}
    while True:
        for p in sorted(inbox.iterdir()):
            if not p.is_file() or p.suffix.lower() not in DOC_EXTS or p.name.startswith((".", "~$")):
                continue
            if sizes.get(p) != p.stat().st_size:  # wait until it has finished copying
                sizes[p] = p.stat().st_size
                continue
            sizes.pop(p, None)
            try:
                if _is_campaign_list(p):
                    a.links = [str(p)]
                    cmd_find(a)
                else:
                    text = p.read_text(encoding="utf-8", errors="replace") if p.suffix.lower() in (".txt", ".md") else ""
                    doc = next((u for u in find_urls(text) if "docs.google.com/document" in u), None)
                    a.brief, a.source, a.count, a.name = doc or str(p), None, None, None
                    if doc:  # a note with the doc link, maybe plus source links
                        a.source = [u for u in find_urls(text) if u != doc and "whop.com" not in u]
                    cmd_make(a)
            except (Exception, SystemExit) as e:
                print(f"!! {p.name}: {e}", file=sys.stderr)
            shutil.move(str(p), done / f"{time.strftime('%Y%m%d_%H%M%S')}_{p.name}")
        time.sleep(a.interval)


def cmd_setup(a):
    from . import transcribe

    cfg, _, data = _ctx(a)
    transcribe.ensure_models(data / "models", cfg["ai"]["whisper"])
    print("speech model ready")
    try:
        b = _browser_factory(data)()
        b.close()
        print("browser ready")
    except BaseException as e:
        print(f"browser not ready: {e}\n  run: playwright install chromium")


def main(argv=None):
    p = argparse.ArgumentParser(prog="clipper", description=__doc__)
    p.add_argument("--config", default="config.toml")
    p.add_argument("--data", default="data")
    p.add_argument("--out", default="output")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="download the speech model and check the browser (one time)")
    s.set_defaults(fn=cmd_setup)
    s = sub.add_parser("login", help="log in to Whop once so campaign pages load")
    s.set_defaults(fn=cmd_login)
    s = sub.add_parser("find", help="rank campaigns by profit: campaign links, a page listing campaigns, "
                                    "a .txt of links, or a .txt of pasted page text")
    s.add_argument("links", nargs="+")
    s.set_defaults(fn=cmd_find)
    s = sub.add_parser("make", help="turn a campaign brief into ready-to-post clips")
    s.add_argument("brief", help="Google Doc link, or the brief as .docx/.pdf/.txt")
    s.add_argument("--source", action="append", help="extra source video link or file (repeatable)")
    s.add_argument("--count", type=int, help="how many clips (default from config)")
    s.add_argument("--name", help="folder name for this campaign")
    s.set_defaults(fn=cmd_make)
    s = sub.add_parser("watch", help="handle anything dropped into the inbox folder")
    s.add_argument("--inbox", default="inbox")
    s.add_argument("--interval", type=float, default=10)
    s.set_defaults(fn=cmd_watch)

    a = p.parse_args(argv)
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass
    a.fn(a)


if __name__ == "__main__":
    main()
