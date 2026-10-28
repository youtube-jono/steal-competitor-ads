---
description: Pull every competitor ad from Google, Facebook/Instagram, TikTok and LinkedIn, plus the landing page behind each
---

Pull every ad our competitors are running.

1. Read `context/competitors.md`. If the request names competitors, write them there first, one per line: `- Name · domain.com`. If it still has none, stop and ask for them.
2. Run `python3 code/pull_ads.py`. It takes a few minutes. Let it finish.
3. If `code/build_dashboard.py` exists, run `python3 code/build_dashboard.py`. If not, skip it.
4. Report back in a few short lines:
   - ads per platform for each competitor (Google, Meta, TikTok, LinkedIn)
   - any platform that came back empty, and why in plain words
   - how many landing pages were captured
   - what the Apify run cost
5. Point to `dashboard/index.html` if it was built.

Rules:
- Never open, fetch or browse facebook.com, instagram.com or any Meta page from this computer. Meta ads only come through Apify.
- Never print anything from `.env`.
- An empty TikTok result is normal. Their library only shows ads run in Europe.
- If a platform fails, say so and carry on. Don't rerun the whole pull for one platform. Use `python3 code/pull_ads.py --only <platform>` instead.
- No em-dashes.
