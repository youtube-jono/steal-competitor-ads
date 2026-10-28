# Ad specs

What each slot holds. `code/gate_rules.py` enforces the character limits. A line over its slot dies before the buyer test sees it.

## Google responsive search ad (the one we publish)

- 15 headlines, 30 characters each. Google shows up to 3 at a time, in any order, so every headline has to stand alone.
- 4 descriptions, 90 characters each. Up to 2 show. Write them to 60-70 characters, shorter wins.
- 2 display paths, 15 characters each. Words the searcher already has in their head, e.g. `google-ads/sprint` is wrong, `google-ads/management` is right.
- Nothing is pinned. Google rotates all 15 and learns which combinations win.
- A `{LOCATION(City):your city}` tag counts as its fallback text. No `{KeyWord:...}` insertion.
- Sentence case. No exclamation mark in a headline, at most one in a description. No phone number in the text, it goes in a call asset.
- Since February 2025 a headline can also show in the description slot or a sitelink slot. Every line has to read alone.

## Meta (Facebook and Instagram) feed ad

- Primary text: 125 characters show before "See more". The hook lives there.
- Headline: 40 characters, about 27 show on a phone.
- Description: 30 characters, often hidden on mobile.
- The image or video does most of the work. Text over 20% of the image doesn't get rejected any more, but it still costs reach.

## TikTok in-feed ad

- Ad text: 12 to 100 characters.
- The first 2 seconds of the video are the ad. Text on screen, a face, the problem.

## LinkedIn single image ad

- Intro text: 150 characters before it truncates (600 max).
- Headline: 70 characters before it truncates (200 max).

## In data/new-ads.json

One object per draft. A Google draft is the ad the way a phone shows it: 3 headlines and 2 descriptions, as lists, one angle. That is also what the buyer test puts beside their ads. `code/publish_ads.py` builds the responsive ad from the S-tier drafts, taking headlines in turn from each draft so every winning angle gets in. Meta, TikTok and LinkedIn drafts hold single strings: `headline`, `body` (the primary text) and `description`.

```
{ "id": "g01", "platform": "google", "angle": "price",
  "headline": ["Know the price first", "No surprises on the bill", "A written price, then the job"],
  "description": ["You know the price before we pick up a tool. A fixed price on the phone for most jobs.",
                  "Bigger job? You get a written price before anything starts. No surprises on the bill."],
  "beats": [], "gate_rules": null, "buyer_test": null, "tier": null }
```

The scripts fill in the rest: `gate_rules` ("pass" or the reasons), `buyer_test` (`{"wins": 4, "runs": 5}`), `beats` (the ids of the three ads it was tested against), `buyer_notes` (why the buyer picked theirs), and `tier` ("S" or null).
