import openpyxl
import docx

from clipper import ingest
from clipper.util import normalize_url, platform_of


def test_normalize_url_variants():
    assert normalize_url("https://www.tiktok.com/@a/video/123?is_from_webapp=1") == "tiktok.com/@a/video/123"
    assert normalize_url("https://m.tiktok.com/@a/video/123/") == "tiktok.com/@a/video/123"
    assert normalize_url("https://www.instagram.com/reels/ABC_1/?igsh=x") == normalize_url("https://instagram.com/reel/ABC_1")
    assert normalize_url("https://youtu.be/xyz") == normalize_url("https://www.youtube.com/shorts/xyz?feature=share")
    assert normalize_url("https://www.youtube.com/watch?v=xyz") == "youtube.com/shorts/xyz"


def test_platform_of():
    assert platform_of("https://vm.tiktok.com/ZM123/") == "tiktok"
    assert platform_of("https://instagram.com/reel/x") == "instagram"
    assert platform_of("https://x.com/a/status/1") == "x"
    assert platform_of("https://whop.com/foo") == "other"


def test_csv_with_headers(tmp_path):
    p = tmp_path / "subs.csv"
    p.write_text("Whop Username,Video Link,Views\n@Alice ,https://www.tiktok.com/@al/video/1,\"12,400\"\n"
                 "bob,https://instagram.com/reel/XYZ,3.2k\n")
    subs, ignored = ingest.load(p)
    assert [(s.submitter, s.platform, s.doc_views) for s in subs] == [("alice", "tiktok", 12400), ("bob", "instagram", 3200)]
    assert ignored == []


def test_freeform_text(tmp_path):
    p = tmp_path / "subs.txt"
    p.write_text("Campaign: https://whop.com/my-campaign\n\nalice\nhttps://tiktok.com/@a/video/1\n"
                 "https://tiktok.com/@a/video/2\nbob - https://youtube.com/shorts/q1\n"
                 "1. carol: https://instagram.com/reel/Z\n")
    subs, ignored = ingest.load(p)
    assert [(s.submitter, s.url.split("/")[-1]) for s in subs] == [("alice", "1"), ("alice", "2"), ("bob", "q1"), ("carol", "Z")]
    assert ignored == ["https://whop.com/my-campaign"]


def test_xlsx(tmp_path):
    p = tmp_path / "subs.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Name", "Submission URL", "Platform"])
    ws.append(["Dave", "https://www.tiktok.com/@d/video/9", "TikTok"])
    wb.save(p)
    subs, _ = ingest.load(p)
    assert len(subs) == 1 and subs[0].submitter == "dave" and subs[0].extra == {"Platform": "TikTok"}


def test_docx_table_and_paragraphs(tmp_path):
    p = tmp_path / "subs.docx"
    d = docx.Document()
    d.add_paragraph("erin https://www.tiktok.com/@e/video/5")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Clipper", "Link"
    t.cell(1, 0).text, t.cell(1, 1).text = "frank", "https://youtube.com/shorts/f1"
    d.save(p)
    subs, _ = ingest.load(p)
    assert sorted((s.submitter, s.platform) for s in subs) == [("erin", "tiktok"), ("frank", "youtube")]
