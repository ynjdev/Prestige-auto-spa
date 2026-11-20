"""Open pages in a real (headless) Chromium so Whop's JavaScript renders.

Your Whop login is kept in data/browser/ after `clipper login`.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin, urlparse


class Browser:
    def __init__(self, profile_dir: str | Path, headless: bool = True):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise SystemExit("Playwright isn't installed: pip install playwright && playwright install chromium") from e
        self._pw = sync_playwright().start()
        Path(profile_dir).mkdir(parents=True, exist_ok=True)
        import os

        extra = {}
        if os.environ.get("CLIPPER_CHROMIUM"):  # use a specific Chrome/Chromium binary
            extra["executable_path"] = os.environ["CLIPPER_CHROMIUM"]
        self.ctx = self._pw.chromium.launch_persistent_context(
            str(profile_dir), headless=headless, viewport={"width": 1366, "height": 900}, **extra)

    def read(self, url: str, wait_ms: int = 2500) -> dict:
        """Visible text, title and all links of a page (scrolls to load lazy parts)."""
        page = self.ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass
            for _ in range(6):
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(400)
            page.wait_for_timeout(wait_ms)
            text = page.evaluate("document.body.innerText")
            hrefs = page.evaluate("Array.from(document.querySelectorAll('a[href]')).map(a => a.href)")
            return {"url": page.url, "title": page.title(), "text": text,
                    "links": list(dict.fromkeys(urljoin(page.url, h) for h in hrefs))}
        finally:
            page.close()

    def login(self, url: str = "https://whop.com/login") -> None:
        page = self.ctx.new_page()
        page.goto(url)
        input("Log in to Whop in the browser window, then press Enter here... ")
        page.close()

    def close(self):
        self.ctx.close()
        self._pw.stop()


def same_site_links(page: dict) -> list[str]:
    host = urlparse(page["url"]).hostname or ""
    out = []
    for u in page["links"]:
        p = urlparse(u)
        if p.hostname == host and p.path.rstrip("/") != urlparse(page["url"]).path.rstrip("/") and not p.fragment:
            out.append(u.split("#")[0])
    return list(dict.fromkeys(out))
