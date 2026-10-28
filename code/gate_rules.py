"""Gate 1: the mechanical rules. No judgment, no debate.

    python3 code/gate_rules.py                                   # checks data/new-ads.json in place
    python3 code/gate_rules.py --file data/sample/new-ads.json
    python3 code/gate_rules.py --platform google --kind headline --line "Live in 8 weeks, or free"

A Google draft is the ad as a phone shows it: 3 headlines and 2 descriptions, as lists. One bad
line sends the whole draft back, with the line and the reason named.

Writes `gate_rules` on every draft: "pass", or the reasons it died. A draft that fails loses
any tier it had. The rules and word lists live in references/gates.md, the slot sizes in
references/ad-specs.md, the claims you can make in context/proof.md and the names you can't
use in context/competitors.md.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROOF = ROOT / "context" / "proof.md"
BUSINESS_ENV = ROOT / ".env"
COMPETITORS = ROOT / "context" / "competitors.md"
GATES = ROOT / "references" / "gates.md"
ADS = ROOT / "data" / "ads.json"
NEW_ADS = ROOT / "data" / "new-ads.json"

LIMITS = {
    "google": {"headline": 30, "description": 90},
    "meta": {"headline": 40, "body": 125, "description": 30},
    "tiktok": {"headline": 40, "body": 100},
    "linkedin": {"headline": 70, "body": 150},
}
NEAR_DUPLICATE = 0.88
EXCLUDED_PROOF = re.compile(r"never|hold|gap|wrong|do not|don't", re.I)
UNITS = {"week", "day", "hour", "minute", "month", "year", "star", "review", "client", "customer",
         "member", "subscriber", "view", "lead", "call", "figure", "installment", "percent",
         "job", "project", "business", "video", "%"}
WORD_NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30}

INSERTION_RE = re.compile(r"\{[A-Za-z]+\([^)]*\)\s*:?([^}]*)\}|\{KeyWord\s*:\s*([^}]*)\}")
NUM_RE = re.compile(r"(?<![\w.])(\$?)(\d[\d,]*(?:\.\d+)?)(\s?[kKmM]\b)?(\+?)(%?)")
PHONE_RE = re.compile(r"\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
CAPS_RE = re.compile(r"\b[A-Z][A-Z']*[A-Z]\b")
GIMMICK_RE = re.compile(r"\b(?:[A-Za-z][\s.-]){3,}[A-Za-z]\b")
REPEAT_PUNCT_RE = re.compile(r"([!?.,$*/])\1|\?!|!\?")
ALLOWED_CHARS = re.compile(r"[\w\s.,:;'’\"“”?!&%$+/()#@*|-]", re.U)


# ---------------------------------------------------------------- reading the rules

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def sections(markdown: str) -> list:
    """-> [(heading, [lines])] for every ## heading."""
    out, heading, lines = [], None, []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if heading is not None:
                out.append((heading, lines))
            heading, lines = line[3:].strip(), []
        elif line.startswith("# "):
            if heading is not None:
                out.append((heading, lines))
            heading, lines = None, []
        elif heading is not None:
            lines.append(line)
    if heading is not None:
        out.append((heading, lines))
    return out


def bullets(lines: list) -> list:
    """One phrase per bullet. Anything after ' - ' is a note."""
    out = []
    for line in lines:
        line = line.strip()
        if line.startswith("- "):
            phrase = line[2:].split(" - ")[0].strip().strip("*").strip('"').strip()
            if phrase:
                out.append(phrase)
    return out


def gate_list(name: str) -> list:
    for heading, lines in sections(read(GATES)):
        if heading.lower() == name.lower():
            return bullets(lines)
    return []


def proof_text() -> str:
    """The claim part of every line in a "Can claim" style section. Sources and dates
    (after the first ' · ') are dropped so '27 Oct 2026' never becomes a provable 27."""
    keep = []
    for heading, lines in sections(read(PROOF)):
        if EXCLUDED_PROOF.search(heading):
            continue
        for line in lines:
            keep.append(line.split(" · ")[0])
    return "\n".join(keep)


