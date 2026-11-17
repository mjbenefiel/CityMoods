"""CityMood daily build.

Fetches one full day of NYC 311 service requests, works out which neighborhood each one
came from, and publishes neighborhood totals only. No addresses, coordinates or individual
requests ever leave this script.

    python pipeline/build.py              # build the latest complete day
    python pipeline/build.py --date 2026-11-14
    python pipeline/build.py --no-claude  # skip the Claude headline

Writes docs/data/latest.json, docs/data/days/<date>.json, docs/data/index.json and,
once, docs/data/neighborhoods.geojson.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests
from shapely import STRtree
from shapely.geometry import Point, shape, mapping

sys.path.insert(0, str(Path(__file__).parent))
from moods import MOODS, mood_of, is_public, nice, detail_of, agency_of, rare_ok, whimsy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
CACHE = ROOT / "pipeline" / "cache"

API_311 = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
API_NTA = "https://data.cityofnewyork.us/resource/9nt8-h7nd.geojson?$limit=500"
API_WEATHER = ("https://api.open-meteo.com/v1/forecast?latitude=40.7128&longitude=-74.006"
               "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
               "&temperature_unit=fahrenheit&precipitation_unit=inch&timezone=America%2FNew_York&past_days=10")

# The ONLY fields ever requested from the 311 dataset. Addresses, cross streets, property IDs
# (BBL), zip codes, request IDs and the free-text resolution notes are never downloaded at all.
# descriptor ("Problem Detail") and descriptor_2 ("Additional Details") are fixed menu choices.
FIELDS_311 = "complaint_type,descriptor,descriptor_2,agency,latitude,longitude"

MIN_CELL = 3          # neighborhood-level counts below this are not published
KEEP_DAYS = 45
MIN_FULL_DAY = 5000   # a day with fewer requests than this is treated as still loading
UA = {"User-Agent": "CityMood/1.0"}
MODEL = os.environ.get("CITYMOOD_MODEL", "claude-opus-5-5")
BOROUGHS = ["Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get(url, **kw):
    for attempt in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=120, **kw)
            if r.status_code < 500 and r.status_code != 429:
                r.raise_for_status()
                return r
            log(f"  server said {r.status_code}, retrying")
        except (requests.ConnectionError, requests.Timeout) as e:
            log(f"  network problem ({type(e).__name__}), retrying")
        time.sleep(5 * 2 ** attempt)
    r = requests.get(url, headers=UA, timeout=120, **kw)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------- neighborhoods

def load_neighborhoods():
    CACHE.mkdir(parents=True, exist_ok=True)
    raw = CACHE / "nta2020.geojson"
    if not raw.exists():
        log("Downloading neighborhood boundaries...")
        raw.write_bytes(get(API_NTA).content)
    feats = json.loads(raw.read_text())["features"]
    hoods = []
    for f in feats:
        p = f["properties"]
        hoods.append({"id": p["nta2020"], "name": p["ntaname"], "borough": p["boroname"],
                      "geom": shape(f["geometry"])})
    out = DATA / "neighborhoods.geojson"
    if not out.exists():
        write_map(hoods, out)
    return hoods


def write_map(hoods, out: Path):
    """Simplified boundaries for the page (drawn by the browser, no map tiles needed)."""
    def rnd(o):
        if isinstance(o, (list, tuple)):
            if o and isinstance(o[0], (int, float)):
                return [round(o[0], 5), round(o[1], 5)]
            return [rnd(x) for x in o]
        return o
    feats = []
    for h in hoods:
        g = h["geom"].simplify(0.00025, preserve_topology=True)
        gm = mapping(g)
        feats.append({"type": "Feature", "id": h["id"],
                      "properties": {"name": h["name"], "borough": h["borough"]},
                      "geometry": {"type": gm["type"], "coordinates": rnd(gm["coordinates"])}})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
    log(f"Wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")


# ---------------------------------------------------------------- 311 data

def day_bounds(day: dt.date):
    return f"created_date >= '{day}T00:00:00' AND created_date < '{day + dt.timedelta(days=1)}T00:00:00'"


def newest_request() -> str:
    """Timestamp of the newest request in the city's dataset (NYC local time)."""
    return get(API_311, params={"$select": "max(created_date) as m"}).json()[0]["m"][:16]


