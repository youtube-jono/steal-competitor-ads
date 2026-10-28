"""Shared helpers for /pull-ads: Apify client, competitors, dates, raw dumps.

Keys come from .env (APIFY_TOKEN, then APIFY_TOKEN_BACKUP). They are never printed.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
PAGES = DATA / "pages"
API = "https://api.apify.com/v2"

# Hosts we never send a browser or HTTP request to. They may only appear inside actor input.
BLOCKED_HOSTS = ("facebook.com", "facebook.net", "fb.me", "fb.com", "fbcdn.net", "fbsbx.com",
                 "instagram.com", "cdninstagram.com", "meta.com", "messenger.com", "threads.net",
                 "whatsapp.com", "oculus.com")


def load_env() -> dict:
    env_path = ROOT / ".env"
    values = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            values[key.strip()] = val.strip().strip('"').strip("'")
    for key in ("APIFY_TOKEN", "APIFY_TOKEN_BACKUP"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


_ENV = load_env()
# The market the competitors advertise in, two letters (US, CA, GB, AU...). Every pull uses it.
COUNTRY = (_ENV.get("COUNTRY") or "US").strip().upper()
_TOKENS = [t for t in (_ENV.get("APIFY_TOKEN"), _ENV.get("APIFY_TOKEN_BACKUP")) if t]


class ApifyError(RuntimeError):
    pass


USED_ACTORS: set[str] = set()  # actors this process ran, for spend_since()
# Free Apify plans allow 5 concurrent runs. Keep one free for other commands sharing the token.
MAX_PARALLEL_RUNS = 4
_SLOTS = threading.BoundedSemaphore(MAX_PARALLEL_RUNS)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def usage_usd(token_index: int = 0) -> float | None:
    """Current monthly usage in USD for one token, or None if it can't be read."""
    if token_index >= len(_TOKENS):
        return None
    try:
        r = requests.get(f"{API}/users/me/limits", headers=_headers(_TOKENS[token_index]), timeout=30)
        r.raise_for_status()
        return float(r.json()["data"]["current"]["monthlyUsageUsd"])
    except Exception:
        return None


def spend_since(started: datetime, actors: set[str] | None = None) -> float | None:
    """USD charged by our own actor runs started after `started`, across both tokens.

    Counts only the actors /pull-ads uses, so other commands sharing the token don't skew it.
    """
    actors = actors if actors is not None else USED_ACTORS
    if not _TOKENS or not actors:
        return 0.0 if not actors else None
    total, ok = 0.0, False
    for token in _TOKENS:
        h = _headers(token)
        try:
            ids = set()
            for name in actors:
                r = requests.get(f"{API}/acts/{name.replace('/', '~')}", headers=h, timeout=30)
                if r.ok:
                    ids.add(r.json()["data"]["id"])
            r = requests.get(f"{API}/actor-runs", params={"desc": 1, "limit": 200}, headers=h, timeout=30)
            r.raise_for_status()
            ok = True
            for run in r.json()["data"]["items"]:
                when = datetime.fromisoformat(run["startedAt"].replace("Z", "+00:00"))
                if when < started:
                    break
                if run.get("actId") in ids:
                    total += float(run.get("usageTotalUsd") or 0)
        except Exception:
            continue
    return round(total, 4) if ok else None


def _run_items(run_id: str, token: str) -> list | None:
    try:
        h = _headers(token)
        d = requests.get(f"{API}/actor-runs/{run_id}", headers=h, timeout=30).json()["data"]
        return requests.get(f"{API}/datasets/{d['defaultDatasetId']}/items",
                            params={"clean": "true", "format": "json"}, headers=h, timeout=120).json()
    except Exception:
        return None


