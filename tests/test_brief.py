from clipper import brief

DOC = """Call of Duty - MW4 Season 01 Trailer Clipping
Source footage: https://www.youtube.com/watch?v=abc123 and https://drive.google.com/drive/folders/XYZ
Campaign: https://whop.com/discover/cod-clips
REQUIREMENTS
- Clips must be 15-45 seconds long
- Caption must include one of #Ad, #Advertisement or #Sponsored
- Tag @callofduty in every post
- Text must be clear and easy to read.
EDITING GUIDELINES
Background music: ALLOWED. Use only music from the platform library.
No AI voices. No AI voiceovers, AI narration, or AI clones.
Do not use #fyp spam hashtags
Never post leaked footage
"""


def test_parse_brief():
    b = brief.parse(DOC)
    assert b.sources == ["https://www.youtube.com/watch?v=abc123", "https://drive.google.com/drive/folders/XYZ"]
    assert b.whop_links == ["https://whop.com/discover/cod-clips"]
    assert (b.min_sec, b.max_sec) == (15, 45)
    assert b.tag_groups == [["#Ad", "#Advertisement", "#Sponsored"], ["@callofduty"]]
    assert b.tags_line() == "#Ad @callofduty"
    assert any("No AI voices" in d for d in b.donts)
    assert any("leaked" in d for d in b.donts)
    assert not any(t[0] == "#fyp" for t in b.tag_groups)
    assert any("Text must be clear" in d for d in b.dos)


def test_length_variants():
    assert (brief.parse("Videos should be at least 20 seconds").min_sec) == 20
    assert (brief.parse("Keep clips under 1 minute").max_sec) == 60
    assert brief.parse("clip length 30 to 90 sec").max_sec == 90


def test_docx_brief(tmp_path):
    import docx

    d = docx.Document()
    d.add_paragraph("Clips must be 20-60 seconds")
    d.add_paragraph("Source: https://youtu.be/xyz")
    p = tmp_path / "brief.docx"
    d.save(p)
    b = brief.parse(brief.load_text(p))
    assert b.sources == ["https://youtu.be/xyz"] and (b.min_sec, b.max_sec) == (20, 60)
