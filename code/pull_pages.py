"""Landing pages: screenshot and read every unique advertiser landing_url in data/ads.json.

Headless Chromium at 1440 wide. Saves data/pages/<name>.png (above the fold) and
data/pages/<name>-full.png (full page). Every request to a Meta host (pixels, embeds,
redirects) is blocked, so this never touches facebook.com, instagram.com or meta.com.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import _apify as ap

WIDTH, HEIGHT = 1440, 900
MAX_FULL_HEIGHT = 9000
CONCURRENCY = 5
MAX_PAGES = 60
NAV_TIMEOUT_MS = 35000
TRACKING = re.compile(r"^(utm_|gclid|gbraid|wbraid|gad_|fbclid|msclkid|ttclid|li_fat_id|hsa_|_hs|mc_|elq|leadsource|campaign_id|adset_id|ad_id|placement|cid$)", re.I)

PRICE_RE = re.compile(r"(?:from|starting at|only|just)?\s*\$\s?\d[\d,]*(?:\.\d{2})?\s*(?:k\b)?"
                      r"(?:\s*(?:/|per)\s*(?:mo(?:nth)?|month|yr|year|hr|hour|week|wk))?", re.I)
OFFER_WORDS = re.compile(r"\b(free|audit|consult\w*|strategy (?:call|session)|plan|quote|proposal|trial|demo|"
                         r"discount|% off|guarantee\w*|bonus|no contract|risk[- ]free|analysis|report|"
                         r"assessment|review|get started|book|schedule|claim)\b", re.I)
PROOF_WORDS = re.compile(r"(\b\d[\d,.]*\+?\s*(?:k\+?|m\+?)?\s*(?:reviews?|clients?|customers?|businesses|"
                         r"companies|brands|case studies|years?|projects|leads|calls|rankings|ratings?|"
                         r"locations|campaigns|users|members)\b|\b\d(?:\.\d)?\s*(?:/\s*5|stars?|-star)\b|"
                         r"\b5[- ]star\b|\btrusted by\b|\bgoogle partner\b|\bpremier partner\b|\baward|"
                         r"\bbbb\b|\binc\.? ?5000\b|\bas seen (?:on|in)\b|\bfeatured in\b|\b\d{2,3}%|\brated\b|"
                         r"\bguarantee)", re.I)

EXTRACT_JS = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const h1 = [...document.querySelectorAll('h1')].find(vis);
  const heads = [...document.querySelectorAll('h1,h2,h3')].filter(vis).slice(0, 12)
     .map(e => e.innerText.trim()).filter(Boolean);
  const buttons = [...document.querySelectorAll('a,button,input[type=submit]')].filter(vis)
     .filter(e => { const r = e.getBoundingClientRect(); return r.top < 1400; })
     .map(e => (e.innerText || e.value || '').trim()).filter(t => t && t.length < 60).slice(0, 40);
  const fields = [...document.querySelectorAll('input,select,textarea')].filter(vis).filter(e => {
     const t = (e.getAttribute('type') || '').toLowerCase();
     return !['hidden','submit','button','image','reset','search'].includes(t); });
  const NUM = /^[$€£]?\d[\d,.]*\s*(\+|%|x|k\+?|m\+?|\/5)?\+?$/i;
  const stats = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.children.length > 0 || !vis(el)) continue;
    const t = (el.innerText || '').trim();
    if (!NUM.test(t)) continue;
    let card = el.parentElement;
    while (card && card.innerText.trim().length <= t.length + 2) card = card.parentElement;
    if (!card) continue;
    const text = card.innerText.replace(/\s+/g, ' ').trim();
    if (text.length <= 90 && !stats.includes(text)) stats.push(text);
    if (stats.length >= 12) break;
  }
  return { title: document.title || null, h1: h1 ? h1.innerText.replace(/\s+/g, ' ').trim() : null, heads, buttons, stats,
           form_fields: fields.length, text: (document.body ? document.body.innerText : '').slice(0, 60000),
           height: Math.max(document.body ? document.body.scrollHeight : 0,
                            document.documentElement ? document.documentElement.scrollHeight : 0) };
}
"""


def normalize_url(url: str) -> str:
    p = urlparse(url)
    query = urlencode([(k, v) for k, v in parse_qsl(p.query) if not TRACKING.match(k)])
    host = (p.hostname or "").lower()
    path = p.path or "/"
    return urlunparse(("https", host, path, "", query, ""))


def _file_stem(url: str) -> str:
    p = urlparse(url)
    base = re.sub(r"[^a-z0-9]+", "-", f"{(p.hostname or '').removeprefix('www.')}{p.path}".lower()).strip("-")
    return f"{base[:70]}-{hashlib.md5(url.encode()).hexdigest()[:6]}"


def _clean_lines(text: str) -> list[str]:
    out, seen = [], set()
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if 3 <= len(line) <= 160 and line.lower() not in seen:
            seen.add(line.lower())
            out.append(line)
    return out


def _offer(data: dict) -> str | None:
    candidates = ([data.get("h1")] if data.get("h1") else []) + data.get("heads", []) + data.get("buttons", [])
    scored = []
    for i, c in enumerate(candidates):
        c = re.sub(r"\s+", " ", c).strip()
        if not c or len(c) > 120:
            continue
        hits = OFFER_WORDS.findall(c)
        if hits:
            score = len(hits) * 2 + (3 if re.search(r"\bfree\b", c, re.I) else 0) - i * 0.05
            scored.append((score, c))
    return max(scored)[1] if scored else None


