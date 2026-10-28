---
description: Write ads that beat the competitors' A tier - the rules, then the blind buyer test. Survivors are tier S.
argument-hint: [optional: google (default) | meta | both]
---

Write ads that beat their best ones. Google first: the goal is one responsive search ad, which needs 15 headlines and 4 descriptions in tier S. Meta only if $ARGUMENTS says meta or both.

## 0. Read first

- `context/business.md`, `context/proof.md`, `context/competitors.md`
- `references/gates.md` (the three gates) and `references/ad-specs.md` (slot sizes, the draft shape)
- `data/ranked.json`, their tier A on the platform you're writing for. No file: stop and say run /rank-ads first. No `context/proof.md`: stop and say run /learn-business first.

Before writing a word, list in a few lines what their A tier says (offer, proof, angle) and what none of them say. The gap is where ours wins. Proof only comes from the "Can claim" sections of `proof.md`. If `## The gap` says there's no client result, no line may promise an outcome.

## 1. Write the drafts

Write `data/new-ads.json` fresh (replace it). One object per draft, shaped like `references/ad-specs.md`:

- Google draft = the ad the way a phone shows it: `"headline": [3 lines]`, `"description": [2 lines]`, one `"angle"` from: offer, speed, price, trust, risk-reversal, ask. Ids `g01`, `g02`...
- Headlines 30 characters, descriptions 90. Count them. Sentence case. Every line must read alone, in any order.
- At least 8 drafts on the first pass, covering all six angles, so 5 or more can survive.
- Meta draft (only if asked): `"headline"`, `"body"` (primary text, 125), `"description"` (30), as strings. Ids `m01`...
- Set `beats: []`, `gate_rules: null`, `buyer_test: null`, `tier: null`.

## 2. Gate 1 - the rules

Run `python3 code/gate_rules.py`. It sends back any draft with a line that breaks a rule, naming the line and the reason. Rewrite those lines and run it again until every draft passes or you drop it. Never edit `references/gates.md` or `context/proof.md` to let a line through.

## 3. Gate 2 - would they click ours instead of theirs?

1. Run `python3 code/buyer_test.py build`. It puts each draft beside their three best ads on the same platform, brand names stripped, order shuffled, five runs each, all questions mixed into `data/buyer-sheet.md`. The answer key goes to `data/buyer-key.json`.
2. Launch ONE fresh subagent (Agent tool, general-purpose) as the buyer, with exactly this prompt and nothing else:

   > Read data/buyer-sheet.md in this project and nothing else. You are the person described at the top of it. Answer every question as that person: on a phone, three seconds per option, pick the one you would actually tap. Write all your answers as JSON to data/buyer-picks.json in the format the sheet shows, with the exact words that won each pick. Then reply "done".

   Never tell the buyer which option is ours. Never show it `data/new-ads.json`, `data/buyer-key.json` or this conversation. You wrote the drafts, so you can't be the judge.
3. Run `python3 code/buyer_test.py record`. Ours must win 4 of 5 runs. Gate 1 plus gate 2 = tier S. It also reports gate 3 and whether there's enough for one Google ad.

## 4. The gate never lowers. The writing goes again.

Not READY means rewrite, not re-ask. For every draft that went back:
- Read why the buyer picked theirs (`buyer_notes` in the file). Change the line, not the wording: a claim from `proof.md` none of the three rivals make, a number nobody else can say, a fear their lines leave untouched.
- Write new drafts for any angle gate 3 says is missing.
- Run gate 1, then `buyer_test.py build` again (it only tests new and rewritten drafts), the buyer subagent again (a fresh one), then `record`.

Loop until `record` says READY for /publish-ads and gate 3 passes. Three or four rounds is normal. After four rounds still short, stop and say exactly which proof is missing. That's the finding, not a copywriting problem.

## 5. Finish

1. If `code/build_dashboard.py` exists, run `python3 code/build_dashboard.py`.
2. Report back in a few short lines: how many drafts went in, how many passed the rules, how many are tier S, the one line you'd put money on, and per angle what beat their best and what died and why. If the proof gap limited the writing, say so.

Rules:
- Every number and claim comes from `context/proof.md`. Never a competitor's name in an ad.
- Never print anything from `.env`. Never open facebook.com or any Meta page.
- No em-dashes in anything you write.
