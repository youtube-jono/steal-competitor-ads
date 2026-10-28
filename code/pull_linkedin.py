"""LinkedIn ads from the LinkedIn Ad Library (fetch_cat), advertiser = brand, US, last year.

LinkedIn gives no run dates or impressions for US ads, and the actor's first/last seen
are scrape times, so start_date, days_running and impressions stay null.
"""
from __future__ import annotations

import re
import sys
from concurrent.futures import ThreadPoolExecutor

import _apify as ap
from pull_tiktok import brand_matches

ACTOR = "fetch_cat/linkedin-ad-library-scraper"
MAX_ADS = 25
FORMATS = {"SPONSORED_VIDEO": "video", "SPONSORED_UPDATE_CAROUSEL": "carousel", "CAROUSEL": "carousel",
           "SPONSORED_STATUS_UPDATE": "image", "SPONSORED_UPDATE": "image", "SINGLE_IMAGE": "image",
           "TEXT_AD": "text", "SPOTLIGHT": "text", "SPONSORED_MESSAGE": "text", "SPONSORED_INMAILS": "text",
           "DOCUMENT": "carousel", "EVENT": "image", "SPONSORED_UPDATE_EVENT": "image"}


def _fetch_one(comp: dict):
    dom = comp["domain"]
    try:
        items = ap.run_actor(ACTOR, {"advertiser": comp["name"], "countries": [ap.COUNTRY], "dateOption": "last-year",
                                     "maxAds": MAX_ADS},
                             label=f"linkedin-{dom}", max_items=MAX_ADS, max_charge_usd=0.05, timeout=290)
        return dom, len(items)
    except Exception as exc:
        ap.log(f"! linkedin {dom}: {exc}")
        return dom, f"failed: {exc}"


def fetch(competitors: list[dict]) -> dict:
    with ThreadPoolExecutor(3) as pool:
        return dict(pool.map(_fetch_one, competitors))


def _matches(it: dict, comp: dict) -> bool:
    # Exact advertiser match only ("acme iq" or "ACME.io" are other companies).
    return brand_matches(it.get("advertiserName") or it.get("payerName"), comp)


def _format(it: dict) -> str | None:
    kind = (it.get("creativeType") or "").upper()
    if kind in FORMATS:
        return FORMATS[kind]
    for key, fmt in (("VIDEO", "video"), ("CAROUSEL", "carousel"), ("IMAGE", "image"), ("TEXT", "text")):
        if key in kind:
            return fmt
    return None


def parse(competitors: list[dict]) -> list[dict]:
    ads = []
    for comp in competitors:
        for it in ap.load_raw(f"linkedin-{comp['domain']}") or []:
            if not it.get("adId") or not _matches(it, comp):
                continue
            media = [m for m in it.get("mediaUrls") or []
                     if "company-logo" not in m and "profile-displayphoto" not in m]
            landing = None
            for key in ("clickUrl", "destinationUrl", "landingUrl", "ctaUrl"):
                landing = landing or ap.clean_url(it.get(key))
            if landing and "linkedin.com" in landing:
                landing = None
            ads.append(ap.blank_ad(
                id=f"linkedin-{it['adId']}", platform="linkedin", advertiser=it.get("advertiserName") or comp["name"],
                domain=comp["domain"], format=_format(it), headline=ap.text_or_none(it.get("headline")),
                body=ap.text_or_none(it.get("creativeText")), cta=ap.text_or_none(it.get("callToAction")),
                landing_url=landing, media={"image": media[0] if media else None, "video": None,
                                            "thumbnail": media[0] if media else None},
                placements=["linkedin"], impressions_range=None, source=ACTOR,
            ))
    return ads


if __name__ == "__main__":
    comps = ap.load_competitors()
    if "--from-raw" not in sys.argv:
        print(fetch(comps))
    print(len(parse(comps)), "linkedin ads")
