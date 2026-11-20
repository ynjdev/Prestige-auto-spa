# Clipper: Whop Content Rewards, done for you

Two jobs, so all you do is caption and post:

1. **Find the money.** Send it any campaign links you come across. It ranks them by what they'd actually pay *you*, using the rules from the clipping tutorial:
   - the **pay per 1K views** on the platforms you post to
   - a **low minimum payout**, so you don't need crazy views to get paid
   - **lots of budget left**, and how fast the rest is being spent
   - **accepting clips right now**
2. **Make the clips.** Send it a campaign's brief (the Google Doc). It:
   - downloads the source videos
   - transcribes them on your computer
   - picks the best moments
   - cuts them into vertical 1080×1920 clips that fit the brief's length rules
   - lists the tags every caption needs and the brief's do's and don'ts

---

## Setup (once)

macOS:

```bash
brew install python ffmpeg
git clone <this repo> && cd Prestige-auto-spa
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium
clipper setup      # downloads the speech model (~200 MB), checks the browser
clipper login      # log in to Whop once in the window that opens
```

Windows: install Python 3.11+ and ffmpeg (`winget install Gyan.FFmpeg`), then run the same commands.

**Recommended:** set `ANTHROPIC_API_KEY` so Claude picks the moments. It reads the whole transcript and the brief, then chooses self-contained moments with a strong hook. It costs about 10–20¢ per hour of source video (my estimate, not a measured figure). Without a key, a basic loudness-and-talking heuristic is used. It works, but the picks are much weaker.

Open `config.toml` and set **`typical_views`** to what your clips usually get. The whole profit ranking depends on that number.

## Every day

```bash
clipper watch
```

Leave that running and drop files into `inbox/`:

| You drop in | It does |
|---|---|
| a `.txt` of Whop campaign links (any you find, one per line) | ranks them → `output/campaigns/<time>/campaigns.html` |
| a Discover or listing page link in that `.txt` | opens every campaign on it and ranks those too |
| a campaign brief: `.docx`, `.pdf`, or a `.txt` with the Google Doc link | makes clips → `output/<campaign>/<time>/clips.html` |

Or run the steps directly:

```bash
clipper find https://whop.com/... https://whop.com/...        # rank campaigns
clipper make "https://docs.google.com/document/d/..."          # brief -> clips
clipper make brief.docx --source https://youtu.be/... --count 15
```

Then:

1. Open `campaigns.html`. Join the top ones on Whop.
2. Send each one's brief to `inbox/`. The brief is locked until you join.
3. Open `clips.html`. Watch the clips, copy the required tags, caption, post, and submit the links on Whop.

## How the ranking works

Your views swing from clip to clip, so the tool doesn't assume every clip gets exactly `typical_views`. It spreads the estimate around that number: most clips near it, a few that pop off, some that flop.

For each platform you post on:

- A clip that doesn't reach the **minimum payout** earns **$0**.
- Above that, you earn the **rate per 1K**, up to the **max payout**.

Averaging over that spread gives **avg $ per clip**, cross-posted to every platform the campaign pays on. A high minimum payout lowers this number, because more of your clips fall short. That's the tutorial's advice turned into math.

The average is then scaled down when:

- **the budget left is small:** under `comfortable_budget`, $2,000 by default
- **the budget is running out fast:** the tool takes spent ÷ days since launch and works out how many days are left. Under `comfortable_days` (7) gets a lower score.

**Skipped:**

- not accepting clips
- doesn't pay on your platforms
- rate under your minimum
- under `min_chance_paid` (40%) of your clips would reach the minimum payout
- under `min_budget_left`

The page also shows what one clip earns at 1k, 5k, 10k and 50k views. The board keeps every campaign you've sent in the last 24 hours, and resending a link refreshes it.

## Staying out of trouble

- **No repeats:** the same moment of a source video is never clipped twice, so you don't post duplicates. Duplicates get rejected.
- **Length rules:** clips always fit the brief's length limits, and cuts start and end on sentence boundaries.
- **Tags and rules up front:** `clips.html` shows the tags every caption needs (with a copy button) and the brief's don'ts.
- **Clean files:** clips are fresh edits with the source file's metadata stripped.

## Limits

- **Reading Whop pages:** the reader was built from the labels in the tutorial video. They are "Per 1K views", "Min payout", "Max payout", "Budget $X / $Y" and "Not accepting clips". It has never been run against a live Whop page, because whop.com was blocked where this was built. If a campaign shows up as "couldn't read pay rates", open the page, press Ctrl+A then Ctrl+C, paste into a `.txt` and drop it in `inbox/`. Pasted text works the same way. If Whop changes its page layout, the reader needs updating.
- **Estimates, not guarantees:** the dollar figures depend on your `typical_views` and on how fast other clippers use up the budget.
- **Brief rules:** they're pulled out by keywords. Skim the real brief once.
- **Logged-in downloads:** some sources (Drive, Instagram) need you logged in. Set `cookies_from_browser` in `config.toml`.
- **Posting:** it doesn't post or submit for you. Whop's API has endpoints for "bounty" submissions, but I couldn't confirm they cover Content Rewards campaigns.

## Tests

```bash
pip install -e '.[dev]' && pytest
```