def _recover(actor: str, token: str, since: datetime, wait: int) -> list | None:
    """After a gateway error or dropped connection, find the run we started and wait for it.

    Avoids starting a second, double-charged run of the same search.
    """
    h = _headers(token)
    deadline = time.time() + wait
    run = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{API}/acts/{actor.replace('/', '~')}/runs", params={"desc": 1, "limit": 5},
                             headers=h, timeout=30)
            runs = [x for x in r.json()["data"]["items"]
                    if datetime.fromisoformat(x["startedAt"].replace("Z", "+00:00")) >= since]
            if runs:
                run = runs[-1]  # the oldest run started after our request is ours
                d = requests.get(f"{API}/actor-runs/{run['id']}", headers=h, timeout=30).json()["data"]
                if d["status"] not in ("READY", "RUNNING"):
                    items = requests.get(f"{API}/datasets/{d['defaultDatasetId']}/items",
                                         params={"clean": "true", "format": "json"}, headers=h, timeout=120)
                    return items.json()
        except Exception:
            pass
        time.sleep(10)
    return None


def run_actor(actor: str, actor_input: dict, *, label: str, timeout: int = 280,
              max_items: int | None = None, max_charge_usd: float | None = None,
              retry_if_empty: bool = False) -> list:
    with _SLOTS:
        return _run_actor(actor, actor_input, label=label, timeout=timeout, max_items=max_items,
                          max_charge_usd=max_charge_usd, retry_if_empty=retry_if_empty)


def _run_actor(actor: str, actor_input: dict, *, label: str, timeout: int,
               max_items: int | None, max_charge_usd: float | None, retry_if_empty: bool) -> list:
    """Run an actor with run-sync-get-dataset-items. Saves raw output to data/raw/<label>.json.

    Falls back to the backup token when the first one is out of credit or rejected (or, with
    retry_if_empty, when an actor silently returns nothing). A gateway error or dropped
    connection waits for the run already started instead of starting a second one.
    """
    if not _TOKENS:
        raise ApifyError("No APIFY_TOKEN in .env")
    params = {"timeout": timeout, "format": "json", "clean": "true"}
    if max_items:
        params["maxItems"] = max_items
    if max_charge_usd:
        params["maxTotalChargeUsd"] = max_charge_usd
    url = f"{API}/acts/{actor.replace('/', '~')}/run-sync-get-dataset-items"
    raw_path(label).unlink(missing_ok=True)  # never let a stale file stand in for a failed run
    USED_ACTORS.add(actor)
    last_err, items = None, None
    for n, token in enumerate(_TOKENS):
        since = datetime.now(timezone.utc) - timedelta(seconds=5)
        try:
            r = requests.post(url, params=params, json=actor_input, headers=_headers(token),
                              timeout=timeout + 60)
            status = r.status_code
        except requests.RequestException as exc:
            r, status = None, 599
            last_err = f"network error: {exc.__class__.__name__}"
        if status in (402, 403) and r is not None and re.search(r"memory|concurren", r.text, re.I):
            # Account busy (memory or concurrency limit): wait for a slot, same token.
            for _ in range(24):
                time.sleep(15)
                since = datetime.now(timezone.utc) - timedelta(seconds=5)
                r = requests.post(url, params=params, json=actor_input, headers=_headers(token),
                                  timeout=timeout + 60)
                status = r.status_code
                if not (status in (402, 403) and re.search(r"memory|concurren", r.text, re.I)):
                    break
        if status in (401, 402, 403):
            last_err = f"HTTP {status} (token rejected or out of credit): {r.text[:160] if r is not None else ''}"
            continue
        if status == 400 and r is not None and "TIMED-OUT" in r.text:
            m = re.search(r"run ID: ([A-Za-z0-9]+)", r.text)
            items = _run_items(m.group(1), token) if m else None
            if items is None:
                raise ApifyError(f"{actor}: timed out after {timeout}s")
            log(f"! {actor} timed out after {timeout}s, kept {len(items)} partial results")
            save_raw(label, {"actor": actor, "input": actor_input, "items": items, "partial": True})
            return items
        if status in (502, 503, 504, 599):
            items = _recover(actor, token, since, timeout + 120)
            if items is None:
                raise ApifyError(f"{actor}: gateway error {status} and the run could not be recovered")
        elif status >= 400:
            msg = r.text[:300].replace("\n", " ")
            raise ApifyError(f"{actor} HTTP {status}: {msg}")
        else:
            try:
                items = r.json()
            except ValueError:
                raise ApifyError(f"{actor} returned non-JSON")
        if isinstance(items, dict):
            items = items.get("items") or items.get("data") or []
        if retry_if_empty and not items and n + 1 < len(_TOKENS):
            last_err = "empty result"
            continue
        save_raw(label, {"actor": actor, "input": actor_input, "items": items})
        return items
    if items is not None:
        save_raw(label, {"actor": actor, "input": actor_input, "items": items})
        return items
    raise ApifyError(f"{actor}: {last_err}")


