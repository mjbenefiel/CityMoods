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

import re

import moods as nyc_moods
import moods_chicago as chi_moods
import moods_simple as simple
from moods_simple import PRIVATE, pretty
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
    date_field = "created_date"

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
        return get(self.api_311, params={"$select": f"max({self.date_field}) as m"}).json()[0]["m"][:16]

    def day_count(self, day) -> int:
        return int(get(self.api_311, params={"$select": "count(*) as n",
                                             "$where": day_bounds(day, self.date_field)}).json()[0]["n"])

    def latest_complete_day(self, newest: str) -> dt.date:
        # If the data already runs to nearly midnight (SF posts through ~11:59 PM), that date is complete;
        # otherwise the newest date is still filling in, so start from the day before.
        day = dt.date.fromisoformat(newest[:10])
        if newest[11:16] < "23:30":
            day -= dt.timedelta(days=1)
        for _ in range(5):
            n = self.day_count(day)
            if n >= self.min_full_day:
                return day
            day -= dt.timedelta(days=1)
        raise SystemExit(f"Couldn't find a complete day of {self.name} 311 data.")

    def _pages(self, select: str, where: str, api: str | None = None) -> list[dict]:
        rows, offset = [], 0
        while True:
            page = get(api or self.api_311, params={"$select": select, "$where": where,
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


# ======================================================================= shared helpers

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _agency(name: str | None, prefixes: list[tuple[str, str]]) -> str:
    n = (name or "").strip()
    for prefix, label in prefixes:
        if n.lower().startswith(prefix.lower()):
            return label
    return "Other agencies"


# ======================================================================= Los Angeles

# LA's 12 Neighborhood Council service regions, grouped into seven familiar areas.
_LA_AREAS = {"East Valley": [1, 4], "West Valley": [2, 3], "Central LA": [5, 6], "Eastside": [7, 8],
             "South LA": [9, 10], "Westside": [11], "Harbor": [12]}
_LA_AREA_OF = {n: area for area, nums in _LA_AREAS.items() for n in nums}
_LA_RENAMED = {"46": "Arts District Little Tokyo"}   # boundary file still uses the council's old name
_LA_AGENCIES = [("LASAN", "Sanitation (LASAN)"), ("recycLA", "recycLA (trash haulers)"), ("OCB", "Graffiti Abatement (OCB)"),
                ("BSS", "Street Services"), ("Street Services", "Street Services"), ("BSL", "Street Lighting"),
                ("LADOT", "Transportation (LADOT)"), ("LAAS", "Animal Services"), ("LADBS", "Building & Safety"),
                ("RAP", "Recreation & Parks"), ("ITA", "311 / ITA"), ("DPW", "Public Works"), ("BOE", "Engineering"),
                ("LADWP", "Water & Power"), ("Department of Water and Power", "Water & Power")]


class LosAngeles(City):
    key, name, people, region_word = "la", "Los Angeles", "Angelenos", "area"
    regions = list(_LA_AREAS)
    date_field = "createddate"
    datasets = {2026: "2cy6-i7zn"}        # MyLA311 Cases <year>; other years are looked up by name
    nc_boundaries = ("https://services1.arcgis.com/PTh9WC0Sf2WS7AAq/arcgis/rest/services/Neighborhood_Councils/"
                     "FeatureServer/0/query?where=1%3D1&outFields=NAME,NC_ID,SERVICE_RE&outSR=4326&f=geojson")
    weather = ("https://api.open-meteo.com/v1/forecast?latitude=34.0522&longitude=-118.2437"
               "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
               "&temperature_unit=fahrenheit&precipitation_unit=inch&timezone=America%2FLos_Angeles&past_days=10")
    min_full_day = 4000
    rare_max_28 = 40
    center_lat = 34.05
    labels = [["San Fernando Valley", -118.47, 34.215], ["Westside", -118.44, 34.03], ["Central LA", -118.32, 34.075],
              ["Eastside", -118.20, 34.09], ["South LA", -118.29, 33.975], ["Harbor", -118.275, 33.775]]
    agency_examples = "Sanitation, Street Services, LADOT, Building & Safety"
    sources = [["MyLA311 Cases", "https://data.lacity.org/browse?q=MyLA311%20Cases"],
               ["Neighborhood Council Boundaries", "https://geohub.lacity.org/datasets/neighborhood-council-boundaries"]]
    mod = simple.LA
    # Request type + department + the city's own Neighborhood Council number. No addresses or coordinates.
    FIELDS = "type,department_name__c,locator_sr_neigborhood_council"
    # Questions and scheduled bulky-item pickups (an appointment, not a gripe) are left off the map;
    # both appear only as citywide "Today in 311" lines.
    WHERE = "type != 'Information-Only' AND type != 'Item Pickups'"

    def api(self, year: int) -> str:
        if year not in self.datasets:
            r = get("https://api.us.socrata.com/api/catalog/v1",
                    params={"domains": "data.lacity.org", "q": f"MyLA311 Cases {year}", "limit": 5}).json()
            hit = next((x["resource"]["id"] for x in r.get("results", [])
                        if x["resource"]["name"].strip().lower() == f"myla311 cases {year}"), None)
            if not hit:
                raise SystemExit(f"Couldn't find the MyLA311 Cases {year} dataset.")
            self.datasets[year] = hit
        return f"https://data.lacity.org/resource/{self.datasets[year]}.json"

    @property
    def api_311(self):
        return self.api(dt.date.today().year)

    def newest_request(self) -> str:
        try:
            m = get(self.api_311, params={"$select": "max(createddate) as m"}).json()[0].get("m")
        except SystemExit:
            m = None
        if not m:   # early January, before the new year's dataset exists
            m = get(self.api(dt.date.today().year - 1), params={"$select": "max(createddate) as m"}).json()[0]["m"]
        return m[:16]

    def day_count(self, day) -> int:
        return int(get(self.api(day.year), params={"$select": "count(*) as n",
                                                   "$where": day_bounds(day, self.date_field)}).json()[0]["n"])

    def _type(self, t):
        t = t or "Unknown"
        return PRIVATE if t in self.mod.sensitive else t

    def load_hoods(self):
        CACHE.mkdir(parents=True, exist_ok=True)
        raw = CACHE / "la_neighborhood_councils.geojson"
        if not raw.exists():
            log("Downloading LA Neighborhood Council boundaries...")
            raw.write_bytes(get(self.nc_boundaries).content)
        hoods = []
        for f in json.loads(raw.read_text())["features"]:
            pr = f["properties"]
            nid = str(int(pr["NC_ID"]))
            name = _LA_RENAMED.get(nid) or re.sub(r"\s+(NC|NDC|CC|COUNCIL)$", "", pr["NAME"].strip(), flags=re.I)
            name = re.sub(r"^NC\s+", "", name, flags=re.I)
            region = int(re.search(r"REGION\s+(\d+)", pr.get("SERVICE_RE") or "REGION 5").group(1))
            hoods.append({"id": nid, "name": " ".join(w if w.isupper() and len(w) <= 3 and w in {"LA", "NOHO"} else w.capitalize()
                                                    for w in name.lower().split()).replace("Noho", "NoHo").replace("La-32", "LA-32"),
                          "borough": _LA_AREA_OF.get(region, "Central LA"), "geom": shape(f["geometry"])})
        out = self.data_dir / "neighborhoods.geojson"
        if not out.exists():
            write_map(hoods, out, tolerance=0.0006)
        return hoods

    def fetch_records(self, day, hoods):
        rows = self._pages(self.FIELDS, f"{day_bounds(day, self.date_field)} AND {self.WHERE}", api=self.api(day.year))
        log(f"Fetched {len(rows):,} requests (questions and scheduled bulky-item pickups left out)")
        valid = {h["id"] for h in hoods}
        out, unplaced = [], 0
        for r in rows:
            nc = r.get("locator_sr_neigborhood_council")
            hood = str(int(float(nc))) if nc else None
            if hood not in valid:
                hood = None
            unplaced += hood is None
            out.append((hood, self._type(r.get("type")), None, _agency(r.get("department_name__c"), _LA_AGENCIES)))
        return out, unplaced

    def _type_counts(self, start, end):
        out = Counter()
        for year in range(start.year, (end - dt.timedelta(days=1)).year + 1):
            r = get(self.api(year), params={"$select": "type,count(*) as n",
                                            "$where": f"createddate >= '{start}T00:00:00' AND createddate < '{end}T00:00:00' AND {self.WHERE}",
                                            "$group": "type", "$limit": 1000}).json()
            for x in r:
                out[self._type(x.get("type"))] += int(x["n"])
        return out

    def detail_counts(self, day):
        types = self._type_counts(day, day + dt.timedelta(days=1))
        return types, Counter({(t, self.nice(t)): n for t, n in types.items()})

    def month_detail_counts(self, day):
        types = self._type_counts(day - dt.timedelta(days=28), day)
        return Counter({(t, self.nice(t)): n for t, n in types.items()})

    def extras(self, day):
        try:
            r = get(self.api(day.year), params={"$select": "type,count(*) as n", "$where": day_bounds(day, self.date_field),
                                                "$group": "type", "$limit": 1000}).json()
        except Exception as e:
            log(f"LA extra stats unavailable: {e}")
            return {}
        c = Counter({x.get("type"): int(x["n"]) for x in r})
        lines = []
        if c["Information-Only"]:
            lines.append({"emoji": "☎️", "text": f"{c['Information-Only']:,} people contacted 311 just to ask a question."})
        if c["Item Pickups"]:
            lines.append({"emoji": "🛋️", "text": f"{c['Item Pickups']:,} Angelenos booked a free bulky-item pickup (they stay off the map: it's an appointment, not a gripe)."})
        if c["Dockless Mobility Enforcement"]:
            lines.append({"emoji": "🛴", "text": f"{c['Dockless Mobility Enforcement']:,} badly parked scooters or bikes reported."})
        return {"lines": lines}


# ======================================================================= San Francisco

_SF_AGENCIES = [("PW", "Public Works"), ("MTA", "SFMTA"), ("Recology", "Recology"), ("PUC", "Public Utilities (PUC)"),
                ("DBI", "Building Inspection"), ("RPD", "Rec & Park"), ("DPH", "Public Health"), ("Police", "Police"),
                ("Entertainment Commission", "Entertainment Commission"), ("PGE", "PG&E"), ("CBD", "Community Benefit Districts"),
                ("311", "311"), ("Noise Report", "Noise reports"), ("US Postal", "US Postal Service"), ("Clear Channel", "Clear Channel")]


class SanFrancisco(City):
    key, name, people, region_word = "sf", "San Francisco", "San Franciscans", "neighborhood"
    regions = []
    api_311 = "https://data.sf.gov/resource/vw6y-z8j6.json"
    api_hoods = "https://data.sf.gov/resource/j2bu-swwd.geojson?$limit=100"
    date_field = "requested_datetime"
    weather = ("https://api.open-meteo.com/v1/forecast?latitude=37.7749&longitude=-122.4194"
               "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
               "&temperature_unit=fahrenheit&precipitation_unit=inch&timezone=America%2FLos_Angeles&past_days=10")
    min_full_day = 1500
    center_lat = 37.76
    labels = [["Downtown", -122.405, 37.791], ["Mission", -122.415, 37.758], ["Sunset", -122.492, 37.751],
              ["Richmond", -122.482, 37.779], ["Bayview", -122.39, 37.73]]
    agency_examples = "Public Works, SFMTA, Recology, Rec & Park"
    sources = [["SF 311 Cases", "https://data.sfgov.org/City-Infrastructure/311-Cases/vw6y-z8j6"],
               ["Analysis Neighborhoods", "https://data.sfgov.org/Geographic-Locations-and-Boundaries/Analysis-Neighborhoods/j2bu-swwd"]]
    mod = simple.SF
    # Category, its two fixed-menu detail levels, agency and the city's own neighborhood name.
    # Never: addresses, coordinates, photos or the free-text status notes.
    FIELDS = "service_name,service_subtype,service_details,agency_responsible,analysis_neighborhood"

    def classify(self, r) -> tuple[str, str | None]:
        name = r.get("service_name") or "Unknown"
        sub, det, agency = r.get("service_subtype") or "", r.get("service_details") or "", r.get("agency_responsible") or ""
        if (name in simple.SF_PRIVATE_NAMES or simple.SF_PRIVATE_WORDS.search(sub) or simple.SF_PRIVATE_WORDS.search(det)
                or "homeless" in agency.lower() or "healthy streets" in agency.lower()):
            return PRIVATE, None
        return name, simple.sf_detail(sub, det)

    def load_hoods(self):
        CACHE.mkdir(parents=True, exist_ok=True)
        raw = CACHE / "sf_analysis_neighborhoods.geojson"
        if not raw.exists():
            log("Downloading SF neighborhood boundaries...")
            raw.write_bytes(get(self.api_hoods).content)
        hoods = [{"id": _slug(f["properties"]["nhood"]), "name": f["properties"]["nhood"], "borough": "San Francisco",
                  "geom": shape(f["geometry"])} for f in json.loads(raw.read_text())["features"]]
        out = self.data_dir / "neighborhoods.geojson"
        if not out.exists():
            write_map(hoods, out, tolerance=0.0001)
        return hoods

    def fetch_records(self, day, hoods):
        rows = self._pages(self.FIELDS, day_bounds(day, self.date_field))
        log(f"Fetched {len(rows):,} requests")
        valid = {h["id"] for h in hoods}
        out, unplaced = [], 0
        for r in rows:
            hood = _slug(r["analysis_neighborhood"]) if r.get("analysis_neighborhood") else None
            if hood not in valid:
                hood = None
            unplaced += hood is None
            t, d = self.classify(r)
            out.append((hood, t, d, _agency(r.get("agency_responsible"), _SF_AGENCIES)))
        return out, unplaced

    def _grouped(self, where):
        rows = get(self.api_311, params={"$select": "service_name,service_subtype,service_details,agency_responsible,count(*) as n",
                                         "$where": where, "$group": "service_name,service_subtype,service_details,agency_responsible",
                                         "$limit": 50000}).json()
        types, details = Counter(), Counter()
        for x in rows:
            t, d = self.classify(x)
            n = int(x["n"])
            types[t] += n
            details[(t, d or self.nice(t))] += n
        return types, details

    def detail_counts(self, day):
        return self._grouped(day_bounds(day, self.date_field))

    def month_detail_counts(self, day):
        start = day - dt.timedelta(days=28)
        return self._grouped(f"requested_datetime >= '{start}T00:00:00' AND requested_datetime < '{day}T00:00:00'")[1]

    def extras(self, day):
        try:
            _, details = self.detail_counts(day)
        except Exception as e:
            log(f"SF extra stats unavailable: {e}")
            return {}
        scooters = sum(n for (t, d), n in details.items() if "scooter" in d.lower())
        mattresses = sum(n for (t, d), n in details.items() if d.lower() == "mattress")
        lines = []
        if scooters:
            lines.append({"emoji": "🛴", "text": f"{scooters:,} scooters reported blocking a sidewalk or street."})
        if mattresses:
            lines.append({"emoji": "🛏️", "text": f"{mattresses:,} mattresses reported left on the sidewalk."})
        return {"lines": lines}


# ======================================================================= Boston

_BOS_AGENCIES = [("Public Works", "Public Works"), ("Boston Transportation", "Transportation (BTD)"),
                 ("Inspectional Services", "Inspectional Services"), ("Animal Care", "Animal Care & Control"),
                 ("Parks", "Parks & Recreation"), ("City of Boston Property", "Property Management"),
                 ("Boston 311", "Boston 311")]


class Boston(City):
    key, name, people, region_word = "boston", "Boston", "Bostonians", "neighborhood"
    regions = []
    resource = "254adca6-64ab-4c5c-9fc0-a6da622be185"   # "311 Service Requests - NEW SYSTEM" (since July 2026)
    sql_api = "https://data.boston.gov/api/3/action/datastore_search_sql"
    hoods_resource = "e5849875-a6f6-4c9c-9d8a-5048b0fbd03e"  # BPDA neighborhood boundaries
    api_311 = "https://data.boston.gov/dataset/311-service-requests"   # for reference; queries go through sql()
    weather = ("https://api.open-meteo.com/v1/forecast?latitude=42.3601&longitude=-71.0589"
               "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
               "&temperature_unit=fahrenheit&precipitation_unit=inch&timezone=America%2FNew_York&past_days=10")
    min_full_day = 300
    rare_max_28 = 12
    center_lat = 42.32
    labels = [["Downtown", -71.06, 42.357], ["Dorchester", -71.062, 42.298], ["East Boston", -71.028, 42.377],
              ["Roxbury", -71.088, 42.318], ["Jamaica Plain", -71.113, 42.308], ["Allston-Brighton", -71.15, 42.352]]
    agency_examples = "Public Works, Transportation, Inspectional Services, Parks"
    sources = [["Boston 311 Service Requests", "https://data.boston.gov/dataset/311-service-requests"],
               ["BPDA Neighborhood Boundaries", "https://data.boston.gov/dataset/bpda-neighborhood-boundaries"]]
    mod = simple.BOSTON

    def sql(self, q: str) -> list[dict]:
        d = get(self.sql_api, params={"sql": q}).json()
        if not d.get("success"):
            raise SystemExit(f"Boston data query failed: {str(d.get('error'))[:200]}")
        return d["result"]["records"]

    def _where(self, start, end):
        return f"open_date >= '{start}T00:00:00' AND open_date < '{end}T00:00:00'"

    def newest_request(self) -> str:
        return str(self.sql(f'SELECT max(open_date) AS m FROM "{self.resource}"')[0]["m"])[:16]

    def day_count(self, day) -> int:
        return int(self.sql(f'SELECT count(*) AS n FROM "{self.resource}" WHERE {self._where(day, day + dt.timedelta(days=1))}')[0]["n"])

    def _type(self, t):
        t = (t or "Unknown").strip()
        return PRIVATE if t in self.mod.sensitive else t

    def load_hoods(self):
        CACHE.mkdir(parents=True, exist_ok=True)
        raw = CACHE / "boston_neighborhoods.geojson"
        if not raw.exists():
            log("Downloading Boston neighborhood boundaries...")
            url = get("https://data.boston.gov/api/3/action/resource_show", params={"id": self.hoods_resource}).json()["result"]["url"]
            raw.write_bytes(get(url).content)
        hoods = [{"id": _slug(f["properties"]["name"]), "name": f["properties"]["name"], "borough": "Boston",
                  "geom": shape(f["geometry"])} for f in json.loads(raw.read_text())["features"]]
        out = self.data_dir / "neighborhoods.geojson"
        if not out.exists():
            write_map(hoods, out, tolerance=0.0001)
        return hoods

    def fetch_records(self, day, hoods):
        # Type, department and the city's own neighborhood name only. Never addresses, coordinates,
        # photos or closure comments.
        rows = self.sql(f'SELECT service_name, assigned_department, neighborhood FROM "{self.resource}" '
                        f'WHERE {self._where(day, day + dt.timedelta(days=1))}')
        log(f"Fetched {len(rows):,} requests")
        valid = {h["id"] for h in hoods}
        out, unplaced = [], 0
        for r in rows:
            hood = _slug(r["neighborhood"]) if r.get("neighborhood") else None
            if hood not in valid:
                hood = None
            unplaced += hood is None
            out.append((hood, self._type(r.get("service_name")), None, _agency(r.get("assigned_department"), _BOS_AGENCIES)))
        return out, unplaced

    def _type_counts(self, start, end):
        out = Counter()
        for x in self.sql(f'SELECT service_name, count(*) AS n FROM "{self.resource}" WHERE {self._where(start, end)} GROUP BY service_name'):
            out[self._type(x.get("service_name"))] += int(x["n"])
        return out

    def detail_counts(self, day):
        types = self._type_counts(day, day + dt.timedelta(days=1))
        return types, Counter({(t, self.nice(t)): n for t, n in types.items()})

    def month_detail_counts(self, day):
        types = self._type_counts(day - dt.timedelta(days=28), day)
        return Counter({(t, self.nice(t)): n for t, n in types.items()})

    def extras(self, day):
        try:
            c = self._type_counts(day, day + dt.timedelta(days=1))
        except Exception as e:
            log(f"Boston extra stats unavailable: {e}")
            return {}
        lines = []
        if c["Trash Placed Out Early"]:
            lines.append({"emoji": "🗑️", "text": f"{c['Trash Placed Out Early']:,} reports of trash put out too early."})
        if c["Illegal Parking"]:
            lines.append({"emoji": "🚗", "text": f"{c['Illegal Parking']:,} illegal parking reports."})
        return {"lines": lines}


CITIES = {"nyc": NYC(), "chicago": Chicago(), "la": LosAngeles(), "sf": SanFrancisco(), "boston": Boston()}
