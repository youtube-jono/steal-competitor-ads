"""DataForSEO Google SERP (live, advanced): the competitor's live search ads with the real
title, description, display URL and final URL. Creds come from .env and are never printed.
"""
from __future__ import annotations

import base64
import re
from datetime import date
from concurrent.futures import ThreadPoolExecutor

import requests

import _apify as ap

API = "https://api.dataforseo.com/v3"
SERP = f"{API}/serp/google/organic/live/advanced"
KEYWORDS_PER_COMPETITOR = 15
MAX_SPEND_USD = 0.90  # hard stop for one pull
LOCATION = {"US": 2840, "CA": 2124, "GB": 2826, "AU": 2036, "NZ": 2554, "IE": 2372}.get(ap.COUNTRY, 2840)


def _auth() -> dict | None:
    login, password = ap._ENV.get("DATAFORSEO_LOGIN"), ap._ENV.get("DATAFORSEO_PASSWORD")
    if not login or not password:
        return None
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def balance() -> float | None:
    headers = _auth()
    if not headers:
        return None
    try:
        r = requests.get(f"{API}/appendix/user_data", headers=headers, timeout=30)
        return float(r.json()["tasks"][0]["result"][0]["money"]["balance"])
    except Exception:
        return None


def keywords_for(comp: dict, spyfu_item: dict | None) -> list[str]:
    """The brand name plus the competitor's own paid keywords from SpyFu, newest and biggest first."""
    picks = [comp["name"].lower()]
    rows = []
    for kw in (spyfu_item or {}).get("adKeywords") or []:
        term = (kw.get("term") or "").strip().lower()
        if not term or kw.get("isThrottled"):
            continue
        rows.append(((kw.get("coverage") or 0) * (kw.get("clicksPerMonth") or 0), term))
    ordered = [t for _, t in sorted(rows, reverse=True)]
    # Then the rest of the keywords SpyFu sees them buying, in SpyFu's order.
    ordered += [(k.get("keyword") or "").strip().lower() for k in (spyfu_item or {}).get("paidKeywords") or []]
    for term in ordered:
        if term and term not in picks:
            picks.append(term)
        if len(picks) >= KEYWORDS_PER_COMPETITOR:
            break
    return picks


def _search(keyword: str, headers: dict) -> tuple[dict, float]:
    body = [{"keyword": keyword, "location_code": LOCATION, "language_code": "en",
             "device": "desktop", "os": "windows", "depth": 10}]
    r = requests.post(SERP, json=body, headers=headers, timeout=120)
    data = r.json()
    task = (data.get("tasks") or [{}])[0]
    return task, float(task.get("cost") or data.get("cost") or 0)


def paid_ads(competitors: list[dict], keywords: dict[str, list[str]]) -> tuple[dict, float]:
    """{domain: [paid items on that domain]}, total cost. Raw saved to data/raw/serp-<domain>.json."""
    headers = _auth()
    if not headers:
        raise RuntimeError("DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD missing in .env")
    jobs = [(c, kw) for c in competitors for kw in keywords.get(c["domain"], [])]
    spent, out, raw = 0.0, {c["domain"]: [] for c in competitors}, {c["domain"]: [] for c in competitors}
    batch = 6
    for i in range(0, len(jobs), batch):
        if spent >= MAX_SPEND_USD:
            ap.log(f"! dataforseo: stopped at ${spent:.2f} spend cap")
            break
        chunk = jobs[i:i + batch]
        with ThreadPoolExecutor(batch) as pool:
            results = list(pool.map(lambda j: (j, *_safe_search(j[1], headers)), chunk))
        for (comp, kw), task, cost in results:
            spent += cost
            items = [it for res in (task.get("result") or []) for it in (res.get("items") or [])]
            paid = [it for it in items if it.get("type") == "paid"]
            raw[comp["domain"]].append({"keyword": kw, "status": task.get("status_message"), "paid": paid})
            for it in paid:
                host = (it.get("domain") or "").lower().removeprefix("www.")
                if host == comp["domain"] or host.endswith("." + comp["domain"]):
                    out[comp["domain"]].append(dict(it, _keyword=kw))
    for dom, rows in raw.items():
        ap.save_raw(f"serp-{dom}", {"source": "dataforseo", "fetched": date.today().isoformat(), "items": rows})
    return out, round(spent, 4)


def labs_paid(competitors: list[dict]) -> tuple[dict, float]:
    """DataForSEO Labs: ads its crawler recorded for each domain (title, description, final URL).

    The live SERP often shows no ads to a crawler, so this fills the gap. Raw saved to
    data/raw/serp-labs-<domain>.json. About $0.01 per competitor.
    """
    headers = _auth()
    if not headers:
        raise RuntimeError("DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD missing in .env")
    out, spent = {}, 0.0
    for comp in competitors:
        body = [{"target": comp["domain"], "location_code": LOCATION, "language_code": "en",
                 "item_types": ["paid"], "limit": 100,
                 "order_by": ["keyword_data.keyword_info.search_volume,desc"]}]
        try:
            r = requests.post(f"{API}/dataforseo_labs/google/ranked_keywords/live", json=body,
                              headers=headers, timeout=120).json()
            task = (r.get("tasks") or [{}])[0]
            spent += float(task.get("cost") or 0)
            items = [it for res in (task.get("result") or []) for it in (res.get("items") or [])]
        except Exception as exc:
            ap.log(f"! dataforseo labs {comp['domain']}: {exc.__class__.__name__}")
            items = []
        paid = [dict((it.get("ranked_serp_element") or {}).get("serp_item") or {},
                     _keyword=(it.get("keyword_data") or {}).get("keyword")) for it in items]
        out[comp["domain"]] = paid
        ap.save_raw(f"serp-labs-{comp['domain']}", {"source": "dataforseo labs", "fetched": date.today().isoformat(),
                                                    "items": [{"keyword": p["_keyword"], "paid": [p]} for p in paid]})
    return out, round(spent, 4)


def _safe_search(keyword: str, headers: dict) -> tuple[dict, float]:
    try:
        return _search(keyword, headers)
    except Exception as exc:
        ap.log(f"! dataforseo '{keyword}': {exc.__class__.__name__}")
        return {}, 0.0


def headline_parts(text: str | None) -> set[str]:
    return {ap.norm(p) for p in re.split(r"\s[-|·:]\s|\s\|\s", text or "") if len(ap.norm(p)) >= 10}