PRICE_CONTEXT = re.compile(r"(pric|\bplans? (?:start|from|cost)|package|starting|from \$|only \$|just \$|"
                           r"per month|a month|retainer|\bfees?\b|\bcosts?\b|flat rate|invest)", re.I)
NOT_PRICE = re.compile(r"(revenue|roi|saved|generated|spend|sales|profit|budget|raised|pipeline|worth|free|"
                       r"value|^\s*[+-])", re.I)


def _price(lines: list[str]) -> str | None:
    for line in lines:
        if not PRICE_CONTEXT.search(line) or NOT_PRICE.search(line):
            continue
        m = PRICE_RE.search(line)
        if m and re.search(r"\$\s?(\d{2,}|\d+\.\d{2})", m.group(0)):
            return re.sub(r"\s+", " ", m.group(0)).strip()
    return None


def _proof(lines: list[str], stats: list[str]) -> list[str]:
    out = []
    for stat in stats:  # stat cards like "500+ Happy Clients", read from the page layout
        stat = re.sub(r"(\d)\s+([+%])", r"\1\2", stat)
        if re.search(r"[a-z]{3,}", stat, re.I) and not re.search(r"(^|\s)0\s?[+%k]?(\s|$)", stat) \
                and stat not in out:
            out.append(stat)
    for line in lines:
        if any(line in o for o in out) or line.endswith("?") or re.search(r"\bhow to\b", line, re.I):
            continue
        if len(line) <= 140 and PROOF_WORDS.search(line):
            out.append(line)
        if len(out) >= 10:
            break
    return out[:10]


async def _block_meta(route):
    if ap.is_blocked_url(route.request.url):
        await route.abort()
    else:
        await route.continue_()


async def _capture(context, url: str, sem: asyncio.Semaphore) -> dict:
    stem = _file_stem(url)
    rec = {"url": url, "screenshot": None, "title": None, "h1": None, "offer": None, "price": None,
           "proof": [], "form_fields": None, "is_homepage": urlparse(url).path in ("", "/"), "ad_ids": []}
    async with sem:
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            if ap.is_blocked_url(page.url):
                ap.log(f"! page {url}: redirected to a Meta host, skipped")
                return rec
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            await page.wait_for_timeout(1200)
            ap.PAGES.mkdir(parents=True, exist_ok=True)
            fold = ap.PAGES / f"{stem}.png"
            await page.screenshot(path=str(fold), full_page=False)
            # Scroll once so lazy images and number counters load, then read and shoot the full page.
            height = min(int(await page.evaluate("document.documentElement.scrollHeight") or HEIGHT),
                         MAX_FULL_HEIGHT)
            for y in range(0, height, 900):
                await page.evaluate(f"window.scrollTo(0, {y})")
                await page.wait_for_timeout(150)
            await page.wait_for_timeout(1200)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(400)
            data = await page.evaluate(EXTRACT_JS)
            height = min(int(data.get("height") or height), MAX_FULL_HEIGHT)
            await page.screenshot(path=str(ap.PAGES / f"{stem}-full.png"),
                                  clip={"x": 0, "y": 0, "width": WIDTH, "height": max(height, HEIGHT)},
                                  full_page=True)
            lines = _clean_lines(data.get("text") or "")
            rec.update(screenshot=f"data/pages/{stem}.png", title=(data.get("title") or "").strip() or None,
                       h1=data.get("h1") or None, offer=_offer(data), price=_price(lines),
                       proof=_proof(lines, data.get("stats") or []), form_fields=int(data.get("form_fields") or 0),
                       is_homepage=urlparse(page.url).path in ("", "/"))
        except Exception as exc:
            ap.log(f"! page {url}: {exc.__class__.__name__}: {str(exc)[:120]}")
        finally:
            await page.close()
    return rec


async def _capture_all(urls: list[str]) -> list[dict]:
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": WIDTH, "height": HEIGHT},
                                            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                        "Chrome/130.0 Safari/537.36"))
        await context.route("**/*", _block_meta)
        sem = asyncio.Semaphore(CONCURRENCY)
        try:
            return await asyncio.gather(*[_capture(context, u, sem) for u in urls])
        finally:
            await browser.close()


def run(ads: list[dict]) -> list[dict]:
    by_url: dict[str, list[str]] = {}
    for ad in ads:
        url = ap.clean_url(ad.get("landing_url"))
        if not url:
            continue
        by_url.setdefault(normalize_url(url), []).append(ad["id"])
    if not by_url:
        return []
    # Most-used pages first, capped so a big advertiser can't make this run for ages.
    urls = sorted(by_url, key=lambda u: -len(by_url[u]))[:MAX_PAGES]
    pages = asyncio.run(_capture_all(urls))
    for rec in pages:
        rec["ad_ids"] = by_url[rec["url"]]
    keep = {_file_stem(p["url"]) for p in pages}
    for png in ap.PAGES.glob("*.png"):  # drop screenshots from earlier pulls
        if png.stem.removesuffix("-full") not in keep:
            png.unlink(missing_ok=True)
    return pages


if __name__ == "__main__":
    ads = json.loads((ap.DATA / "ads.json").read_text())
    pages = run(ads)
    (ap.DATA / "pages.json").write_text(json.dumps(pages, indent=2, ensure_ascii=False))
    print(f"{len(pages)} pages, {sum(1 for p in pages if p['screenshot'])} screenshots")
