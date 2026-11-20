import csv

from clipper import config, hunt
from clipper.browser import Browser
from clipper.db import DB

from test_campaigns import GROUPED, VIDEO_PAGE


class FakeBrowser:
    def __init__(self, pages):
        self.pages, self.opened = pages, []

    def read(self, url, wait_ms=0):
        self.opened.append(url)
        return self.pages[url]

    def close(self):
        pass


def page(url, text, links=()):
    return {"url": url, "title": "", "text": text, "links": list(links)}


def test_listing_page_is_expanded_and_ranked(tmp_path):
    big = GROUPED
    small = GROUPED.replace("Gaming Highlights Clipping", "Small Budget Clips").replace("$1.2k / $20k", "$1.7k / $2k")
    pages = {
        "https://whop.com/discover/content-rewards": page(
            "https://whop.com/discover/content-rewards", "Campaigns for you ...",
            ["https://whop.com/c/a", "https://whop.com/c/b", "https://whop.com/c/c", "https://other.com/x"]),
        "https://whop.com/c/a": page("https://whop.com/c/a", small),
        "https://whop.com/c/b": page("https://whop.com/c/b", big),
        "https://whop.com/c/c": page("https://whop.com/c/c", VIDEO_PAGE),
    }
    fb = FakeBrowser(pages)
    cfg = config.load(None)
    cfg["you"]["platforms"] = ["tiktok", "instagram"]
    vs, out = hunt.run(["https://whop.com/discover/content-rewards"], cfg, DB(tmp_path / "c.db"), tmp_path,
                       lambda: fb, log=lambda *_: None)
    assert "https://other.com/x" not in fb.opened
    assert [v.campaign.url for v in vs] == ["https://whop.com/c/b", "https://whop.com/c/a", "https://whop.com/c/c"]
    assert vs[0].skip == [] and vs[1].skip == [] and vs[2].skip == ["not accepting clips right now"]
    assert vs[0].score > vs[1].score  # same pay, but b has far more budget left
    rows = list(csv.DictReader(open(out / "campaigns.csv")))
    assert rows[0]["rank"] == "1" and rows[0]["campaign"] == "Gaming Highlights Clipping"
    html = (out / "campaigns.html").read_text()
    assert "Join these, best first" in html and "not accepting clips" in html


def test_pasted_page_text_needs_no_browser(tmp_path):
    f = tmp_path / "pasted.txt"
    f.write_text("https://whop.com/c/zzz\n" + GROUPED)
    vs, _ = hunt.run([str(f)], config.load(None), DB(tmp_path / "c.db"), tmp_path,
                     lambda: (_ for _ in ()).throw(AssertionError("browser opened")), log=lambda *_: None)
    assert vs[0].campaign.url == "https://whop.com/c/zzz" and vs[0].campaign.pay["tiktok"].rate == 2.0


def test_real_browser_reads_rendered_page(tmp_path):
    # page whose numbers only exist after JavaScript runs, like Whop's
    html = tmp_path / "campaign.html"
    body = GROUPED.replace("\n", "<br>")
    html.write_text(f"<html><head><title>Gaming Highlights</title></head><body><div id=app></div>"
                    f"<a href='https://docs.google.com/document/d/abc/edit'>Brief</a>"
                    f"<script>document.getElementById('app').innerHTML = `{body}`;</script></body></html>")
    b = Browser(tmp_path / "profile")
    try:
        p = b.read(html.as_uri(), wait_ms=100)
    finally:
        b.close()
    from clipper.campaigns import parse_text

    c = parse_text(p["text"], p["url"], p["title"], p["links"])
    assert c.title == "Gaming Highlights" and c.pay["tiktok"].rate == 2.0
    assert c.brief_links == ["https://docs.google.com/document/d/abc/edit"]


def test_board_keeps_campaigns_sent_earlier(tmp_path):
    cfg = config.load(None)
    db = DB(tmp_path / "c.db")
    first, second = tmp_path / "a.txt", tmp_path / "b.txt"
    first.write_text("https://whop.com/c/a\n" + GROUPED)
    second.write_text("https://whop.com/c/b\n" + GROUPED.replace("Gaming Highlights Clipping", "Other One"))
    no_browser = lambda: (_ for _ in ()).throw(AssertionError("browser opened"))
    hunt.run([str(first)], cfg, db, tmp_path, no_browser, log=lambda *_: None)
    vs, out2 = hunt.run([str(second)], cfg, db, tmp_path, no_browser, log=lambda *_: None)
    assert {v.campaign.url for v in vs} == {"https://whop.com/c/a", "https://whop.com/c/b"}
    cfg["campaigns"]["keep_hours"] = 0
    vs, out3 = hunt.run([str(second)], cfg, db, tmp_path, no_browser, log=lambda *_: None)
    assert [v.campaign.url for v in vs] == ["https://whop.com/c/b"] and out3 != out2
