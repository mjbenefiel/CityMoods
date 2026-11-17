"""Mood rules for cities whose 311 data is a single request type (plus, for SF, a detail).

Each city gets a SimpleMoods instance: which types go in which mood, friendly names, and which
types are private (counted as "everything else", never named or featured).
"""
from __future__ import annotations

import re

from moods import _GRIM_RE, whimsy as _whimsy

PRIVATE = "Private request"   # what sensitive requests are relabeled as before anything is counted


class SimpleMoods:
    def __init__(self, moods: dict[str, list[str]], sensitive: set[str], names: dict[str, str],
                 keyword_moods: list[tuple[str, str]] = ()):
        self._lookup = {t: m for m, types in moods.items() for t in types}
        self.sensitive = set(sensitive) | {PRIVATE}
        self.names = names
        self.keyword_moods = [(re.compile(p, re.I), m) for p, m in keyword_moods]

    def mood_of(self, t: str) -> str:
        if t in self.sensitive:
            return "other"
        if t in self._lookup:
            return self._lookup[t]
        for rx, m in self.keyword_moods:
            if rx.search(t):
                return m
        return "other"

    def is_public(self, t: str) -> bool:
        return t not in self.sensitive

    def nice(self, t: str) -> str:
        if t in self.names:
            return self.names[t]
        s = re.sub(r"\s*(Request|Complaint|Issues?|Services?)$", "", t).strip() or t
        return sentence(s)

    def rare_ok(self, t: str, label: str) -> bool:
        return self.is_public(t) and not _GRIM_RE.search(f"{t} {label}".lower())

    def whimsy(self, t: str, label: str) -> int:
        return _whimsy(t, label)


_KEEP_CAPS = {"ADA", "LA", "SF", "MTA", "PG&E", "TV", "ATM", "BID", "ID", "NC", "DPW"}


def sentence(s: str) -> str:
    """'Trees or Pests in the Park' -> 'Trees or pests in the park' (keeps short acronyms like ADA)."""
    words = s.split()
    capped = sum(1 for w in words if w[:1].isupper())
    if words and (s.isupper() or capped >= 0.5 * len(words)):
        words = [w if w.upper() in _KEEP_CAPS and w.isupper() else w.lower() for w in words]
        s = " ".join(words)
    return s[:1].upper() + s[1:]


def pretty(code: str | None) -> str:
    """'lime_standing_scooter' -> 'Lime standing scooter'."""
    s = re.sub(r"\s+", " ", (code or "").replace("_", " ")).strip()
    s = re.sub(r"\s*request for service$", "", s, flags=re.I)
    return s[:1].upper() + s[1:]


# SF detail labels: friendlier names for common codes, and subtypes too generic to show on their own.
SF_LABELS = {
    "blocking_driveway_cite_only": "Blocked driveway", "blocking_driveway_cite_tow": "Blocked driveway (tow requested)",
    "other_illegal_parking": "Illegal parking", "parking_on_sidewalk": "Parking on the sidewalk",
    "lime_standing_scooter": "Lime scooter", "spin_standing_scooter": "Spin scooter",
    "scooter_without_license_plate": "Scooter with no license plate", "city_garbage_can_overflowing": "Overflowing city trash can",
    "other_loose_garbage_debris_yard_waste": "Loose garbage", "other_bagged_boxed_contained_garbage": "Bagged or boxed garbage",
    "refrigerator_appliance": "Fridge or appliance", "transit_shelter_platform": "Trash at a transit shelter",
    "other_excessive_noise": "Excessive noise", "abandoned_vehicle": "Abandoned car", "large_vehicle": "Oversized vehicle",
    "toters_left_out_24x7": "Trash bins left out", "other_including_abandoned_toter": "Abandoned trash bin",
    "pavement_defect": "Pavement defect", "sewage_back-up_discharge": "Sewage backup", "catch_basin": "Clogged storm drain",
    "parking_meter": "Broken parking meter", "film_commission": "Film shoot",
}
SF_GENERIC_SUBTYPES = {"garbage_and_debris", "not_offensive", "offensive", "blocked_sidewalk", "public_works",
                       "municipal_transportation_agency", "public_health", "park_services_area"}


