"""Google ads from three sources, merged:
- Transparency Center (solidcode): every creative with first/last shown and days running.
  Text ads come back as images, so we OCR them on this Mac (code/_ocr.swift, Apple Vision).
- SpyFu (clearpath): share of ads served per ad, plus the competitor's paid keywords.
- DataForSEO live Google SERP (US, desktop) on those keywords: the live ad's real title,
  description, display URL and final URL, so "follow the click" works.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

import _apify as ap
import _dataforseo as dfs

ACTOR = "solidcode/ads-transparency-scraper"
SPYFU = "clearpath/spyfu-scraper"
MAX_ADS = 60
OCR_DIR = ap.RAW / "google-ocr"
OCR_SCRIPT = Path(__file__).with_name("_ocr.swift")
DFS = "dataforseo"
DFS_SPEND = {"usd": None}  # DataForSEO cost of the last fetch, for the run summary


def _transparency(comp: dict):
    domain = comp["domain"]
    try:
        items = ap.run_actor(ACTOR, {"searchQuery": domain, "region": ap.COUNTRY, "maxResults": MAX_ADS},
                             label=f"google-{domain}", max_items=MAX_ADS, max_charge_usd=0.25)
        return domain, len(items)
    except Exception as exc:  # one competitor failing never stops the run
        ap.log(f"! google {domain}: {exc}")
        return domain, f"failed: {exc}"


def fetch(competitors: list[dict]) -> dict:
    with ThreadPoolExecutor(3) as pool:
        status = dict(pool.map(_transparency, competitors))
    try:
        ap.run_actor(SPYFU, {"queries": [c["domain"] for c in competitors], "countryCode": ap.COUNTRY},
                     label="spyfu", max_charge_usd=0.1, retry_if_empty=True)
    except Exception as exc:
        ap.log(f"! spyfu: {exc}")
    spy = {(it.get("normalizedQuery") or it.get("query") or "").lower().removeprefix("www."): it
           for it in ap.load_raw("spyfu") or []}
    try:
        keywords = {c["domain"]: dfs.keywords_for(c, spy.get(c["domain"])) for c in competitors}
        found, cost = dfs.paid_ads(competitors, keywords)
        labs, labs_cost = dfs.labs_paid(competitors)
        DFS_SPEND["usd"] = round(cost + labs_cost, 4)
        status["dataforseo ads"] = {d: len(found.get(d, [])) + len(labs.get(d, [])) for d in found}
    except Exception as exc:
        ap.log(f"! dataforseo: {exc}")
    return status


# ---------- OCR for text ads ----------

def _download(url: str) -> Path | None:
    if ap.is_blocked_url(url):
        return None
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    path = OCR_DIR / (hashlib.md5(url.encode()).hexdigest()[:16] + ".png")
    if path.exists() and path.stat().st_size > 0:
        return path
    try:
        r = requests.get(url, timeout=30)
        if r.ok and r.headers.get("content-type", "").startswith("image"):
            path.write_bytes(r.content)
            return path
    except requests.RequestException:
        pass
    return None


def _ocr(paths: list[Path]) -> dict:
    """Run Apple Vision OCR on images. Returns {path: [{"text", "h", "y"}]} or {} if unavailable."""
    cache = OCR_DIR / "ocr.json"
    done = json.loads(cache.read_text()) if cache.exists() else {}
    todo = [str(p) for p in paths if str(p) not in done]
    if todo and sys.platform == "darwin" and OCR_SCRIPT.exists():
        try:
            out = subprocess.run(["swift", str(OCR_SCRIPT), *todo], capture_output=True,
                                 text=True, timeout=600)
            done.update(json.loads(out.stdout or "{}"))
            cache.write_text(json.dumps(done))
        except (subprocess.SubprocessError, ValueError, OSError) as exc:
            ap.log(f"! google OCR skipped: {exc.__class__.__name__}")
    return done


URL_LINE = re.compile(r"^(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:[/›][^\s]*)?$", re.I)
NOISE = re.compile(r"^(sponsored|ad|ads|ad ·|\W+)$", re.I)
HEAD_GAP = 0.64    # blank space under a headline line, in line-heights, that ends the headline
HEAD_SHRINK = 0.75  # a line this much smaller than the headline starts the description
DESC_GAP = 1.5     # blank space that ends the description (sitelinks start after it)


def _space(prev: dict, ln: dict) -> float:
    return (ln["y"] - (prev["y"] + prev["h"])) / max(prev["h"], 1e-6)


def _parse_text_ad(lines: list[dict]) -> dict:
    """Turn OCR lines of a rendered search ad into headline / description / display URL.

    Layout: [favicon/name] [display URL] | headline (1-2 lines) | description | sitelinks.
    Sitelinks are dropped.
    """
    lines = [dict(ln, text=ln["text"].replace("®", "").strip()) for ln in lines
             if ln.get("text", "").strip() and not NOISE.match(ln["text"].strip())]
    if not lines:
        return {}
    lines.sort(key=lambda ln: ln["y"])
    url_idx = -1
    for i, ln in enumerate(lines[:5]):
        if URL_LINE.match(re.sub(r"\s*[›>]\s*", "›", ln["text"])):
            url_idx = i
    display_url = None
    if url_idx >= 0:
        display_url = re.sub(r"^(https?://)?(www\.)?", "", re.sub(r"\s+", "", lines[url_idx]["text"])).lower()
    rest = lines[url_idx + 1:]
    if not rest:
        return {"display_url": display_url}
    head, desc = [rest[0]], []
    for prev, ln in zip(rest, rest[1:]):
        if not desc:
            top = max(x["h"] for x in head)
            ends_head = (len(head) >= 2 or _space(prev, ln) > HEAD_GAP
                         or ln["h"] < HEAD_SHRINK * top or prev["text"].endswith((".", "!", "?")))
            if not ends_head:
                head.append(ln)
                continue
            desc.append(ln)
        elif _space(prev, ln) > DESC_GAP:
            break
        else:
            desc.append(ln)
    headline = " ".join(x["text"] for x in head).strip() or None
    description = " ".join(x["text"] for x in desc).strip() or None
    return {"display_url": display_url, "headline": headline, "description": description}


# ---------- normalize ----------

SPYFU_RECENT_DAYS = 120  # SpyFu keyword ads seen in this window count as current


def _spyfu_by_domain() -> dict:
    return {(it.get("normalizedQuery") or it.get("query") or "").lower().removeprefix("www."): it
            for it in ap.load_raw("spyfu") or []}


def _spy_date(value) -> str | None:
    m = re.match(r"(\d{4})(\d{2})(\d{2})", str(value or ""))
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _spyfu_candidates(item: dict | None) -> list[dict]:
    """SpyFu ads with copy: the top ads by share, plus every ad seen on their keywords lately."""
    if not item:
        return []
    share = {a.get("adId"): a.get("percentageAdsServed") for a in item.get("adHistory") or []}
    found: dict = {}
    for a in item.get("adHistory") or []:
        if a.get("creativeAvailable") and a.get("title"):
            found[a["adId"]] = {"title": a["title"], "body": a.get("body"), "url": a.get("fullUrl"), "dates": set()}
    for kw in item.get("adKeywords") or []:
        for a in kw.get("ads") or []:
            if not (a.get("creativeAvailable") and a.get("title")):
                continue
            e = found.setdefault(a["adId"], {"title": a["title"], "body": a.get("body"),
                                             "url": a.get("fullUrl"), "dates": set()})
            if a.get("searchDateId"):
                e["dates"].add(a["searchDateId"])
    newest = max((d for e in found.values() for d in e["dates"]), default=None)
    out = []
    for ad_id, e in found.items():
        last = _spy_date(max(e["dates"])) if e["dates"] else None
        if e["dates"] and newest and ap.days_between(last, _spy_date(newest)) > SPYFU_RECENT_DAYS \
                and not share.get(ad_id, 0) >= 0.03:
            continue  # old ad that isn't one of their big ones
        body = re.sub(r"\\n.*$", "", e["body"] or "", flags=re.S).strip() or None
        out.append({"id": f"google-spyfu-{ad_id}", "title": e["title"], "description": body, "url": e["url"],
                    "start": _spy_date(min(e["dates"])) if e["dates"] else None, "last": last,
                    "share": round(float(share[ad_id]), 4) if share.get(ad_id) else None, "source": SPYFU})
    return out


def _dfs_candidates(comp: dict) -> list[dict]:
    """Paid results on the competitor's domain from the live SERP and from DataForSEO Labs."""
    out, seen = [], set()
    for label in (f"serp-{comp['domain']}", f"serp-labs-{comp['domain']}"):
        path = ap.raw_path(label)
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        for row in payload.get("items") or []:
            for it in row.get("paid") or []:
                host = (it.get("domain") or "").lower().removeprefix("www.")
                if not (host == comp["domain"] or host.endswith("." + comp["domain"])) or not it.get("title"):
                    continue
                desc = it.get("description") or " ".join(r for r in it.get("description_rows") or [] if r) or None
                key = (ap.norm(it["title"]), ap.norm(desc))
                if key in seen:
                    continue
                seen.add(key)
                crumb = (it.get("breadcrumb") or "").replace(" › ", "/").replace("›", "/")
                digest = hashlib.md5(f"{it['title']}|{desc}".encode()).hexdigest()[:10]
                out.append({"id": f"google-dfs-{digest}", "title": it["title"], "description": desc,
                            "url": it.get("url"), "display": re.sub(r"^https?://(www\.)?", "", crumb).rstrip("/") or None,
                            "start": None, "last": payload.get("fetched"), "share": None, "source": DFS,
                            "live": True})
    return out


