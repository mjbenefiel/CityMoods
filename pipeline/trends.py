"""Trends data for the Trends page: a year of 311 counts by neighborhood and request type (Chicago first).

The city's portal counts the requests on its side (grouped by community area and request type), so no
individual request, address or location is ever downloaded. Writes:

  docs/data/chicago/trends.json         windows (7, 30, 90, 180, 365 days) x request type x neighborhood,
                                        mood totals, citywide totals, neighborhood population
  docs/data/chicago/trends-series.json  13 thirty-day periods per request type x neighborhood (trend lines)
  docs/data/chicago/close.json          how fast the city closes each request type: citywide "usually within N days",
                                        share closed within a week and share still open, plus the same shares
                                        by neighborhood (only where a neighborhood has CLOSE_MIN+ requests)

Privacy, same rules as the rest of the site:
  * neighborhood totals only; any count under MIN_CELL (3) is published as null ("under 3"), zeros too
  * people-related request types (moods_chicago.SENSITIVE) and grim types are left out entirely
  * only common request types (TYPE_MIN reports a year citywide); rare ones stay citywide-only elsewhere
  * the population table is total residents per community area only, nothing demographic

Run on its own:  python3 pipeline/trends.py [--force]
The nightly build calls export_trends() after the cities; it skips the work if Chicago has no new day.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, get, log  # noqa: E402
from build import MIN_CELL, assert_no_pii  # noqa: E402
from cities import CITIES  # noqa: E402
import moods_chicago as chi  # noqa: E402
from moods import _GRIM_RE  # noqa: E402

BLOCK, NBLOCKS = 30, 13          # thirteen 30-day periods: 390 days, enough for "1 year" plus a trend line
WINDOWS = [7, 30, 90, 180, 365]
TYPE_MIN = 100                   # a request type needs this many reports citywide in the past year to be listed
POP_API = "https://data.cityofchicago.org/resource/7umk-8dtw.json"   # ACS 5-year data by community area
CLOSE_LAG = 30                   # time to close counts requests made in the year ending this many days ago,
CLOSE_MIN = 20                   # so each had at least a month; neighborhood shares need this many requests
CLOSE_STEPS = [1, 3, 7, 14, 30, 90]   # "usually closed within N days" steps (None = over 90 days)


def _counts(C, start: dt.date, end: dt.date) -> Counter:
    """(community area id, request type) -> count for requests created in [start, end)."""
    where = f"created_date >= '{start}T00:00:00' AND created_date < '{end}T00:00:00' AND {C.WHERE}"
    rows = get(C.api_311, params={"$select": "community_area,sr_type,count(*) as n", "$where": where,
                                  "$group": "community_area,sr_type", "$limit": 50000}).json()
    if len(rows) >= 50000:
        raise SystemExit("Trends: too many rows in one period; shorten BLOCK")
    out = Counter()
    for r in rows:
        if r.get("community_area") and r.get("sr_type"):
            out[(str(int(float(r["community_area"]))), r["sr_type"])] += int(r["n"])
    return out


def _population(hoods: list[dict]) -> dict[str, int]:
    """Community area id -> total residents (latest ACS 5-year estimate). Names are matched to the boundary file."""
    rows = get(POP_API, params={"$select": "community_area,total_population,acs_year", "$limit": 200}).json()
    norm = lambda s: "".join(ch for ch in s.upper() if ch.isalnum())
    by_name = {norm(h["raw_name"]): h["id"] for h in hoods}
    pop = {}
    for r in rows:
        hid = by_name.get(norm(r.get("community_area", "")))
        if hid and r.get("total_population"):
            pop[hid] = int(float(r["total_population"]))
    missing = [h["name"] for h in hoods if h["id"] not in pop]
    if missing:
        log(f"Trends: no population for {', '.join(missing)}")
    return pop


def _inlist(types: list[str]) -> str:
    return ",".join("'" + t.replace("'", "''") + "'" for t in types)


def _close(C, types: list[str], ids: list[str], last: dt.date) -> dict:
    """How fast the city closes each listed request type. All of it is counted on the portal's side, in 30-day
    blocks (a whole year in one query is slow and sometimes times out). City totals are the neighborhoods added up."""
    end = last + dt.timedelta(days=1) - dt.timedelta(days=CLOSE_LAG)
    start = end - dt.timedelta(days=365)
    within = "".join(f", sum(case(status='Completed' and date_diff_d(closed_date, created_date) <= {d},1,true,0)) as d{d}"
                     for d in CLOSE_STEPS)
    select = f"community_area,sr_type,count(*) as n,sum(case(status='Open',1,true,0)) as open{within}"
    keys = ["n", "open"] + [f"d{d}" for d in CLOSE_STEPS]
    by = defaultdict(lambda: dict.fromkeys(keys, 0))
    b_start = start
    while b_start < end:
        b_end = min(b_start + dt.timedelta(days=BLOCK), end)
        where = (f"status in ('Completed','Open') AND created_date >= '{b_start}T00:00:00' AND created_date < '{b_end}T00:00:00' "
                 f"AND sr_type in ({_inlist(types)}) AND {C.WHERE}")
        for r in get(C.api_311, params={"$select": select, "$where": where,
                                        "$group": "community_area,sr_type", "$limit": 50000}).json():
            if r.get("community_area") and r.get("sr_type"):
                cell = by[(str(int(float(r["community_area"]))), r["sr_type"])]
                for k in keys:
                    cell[k] += int(r[k])
        b_start = b_end
    city = defaultdict(lambda: dict.fromkeys(keys, 0))
    for (a, t), cell in by.items():
        for k in keys:
            city[t][k] += cell[k]
    pct = lambda part, n: round(100 * part / n) if n else None
    out_types = []
    for t in types:
        c = city.get(t)
        if not c or c["n"] < CLOSE_MIN:
            out_types.append(None)
            continue
        # "Usually closed within N days": the first step that covers half of all requests (None = over 90 days)
        typ = next((d for d in CLOSE_STEPS if c[f"d{d}"] * 2 >= c["n"]), None)
        out_types.append({"n": c["n"], "typ": typ, "wk": pct(c["d7"], c["n"]), "open": pct(c["open"], c["n"])})
    areas = [[(lambda v: [pct(v["d7"], v["n"]), pct(v["open"], v["n"])] if v and v["n"] >= CLOSE_MIN else None)(by.get((a, t)))
              for a in ids] for t in types]
    return {"updated": str(last), "window": {"start": str(start), "end": str(end - dt.timedelta(days=1))},
            "min_n": CLOSE_MIN, "type_names": types, "types": out_types, "areas": areas}


def _cell(n: int) -> int | None:
    return n if n >= MIN_CELL else None


def export_trends(key: str = "chicago", force: bool = False):
    if key != "chicago":
        raise SystemExit("Trends are Chicago-only for now")
    C = CITIES[key]
    out_dir = DATA / key
    days = json.loads((out_dir / "index.json").read_text())["days"]
    last = dt.date.fromisoformat(days[0])            # newest day on the site
    target = out_dir / "trends.json"
    if target.exists() and not force and json.loads(target.read_text()).get("updated") == str(last):
        log(f"Trends: {C.name} already up to date through {last}")
        return
    end = last + dt.timedelta(days=1)

    # Neighborhoods, in community area order. load_hoods() also makes sure the boundary file is cached;
    # its raw upper-case names are what the population table uses.
    loaded = C.load_hoods()
    cache = Path(__file__).resolve().parent / "cache" / "chicago_community_areas.geojson"
    raw = {str(int(f["properties"]["area_numbe"])): f["properties"]["community"]
           for f in json.loads(cache.read_text())["features"]}
    hoods = sorted(({"id": h["id"], "name": h["name"], "side": h["borough"], "raw_name": raw[h["id"]]} for h in loaded),
                   key=lambda h: int(h["id"]))
    ids = [h["id"] for h in hoods]

    # Thirteen 30-day periods (newest first), a 7-day window and the 5 days that turn 360 into 365.
    log(f"Trends: counting {C.name} requests for the year through {last} (about 3 minutes)...")
    blocks = []
    for k in range(NBLOCKS):
        b_end = end - dt.timedelta(days=BLOCK * k)
        blocks.append((b_end - dt.timedelta(days=BLOCK), b_end, _counts(C, b_end - dt.timedelta(days=BLOCK), b_end)))
    week = _counts(C, end - dt.timedelta(days=7), end)
    edge = _counts(C, end - dt.timedelta(days=365), end - dt.timedelta(days=360))
    win = {7: week, 30: blocks[0][2], 90: sum((b[2] for b in blocks[:3]), Counter()),
           180: sum((b[2] for b in blocks[:6]), Counter()), 365: sum((b[2] for b in blocks[:12]), Counter()) + edge}

    # Which request types to list: public, not grim, common enough
    year_by_type = Counter()
    for (a, t), n in win[365].items():
        year_by_type[t] += n
    def ok(t):
        return chi.is_public(t) and not _GRIM_RE.search(f"{t} {chi.nice(t)}".lower())
    types = [t for t, n in year_by_type.most_common() if n >= TYPE_MIN and ok(t)]
    public = {t for t in year_by_type if ok(t)}     # mood totals use every public type, listed or not

    counts, moods, citywide = {}, {}, {}
    for w in WINDOWS:
        c = win[w]
        counts[str(w)] = [[_cell(c.get((a, t), 0)) for a in ids] for t in types]
        by_mood = defaultdict(Counter)
        city_t = Counter()
        for (a, t), n in c.items():
            if t in public:
                by_mood[chi.mood_of(t)][a] += n
                city_t[t] += n
        moods[str(w)] = {m: [_cell(cnt.get(a, 0)) for a in ids] for m, cnt in sorted(by_mood.items())}
        citywide[str(w)] = [_cell(city_t.get(t, 0)) for t in types]

    try:
        pop = _population(hoods)
    except Exception as e:                           # keep last night's numbers if the portal hiccups
        log(f"Trends: population not refreshed ({type(e).__name__}: {e})")
        old = json.loads(target.read_text()) if target.exists() else {}
        pop = {a["id"]: a.get("pop") for a in old.get("areas", []) if a.get("pop")}

    data = {
        "city": key, "name": C.name, "updated": str(last),
        "windows": [{"days": w, "start": str(end - dt.timedelta(days=w)), "end": str(last)} for w in WINDOWS],
        "areas": [{"id": h["id"], "name": h["name"], "side": h["side"], "pop": pop.get(h["id"])} for h in hoods],
        "types": [{"label": chi.nice(t), "type": t, "mood": chi.mood_of(t)} for t in types],
        "counts": counts, "moods": moods, "citywide": citywide,
        "min_cell": MIN_CELL,
        "population_source": "U.S. Census Bureau American Community Survey 5-year estimates, via the City of Chicago Data Portal",
    }
    series = {
        "city": key, "updated": str(last),
        "periods": [{"start": str(s), "end": str(e - dt.timedelta(days=1))} for s, e, _ in reversed(blocks)],
        "types": [[[_cell(b[2].get((a, t), 0)) for b in reversed(blocks)] for a in ids] for t in types],
    }
    try:
        close = _close(C, types, ids, last)
    except Exception as e:                           # time to close is extra; never let it stop the trends
        log(f"Trends: time to close not refreshed ({type(e).__name__}: {e})")
        close = None
    for obj in (data, series, close or {}):
        assert_no_pii(obj)
    (out_dir / "trends-series.json").write_text(json.dumps(series, separators=(",", ":")))
    if close:
        (out_dir / "close.json").write_text(json.dumps(close, separators=(",", ":")))
    target.write_text(json.dumps(data, separators=(",", ":")))
    log(f"Trends: wrote {len(types)} request types x {len(ids)} neighborhoods through {last}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    export_trends(force=ap.parse_args().force)
