"""Meta ads (Facebook + Instagram) through Apify only. Nothing here opens a Meta URL.

1. Find the competitor's Facebook Page: read the facebook.com links in the HTML of their
   own homepage (we never request those links), else an Ad Library keyword search for the
   brand name (home country, COUNTRY in .env) and keep the Page whose name matches.
2. Home pull: that Page's active ads, sorted by total impressions. impressions_rank = the
   order Meta returned them (1 = most delivered). Facebook URLs only go to Apify as input.
3. EU pull: the same Page in Ireland, to pick up eu_total_reach when they advertise in Europe.
"""
from __future__ import annotations

import re
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

import _apify as ap

ACTOR = "apify/facebook-ads-scraper"
US_LIMIT = 50
EU_LIMIT = 10
KW_LIMIT = 30
EU_COUNTRY = "IE"
MAX_PAGES = 2
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
FB_LINK = re.compile(r"https?://(?:www\.|m\.)?(?:facebook|fb)\.com/([A-Za-z0-9.\-_]+(?:\?id=\d+)?)", re.I)
NOT_PAGES = {"tr", "sharer", "sharer.php", "share", "share.php", "plugins", "dialog", "business", "groups",
             "events", "watch", "pages", "login", "help", "policies", "privacy", "ads", "hashtag",
             "story.php", "permalink.php", "photo.php", "l.php", "legal", "about", "marketplace", "gaming"}


def _keyword_url(keyword: str, country: str) -> str:
    # Built only to hand to Apify as actor input. Never requested from this machine.
    return ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
            f"&country={country}&q={quote(keyword)}&search_type=keyword_unordered&media_type=all"
            "&sort_data[mode]=total_impressions&sort_data[direction]=desc")


def _page_id_url(page_id: str, country: str) -> str:
    return ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
            f"&country={country}&view_all_page_id={page_id}&search_type=page&media_type=all"
            "&sort_data[mode]=total_impressions&sort_data[direction]=desc")


def _input(urls: list[str], limit: int) -> dict:
    return {"startUrls": [{"url": u} for u in urls], "resultsLimit": limit,
            "isDetailsPerAd": True, "activeStatus": "active", "sorting": "total_impressions",
            "includeAboutPage": False, "enrichWithEcommerceData": False}


def find_page_urls(domain: str) -> list[str]:
    """Facebook Page URLs linked from the competitor's own homepage (only their site is requested)."""
    found = []
    for url in (f"https://www.{domain}/", f"https://{domain}/"):
        try:
            html = requests.get(url, headers=UA, timeout=30).text
        except requests.RequestException:
            continue
        for slug in FB_LINK.findall(html):
            head = slug.split("?")[0].strip("/").lower()
            if head in NOT_PAGES or not head:
                continue
            if head == "profile.php":
                m = re.search(r"id=(\d+)", slug)
                if not m:
                    continue
                page = m.group(1)
            else:
                page = slug.split("?")[0].strip("/")
            link = f"https://www.facebook.com/{page}"
            if link.lower() not in [f.lower() for f in found]:
                found.append(link)
        if found:
            break
    return found[:MAX_PAGES]


def _run(comp: dict, tag: str, urls: list[str], limit: int) -> int:
    items = ap.run_actor(ACTOR, _input(urls, limit), label=f"meta-{tag}-{comp['domain']}",
                         max_items=limit * len(urls), timeout=290,
                         max_charge_usd=round(limit * len(urls) * 0.0065 + 0.02, 2))
    return len([i for i in items if i.get("adArchiveID") or i.get("adArchiveId")])


def _page_ids(items: list, comp: dict) -> list[str]:
    ids = []
    for it in items or []:
        pid = str(it.get("pageID") or it.get("pageId") or "")
        if pid and pid not in ids and _page_matches(it, comp):
            ids.append(pid)
    return ids[:MAX_PAGES]


