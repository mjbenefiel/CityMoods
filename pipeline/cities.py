"""Per-city settings and data access. Everything city-specific lives here; build.py is shared.

Each city returns the same shape of records: (neighborhood_id, request_type, detail, agency).
Privacy rule for every city: request only the fields listed in FIELDS. Never addresses, street
names, ZIP codes, request numbers or free text.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter

from shapely import STRtree
from shapely.geometry import Point, shape

import moods as nyc_moods
import moods_chicago as chi_moods
from common import CACHE, DATA, day_bounds, get, log, write_map


class City:
    key = name = people = region_word = ""
    regions: list[str] = []
    api_311 = ""
    weather = ""
    min_full_day = 0
    center_lat = 0.0
    labels: list[list] = []        # [name, lon, lat] faint labels drawn on the map
    agency_examples = ""
    sources: list[list] = []       # [label, url] for the footer
    rare_max_28 = 3                # a "rare find" appeared at most this many times in the previous 28 days

    @property
    def data_dir(self):
        return DATA / self.key

    def meta(self) -> dict:
        return {"key": self.key, "name": self.name, "people": self.people, "region_word": self.region_word,
                "regions": self.regions, "center_lat": self.center_lat, "labels": self.labels, "sources": self.sources}

    # Mood helpers default to the city's moods module.
    mod = None

    def mood_of(self, t):
        return self.mod.mood_of(t)

    def is_public(self, t):
        return self.mod.is_public(t)

    def nice(self, t):
        return self.mod.nice(t)

    def rare_ok(self, t, label):
        return self.mod.rare_ok(t, label)

    def whimsy(self, t, label):
        return self.mod.whimsy(t, label)

    def newest_request(self) -> str:
        return get(self.api_311, params={"$select": "max(created_date) as m"}).json()[0]["m"][:16]

    def latest_complete_day(self, newest: str) -> dt.date:
        day = dt.date.fromisoformat(newest[:10]) - dt.timedelta(days=1)
        for _ in range(5):
            n = int(get(self.api_311, params={"$select": "count(*) as n", "$where": day_bounds(day)}).json()[0]["n"])
            if n >= self.min_full_day:
                return day
            day -= dt.timedelta(days=1)
        raise SystemExit(f"Couldn't find a complete day of {self.name} 311 data.")

    def _pages(self, select: str, where: str) -> list[dict]:
        rows, offset = [], 0
        while True:
            page = get(self.api_311, params={"$select": select, "$where": where,
                                             "$limit": 50000, "$offset": offset, "$order": ":id"}).json()
            rows += page
            if len(page) < 50000:
                return rows
            offset += 50000


# ======================================================================= New York City

class NYC(City):
    key, name, people, region_word = "nyc", "New York", "New Yorkers", "borough"
    regions = ["Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"]
    api_311 = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
    api_nta = "https://data.cityofnewyork.us/resource/9nt8-h7nd.geojson?$limit=500"
    weather = ("https://api.open-meteo.com/v1/forecast?latitude=40.7128&longitude=-74.006"
               "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
               "&temperature_unit=fahrenheit&precipitation_unit=inch&timezone=America%2FNew_York&past_days=10")
    min_full_day = 5000
    center_lat = 40.7
    labels = [["Manhattan", -73.972, 40.785], ["Bronx", -73.866, 40.852], ["Brooklyn", -73.947, 40.648],
              ["Queens", -73.805, 40.712], ["Staten Island", -74.152, 40.582]]
    agency_examples = "NYPD, Sanitation, Buildings, HPD"
    sources = [["NYC 311 Service Requests", "https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9/about_data"],
               ["2020 Neighborhood Tabulation Areas", "https://data.cityofnewyork.us/City-Government/2020-Neighborhood-Tabulation-Areas-NTAs-/9nt8-h7nd"]]
    mod = nyc_moods
    # complaint_type + the two fixed-menu detail levels + agency + location (used once, then dropped)
    FIELDS = "complaint_type,descriptor,descriptor_2,agency,latitude,longitude"

    def load_hoods(self):
        CACHE.mkdir(parents=True, exist_ok=True)
        raw = CACHE / "nta2020.geojson"
        if not raw.exists():
            log("Downloading NYC neighborhood boundaries...")
            raw.write_bytes(get(self.api_nta).content)
        hoods = [{"id": f["properties"]["nta2020"], "name": f["properties"]["ntaname"],
                  "borough": f["properties"]["boroname"], "geom": shape(f["geometry"])}
                 for f in json.loads(raw.read_text())["features"]]
        out = self.data_dir / "neighborhoods.geojson"
        if not out.exists():
            write_map(hoods, out)
        return hoods

    def fetch_records(self, day, hoods):
        rows = self._pages(self.FIELDS, day_bounds(day))
        log(f"Fetched {len(rows):,} requests")
        tree = STRtree([h["geom"] for h in hoods])
        out, unplaced = [], 0
        for r in rows:
            t = r.get("complaint_type") or "Unknown"
            hood = None
            try:
                pt = Point(float(r["longitude"]), float(r["latitude"]))
                for idx in tree.query(pt, predicate="intersects"):
                    hood = hoods[idx]["id"]
                    break
            except (KeyError, TypeError, ValueError):
                pass
            unplaced += hood is None
            out.append((hood, t, nyc_moods.detail_of(t, r.get("descriptor"), r.get("descriptor_2")),
                        nyc_moods.agency_of(r.get("agency"))))
        rows.clear()  # drop the raw rows (and their coordinates) as soon as we're done
        return out, unplaced

    def _grouped(self, where):
        return get(self.api_311, params={"$select": "complaint_type,descriptor,descriptor_2,count(*) as n",
                                         "$where": where, "$group": "complaint_type,descriptor,descriptor_2",
                                         "$limit": 50000}).json()

    def detail_counts(self, day):
        types, details = Counter(), Counter()
        for x in self._grouped(day_bounds(day)):
            t = x.get("complaint_type")
            if t:
                n = int(x["n"])
                types[t] += n
                details[(t, nyc_moods.detail_of(t, x.get("descriptor"), x.get("descriptor_2")) or self.nice(t))] += n
        return types, details

    def month_detail_counts(self, day):
        start = day - dt.timedelta(days=28)
        out = Counter()
        for x in self._grouped(f"created_date >= '{start}T00:00:00' AND created_date < '{day}T00:00:00'"):
            t = x.get("complaint_type")
            if t:
                out[(t, nyc_moods.detail_of(t, x.get("descriptor"), x.get("descriptor_2")) or self.nice(t))] += int(x["n"])
        return out

    def extras(self, day):
        """How NYPD noise calls ended, from the police's standard closing notes (counted, never quoted)."""
        try:
            rows = get(self.api_311, params={
                "$select": "resolution_description,count(*) as n",
                "$where": day_bounds(day) + " AND starts_with(complaint_type,'Noise') AND agency='NYPD'",
                "$group": "resolution_description", "$limit": 200}).json()
        except Exception as e:
            log(f"NYPD outcome stats unavailable: {e}")
            return {}
        c = Counter()
        for r in rows:
            text, n = (r.get("resolution_description") or "").lower(), int(r["n"])
            c["total"] += n
            if "observed no evidence" in text or "observed no criminal violation upon their arrival" in text:
                c["nothing"] += n
            elif "condition was corrected" in text:
                c["fixed"] += n
            elif "unable to gain entry" in text:
                c["no_entry"] += n
            elif "not necessary" in text:
                c["not_needed"] += n
            elif "issued a summons" in text:
                c["summons"] += n
        if c["total"] < 50:
            return {}
        stats = {"nypd_noise": dict(c)}
        stats["lines"] = [
            {"emoji": "🚓", "text": f"NYPD answered {c['total']:,} noise complaints. {c['nothing']:,} times they found nothing going on when they got there."},
            {"emoji": "🚪", "text": f"{c['no_entry']:,} times officers couldn't get inside. {c['summons']:,} noise calls ended with a ticket."},
        ]
        return stats