def sf_detail(subtype: str | None, details: str | None) -> str | None:
    sub, det = (subtype or "").strip(), (details or "").strip()
    if det.lower() in ("", "other", "n/a", "na", "request_for_service"):
        det = ""
    if det in SF_LABELS:
        return SF_LABELS[det]
    if sub in SF_LABELS and not det:
        return SF_LABELS[sub]
    if det and sub in ("not_offensive", "offensive"):      # graffiti: say where it is
        return f"{'Offensive graffiti' if sub == 'offensive' else 'Graffiti'} on {pretty(det).lower()}"
    if det and sub and sub not in SF_GENERIC_SUBTYPES:
        head = SF_LABELS.get(sub) or pretty(sub)
        return f"{head}: {pretty(det).lower()}"
    if det:
        return pretty(det)
    if sub and sub not in SF_GENERIC_SUBTYPES and not sub.lower().startswith("other"):
        return SF_LABELS.get(sub) or pretty(sub)
    return None


# ======================================================================= Los Angeles

LA = SimpleMoods(
    moods={
        "trash": ["Illegal Dumping Item Pickup", "Graffiti Removal", "Street Sweeping",
                  "Public Street Receptacles", "Illegal Sign Removal, News Rack Issues", "Illegal Dumping Food Waste",
                  "Park Cleanliness, Trash and Ground Maintenance", "Service Not Complete"],
        "streets": ["Streetlight Repair Services", "Street Pavement Issues", "Obstructions", "Traffic Safety",
                    "Report a Sidewalk Problem", "General Street Inspection", "Traffic Sign Issues", "Barricade Removal",
                    "Curb Issues", "Bus Stop Furniture", "Traffic Signal Issues", "Sidewalk Repair Access Request Program",
                    "Streetlight Non-Repair Services", "Land/Mud Slide", "Guard/Warning Rail Maintenance",
                    "Streetlight ADA Repair Services", "Bus Stop Parking Sign & Markings", "Accessible Bus Stop Issues",
                    "Bicycle Facilities Issues", "Median Island Maintenance"],
        "trees": ["Tree Emergency", "Tree Obstruction", "Landscape Maintenance", "Street Tree Inspection",
                  "Street Tree Violations", "Trees or Pests in the Park"],
        "parking": ["Dockless Mobility Enforcement", "Parking Issues", "Parking Meter Maintenance"],
        "critters": ["Dead Animal Removal", "Animal Loose", "Animal Complaint/Violation", "Animal Confined",
                     "Bees or Beehive"],
        "noise": ["Nuisance Barking Dogs", "Illegal Auto Repair or Construction, and Leaf Blowers"],
        "water": ["Flooding", "Watershed Protection Division (WPD) Enforcement", "Report Water Wasting",
                  "Illegal Discharge of Water", "Sewer or Sidewalk Rebates"],
        "housing": ["Private Property Violation"],
    },
    sensitive={"Homeless Encampment", "Illegal Activities (Non-Emergency)"},
    names={
        "Item Pickups": "Bulky item pickup", "Illegal Dumping Item Pickup": "Illegal dumping",
        "Graffiti Removal": "Graffiti", "Service Not Complete": "Service not completed (follow-up)",
        "Streetlight Repair Services": "Streetlight repair", "Street Pavement Issues": "Potholes and pavement",
        "Dead Animal Removal": "Dead animal", "Dockless Mobility Enforcement": "Badly parked scooter or bike",
        "Report a Sidewalk Problem": "Sidewalk problem", "Private Property Violation": "Property violation",
        "Illegal Auto Repair or Construction, and Leaf Blowers": "Street auto repair, construction or leaf blowers",
        "Nuisance Barking Dogs": "Barking dogs", "Bees or Beehive": "Bees or a beehive",
        "Watershed Protection Division (WPD) Enforcement": "Stormwater violation",
        "Illegal Sign Removal, News Rack Issues": "Illegal signs or news racks",
        "Park Cleanliness, Trash and Ground Maintenance": "Dirty park", "Report Water Wasting": "Water wasting",
        "Land/Mud Slide": "Mudslide", "Searchlight & Generator Permits": "Searchlight or generator permit",
    },
)

LA_EXCLUDED = {"Information-Only"}   # questions, not complaints: left out before anything is counted


# ======================================================================= San Francisco

