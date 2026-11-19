"""SQLite memory: every clip ever seen, strikes, bans, and who owns which account.

This is what lets the system catch a clip that was approved last week being
re-submitted today, or a banned clipper coming back.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS clippers (
    name TEXT PRIMARY KEY,
    points INTEGER NOT NULL DEFAULT 0,
    banned INTEGER NOT NULL DEFAULT 0,
    ban_reason TEXT,
    banned_at REAL
);
CREATE TABLE IF NOT EXISTS accounts (
    platform TEXT NOT NULL,
    account TEXT NOT NULL,
    owner TEXT NOT NULL,
    PRIMARY KEY (platform, account)
);
CREATE TABLE IF NOT EXISTS clips (
    key TEXT PRIMARY KEY,          -- normalised url
    video_key TEXT,                -- platform:video_id once fetched
    url TEXT NOT NULL,
    submitter TEXT NOT NULL,
    platform TEXT,
    account TEXT,
    decision TEXT,                 -- approve / reject / manual
    reasons TEXT,                  -- json list
    score REAL,
    views INTEGER,
    fingerprint TEXT,              -- json list of frame hashes
    file TEXT,
    batch TEXT,
    seen_at REAL
);
CREATE INDEX IF NOT EXISTS clips_video_key ON clips(video_key);
CREATE TABLE IF NOT EXISTS strikes (
    name TEXT, points INTEGER, reason TEXT, url TEXT, batch TEXT, at REAL
);
"""


class DB:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def commit(self):
        self.conn.commit()

    # clippers ---------------------------------------------------------------
    def clipper(self, name: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM clippers WHERE name=?", (name,)).fetchone()

    def is_banned(self, name: str) -> bool:
        r = self.clipper(name)
        return bool(r and r["banned"])

    def add_points(self, name: str, points: int, reason: str, url: str, batch: str) -> int:
        self.conn.execute("INSERT OR IGNORE INTO clippers(name) VALUES (?)", (name,))
        if points:
            self.conn.execute("UPDATE clippers SET points = points + ? WHERE name=?", (points, name))
            self.conn.execute(
                "INSERT INTO strikes VALUES (?,?,?,?,?,?)", (name, points, reason, url, batch, time.time())
            )
        return self.clipper(name)["points"]

    def ban(self, name: str, reason: str):
        self.conn.execute("INSERT OR IGNORE INTO clippers(name) VALUES (?)", (name,))
        self.conn.execute(
            "UPDATE clippers SET banned=1, ban_reason=?, banned_at=? WHERE name=?", (reason, time.time(), name)
        )

    def unban(self, name: str, reset_points: bool = True):
        self.conn.execute(
            "UPDATE clippers SET banned=0, ban_reason=NULL, banned_at=NULL"
            + (", points=0" if reset_points else "")
            + " WHERE name=?",
            (name,),
        )

    def banned_list(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM clippers WHERE banned=1 ORDER BY banned_at").fetchall()

    def all_clippers(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM clippers ORDER BY banned DESC, points DESC, name").fetchall()

    # accounts -------------------------------------------------------------
    def account_owner(self, platform: str, account: str) -> str | None:
        r = self.conn.execute(
            "SELECT owner FROM accounts WHERE platform=? AND account=?", (platform, account)
        ).fetchone()
        return r["owner"] if r else None

    def claim_account(self, platform: str, account: str, owner: str):
        self.conn.execute("INSERT OR IGNORE INTO accounts VALUES (?,?,?)", (platform, account, owner))

    # clips ----------------------------------------------------------------
    def clip(self, key: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM clips WHERE key=?", (key,)).fetchone()

    def clip_by_video(self, video_key: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM clips WHERE video_key=? ORDER BY seen_at LIMIT 1", (video_key,)
        ).fetchone()

    def fingerprints(self) -> list[tuple[str, str, list[int]]]:
        """(submitter, url, hashes) for every clip we have a fingerprint for."""
        rows = self.conn.execute(
            "SELECT submitter, url, fingerprint FROM clips WHERE fingerprint IS NOT NULL ORDER BY seen_at"
        ).fetchall()
        return [(r["submitter"], r["url"], json.loads(r["fingerprint"])) for r in rows]

    def save_clip(self, **c):
        c.setdefault("seen_at", time.time())
        if isinstance(c.get("reasons"), list):
            c["reasons"] = json.dumps(c["reasons"])
        if isinstance(c.get("fingerprint"), list):
            c["fingerprint"] = json.dumps(c["fingerprint"])
        cols = ",".join(c)
        self.conn.execute(
            f"INSERT OR REPLACE INTO clips({cols}) VALUES ({','.join('?' * len(c))})", tuple(c.values())
        )

    def accounts_of(self, owner: str) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM accounts WHERE owner=?", (owner,)).fetchall()

    def release_account(self, platform: str, account: str) -> int:
        return self.conn.execute(
            "DELETE FROM accounts WHERE platform=? AND account=?", (platform, account.lower())
        ).rowcount