# ======================================================================= Chicago

# Chicago's 77 community areas, grouped into five familiar parts of town.
_CHI_SIDES = {
    "North Side": [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 76, 77],
    "West Side": [23, 24, 25, 26, 27, 28, 29, 30, 31],
    "Downtown": [8, 32, 33],
    "South Side": [34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 60, 69],
    "Southwest Side": [56, 57, 58, 59, 61, 62, 63, 64, 65, 66, 67, 68, 70, 71, 72, 73, 74, 75],
}
_CHI_SIDE_OF = {n: side for side, nums in _CHI_SIDES.items() for n in nums}
_CHI_NAME_FIX = {"OHARE": "O'Hare", "MCKINLEY PARK": "McKinley Park", "LAKE VIEW": "Lake View",
                 "WEST TOWN": "West Town", "LOOP": "The Loop"}


def _title(name: str) -> str:
    return _CHI_NAME_FIX.get(name, " ".join(w.capitalize() for w in name.lower().split()))


class Chicago(City):
    key, name, people, region_word = "chicago", "Chicago", "Chicagoans", "side"
    regions = list(_CHI_SIDES)
    api_311 = "https://data.cityofchicago.org/resource/v6vf-nfxy.json"
    api_areas = "https://data.cityofchicago.org/resource/igwz-8jzy.geojson?$limit=100"
    weather = ("https://api.open-meteo.com/v1/forecast?latitude=41.8781&longitude=-87.6298"
               "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
               "&temperature_unit=fahrenheit&precipitation_unit=inch&timezone=America%2FChicago&past_days=10")
    min_full_day = 2000
    rare_max_28 = 40               # Chicago has ~100 request types (vs thousands of NYC combos): "rare" = its least common ones
    center_lat = 41.84
    labels = [["North Side", -87.70, 41.955], ["West Side", -87.735, 41.875], ["Downtown", -87.625, 41.885],
              ["South Side", -87.60, 41.755], ["Southwest Side", -87.73, 41.78], ["O'Hare", -87.885, 41.978]]
    agency_examples = "Streets & Sanitation, CDOT, Water Management, Buildings"
    sources = [["Chicago 311 Service Requests", "https://data.cityofchicago.org/Service-Requests/311-Service-Requests/v6vf-nfxy"],
               ["Community Area Boundaries", "https://data.cityofchicago.org/Facilities-Geographic-Boundaries/Boundaries-Community-Areas/igwz-8jzy"]]
    mod = chi_moods
    # Request type + community area + department. No addresses, coordinates or request numbers at all:
    # Chicago already tells us the community area, so locations are never downloaded.
    FIELDS = "sr_type,community_area,owner_department"
    # Questions, airport-logged plane noise and duplicate reports are left out of everything except the
    # citywide stats.
    WHERE = ("duplicate = false AND sr_type != '311 INFORMATION ONLY CALL' "
             "AND sr_type != 'Aircraft Noise Complaint'")

    def load_hoods(self):
        CACHE.mkdir(parents=True, exist_ok=True)
        raw = CACHE / "chicago_community_areas.geojson"
        if not raw.exists():
            log("Downloading Chicago community area boundaries...")
            raw.write_bytes(get(self.api_areas).content)
        hoods = []
        for f in json.loads(raw.read_text())["features"]:
            num = int(f["properties"]["area_numbe"])
            hoods.append({"id": str(num), "name": _title(f["properties"]["community"]),
                          "borough": _CHI_SIDE_OF[num], "geom": shape(f["geometry"])})
        out = self.data_dir / "neighborhoods.geojson"
        if not out.exists():
            write_map(hoods, out, tolerance=0.0003)
        return hoods

    def fetch_records(self, day, hoods):
        rows = self._pages(self.FIELDS, f"{day_bounds(day)} AND {self.WHERE}")
        log(f"Fetched {len(rows):,} requests (questions, airport noise and duplicates left out)")
        valid = {h["id"] for h in hoods}
        out, unplaced = [], 0
        for r in rows:
            t = r.get("sr_type") or "Unknown"
            hood = str(int(float(r["community_area"]))) if r.get("community_area") else None
            if hood not in valid:
                hood = None
            unplaced += hood is None
            out.append((hood, t, None, chi_moods.agency_of(r.get("owner_department"))))
        return out, unplaced

    def _type_counts(self, where):
        r = get(self.api_311, params={"$select": "sr_type,count(*) as n", "$where": f"{where} AND {self.WHERE}",
                                      "$group": "sr_type", "$limit": 1000}).json()
        return Counter({x["sr_type"]: int(x["n"]) for x in r if x.get("sr_type")})

    def detail_counts(self, day):
        types = self._type_counts(day_bounds(day))
        return types, Counter({(t, self.nice(t)): n for t, n in types.items()})

    def month_detail_counts(self, day):
        start = day - dt.timedelta(days=28)
        types = self._type_counts(f"created_date >= '{start}T00:00:00' AND created_date < '{day}T00:00:00'")
        return Counter({(t, self.nice(t)): n for t, n in types.items()})

    def extras(self, day):
        """Citywide-only stats: O'Hare's noise complaints and a few Chicago classics."""
        try:
            r = get(self.api_311, params={"$select": "sr_type,count(*) as n", "$where": day_bounds(day),
                                          "$group": "sr_type", "$limit": 1000}).json()
        except Exception as e:
            log(f"Chicago extra stats unavailable: {e}")
            return {}
        c = Counter({x["sr_type"]: int(x["n"]) for x in r if x.get("sr_type")})
        lines = []
        if c["Aircraft Noise Complaint"]:
            lines.append({"emoji": "✈️", "text": f"O'Hare received {c['Aircraft Noise Complaint']:,} noise complaints (they're all filed at the airport, so they stay off the map)."})
        if c["311 INFORMATION ONLY CALL"]:
            lines.append({"emoji": "☎️", "text": f"{c['311 INFORMATION ONLY CALL']:,} people called 311 just to ask a question."})
        trim = c["Tree Trim Request (NO LONGER BEING ACCEPTED)"]
        if trim:
            lines.append({"emoji": "🌳", "text": f"{trim:,} people requested a tree trim, a request type the city says it no longer accepts."})
        lake = c["Submerged Divvy or Lime Device in the Lake/River"]
        if lake:
            lines.append({"emoji": "🛴", "text": f"{lake} bike or scooter{'s' if lake != 1 else ''} reported sleeping with the fishes in the lake or river."})
        return {"counts": {"aircraft_noise": c["Aircraft Noise Complaint"], "info_calls": c["311 INFORMATION ONLY CALL"],
                           "tree_trim_no_longer_accepted": trim, "submerged_devices": lake}, "lines": lines}


CITIES = {"nyc": NYC(), "chicago": Chicago()}