def latest_complete_day(newest: str) -> dt.date:
    day = dt.date.fromisoformat(newest[:10]) - dt.timedelta(days=1)
    for _ in range(5):
        n = int(get(API_311, params={"$select": "count(*) as n", "$where": day_bounds(day)}).json()[0]["n"])
        if n >= MIN_FULL_DAY:
            return day
        day -= dt.timedelta(days=1)
    raise SystemExit("Couldn't find a complete day of 311 data.")


def fetch_day(day: dt.date) -> list[dict]:
    rows, offset = [], 0
    while True:
        page = get(API_311, params={"$select": FIELDS_311, "$where": day_bounds(day),
                                    "$limit": 50000, "$offset": offset, "$order": ":id"}).json()
        rows += page
        if len(page) < 50000:
            return rows
        offset += 50000


def detail_counts(day: dt.date) -> tuple[Counter, Counter]:
    """Counts per complaint type and per (type, detail label) for one day, totals only."""
    r = get(API_311, params={"$select": "complaint_type,descriptor,descriptor_2,count(*) as n",
                             "$where": day_bounds(day), "$group": "complaint_type,descriptor,descriptor_2",
                             "$limit": 20000}).json()
    types, details = Counter(), Counter()
    for x in r:
        t = x.get("complaint_type")
        if not t:
            continue
        n = int(x["n"])
        types[t] += n
        details[(t, detail_of(t, x.get("descriptor"), x.get("descriptor_2")) or nice(t))] += n
    return types, details


def month_detail_counts(day: dt.date) -> Counter:
    """How often each (type, detail) appeared in the 28 days before this one. Used to spot rare finds."""
    start = day - dt.timedelta(days=28)
    where = f"created_date >= '{start}T00:00:00' AND created_date < '{day}T00:00:00'"
    r = get(API_311, params={"$select": "complaint_type,descriptor,descriptor_2,count(*) as n", "$where": where,
                             "$group": "complaint_type,descriptor,descriptor_2", "$limit": 50000}).json()
    out = Counter()
    for x in r:
        t = x.get("complaint_type")
        if t:
            out[(t, detail_of(t, x.get("descriptor"), x.get("descriptor_2")) or nice(t))] += int(x["n"])
    return out


def rare_finds(city_details: Counter, month: Counter) -> list[dict]:
    """Things reported yesterday that happen less than about once a week. Citywide only."""
    out = []
    for (t, label), n in city_details.items():
        before = month.get((t, label), 0)
        if before <= 3 and rare_ok(t, label):
            out.append({"name": label, "mood": mood_of(t), "n": n, "past_28_days": before,
                        "_score": (whimsy(t, label), -before, n), "_fun": whimsy(t, label) >= 0})
    out.sort(key=lambda x: x["_score"], reverse=True)
    for x in out:
        x.pop("_score")
    return out[:15]


def strip_private(c: dict) -> dict:
    return {k: v for k, v in c.items() if not k.startswith("_")}


def baseline(day: dt.date) -> tuple[Counter, Counter]:
    """Average counts on the same weekday over the previous four weeks."""
    types, details = Counter(), Counter()
    for w in range(1, 5):
        t, d = detail_counts(day - dt.timedelta(weeks=w))
        types += t
        details += d
    return Counter({k: v / 4 for k, v in types.items()}), Counter({k: v / 4 for k, v in details.items()})


def weather(day: dt.date):
    try:
        d = get(API_WEATHER).json()["daily"]
        i = d["time"].index(day.isoformat())
        return {"high_f": round(d["temperature_2m_max"][i]), "low_f": round(d["temperature_2m_min"][i]),
                "rain_in": round(d["precipitation_sum"][i] or 0, 2)}
    except Exception as e:  # weather is a nice-to-have
        log(f"Weather unavailable: {e}")
        return None


# ---------------------------------------------------------------- aggregation

def assign(rows, hoods):
    """Neighborhood id for each request. Coordinates are discarded right here."""
    tree = STRtree([h["geom"] for h in hoods])
    out = []
    unplaced = 0
    for r in rows:
        ctype = r.get("complaint_type") or "Unknown"
        detail = detail_of(ctype, r.get("descriptor"), r.get("descriptor_2"))
        agency = agency_of(r.get("agency"))
        hood = None
        try:
            pt = Point(float(r["longitude"]), float(r["latitude"]))
            for idx in tree.query(pt, predicate="intersects"):
                hood = hoods[idx]["id"]
                break
        except (KeyError, TypeError, ValueError):
            pass
        if hood is None:
            unplaced += 1
        out.append((hood, ctype, detail, agency))
    rows.clear()  # drop the raw rows (and their coordinates) as soon as we're done
    return out, unplaced


