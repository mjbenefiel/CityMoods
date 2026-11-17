"""Groups NYC 311 complaint types into a handful of friendly "moods".

Anything not listed falls into "other". Complaint types in SENSITIVE are also counted
as "other" and are never named on the site or in the daily headline: they are about
people (often vulnerable people), not about the city, and this map shouldn't joke about them.
"""

MOODS = {
    "heat":     {"label": "No heat",        "emoji": "🥶", "color": "#4C8DF6"},
    "noise":    {"label": "Noise",          "emoji": "🔊", "color": "#E2557B"},
    "parking":  {"label": "Parking wars",   "emoji": "🚗", "color": "#F2A33A"},
    "housing":  {"label": "Home repairs",   "emoji": "🔧", "color": "#8E6CDB"},
    "streets":  {"label": "Street fixes",   "emoji": "🚧", "color": "#7A8699"},
    "trash":    {"label": "Trash talk",     "emoji": "🗑️", "color": "#4FB286"},
    "critters": {"label": "Critters",       "emoji": "🐀", "color": "#A0522D"},
    "water":    {"label": "Water & sewers", "emoji": "💧", "color": "#2BB3C0"},
    "trees":    {"label": "Trees",          "emoji": "🌳", "color": "#5E9E3A"},
    "other":    {"label": "Everything else", "emoji": "📋", "color": "#B9BEC7"},
}

_EXACT = {
    "heat": ["HEAT/HOT WATER", "Non-Residential Heat", "Boilers"],
    "parking": ["Illegal Parking", "Blocked Driveway", "Abandoned Vehicle", "Derelict Vehicles",
                "Broken Parking Meter", "Municipal Parking Facility"],
    "housing": ["UNSANITARY CONDITION", "PLUMBING", "Plumbing", "PAINT/PLASTER", "DOOR/WINDOW", "GENERAL",
                "WATER LEAK", "ELECTRIC", "Electrical", "FLOORING/STAIRS", "APPLIANCE", "Elevator", "ELEVATOR",
                "SAFETY", "OUTSIDE BUILDING", "Mold", "Lead", "Indoor Air Quality", "Asbestos", "Indoor Sewage",
                "General Construction/Plumbing", "Building/Use", "Construction Lead Dust", "Scaffold Safety",
                "Cranes and Derricks", "Building Drinking Water Tank", "BEST/Site Safety"],
    "streets": ["Street Condition", "Street Light Condition", "Traffic Signal Condition", "Sidewalk Condition",
                "Curb Condition", "Root/Sewer/Sidewalk Condition", "Obstruction", "Traffic", "Bridge Condition",
                "Bus Stop Shelter Complaint", "Bus Stop Shelter Placement", "Bench", "Bike Rack", "Tunnel Condition",
                "Snow or Ice", "Wayfinding", "LinkNYC"],
    "trash": ["Dirty Condition", "Illegal Dumping", "Missed Collection", "Residential Disposal Complaint",
              "Commercial Disposal Complaint", "Institution Disposal Complaint", "Litter Basket Request",
              "Litter Basket Complaint", "Recycling Basket Complaint", "Graffiti", "Illegal Posting",
              "Posting Advertisement", "Sanitation Worker or Vehicle Complaint", "Dumpster Complaint",
              "Street Sweeping Complaint", "Lot Condition", "Wood Pile Remaining", "Abandoned Bike"],
    "critters": ["Rodent", "Dead Animal", "Unsanitary Pigeon Condition", "Animal in a Park", "Unleashed Dog",
                 "Mosquitoes", "Harboring Bees/Wasps", "Unsanitary Animal Pvt Property", "Standing Water",
                 "Illegal Animal Kept as Pet"],
    "water": ["Water Maintenance", "Sewer Maintenance", "Water Quality", "Drinking Water", "Water Conservation",
              "Green Infrastructure", "Industrial Waste", "Dry Weather Discharge", "Waste Water Treatment Plant"],
    "trees": ["Damaged Tree", "Overgrown Tree/Branches", "Dead/Dying Tree", "Illegal Tree Damage",
              "New Tree Request", "Uprooted Stump"],
}

SENSITIVE = {
    "Homeless Person Assistance", "Encampment", "Panhandling", "Drug Activity", "Drinking",
    "Urinating in Public", "Disorderly Youth", "Non-Emergency Police Matter", "Animal-Abuse",
    "Investigations and Discipline (IAD)", "Lost Property", "Found Property", "Day Care",
    "Emergency Response Team (ERT)", "Dept of Investigations", "Special Operations", "Real Time Enforcement",
}

_LOOKUP = {t: m for m, types in _EXACT.items() for t in types}


def mood_of(complaint_type: str) -> str:
    if complaint_type in SENSITIVE:
        return "other"
    if complaint_type in _LOOKUP:
        return _LOOKUP[complaint_type]
    if complaint_type.startswith("Noise") or complaint_type == "Illegal Fireworks":
        return "noise"
    return "other"


def is_public(complaint_type: str) -> bool:
    """May this complaint type be named on the site?"""
    return complaint_type not in SENSITIVE


