"""Build dashboard/index.html from whatever data exists.

Usage:
    python3 code/build_dashboard.py            # real data, or data/sample/ if data/ads.json is missing
    python3 code/build_dashboard.py --sample   # force the sample data
    python3 code/build_dashboard.py --out /tmp/x/index.html   # write somewhere else (for testing)

One self-contained HTML file: CSS, JS and data are inlined, so it opens by double-click.
Landing page screenshots stay as files and are linked with relative paths.
Each stage's section only appears once its file exists.
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASH = ROOT / "dashboard"
ASSETS = DASH / "assets"
CSS_FILES = ["shell.css", "views.css", "platforms.css"]
JS_FILES = ["util.js", "icons.js", "ads.js", "carousel.js", "panel.js", "views.js", "app.js"]
PLATFORMS = {"google", "meta", "facebook", "instagram", "tiktok", "linkedin"}
DOMAIN_RE = re.compile(r"\b((?:[a-z0-9-]+\.)+(?:com|co|io|net|org|ie|uk|ca|au|nz|ai|app|agency))\b", re.I)


def warn(msg):
    print(f"  warning: {msg}", file=sys.stderr)


def read_json(path, kind):
    """Read a JSON file. Missing is normal (stage not run yet). Broken is a warning, never a crash."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        warn(f"{path.relative_to(ROOT)} could not be read ({e}), skipping it")
        return None
    if not isinstance(data, kind):
        warn(f"{path.relative_to(ROOT)} should be a {kind.__name__}, skipping it")
        return None
    return data


def read_text(path):
    try:
        return path.read_text(encoding="utf-8") if path.exists() else None
    except OSError as e:
        warn(f"{path} could not be read ({e})")
        return None