def _merge_candidates(ads: list[dict], comp: dict, candidates: list[dict]) -> None:
    """Fill a matching creative (same headline parts) with the real copy and URL, else add a new ad."""
    mine = [a for a in ads if a["domain"] == comp["domain"]]
    ids = {a["id"] for a in ads}
    for c in candidates:
        url = ap.clean_url(c.get("url"))
        if url and re.match(r"^https?://\d+\.", url):
            continue  # numbered subdomain = a client's hosted site, not the competitor's own ad
        if c["id"] in ids:
            continue
        parts = dfs.headline_parts(c["title"])
        best, best_score = None, 0
        for ad in mine:
            if ad.get("_merged") or not ad["headline"]:
                continue
            score = len(parts & dfs.headline_parts(ad["headline"]))
            if ap.norm(ad["headline"]) == ap.norm(c["title"]):
                score += 5
            if score > best_score:
                best, best_score = ad, score
        display = c.get("display") or (re.sub(r"^https?://(www\.)?", "", url).rstrip("/") if url else None)
        if best:
            best["_merged"] = True
            best["landing_url"] = best["landing_url"] or url
            best["description"] = best["description"] or c.get("description")
            best["display_url"] = best["display_url"] or display
            best["spyfu_share"] = best["spyfu_share"] or c.get("share")
            if c.get("live"):
                best["active"] = True
            continue
        ad = ap.blank_ad(
            id=c["id"], platform="google", advertiser=comp["name"], domain=comp["domain"], format="text",
            headline=c["title"], description=c.get("description"), display_url=display, landing_url=url,
            placements=["google"], start_date=c.get("start"), last_seen=c.get("last"),
            days_running=ap.days_between(c["start"], c["last"]) if c.get("start") else None,
            active=True if c.get("live") else None, spyfu_share=c.get("share"), source=c["source"],
        )
        ad["_merged"] = True
        ads.append(ad)
        mine.append(ad)
        ids.add(ad["id"])


