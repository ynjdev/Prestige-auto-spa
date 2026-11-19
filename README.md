# Clipper: Whop Content Rewards clip pipeline

You send it the submissions doc. It does the rest:

- **Enforces your rules**: platform, length, required tags, posting date and minimum views.
- **Catches cheaters**:
  - reuploads of another clipper's video, even re-encoded or trimmed
  - one link submitted twice, or the same video under a second link
  - someone submitting an account that belongs to another clipper
  - botted views
- **Strikes and bans**: every violation adds points, and enough points bans the clipper. Bans carry over between batches, so a banned clipper is rejected automatically from then on.
- **Collects the best clips**: approved clips get a 0–100 score. The top ones go into `ready_to_post/`, ranked, with the original uploader's metadata removed. Cross-posts of the same clip are collected only once.
- **Writes your to-do list**: who to ban, what to reject (with a reason you can copy and paste), and what to approve.

**All you do:** click the actions into Whop, then caption and post the clips.

> **Why you still click in Whop:** Whop's API can *list* bounty submissions, but it has no endpoint to approve, reject or ban (as of Nov 2026). Those actions exist only in the Whop dashboard. Clipper makes every decision and gives you copy buttons, so it's a few minutes of clicking. If you don't act within 48 hours, Whop may auto-approve submissions its own review AI marks as legit, so clear the reject list promptly.

---

## Setup (once, on your computer)

macOS:

```bash
brew install python ffmpeg
git clone <this repo> && cd Prestige-auto-spa
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Windows: install Python 3.11+ and ffmpeg (`winget install Gyan.FFmpeg`), then run the same `pip install -e .`.

Then open `config.toml` and set your campaign rules (it's commented line by line).

## Every batch

**Option A: hands-off.** Leave this running:

```bash
clipper watch
```

Drop each submissions doc into the `inbox/` folder. It's processed automatically and moved to `inbox/done/`.

**Option B: one doc at a time.**

```bash
clipper run ~/Downloads/submissions.xlsx
```

Then open `output/<batch>/report.html`:

| Section | What you do |
|---|---|
| **Ready to post** | Watch, caption, post. Files are in `ready_to_post/`. Write your captions in `captions.csv`. |
| **1 · Ban in Whop** | Ban these clippers. |
| **2 · Reject in Whop** | Reject each one. Use **Copy reason** and paste it in. |
| **3 · Approve in Whop** | Approve these. |
| **Check by hand** | Links that wouldn't load (private, deleted, or the platform blocked the download). They're retried on the next run. |

The same lists are in `whop_actions.csv` and `bans.txt`.

## What the doc can look like

Any of these work: `.xlsx`, `.csv`, `.docx`, `.txt`, `.json`, or text pasted from Discord or Whop.

- **With column headers** (e.g. `Username | Video Link | Views`): the columns are detected automatically.
- **Without headers:** every TikTok, Instagram, YouTube, X or Facebook link becomes a submission, and the name on the same line (or the line just above) becomes the clipper.
- **Other links** (your Whop page, Google Drive): listed under *Ignored links*, never silently dropped.

## Rules and points (defaults, all in `config.toml`)

| Violation | Points | Notes |
|---|---|---|
| Reupload of another clipper's video | 3 → **instant ban** | Matched by video fingerprint, not by link. The first submitter keeps it. |
| Account registered to another clipper | 3 → **instant ban** | The first clipper to submit a social account owns it. |
| Botted views | 2 | Below a 0.3% like rate, or zero comments on 50k+ views. A second offence means a ban. |
| Missing tags / before start date / too short / too long / wrong platform | 1 each | |
| Duplicate link, below min views, deleted video | 0 | Rejected, no strike. |

A clipper hits `ban_at_points = 3` → banned. When a clipper is banned, their other clips in that same batch are rejected too.

## Commands

```bash
clipper run <doc> [more docs]       # process docs
clipper watch                       # process anything dropped into inbox/
clipper clippers                    # everyone: points, bans, linked accounts
clipper ban <name> --reason "..."   # manual ban
clipper unban <name>                # lift a ban (resets points; --keep-points to keep them)
clipper release-account tiktok <account_id>   # free an account claimed by the wrong person
```

Everything is remembered in `data/clipper.db`. Back that file up, because it holds your ban list and clip history.

## Limits you should know

- **Bot detection is a heuristic.** It flags engagement far below normal. It can't see a platform's internal fraud data. Tune `min_like_rate` if it is too strict or too loose for your niche.
- **Reupload matching** catches re-encodes, resizes and trims. It will not reliably catch heavily edited copies (mirrored, cropped hard, big overlays).
- **Instagram and TikTok sometimes block anonymous downloads.** If many links land in *Check by hand*, set `cookies_from_browser = "chrome"` (or your browser) in `config.toml` and stay logged in there.
- **Instagram often hides view counts.** A views column in your doc fills the gap. Otherwise the score treats views as neutral.
- **Account ownership is first come, first served.** If someone claims an account first, fix it with `release-account`.

## Tests

```bash
pip install -e '.[dev]' && pytest
```

The tests generate real video files with ffmpeg. They run two batches covering a stolen reupload, botted views, a duplicate link, a claimed account, a banned clipper coming back, an unloadable link, tags and the campaign start date.
