---
description: Rank every competitor ad and grade it A, B or C - which of their ads are actually winning
---

Rank the competitor ads.

1. If `data/ads.json` doesn't exist, stop and say: run /pull-ads first.
2. Run `python3 code/rank_ads.py`. It reads `data/ads.json` (and `data/pages.json` for the landing page bonus) and writes `data/ranked.json`.
3. If `code/build_dashboard.py` exists, run `python3 code/build_dashboard.py`.
4. Report back in a few short lines:
   - per platform, their A tier: the advertiser, the headline, and the one-line why
   - how sure we are: how many ads had real delivery data (grade A), a rank only (B), or dates only (C)
   - one plain sentence: no ad library shows spend, so the score is built from delivery clues, and days running only breaks ties. A year at $1 a day is not a winner.
5. Point to `dashboard/index.html`.

How the score works, if asked (details in `references/ranking-research.md`, "FINAL METHOD"):
- Meta: EU reach per day when the ad ran in Europe, else its position in Meta's impressions-sorted pull. A boost for 30+ days running and for copies.
- Google: SpyFu's share of ads served, ranked within each competitor. Then days shown.
- TikTok and LinkedIn: EU impression ranges where they exist.
- Delivery counts four times as much as time. Missing data is never zero: a dates-only ad tops out at 60.
- Under 7 days on Meta or 14 on Google is too new to judge, so it can't be a winner. Hiring posts go to C.
- Tier A is the top 15% per platform, never fewer than 3. C is the bottom third.

Rules:
- Never edit scores or tiers by hand. If a ranking looks wrong, say why and fix `code/rank_ads.py`.
- Never open facebook.com, instagram.com or any Meta page from this computer.
- Never print anything from `.env`.
- No em-dashes.