def parse(competitors: list[dict]) -> list[dict]:
    ads, to_ocr = [], {}
    spy = _spyfu_by_domain()
    for comp in competitors:
        items = ap.load_raw(f"google-{comp['domain']}")
        if items is None:
            continue
        for it in items:
            cid = it.get("creativeId")
            if not cid:
                continue
            fmt = (it.get("adFormat") or "").lower()
            start, last = ap.to_date(it.get("firstShown")), ap.to_date(it.get("lastShown"))
            days = it.get("approxDaysShown")
            ad = ap.blank_ad(
                id=f"google-{cid}", platform="google", advertiser=it.get("advertiserName") or comp["name"],
                domain=comp["domain"], format=fmt if fmt in ("text", "image", "video") else None,
                media={"image": it.get("imageUrl"), "video": None,
                       "thumbnail": it.get("imageUrl")},
                placements=["google"], start_date=start, last_seen=last,
                days_running=int(days) if isinstance(days, (int, float)) else ap.days_between(start, last),
                active=None, source=ACTOR,
            )
            ad["_preview"] = it.get("previewUrl")
            ad["_transparency_url"] = it.get("adUrl")
            if fmt == "text" and it.get("imageUrl"):
                to_ocr[ad["id"]] = it["imageUrl"]
            ads.append(ad)

    # OCR text ads (image downloads from Google's CDN only)
    if to_ocr:
        with ThreadPoolExecutor(8) as pool:
            paths = dict(zip(to_ocr, pool.map(_download, to_ocr.values())))
        ocr = _ocr([p for p in paths.values() if p])
        for ad in ads:
            p = paths.get(ad["id"])
            if p and str(p) in ocr:
                ad.update({k: v for k, v in _parse_text_ad(ocr[str(p)]).items() if v})

    # "active" = last shown within the last 3 days of the newest date in the pull
    newest = max((a["last_seen"] for a in ads if a["last_seen"]), default=None)
    for ad in ads:
        if newest and ad["last_seen"]:
            ad["active"] = ap.days_between(ad["last_seen"], newest) <= 3

    # Ad copy and real final URLs: DataForSEO first (live), then SpyFu (with share of ads served).
    for comp in competitors:
        _merge_candidates(ads, comp, _dfs_candidates(comp))
        _merge_candidates(ads, comp, _spyfu_candidates(spy.get(comp["domain"])))

    # The Transparency Center gives no landing URL. Display URL paths are decorative, so
    # landing_url stays null unless DataForSEO or SpyFu gave the real final URL.
    for ad in ads:
        for key in ("_preview", "_transparency_url", "_merged"):
            ad.pop(key, None)
    return ads


if __name__ == "__main__":
    comps = ap.load_competitors()
    if "--from-raw" not in sys.argv:
        print(fetch(comps))
    out = parse(comps)
    print(len(out), "google ads")
