"""Shared helpers for every city: paths, logging, polite HTTP with retries, map simplification."""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
CACHE = ROOT / "pipeline" / "cache"
UA = {"User-Agent": "CityMoods/1.0"}
# The public address of the site. Link previews need full URLs; change this when the custom domain is live.
SITE = "https://citymoods311.com/"


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


def day_bounds(day: dt.date, field: str = "created_date") -> str:
    return range_bounds(day, day + dt.timedelta(days=1), field)


def range_bounds(start: dt.date, end: dt.date, field: str = "created_date") -> str:
    """From the start of `start` up to (not including) the start of `end`."""
    return f"{field} >= '{start}T00:00:00' AND {field} < '{end}T00:00:00'"


def write_map(hoods, out: Path, tolerance: float = 0.00025):
    """Simplified boundaries for the page (drawn by the browser, no map tiles needed)."""
    def rnd(o):
        if isinstance(o, (list, tuple)):
            if o and isinstance(o[0], (int, float)):
                return [round(o[0], 5), round(o[1], 5)]
            return [rnd(x) for x in o]
        return o
    feats = []
    for h in hoods:
        gm = mapping(h["geom"].simplify(tolerance, preserve_topology=True))
        feats.append({"type": "Feature", "id": h["id"],
                      "properties": {"name": h["name"], "borough": h["borough"]},
                      "geometry": {"type": gm["type"], "coordinates": rnd(gm["coordinates"])}})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
    log(f"Wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
