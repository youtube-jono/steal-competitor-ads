"""Put the S-tier ads in Google Ads: one Search campaign, one ad group, one responsive search ad.

    python3 code/publish_ads.py                 # validate only (default) - Google checks it, nothing is created
    python3 code/publish_ads.py --apply         # creates it, everything PAUSED
    python3 code/publish_ads.py --customer 1234567890      # a different account than .env

Reads:
  data/new-ads.json      the S-tier Google drafts (15 headlines and 4 descriptions are picked from them)
  context/business.md    Market (country), Monthly ad budget, Landing page, Keywords to bid on
  .env                   GOOGLE_ADS_* keys, GOOGLE_ADS_CUSTOMER_ID, BUSINESS_NAME, SITE_BASE_URL

Safety, in code:
- validate_only unless --apply. Even with --apply, Google validates the whole request first.
- The campaign, the ad group and the ad are created PAUSED. A paused campaign can't spend,
  whatever its budget says. Enabling it is a human decision in the Google Ads UI.
- The account's name must match BUSINESS_NAME in .env, so ads never land in the wrong account.
- Only tier S lines go in. --allow-untested (gate 1 passes, no buyer test yet) works for a
  validate-only check and is refused with --apply.
- Every operation is a create. Nothing existing is edited or removed.

Writes data/published.json. Built from the working push code in ads-test-drive (push_ads.py,
build_campaigns.py, _common.py), copied here so this repo stands alone.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_rules import draft_hash  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DRAFTS = DATA / "new-ads.json"
BUSINESS = ROOT / "context" / "business.md"
OUT = DATA / "published.json"

HEADLINES, DESCRIPTIONS = 15, 4
HEADLINE_MAX, DESCRIPTION_MAX, PATH_MAX = 30, 90, 15
MAX_KEYWORDS = 20
COUNTRY_GEO = {
    "united states": "2840", "usa": "2840", "us": "2840", "canada": "2124", "ca": "2124",
    "united kingdom": "2826", "uk": "2826", "australia": "2036", "new zealand": "2554",
    "ireland": "2372",
}


# ---------------------------------------------------------------- reading the project

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


def business_text() -> str:
    if not BUSINESS.exists():
        sys.exit("No context/business.md. Run /learn-business first.")
    return BUSINESS.read_text(encoding="utf-8")


def read_line(text: str, label: str):
    m = re.search(rf"^{label}:\s*(.+)$", text, re.M | re.I)
    return m.group(1).strip() if m else None


def read_keywords(text: str) -> list:
    keywords, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = "keyword" in line.lower()
            continue
        if inside and line.strip().startswith("- "):
            kw = line.strip()[2:].split(" · ")[0].strip().lower()
            if kw and kw not in keywords:
                keywords.append(kw)
    return keywords[:MAX_KEYWORDS]


def daily_budget(text: str, override) -> float:
    if override:
        return float(override)
    m = re.search(r"Monthly ad budget:\s*\$?([\d,]+)", text, re.I)
    if not m:
        sys.exit('No "Monthly ad budget: $2,000 a month" line in context/business.md. '
                 "Add one, or pass --daily-budget 20.")
    return round(int(m.group(1).replace(",", "")) / 30.4, 2)


def country_geo(text: str, override) -> str:
    name = (override or read_line(text, "Market") or "").strip().lower()
    name = re.split(r"[,(·]", name)[0].strip()
    if name not in COUNTRY_GEO:
        sys.exit(f'Can\'t target {name or "an empty market"!r}. Add "Market: United States" to '
                 "context/business.md, or pass --country US.")
    return COUNTRY_GEO[name]


ISO_BY_GEO = {"2840": "US", "2124": "CA", "2826": "GB", "2036": "AU", "2554": "NZ", "2372": "IE"}


def city_geo(client, city: str, country_geo: str):
    """MAIN_CITY as a Google city target inside the market's country. (id, name) or None."""
    svc = client.get_service("GeoTargetConstantService")
    req = client.get_type("SuggestGeoTargetConstantsRequest")
    req.locale = "en"
    req.country_code = ISO_BY_GEO.get(country_geo, "US")
    req.location_names.names.append(city)
    for s in svc.suggest_geo_target_constants(request=req).geo_target_constant_suggestions:
        g = s.geo_target_constant
        if g.target_type == "City" and g.status.name == "ENABLED":
            return g.resource_name.split("/")[-1], g.canonical_name
    return None


