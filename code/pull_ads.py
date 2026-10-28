"""/pull-ads: every competitor ad from Google, Meta, TikTok and LinkedIn, plus landing pages.

    python3 code/pull_ads.py              # pull fresh from Apify, then capture landing pages
    python3 code/pull_ads.py --from-raw   # rebuild ads.json/pages.json from data/raw (no spend)
    python3 code/pull_ads.py --skip-pages # ads only
    python3 code/pull_ads.py --only google,meta

Writes data/ads.json and data/pages.json (shapes in references/data-contract.md).
One platform failing never stops the others.
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import _apify as ap
import pull_google
import pull_linkedin
import pull_meta
import pull_pages
import pull_tiktok

PLATFORMS = {"google": pull_google, "meta": pull_meta, "tiktok": pull_tiktok, "linkedin": pull_linkedin}
WHY_EMPTY = {
    "tiktok": "TikTok's library only shows ads run in Europe",
    "linkedin": f"no LinkedIn ads in the {ap.COUNTRY} library for the last year",
    "meta": "no active ads on their Facebook Page",
    "google": "no ads in Google's Transparency Center for the US",
}


def _arg(name: str) -> str | None:
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    return None


def _fetch(name: str, module, competitors: list[dict]):
    t0 = time.time()
    try:
        status = module.fetch(competitors)
    except Exception as exc:
        ap.log(f"! {name} fetch failed: {exc}")
        status = {"error": str(exc)}
    return name, status, round(time.time() - t0)


def main() -> int:
    competitors = ap.load_competitors()
    if not competitors:
        print("No competitors in context/competitors.md")
        return 1
    only = _arg("--only")
    chosen = {k: v for k, v in PLATFORMS.items() if not only or k in only.split(",")}
    from_raw = "--from-raw" in sys.argv
    print("Competitors: " + ", ".join(f"{c['name']} ({c['domain']})" for c in competitors))

    started = datetime.now(timezone.utc)
    fetch_notes = {}
    if not from_raw:
        print(f"Pulling {', '.join(chosen)} through Apify (a few minutes)...")
        with ThreadPoolExecutor(len(chosen)) as pool:
            for name, status, secs in pool.map(lambda kv: _fetch(kv[0], kv[1], competitors), chosen.items()):
                fetch_notes[name] = status
                print(f"  {name} done in {secs}s: {status}")

    ads, failed = [], []
    for name, module in chosen.items():
        try:
            ads.extend(module.parse(competitors))
        except Exception as exc:
            ap.log(f"! {name} parse failed: {exc}")
            failed.append(name)
    if only:  # keep other platforms' ads from the last run
        old = ap.DATA / "ads.json"
        if old.exists():
            keep = [a for a in json.loads(old.read_text()) if a.get("platform") not in chosen]
            ads = keep + ads
    seen, unique = set(), []
    for ad in ads:
        if ad["id"] not in seen:
            seen.add(ad["id"])
            unique.append(ad)
    ads = unique
    ap.DATA.mkdir(parents=True, exist_ok=True)
    (ap.DATA / "ads.json").write_text(json.dumps(ads, indent=2, ensure_ascii=False))

    pages = []
    if "--skip-pages" not in sys.argv:
        print("Capturing landing pages...")
        try:
            pages = pull_pages.run(ads)
            (ap.DATA / "pages.json").write_text(json.dumps(pages, indent=2, ensure_ascii=False))
        except Exception as exc:
            ap.log(f"! landing pages failed: {exc}")

    spend = None if from_raw else ap.spend_since(started)
    _summary(competitors, ads, pages, failed, spend, ap.usage_usd(0))
    if not from_raw and pull_google.DFS_SPEND["usd"] is not None:
        print(f"DataForSEO spend this run: ${pull_google.DFS_SPEND['usd']:.2f}")
    return 0


def _summary(competitors, ads, pages, failed, spend, month) -> None:
    print("\nAds pulled")
    names = [c["domain"] for c in competitors]
    print(f"  {'platform':<10}" + "".join(f"{n:>18}" for n in names) + f"{'total':>8}")
    for plat in PLATFORMS:
        counts = [sum(1 for a in ads if a["platform"] == plat and a["domain"] == n) for n in names]
        flag = "  (failed)" if plat in failed else ""
        print(f"  {plat:<10}" + "".join(f"{c:>18}" for c in counts) + f"{sum(counts):>8}{flag}")
    print(f"  {'total':<10}" + "".join(f"{sum(1 for a in ads if a['domain'] == n):>18}" for n in names)
          + f"{len(ads):>8}")
    for plat in PLATFORMS:
        none = [n for n in names if not any(a["platform"] == plat and a["domain"] == n for a in ads)]
        if none:
            who = "any competitor" if len(none) == len(names) else ", ".join(none)
            print(f"  {plat}: nothing for {who}. Likely {WHY_EMPTY[plat]}.")
    shots = sum(1 for p in pages if p.get("screenshot"))
    print(f"\nLanding pages: {len(pages)} unique, {shots} screenshots in data/pages/")
    fields = [k for k in ap.blank_ad() if k not in ("id", "platform", "domain", "source", "placements", "media")]
    null_all = [k for k in fields if ads and all(a.get(k) in (None, [], "") for a in ads)]
    if null_all:
        print("Empty on every ad: " + ", ".join(null_all))
    if spend is not None:
        mtd = f" (account month to date ${month:.2f})" if month is not None else ""
        print(f"Apify spend this run: ${spend:.2f}{mtd}")
    print("Wrote data/ads.json and data/pages.json")


if __name__ == "__main__":
    sys.exit(main())
