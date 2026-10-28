# How competitor ads get ranked

`code/rank_ads.py` does this. `/rank-ads` runs it. Never edit a score by hand: if a ranking looks wrong, fix the script.

## The short answer

- No ad library shows spend, clicks or results for normal business ads. Not in the US, not in Europe.
- So a "winner" is always a score built from clues. Days running is the clue everyone uses, and it's weak alone. A year at $1 a day is not a winner.
- The ranking uses delivery clues first. Days running only breaks ties.

## FINAL METHOD

No tool, free or paid, shows a small local rival's real spend. Spy tools that claim to estimate it from European reach, which a local business doesn't have. So ads are ranked by delivery clues, strongest first.

Meta (Apify `apify/facebook-ads-scraper`, the competitor's Page, active ads, sorted by impressions):
1. Impressions rank. The order of Meta's "sort by impressions" is its hidden delivery rank. The numbers stay hidden, the order doesn't. Keep the top of the list.
2. A boost for an ad that has run 30+ days, and for one that appears under 2+ ad IDs (copies). More copies means more ad sets, which means more budget.
3. Drop anything labelled "<100" impressions, and anything under 7 days old.

Meta, when the rival also advertises in Europe:
- Rank by EU reach per day. Europe's Digital Services Act makes Meta show real reach for ads shown there.
- Spend as a rough range only: reach x 1.5 to 3 (how often each person sees it) x the local cost per 1,000 views.
- Meta's EU data starts with ads created on 22 June 2023, so older ads show no reach.

Google (Apify `solidcode/ads-transparency-scraper` and `clearpath/spyfu-scraper`):
1. SpyFu's share of ads served. Each ad gets the share of the domain's ad appearances it took. Top ads take 3-9%, the long tail about 0.5%. That gap is the winner vs $1-a-day split. It ranks ads within one competitor, it isn't a spend figure. It returns nothing for very small advertisers.
2. Days shown from Google's Ads Transparency Center breaks ties. Google has no hidden impressions sort.

TikTok and LinkedIn: EU impression ranges where the library gives one, else days running. TikTok's library only covers ads shown in Europe.

Cut, because the data is bad for local businesses: Semrush, Similarweb, Ahrefs, and spy tools that rank by likes (service ads get almost none).

## The score

- Delivery counts four times as much as time, on a log scale, so one giant ad doesn't swamp the rest.
- Missing data is never zero. An ad with dates only tops out at 60, and its confidence grade says so: A = real delivery data, B = a rank only, C = dates only.
- Under 7 days on Meta or 14 on Google is too new to judge, so it can't be a winner.
- Hiring posts, brand posts and ads with no readable text go to C.
- A small bonus when the ad lands on its own page instead of the homepage: someone invested in that page.
- Tiers per platform: A is the top 15%, never fewer than 3. C is the bottom third. B is everything between.

## Three rules behind it

- The longevity rule: a losing ad gets switched off in a week or two, so a months-long ad is paying. Signal: days running, weighted by delivery.
- The multi-variant rule: an angle that works gets scaled with extra versions. Signal: Meta's copy count, and near-identical ads grouped and counted.
- The landing page rule: a winner usually lands on a page someone built for it (its own page, reviews, a price, a form). Signal: the landing page bonus.

## Proof that days running alone misleads

A test on plumbing ads in Ireland, where Meta shows real reach: a heat pump ad 15 days old reached about 12,000 people a day. A 263-day ad from another plumber reached about 54 a day. Days running alone would have picked the wrong one.