SF = SimpleMoods(
    moods={
        "trash": ["Street and Sidewalk Cleaning", "Graffiti Public", "Graffiti Private", "Litter Receptacle Maintenance",
                  "Illegal Postings"],
        "parking": ["Parking Enforcement", "Blocked Street and Sidewalk", "Abandoned Vehicle"],
        "streets": ["Street Defect", "Sidewalk and Curb", "Streetlights", "MTA Parking Traffic Signs Normal Priority",
                    "Damage Property", "Muni Service Feedback"],
        "noise": ["Noise"],
        "trees": ["Tree Maintenance"],
        "water": ["Sewer"],
        "housing": ["Residential Building"],
    },
    sensitive=set(),          # SF's sensitive cases are relabeled PRIVATE in cities.py (they depend on subtype/agency)
    names={"Street and Sidewalk Cleaning": "Street cleaning", "MTA Parking Traffic Signs Normal Priority": "Traffic sign",
           "Damage Property": "Damaged city property", "Graffiti Public": "Graffiti (public)",
           "Graffiti Private": "Graffiti (private property)", "Muni Service Feedback": "Muni service"},
    keyword_moods=[(r"graffiti", "trash"), (r"tree", "trees"), (r"sewer|water", "water")],
)

# Subtypes/details that are about people (homelessness, drug use, bodily waste) or individual employees.
SF_PRIVATE_NAMES = {"Encampment", "Muni Employee Feedback"}
SF_PRIVATE_WORDS = re.compile(r"homeless|encamp|needle|syringe|human_waste|urine|feces|drug|aggressive", re.I)


# ======================================================================= Boston

BOSTON = SimpleMoods(
    moods={
        "parking": ["Illegal Parking", "Abandoned Vehicles", "Illegal Yard Parking", "Parking Meter Repairs",
                    "Abandoned Bicycles", "Sticker Request"],
        "trash": ["Litter & Debris", "Missed Waste Pick-up", "Trash Placed Out Early", "Illegal Dumping or Disposal",
                  "Improper Trash Storage", "Overflowing Trash", "Illegal Graffiti", "Construction Debris",
                  "Unauthorized Signage", "Broken Public Waste Receptacle", "Request New Public Waste Receptacle",
                  "Code Enforcement Collection", "Overgrown Weeds"],
        "streets": ["Street Light Outage", "Sidewalk Repair", "Pothole", "Missing / Knocked Down Sign",
                    "Illegally Blocked Sidewalk", "Traffic Signal Request", "Utility Contractor Complaints",
                    "New / Modified Sign Request", "Install New Signal", "Street Light Other",
                    "Street Light Electrical Safety", "Request New Markings", "Traffic Signal Knockdown",
                    "Street Light Knockdown", "Lane Divider", "Road Marking Maintenance", "Crosswalk Maintenance",
                    "Bicycle Racks / Bicycle Parking", "Request New Crosswalk", "Damaged/Faded Sign",
                    "Fences/Guardrails/Bollards"],
        "critters": ["Dead Animal General", "Domestic Animal Issue", "Rat Activity", "Wild Animal Issue", "Lost Pet",
                     "Pest Infestation - Residential"],
        "trees": ["Park Groundskeeping", "Pruning Request", "Fallen Tree or Branches", "Tree or Stump Removal",
                  "Planting Request"],
        "housing": ["Unsatisfactory Living Conditions", "No Building Permit or Violation of Permit",
                    "Building Contractor Complaint", "Building Maintenance Violations", "Unsafe Structure",
                    "Adjoining Property Construction", "Unsatisfactory Utilities - (Electrical, Plumbing)"],
        "heat": ["Insufficient Heat"],
    },
    sensitive={"Needle Pickup"},
    names={"Missed Waste Pick-up": "Missed trash pickup", "Illegal Graffiti": "Graffiti",
           "Dead Animal General": "Dead animal", "Litter & Debris": "Litter and debris",
           "Missing / Knocked Down Sign": "Missing or knocked-down sign", "Rat Activity": "Rats",
           "Insufficient Heat": "Not enough heat", "Trash Placed Out Early": "Trash put out too early"},
    keyword_moods=[(r"street light|signal|sign|sidewalk|crosswalk", "streets"), (r"tree|prun|park ", "trees"),
                   (r"trash|litter|dumping|graffiti", "trash"), (r"animal|rat|pest", "critters")],
)
