"""CityMoods daily build.

For each city: fetch one full day of 311 service requests, work out which neighborhood each one
came from, and publish neighborhood totals only. No addresses, coordinates or individual
requests ever leave this script. City-specific settings live in cities.py.

    python pipeline/build.py                       # every city: build any new complete days
    python pipeline/build.py --city chicago
    python pipeline/build.py --city nyc --date 2026-11-14
    python pipeline/build.py --no-claude           # skip the Claude headline

Writes docs/data/<city>/latest.json, days/<date>.json, index.json and, once, neighborhoods.geojson,
plus docs/data/cities.json.
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

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, get, log  # noqa: E402
from city_pages import write_city_page  # noqa: E402
from moods import MOODS  # noqa: E402
from cities import CITIES, City  # noqa: E402

MIN_CELL = 3          # neighborhood-level counts below this are not published
KEEP_DAYS = None      # every built day stays on the site (about 230 KB a day for all five cities)
MAX_CATCH_UP = 7      # never build more than this many missed days in one run
MODEL = os.environ.get("CITYMOODS_MODEL", "claude-opus-5-5")

C: City = CITIES["nyc"]   # the city being built right now (set in main)


# ---------------------------------------------------------------- comparisons

def baseline(day: dt.date) -> tuple[Counter, Counter]:
    """Average counts on the same weekday over the previous four weeks."""
    types, details = Counter(), Counter()
    for w in range(1, 5):
        t, d = C.detail_counts(day - dt.timedelta(weeks=w))
        types += t
        details += d
    return Counter({k: v / 4 for k, v in types.items()}), Counter({k: v / 4 for k, v in details.items()})


def rare_finds(city_details: Counter, month: Counter) -> list[dict]:
    """Things reported yesterday that happen less than about once a week. Citywide only."""
    out = []
    for (t, label), n in city_details.items():
        before = month.get((t, label), 0)
        if before <= C.rare_max_28 and C.rare_ok(t, label):
            score = C.whimsy(t, label)
            out.append({"name": label, "mood": C.mood_of(t), "n": n, "past_28_days": before,
                        "_score": (score, -before, n), "_fun": score >= 0})
    out.sort(key=lambda x: x["_score"], reverse=True)
    for x in out:
        x.pop("_score")
    return out[:15]


def strip_private(c: dict) -> dict:
    return {k: v for k, v in c.items() if not k.startswith("_")}


def weather(day: dt.date):
    try:
        d = get(C.weather).json()["daily"]
        i = d["time"].index(day.isoformat())
        return {"high_f": round(d["temperature_2m_max"][i]), "low_f": round(d["temperature_2m_min"][i]),
                "rain_in": round(d["precipitation_sum"][i] or 0, 2)}
    except Exception as e:  # weather is a nice-to-have
        log(f"Weather unavailable: {e}")
        return None


# ---------------------------------------------------------------- aggregation

DISTINCT_MIN = 5        # a neighborhood needs at least this many reports of a detail for it to count
DISTINCT_MIN_TOTAL = 30  # ...and at least this many reports overall, so tiny areas don't produce flukes


def distinctive(details: Counter, hood_total: int, city_keys: Counter, city_total: int):
    """The detail this neighborhood reports most out of proportion to the rest of the city.

    Score = (share of this neighborhood's reports) / (share of the city's reports). 3.0 means
    "three times the city's rate". Returns None if nothing stands out.
    """
    if hood_total < DISTINCT_MIN_TOTAL:
        return None
    best = None
    for (mood, label), n in details.items():
        city_n = city_keys.get((mood, label), 0)
        if n < DISTINCT_MIN or city_n < 20:
            continue
        x = (n / hood_total) / (city_n / city_total)
        if best is None or (x, n) > (best["x"], best["n"]):
            best = {"name": label, "mood": mood, "n": n, "x": round(x, 1)}
    return best if best and best["x"] >= 1.5 else None


def aggregate(assigned, hoods, base: Counter, base_details: Counter, month: Counter):
    mood_of, is_public, nice = C.mood_of, C.is_public, C.nice
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
    # Citywide counts of each (mood, detail), for working out what's distinctive about a neighborhood.
    city_keys = Counter((mood_of(t), d or nice(t)) for _, t, d, _ in assigned if is_public(t) and mood_of(t) != "other")
    city_total = len(assigned)
    for hid, recs in by_hood.items():
        types = [t for t, _, _ in recs]
        # Details, labelled with the mood they belong to. Requests without a detail fall back to
        # their request type name so each mood's parts still add up.
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
            "details": [{"name": d, "mood": m, "n": n} for (m, d), n in details.most_common() if n >= MIN_CELL][:20],
            "distinct": distinctive(details, len(recs), city_keys, city_total),
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
    if city_agencies.get("Other agencies"):
        agencies.append({"name": "Other agencies", "n": city_agencies["Other agencies"]})

    regions = defaultdict(Counter)
    for info in neighborhoods.values():
        for m, n in info["moods"].items():
            regions[info["borough"]][m] += n
    # Cities without boroughs/areas (SF, Boston) skip the per-region lines.
    region_summary = ({b: [{"id": m, "n": n} for m, n in c.most_common() if m != "other"][:3]
                       for b, c in sorted(regions.items())} if C.regions else {})

    return {"total": sum(city_types.values()), "typical_total": round(sum(base.values())),
            "moods": moods, "top_types": top_types, "spikes": spikes[:5],
            "top_details": top_details, "detail_spikes": odd[:6], "agencies": agencies,
            "rare_candidates": rare_finds(city_details, month),
            "boroughs": region_summary, "neighborhoods": neighborhoods}


# ---------------------------------------------------------------- headline

PROMPT = """You write the daily headline for CityMoods, a playful website that maps what {people} reported to 311 ({city}'s non-emergency line) on a given day, grouped into "moods".

People will often read this a day or two later, so never say "yesterday", "today" or "last night"; when you need to say when, use the weekday (it's in the data).

Here is the day's data (all numbers are counts of 311 requests; "typical" is the average for the same weekday over the previous four weeks):

{data}

Write:
- headline: at most 70 characters. Curious, warm, a little funny, like a friendly local columnist. Lead with the most interesting thing in the data (a big spike or the mood that dominated).
- blurb: two short sentences that add one or two specific numbers from the data.
- card_line: at most 45 characters. A witty one-liner capturing the city's mood that day, for its card on the front page, in the same columnist voice, saying something different from the headline. The card already shows the label "The mood", the city name and the date, so don't use the word "mood", the weekday or the city's name. No numbers needed.
{regions_line}
- rare_finds: pick the 3 most absurd items from rare_find_candidates and give each a quip of at most 130 characters. Copy each name exactly as given.
  Background (the page already explains this to readers, so you don't need to): each candidate is an official option on the city's 311 menu that someone picked on this day, and it usually gets picked less than about once a week. Don't make every quip about menus or dropdowns; vary the angle.
  Voice: a jaded, deadpan local who has seen everything and is unimpressed by City Hall. Sharp, dry, a little edgy, with attitude. Roast the bureaucracy itself: the agencies ({agency_examples} and so on, as institutions), the forms, the oddly specific dropdown categories, the slow response times, the red tape, the city somehow having an official process for this.
  Make the three quips different in shape (a one-liner, a mock memo or status update, a deadpan observation). Avoid "what's the deal" and any Seinfeld-style setups.
  Never make fun of the person who called, never guess who reported it or where, and don't mock individual city workers as people (no "lazy worker" jokes): the target is the system, not the people doing the jobs. Don't name, quote or impersonate any real comedian, TV show or character. Nothing about bodies, race, religion, money troubles, politics or politicians.

Don't reuse puns, phrases, jokes or openings from recent_writing_to_avoid_repeating (other days' headlines and quips); each day should feel fresh. Don't repeat a recent quip's structure or punchline.

"Problem details" are the specific sub-types people chose; a vivid detail often makes a better headline than a broad mood. "Responding agencies" are the city departments the requests were sent to.

Rules:
- Use only the numbers and facts given. Do not invent events, causes, places or people. You may connect heat complaints to the temperatures given, and wet-weather complaints to the rain given, but nothing else.
- Laugh with the city, never at people. No jokes about poverty, homelessness, immigrants, landlords or tenants as people, or any group.
- Plain words. No hashtags, no emoji."""


def recent_writing(day: dt.date, n: int = 7) -> dict:
    """Claude's headlines and quips from the nearest other days, so it doesn't repeat itself."""
    heads, quips = [], []
    others = sorted((p for p in (C.data_dir / "days").glob("*.json") if p.stem != day.isoformat()),
                    key=lambda p: abs((dt.date.fromisoformat(p.stem) - day).days))[:n]
    for p in others:
        try:
            d = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if d.get("words", {}).get("by") == "claude":
            heads.append(d["words"]["headline"])
            quips += [r["quip"] for r in d.get("rare_finds", []) if r.get("quip")]
    return {"headlines": heads, "quips": quips}


def headline_with_claude(summary, day, wx):
    import anthropic

    compact = {
        "city": C.name, "date": day.isoformat(), "weekday": day.strftime("%A"), "weather": wx,
        "total_requests": summary["total"], "typical_total": summary["typical_total"],
        "moods": [{"mood": MOODS[m["id"]]["label"], "count": m["n"], "typical": m["typical"]}
                  for m in summary["moods"] if m["id"] != "other" and m["n"]],
        "top_complaints": [{k: x[k] for k in ("name", "n", "typical")} for x in summary["top_types"][:8]],
        "unusual_spikes": [{k: x[k] for k in ("name", "n", "typical")} for x in summary["spikes"]],
        "top_problem_details": [{k: x[k] for k in ("name", "n", "typical")} for x in summary["top_details"][:10]],
        "unusual_problem_details": [{k: x[k] for k in ("name", "n", "typical")} for x in summary["detail_spikes"]],
        "responding_agencies": summary["agencies"][:5],
        "recent_writing_to_avoid_repeating": recent_writing(day),
        "rare_find_candidates": [{k: x[k] for k in ("name", "n", "past_28_days")} for x in summary["rare_candidates"]],
        "regions": {b: [{"mood": MOODS[m["id"]]["label"], "count": m["n"]} for m in v]
                    for b, v in summary["boroughs"].items()},
    }
    props = {
        "headline": {"type": "string"},
        "blurb": {"type": "string"},
        "card_line": {"type": "string"},
        "rare_finds": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "quip": {"type": "string"}},
            "required": ["name", "quip"], "additionalProperties": False}},
    }
    if C.regions:
        props["regions"] = {"type": "object", "properties": {b: {"type": "string"} for b in C.regions},
                            "required": C.regions, "additionalProperties": False}
    else:
        compact.pop("regions", None)
    schema = {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    regions_line = (f"- regions: one short line (at most 90 characters) for each {C.region_word} in the data, "
                    f"about what it reported most.\n" if C.regions else "")
    prompt = PROMPT.format(people=C.people, city=C.name, regions_line=regions_line,
                           agency_examples=C.agency_examples, data=json.dumps(compact, indent=1))
    # A slow reply must never hold up the daily update: wait at most 90 s, retry once, then fall back.
    client = anthropic.Anthropic(timeout=90.0, max_retries=1)
    started = time.monotonic()
    try:
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APITimeoutError:
        log(f"Claude took too long ({time.monotonic() - started:.0f}s); using the plain headline.")
        return None
    except anthropic.APIConnectionError as e:
        log(f"Claude unreachable: {e}")
        return None
    except anthropic.APIStatusError as e:
        log(f"Claude API error {e.status_code}: {e.message}")
        return None
    u = resp.usage
    cost = (u.input_tokens * 4 + u.output_tokens * 20) / 1_000_000  # Claude Opus 5.5 list prices per token
    log(f"Claude usage: {u.input_tokens:,} input + {u.output_tokens:,} output tokens, about ${cost:.3f}, "
        f"{time.monotonic() - started:.0f}s")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(f"Claude ({C.name}): {u.input_tokens:,} input + {u.output_tokens:,} output tokens (about ${cost:.3f})\n\n")
    if resp.stop_reason != "end_turn":
        log(f"Claude stopped with {resp.stop_reason}; using the plain headline.")
        return None
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        log("Claude returned invalid JSON; using the plain headline.")
        return None
    out["boroughs"] = out.pop("regions", {})   # the page calls them "boroughs" for every city
    if len(out.get("card_line", "")) > 60:     # keep the card tidy if Claude runs long
        out["card_line"] = out["card_line"][:57].rsplit(" ", 1)[0] + "…"
    out["by"] = "claude"
    return out


def headline_plain(summary, wx, day):
    top = next((m for m in summary["moods"] if m["id"] != "other"), summary["moods"][0])
    lab = MOODS[top["id"]]["label"].lower()
    if summary["spikes"]:
        s = summary["spikes"][0]
        head = f"{s['name']} reports jumped to {s['n']:,}, about {s['ratio']:.1f}x a typical day"
    else:
        head = f"{C.name}'s biggest gripe on {day:%A}: {lab}"
    blurb = (f"{C.people} made {summary['total']:,} requests to 311. "
             f"The top mood was {lab}, with {top['n']:,} reports.")
    if wx:
        blurb += f" The high was {wx['high_f']}°F."
    return {"headline": head, "blurb": blurb, "boroughs": {}, "by": "rules"}


# ---------------------------------------------------------------- privacy check

ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+(?:[A-Za-z0-9]+\s){0,4}(?:ST|STREET|AVE|AVENUE|RD|ROAD|BLVD|PL|PLACE|DR|LANE|LN)\b"
    # ...but "57 calls for street fixes" or "street noise" aren't addresses: those are our own category names.
    r"(?![\s-]+(?:fix|fixes|noise|light|lights|sweeping|condition|vendor|sign|signs|tree|trees|fair|food|cleaning)\b)",
    re.I)
BANNED_KEYS = {
    # NYC
    "incident_address", "street_name", "cross_street_1", "cross_street_2", "intersection_street_1",
    "intersection_street_2", "bbl", "latitude", "longitude", "location", "unique_key",
    "x_coordinate_state_plane", "y_coordinate_state_plane", "incident_zip", "landmark", "resolution_description",
    # Chicago
    "street_address", "street_number", "street_direction", "street_type", "zip_code", "sr_number",
    "x_coordinate", "y_coordinate", "police_beat", "precinct", "parent_sr_number", "legacy_sr_number",
    # Los Angeles
    "casenumber", "locator_gis_returned_address", "locator_sr_house_number_", "locator_sr_street_name__c",
    "zipcode__c", "geolocation__latitude__s", "geolocation__longitude__s", "assigned_to__c",
    # San Francisco
    "service_request_id", "status_notes", "address", "street", "lat", "long", "point", "point_geom", "media_url",
    # Boston
    "case_id", "full_address", "closure_comments", "submitted_photo", "closed_photo",
}
# Latitude/longitude ranges for every city we cover (NYC, Chicago, LA, SF, Boston).
_COORD_RANGES = [(40.4, 41.0), (73.6, 74.3), (41.6, 42.1), (87.5, 88.0), (33.6, 34.4), (118.0, 118.8),
                 (37.6, 37.9), (122.3, 122.6), (42.2, 42.45), (70.9, 71.2)]


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
        if precise and any(lo <= abs(obj) <= hi for lo, hi in _COORD_RANGES):
            raise SystemExit(f"Privacy check failed: coordinate-like number {obj} at {path}")
    elif isinstance(obj, str):
        if ADDRESS_RE.search(obj):
            raise SystemExit(f"Privacy check failed: address-like text at {path}: {obj!r}")


# ---------------------------------------------------------------- build

def build_day(day: dt.date, hoods, newest: str, use_claude: bool):
    log(f"[{C.name}] Building {day} ({day:%A})")
    assigned, unplaced = C.fetch_records(day, hoods)
    log(f"{unplaced:,} had no usable neighborhood (counted citywide only)")

    base_types, base_details = baseline(day)
    summary = aggregate(assigned, hoods, base_types, base_details, C.month_detail_counts(day))
    wx = weather(day)

    words = headline_with_claude(summary, day, wx) if use_claude else None
    if words:
        # Claude never sees addresses, but if its writing ever trips the privacy check
        # (even as a false alarm), use the plain headline for this day instead of failing the build.
        try:
            assert_no_pii(words)
        except SystemExit as e:
            log(f"Claude's text tripped the privacy check ({e}); using the plain headline.")
            words = None
    words = words or headline_plain(summary, wx, day)

    # Rare finds: Claude's picks and quips when available, otherwise the top-scored candidates.
    cands = {c["name"]: c for c in summary.pop("rare_candidates")}
    picks = [dict(strip_private(cands[r["name"]]), quip=r["quip"][:160])
             for r in words.pop("rare_finds", []) if r.get("name") in cands]
    fallback = [strip_private(c) for c in cands.values() if c["_fun"]]
    summary["rare_finds"] = (picks or fallback)[:4]

    entry = {"city": C.key, "date": day.isoformat(), "weekday": day.strftime("%A"), "weather": wx,
             "built": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
             "source_newest": newest, "words": words, **summary}
    assert_no_pii(entry)

    days_dir = C.data_dir / "days"
    days_dir.mkdir(parents=True, exist_ok=True)
    (days_dir / f"{day}.json").write_text(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))

    log(f"[{C.name}] Headline ({words['by']}): {words['headline']}")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(f"## {C.name}, {day}: {words['headline']}\n\n{words['blurb']}\n\n")


def refresh_indexes():
    days_dir = C.data_dir / "days"
    if KEEP_DAYS:
        for old in sorted(days_dir.glob("*.json"))[:-KEEP_DAYS]:
            old.unlink()
    dates = sorted((p.stem for p in days_dir.glob("*.json")), reverse=True)
    if not dates:
        return
    (C.data_dir / "latest.json").write_text((days_dir / f"{dates[0]}.json").read_text())
    (C.data_dir / "index.json").write_text(json.dumps({"days": dates, "moods": MOODS, "city": C.meta()},
                                                      ensure_ascii=False))
    write_cities_list()
    write_city_page(C.key, C.name, json.loads((days_dir / f"{dates[0]}.json").read_text()))


def write_cities_list():
    listed = [c.meta() for c in CITIES.values() if (c.data_dir / "index.json").exists()]
    (DATA / "cities.json").write_text(json.dumps({"cities": listed}, ensure_ascii=False))


def built_days() -> set[dt.date]:
    return {dt.date.fromisoformat(p.stem) for p in (C.data_dir / "days").glob("*.json")}


def plan_days(latest: dt.date, have: set[dt.date], force: bool) -> list[dt.date]:
    """Which days this run should build: any complete days after the last one built, oldest first.

    If the newest complete day is already built, there's nothing to do (unless forced), so a run
    that happens before the city's refresh doesn't rebuild yesterday's page or call Claude twice.
    """
    if force:
        return [latest]
    if latest in have:
        return []
    last = max((d for d in have if d < latest), default=latest - dt.timedelta(days=1))
    gap = (latest - last).days
    return [last + dt.timedelta(days=k) for k in range(1, gap + 1)][-MAX_CATCH_UP:]


def run_city(args, have_key: bool):
    hoods = C.load_hoods()
    newest = C.newest_request()

    if args.date or args.dates:
        raw = (args.dates or args.date).replace(",", " ").split()
        try:
            days = sorted({dt.date.fromisoformat(x) for x in raw})
        except ValueError:
            raise SystemExit(f"Dates must look like 2026-11-08; got: {raw}")
        latest = C.latest_complete_day(newest)
        if len(days) > 10 or any(d > latest for d in days):
            raise SystemExit(f"[{C.name}] Pick at most 10 days, none after {latest} (the newest complete day).")
        for day in days:
            build_day(day, hoods, newest, use_claude=have_key and args.claude)
            refresh_indexes()  # after every day, so a stopped run still keeps the days it finished
        return

    latest = C.latest_complete_day(newest)
    todo = plan_days(latest, built_days(), args.force)
    if not todo:
        log(f"[{C.name}] {latest} is already built and the city hasn't posted a newer full day yet "
            f"(its data runs through {newest}). Nothing to do.")
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
                fh.write(f"{C.name}: nothing new; {latest} is already built (data runs through {newest}).\n\n")
        return
    for day in todo:
        # Every day this run builds gets Claude's headline and quips, including caught-up days
        # (at most MAX_CATCH_UP, so a long outage costs at most a few Claude calls).
        build_day(day, hoods, newest, use_claude=have_key)
        refresh_indexes()


def main():
    global C
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="all", choices=["all", *CITIES])
    ap.add_argument("--date", help="build this one day (no Claude unless --claude)")
    ap.add_argument("--dates", help="several days, e.g. '2026-11-08 2026-11-09' (max 10)")
    ap.add_argument("--claude", action="store_true", help="with --date/--dates: let Claude write those days too")
    ap.add_argument("--no-claude", action="store_true")
    ap.add_argument("--force", action="store_true", help="rebuild the newest day even if it already exists")
    args = ap.parse_args()
    have_key = bool(os.environ.get("ANTHROPIC_API_KEY")) and not args.no_claude

    failed = []
    for key in (CITIES if args.city == "all" else [args.city]):
        C = CITIES[key]
        try:
            run_city(args, have_key)
        except SystemExit as e:   # one city's problem shouldn't stop the others
            log(f"[{C.name}] stopped: {e}")
            failed.append(key)
        except Exception as e:
            log(f"[{C.name}] failed: {type(e).__name__}: {e}")
            failed.append(key)
    write_cities_list()
    if failed:
        raise SystemExit(f"Some cities failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
