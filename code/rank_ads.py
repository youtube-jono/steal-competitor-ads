"""Score every competitor ad and grade it A, B or C.

    python3 code/rank_ads.py                     # data/ads.json -> data/ranked.json
    python3 code/rank_ads.py --input data/sample/rank-fixture.json

No ad library shows spend, so the score is built from delivery clues, strongest first
(references/ranking-research.md, "FINAL METHOD"):

- Meta:     EU reach per day when the ad ran in Europe, else its position in the
            impressions-sorted pull. Boosted for 30+ days running and for copies.
- Google:   SpyFu share of ads served, ranked within each competitor. Then days shown.
- TikTok,   EU impressions range per day where the library gives one.
  LinkedIn:
- Days running is only ever a tie-breaker, and it counts a quarter as much as delivery.

Missing data is never zero. An ad with no delivery clue scores from its dates alone, capped
at 60, and its confidence grade says so: A = real delivery data, B = a rank only, C = dates only.

Too new to judge (under 7 days on Meta, 14 on Google) and "<100 impressions" ads never make
the A tier. Hiring and brand posts aren't selling anything, so they go to C. So do ads with
no readable text.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

PLATFORM_ORDER = ["google", "meta", "tiktok", "linkedin"]
PLATFORM_NAME = {"google": "Google", "meta": "Meta", "tiktok": "TikTok", "linkedin": "LinkedIn"}
MIN_DAYS = {"meta": 7, "google": 14}

DELIVERY_WEIGHT = 2.0      # delivery rate counts double
TIME_WEIGHT = 0.5          # time counts half
DATES_ONLY_CAP = 0.6       # a dates-only score tops out at 60
DAYS_SCALE = 365           # a year running fills the time component
LONG_RUN_DAYS = 30
LONG_RUN_BOOST = 4
COPY_BOOST_PER_DOUBLING = 4
COPY_BOOST_MAX = 10
PAGE_BOOST_MAX = 5
BASE_POINTS = 88           # the clues earn up to 88, boosts can add the rest

A_SHARE = 0.15             # top ~15% are their winners
A_MIN = 3                  # and always at least the top 3 per platform
C_SHARE = 1 / 3            # the bottom third is C

NOT_SELLING = re.compile(
    r"\b(we'?re hiring|now hiring|join our team|careers? at|apply now for|job opening|open roles?)\b",
    re.I)


# ---------------------------------------------------------------- input

def pick_input(arg: str | None) -> Path:
    if arg:
        path = Path(arg)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            sys.exit(f"No file at {path}")
        return path
    for candidate in (DATA / "ads.json", DATA / "sample" / "ads.json",
                      DATA / "sample" / "rank-fixture.json"):
        if candidate.exists():
            return candidate
    sys.exit("No data/ads.json yet. Run /pull-ads first.")


def default_output(input_path: Path) -> Path:
    """Real pulls write data/ranked.json. Any other file writes <name>-ranked.json beside
    itself, so a sample never overwrites the real ranking or anyone's sample."""
    if input_path.resolve() == (DATA / "ads.json").resolve():
        return DATA / "ranked.json"
    return input_path.with_name(f"{input_path.stem}-ranked.json")


def load_pages() -> dict:
    """ad id -> its landing page from data/pages.json, if /pull-ads wrote one."""
    path = DATA / "pages.json"
    if not path.exists():
        return {}
    try:
        pages = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    by_ad = {}
    for page in pages if isinstance(pages, list) else []:
        for ad_id in page.get("ad_ids") or []:
            by_ad[ad_id] = page
    return by_ad


# ---------------------------------------------------------------- clues

