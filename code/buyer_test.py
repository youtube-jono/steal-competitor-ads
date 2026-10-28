"""Gate 2: would they click ours instead of theirs?

    python3 code/buyer_test.py build       # data/buyer-sheet.md (for the buyer) + data/buyer-key.json (hidden)
    python3 code/buyer_test.py record      # reads data/buyer-picks.json, scores, writes tier S
    python3 code/buyer_test.py status

build: every draft in data/new-ads.json that passed gate 1 goes beside the three best
competitor ads on the same platform (tier A in data/ranked.json, best rank first). Brand names
stripped, order shuffled, five runs per draft, and every question shuffled into one sheet, so
the buyer can't tell which option is ours or line one draft's runs up.

The buyer is a fresh subagent that reads ONLY data/buyer-sheet.md and writes its picks to
data/buyer-picks.json. It never sees data/new-ads.json or data/buyer-key.json.

record: ours must be picked in at least 4 of 5 runs. Pass gate 1 and gate 2 and the draft is
tier S. Then it checks gate 3 (the variety floor) and whether the S tier fills one Google ad.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_rules import competitor_names, draft_hash, env_value, sections  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DRAFTS = DATA / "new-ads.json"
RANKED = DATA / "ranked.json"
SHEET = DATA / "buyer-sheet.md"
KEY = DATA / "buyer-key.json"
PICKS = DATA / "buyer-picks.json"
BUSINESS = ROOT / "context" / "business.md"

RUNS = 5
WINS_NEEDED = 4
RIVALS = 3
ANGLES = ["offer", "speed", "price", "trust", "risk-reversal", "ask"]
MIN_ANGLES = 4
MAX_ANGLE_SHARE = 1 / 3
RSA_HEADLINES, RSA_DESCRIPTIONS = 15, 4
LETTERS = "ABCD"
SCENE = {
    "google": 'You searched Google for "{search}". Four ads sit above the results. Which one do you tap?',
    "meta": "You're scrolling Instagram on your phone. Four ads go past. Which one gets your tap?",
    "tiktok": "You're scrolling TikTok. Four ads go past. Which one gets your tap?",
    "linkedin": "You're scrolling LinkedIn. Four sponsored posts go past. Which one gets your click?",
}
DEFAULT_BUYER = ("A sceptical buyer who needs what these ads sell, reading on a phone, three seconds "
                 "per ad, who has been burned before and has no reason to care about any of them.")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path, what: str):
    if not path.exists():
        sys.exit(f"No {rel(path)}. {what}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"{rel(path)} isn't valid JSON: {exc}")


# ---------------------------------------------------------------- business context

def buyer_and_searches() -> tuple:
    text = BUSINESS.read_text() if BUSINESS.exists() else ""
    m = re.search(r"^Buyer:\s*(.+)$", text, re.M)
    buyer = m.group(1).strip() if m else DEFAULT_BUYER
    searches = []
    for heading, lines in sections(text):
        if "keyword" in heading.lower():
            for line in lines:
                if line.strip().startswith("- "):
                    searches.append(line.strip()[2:].split(" · ")[0].strip())
    return buyer, searches


def stripper():
    """Brand names out of every option, ours included, so it's the words that win."""
    names = competitor_names() + [env_value("BUSINESS_NAME")]
    site = env_value("SITE_BASE_URL").replace("https://", "").replace("http://", "").strip("/")
    if site:
        names += [site, site.replace("www.", "")]
    names = sorted({n for n in names if n and len(n) >= 3}, key=len, reverse=True)
    patterns = [re.compile(r"\b" + re.escape(n) + r"\b", re.I) for n in names]

    def strip(text):
        if not text:
            return text
        for p in patterns:
            text = p.sub("[brand]", str(text))
        parts = [p.strip() for p in re.split(r"\s\|\s", text)]
        parts = [p for p in parts if p and p != "[brand]"]          # a brand-only headline goes
        text = " | ".join(parts)
        text = re.sub(r"^\[brand\][\s:-]+|[\s:-]+\[brand\]$", "", text)  # so does a leading or trailing one
        return text.strip()
    return strip


# ---------------------------------------------------------------- the options

def ours_option(draft: dict, run: int, n_heads: int, n_descs: int) -> dict:
    """Ours shown the way Google rotates a responsive ad: as many headlines as the rivals show,
    one description, a different combination each run. Same shape as theirs, so length is
    never the tell, and every line gets its turn in front of the buyer."""
    def rotate(value, n, sep):
        if not isinstance(value, list):
            return value or ""
        if not value:
            return ""
        start = (run - 1) % len(value)
        return sep.join(value[(start + i) % len(value)] for i in range(min(n, len(value))))
    return {"headline": rotate(draft.get("headline"), n_heads, " | "),
            "body": rotate(draft.get("body"), 1, " "),
            "description": rotate(draft.get("description"), n_descs, " ")}