# Friendlier names for the most common raw types (raw 311 names are shouty or terse).
NICE_NAMES = {
    "HEAT/HOT WATER": "No heat or hot water",
    "UNSANITARY CONDITION": "Unsanitary apartment",
    "PAINT/PLASTER": "Peeling paint or plaster",
    "DOOR/WINDOW": "Broken door or window",
    "PLUMBING": "Plumbing", "WATER LEAK": "Water leak", "ELECTRIC": "Electrical problem",
    "FLOORING/STAIRS": "Floors or stairs", "APPLIANCE": "Broken appliance", "GENERAL": "General repairs",
    "ELEVATOR": "Elevator", "SAFETY": "Building safety", "OUTSIDE BUILDING": "Outside of building",
    "Noise - Residential": "Noisy neighbors", "Noise - Street/Sidewalk": "Street noise",
    "Noise - Commercial": "Noisy business", "Noise - Vehicle": "Noisy vehicle", "Noise - Park": "Noise in a park",
    "Noise - Helicopter": "Helicopters", "Noise": "Construction or other noise",
    "Rodent": "Rats and mice", "Dirty Condition": "Dirty street or sidewalk",
    "Illegal Parking": "Illegal parking", "Blocked Driveway": "Blocked driveway",
    "Abandoned Vehicle": "Abandoned car", "Derelict Vehicles": "Derelict car",
    "Street Condition": "Potholes and street damage", "Street Light Condition": "Street light out",
    "Traffic Signal Condition": "Traffic signal problem", "Sidewalk Condition": "Broken sidewalk",
    "Water Maintenance": "Water main or hydrant", "Sewer Maintenance": "Sewer problem",
    "Missed Collection": "Missed trash pickup", "Illegal Dumping": "Illegal dumping",
    "General Construction/Plumbing": "Construction or plumbing work", "Elevator": "Elevator",
    "Damaged Tree": "Damaged tree", "Overgrown Tree/Branches": "Overgrown tree",
    "Consumer Complaint": "Consumer complaint", "Food Establishment": "Restaurant problem",
    "Vendor Enforcement": "Street vendor", "Graffiti": "Graffiti", "Dead Animal": "Dead animal",
    "Illegal Fireworks": "Illegal fireworks",
}


def nice(complaint_type: str) -> str:
    return NICE_NAMES.get(complaint_type, complaint_type)


# ---------------------------------------------------------------- problem details
# 311 has two more levels below the complaint type: "Problem Detail" (descriptor) and
# "Additional Details" (descriptor_2). Both are picked from fixed menus, not typed freely,
# but build.py still only publishes a detail once it shows up at least 3 times in a place.

def _re_split(s):
    import re
    return re.split(r"[\s/,-]+", s)


_BLANK = {"", "N/A", "NA", "-", "OTHER", "Other", "Other (complaint details)", "Unknown"}

# Labels for combinations that read badly as-is. Keys are (descriptor, descriptor_2), lowercased.
_DETAIL_LABELS = {
    ("no access", ""): "Driveway fully blocked",
    ("partial access", ""): "Driveway partly blocked",
    ("with license plate", ""): "Abandoned car (with plates)",
    ("derelict vehicles", ""): "Derelict car",
    ("construction", "before/after hours"): "Construction at odd hours",
    ("dog", ""): "Barking dog",
    ("alarm", "chronic"): "Alarm that won't stop",
    ("lead kit", ""): "Lead test kit request",
    ("removal request", ""): "Dumped stuff to haul away",
    ("trash", "littering"): "Littering",
    ("trash", "not cleaned by property owner"): "Trash left by property owner",
    ("mold", ""): "Mold",
    ("catch basin clogged", ""): "Clogged storm drain",
    ("backup", ""): "Sewer backup",
    ("flooding on street", ""): "Flooded street",
    ("dirty water", ""): "Dirty tap water",
    ("controller", "allout"): "Traffic signal completely out",
    ("controller", "all out"): "Traffic signal completely out",
    ("controller", "operating improperly"): "Traffic signal acting up",
    ("building shaking/vibrating/structural stability", ""): "Building shaking or unstable",
    ("trees and sidewalks program", "free repair"): "Tree-damaged sidewalk (free repair)",
}


def _sentence(s: str) -> str:
    s = " ".join(s.split())
    words = [w for w in _re_split(s) if w]
    capped = sum(1 for w in words if w[:1].isupper())
    if s.isupper() or (words and capped >= 0.6 * len(words)):
        s = s.lower()
    return s[:1].upper() + s[1:]