def num(value):
    """A usable positive number, or None. Never turns missing into zero."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def days_running(ad: dict):
    days = ad.get("days_running")
    if isinstance(days, (int, float)) and not isinstance(days, bool) and days >= 0:
        return int(days)
    try:
        start = date.fromisoformat(str(ad.get("start_date"))[:10])
        end = date.fromisoformat(str(ad.get("last_seen"))[:10])
        return max(0, (end - start).days)
    except (TypeError, ValueError):
        return None


def impressions_per_day(ad: dict, days):
    rng = ad.get("impressions_range")
    if not isinstance(rng, (list, tuple)) or len(rng) != 2:
        return None
    lo, hi = num(rng[0]), num(rng[1])
    if hi is None:
        return None
    mid = (lo + hi) / 2 if lo else hi
    return mid / max(days or 1, 1)


def reach_per_day(ad: dict, days):
    rpd = num(ad.get("reach_per_day"))
    if rpd:
        return rpd
    reach = num(ad.get("eu_reach"))
    if reach and days:
        return reach / days
    return None


def under_100(ad: dict) -> bool:
    rng = ad.get("impressions_range")
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        hi = num(rng[1])
        return hi is not None and hi < 100
    return False


def is_not_selling(ad: dict) -> bool:
    text = " ".join(str(ad.get(k) or "") for k in ("headline", "body", "description", "cta"))
    return bool(NOT_SELLING.search(text))


TEMPLATE = re.compile(r"<[A-Za-z ()]+>")


def is_unreadable(ad: dict) -> bool:
    """No ad text came back (an image the OCR couldn't read) or only a preview template."""
    text = " ".join(str(ad.get(k) or "") for k in ("headline", "body", "description"))
    return len(re.sub(r"[^A-Za-z]", "", text)) < 12 or bool(TEMPLATE.search(text))


def ratio_score(value, best):
    """Log scale relative to the best: equal = 1.0, a tenth = 0.5, a hundredth = 0."""
    if not value or not best:
        return None
    return max(0.0, min(1.0, 1 + math.log10(value / best) / 2))


def rank_score(rank, out_of):
    """Top of a sorted list scores highest, and the top few matter most."""
    if not rank or not out_of:
        return None
    return max(0.0, 1 - math.log(rank) / math.log(out_of + 1))


def time_score(days):
    if days is None:
        return None
    return min(1.0, math.log1p(days) / math.log1p(DAYS_SCALE))


# ---------------------------------------------------------------- scoring

def gather(ads: list) -> list:
    """Attach the raw clues to each ad, so normalising can see the whole field."""
    rows = []
    for ad in ads:
        days = days_running(ad)
        rows.append({
            "ad": ad,
            "platform": (ad.get("platform") or "").lower(),
            # Group by domain: one competitor shows up as "Acme" in one library and
            # "Acme, LLC" in another.
            "group": (ad.get("domain") or ad.get("advertiser") or "unknown").lower(),
            "advertiser": ad.get("advertiser") or ad.get("domain") or "unknown",
            "days": days,
            "reach_pd": reach_per_day(ad, days),
            "impr_pd": impressions_per_day(ad, days),
            "imp_rank": num(ad.get("impressions_rank")),
            "share": num(ad.get("spyfu_share")),
            "ctr_rank": num(ad.get("ctr_rank")),
            "copies": num(ad.get("copies")),
        })
    return rows


def field_maxima(rows: list) -> dict:
    """The yardsticks: best reach and impressions per platform, deepest rank and best share
    per competitor per platform."""
    best = defaultdict(float)
    for r in rows:
        p, a = r["platform"], r["group"]
        if r["reach_pd"]:
            best[("reach", p)] = max(best[("reach", p)], r["reach_pd"])
        if r["impr_pd"]:
            best[("impr", p)] = max(best[("impr", p)], r["impr_pd"])
        if r["imp_rank"]:
            best[("rank", p, a)] = max(best[("rank", p, a)], r["imp_rank"])
        if r["share"]:
            best[("share", p, a)] = max(best[("share", p, a)], r["share"])
        if r["ctr_rank"]:
            best[("ctr", p)] = max(best[("ctr", p)], r["ctr_rank"])
    return best


def delivery(r: dict, best: dict):
    """-> (score 0-1 or None, confidence grade, the clue in plain words)."""
    p, g, a = r["platform"], r["group"], r["advertiser"]
    name = PLATFORM_NAME.get(p, p)
    if r["reach_pd"]:
        return (ratio_score(r["reach_pd"], best[("reach", p)]), "A",
                f"reaches about {r['reach_pd']:,.0f} people a day in the EU")
    if r["impr_pd"]:
        return (ratio_score(r["impr_pd"], best[("impr", p)]), "A",
                f"about {r['impr_pd']:,.0f} impressions a day (EU range)")
    if r["imp_rank"] and p == "meta":
        out_of = int(best[("rank", p, g)])
        return (rank_score(r["imp_rank"], out_of), "B",
                f"#{int(r['imp_rank'])} of {out_of} in {a}'s impressions sort")
    if r["share"]:
        pct = r["share"] * 100 if r["share"] <= 1 else r["share"]   # SpyFu gives 0.076 for 7.6%
        return (ratio_score(r["share"], best[("share", p, g)]), "B",
                f"shown in {pct:.1f}% of {a}'s Google ad appearances (SpyFu)")
    if r["ctr_rank"]:
        out_of = int(best[("ctr", p)])
        return (rank_score(r["ctr_rank"], out_of), "B",
                f"#{int(r['ctr_rank'])} CTR rank in {name}'s Creative Center")
    return None, "C", None


def page_boost(ad: dict, pages: dict):
    page = pages.get(ad.get("id"))
    if not page:
        return 0, None
    boost = 0
    if page.get("is_homepage") is False:
        boost += 3
    if page.get("price"):
        boost += 1
    if page.get("proof"):
        boost += 1
    boost = min(boost, PAGE_BOOST_MAX)
    return boost, ("lands on its own page" if page.get("is_homepage") is False else None)


def score_row(r: dict, best: dict, pages: dict) -> dict:
    ad, p, days = r["ad"], r["platform"], r["days"]
    d_score, grade, d_clue = delivery(r, best)
    t_score = time_score(days)
    clues = [d_clue] if d_clue else []
    if days is not None:
        clues.append(f"{days} days running")

    if d_score is not None:
        base = d_score if t_score is None else (
            (DELIVERY_WEIGHT * d_score + TIME_WEIGHT * t_score) / (DELIVERY_WEIGHT + TIME_WEIGHT))
    elif t_score is not None:
        base = DATES_ONLY_CAP * t_score
    else:
        base = None

    boost = 0
    if base is not None:
        if p == "meta" and days is not None and days >= LONG_RUN_DAYS:
            boost += LONG_RUN_BOOST
        if p == "meta" and r["copies"] and r["copies"] >= 2:
            boost += min(COPY_BOOST_MAX, COPY_BOOST_PER_DOUBLING * math.log2(r["copies"]))
            clues.append(f"{int(r['copies'])} copies")
        pb, page_clue = page_boost(ad, pages)
        boost += pb
        if page_clue:
            clues.append(page_clue)

    score = None if base is None else int(round(max(0, min(100, base * BASE_POINTS + boost))))

    flags = []
    min_days = MIN_DAYS.get(p)
    too_new = min_days is not None and days is not None and days < min_days
    if too_new:
        flags.append("too_new")
        clues = [f"too new to judge ({days} days)"]
    if under_100(ad):
        flags.append("under_100")
        clues.append("under 100 impressions")
    if is_not_selling(ad):
        flags.append("not_selling")
        clues = ["not selling anything (hiring or brand post)"]
    elif is_unreadable(ad):
        flags.append("no_text")
        clues = ["no readable ad text, nothing to learn from"]
    if score is None:
        clues = ["no dates or delivery data from this library, can't rank it"]
    elif grade == "C" and not too_new and "not_selling" not in flags:
        clues.append("dates only, low confidence")

    why = ", ".join(c for c in clues if c)
    return {"score": score, "grade": grade, "why": why[:1].upper() + why[1:], "flags": flags}


# ---------------------------------------------------------------- tiers

def assign_tiers(rows: list) -> None:
    """Per platform: A = their winners, C = the bottom third, B = everything between."""
    by_platform = defaultdict(list)
    for r in rows:
        by_platform[r["platform"]].append(r)

    for plat_rows in by_platform.values():
        # Days running only ever breaks a tie.
        def order(r):
            return (-r["result"]["score"], -(r["days"] or 0), r["imp_rank"] or 10**6)

        scored = [r for r in plat_rows if r["result"]["score"] is not None]
        judged = sorted((r for r in scored if not r["result"]["flags"]), key=order)
        flagged = sorted((r for r in scored if r["result"]["flags"]), key=order)
        unscored = [r for r in plat_rows if r["result"]["score"] is None]
        for i, r in enumerate(judged + flagged + unscored, start=1):
            r["result"]["rank"] = i

        a_count = min(len(judged), max(A_MIN, math.ceil(A_SHARE * len(scored))))
        c_from = len(judged) - int(len(judged) * C_SHARE)
        for i, r in enumerate(judged):
            r["result"]["tier"] = "A" if i < a_count else ("C" if i >= max(c_from, a_count) else "B")
        for r in flagged:
            flags = r["result"]["flags"]
            # Too new is "can't tell yet", not a loser. Not selling or under 100 is out.
            r["result"]["tier"] = "C" if {"not_selling", "under_100", "no_text"} & set(flags) else "B"
        for r in unscored:
            r["result"]["tier"] = "B"


def rank(ads: list, pages: dict) -> list:
    rows = gather(ads)
    best = field_maxima(rows)
    for r in rows:
        r["result"] = score_row(r, best, pages)
    assign_tiers(rows)

    out = []
    for r in rows:
        res = r["result"]
        out.append({**r["ad"], "score": res["score"], "tier": res["tier"], "grade": res["grade"],
                    "rank": res["rank"], "why": res["why"]})
    order = {p: i for i, p in enumerate(PLATFORM_ORDER)}
    out.sort(key=lambda a: (order.get((a.get("platform") or "").lower(), 99), a["rank"]))
    return out


# ---------------------------------------------------------------- report

def report(ranked: list, out_path: Path) -> None:
    by_platform = defaultdict(list)
    for ad in ranked:
        by_platform[(ad.get("platform") or "").lower()].append(ad)
    print(f"Ranked {len(ranked)} ads -> {out_path.relative_to(ROOT)}\n")
    for plat in sorted(by_platform, key=lambda p: PLATFORM_ORDER.index(p) if p in PLATFORM_ORDER else 99):
        ads = by_platform[plat]
        tiers = {t: sum(1 for a in ads if a["tier"] == t) for t in "ABC"}
        grades = {g: sum(1 for a in ads if a["grade"] == g) for g in "ABC"}
        print(f"{PLATFORM_NAME.get(plat, plat)}: {len(ads)} ads · tier A {tiers['A']}, B {tiers['B']}, "
              f"C {tiers['C']} · confidence A {grades['A']}, B {grades['B']}, C {grades['C']}")
        for ad in [a for a in ads if a["tier"] == "A"][:5]:
            line = (ad.get("headline") or ad.get("body") or "")[:60].replace("\n", " ")
            print(f"  A #{ad['rank']} {ad['score']:>3} · {ad.get('advertiser')} · {line!r}")
            print(f"       {ad['why']}")
        print()


def main():
    ap = argparse.ArgumentParser(description="Score competitor ads and grade them A, B or C.")
    ap.add_argument("--input", help="ads file (default data/ads.json)")
    ap.add_argument("--out", help="where to write (default data/ranked.json)")
    args = ap.parse_args()

    in_path = pick_input(args.input)
    out_path = Path(args.out) if args.out else default_output(in_path)
    if not out_path.is_absolute():
        out_path = ROOT / out_path

    try:
        ads = json.loads(in_path.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"{in_path.name} isn't valid JSON: {exc}")
    if not isinstance(ads, list) or not ads:
        sys.exit(f"{in_path.name} has no ads in it.")
    if in_path.parent.name == "sample":
        print(f"Using the sample file {in_path.relative_to(ROOT)} - real pulls go in data/ads.json\n")

    ranked = rank(ads, load_pages())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ranked, indent=2, ensure_ascii=False))
    report(ranked, out_path)


if __name__ == "__main__":
    main()