def aggregate(assigned, hoods, base: Counter, base_details: Counter, month: Counter):
    city_types = Counter(t for _, t, _, _ in assigned)
    city_moods = Counter(mood_of(t) for _, t, _, _ in assigned)
    city_details = Counter((t, d or nice(t)) for _, t, d, _ in assigned if is_public(t))
    city_agencies = Counter(a for _, _, _, a in assigned)
    base_moods = Counter()
    for t, v in base.items():
        base_moods[mood_of(t)] += v

    by_hood = defaultdict(list)
    for h, t, d, a in assigned:
        if h:
            by_hood[h].append((t, d, a))

    names = {h["id"]: h for h in hoods}
    neighborhoods = {}
    for hid, recs in by_hood.items():
        types = [t for t, _, _ in recs]
        # Problem details, labelled with the mood they belong to. Requests without a detail
        # fall back to their complaint type name so each mood's parts still add up.
        details = Counter((mood_of(t), d or nice(t)) for t, d, _ in recs if is_public(t) and mood_of(t) != "other")
        agencies = Counter(a for _, _, a in recs)
        lead_agency, lead_n = agencies.most_common(1)[0]
        moods = Counter(mood_of(t) for t in types)
        named = [m for m in moods.most_common() if m[0] != "other"]
        top = named[0][0] if named and named[0][1] >= MIN_CELL else None
        neighborhoods[hid] = {
            "name": names[hid]["name"],
            "borough": names[hid]["borough"],
            "total": len(types),
            "top": top,
            "moods": {m: n for m, n in moods.items() if n >= MIN_CELL},
            # What makes up each mood's total, at the "Problem Detail" level.
            "details": [{"name": d, "mood": m, "n": n} for (m, d), n in details.most_common() if n >= MIN_CELL][:20],
            "agency": ({"name": lead_agency, "n": lead_n}
                       if lead_n >= MIN_CELL and lead_agency != "Other agencies" else None),
        }

    def ratio(now, typical):
        return round(now / typical, 2) if typical >= 1 else None

    moods = [{"id": m, "n": city_moods.get(m, 0), "typical": round(base_moods.get(m, 0)),
              "ratio": ratio(city_moods.get(m, 0), base_moods.get(m, 0))} for m in MOODS]
    moods.sort(key=lambda x: -x["n"])

    top_types = [{"name": nice(t), "raw": t, "mood": mood_of(t), "n": n, "typical": round(base.get(t, 0)),
                  "ratio": ratio(n, base.get(t, 0))}
                 for t, n in city_types.most_common() if is_public(t)][:12]
    spikes = [x for x in ({"name": nice(t), "mood": mood_of(t), "n": n, "typical": round(base.get(t, 0)),
                           "ratio": ratio(n, base.get(t, 0))}
                          for t, n in city_types.items() if is_public(t) and n >= 40)
              if x["ratio"] and x["ratio"] >= 1.6]
    spikes.sort(key=lambda x: -x["ratio"])

    top_details = [{"name": d, "mood": mood_of(t), "n": n, "typical": round(base_details.get((t, d), 0)),
                    "ratio": ratio(n, base_details.get((t, d), 0))}
                   for (t, d), n in city_details.most_common() if n >= 10][:15]
    odd = [x for x in ({"name": d, "mood": mood_of(t), "n": n, "typical": round(base_details.get((t, d), 0)),
                        "ratio": ratio(n, base_details.get((t, d), 0))}
                       for (t, d), n in city_details.items() if n >= 25)
           if x["ratio"] and x["ratio"] >= 1.8]
    odd.sort(key=lambda x: -x["ratio"])
    agencies = [{"name": a, "n": n} for a, n in city_agencies.most_common() if a != "Other agencies"]
    other_ag = city_agencies.get("Other agencies", 0)
    if other_ag:
        agencies.append({"name": "Other agencies", "n": other_ag})

    boroughs = defaultdict(Counter)
    for hid, info in neighborhoods.items():
        for m, n in info["moods"].items():
            boroughs[info["borough"]][m] += n
    borough_summary = {b: [{"id": m, "n": n} for m, n in c.most_common() if m != "other"][:3]
                       for b, c in sorted(boroughs.items())}

    return {"total": sum(city_types.values()), "typical_total": round(sum(base.values())),
            "moods": moods, "top_types": top_types, "spikes": spikes[:5],
            "top_details": top_details, "detail_spikes": odd[:6], "agencies": agencies,
            "rare_candidates": rare_finds(city_details, month),
            "boroughs": borough_summary, "neighborhoods": neighborhoods}


