"""Chicago: which 311 request types belong to which mood, friendly names, and what's never shown.

Chicago's 311 data has one level of detail (the request type), so the type *is* the detail.
Moods share ids and colors with NYC (see moods.MOODS) so the site looks the same in every city.
"""
from moods import _GRIM_RE, whimsy as _whimsy  # noqa: F401  (shared filters)

# Left out entirely before anything is counted (handled in cities.py):
#   "311 INFORMATION ONLY CALL"  - questions, not complaints
#   "Aircraft Noise Complaint"   - all logged at O'Hare itself, so it says nothing about neighborhoods
#                                   (shown only as a citywide stat)
EXCLUDED = {"311 INFORMATION ONLY CALL", "Aircraft Noise Complaint"}

_MOODS = {
    "critters": ["Rodent Baiting/Rat Complaint", "Dead Animal Pick-Up Request", "Stray Animal Complaint",
                 "Report an Injured Animal", "Nuisance Animal Complaint", "Coyote Interaction Complaint",
                 "Vicious Animal Complaint", "Pet Wellness Check Request", "Dead Bird", "Bee/Wasp Removal",
                 "Animal In Trap Complaint"],
    "trash": ["Graffiti Removal Request", "Garbage Cart Maintenance", "Yard Waste Pick-Up Request", "Fly Dumping Complaint",
              "Blue Recycling Cart", "Sanitation Code Violation", "Missed Garbage Pick-Up Complaint", "Street Cleaning Request",
              "Recycling Pick Up", "Clean Vacant Lot Request", "Wire Basket Request", "Recycling Inspection Request",
              "Clean and Green Program Request"],
    "streets": ["Street Light Out Complaint", "Pothole in Street Complaint", "Traffic Signal Out Complaint",
                "Sign Repair Request - All Other Signs", "Inspect Public Way Request", "Alley Pothole Complaint",
                "Sidewalk Inspection Request", "Alley Light Out Complaint", "Sign Repair Request - Stop Sign",
                "Street Light Pole Damage Complaint", "Sign Repair Request - One Way Sign", "Bicycle Request/Complaint",
                "Street Light On During Day Complaint", "Sign Repair Request - Do Not Enter Sign",
                "Street Light Pole Door Missing Complaint", "Protected Bike Lane - Debris Removal",
                "Viaduct Light Out Complaint", "Snow – Uncleared Sidewalk Complaint"],
    "trees": ["Tree Trim Request (NO LONGER BEING ACCEPTED)", "Tree Debris Clean-Up Request", "Tree Removal Inspection",
              "Tree Emergency", "Tree Planting Request", "Weed Removal Request"],
    "water": ["Water Lead Test Kit Request", "Sewer Cleaning Inspection Request", "Check for Leak", "Sewer Cave-In Inspection Request",
              "Water On Street Complaint", "No Water Complaint", "Water in Basement Complaint", "Water Lead Test Visit Request",
              "Open Fire Hydrant Complaint", "Low Water Pressure Complaint", "Alley Sewer Inspection Request",
              "Water Quality Concern"],
    "parking": ["Abandoned Vehicle Complaint", "Finance Parking Code Enforcement Review", "City Vehicle Sticker Violation",
                "E-Scooter Parking Complaint", "Divvy Bike Parking Complaint"],
    "housing": ["Building Violation", "Buildings - Plumbing Violation", "No Building Permit and Construction Violation",
                "Vacant/Abandoned Building Complaint", "Porch Inspection Request", "No Air Conditioning",
                "Lead Inspection Request"],
}
_LOOKUP = {t: m for m, types in _MOODS.items() for t in types}

# About people's livelihoods or hardship: counted as "everything else", never named or featured.
SENSITIVE = {"Renters and Foreclosure Complaint", "Wage Complaint", "Paid Sick Leave Violation",
             "Tobacco - Sale to Minors Complaint", "Home Buyer Program Info Request"}

