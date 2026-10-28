---
description: Learn your business from your website and Google reviews into context/business.md and context/proof.md
argument-hint: [optional Google Maps place URL]
---

Learn the business in `.env` (BUSINESS_NAME, SITE_BASE_URL) from its website and its Google reviews.

1. Run `python3 code/learn_business.py`. If $ARGUMENTS holds a Google Maps URL, add `--place-url "<that url>"`.
   - It reads the site headless (home page plus up to 11 linked pages), then finds the Google Business Profile through Apify and pulls up to 40 reviews. About $0.01 to $0.05, hard cap $0.50.
   - It writes `data/business.json`. Read it in full.
2. Read `context/business.md` and `context/proof.md` if they already exist. Keep every fact in them and its source tier. If the site now says something different, the site wins: change it and say what changed.
3. Write `context/business.md`. Plain sentences, no tables. In this order:
   - `# <business name>`, then the pitch in two short lines (what it is, who for, the headline offer). The dashboard shows these.
   - One line saying what it was read from and when, then the source tiers: A = owner said it, B = the live site says it, C = from somewhere else, treat as stale, M = measured on the platform.
   - These exact lines, which the scripts read: `Market: <country>`, `Monthly ad budget: $<n> a month`, `Landing page: <url>`, `Buyer: <one sentence: who searches, on a phone, sceptical, what burned them before>`.
   - Sections: What it is · What ads are allowed to sell (with prices) · What ads must never sell · Who it is for · Where and when · How a lead becomes a client · The story · Contact · Google Business Profile · `## Keywords to bid on` (bullets, `keyword · searches a month · cost a click`, the lane being advertised) · Still open.
4. Write `context/proof.md`. `code/gate_rules.py` reads these headings, so keep them exactly:
   - `## The gap` - what the ads can't claim yet, said plainly. If there's no client result for what the ads sell, say so first: ads can claim the offer and the price, never an outcome.
   - `## Can claim: the offer and the price`, `## Can claim: the promises`, `## Can claim: the numbers` - one claim per bullet, written the way an ad could say it, then ` · ` then the source and tier. Round numbers down and write the ad form too: `150,000+ YouTube subscribers (150K+)`.
   - `## Hold: ...` - true but too weak or out of scope: under 10 reviews, community numbers, client results from a different service, dated claims.
   - `## Never say` - one phrase per bullet, a note after ` - `: superlatives, outcomes with no result on file, credentials not held, wrong numbers.
   - Nothing goes under "Can claim" without a source. A review count under 10 goes under Hold. A client result only counts for the service it came from.
5. If `code/build_dashboard.py` exists, run `python3 code/build_dashboard.py`.
6. Report back in a few short lines: what the business sells and to whom, the three strongest proof lines, the gap, the Google rating and review count (or that no profile was found), and the Apify spend.

Rules:
- Never print anything from `.env`.
- Never open facebook.com, instagram.com or any Meta page. Social links on the site are listed, never visited.
- Never invent a number, a review or a result. If the site doesn't say it and the owner didn't, it isn't proof.
- No em-dashes.