def never_say() -> list:
    for heading, lines in sections(read(PROOF)):
        if re.search(r"never say", heading, re.I):
            return bullets(lines)
    return []


def env_value(key: str) -> str:
    for line in read(BUSINESS_ENV).splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def competitor_names() -> list:
    """Names and domains from context/competitors.md, plus advertisers in data/ads.json."""
    names = set()
    for line in read(COMPETITORS).splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        for part in re.split(r"\s[·|,]\s|\s-\s", line[2:]):
            part = part.strip().strip("*")
            if not part:
                continue
            names.add(part)
            if "." in part and " " not in part:
                names.add(part.split(".")[0])
    if ADS.exists():
        try:
            for ad in json.loads(read(ADS)):
                if ad.get("advertiser"):
                    names.add(str(ad["advertiser"]).strip())
        except (json.JSONDecodeError, TypeError):
            pass
    ours = env_value("BUSINESS_NAME").lower()
    unique = {}
    for n in sorted(names, key=lambda n: (len(n), n != n.lower()), reverse=True):
        unique.setdefault(n.lower(), n)
    return sorted(n for k, n in unique.items() if len(k) >= 3 and k != ours)


class Rules:
    def __init__(self):
        self.proof = proof_text()
        self.proof_lower = self.proof.lower()
        self.proof_nums, self.proof_pairs = numbers(self.proof)
        self.banned = list(dict.fromkeys(w.lower() for w in gate_list("Banned words") + never_say()))
        self.claim_words = [w.lower() for w in gate_list("Claim words")]
        self.caps_ok = {w.upper() for w in gate_list("Allowed capitals")}
        self.competitors = competitor_names()
        if not self.proof:
            print("! context/proof.md has no claims in it. Run /learn-business first.")


# ---------------------------------------------------------------- numbers

def numbers(text: str):
    """-> (set of numbers, set of (number, unit)). '$9,500' -> 9500 with unit '$',
    '150K+' -> 150000, '8-week' -> (8, 'week'), 'eight weeks' -> (8, 'week')."""
    text = re.sub(r"\b(" + "|".join(WORD_NUMBERS) + r")\b",
                  lambda m: str(WORD_NUMBERS[m.group(1).lower()]), text, flags=re.I)
    nums, pairs = set(), set()
    for m in NUM_RE.finditer(text):
        dollar, digits, suffix, _plus, pct = m.groups()
        try:
            value = float(digits.replace(",", ""))
        except ValueError:
            continue
        suffix = (suffix or "").strip().lower()
        value *= {"k": 1_000, "m": 1_000_000}.get(suffix, 1)
        key = str(int(value)) if value == int(value) else str(value)
        nums.add(key)
        unit = "$" if dollar else ("%" if pct else unit_after(text[m.end():m.end() + 40]))
        pairs.add((key, unit))
    return nums, pairs


def unit_after(rest: str):
    for word in re.findall(r"[a-z]+", rest.lower())[:3]:
        stem = word[:-1] if word.endswith("s") and word[:-1] in UNITS else word
        if stem in UNITS:
            return stem
        if stem == "percent":
            return "%"
    return None


def unproven_numbers(text: str, rules: Rules) -> list:
    nums, pairs = numbers(text)
    bad = []
    for key, unit in sorted(pairs, key=str):
        if key not in rules.proof_nums:
            bad.append(f"{key}{' ' + unit if unit and unit != '$' else ''}")
        elif unit and unit != "$" and (key, unit) not in rules.proof_pairs:
            bad.append(f"{key} {unit}")
    return bad


# ---------------------------------------------------------------- the checks

def visible(text: str) -> str:
    """An insertion tag serves as its fallback, so that's what counts."""
    return INSERTION_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)


