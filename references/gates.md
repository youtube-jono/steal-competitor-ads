# The gates

Every new ad passes three gates, in order. A line that fails any one goes back for a rewrite. The gate never lowers. The writing goes again.

The lists below are read by `code/gate_rules.py`. Edit them here, not in the code. One phrase per bullet. Anything after " - " is a note, not part of the phrase.

## Gate 1 - the rules (mechanical, in code, no judgment)

`python3 code/gate_rules.py` checks every draft in `data/new-ads.json` and writes `gate_rules`: `pass` or the reason it died.

- Fits the slot. Google headline 30 characters, description 90. Meta headline 40, primary text 125, description 30. TikTok text 100. LinkedIn headline 70, intro 150. A `{LOCATION(City):your city}` tag counts as its fallback text. See references/ad-specs.md.
- No competitor names. Read from `context/competitors.md`, plus every advertiser name in `data/ads.json`.
- Every number is in `context/proof.md`, under a "Can claim" heading, with the same unit. "8 weeks" needs "8 weeks" in the proof, not just an 8 somewhere. The Hold, Never say and Gap sections never count as proof.
- Every claim word below is in `context/proof.md` too. "Guaranteed" needs a guarantee on file.
- Nothing from the "Never say" list in `context/proof.md`, and nothing from the banned list below.
- No ALL CAPS words, except the acronyms below. No "!!". No "!" in a Google headline, and at most one in a Google description.
- No phone numbers, no emoji or symbols, no em-dashes, no repeated punctuation, no gimmick spacing ("F R E E").
- No near-duplicates. A line 88% the same as one already in the pool dies, and the first one stays.

## Gate 2 - would they click ours instead of theirs? (the buyer test)

Not "is this a good line". One question: does the buyer tap ours over theirs?

- `python3 code/buyer_test.py build` puts each surviving line beside the three A-tier competitor lines on the same platform (headline against their headlines, description against their descriptions). Brand names stripped, order shuffled, five runs, every question shuffled into one sheet: `data/buyer-sheet.md`. The answer key goes in `data/buyer-key.json`, which the buyer never sees.
- The buyer is a fresh subagent that has never seen our drafts. It reads only the sheet and answers each question as the buyer in `context/business.md`: sceptical, on a phone, three seconds per ad, has already read the competitors' ads, no reason to care about us.
- `python3 code/buyer_test.py record` scores it. Ours must be picked in at least 4 of 5 runs. Pass gate 1 and gate 2 and the line is tier S. Anything else gets no tier.
- Losers get rewritten, not re-asked. To change the verdict, change the line: a claim the three rivals don't make, a number from proof.md nobody else can say, or a fear their lines leave untouched.

## Gate 3 - the variety floor

After gates 1 and 2, the S-tier lines must cover at least 4 of the 6 angles, and no angle may hold more than a third of them. Thirty speed lines is one ad written thirty ways, and Google learns nothing from it. `buyer_test.py record` reports it. An empty angle means write more of that angle.

The six angles: offer · speed · price · trust · risk-reversal · ask. Keyword lines for the first headline slot are tagged `keyword` and sit outside the count.

## Enough for one Google ad

One responsive search ad needs 15 S-tier headlines and 4 S-tier descriptions. Fewer is not a result to report. Write more and run the gates again.

## Banned words

- #1
- number one
- best
- top-rated
- top rated
- cheapest
- lowest price
- fastest
- unbeatable
- amazing
- shocking
- miracle
- revolutionary
- world-class
- game-changer
- game changer
- secret
- hack
- click here
- risk-free
- 100% guaranteed
- act now
- don't miss
- limited time

## Claim words

- guarantee - "guaranteed" and "guarantees" too
- warranty
- certified
- licensed
- insured
- award
- rated
- review
- stars
- partner
- accredited
- refund
- money-back
- results
- proven
- trusted
- experts

## Allowed capitals

- SEO
- PPC
- CRM
- ROI
- AI
- US
- USA
- UK
- EU
- CPA
- CPC
- CPL
- CTR
- GBP
- FAQ
- B2B
- HVAC
- LLC
- GTA
- ASAP
- CEO
- DIY
- API
- SMS
- TV
- PDF
- OK