def _fetch_one(comp: dict) -> tuple[str, str]:
    dom, notes = comp["domain"], []
    try:
        pages = find_page_urls(dom)
        if pages:
            notes.append(f"page from site: {', '.join(p.rsplit('/', 1)[-1] for p in pages)}")
        else:
            ap.run_actor(ACTOR, _input([_keyword_url(comp["name"], ap.COUNTRY)], KW_LIMIT),
                         label=f"meta-kw-{dom}", max_items=KW_LIMIT, timeout=290,
                         max_charge_usd=round(KW_LIMIT * 0.0065 + 0.02, 2))
            pages = [_page_id_url(pid, ap.COUNTRY) for pid in _page_ids(ap.load_raw(f"meta-kw-{dom}"), comp)]
            notes.append(f"page from keyword search: {len(pages)}")
        if not pages:
            return dom, "; ".join(notes + ["no Facebook Page found"])
        n_us = _run(comp, "us", pages, US_LIMIT)
        notes.append(f"us {n_us}")
        ids = _page_ids(ap.load_raw(f"meta-us-{dom}"), comp)
        if ids:
            notes.append(f"eu {_run(comp, 'eu', [_page_id_url(i, EU_COUNTRY) for i in ids], EU_LIMIT)}")
        return dom, "; ".join(notes)
    except Exception as exc:  # one competitor failing never stops the others
        ap.log(f"! meta {dom}: {exc}")
        return dom, "; ".join(notes + [f"failed: {exc}"])


def fetch(competitors: list[dict]) -> dict:
    with ThreadPoolExecutor(3) as pool:
        return dict(pool.map(_fetch_one, competitors))


# ---------- normalize ----------

def _page_matches(item: dict, comp: dict) -> bool:
    snap = item.get("snapshot") or {}
    brand, stem = ap.norm(comp["name"]), ap.norm(comp["domain"].split(".")[0])
    page = ap.norm(item.get("pageName") or snap.get("pageName"))
    if page and (brand in page or stem in page or (len(page) >= 6 and page in brand)):
        return True
    links = [snap.get("linkUrl"), snap.get("caption")] + [c.get("linkUrl") for c in snap.get("cards") or []]
    links += [c.get("caption") for c in snap.get("cards") or []]
    return any(link and comp["domain"] in str(link).lower() for link in links)


def _format(snap: dict) -> str | None:
    fmt = (snap.get("displayFormat") or "").upper()
    cards = snap.get("cards") or []
    if fmt == "VIDEO" or snap.get("videos"):
        return "video"
    if fmt in ("CAROUSEL", "MULTI_IMAGES", "DPA") or len(cards) > 1:
        return "carousel"
    if fmt in ("IMAGE",) or snap.get("images") or cards:
        if cards and (cards[0].get("videoHdUrl") or cards[0].get("videoSdUrl")):
            return "video"
        return "image"
    if fmt == "TEXT":
        return "text"
    return None


def _media(snap: dict) -> dict:
    vids, imgs, cards = snap.get("videos") or [], snap.get("images") or [], snap.get("cards") or []
    video = thumb = image = None
    if vids:
        video = vids[0].get("videoHdUrl") or vids[0].get("videoSdUrl")
        thumb = vids[0].get("videoPreviewImageUrl")
    if imgs:
        image = imgs[0].get("originalImageUrl") or imgs[0].get("resizedImageUrl")
    for c in cards:
        video = video or c.get("videoHdUrl") or c.get("videoSdUrl")
        thumb = thumb or c.get("videoPreviewImageUrl")
        image = image or c.get("originalImageUrl") or c.get("resizedImageUrl")
    return {"image": image, "video": video, "thumbnail": thumb or (imgs[0].get("resizedImageUrl") if imgs else None) or image}


def _range(text) -> list | None:
    """'<100' -> [0, 100]; '1K-5K' -> [1000, 5000]; anything else -> None."""
    if not text or not isinstance(text, str):
        return None
    def num(s):
        m = re.match(r"([\d.,]+)\s*([KkMm]?)", s.strip())
        if not m:
            return None
        v = float(m.group(1).replace(",", ""))
        return int(v * {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1))
    t = text.replace("–", "-").strip()
    if t.startswith("<"):
        hi = num(t[1:])
        return [0, hi] if hi is not None else None
    if t.startswith(">"):
        lo = num(t[1:])
        return [lo, None] if lo is not None else None
    parts = t.split("-")
    if len(parts) == 2 and num(parts[0]) is not None and num(parts[1]) is not None:
        return [num(parts[0]), num(parts[1])]
    return None


