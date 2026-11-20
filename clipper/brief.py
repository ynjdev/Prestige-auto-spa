"""Read the campaign brief (the Google Doc / file the brand gives you) and pull
out what matters for making clips: source videos, length limits, required
tags, and the do / don't rules."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .util import find_urls, platform_of

NEG = re.compile(r"\b(no|not|don'?t|do not|never|avoid|banned|prohibited|forbidden|without|isn'?t allowed|not allowed)\b", re.I)
POS = re.compile(r"\b(must|required?|include|always|make sure|need to|should|allowed|use)\b", re.I)
SOURCE_HOSTS = re.compile(r"youtube\.com|youtu\.be|drive\.google\.com|dropbox\.com|twitch\.tv|kick\.com|"
                          r"vimeo\.com|tiktok\.com|instagram\.com|x\.com|twitter\.com|rumble\.com|streamable\.com", re.I)
UNIT = r"(s|sec|secs|seconds?|m|mins?|minutes?)\b"


@dataclass
class Brief:
    text: str
    sources: list[str] = field(default_factory=list)
    tag_groups: list[list[str]] = field(default_factory=list)  # each group: pick any one
    min_sec: float | None = None
    max_sec: float | None = None
    dos: list[str] = field(default_factory=list)
    donts: list[str] = field(default_factory=list)
    whop_links: list[str] = field(default_factory=list)

    def tags_line(self) -> str:
        return " ".join(g[0] for g in self.tag_groups)


def _secs(n: str, unit: str) -> float:
    return float(n) * (60 if unit.lower().startswith("m") else 1)


def load_text(src: str | Path, browser_factory=None) -> str:
    """Brief from a file, a Google Doc link, or any web page."""
    s = str(src)
    if s.startswith("http"):
        m = re.search(r"docs\.google\.com/document/d/([\w-]+)", s)
        if m:
            import requests

            r = requests.get(f"https://docs.google.com/document/d/{m.group(1)}/export?format=txt", timeout=60)
            if r.ok and "<html" not in r.text[:200].lower():
                return r.text
            raise SystemExit("Couldn't open that Google Doc. In the doc: Share > General access > "
                             "'Anyone with the link', or download it (File > Download > .docx) and send the file.")
        if browser_factory is None:
            raise SystemExit(f"Can't read {s} without a browser")
        b = browser_factory()
        try:
            return b.read(s)["text"]
        finally:
            b.close()
    p = Path(s)
    ext = p.suffix.lower()
    if ext == ".docx":
        import docx

        d = docx.Document(str(p))
        parts = [para.text for para in d.paragraphs]
        for t in d.tables:
            parts += [" | ".join(c.text for c in row.cells) for row in t.rows]
        parts += [r.target_ref for r in d.part.rels.values() if "hyperlink" in r.reltype]
        return "\n".join(parts)
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise SystemExit("pip install pypdf to read PDF briefs, or send the doc as .docx/.txt") from e
        return "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages)
    if ext in (".html", ".htm"):
        html = p.read_text(encoding="utf-8", errors="replace")
        links = re.findall(r'href="(https?://[^"]+)"', html)
        return re.sub(r"<[^>]+>", "\n", html) + "\n" + "\n".join(links)
    return p.read_text(encoding="utf-8", errors="replace")


def parse(text: str) -> Brief:
    b = Brief(text=text)
    lines = [ln.strip(" \t•*-–—·>") for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    for u in find_urls(text):
        if "whop.com" in u:
            b.whop_links.append(u)
        elif SOURCE_HOSTS.search(u) and "docs.google.com/document" not in u and u not in b.sources:
            b.sources.append(u)

    seen_tags: set[str] = set()
    for ln in lines:
        tags = re.findall(r"(?<![\w/])([#@][A-Za-z0-9_.]*[A-Za-z0-9_])", ln)
        tags = [t for t in tags if not re.fullmatch(r"@?\d+", t)]
        if tags and not NEG.search(ln.split(tags[0])[0]):
            if re.search(r"\bone of\b|\beither\b|\bor\b", ln, re.I) and len(tags) > 1:
                group = [t for t in tags if t.lower() not in seen_tags]
                if group:
                    b.tag_groups.append(group)
                    seen_tags.update(t.lower() for t in group)
            else:
                for t in tags:
                    if t.lower() not in seen_tags:
                        b.tag_groups.append([t])
                        seen_tags.add(t.lower())

        low = ln.lower()
        if re.search(r"clip|video|length|long|duration|second|minute", low):
            m = re.search(r"(\d+)\s*" + r"(?:" + UNIT[1:-3] + r")?\s*(?:-|–|to)\s*(\d+)\s*" + UNIT, ln, re.I)
            if m:
                unit = m.group(3)
                b.min_sec, b.max_sec = _secs(m.group(1), unit), _secs(m.group(2), unit)
            else:
                lo = re.search(r"(?:at least|minimum(?: of)?|min\.?|no shorter than|longer than|over)\s*(\d+)\s*" + UNIT, ln, re.I)
                hi = re.search(r"(?:under|max(?:imum)?(?: of)?|no longer than|less than|up to|shorter than|below)\s*(\d+)\s*" + UNIT, ln, re.I)
                if lo:
                    b.min_sec = _secs(lo.group(1), lo.group(2))
                if hi:
                    b.max_sec = _secs(hi.group(1), hi.group(2))

        if 6 <= len(ln) <= 300 and not find_urls(ln):
            if NEG.search(ln):
                b.donts.append(ln)
            elif POS.search(ln):
                b.dos.append(ln)
    return b


def source_platform(url: str) -> str:
    return platform_of(url)
