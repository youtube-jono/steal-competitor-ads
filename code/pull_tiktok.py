"""TikTok ads from TikTok's EU ad library (lexis-solutions), sorted by impressions.

The library only covers ads shown in the EU/EEA/UK/CH, so a US-only brand returning
nothing is a valid result, not an error.
"""
from __future__ import annotations

import re
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import _apify as ap

ACTOR = "lexis-solutions/tiktok-ads-scraper"
FORMATS = {"1": "text", "2": "video", "3": "image"}


def _fetch_one(comp: dict):
    dom = comp["domain"]
    try:
        items = ap.run_actor(ACTOR, {"query": comp["name"], "country": "all",
                                     "sortBy": "impression,desc", "maxPages": 1, "quickSearch": False},
                             label=f"tiktok-{dom}", max_items=50, max_charge_usd=0.05, timeout=150)
        return dom, len(items)
    except Exception as exc:
        ap.log(f"! tiktok {dom}: {exc}")
        return dom, f"failed: {exc}"


def fetch(competitors: list[dict]) -> dict:
    with ThreadPoolExecutor(2) as pool:
        return dict(pool.map(_fetch_one, competitors))


def _num(s: str) -> int | None:
    m = re.match(r"([\d.,]+)\s*([KkMmBb]?)", s.strip())
    if not m:
        return None
    return int(float(m.group(1).replace(",", "")) * {"k": 1e3, "m": 1e6, "b": 1e9}.get(m.group(2).lower(), 1))


def _range(text) -> list | None:
    if not text or not isinstance(text, str):
        return None
    parts = text.replace("–", "-").split("-")
    if len(parts) == 2 and _num(parts[0]) is not None and _num(parts[1]) is not None:
        return [_num(parts[0]), _num(parts[1])]
    if len(parts) == 1 and _num(parts[0]) is not None:
        return [_num(parts[0]), _num(parts[0])]
    return None


LEGAL = re.compile(r"[\s,.]+(inc|llc|l\.l\.c|ltd|limited|corp|corporation|co|company|pte|plc|gmbh|"
                   r"s\.?\s?r\.?\s?o)\.?$", re.I)


def brand_matches(name: str | None, comp: dict) -> bool:
    """True only when the advertiser IS the competitor: the whole name (before any ' - tagline'),
    minus legal suffixes, equals the brand or the domain. For acme.com, 'DJ MS Acme' and 'acme iq' fail."""
    if not name:
        return False
    lead = re.split(r"\s[-|\u2013:]\s|\s?\(", name.strip(), maxsplit=1)[0].strip().lower()
    prev = None
    while prev != lead:
        prev, lead = lead, LEGAL.sub("", lead).strip(" ,.")
    return lead == comp["domain"] or lead == "www." + comp["domain"] or ap.norm(lead) == ap.norm(comp["name"])


def _on_domain(url: str | None, comp: dict) -> bool:
    host = (urlparse(url).hostname or "").lower() if url else ""
    return host == comp["domain"] or host.endswith("." + comp["domain"])


def _matches(it: dict, comp: dict) -> bool:
    name = it.get("advertiserName") or it.get("advertiserPaidForBy")
    return brand_matches(name, comp) or _on_domain(it.get("adLandingUrl"), comp)


def parse(competitors: list[dict]) -> list[dict]:
    ads = []
    for comp in competitors:
        for it in ap.load_raw(f"tiktok-{comp['domain']}") or []:
            if not it.get("adId") or not _matches(it, comp):
                continue
            start, end = ap.to_date(it.get("adStartDate")), ap.to_date(it.get("adEndDate"))
            imgs = it.get("adImageUrls") or []
            ads.append(ap.blank_ad(
                id=f"tiktok-{it['adId']}", platform="tiktok", advertiser=it.get("advertiserName") or comp["name"],
                domain=comp["domain"], format=FORMATS.get(str(it.get("adType"))),
                headline=ap.text_or_none(it.get("adTitle")), landing_url=ap.clean_url(it.get("adLandingUrl")),
                media={"image": imgs[0] if imgs else None, "video": it.get("adVideoUrl"),
                       "thumbnail": it.get("adVideoCover") or (imgs[0] if imgs else None)},
                placements=["tiktok"], start_date=start, last_seen=end, days_running=ap.days_between(start, end),
                active=(it.get("status") == "active") if it.get("status") else None,
                impressions_range=_range(it.get("adImpressions")), source=ACTOR,
            ))
    return ads


if __name__ == "__main__":
    comps = ap.load_competitors()
    if "--from-raw" not in sys.argv:
        print(fetch(comps))
    print(len(parse(comps)), "tiktok ads")