def _to_ad(item: dict, comp: dict) -> dict:
    snap = item.get("snapshot") or {}
    cards = snap.get("cards") or []
    first = cards[0] if cards else {}
    body = ap.text_or_none(snap.get("body")) or ap.text_or_none(first.get("body"))
    title = ap.text_or_none(snap.get("title"))
    page_name = item.get("pageName") or snap.get("pageName")
    if not title or title == page_name:
        title = ap.text_or_none(first.get("title")) or title
    landing = ap.clean_url(snap.get("linkUrl")) or next(
        (ap.clean_url(c.get("linkUrl")) for c in cards if ap.clean_url(c.get("linkUrl"))), None)
    caption = ap.text_or_none(snap.get("caption")) or ap.text_or_none(first.get("caption"))
    if caption and (ap.is_blocked_url("https://" + caption.split("/")[0]) or " " in caption):
        caption = None
    start = ap.to_date(item.get("startDateFormatted") or item.get("startDate"))
    end = ap.to_date(item.get("endDateFormatted") or item.get("endDate"))
    aaa = (item.get("ad_details") or {}).get("aaa_info") or {}
    reach = aaa.get("eu_total_reach")
    days = ap.days_between(start, end)
    imp = (item.get("impressionsWithIndex") or {}).get("impressionsText")
    return ap.blank_ad(
        id=f"meta-{item.get('adArchiveID') or item.get('adArchiveId')}", platform="meta",
        advertiser=page_name or comp["name"], domain=comp["domain"], format=_format(snap),
        headline=title, body=body,
        description=ap.text_or_none(snap.get("linkDescription")) or ap.text_or_none(first.get("linkDescription")),
        cta=ap.text_or_none(snap.get("ctaText")) or ap.text_or_none(first.get("ctaText")),
        display_url=caption, landing_url=landing, media=_media(snap),
        placements=sorted({p.lower() for p in item.get("publisherPlatform") or []}),
        start_date=start, last_seen=end, days_running=days,
        active=item.get("isActive") if isinstance(item.get("isActive"), bool) else None,
        copies=item.get("collationCount"), impressions_range=_range(imp),
        eu_reach=int(reach) if isinstance(reach, (int, float)) and reach > 0 else None,
        source=ACTOR,
    )


def _ad_id(it: dict) -> str | None:
    return it.get("adArchiveID") or it.get("adArchiveId")


def parse(competitors: list[dict]) -> list[dict]:
    ads: dict[str, dict] = {}
    for comp in competitors:
        dom = comp["domain"]
        us = ap.load_raw(f"meta-us-{dom}")
        if us is None:  # page pull failed: fall back to the keyword search, if it ran
            us = ap.load_raw(f"meta-kw-{dom}") or []
        ranks: dict[str, int] = {}  # rank restarts per Page searched
        for it in us:
            if not _ad_id(it) or not _page_matches(it, comp):
                continue
            ad = _to_ad(it, comp)
            if ad["id"] in ads:
                continue
            key = it.get("inputUrl") or ""
            ranks[key] = ranks.get(key, 0) + 1
            ad["impressions_rank"] = ranks[key]
            ads[ad["id"]] = ad
        for it in ap.load_raw(f"meta-eu-{dom}") or []:
            if not _ad_id(it) or not _page_matches(it, comp):
                continue
            eu = _to_ad(it, comp)
            if eu["id"] in ads:
                ads[eu["id"]]["eu_reach"] = ads[eu["id"]]["eu_reach"] or eu["eu_reach"]
            else:
                ads[eu["id"]] = eu  # EU-only ad: no US impressions rank
    for ad in ads.values():
        if ad["eu_reach"] and ad["days_running"]:
            ad["reach_per_day"] = round(ad["eu_reach"] / ad["days_running"], 1)
    return list(ads.values())


if __name__ == "__main__":
    comps = ap.load_competitors()
    if "--from-raw" not in sys.argv:
        print(fetch(comps))
    print(len(parse(comps)), "meta ads")