# ---------------------------------------------------------------- headline

PROMPT = """You write the daily headline for CityMood, a playful website that maps what New Yorkers reported to 311 (the city's non-emergency line) yesterday, grouped into "moods".

Here is yesterday's data (all numbers are counts of 311 requests; "typical" is the average for the same weekday over the previous four weeks):

{data}

Write:
- headline: at most 70 characters. Curious, warm, a little funny, like a friendly local columnist. Lead with the most interesting thing in the data (a big spike, or the mood that dominated).
- blurb: two short sentences that add one or two specific numbers from the data.
- boroughs: one short line (at most 90 characters) for each borough in the data, about what that borough reported most.

- rare_finds: pick the 3 most delightful or baffling items from rare_find_candidates (things that are reported less than about once a week) and give each a quip of at most 100 characters. Copy each name exactly as given. Quips may only riff on the item itself; never guess who reported it or where.

"Problem details" are the specific sub-types people chose (for example "Roaches" or "Loud music/party"); a vivid detail often makes a better headline than a broad mood. "Responding agencies" are the city departments the requests were sent to.

Rules:
- Use only the numbers and facts given. Do not invent events, causes, places or people. You may connect heat complaints to the temperatures given, and wet-weather complaints to the rain given, but nothing else.
- Laugh with the city, never at people. No jokes about poverty, homelessness, immigrants, landlords or tenants as people, or any group.
- Plain words. No hashtags, no emoji."""


def headline_with_claude(summary, day, wx):
    import anthropic

    compact = {
        "date": day.isoformat(), "weekday": day.strftime("%A"), "weather": wx,
        "total_requests": summary["total"], "typical_total": summary["typical_total"],
        "moods": [{"mood": MOODS[m["id"]]["label"], "count": m["n"], "typical": m["typical"]}
                  for m in summary["moods"] if m["id"] != "other"],
        "top_complaints": [{k: x[k] for k in ("name", "n", "typical")} for x in summary["top_types"][:8]],
        "unusual_spikes": [{k: x[k] for k in ("name", "n", "typical")} for x in summary["spikes"]],
        "top_problem_details": [{k: x[k] for k in ("name", "n", "typical")} for x in summary["top_details"][:10]],
        "unusual_problem_details": [{k: x[k] for k in ("name", "n", "typical")} for x in summary["detail_spikes"]],
        "responding_agencies": summary["agencies"][:5],
        "rare_find_candidates": [{k: x[k] for k in ("name", "n", "past_28_days")} for x in summary["rare_candidates"]],
        "boroughs": {b: [{"mood": MOODS[m["id"]]["label"], "count": m["n"]} for m in v]
                     for b, v in summary["boroughs"].items()},
    }
    schema = {
        "type": "object",
        "properties": {
            "headline": {"type": "string"},
            "blurb": {"type": "string"},
            "boroughs": {"type": "object",
                         "properties": {b: {"type": "string"} for b in BOROUGHS},
                         "required": BOROUGHS, "additionalProperties": False},
            "rare_finds": {"type": "array", "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "quip": {"type": "string"}},
                "required": ["name", "quip"], "additionalProperties": False}},
        },
        "required": ["headline", "blurb", "boroughs", "rare_finds"],
        "additionalProperties": False,
    }
    client = anthropic.Anthropic()
    try:
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": PROMPT.format(data=json.dumps(compact, indent=1))}],
        )
    except anthropic.APIConnectionError as e:
        log(f"Claude unreachable: {e}")
        return None
    except anthropic.APIStatusError as e:
        log(f"Claude API error {e.status_code}: {e.message}")
        return None
    u = resp.usage
    cost = (u.input_tokens * 4 + u.output_tokens * 20) / 1_000_000  # Claude Opus 5.5 list prices per token
    log(f"Claude usage: {u.input_tokens:,} input + {u.output_tokens:,} output tokens, about ${cost:.3f}")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(f"Claude: {u.input_tokens:,} input + {u.output_tokens:,} output tokens (about ${cost:.3f})\n\n")
    if resp.stop_reason != "end_turn":
        log(f"Claude stopped with {resp.stop_reason}; using the plain headline.")
        return None
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        log("Claude returned invalid JSON; using the plain headline.")
        return None
    out["by"] = "claude"
    return out