def norm_url(u):
    """Compare landing URLs without query, fragment, www or trailing slash."""
    if not u or not isinstance(u, str):
        return None
    p = urllib.parse.urlparse(u.strip())
    host = (p.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return f"{host}{p.path.rstrip('/')}" if host else None


OUT_DIR = DASH  # where index.html is written; local paths are made relative to it


def local_asset(p):
    """Remote URLs pass through. Local paths become relative to the output folder (or None if the file is missing)."""
    if not p or not isinstance(p, str):
        return None
    if re.match(r"^https?://", p, re.I):
        return p
    if re.match(r"^[a-z][a-z0-9+.-]*:", p, re.I):
        return None
    path = Path(p) if Path(p).is_absolute() else ROOT / p
    if not path.exists():
        return None
    return urllib.parse.quote(os.path.relpath(path, OUT_DIR).replace(os.sep, "/"))


def clean_ads(ads):
    out = []
    for a in ads or []:
        if not isinstance(a, dict) or not a.get("id"):
            continue
        if str(a.get("platform", "")).lower() not in PLATFORMS:
            warn(f"ad {a.get('id')} has unknown platform {a.get('platform')!r}, skipping it")
            continue
        a = dict(a)
        media = a.get("media") if isinstance(a.get("media"), dict) else {}
        a["media"] = {k: local_asset(media.get(k)) for k in ("image", "video", "thumbnail")}
        if a.get("avatar"):
            a["avatar"] = local_asset(a["avatar"])
        if isinstance(a.get("cards"), list):
            a["cards"] = [{**c, "image": local_asset(c.get("image"))} for c in a["cards"] if isinstance(c, dict)]
        out.append(a)
    return out


def merge_ranked(ads, ranked):
    """ranked.json is the ads list plus score, tier, grade, rank, why. Merge by id."""
    if not ranked:
        return ads
    by_id = {r["id"]: r for r in ranked if isinstance(r, dict) and r.get("id")}
    keys = ("score", "tier", "grade", "rank", "why")
    merged = [{**a, **{k: by_id[a["id"]].get(k) for k in keys}} if a["id"] in by_id else a for a in ads]
    known = {a["id"] for a in ads}
    merged += clean_ads([r for r in by_id.values() if r["id"] not in known])
    return merged


def attach_pages(ads, pages):
    clean = []
    for p in pages or []:
        if isinstance(p, dict) and p.get("url"):
            clean.append({**p, "screenshot": local_asset(p.get("screenshot"))})
    by_ad, by_url = {}, {}
    for i, p in enumerate(clean):
        for aid in p.get("ad_ids") or []:
            by_ad.setdefault(aid, i)
        by_url.setdefault(norm_url(p["url"]), i)
    for a in ads:
        i = by_ad.get(a["id"], by_url.get(norm_url(a.get("landing_url"))))
        if i is not None:
            a["_page"] = i
    return clean


def parse_competitors(text):
    out = []
    for line in (text or "").splitlines():
        m = re.match(r"^\s*[-*]\s*(.+?)\s*[·|,-]\s*([a-z0-9.-]+\.[a-z]{2,})\s*$", line, re.I)
        if m:
            out.append({"name": m.group(1).strip(), "domain": m.group(2).lower()})
    return out


META_LINE = re.compile(r"^(read |source tiers|facts |sample data|[A-Z][A-Za-z ]{1,28}:\s)", re.I)
NEG_HEAD = re.compile(r"hold|never|wrong|weak|avoid|banned|don.?t|do not|not allowed|gap|fix", re.I)


def parse_business(text):
    """Name from the first heading, domain from the first domain-like word, summary from the opening paragraphs."""
    if not text:
        return None
    name, summary = None, []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("# ") and not name:
            name = re.sub(r"\s*\(sample\)\s*$", " (sample)", s[2:].strip())
            continue
        if s.startswith("## "):
            break
        if not s.startswith(("#", "-", "*", "|", ">")) and not META_LINE.match(s) and len(summary) < 2:
            summary.append(s)
    site = re.search(r"(?:landing page|website|site|domain):\s*(?:https?://)?(?:www\.)?([^\s/]+)", text, re.I)
    m = DOMAIN_RE.search(site.group(1)) if site else None
    m = m or DOMAIN_RE.search(text)
    return {"name": name, "domain": m.group(1).lower() if m else None, "summary": summary}


def parse_proof(text):
    """Bullets in proof.md are claims, grouped by their ## heading. 'claim · source' splits on the middle dot.
    If any heading says 'Can claim', only those sections count. Hold / Never say sections never count."""
    if not text:
        return None
    sections, cur = [], {"title": None, "items": []}
    for line in text.splitlines():
        h = re.match(r"^\s*#{2,4}\s+(.+)$", line)
        if h:
            sections.append(cur)
            cur = {"title": h.group(1).strip(), "items": []}
            continue
        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if m:
            parts = re.split(r"\s+·\s+", m.group(1), maxsplit=1)
            cur["items"].append({"claim": parts[0].strip(), "source": parts[1].strip() if len(parts) > 1 else None})
    sections.append(cur)
    sections = [x for x in sections if x["items"]]
    if any(x["title"] and re.search(r"can claim", x["title"], re.I) for x in sections):
        sections = [x for x in sections if x["title"] and re.search(r"can claim", x["title"], re.I)]
        for x in sections:
            x["title"] = re.sub(r"^can claim:?\s*", "", x["title"], flags=re.I).strip() or None
    else:
        sections = [x for x in sections if not (x["title"] and NEG_HEAD.search(x["title"]))]
    return sections or None


def build_payload(use_sample):
    real = (ROOT / "data" / "ads.json").exists() and not use_sample
    base = ROOT / "data" if real else ROOT / "data" / "sample"
    ctx = ROOT / "context" if real else base
    ads = clean_ads(read_json(base / "ads.json", list))
    ranked = read_json(base / "ranked.json", list)
    ads = merge_ranked(ads, ranked)
    pages = attach_pages(ads, read_json(base / "pages.json", list))
    proof = parse_proof(read_text(ctx / "proof.md"))
    drafts = [d for d in (read_json(base / "new-ads.json", list) or []) if isinstance(d, dict)]
    published = read_json(base / "published.json", dict)
    return {
        "mode": "real" if real else "sample",
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "competitors": parse_competitors(read_text(ROOT / "context" / "competitors.md")),
        "ads": ads,
        "pages": pages,
        "ranked": bool(ranked),
        "proof": proof,
        "business": parse_business(read_text(ctx / "business.md")) if proof else None,
        "drafts": drafts or None,
        "published": published,
    }


def inline_json(payload):
    """JSON inside a <script> tag: escape anything that could close the tag."""
    s = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return s.replace("</", "<\\/").replace("<!--", "<\\!--").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def build_html(payload):
    template = (ASSETS / "template.html").read_text(encoding="utf-8")
    css = "\n".join((ASSETS / f).read_text(encoding="utf-8") for f in CSS_FILES)
    js = "\n".join((ASSETS / "js" / f).read_text(encoding="utf-8") for f in JS_FILES)
    return (template.replace("/*__CSS__*/", css)
            .replace("/*__JS__*/", js)
            .replace("__PAYLOAD__", inline_json(payload)))


def main():
    ap = argparse.ArgumentParser(description="Build dashboard/index.html")
    ap.add_argument("--sample", action="store_true", help="use data/sample/ even if real data exists")
    ap.add_argument("--out", type=Path, default=DASH / "index.html", help="output file (default dashboard/index.html)")
    args = ap.parse_args()
    global OUT_DIR
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    OUT_DIR = out.parent
    payload = build_payload(args.sample)
    out.write_text(build_html(payload), encoding="utf-8")
    stages = [name for name, on in (("ranked", payload["ranked"]), ("your business", payload["proof"]),
                                    ("ours vs theirs", payload["drafts"]), ("published", payload["published"])) if on]
    print(f"Dashboard built from {payload['mode']} data: {len(payload['ads'])} ads, {len(payload['pages'])} landing pages"
          + (f", plus {', '.join(stages)}" if stages else ""))
    print(f"Open: {out}")


if __name__ == "__main__":
    main()