def headline_segments(ads: list) -> int:
    """How many headlines the rivals show, so ours shows the same number."""
    counts = sorted(len([p for p in re.split(r"\s[|\u2013-]\s", a.get("headline") or "") if p.strip()])
                    for a in ads if a.get("headline"))
    return max(1, min(3, counts[len(counts) // 2])) if counts else 2


def description_count(ads: list) -> int:
    """Rivals whose description runs past one 90-character slot are showing two."""
    lengths = sorted(len(a.get("description") or a.get("body") or "") for a in ads)
    return 2 if lengths and lengths[len(lengths) // 2] > 90 else 1


def theirs_option(ad: dict) -> dict | None:
    head = (ad.get("headline") or "").strip()
    body = (ad.get("body") or "").strip()
    desc = (ad.get("description") or "").strip()
    if ad.get("platform") == "google":
        desc = desc or body
        body = ""
    if not (head or body or desc):
        return None
    return {"headline": head, "body": body, "description": desc}


def pick_rivals(ranked: list, platform: str) -> list:
    """The three best competitor ads on this platform that have words in them.
    Tier A first, best rank first. Short of three, the next best on the same platform,
    then tier A from other platforms (marked) so the buyer still has three to beat."""
    def usable(ads):
        return [a for a in ads if theirs_option(a)]

    same = sorted(usable([a for a in ranked if a.get("platform") == platform]),
                  key=lambda a: (a.get("tier") != "A", a.get("rank") or 999))
    others = sorted(usable([a for a in ranked if a.get("platform") != platform and a.get("tier") == "A"]),
                    key=lambda a: (a.get("rank") or 999))
    out, seen = [], set()
    for ad in same + others:
        # The same ad pulled twice ("-" in one library, "|" in another) counts once.
        words = re.findall(r"[a-z0-9]+", json.dumps(theirs_option(ad)).lower())
        key = " ".join(sorted(set(words)))
        if key in seen:
            continue
        seen.add(key)
        out.append(ad)
        if len(out) == RIVALS:
            break
    return out


def render(option: dict, strip, platform: str) -> list:
    lines = []
    if option.get("headline"):
        lines.append(strip(option["headline"]))
    if option.get("body"):
        lines.append(strip(option["body"]))
    if option.get("description"):
        lines.append(strip(option["description"]))
    if platform == "google":
        lines.insert(0, "Sponsored")
    return [l for l in lines if l]


# ---------------------------------------------------------------- build

def build(drafts_path: Path, ranked_path: Path, retest: bool) -> None:
    drafts = load_json(drafts_path, "Write the drafts first, then run code/gate_rules.py.")
    ranked = load_json(ranked_path, "Run /rank-ads first - the buyer test needs their A tier.")
    ready = [d for d in drafts if d.get("gate_rules") == "pass"]
    if not ready:
        sys.exit("No drafts have passed gate 1. Run python3 code/gate_rules.py first.")
    if not retest:
        # A draft keeps its verdict until its words change. Only new or rewritten drafts go in.
        ready = [d for d in ready if not d.get("buyer_test") or d.get("buyer_hash") != draft_hash(d)]
        if not ready:
            sys.exit("Every draft that passed gate 1 already has a buyer-test result. "
                     "Write or rewrite some, or pass --retest to run them all again.")

    buyer, searches = buyer_and_searches()
    strip = stripper()
    questions, key_drafts = [], {}
    for draft in ready:
        platform = draft.get("platform")
        rivals = pick_rivals(ranked, platform)
        if not rivals:
            print(f"! {draft['id']}: no competitor ads with words on {platform} or anywhere - skipped")
            continue
        key_drafts[draft["id"]] = {"hash": draft_hash(draft), "rivals": [a["id"] for a in rivals],
                                   "rivals_from": sorted({a.get("platform") for a in rivals})}
        n_heads, n_descs = headline_segments(rivals), description_count(rivals)
        theirs = [(a["id"], theirs_option(a)) for a in rivals]
        for run in range(1, RUNS + 1):
            rng = random.Random(f"{draft['id']}-{run}-{key_drafts[draft['id']]['hash']}")
            order = [("ours", ours_option(draft, run, n_heads, n_descs))] + theirs
            rng.shuffle(order)
            search = searches[(run - 1) % len(searches)] if searches else "what this business sells"
            questions.append({"draft": draft["id"], "run": run, "platform": platform,
                              "scene": SCENE.get(platform, SCENE["meta"]).format(search=search),
                              "order": order})

    random.Random(len(questions)).shuffle(questions)
    sheet = [
        "# Which ad would you tap?",
        "",
        f"You are this person: {buyer}",
        "",
        "Rules:",
        "- Judge only the words on screen. Three seconds per option, like a real feed or results page.",
        "- Pick the one you would actually tap, not the one you admire.",
        "- Brand names are hidden as [brand]. Ignore that.",
        "- Every question stands alone. Don't try to stay consistent with earlier answers.",
        "- No ties and no skips. Every question gets exactly one letter.",
        "",
        f"Write every answer to {rel(PICKS)} as JSON, one entry per question:",
        '{"Q1": {"pick": "B", "why": "the exact words that won it"}, "Q2": {...}}',
        "",
    ]
    key = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "drafts_file": rel(drafts_path), "ranked_file": rel(ranked_path),
           "drafts": key_drafts, "questions": {}}
    for n, q in enumerate(questions, start=1):
        qid = f"Q{n}"
        sheet += [f"## {qid}", q["scene"], ""]
        for letter, (oid, option) in zip(LETTERS, q["order"]):
            rendered = render(option, strip, q["platform"])
            sheet.append(f"{letter}. " + rendered[0])
            sheet += [f"   {line}" for line in rendered[1:]]
            sheet.append("")
        ours = next(l for l, (oid, _) in zip(LETTERS, q["order"]) if oid == "ours")
        shown = next(opt for oid, opt in q["order"] if oid == "ours")
        key["questions"][qid] = {"draft": q["draft"], "run": q["run"], "ours": ours,
                                 "options": [oid for oid, _ in q["order"]],
                                 "shown_headline": shown.get("headline", "")}

    SHEET.write_text("\n".join(sheet), encoding="utf-8")
    KEY.write_text(json.dumps(key, indent=2), encoding="utf-8")
    if PICKS.exists():
        PICKS.unlink()          # old picks belong to an old sheet
    print(f"Built {len(questions)} questions for {len(key_drafts)} drafts ({RUNS} runs each).")
    print(f"  Sheet for the buyer: {rel(SHEET)}")
    print(f"  Answer key (never show the buyer): {rel(KEY)}")
    if ranked_path.parent.name == "sample":
        print(f"  ! Rivals came from the sample file {rel(ranked_path)}, not a real pull.")
    for did, info in key_drafts.items():
        if info["rivals_from"] != [next(d for d in ready if d["id"] == did)["platform"]]:
            print(f"  ! {did}: fewer than 3 rivals with words on its own platform, "
                  f"borrowed from {', '.join(info['rivals_from'])}")
    print(f"\nNext: a fresh subagent answers {rel(SHEET)} into {rel(PICKS)}, "
          "then python3 code/buyer_test.py record")


# ---------------------------------------------------------------- record

def read_picks() -> dict:
    raw = load_json(PICKS, "The buyer hasn't answered yet.")
    picks = {}
    items = raw.items() if isinstance(raw, dict) else ((r.get("q") or r.get("id"), r) for r in raw)
    for qid, value in items:
        pick = value.get("pick") if isinstance(value, dict) else value
        why = value.get("why", "") if isinstance(value, dict) else ""
        if qid and isinstance(pick, str) and pick.strip().upper()[:1] in LETTERS:
            picks[str(qid).strip()] = (pick.strip().upper()[:1], why)
    return picks


def variety(s_drafts: list) -> tuple:
    angles = [(d.get("angle") or "").lower() for d in s_drafts if (d.get("angle") or "").lower() in ANGLES]
    counts = {a: angles.count(a) for a in ANGLES if a in angles}
    ok = len(counts) >= MIN_ANGLES and all(n / max(len(angles), 1) <= MAX_ANGLE_SHARE for n in counts.values())
    return ok, counts


def rsa_lines(s_drafts: list) -> tuple:
    heads, descs = [], []
    for d in s_drafts:
        if d.get("platform") != "google":
            continue
        for h in d.get("headline") or []:
            if h.lower() not in (x.lower() for x in heads):
                heads.append(h)
        for t in d.get("description") or []:
            if t.lower() not in (x.lower() for x in descs):
                descs.append(t)
    return heads, descs


def record(drafts_path: Path) -> None:
    key = load_json(KEY, "Run python3 code/buyer_test.py build first.")
    drafts = load_json(drafts_path, "No drafts file.")
    picks = read_picks()
    results = {}
    for qid, q in key["questions"].items():
        r = results.setdefault(q["draft"], {"wins": 0, "answered": 0, "lost_to": [], "why": [], "lost_lines": []})
        if qid not in picks:
            continue
        letter, why = picks[qid]
        r["answered"] += 1
        if letter == q["ours"]:
            r["wins"] += 1
        else:
            r["lost_to"].append(q["options"][LETTERS.index(letter)])
            r["lost_lines"] += [h.strip() for h in q.get("shown_headline", "").split(" | ") if h.strip()]
            if why:
                r["why"].append(why)

    missing = [qid for qid in key["questions"] if qid not in picks]
    if missing:
        print(f"! {len(missing)} questions unanswered ({', '.join(missing[:8])}...). "
              "Those drafts can't reach S until every run is answered.")

    for d in drafts:
        r, info = results.get(d.get("id")), key["drafts"].get(d.get("id"))
        if not r or not info:
            continue
        if info["hash"] != draft_hash(d):
            print(f"! {d['id']} changed since the sheet was built - rebuild before trusting it")
            d["buyer_test"], d["tier"] = None, None
            continue
        d["buyer_test"] = {"wins": r["wins"], "runs": RUNS}
        d["buyer_hash"] = info["hash"]
        d["beats"] = info["rivals"]
        d["buyer_notes"] = r["why"][:3]
        d["lost_lines"] = sorted(set(r["lost_lines"]))   # headlines on screen when theirs won
        passed = d.get("gate_rules") == "pass" and r["answered"] == RUNS and r["wins"] >= WINS_NEEDED
        d["tier"] = "S" if passed else None

    drafts_path.write_text(json.dumps(drafts, indent=2, ensure_ascii=False))
    report(drafts)


def report(drafts: list) -> None:
    tested = [d for d in drafts if d.get("buyer_test")]
    s_tier = [d for d in drafts if d.get("tier") == "S"]
    print(f"Gate 2: {len(s_tier)} of {len(tested)} tested drafts won {WINS_NEEDED}+ of {RUNS} runs -> tier S\n")
    for d in tested:
        bt = d["buyer_test"]
        mark = "S   " if d.get("tier") == "S" else "back"
        print(f"  {mark} {d['id']} {bt['wins']}/{bt['runs']} [{d.get('angle') or 'no angle'}]")
        if d.get("tier") != "S" and d.get("buyer_notes"):
            print(f"       lost because: {d['buyer_notes'][0]}")

    ok, counts = variety(s_tier)
    spread = ", ".join(f"{a} {n}" for a, n in counts.items()) or "none"
    print(f"\nGate 3, the variety floor: {'PASS' if ok else 'NOT YET'} · angles in tier S: {spread}")
    if not ok:
        missing = [a for a in ANGLES if a not in counts]
        print(f"  Needs {MIN_ANGLES}+ of the 6 angles and none over a third. "
              f"Write more of: {', '.join(missing) or 'the thin angles'}")

    heads, descs = rsa_lines(s_tier)
    enough = len(heads) >= RSA_HEADLINES and len(descs) >= RSA_DESCRIPTIONS
    print(f"\nOne Google ad needs {RSA_HEADLINES} headlines and {RSA_DESCRIPTIONS} descriptions from tier S: "
          f"have {len(heads)} and {len(descs)} -> {'READY for /publish-ads' if enough else 'write more and run the gates again'}")


def status(drafts_path: Path) -> None:
    if not KEY.exists():
        print("No sheet built yet: python3 code/buyer_test.py build")
        return
    key = json.loads(KEY.read_text())
    answered = len(read_picks()) if PICKS.exists() else 0
    print(f"Sheet built {key['built_at']}: {len(key['questions'])} questions, {answered} answered.")
    if drafts_path.exists():
        report(json.loads(drafts_path.read_text()))


def main():
    ap = argparse.ArgumentParser(description="Gate 2: the blind buyer test.")
    ap.add_argument("step", choices=["build", "record", "status"])
    ap.add_argument("--file", help="drafts file (default data/new-ads.json)")
    ap.add_argument("--ranked", help="ranked competitor ads (default data/ranked.json)")
    ap.add_argument("--retest", action="store_true", help="build: test every gate-1 pass again, not just new ones")
    args = ap.parse_args()

    def resolve(value, default):
        path = Path(value) if value else default
        return path if path.is_absolute() else ROOT / path

    drafts_path = resolve(args.file, DRAFTS)
    if args.step != "build" and not args.file and KEY.exists():
        # Score the same file the sheet was built from.
        drafts_path = resolve(json.loads(KEY.read_text()).get("drafts_file"), DRAFTS)
    if args.step == "build":
        build(drafts_path, resolve(args.ranked, RANKED), args.retest)
    elif args.step == "record":
        record(drafts_path)
    else:
        status(drafts_path)


if __name__ == "__main__":
    main()
