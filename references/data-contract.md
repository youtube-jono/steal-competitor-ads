# Data contract

Every script reads and writes these shapes. Fields that a platform doesn't give are `null`, never guessed.

## data/ads.json (written by /pull-ads)
A list. One object per ad:
- `id` - stable string, `<platform>-<native id>`
- `platform` - `google` | `meta` | `tiktok` | `linkedin`
- `advertiser` - display name; `domain` - the competitor's domain from context/competitors.md
- `format` - `text` | `image` | `video` | `carousel`
- `headline`, `body`, `description`, `cta`, `display_url`
- `landing_url` - the advertiser's page (never a facebook.com URL)
- `media` - `{ "image": url|null, "video": url|null, "thumbnail": url|null }`
- `placements` - list, e.g. `["facebook","instagram"]`
- `start_date`, `last_seen` - ISO dates; `days_running` - integer; `active` - bool
- `copies` - Meta collationCount or null
- `impressions_rank` - 1-based position in the impressions-sorted pull (Meta), else null
- `impressions_range` - `[low, high]` where a library gives one (EU), else null
- `eu_reach` - integer or null; `reach_per_day` - number or null
- `spyfu_share` - percentageAdsServed (Google) or null
- `ctr_rank` - TikTok Creative Center CTR ranking or null
- `source` - the Apify actor id

## data/pages.json (written by /pull-ads)
A list. One object per unique landing URL:
- `url`, `screenshot` (path under data/pages/), `title`, `h1`
- `offer`, `price`, `proof` (list of short strings), `form_fields` (integer), `is_homepage` (bool)
- `ad_ids` - the ads that point here

## data/ranked.json (written by /rank-ads)
The ads list plus, per ad: `score` (0-100), `tier` (`A` | `B` | `C`), `grade` (confidence `A` | `B` | `C`), `rank` (1 = best, per platform), `why` (one short line naming the clues that scored it).

## context/business.md and context/proof.md (written by /learn-business)
Human-readable, no tables. proof.md lists only claims with a source: rating and review count, years, licences, guarantees, prices, named results.

## data/new-ads.json (written by /write-ads)
A list of our drafts. Per draft: `platform`, `headline`, `description` (Google: headlines up to 30 characters, descriptions up to 90), `angle`, `beats` (ids of the A-tier ads it was tested against), `gate_rules` (`pass` | reason), `buyer_test` (`{ "wins": n, "runs": 5 }`), `tier` (`S` if it passed both, else null).

## data/published.json (written by /publish-ads)
`{ "customer_id", "campaign_id", "campaign_name", "ad_group_id", "ad_ids": [], "status": "PAUSED", "validate_only": bool, "at": iso }`
