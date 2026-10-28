---
description: Put the S-tier ads in Google Ads as one paused Search campaign
argument-hint: [optional: check - validate only, create nothing]
---

Put the winners in Google Ads: one Search campaign, one ad group, one responsive search ad, all PAUSED.

1. Run `python3 code/publish_ads.py`. This is validate only: Google checks the whole request and nothing is created.
   - "STOPPED: account ... is ..." means `GOOGLE_ADS_CUSTOMER_ID` in `.env` points at a different business. Say so and stop. Never create in an account whose name doesn't match.
   - "NOT ENOUGH TO BUILD ONE AD" means fewer than 15 headlines or 4 descriptions in tier S. Say so and point to /write-ads.
   - "Google rejected it" lists the field and the reason. Fix the line (back through /write-ads if it's ad text) and run it again.
2. If $ARGUMENTS says check or validate, stop here and report.
3. Otherwise asking for the paused campaign is the go-ahead. Run `python3 code/publish_ads.py --apply`. Everything lands PAUSED. A paused campaign can't spend, whatever its budget.
4. If `code/build_dashboard.py` exists, run `python3 code/build_dashboard.py`.
5. Report back in a few short lines:
   - the account, campaign name and id, ad group, ad id, and that all three are PAUSED
   - the daily budget it will use once someone enables it, and the keywords
   - what's left before enabling: review it in Google Ads, check conversion tracking, add a call asset and sitelinks, and a landing page that matches the ad if it points at the home page
   - `data/published.json` and `dashboard/index.html`

Rules:
- Never enable anything. Never edit or remove anything already in the account.
- Never use `--allow-untested` with `--apply`. Only tier S lines go live.
- Never print anything from `.env`.
- No em-dashes.