NICE_NAMES = {
    "Rodent Baiting/Rat Complaint": "Rats",
    "Graffiti Removal Request": "Graffiti",
    "Abandoned Vehicle Complaint": "Abandoned car",
    "Garbage Cart Maintenance": "Busted garbage cart",
    "Yard Waste Pick-Up Request": "Yard waste pickup",
    "Tree Trim Request (NO LONGER BEING ACCEPTED)": "Tree trim (no longer accepted)",
    "Street Light Out Complaint": "Street light out",
    "Pothole in Street Complaint": "Pothole",
    "Water Lead Test Kit Request": "Lead test kit",
    "Traffic Signal Out Complaint": "Traffic signal out",
    "Finance Parking Code Enforcement Review": "Parking enforcement review",
    "Fly Dumping Complaint": "Illegal dumping",
    "Dead Animal Pick-Up Request": "Dead animal",
    "Blue Recycling Cart": "Recycling cart",
    "Coyote Interaction Complaint": "Coyote encounter",
    "Vicious Animal Complaint": "Vicious animal",
    "Alley Pothole Complaint": "Alley pothole",
    "Missed Garbage Pick-Up Complaint": "Missed garbage pickup",
    "Buildings - Plumbing Violation": "Plumbing violation",
    "No Building Permit and Construction Violation": "Construction without a permit",
    "Vacant/Abandoned Building Complaint": "Vacant building",
    "E-Scooter Parking Complaint": "Badly parked e-scooter",
    "Divvy Bike Parking Complaint": "Badly parked Divvy bike",
    "Submerged Divvy or Lime Device in the Lake/River": "Divvy or Lime in the lake or river",
    "Snow – Uncleared Sidewalk Complaint": "Unshoveled sidewalk",
    "Water in Basement Complaint": "Water in the basement",
    "Street Light On During Day Complaint": "Street light on during the day",
    "Sign Repair Request - All Other Signs": "Sign repair",
    "Sign Repair Request - Stop Sign": "Stop sign repair",
    "Sign Repair Request - One Way Sign": "One-way sign repair",
    "Sign Repair Request - Do Not Enter Sign": "Do Not Enter sign repair",
    "Inspect Public Way Request": "Public way inspection",
    "Sewer Cleaning Inspection Request": "Sewer cleaning",
    "Sewer Cave-In Inspection Request": "Sewer cave-in",
    "Alley Sewer Inspection Request": "Alley sewer",
    "Tree Debris Clean-Up Request": "Tree debris cleanup",
    "Tree Removal Inspection": "Tree removal",
    "Water Lead Test Visit Request": "Lead test visit",
    "Check for Leak": "Possible water leak",
    "City Vehicle Sticker Violation": "Missing city vehicle sticker",
    "Sanitation Code Violation": "Sanitation code violation",
    "Bicycle Request/Complaint": "Bike issue",
    "Cab Feedback": "Cab feedback",
    "Pet Wellness Check Request": "Pet wellness check",
    "Report an Injured Animal": "Injured animal",
    "Bee/Wasp Removal": "Bees or wasps",
    "Protected Bike Lane - Debris Removal": "Debris in a protected bike lane",
    "Sidewalk Café/Outdoor Dining Complaint": "Sidewalk café",
    "Shared Housing/Vacation Rental Complaint": "Vacation rental",
    "Commercial Fire Safety Inspection Request": "Fire safety inspection",
    "Bungalow/Vintage Home Information Request": "Bungalow or vintage home question",
    "Inaccurate Fuel Pump Complaint": "Inaccurate gas pump",
    "Cable TV Complaint": "Cable TV",
    "Animal In Trap Complaint": "Animal stuck in a trap",
    "No Solicitation Complaint": "Ignored 'No Solicitation' sign",
    "Outdated Merchandise Complaint": "Outdated merchandise",
    "Clean and Green Program Request": "Clean and Green program",
    "Wire Basket Request": "Wire trash basket",
}


def mood_of(t: str) -> str:
    if t in SENSITIVE:
        return "other"
    return _LOOKUP.get(t, "other")


def is_public(t: str) -> bool:
    return t not in SENSITIVE and t not in EXCLUDED


def nice(t: str) -> str:
    if t in NICE_NAMES:
        return NICE_NAMES[t]
    s = t
    for suffix in (" Request/Complaint", " Complaint", " Request", " Inspection Request"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    return s[:1].upper() + s[1:].lower()  # "Water On Street" -> "Water on street"


def rare_ok(t: str, label: str) -> bool:
    return is_public(t) and not _GRIM_RE.search(f"{t} {label}".lower())


def whimsy(t: str, label: str) -> int:
    return _whimsy(t, label)


AGENCIES = {
    "Streets and Sanitation": "Streets & Sanitation",
    "CDOT - Department of Transportation": "Transportation (CDOT)",
    "DWM - Department of Water Management": "Water Management",
    "DOB - Buildings": "Buildings",
    "Animal Care and Control": "Animal Care & Control",
    "Finance": "Finance",
    "Health": "Public Health",
    "BACP - Business Affairs and Consumer Protection": "Business Affairs (BACP)",
    "Outside Agencies": "Outside agencies",
    "City Clerk's Office": "City Clerk",
    "Fire": "Fire Department",
    "Department of Housing": "Housing",
}


def agency_of(dept: str | None) -> str:
    return AGENCIES.get((dept or "").strip(), "Other agencies")