def raw_path(label: str) -> Path:
    return RAW / (re.sub(r"[^a-zA-Z0-9._-]+", "-", label) + ".json")


def save_raw(label: str, payload) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    raw_path(label).write_text(json.dumps(payload, indent=1, ensure_ascii=False))


def load_raw(label: str) -> list | None:
    """Items saved by run_actor for this label, or None if that run failed or never ran."""
    path = raw_path(label)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text()).get("items") or []
    except (ValueError, AttributeError):
        return None


def load_competitors() -> list[dict]:
    """Parse context/competitors.md lines like '- SavClicks · savclicks.com'."""
    path = ROOT / "context" / "competitors.md"
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        body = line.lstrip("-* ").strip()
        parts = re.split(r"\s+[·|,]\s+|\s+-\s+|\s+\u2014\s+", body)
        domain = next((p for p in parts if re.search(r"\.[a-z]{2,}$", p.strip().lower())), None)
        if not domain:
            continue
        domain = domain.strip().lower().replace("https://", "").replace("http://", "").strip("/")
        domain = domain.removeprefix("www.")
        name = next((p.strip() for p in parts if p.strip().lower() != domain), domain.split(".")[0])
        out.append({"name": name, "domain": domain})
    return out


def norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def is_blocked_url(url: str | None) -> bool:
    if not url:
        return True
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in BLOCKED_HOSTS)


def clean_url(url: str | None) -> str | None:
    """Return the advertiser URL, or None if it is empty or points at Meta."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        if re.match(r"^[a-z0-9.-]+\.[a-z]{2,}(/|$)", url.lower()):
            url = "https://" + url
        else:
            return None
    return None if is_blocked_url(url) else url


def to_date(value) -> str | None:
    """ISO date (YYYY-MM-DD) from epoch seconds/ms or a date-ish string."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)):
            secs = value / 1000 if value > 10_000_000_000 else value
            return datetime.fromtimestamp(secs, tz=timezone.utc).date().isoformat()
        text = str(value).strip()
        if text.isdigit():
            return to_date(int(text))
        return datetime.fromisoformat(text.replace("Z", "+00:00")[:25]).date().isoformat()
    except (ValueError, OverflowError, OSError):
        m = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
        return m.group(0) if m else None


def days_between(start: str | None, end: str | None) -> int | None:
    if not start:
        return None
    try:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end) if end else date.today()
        return max((e - s).days, 0) + 1
    except ValueError:
        return None


def blank_ad(**fields) -> dict:
    """Every ad has every contract field. Missing data is null, never guessed."""
    ad = {
        "id": None, "platform": None, "advertiser": None, "domain": None, "format": None,
        "headline": None, "body": None, "description": None, "cta": None, "display_url": None,
        "landing_url": None, "media": {"image": None, "video": None, "thumbnail": None},
        "placements": [], "start_date": None, "last_seen": None, "days_running": None,
        "active": None, "copies": None, "impressions_rank": None, "impressions_range": None,
        "eu_reach": None, "reach_per_day": None, "spyfu_share": None, "ctr_rank": None,
        "source": None,
    }
    ad.update(fields)
    return ad


def text_or_none(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("text")
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or re.fullmatch(r"\{\{.*\}\}", value):
        return None
    return value


def log(msg: str) -> None:
    print(msg, file=sys.stderr if msg.startswith("!") else sys.stdout, flush=True)
