"""Read your website and your Google reviews into data/business.json.

    python3 code/learn_business.py                    # site + Google reviews
    python3 code/learn_business.py --no-reviews       # site only, spends nothing
    python3 code/learn_business.py --place-url "https://www.google.com/maps/place/..."

Reads BUSINESS_NAME and SITE_BASE_URL from .env (and MAIN_CITY to narrow the Maps search).
Claude then turns data/business.json into context/business.md and context/proof.md.

- The site: headless Chromium (Playwright), the home page plus up to 11 pages it links to on
  the same domain. Plain requests is the fallback if a browser can't start.
- Google reviews: Apify. First a Google Maps search for the business name (compass/crawler-
  google-places, 5 places max, about $0.02), matched on your domain or exact name. Then up to
  40 reviews from that place (compass/google-maps-reviews-scraper, about $0.03). No match means
  no Google Business Profile was found, and the file says so. Hard cap $0.50 per run.

Keys are read from .env and never printed. Social links on your site are listed, never opened.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "business.json"
APIFY = "https://api.apify.com/v2"
MAPS_ACTOR = "compass~crawler-google-places"
REVIEWS_ACTOR = "compass~google-maps-reviews-scraper"

MAX_PAGES = 12
TEXT_LIMIT = 8000
MAX_PLACES = 5
MAX_REVIEWS = 40
SPEND_CAP_USD = 0.50
MAPS_CHARGE_CAP = 0.50      # the Maps actor's minimum allowed cap
REVIEWS_CHARGE_CAP = 0.10

# Pages most likely to hold offers and proof get read first.
PRIORITY = ("pricing", "price", "service", "offer", "guarantee", "about", "review", "testimonial",
            "case", "result", "faq", "contact", "work", "client")
SKIP_PATH = re.compile(r"\.(pdf|jpe?g|png|gif|svg|webp|zip|mp4)$|/(wp-admin|cart|checkout|login)", re.I)
NEVER_OPEN = ("facebook.com", "fb.com", "instagram.com", "meta.com", "messenger.com", "threads.net")

MONEY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?\s?[kK]?\+?(?:\s?(?:/|a|per)\s?(?:month|mo|year|yr|hour|hr))?")
PHONE_RE = re.compile(r"\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
CLAIM_RE = re.compile(
    r"[^.\n]*\b(guarantee|warrant|certified|licen[cs]ed|insured|award|years|since \d{4}|"
    r"clients?|customers?|reviews?|stars?|rated|subscribers?|members?|month[- ]to[- ]month|"
    r"no (?:contract|lock)|keep everything|refund|live in)\b[^.\n]*", re.I)


# ---------------------------------------------------------------- env

def load_env() -> dict:
    values = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def domain_of(url: str) -> str:
    host = urlparse(url if "//" in url else f"https://{url}").netloc.lower()
    return host[4:] if host.startswith("www.") else host


# ---------------------------------------------------------------- the site

def facts_from_text(text: str) -> dict:
    claims = []
    for m in CLAIM_RE.finditer(text):
        line = " ".join(m.group(0).split())
        if 12 <= len(line) <= 220 and line not in claims:
            claims.append(line)
    return {
        "prices": sorted(set(" ".join(p.split()) for p in MONEY_RE.findall(text))),
        "phones": sorted(set(p.strip() for p in PHONE_RE.findall(text) if len(re.sub(r"\D", "", p)) >= 10)),
        "emails": sorted(set(EMAIL_RE.findall(text))),
        "claim_lines": claims[:40],
    }


def pick_links(base: str, links: list, seen: set) -> list:
    site = domain_of(base)
    keep = []
    for href in links:
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base, href).split("#")[0].split("?")[0].rstrip("/")
        if domain_of(url) != site or SKIP_PATH.search(url) or url in seen or url in keep:
            continue
        keep.append(url)
    keep.sort(key=lambda u: next((i for i, w in enumerate(PRIORITY) if w in u.lower()), len(PRIORITY)))
    return keep


def external_links(links: list, site: str) -> list:
    out = []
    for href in links:
        if href and href.startswith("http") and domain_of(href) != site and href not in out:
            out.append(href)
    return out


def read_site_playwright(base: str) -> list:
    from playwright.sync_api import sync_playwright

    pages, seen, queue = [], set(), [base.rstrip("/")]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        while queue and len(pages) < MAX_PAGES:
            url = queue.pop(0)
            if url in seen or any(bad in domain_of(url) for bad in NEVER_OPEN):
                continue
            seen.add(url)
            try:
                resp = page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception as exc:  # noqa: BLE001 - one dead page never stops the read
                pages.append({"url": url, "status": None, "error": str(exc)[:200]})
                continue
            status = resp.status if resp else None
            text = page.inner_text("body") if status and status < 400 else ""
            links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
            pages.append(page_record(url, status, page.title(), text,
                                     page.eval_on_selector_all("h1", "els => els.map(e => e.innerText)"),
                                     page.eval_on_selector_all("h2", "els => els.map(e => e.innerText)"),
                                     page.eval_on_selector_all('meta[name="description"]',
                                                               "els => els.map(e => e.content)"),
                                     links))
            queue += pick_links(url, links, seen | set(queue))
        browser.close()
    return pages


def read_site_requests(base: str) -> list:
    pages, seen, queue = [], set(), [base.rstrip("/")]
    while queue and len(pages) < MAX_PAGES:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (learn_business.py)"})
        except requests.RequestException as exc:
            pages.append({"url": url, "status": None, "error": str(exc)[:200]})
            continue
        html = r.text
        strip = lambda s: " ".join(re.sub(r"<[^>]+>", " ", s).split())
        body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
        links = re.findall(r'href="([^"]+)"', html)
        pages.append(page_record(
            url, r.status_code, strip("".join(re.findall(r"<title>(.*?)</title>", html, re.S))),
            strip(body), [strip(h) for h in re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S)],
            [strip(h) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S)],
            re.findall(r'<meta name="description" content="([^"]*)"', html), links))
        queue += pick_links(url, links, seen | set(queue))
    return pages


def page_record(url, status, title, text, h1s, h2s, metas, links) -> dict:
    text = re.sub(r"\n\s*\n+", "\n", text or "").strip()
    return {
        "url": url, "status": status, "title": (title or "").strip(),
        "meta_description": (metas or [""])[0], "h1": [h.strip() for h in h1s if h.strip()],
        "h2": [h.strip() for h in h2s if h.strip()][:20],
        "text": text[:TEXT_LIMIT], "text_truncated": len(text) > TEXT_LIMIT,
        "facts": facts_from_text(text),
        "external_links": external_links([urljoin(url, l or "") for l in links], domain_of(url))[:20],
    }


def read_site(base: str) -> list:
    try:
        return read_site_playwright(base)
    except Exception as exc:  # noqa: BLE001 - no browser on this machine is not a dead end
        print(f"  ! headless browser failed ({str(exc)[:120]}), falling back to plain requests")
        return read_site_requests(base)


# ---------------------------------------------------------------- Google reviews

class Apify:
    def __init__(self, tokens: list):
        self.tokens = [t for t in tokens if t]
        self.spent = 0.0

    def _headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    def run(self, actor: str, actor_input: dict, cap: float) -> list:
        if self.spent >= SPEND_CAP_USD:
            raise RuntimeError(f"stopped at the ${SPEND_CAP_USD:.2f} spend cap for this run")
        last_err = None
        for token in self.tokens:
            try:
                r = requests.post(f"{APIFY}/acts/{actor}/runs", headers=self._headers(token),
                                  params={"waitForFinish": 240, "maxTotalChargeUsd": cap},
                                  json=actor_input, timeout=280)
                if r.status_code in (401, 402, 403):
                    last_err = f"token rejected or out of credit ({r.status_code})"
                    continue
                r.raise_for_status()
                run = self._wait(token, r.json()["data"])
                self.spent += self._cost(run)
                if run.get("status") != "SUCCEEDED":
                    raise RuntimeError(f"{actor} ended {run.get('status')}")
                items = requests.get(f"{APIFY}/datasets/{run['defaultDatasetId']}/items",
                                     headers=self._headers(token), params={"clean": "true"}, timeout=60)
                items.raise_for_status()
                return items.json()
            except requests.RequestException as exc:
                last_err = str(exc)[:200].replace(token, "***")
        raise RuntimeError(last_err or "no APIFY_TOKEN in .env")

    def _wait(self, token, run):
        for _ in range(40):
            if run.get("status") not in ("READY", "RUNNING"):
                return run
            time.sleep(6)
            run = requests.get(f"{APIFY}/actor-runs/{run['id']}", headers=self._headers(token),
                               timeout=30).json()["data"]
        return run

    @staticmethod
    def _cost(run) -> float:
        """Pay-per-event actors bill events, not compute. Fall back to the usage figure."""
        events = run.get("chargedEventCounts") or {}
        prices = ((run.get("pricingInfo") or {}).get("pricingPerEvent") or {}).get("actorChargeEvents") or {}
        total = 0.0
        for name, count in events.items():
            info = prices.get(name) or {}
            price = info.get("eventPriceUsd")
            if price is None:
                tiers = info.get("eventTieredPricingUsd") or {}
                price = max((t.get("tieredEventPriceUsd", 0) for t in tiers.values()), default=0)
            total += (price or 0) * count
        return round(float(run.get("usageTotalUsd") or 0) or total, 4)


def find_place(apify: Apify, name: str, site_domain: str, location: str | None):
    actor_input = {"searchStringsArray": [name], "maxCrawledPlacesPerSearch": MAX_PLACES,
                   "language": "en", "maxReviews": 0, "maxImages": 0, "scrapePlaceDetailPage": False}
    if location:
        actor_input["locationQuery"] = location
    places = apify.run(MAPS_ACTOR, actor_input, MAPS_CHARGE_CAP)
    for place in places:
        if site_domain and domain_of(place.get("website") or "") == site_domain:
            return place, places, "matched on website"
    for place in places:
        if (place.get("title") or "").strip().lower() == name.strip().lower():
            return place, places, "matched on exact name (no website on the profile)"
    return None, places, None


def read_reviews(apify: Apify, place_url: str) -> list:
    items = apify.run(REVIEWS_ACTOR, {"startUrls": [{"url": place_url}], "maxReviews": MAX_REVIEWS,
                                      "reviewsSort": "newest", "language": "en", "personalData": False},
                      REVIEWS_CHARGE_CAP)
    reviews = []
    for it in items:
        text = (it.get("text") or it.get("textTranslated") or "").strip()
        reviews.append({"stars": it.get("stars"), "text": text[:600],
                        "date": (it.get("publishedAtDate") or "")[:10],
                        "owner_reply": bool(it.get("responseFromOwnerText"))})
    return reviews


def google_reviews(env: dict, site_domain: str, place_url: str | None, location: str | None) -> dict:
    apify = Apify([env.get("APIFY_TOKEN"), env.get("APIFY_TOKEN_BACKUP")])
    name = env.get("BUSINESS_NAME", "")
    out = {"searched_for": name, "location": location, "found": False, "spend_usd": 0.0}
    try:
        place, candidates, how = (None, [], "given in --place-url") if place_url else \
            find_place(apify, name, site_domain, location)
        if not place_url and not place and location:
            # A remote business may not sit near its main city on Maps. One wider search.
            place, more, how = find_place(apify, name, site_domain, None)
            candidates += more
        out["candidates"] = [{"title": c.get("title"), "website": c.get("website"),
                              "address": c.get("address"), "reviews": c.get("reviewsCount")}
                             for c in candidates]
        if place_url or place:
            url = place_url or place.get("url")
            out.update({"found": True, "how": how, "place_url": url})
            if place:
                out.update({"title": place.get("title"), "rating": place.get("totalScore"),
                            "review_count": place.get("reviewsCount"),
                            "address": place.get("address"), "category": place.get("categoryName")})
            out["reviews"] = read_reviews(apify, url) if (place_url or (place.get("reviewsCount") or 0)) else []
            if place_url and out["reviews"]:
                stars = [r["stars"] for r in out["reviews"] if r.get("stars")]
                out["rating_of_pulled"] = round(sum(stars) / len(stars), 2) if stars else None
        else:
            out["note"] = (f"No Google Business Profile matched {name!r} on {site_domain}. "
                           "Ads cannot quote a Google rating or review count.")
    except Exception as exc:  # noqa: BLE001 - reviews failing never loses the site read
        out["error"] = str(exc)[:300]
    out["spend_usd"] = round(apify.spent, 4)
    return out


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Read your site and Google reviews into data/business.json")
    ap.add_argument("--no-reviews", action="store_true", help="skip Google reviews (spends nothing)")
    ap.add_argument("--place-url", help="your Google Maps place URL, if the search can't find it")
    ap.add_argument("--location", help="narrow the Maps search, e.g. 'City, Country' (default MAIN_CITY)")
    args = ap.parse_args()

    env = load_env()
    base = env.get("SITE_BASE_URL", "").strip()
    name = env.get("BUSINESS_NAME", "").strip()
    if not base or not name:
        sys.exit("Set BUSINESS_NAME and SITE_BASE_URL in .env first.")
    if not base.startswith("http"):
        base = "https://" + base
    site = domain_of(base)

    print(f"Reading {base} ...")
    pages = read_site(base)
    ok = [p for p in pages if p.get("status") and p["status"] < 400]
    print(f"  {len(ok)} of {len(pages)} pages read")
    if not ok:
        sys.exit(f"Couldn't read any page on {base}. Is the site up?")

    google = {"skipped": True}
    if not args.no_reviews:
        location = args.location or (env.get("MAIN_CITY") or None)
        print(f"Looking for {name!r} on Google Maps{f' near {location}' if location else ''} ...")
        google = google_reviews(env, site, args.place_url, location)
        if google.get("error"):
            print(f"  ! reviews failed: {google['error']}")
        elif google.get("found"):
            print(f"  found: {google.get('title') or google.get('place_url')} · "
                  f"{google.get('rating')} stars · {google.get('review_count')} reviews · "
                  f"{len(google.get('reviews') or [])} pulled")
        else:
            print(f"  {google.get('note')}")
        print(f"  Apify spend this run: ${google.get('spend_usd', 0):.3f}")

    all_text = "\n".join(p.get("text", "") for p in ok)
    result = {
        "business_name": name, "site": base,
        "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "site_facts": facts_from_text(all_text),
        "pages": pages, "google": google,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUT.relative_to(ROOT)} · prices seen: {', '.join(result['site_facts']['prices']) or 'none'}")
    print("Next: Claude writes context/business.md and context/proof.md from it.")


if __name__ == "__main__":
    main()
