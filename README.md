# Steal Competitor Ads

Pull every ad your competitors run on Google, Facebook, Instagram, TikTok and LinkedIn, plus the page behind each one. Find the ones that are actually winning. Learn your business, write ads that beat theirs, and put them in Google Ads as a paused campaign.

## Setup

1. Install Claude Code, clone this repo and open the folder in it.
2. Run `pip3 install -r requirements.txt`, then `python3 -m playwright install chromium`.
3. Copy `.env.example` to `.env` and fill it in. Each key says where to get it.

## The five prompts

Type these in order. Open `dashboard/index.html` after any of them.

1. `Pull every ad competitor1.com, competitor2.com and competitor3.com run on Google, Facebook, TikTok and LinkedIn, plus the page behind each ad, and put it in a dashboard.`
2. `Rank them. Which ads are actually winning?`
3. `Learn my business from yoursite.com and my Google reviews.`
4. `Write me ads that beat their best ones. Run them through the rules and the buyer test.`
5. `Put the winners in my Google Ads account as a paused campaign.`

Each one runs a command in `.claude/commands/`: `/pull-ads`, `/rank-ads`, `/learn-business`, `/write-ads`, `/publish-ads`.

## Good to know

- No ad library shows what an ad spends. The ranking is built from delivery clues, and days running only breaks ties. A year at $1 a day is not a winner. `references/ranking-research.md` has the method.
- Your ads only count if they pass the rules and then beat the competitors' best three in a blind buyer test, 4 runs out of 5. `references/gates.md` has the rules.
- TikTok's library only covers ads shown in Europe, so local businesses usually show zero there. LinkedIn is mostly business-to-business.
- Google text ads come back as images and are read with Apple's built-in text reader, so that step needs a Mac. On other computers those ads show without their text.
- The Google Ads campaign is created paused. Nothing spends until you turn it on.
- Facebook is never opened from your computer. Meta ads come through Apify.
- A full run costs about $1 in Apify and a few cents in DataForSEO.
