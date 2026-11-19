"""clipper: drop in the doc, get back bans, rejects, approvals and the best clips."""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from . import config as config_mod
from .db import DB
from .media import have_ffmpeg

DOC_EXTS = {".csv", ".tsv", ".xlsx", ".xlsm", ".docx", ".txt", ".md", ".json"}


def _ctx(a):
    cfg = config_mod.load(a.config)
    data = Path(a.data)
    return cfg, DB(data / "clipper.db"), data


def _run_one(doc: Path, a) -> None:
    from .pipeline import run

    cfg, db, data = _ctx(a)
    b = run(doc, cfg, db, a.out, clip_dir=data / "clips")
    n = {k: sum(r.decision == k for r in b.results) for k in ("approve", "reject", "manual")}
    print(f"\nDone: {n['approve']} approve · {n['reject']} reject · {len(b.new_bans)} new bans · "
          f"{n['manual']} check by hand · {len(b.ready)} ready to post")
    print(f"Open:  {b.out_dir / 'report.html'}")
    if b.ready:
        print(f"Clips: {b.out_dir / 'ready_to_post'}")


def cmd_run(a):
    for d in a.docs:
        p = Path(d)
        if not p.exists():
            sys.exit(f"not found: {p}")
        _run_one(p, a)


def cmd_watch(a):
    inbox = Path(a.inbox)
    done = inbox / "done"
    inbox.mkdir(parents=True, exist_ok=True)
    done.mkdir(exist_ok=True)
    print(f"Watching {inbox.resolve()}. Drop a submissions doc in it. Ctrl+C to stop.")
    sizes: dict[Path, int] = {}
    while True:
        for p in sorted(inbox.iterdir()):
            if not p.is_file() or p.suffix.lower() not in DOC_EXTS or p.name.startswith((".", "~$")):
                continue
            size = p.stat().st_size
            if sizes.get(p) != size:  # wait one tick so a file still being copied isn't read half-written
                sizes[p] = size
                continue
            sizes.pop(p, None)
            try:
                _run_one(p, a)
            except Exception as e:  # keep watching even if one doc is broken
                print(f"!! {p.name} failed: {e}", file=sys.stderr)
            target = done / f"{time.strftime('%Y%m%d_%H%M%S')}_{p.name}"
            shutil.move(str(p), target)
        time.sleep(a.interval)


def cmd_ban(a):
    _, db, _ = _ctx(a)
    from .util import clean_name
    db.ban(clean_name(a.name), a.reason or "banned manually")
    db.commit()
    print(f"banned {clean_name(a.name)}")


def cmd_unban(a):
    _, db, _ = _ctx(a)
    from .util import clean_name
    db.unban(clean_name(a.name), reset_points=not a.keep_points)
    db.commit()
    print(f"unbanned {clean_name(a.name)}")


def cmd_clippers(a):
    _, db, _ = _ctx(a)
    rows = db.all_clippers()
    if not rows:
        print("no clippers yet")
    for r in rows:
        flag = "BANNED " if r["banned"] else "       "
        accts = ", ".join(f"{x['platform']}:{x['account']}" for x in db.accounts_of(r["name"]))
        print(f"{flag}{r['name']:<28} {r['points']} pts  {accts}"
              + (f"\n        reason: {r['ban_reason']}" if r["banned"] else ""))


def cmd_release(a):
    _, db, _ = _ctx(a)
    n = db.release_account(a.platform, a.account)
    db.commit()
    print("released" if n else "no such account claim")


def main(argv=None):
    p = argparse.ArgumentParser(prog="clipper", description=__doc__)
    p.add_argument("--config", default="config.toml")
    p.add_argument("--data", default="data", help="where the database and downloaded clips live")
    p.add_argument("--out", default="output", help="where batch reports and ready_to_post go")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("run", help="process one or more submission docs")
    s.add_argument("docs", nargs="+")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("watch", help="process every doc dropped into the inbox folder, forever")
    s.add_argument("--inbox", default="inbox")
    s.add_argument("--interval", type=float, default=10)
    s.set_defaults(fn=cmd_watch)

    s = sub.add_parser("ban", help="ban a clipper by name")
    s.add_argument("name")
    s.add_argument("--reason", default="")
    s.set_defaults(fn=cmd_ban)

    s = sub.add_parser("unban", help="lift a ban (also resets strike points)")
    s.add_argument("name")
    s.add_argument("--keep-points", action="store_true")
    s.set_defaults(fn=cmd_unban)

    s = sub.add_parser("clippers", help="list clippers, strike points, bans and their accounts")
    s.set_defaults(fn=cmd_clippers)

    s = sub.add_parser("release-account", help="free a social account claimed by the wrong clipper")
    s.add_argument("platform")
    s.add_argument("account")
    s.set_defaults(fn=cmd_release)

    a = p.parse_args(argv)
    try:
        sys.stdout.reconfigure(line_buffering=True)  # live progress when run in the background
    except AttributeError:
        pass
    if a.cmd in ("run", "watch") and not have_ffmpeg():
        print("warning: ffmpeg not found: reupload detection and clean export are off", file=sys.stderr)
    a.fn(a)


if __name__ == "__main__":
    main()