def live_url(url: str) -> str:
    """The page must load, because Google rejects an ad whose final URL is dead."""
    try:
        r = requests.get(url, timeout=20, allow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (publish_ads.py)"})
    except requests.RequestException as exc:
        sys.exit(f"The landing page {url} didn't load: {exc}")
    if r.status_code != 200:
        sys.exit(f"The landing page {url} returned {r.status_code}. Fix the page first.")
    return r.url


def paths_from(keyword: str, override):
    words = (override or "").strip("/").split("/") if override else None
    if not words and keyword:
        parts = re.sub(r"[^a-z0-9 ]", "", keyword.lower()).split()
        words = ["-".join(parts[:2]), "-".join(parts[2:])]
    words = [w[:PATH_MAX] for w in (words or []) if w]
    return (words + ["", ""])[:2]


# ---------------------------------------------------------------- picking the lines

def pick_lines(drafts: list, allow_untested: bool) -> tuple:
    """Round-robin across the drafts, best buyer-test result first, so every angle that won
    gets a headline before any angle gets a second one."""
    google = [d for d in drafts if (d.get("platform") or "").lower() == "google"]
    if allow_untested:
        chosen = [d for d in google if d.get("gate_rules") == "pass"]
    else:
        # S only counts for the exact words the buyer judged.
        chosen = [d for d in google if d.get("tier") == "S" and d.get("buyer_hash") == draft_hash(d)]
    chosen.sort(key=lambda d: -((d.get("buyer_test") or {}).get("wins") or 0))

    def round_robin(field, limit):
        # A headline that was on screen when the buyer picked theirs goes in last, if at all.
        lost = {l.lower() for d in chosen for l in d.get("lost_lines") or []} if field == "headline" else set()
        out, seen = [], set(lost)
        lists = [d.get(field) if isinstance(d.get(field), list) else [d.get(field)] for d in chosen]
        for i in range(max((len(l) for l in lists), default=0)):
            for lines in lists:
                if i < len(lines) and lines[i] and lines[i].strip().lower() not in seen:
                    seen.add(lines[i].strip().lower())
                    out.append(lines[i].strip())
        for lines in lists:                  # only if the winners run short
            out += [l.strip() for l in lines if l and l.strip().lower() in lost and l.strip() not in out]
        return out[:limit]

    return chosen, round_robin("headline", HEADLINES), round_robin("description", DESCRIPTIONS)


def check_lines(headlines: list, descriptions: list) -> list:
    problems = []
    if len(headlines) < HEADLINES:
        problems.append(f"{len(headlines)} headlines, one ad needs {HEADLINES}")
    if len(descriptions) < DESCRIPTIONS:
        problems.append(f"{len(descriptions)} descriptions, one ad needs {DESCRIPTIONS}")
    problems += [f"headline over {HEADLINE_MAX}: {h!r}" for h in headlines if len(h) > HEADLINE_MAX]
    problems += [f"description over {DESCRIPTION_MAX}: {d!r}" for d in descriptions if len(d) > DESCRIPTION_MAX]
    return problems


# ---------------------------------------------------------------- Google Ads

def load_client(env: dict):
    """From ads-test-drive code/_common.py. Keys come from .env and are never printed."""
    from google.ads.googleads.client import GoogleAdsClient
    cfg = {
        "client_id": env.get("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": env.get("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": env.get("GOOGLE_ADS_REFRESH_TOKEN"),
        "login_customer_id": env.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID") or None,
        "use_proto_plus": True,
    }
    missing = [k for k, v in cfg.items() if not v and k != "login_customer_id"]
    if missing:
        sys.exit(f"Missing Google Ads keys in .env: {', '.join(missing)}")
    if env.get("GOOGLE_ADS_DEVELOPER_TOKEN"):
        cfg["developer_token"] = env["GOOGLE_ADS_DEVELOPER_TOKEN"]
    return GoogleAdsClient.load_from_dict(cfg)


def account_name(client, customer_id: str) -> str:
    ga = client.get_service("GoogleAdsService")
    for row in ga.search(customer_id=customer_id, query="SELECT customer.descriptive_name FROM customer"):
        return row.customer.descriptive_name
    return ""


def unused_name(client, customer_id: str, base: str) -> str:
    ga = client.get_service("GoogleAdsService")
    rows = ga.search(customer_id=customer_id, query=(
        "SELECT campaign.name FROM campaign WHERE campaign.status != 'REMOVED'"))
    taken = {r.campaign.name for r in rows}
    name, n = base, 2
    while name in taken:
        name, n = f"{base} ({n})", n + 1
    return name


def build_ops(client, customer_id: str, plan: dict) -> list:
    """budget -> campaign (PAUSED) -> country -> ad group (PAUSED) -> keywords -> ad (PAUSED).
    Temporary negative ids tie them together in one atomic request."""
    ga, enums, ops = client.get_service("GoogleAdsService"), client.enums, []
    budget_rn = ga.campaign_budget_path(customer_id, -1)
    campaign_rn = ga.campaign_path(customer_id, -2)
    ad_group_rn = ga.ad_group_path(customer_id, -3)

    op = client.get_type("MutateOperation")
    b = op.campaign_budget_operation.create
    b.resource_name = budget_rn
    b.name = f"{plan['campaign_name']} budget"
    b.amount_micros = int(round(plan["daily_budget"] * 100)) * 10_000
    b.delivery_method = enums.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False
    ops.append(op)

    op = client.get_type("MutateOperation")
    c = op.campaign_operation.create
    c.resource_name = campaign_rn
    c.name = plan["campaign_name"]
    c.status = enums.CampaignStatusEnum.PAUSED
    c.advertising_channel_type = enums.AdvertisingChannelTypeEnum.SEARCH
    c.campaign_budget = budget_rn
    c.network_settings.target_google_search = True
    c.network_settings.target_search_network = False
    c.network_settings.target_content_network = False
    c.network_settings.target_partner_search_network = False
    client.copy_from(c.maximize_conversions, client.get_type("MaximizeConversions"))
    c.geo_target_type_setting.positive_geo_target_type = enums.PositiveGeoTargetTypeEnum.PRESENCE
    c.geo_target_type_setting.negative_geo_target_type = enums.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = (
        enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING)
    ops.append(op)

    op = client.get_type("MutateOperation")
    cc = op.campaign_criterion_operation.create
    cc.campaign = campaign_rn
    cc.location.geo_target_constant = f"geoTargetConstants/{plan['geo']}"
    ops.append(op)

    op = client.get_type("MutateOperation")
    ag = op.ad_group_operation.create
    ag.resource_name = ad_group_rn
    ag.campaign = campaign_rn
    ag.name = plan["ad_group_name"]
    ag.status = enums.AdGroupStatusEnum.PAUSED
    ag.type_ = enums.AdGroupTypeEnum.SEARCH_STANDARD
    ops.append(op)

    for kw in plan["keywords"]:
        op = client.get_type("MutateOperation")
        agc = op.ad_group_criterion_operation.create
        agc.ad_group = ad_group_rn
        agc.status = enums.AdGroupCriterionStatusEnum.ENABLED   # inside a paused ad group
        agc.keyword.text = kw
        agc.keyword.match_type = enums.KeywordMatchTypeEnum.PHRASE
        ops.append(op)

    op = client.get_type("MutateOperation")
    ada = op.ad_group_ad_operation.create
    ada.ad_group = ad_group_rn
    ada.status = enums.AdGroupAdStatusEnum.PAUSED
    ada.ad.final_urls.append(plan["final_url"])
    rsa = ada.ad.responsive_search_ad
    for text in plan["headlines"]:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        rsa.headlines.append(asset)
    for text in plan["descriptions"]:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        rsa.descriptions.append(asset)
    if plan["path1"]:
        rsa.path1 = plan["path1"]
        if plan["path2"]:
            rsa.path2 = plan["path2"]
    ops.append(op)
    return ops


def assert_safe(ops: list) -> None:
    """Belt and braces: only creates, and every campaign, ad group and ad is PAUSED."""
    for op in ops:
        which = op._pb.WhichOneof("operation")
        inner = getattr(op, which)
        if inner._pb.WhichOneof("operation") != "create":
            sys.exit(f"REFUSING TO SEND: a {which} that isn't a create.")
        status = getattr(inner.create, "status", None)
        if which in ("campaign_operation", "ad_group_operation", "ad_group_ad_operation") and \
                status.name != "PAUSED":
            sys.exit(f"REFUSING TO SEND: a {which} that isn't PAUSED.")


def send(client, customer_id: str, ops: list, validate_only: bool):
    ga = client.get_service("GoogleAdsService")
    req = client.get_type("MutateGoogleAdsRequest")
    req.customer_id = customer_id
    req.mutate_operations.extend(ops)
    req.validate_only = validate_only
    req.partial_failure = False
    return ga.mutate(request=req)


def explain(exc) -> None:
    print(f"\nGoogle rejected it (request id {exc.request_id}). Nothing was created:")
    for err in exc.failure.errors:
        where = ".".join(f"{fp.field_name}{f'[{fp.index}]' if fp.index is not None else ''}"
                         for fp in err.location.field_path_elements) if err.location else ""
        print(f"  - {where} {err.error_code}: {err.message}")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="One paused Search campaign from the S-tier ads.")
    ap.add_argument("--apply", action="store_true", help="really create it (PAUSED). Default is validate only.")
    ap.add_argument("--file", help="drafts file (default data/new-ads.json)")
    ap.add_argument("--customer", help="Google Ads account id, if not GOOGLE_ADS_CUSTOMER_ID in .env")
    ap.add_argument("--final-url", help="landing page (default: 'Landing page:' in business.md, else SITE_BASE_URL)")
    ap.add_argument("--path", help="display path, e.g. google-ads/agency (default: from the first keyword)")
    ap.add_argument("--country", help="target the whole country (default: MAIN_CITY in .env, else 'Market:' in business.md)")
    ap.add_argument("--daily-budget", help="daily budget in account currency (default: monthly budget / 30.4)")
    ap.add_argument("--allow-untested", action="store_true",
                    help="use gate-1 passes with no buyer test. Validate only, refused with --apply.")
    args = ap.parse_args()

    if args.apply and args.allow_untested:
        sys.exit("--allow-untested is for checking the request only. Real ads have to be tier S.")

    env = load_env()
    text = business_text()
    drafts_path = Path(args.file) if args.file else DRAFTS
    if not drafts_path.is_absolute():
        drafts_path = ROOT / drafts_path
    if not drafts_path.exists():
        sys.exit(f"No {drafts_path.relative_to(ROOT)}. Run /write-ads first.")
    drafts = json.loads(drafts_path.read_text())

    chosen, headlines, descriptions = pick_lines(drafts, args.allow_untested)
    problems = check_lines(headlines, descriptions)
    if problems:
        print("NOT ENOUGH TO BUILD ONE AD. Nothing was sent to Google:")
        for p in problems:
            print(f"  - {p}")
        print("Write more drafts, run the gates again (/write-ads), then come back.")
        sys.exit(1)

    keywords = read_keywords(text)
    if not keywords:
        sys.exit('No keywords. Add a "## Keywords to bid on" list to context/business.md - '
                 "an ad group without keywords never shows.")
    final_url = live_url(args.final_url or read_line(text, "Landing page") or env.get("SITE_BASE_URL", ""))
    path1, path2 = paths_from(keywords[0], args.path)
    business = env.get("BUSINESS_NAME") or "Business"
    date = datetime.now().strftime("%Y-%m-%d")
    plan = {
        "daily_budget": daily_budget(text, args.daily_budget), "geo": country_geo(text, args.country),
        "final_url": final_url, "path1": path1, "path2": path2, "keywords": keywords,
        "headlines": headlines, "descriptions": descriptions,
        "campaign_name": f"{business} - Search - Competitor winners - {date}",
        "ad_group_name": keywords[0].capitalize(),
    }

    customer_id = re.sub(r"\D", "", args.customer or env.get("GOOGLE_ADS_CUSTOMER_ID", ""))
    if not customer_id:
        sys.exit("No GOOGLE_ADS_CUSTOMER_ID in .env and no --customer.")
    from google.ads.googleads.errors import GoogleAdsException
    client = load_client(env)
    try:
        name = account_name(client, customer_id)
    except GoogleAdsException as exc:
        explain(exc)
        sys.exit(1)
    if business.lower() not in name.lower():
        sys.exit(f"STOPPED: account {customer_id} is {name!r}, but BUSINESS_NAME is {business!r}. "
                 "Set GOOGLE_ADS_CUSTOMER_ID in .env to the right account, or pass --customer.")
    plan["campaign_name"] = unused_name(client, customer_id, plan["campaign_name"])
    city = (env.get("MAIN_CITY") or "").strip()
    if city and not args.country:
        try:
            found = city_geo(client, city, plan["geo"])
        except GoogleAdsException:
            found = None
        if found:
            plan["geo"], plan["geo_name"] = found
        else:
            print(f"! MAIN_CITY {city!r} isn't a Google city target. Targeting the whole country.")

    tested = "S tier" if not args.allow_untested else "gate 1 only, NOT buyer-tested"
    print(f"Account   {customer_id} · {name}")
    print(f"Campaign  {plan['campaign_name']} · Search · PAUSED · ${plan['daily_budget']:.2f}/day "
          f"(can't spend while paused) · targets {plan.get('geo_name') or plan['geo']}")
    print(f"Ad group  {plan['ad_group_name']} · PAUSED · {len(keywords)} phrase keywords: {', '.join(keywords)}")
    print(f"Ad        1 responsive search ad · PAUSED · {final_url} · /{path1}/{path2}")
    print(f"Lines     {len(headlines)} headlines and {len(descriptions)} descriptions from "
          f"{len(chosen)} drafts ({tested})")
    for h in headlines:
        print(f"  H {len(h):>2}  {h}")
    for d in descriptions:
        print(f"  D {len(d):>2}  {d}")

    ops = build_ops(client, customer_id, plan)
    assert_safe(ops)
    try:
        send(client, customer_id, ops, validate_only=True)
    except GoogleAdsException as exc:
        explain(exc)
        sys.exit(1)
    print(f"\nGoogle validated all {len(ops)} operations (validate_only). No policy or format errors.")

    result = {"customer_id": customer_id, "campaign_id": None, "campaign_name": plan["campaign_name"],
              "ad_group_id": None, "ad_ids": [], "status": "PAUSED", "validate_only": True,
              "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "account_name": name, "final_url": final_url, "path": [path1, path2],
              "daily_budget": plan["daily_budget"], "keywords": keywords,
              "geo": plan.get("geo_name") or plan["geo"],
              "headlines": headlines, "descriptions": descriptions,
              "drafts": [d.get("id") for d in chosen], "buyer_tested": not args.allow_untested}

    if args.apply:
        try:
            resp = send(client, customer_id, ops, validate_only=False)
        except GoogleAdsException as exc:
            explain(exc)
            sys.exit(1)
        for r in resp.mutate_operation_responses:
            which = r._pb.WhichOneof("response")
            rn = getattr(r, which).resource_name
            if which == "campaign_result":
                result["campaign_id"] = rn.split("/")[-1]
            elif which == "ad_group_result":
                result["ad_group_id"] = rn.split("/")[-1]
            elif which == "ad_group_ad_result":
                result["ad_ids"].append(rn.split("~")[-1])
        result["validate_only"] = False
        print(f"CREATED, all PAUSED: campaign {result['campaign_id']}, ad group {result['ad_group_id']}, "
              f"ad {', '.join(result['ad_ids'])}. Nothing spends until you enable it in Google Ads.")
    else:
        print("Nothing was created. Run again with --apply to create it, PAUSED.")

    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
