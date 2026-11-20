"""Remembers campaigns you've checked and every moment already clipped, so you
never post the same moment twice (duplicate clips get rejected)."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (url TEXT PRIMARY KEY, data TEXT, checked_at REAL);
CREATE TABLE IF NOT EXISTS moments (
    source_key TEXT, start REAL, end REAL, campaign TEXT, file TEXT, created_at REAL
);
CREATE INDEX IF NOT EXISTS moments_src ON moments(source_key);
"""


class DB:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def save_campaign(self, url: str, data: dict):
        self.conn.execute("INSERT OR REPLACE INTO campaigns VALUES (?,?,?)", (url, json.dumps(data), time.time()))
        self.conn.commit()

    def campaigns(self, max_age_hours: float | None = None) -> list[dict]:
        rows = self.conn.execute("SELECT data, checked_at FROM campaigns ORDER BY checked_at DESC").fetchall()
        cutoff = time.time() - max_age_hours * 3600 if max_age_hours else 0
        return [json.loads(r["data"]) for r in rows if r["checked_at"] >= cutoff]

    def used(self, source_key: str) -> list[tuple[float, float]]:
        return [(r["start"], r["end"]) for r in
                self.conn.execute("SELECT start, end FROM moments WHERE source_key=?", (source_key,))]

    def add_moment(self, source_key: str, start: float, end: float, campaign: str, file: str):
        self.conn.execute("INSERT INTO moments VALUES (?,?,?,?,?,?)",
                          (source_key, start, end, campaign, file, time.time()))
        self.conn.commit()