def detail_of(ctype: str, d1: str | None, d2: str | None) -> str | None:
    """A short human label for the problem detail, or None if there's nothing useful."""
    d1 = (d1 or "").strip()
    d2 = (d2 or "").strip()
    if d1 in _BLANK:
        d1 = ""
    if d2 in _BLANK or d2.startswith("Location Type"):
        d2 = ""
    if not d1 and not d2:
        return None
    key = (d1.lower(), d2.lower())
    if key in _DETAIL_LABELS:
        return _DETAIL_LABELS[key]
    if ctype == "HEAT/HOT WATER":
        base = _sentence(d2 or "No heat or hot water")
        return base + (" (whole building)" if d1.upper() == "ENTIRE BUILDING" else " (one apartment)")
    if d1.upper() == "PESTS":
        return _sentence(d2) if d2 else "Pests"
    if d1.lower().startswith("elevator"):
        return "Elevator out"
    if d1 and d2:
        label = f"{_sentence(d1)}: {d2.lower()}"
    else:
        label = _sentence(d1 or d2)
    where = _NOISE_WHERE.get(ctype)
    return f"{label} ({where})" if where else label


# The same noise detail can come from different places; say which.
_NOISE_WHERE = {
    "Noise - Residential": "next door",
    "Noise - Street/Sidewalk": "on the street",
    "Noise - Commercial": "at a business",
    "Noise - Park": "in a park",
}


# Responding agencies: short, friendly names.
AGENCIES = {
    "NYPD": "Police (NYPD)",
    "HPD": "Housing (HPD)",
    "DEP": "Environmental Protection (DEP)",
    "DSNY": "Sanitation (DSNY)",
    "DOT": "Transportation (DOT)",
    "DOB": "Buildings (DOB)",
    "DOHMH": "Health (DOHMH)",
    "DPR": "Parks (DPR)",
    "TLC": "Taxi & Limousine (TLC)",
    "DCWP": "Consumer & Worker Protection",
    "EDC": "Economic Development (EDC)",
}


def agency_of(code: str | None) -> str:
    # Agencies not listed (including Homeless Services, whose requests are about people) count as "Other agencies".
    return AGENCIES.get((code or "").strip(), "Other agencies")


# ---------------------------------------------------------------- rare finds
# Rare menu choices make the best "huh?" moments. These are shown citywide only (never by
# neighborhood), and anything grim or about vulnerable people is filtered out.

_GRIM = ("harass", "traffick", "abuse", "assault", "discriminat", "bias", "weapon", "death", "dead ",
         "suicide", "overdose", "child", "minor", "lead", "asbestos", "sewage", "gas leak", "carbon monoxide",
         "fire", "smoke detector", "collapse", "unsafe", "injur", "eviction", "illegal conversion", "homeless")

# Words that tend to make a rare item delightful rather than dull.
_WHIMSY = ("horse", "bee", "pigeon", "goat", "chicken", "rooster", "farm", "animal", "pet", "poison ivy", "worm",
           "insect", "statue", "monument", "film", "tattoo", "airline", "scale", "laser", "ice cream", "sauna",
           "pool", "beach", "pedicab", "compliment", "hummock", "mosquito", "duck", "swan", "snake", "parrot",
           "karaoke", "costume", "calorie", "fortune", "psychic", "carriage", "hot dog", "pretzel", "souvenir",
           "ticket", "tour bus", "street fair", "stoop", "gift", "hotel", "barber", "nail salon", "car wash",
           "snake", "wildlife", "bird", "flying", "helicopter", "raccoon", "coyote", "hawk", "owl", "bat", "turtle",
           "squirrel", "deer", "fox", "opossum", "skunk", "news gathering", "film shoot", "drone", "gender pricing",
           "bookings under 4 hours",
           # Chicago
           "coyote", "divvy", "lime", "lake", "river", "submerged", "scooter", "viaduct", "fuel pump", "cable tv",
           "bungalow", "vintage", "porch", "no longer", "solicitation", "outdated merchandise")



import re as _re

_GRIM_RE = _re.compile(r"\b(" + "|".join(_re.escape(g.strip()) for g in _GRIM) + ")")
_WHIMSY_RE = _re.compile(r"\b(" + "|".join(_re.escape(w) for w in _WHIMSY) + r")(e?s)?\b")


def rare_ok(complaint_type: str, label: str) -> bool:
    text = f"{complaint_type} {label}".lower()
    return is_public(complaint_type) and not _GRIM_RE.search(text)


_CRITTER_TYPES = {"Illegal Animal Sold", "Animal in a Park", "Harboring Bees/Wasps", "Unsanitary Pigeon Condition",
                  "Illegal Animal Kept as Pet", "Pet Sale", "Animal Facility - No Permit"}


def whimsy(complaint_type: str, label: str) -> int:
    # Judge the detail itself; the broad category name alone shouldn't make a dull item look fun.
    text = label.lower()
    score = 2 * len(set(m.group(1) for m in _WHIMSY_RE.finditer(text)))
    if complaint_type in _CRITTER_TYPES:
        score += 2
    if _re.search(r"receipt|refund|not posted|not displayed|not provided|explain below|\bother\b|unsanitary|maintenance|equipment", text):
        score -= 3
    # Hardware faults (street lights, signals) are rare but not much fun.
    if complaint_type in ("Street Light Condition", "Traffic Signal Condition", "Street Sign - Damaged",
                          "Street Sign - Dangling", "Street Sign - Missing", "Highway Sign - Damaged"):
        score -= 3
    return score
