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
