"""Turn whatever doc you were sent into a list of submissions.

Handles .csv / .tsv / .xlsx / .xlsm / .docx / .txt / .md / .json.
If the doc has a header row we use the columns; otherwise every link in the
file becomes a submission and the text around it on the same line is taken
as the clipper's name.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .util import clean_name, find_urls, platform_of

URL_HEADERS = ("url", "link", "video", "clip", "post", "submission")
USER_HEADERS = ("username", "user", "handle", "clipper", "creator", "name", "discord", "whop", "member", "email")
VIEW_HEADERS = ("views", "view count", "view_count", "plays")


@dataclass
class Submission:
    url: str
    submitter: str
    platform: str = ""
    doc_views: int | None = None
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        self.submitter = clean_name(self.submitter) or "unknown"
        self.platform = self.platform or platform_of(self.url)


def _pick(headers: list[str], keys: tuple[str, ...]) -> int | None:
    lowered = [h.strip().lower() for h in headers]
    for key in keys:  # priority order: exact match first
        for i, h in enumerate(lowered):
            if h == key:
                return i
    for key in keys:
        for i, h in enumerate(lowered):
            if key in h:
                return i
    return None


def _to_int(v) -> int | None:
    if v is None:
        return None
    s = str(v).strip().lower().replace(",", "")
    m = re.match(r"^([\d.]+)\s*([km]?)$", s)
    if not m:
        return None
    n = float(m.group(1)) * {"": 1, "k": 1_000, "m": 1_000_000}[m.group(2)]
    return int(n)


def from_rows(rows: list[list]) -> list[Submission]:
    rows = [[("" if c is None else str(c)) for c in r] for r in rows if any(c not in (None, "") for c in r)]
    if not rows:
        return []
    header = rows[0]
    header_has_url = any(find_urls(c) for c in header)
    url_i = None if header_has_url else _pick(header, URL_HEADERS)
    if url_i is None:
        # no usable header: fall back to scanning each row
        return from_text("\n".join(" | ".join(r) for r in rows))
    user_i = _pick(header, USER_HEADERS)
    if user_i == url_i:
        user_i = None
    view_i = _pick(header, VIEW_HEADERS)
    subs: list[Submission] = []
    for r in rows[1:]:
        r = r + [""] * (len(header) - len(r))
        urls = find_urls(r[url_i]) or [u for c in r for u in find_urls(c)]
        user = r[user_i] if user_i is not None else ""
        views = _to_int(r[view_i]) if view_i is not None else None
        extra = {header[i]: r[i] for i in range(len(header)) if i not in (url_i, user_i, view_i) and r[i]}
        for u in urls:
            subs.append(Submission(url=u, submitter=user, doc_views=views, extra=extra))
    return subs


def from_text(text: str) -> list[Submission]:
    subs: list[Submission] = []
    last_name = ""
    for line in text.splitlines():
        urls = find_urls(line)
        rest = line
        for u in urls:
            rest = rest.replace(u, " ")
        rest = re.sub(r"[|:\-–—•*,\t]+", " ", rest).strip()
        rest = re.sub(r"^\d+[.)]\s*", "", rest)  # "1. name"
        if not urls:
            # a line with just a name labels the links that follow it
            if rest and len(rest) <= 40:
                last_name = rest
            continue
        name = rest if rest and len(rest) <= 60 else last_name
        for u in urls:
            subs.append(Submission(url=u, submitter=name))
    return subs


def _from_json(obj) -> list[Submission]:
    subs: list[Submission] = []

    def walk(o):
        if isinstance(o, dict):
            flat = {k: v for k, v in o.items() if isinstance(v, (str, int, float))}
            urls = [u for v in flat.values() if isinstance(v, str) for u in find_urls(v)]
            if urls:
                keys = list(flat.keys())
                ui = _pick(keys, USER_HEADERS)
                vi = _pick(keys, VIEW_HEADERS)
                user = str(flat[keys[ui]]) if ui is not None and not find_urls(str(flat[keys[ui]])) else ""
                views = _to_int(flat[keys[vi]]) if vi is not None else None
                for u in urls:
                    subs.append(Submission(url=u, submitter=user, doc_views=views))
            for v in o.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return subs


def load(path: str | Path) -> tuple[list[Submission], list[str]]:
    """Returns (submissions, ignored_links). Links that aren't social video posts
    (a Whop page, a Google Drive folder...) are returned separately so nothing
    vanishes silently."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in (".csv", ".tsv"):
        with open(path, newline="", encoding="utf-8-sig") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            except csv.Error:
                dialect = csv.excel_tab if ext == ".tsv" else csv.excel
            subs = from_rows(list(csv.reader(f, dialect)))
    elif ext in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        subs = []
        for ws in wb.worksheets:
            subs += from_rows([list(r) for r in ws.iter_rows(values_only=True)])
    elif ext == ".docx":
        import docx

        d = docx.Document(str(path))
        subs = []
        for t in d.tables:
            subs += from_rows([[c.text for c in row.cells] for row in t.rows])
        # hyperlinks hidden behind link text live in the relationships
        para_text = "\n".join(p.text for p in d.paragraphs)
        subs += from_text(para_text)
        known = {s.url for s in subs}
        for rel in d.part.rels.values():
            if "hyperlink" in rel.reltype and rel.target_ref not in known and rel.target_ref.startswith("http"):
                subs.append(Submission(url=rel.target_ref, submitter=""))
    elif ext == ".json":
        subs = _from_json(json.loads(path.read_text(encoding="utf-8")))
    else:
        subs = from_text(path.read_text(encoding="utf-8", errors="replace"))
    keep = [s for s in subs if s.platform != "other"]
    ignored = [s.url for s in subs if s.platform == "other"]
    return keep, ignored