def phrase_in(phrase: str, text_lower: str) -> bool:
    if re.match(r"\w", phrase) and re.search(r"\w$", phrase):
        return re.search(r"\b" + re.escape(phrase) + r"\b", text_lower) is not None
    return phrase in text_lower


def check_text(text: str, platform: str, field: str, rules: Rules) -> list:
    reasons = []
    shown = visible(text).strip()
    lower = shown.lower()

    limit = LIMITS.get(platform, {}).get(field)
    if limit and len(shown) > limit:
        reasons.append(f"{field} is {len(shown)} characters, the slot is {limit}")
    if not shown:
        reasons.append(f"{field} is empty")

    squashed = re.sub(r"[^a-z0-9]", "", lower)
    for name in rules.competitors:
        n = name.lower()
        if phrase_in(n, lower) or (len(n) >= 6 and re.sub(r"[^a-z0-9]", "", n) in squashed):
            reasons.append(f"competitor name: {name}")
            break

    for phrase in rules.banned:
        if phrase_in(phrase, lower):
            reasons.append(f"banned: \"{phrase}\"")

    caps = [w for w in CAPS_RE.findall(shown) if w.replace("'", "") not in rules.caps_ok]
    if caps:
        reasons.append(f"ALL CAPS: {', '.join(caps)}")
    if "!!" in shown:
        reasons.append('"!!"')
    elif platform == "google" and field == "headline" and "!" in shown:
        reasons.append("no ! in a Google headline")
    elif platform == "google" and field == "description" and shown.count("!") > 1:
        reasons.append("more than one ! in a Google description")
    if REPEAT_PUNCT_RE.search(shown):
        reasons.append("repeated punctuation")
    if "\u2014" in shown or "\u2013" in shown:
        reasons.append("em or en dash, use a hyphen")
    odd = sorted(set(ch for ch in shown if not ALLOWED_CHARS.match(ch) and ch not in "\u2014\u2013"))
    if odd:
        reasons.append(f"symbol or emoji: {' '.join(odd)}")
    if PHONE_RE.search(shown):
        reasons.append("phone number in the text, it goes in a call asset")
    if GIMMICK_RE.search(shown):
        reasons.append("gimmick spacing")

    bad_nums = unproven_numbers(shown, rules)
    if bad_nums:
        reasons.append(f"not in proof.md: {', '.join(bad_nums)}")
    for word in rules.claim_words:
        stem = word.rstrip("s")
        if re.search(r"\b" + re.escape(stem), lower) and not re.search(r"\b" + re.escape(stem), rules.proof_lower):
            reasons.append(f"claim not in proof.md: \"{word}\"")
    return reasons


SHAPE = {"google": {"headline": 3, "description": 2}}   # a draft is the ad as a phone shows it


def lines_of(draft: dict) -> list:
    """-> [(field, label, text)]. Google drafts hold lists (3 headlines, 2 descriptions),
    Meta, TikTok and LinkedIn drafts hold single strings."""
    out = []
    for field in ("headline", "body", "description"):
        value = draft.get(field)
        if value is None:
            continue
        items = value if isinstance(value, list) else [value]
        for i, text in enumerate(items, start=1):
            text = str(text or "").strip()
            if text:
                out.append((field, f"{field} {i}" if isinstance(value, list) else field, text))
    return out


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", visible(text).lower()).strip()


def draft_hash(draft: dict) -> str:
    """Fingerprint of a draft's words. A buyer-test verdict only holds for the words it judged."""
    text = json.dumps([t for _, _, t in lines_of(draft)], ensure_ascii=False)
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def shape_problems(draft: dict, platform: str) -> list:
    problems = []
    for field, want in SHAPE.get(platform, {}).items():
        got = draft.get(field)
        n = len(got) if isinstance(got, list) else (1 if got else 0)
        if n != want:
            problems.append(f"needs {want} {field}s, has {n}")
    if platform != "google" and not (draft.get("headline") or draft.get("body")):
        problems.append("needs a headline or body")
    return problems