def headline_plain(summary, wx):
    top = next(m for m in summary["moods"] if m["id"] != "other")
    lab = MOODS[top["id"]]["label"].lower()
    if summary["spikes"]:
        s = summary["spikes"][0]
        head = f"{s['name']} reports jumped to {s['n']:,}, about {s['ratio']:.1f}x a typical day"
    else:
        head = f"New York's biggest gripe yesterday: {lab}"
    blurb = (f"New Yorkers made {summary['total']:,} requests to 311. "
             f"The top mood was {lab}, with {top['n']:,} reports.")
    if wx:
        blurb += f" The high was {wx['high_f']}°F."
    return {"headline": head, "blurb": blurb, "boroughs": {}, "by": "rules"}


# ---------------------------------------------------------------- privacy check

ADDRESS_RE = re.compile(r"\b\d{1,5}\s+[A-Z0-9 ]+\s(ST|STREET|AVE|AVENUE|RD|ROAD|BLVD|PL|PLACE|DR|LANE|LN)\b", re.I)
BANNED_KEYS = {"incident_address", "street_name", "cross_street_1", "cross_street_2", "intersection_street_1",
               "intersection_street_2", "bbl", "latitude", "longitude", "location", "unique_key",
               "x_coordinate_state_plane", "y_coordinate_state_plane", "incident_zip", "landmark"}


def assert_no_pii(obj, path="$"):
    """Fail the build if anything that looks like a record-level detail slipped into the output."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in BANNED_KEYS:
                raise SystemExit(f"Privacy check failed: field {k} at {path}")
            assert_no_pii(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            assert_no_pii(v, f"{path}[{i}]")
    elif isinstance(obj, float):
        precise = len(repr(obj).split(".")[-1]) >= 3
        if precise and (40.4 <= abs(obj) <= 41.0 or 73.6 <= abs(obj) <= 74.3):
            raise SystemExit(f"Privacy check failed: coordinate-like number {obj} at {path}")
    elif isinstance(obj, str):
        if ADDRESS_RE.search(obj):
            raise SystemExit(f"Privacy check failed: address-like text at {path}: {obj!r}")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--no-claude", action="store_true")
    args = ap.parse_args()

    hoods = load_neighborhoods()
    newest = newest_request()
    day = dt.date.fromisoformat(args.date) if args.date else latest_complete_day(newest)
    log(f"Building {day} ({day:%A})")

    rows = fetch_day(day)
    log(f"Fetched {len(rows):,} requests")
    assigned, unplaced = assign(rows, hoods)
    log(f"{unplaced:,} had no usable location (counted citywide only)")

    base_types, base_details = baseline(day)
    summary = aggregate(assigned, hoods, base_types, base_details, month_detail_counts(day))
    wx = weather(day)

    words = None
    if not args.no_claude and os.environ.get("ANTHROPIC_API_KEY"):
        words = headline_with_claude(summary, day, wx)
    words = words or headline_plain(summary, wx)

    # Rare finds: Claude's picks and quips when available, otherwise the top-scored candidates.
    cands = {c["name"]: c for c in summary.pop("rare_candidates")}
    picks = [dict(strip_private(cands[r["name"]]), quip=r["quip"][:140])
             for r in words.pop("rare_finds", []) if r.get("name") in cands]
    fallback = [strip_private(c) for c in cands.values() if c["_fun"]]
    summary["rare_finds"] = (picks or fallback)[:4]

    entry = {"date": day.isoformat(), "weekday": day.strftime("%A"), "weather": wx,
             "built": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
             "source_newest": newest,
             "words": words, **summary}
    assert_no_pii(entry)

    days_dir = DATA / "days"
    days_dir.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
    (days_dir / f"{day}.json").write_text(blob)

    files = sorted(days_dir.glob("*.json"))
    for old in files[:-KEEP_DAYS]:
        old.unlink()
    dates = sorted((p.stem for p in days_dir.glob("*.json")), reverse=True)
    newest = dates[0]
    (DATA / "latest.json").write_text((days_dir / f"{newest}.json").read_text())
    (DATA / "index.json").write_text(json.dumps({"days": dates, "moods": MOODS}, ensure_ascii=False))

    log(f"Headline ({words['by']}): {words['headline']}")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(f"## {day}: {words['headline']}\n\n{words['blurb']}\n")


if __name__ == "__main__":
    main()
