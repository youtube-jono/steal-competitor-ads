# Steal Competitor Ads

Pull every ad your competitors run, find the ones that are actually winning, learn your business, write ads that beat theirs, and push them into Google Ads paused.

## Commands, in order
1. `/pull-ads` - every ad from Google, Facebook/Instagram, TikTok and LinkedIn, plus the landing page behind each, into the dashboard
2. `/rank-ads` - score every ad, grade competitor ads A, B or C
3. `/learn-business` - read your website and Google reviews into `context/`
4. `/write-ads` - write ads that beat their A tier: rules, then the buyer test. Survivors are S tier.
5. `/publish-ads` - a paused Search campaign in your Google Ads account

## Files
- `context/business.md`, `context/proof.md`, `context/competitors.md` - who you are, what you can prove, who you're up against. Every command reads them.
- `data/` - pulled ads, pages, rankings, new ads, publish results. Generated, safe to delete.
- `dashboard/index.html` - open it in a browser. Rebuilt by every command.
- `code/` - the scripts the commands call.
- `references/` - how ranking, the gates and ad specs work.

## Rules
- Never open facebook.com or any Meta page from this computer. Meta ads come through Apify only.
- Keys live in `.env` (APIFY_TOKEN, GOOGLE_ADS_*). Never print them, never commit `.env`.
- Days running is a tie-breaker, never the main score. A year at $1 a day is not a winner.
- Every claim in a new ad must be in `context/proof.md`. Never a competitor's name in an ad.
- Nothing in Google Ads is created enabled. Paused only.
- No em-dashes in anything you write.