def check_drafts(drafts: list, rules: Rules) -> list:
    pool = []            # (platform, field, normalised line, draft id) from drafts that passed
    for i, draft in enumerate(drafts, start=1):
        draft.setdefault("id", f"d{i:02d}")
        if draft.get("buyer_hash") and draft["buyer_hash"] != draft_hash(draft):
            # Rewritten since the buyer judged it: the old verdict no longer applies.
            draft.update({"buyer_test": None, "buyer_hash": None, "tier": None, "beats": []})
        platform = (draft.get("platform") or "").lower()
        reasons = [] if platform in LIMITS else [f"unknown platform {platform!r}"]
        reasons += shape_problems(draft, platform)
        lines = lines_of(draft)
        seen = set()
        for field, label, text in lines:
            for r in check_text(text, platform, field, rules):
                reasons.append(f'{label} "{text}": {r}')
            key = norm(text)
            if key in seen:
                reasons.append(f'{label} "{text}": said twice in this draft')
            seen.add(key)
        if not reasons:
            for field, label, text in lines:
                key = norm(text)
                twin = next((d for p, f, other, d in pool if p == platform and f == field and
                             difflib.SequenceMatcher(None, key, other).ratio() >= NEAR_DUPLICATE), None)
                if twin:
                    reasons.append(f'{label} "{text}": near-duplicate of a line in {twin}')
        if reasons:
            draft["gate_rules"] = "; ".join(dict.fromkeys(reasons))
            draft["tier"] = None
        else:
            draft["gate_rules"] = "pass"
            pool += [(platform, f, norm(t), draft["id"]) for f, _, t in lines]
    return drafts


# ---------------------------------------------------------------- main

def show(drafts: list) -> None:
    ok = [d for d in drafts if d["gate_rules"] == "pass"]
    print(f"Gate 1: {len(ok)} of {len(drafts)} drafts passed, {len(drafts) - len(ok)} go back\n")
    for d in drafts:
        mark = "pass" if d["gate_rules"] == "pass" else "BACK"
        print(f"  {mark} {d['id']} [{d.get('platform')}{' · ' + d['angle'] if d.get('angle') else ''}]")
        for _, label, text in lines_of(d):
            print(f"       {label:<13} {text}")
        if d["gate_rules"] != "pass":
            for reason in d["gate_rules"].split("; "):
                print(f"       x {reason}")
    heads = sum(len(d["headline"]) for d in ok if isinstance(d.get("headline"), list))
    descs = sum(len(d["description"]) for d in ok if isinstance(d.get("description"), list))
    if heads or descs:
        print(f"\nGoogle lines through gate 1: {heads} headlines, {descs} descriptions "
              "(one ad needs 15 and 4 after the buyer test)")


def main():
    ap = argparse.ArgumentParser(description="Gate 1: mechanical rules for new ads.")
    ap.add_argument("--file", help="drafts file (default data/new-ads.json)")
    ap.add_argument("--line", action="append", help="check one line instead of a file (repeatable)")
    ap.add_argument("--platform", default="google")
    ap.add_argument("--kind", default="headline", help="headline | description | body")
    args = ap.parse_args()

    rules = Rules()
    if args.line:
        failed = 0
        for text in args.line:
            reasons = check_text(text, args.platform, args.kind, rules)
            failed += bool(reasons)
            print(f"{'pass' if not reasons else 'BACK'}  [{args.platform} {args.kind}] {text}")
            for r in reasons:
                print(f"      x {r}")
        sys.exit(1 if failed else 0)

    path = Path(args.file) if args.file else NEW_ADS
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        sys.exit(f"No {path.relative_to(ROOT)} yet. Write the drafts first (see /write-ads).")
    try:
        drafts = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"{path.name} isn't valid JSON: {exc}")
    check_drafts(drafts, rules)
    path.write_text(json.dumps(drafts, indent=2, ensure_ascii=False))
    show(drafts)


if __name__ == "__main__":
    main()
