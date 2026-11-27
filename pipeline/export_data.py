"""Write the downloadable CSVs for the Data page (docs/data/downloads/).

Everything here is re-shaped from the day files the site already publishes (docs/data/<city>/days/*.json),
so the downloads never contain anything the maps don't already show: neighborhood totals of 3 or more,
city-wide counts, and the category mapping. No addresses, coordinates or individual requests.

    python pipeline/export_data.py      # also runs at the end of every nightly build

Per city (docs/data/downloads/<city>/):
  citywide.csv                    every day: requests per mood, the usual level, weather
  notable-types.csv               every day: the day's top and spiking request types, with their usual level
  neighborhoods-YYYY-MM.csv       one row per neighborhood, mood and day (counts under 3 never published)
  neighborhood-types-YYYY-MM.csv  each neighborhood's top request types per day (3 or more)
  mood-map.csv                    which raw 311 request types count toward each mood
Plus all-cities-citywide.csv and manifest.json (for scripts and AI agents).
"""
from __future__ import annotations

import csv
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, log  # noqa: E402
from moods import MOODS  # noqa: E402
import moods as nyc_moods  # noqa: E402
import moods_chicago as chi_moods  # noqa: E402
import moods_simple as simple  # noqa: E402
from build import ADDRESS_RE, MIN_CELL  # noqa: E402

OUT = DATA / "downloads"
SITE = "https://citymoods311.com"
LICENSE = "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Credit: CityMoods (citymoods311.com)"
AREA_WORD = {"nyc": "borough"}   # everyone else: "area" (Chicago sides, LA regions; SF and Boston have one)


def mood_rules(key: str) -> list[tuple[str, str, str]]:
    """(mood, how it matches, raw 311 type or pattern). Sensitive types are never listed."""
    rows = []
    if key == "nyc":
        rows += [(m, "exact", t) for m, ts in nyc_moods._EXACT.items() for t in ts]
        rows += [("noise", "starts with", "Noise"), ("noise", "exact", "Illegal Fireworks")]
    elif key == "chicago":
        rows += [(m, "exact", t) for m, ts in chi_moods._MOODS.items() for t in ts]
    else:
        sm = {"la": simple.LA, "sf": simple.SF, "boston": simple.BOSTON}[key]
        rows += [(m, "exact", t) for t, m in sm._lookup.items() if t not in sm.sensitive]
        rows += [(m, "contains (regex)", rx.pattern) for rx, m in sm.keyword_moods]
    return sorted(set(rows), key=lambda r: (list(MOODS).index(r[0]), r[1], r[2].lower(), r[2]))


# Every column in every download, in plain words (rendered on the Data page and as data-dictionary.csv).
_CITY = [("city", "City key: nyc, chicago, la, sf or boston."), ("city_name", "City name.")]
_DAY = [("date", "The day the 311 requests were created, in the city's local time (YYYY-MM-DD)."),
        ("weekday", "Day of the week for that date.")]
_HOOD = [("neighborhood_id", "The city's own code for the neighborhood (NYC NTA code, Chicago community area number, "
                             "and so on). Stable across days, so use it to join files."),
         ("neighborhood", "Neighborhood name, from the city's official boundaries."),
         ("area / borough", "The larger part of the city the neighborhood sits in: NYC borough, Chicago side, LA region. "
                            "SF and Boston have just one area. Called 'borough' in New York's own files.")]
_MOOD = [("mood", "CityMoods category id: heat, noise, parking, housing, streets, trash, critters, water, trees, other."),
         ("mood_label", "The category's display name, e.g. 'Parking wars'.")]
_REQ = ("requests", "Number of 311 requests that day.")
_USUAL = ("usual", "Average requests on the same weekday over the previous 4 weeks. Compare with 'requests' to spot a "
                   "spike. Blank when there isn't enough history.")
DICTIONARY = (
    [("citywide.csv", c, m) for c, m in _DAY + _MOOD] + [
        ("citywide.csv", *_REQ),
        ("citywide.csv", *_USUAL),
        ("citywide.csv", "high_f", "That day's high temperature in °F (Open-Meteo, city center)."),
        ("citywide.csv", "low_f", "That day's low temperature in °F."),
        ("citywide.csv", "rain_in", "Total rain (precipitation) that day, in inches."),
        ("citywide.csv", "(mood = all)", "One row per day with mood 'all' gives the total for every request type."),
    ]
    + [("all-cities-citywide.csv", c, m) for c, m in _CITY]
    + [("all-cities-citywide.csv", "(other columns)", "Same as citywide.csv, for all five cities in one file.")]
    + [("notable-types.csv", c, m) for c, m in _DAY] + [
        ("notable-types.csv", "request_type", "A specific 311 request type (cleaned-up name), e.g. 'Rats' or 'Flooding: on street'."),
        ("notable-types.csv", "mood", "The mood that request type counts toward."),
        ("notable-types.csv", *_REQ),
        ("notable-types.csv", *_USUAL),
        ("notable-types.csv", "ratio", "requests ÷ usual. 3.0 means three times the usual level."),
        ("notable-types.csv", "kind", "'spike' = well above its usual level that day; 'top' = one of the day's most common types."),
    ]
    + [("neighborhoods-YYYY-MM.csv", c, m) for c, m in _DAY[:1] + _HOOD] + [
        ("neighborhoods-YYYY-MM.csv", "neighborhood_total", "All requests from that neighborhood that day."),
        ("neighborhoods-YYYY-MM.csv", "mood", _MOOD[0][1]),
        ("neighborhoods-YYYY-MM.csv", "requests", "Requests in that mood from that neighborhood that day. Only counts "
                                                  "of 3 or more are published, so moods can be missing and rows may "
                                                  "not add up to neighborhood_total."),
    ]
    + [("neighborhood-types-YYYY-MM.csv", c, m) for c, m in _DAY[:1] + _HOOD] + [
        ("neighborhood-types-YYYY-MM.csv", "request_type", "One of that neighborhood's most common request types that day."),
        ("neighborhood-types-YYYY-MM.csv", "mood", "The mood that request type counts toward."),
        ("neighborhood-types-YYYY-MM.csv", "requests", "Requests of that type from that neighborhood that day (3 or more)."),
    ]
    + [("all-cities-neighborhoods-YYYY-MM.csv / all-cities-neighborhood-types-YYYY-MM.csv", c, m) for c, m in _CITY]
    + [("all-cities-neighborhoods-YYYY-MM.csv / all-cities-neighborhood-types-YYYY-MM.csv", "(other columns)",
        "Same as the per-city neighborhood files, for all five cities in one file per month; the area column is always called 'area'.")]
    + [("mood-map.csv", c, m) for c, m in _MOOD] + [
        ("mood-map.csv", "match", "'exact' = this exact raw type; 'starts with' or 'contains (regex)' = any raw type matching the pattern."),
        ("mood-map.csv", "raw_311_type", "The request type exactly as the city's open data names it (or the pattern)."),
    ]
)


class Writer:
    """Collects CSV text, checks it, and only rewrites files whose content changed (keeps the repo small)."""

    def __init__(self):
        self.files = []

    def write(self, path: Path, header: list[str], rows: list[list]):
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
        text = buf.getvalue()
        for line in text.splitlines():
            if ADDRESS_RE.search(line):
                raise SystemExit(f"Privacy check failed in {path.name}: {line!r}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
        self.files.append({"path": str(path.relative_to(DATA.parent)), "rows": len(rows),
                           "url": f"{SITE}/{path.relative_to(DATA.parent)}"})


def export_city(key: str, name: str, W: Writer) -> list[list]:
    city_dir = DATA / key
    dates = sorted(json.loads((city_dir / "index.json").read_text())["days"])
    out = OUT / key
    citywide, notable = [], []
    hoods_by_month, types_by_month = defaultdict(list), defaultdict(list)
    for d in dates:
        day = json.loads((city_dir / "days" / f"{d}.json").read_text())
        wx = day.get("weather") or {}
        base = [d, day["weekday"]]
        citywide.append(base + ["all", "All requests", day["total"], day.get("typical_total", ""),
                                wx.get("high_f", ""), wx.get("low_f", ""), wx.get("rain_in", "")])
        for m in day["moods"]:
            citywide.append(base + [m["id"], MOODS[m["id"]]["label"], m["n"], m.get("typical", ""),
                                    wx.get("high_f", ""), wx.get("low_f", ""), wx.get("rain_in", "")])
        seen = set()
        for kind, items in (("spike", day.get("detail_spikes", []) + day.get("spikes", [])),
                            ("top", day.get("top_details", []) + day.get("top_types", []))):
            for t in items:
                if t["name"] in seen:
                    continue
                seen.add(t["name"])
                notable.append(base + [t["name"], t["mood"], t["n"], t.get("typical", ""), t.get("ratio", ""), kind])
        month = d[:7]
        for hid, h in sorted(day["neighborhoods"].items(), key=lambda kv: kv[1]["name"]):
            for mood, n in sorted(h["moods"].items(), key=lambda kv: -kv[1]):
                if n < MIN_CELL:
                    raise SystemExit(f"{key} {d} {h['name']}: count under {MIN_CELL} in published data")
                hoods_by_month[month].append([d, hid, h["name"], h.get("borough", ""), h["total"], mood, n])
            for t in h.get("details", []):
                if t["n"] >= MIN_CELL:
                    types_by_month[month].append([d, hid, h["name"], h.get("borough", ""), t["name"], t["mood"], t["n"]])

    W.write(out / "citywide.csv", ["date", "weekday", "mood", "mood_label", "requests", "usual",
                                   "high_f", "low_f", "rain_in"], citywide)
    W.write(out / "notable-types.csv", ["date", "weekday", "request_type", "mood", "requests", "usual",
                                        "ratio", "kind"], notable)
    area = AREA_WORD.get(key, "area")
    for month, rows in sorted(hoods_by_month.items()):
        W.write(out / f"neighborhoods-{month}.csv", ["date", "neighborhood_id", "neighborhood", area,
                                                    "neighborhood_total", "mood", "requests"], rows)
    for month, rows in sorted(types_by_month.items()):
        W.write(out / f"neighborhood-types-{month}.csv", ["date", "neighborhood_id", "neighborhood", area,
                                                         "request_type", "mood", "requests"], rows)
    W.write(out / "mood-map.csv", ["mood", "mood_label", "match", "raw_311_type"],
            [[m, MOODS[m]["label"], how, t] for m, how, t in mood_rules(key)])
    tag = lambda rows: [[key, name] + r for r in rows]
    return tag(citywide), {m: tag(r) for m, r in hoods_by_month.items()}, {m: tag(r) for m, r in types_by_month.items()}


def export_all():
    cities = json.loads((DATA / "cities.json").read_text())["cities"]
    W = Writer()
    combined, all_hoods, all_types = [], defaultdict(list), defaultdict(list)
    for c in cities:
        cw, hoods, types = export_city(c["key"], c["name"], W)
        combined += cw
        for m, rows in hoods.items():
            all_hoods[m] += rows
        for m, rows in types.items():
            all_types[m] += rows
    W.write(OUT / "all-cities-citywide.csv", ["city", "city_name", "date", "weekday", "mood", "mood_label",
                                             "requests", "usual", "high_f", "low_f", "rain_in"], combined)
    for m, rows in sorted(all_hoods.items()):
        W.write(OUT / f"all-cities-neighborhoods-{m}.csv", ["city", "city_name", "date", "neighborhood_id",
                "neighborhood", "area", "neighborhood_total", "mood", "requests"], rows)
    for m, rows in sorted(all_types.items()):
        W.write(OUT / f"all-cities-neighborhood-types-{m}.csv", ["city", "city_name", "date", "neighborhood_id",
                "neighborhood", "area", "request_type", "mood", "requests"], rows)
    W.write(OUT / "data-dictionary.csv", ["file", "column", "meaning"], [list(r) for r in DICTIONARY])
    manifest = {
        "name": "CityMoods 311 data",
        "description": "Daily 311 service-request counts by mood and neighborhood for New York City, Chicago, "
                       "Los Angeles, San Francisco and Boston, from each city's open data portal. Neighborhood "
                       "counts under 3 are not published; requests about people are grouped into 'other' and "
                       "never named. 'usual' is the average for the same weekday over the previous 4 weeks.",
        "license": LICENSE,
        "docs": f"{SITE}/data/",
        "sources": {c["key"]: c.get("sources", []) for c in cities},
        "moods": {k: v["label"] for k, v in MOODS.items()},
        "columns": [{"file": f, "column": c, "meaning": m} for f, c, m in DICTIONARY],
        "files": W.files,
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=1)
    if not (OUT / "manifest.json").exists() or (OUT / "manifest.json").read_text() != text:
        (OUT / "manifest.json").write_text(text)
    write_page(cities, W.files)
    log(f"Exported {len(W.files)} download files")


ASK_SCRIPT = """<script>
(function () {
  var q = document.getElementById("askq"), p = document.getElementById("askp"),
      c = document.getElementById("askc"), ok = document.getElementById("asko");
  function prompt() {
    var question = q.value.trim() || q.placeholder;
    return "Use the CityMoods 311 data at https://citymoods311.com/llms.txt (every CSV is listed in " +
      "https://citymoods311.com/data/downloads/manifest.json). Answer only from that data. Say which files and " +
      "dates you used, and when you call something a spike, compare 'requests' with the 'usual' column.\\n\\n" +
      "My question: " + question;
  }
  function render() { p.textContent = prompt(); ok.textContent = ""; }
  q.addEventListener("input", render);
  document.querySelectorAll(".ask .ex a").forEach(function (a) {
    function pick() { q.value = a.getAttribute("data-q"); render(); q.focus(); }
    a.addEventListener("click", pick);
    a.addEventListener("keydown", function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(); } });
  });
  c.addEventListener("click", function () {
    var text = prompt();
    function done() { ok.textContent = "Copied. Paste it into your AI assistant."; }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(text); done(); });
    } else { fallback(text); done(); }
  });
  function fallback(text) {
    var t = document.createElement("textarea"); t.value = text; document.body.appendChild(t);
    t.select(); try { document.execCommand("copy"); } catch (e) {} document.body.removeChild(t);
  }
  render();
})();
</script>
<script src="/menu.js?v=202611250100"></script>"""


def write_page(cities: list[dict], files: list[dict]):
    """docs/data/index.html: the Data page (static, so search engines and AI agents can read it)."""
    from html import escape as e
    by_city = defaultdict(list)
    for f in files:
        parts = Path(f["path"]).parts            # data/downloads/<city>/<file> or data/downloads/<file>
        by_city[parts[2] if len(parts) == 4 else "_all"].append(f)

    def link(f, label):
        name = Path(f["path"]).name
        return f'<a href="downloads/{e(f["path"].split("downloads/")[1])}" download>{e(label)}</a> <span class="n">{f["rows"]:,} rows</span>'

    blocks = []
    for c in cities:
        fs = {Path(f["path"]).name: f for f in by_city[c["key"]]}
        months = sorted(n[14:21] for n in fs if n.startswith("neighborhoods-"))
        month_links = " · ".join(
            link(fs[f"neighborhoods-{m}.csv"], m) for m in reversed(months))
        type_links = " · ".join(
            link(fs[f"neighborhood-types-{m}.csv"], m) for m in reversed(months) if f"neighborhood-types-{m}.csv" in fs)
        srcs = " · ".join(f'<a href="{e(u)}">{e(l)}</a>' for l, u in c.get("sources", []))
        blocks.append(f"""
<section class="city" id="{e(c["key"])}">
  <h2>{e(c["name"])}</h2>
  <ul>
    <li>{link(fs["citywide.csv"], "Citywide by mood")}: every day, with the usual level and weather</li>
    <li>{link(fs["notable-types.csv"], "Top and spiking request types")}: every day, with the usual level</li>
    <li>Neighborhoods by mood, by month: {month_links}</li>
    <li>Neighborhood top request types, by month: {type_links}</li>
    <li>{link(fs["mood-map.csv"], "Mood map")}: which raw 311 types count toward each mood</li>
  </ul>
  <p class="src">Official source: {srcs}</p>
</section>""")
    alls = {Path(f["path"]).name: f for f in by_city["_all"]}
    months = sorted({n[-11:-4] for n in alls if n.startswith("all-cities-neighborhoods-")}, reverse=True)
    all_block = ""
    if "all-cities-citywide.csv" in alls:
        all_block = f"""
<section class="city">
  <h2>All five cities</h2>
  <ul>
    <li>{link(alls["all-cities-citywide.csv"], "Citywide by mood, all cities")}: every day, with the usual level and weather</li>
    <li>Every neighborhood in every city, by mood, by month: {" · ".join(link(alls[f"all-cities-neighborhoods-{m}.csv"], m) for m in months)}</li>
    <li>Every neighborhood's top request types, by month: {" · ".join(link(alls[f"all-cities-neighborhood-types-{m}.csv"], m) for m in months if f"all-cities-neighborhood-types-{m}.csv" in alls)}</li>
    <li>{link(alls["data-dictionary.csv"], "Data dictionary")}: every column in every file, explained</li>
  </ul>
  <p class="src">This is everything behind the maps. Individual 311 records (with addresses and notes) are never collected or shared here; for those, use each city's official portal below.</p>
</section>"""
    dict_rows = "".join(
        f"<tr><td>{e(f)}</td><td><code>{e(c)}</code></td><td>{e(m)}</td></tr>" for f, c, m in DICTIONARY)
    updated = max(json.loads((DATA / c["key"] / "index.json").read_text())["days"][0] for c in cities)
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Data downloads · CityMoods</title>
<meta name="description" content="Free CSV downloads of daily 311 complaint counts by mood and neighborhood for New York, Chicago, Los Angeles, San Francisco and Boston. Updated nightly, CC BY 4.0.">
<meta property="og:title" content="CityMoods data: 311 complaints by neighborhood, free to download">
<meta property="og:description" content="Daily 311 counts by mood and neighborhood for five US cities, comparable across cities. CSV, updated nightly, CC BY 4.0.">
<meta property="og:url" content="{SITE}/data/">
<meta property="og:image" content="{SITE}/share/site.png?v=dark1">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="icon" href="../favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<link rel="alternate" type="application/json" href="downloads/manifest.json" title="CityMoods data manifest">
<link rel="stylesheet" href="../style.css?v=202611261600">
<style>
main{{max-width:760px;padding:24px 16px 48px}} main p,main li{{color:var(--muted);line-height:1.55}}
h1{{font-size:32px}} h2{{margin-top:28px}} main a{{color:var(--ink)}}
.city{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:14px 18px;margin:14px 0}}
.city h2{{margin:0 0 6px}} .city ul{{padding-left:18px;margin:6px 0}} .city li{{margin:4px 0}}
.n{{font-size:12px;color:var(--muted)}} .src{{font-size:13px;margin:8px 0 0}}
code{{font-size:13px;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:1px 5px;word-break:break-all}}
.ask{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:14px 18px;margin:14px 0}}
.ask label{{display:block;font-weight:600;margin-bottom:6px}}
.ask input{{width:100%;box-sizing:border-box;font:inherit;font-size:16px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink)}}
.ask pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;color:var(--muted);background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:10px 0}}
.ask button{{font:inherit;font-weight:600;border:0;border-radius:999px;padding:9px 16px;background:var(--accent);color:#fff;cursor:pointer}}
.ask .ok{{margin-left:10px;font-size:14px;color:var(--muted)}}
.ask .ex{{font-size:13px;margin:12px 0 0;color:var(--muted)}} .ask .ex b{{display:block;font-weight:600;margin-bottom:4px}}
.ask .ex a{{display:inline-block;cursor:pointer;text-decoration:none;color:var(--ink);border:1px solid var(--line);border-radius:999px;padding:4px 11px;margin:3px 4px 3px 0;background:var(--bg)}}
.ask .ex a:hover,.ask .ex a:focus-visible{{border-color:var(--accent)}}
.lead{{font-size:18px}}
.toast {{ position: fixed; left: 50%; bottom: 20px; transform: translate(-50%, 20px); opacity: 0; pointer-events: none;
  background: var(--ink); color: var(--bg); padding: 10px 16px; border-radius: 999px; font-size: 14px; max-width: calc(100% - 32px);
  box-shadow: 0 4px 18px rgba(0,0,0,.25); transition: opacity .2s, transform .2s; z-index: 50; text-align: center; }}
.toast.on {{ opacity: 1; transform: translate(-50%, 0); }}
.dict{{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}}
.dict table{{border-collapse:collapse;width:100%;font-size:14px}}
.dict th,.dict td{{text-align:left;vertical-align:top;padding:8px 10px;border-bottom:1px solid var(--line);color:var(--muted)}}
.dict th{{color:var(--ink);font-weight:600}} .dict td:first-child{{font-size:12px;min-width:110px}}
.dict code{{word-break:normal;white-space:nowrap}}
</style>
<script data-goatcounter="https://citymoods.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>
</head>
<body>
<header class="top"><a class="brand" href="/" aria-label="CityMoods home"><img src="/favicon.svg" alt="" width="22" height="22"> CityMoods</a></header>
<main>
<h1>Data downloads</h1>
<p class="lead">Every day, CityMoods sorts each city's 311 requests into the same ten moods, so you can compare rats in Chicago with rodents in New York. Here's all of it as plain CSV files, free to use.</p>
<p>Updated nightly (newest day: {e(updated)}). Free to use with credit under <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>: please cite <b>"CityMoods (citymoods311.com), from [city] 311 open data"</b>.</p>

<h2>What you can do with it</h2>
<ul>
  <li><b>Spot a spike.</b> San Francisco's storm on Wednesday, Nov 18 brought 677 street flooding reports, against a usual 3. In any city's citywide file, compare <code>requests</code> with <code>usual</code>.</li>
  <li><b>Find where it happened.</b> The neighborhood files showed that 34 of New York's 52 "alarm that won't stop" reports that day came from Long Island City–Hunters Point.</li>
  <li><b>Compare cities.</b> The all-cities file puts the five side by side, say no-heat complaints in New York and Boston as winter sets in.</li>
  <li><b>Track a trend.</b> Every day is kept, so you can follow rats, flooding or streetlights week by week.</li>
</ul>

<h2>How to start</h2>
<ol>
  <li>Download a CSV below and open it in Google Sheets or Excel. Unsure what a column means? See the <a href="#columns">column definitions</a>.</li>
  <li>Filter by <code>mood</code> or <code>neighborhood</code>.</li>
  <li>Compare <code>requests</code> with <code>usual</code>. Anything around 2× or more is a spike worth a look.</li>
</ol>

<h2>Analyze it with AI</h2>
<p>Type a question, copy the prompt, and paste it into Claude, ChatGPT or any AI assistant that can read web pages. It pulls the numbers straight from these files, down to each neighborhood's top request types, which makes it useful for newsrooms, researchers, real estate and legal teams.</p>
<div class="ask">
  <label for="askq">Your question</label>
  <input id="askq" type="text" placeholder="Give me a profile of 311 activity in Logan Square, Chicago this month." autocomplete="off">
  <pre id="askp"></pre>
  <button type="button" id="askc">Copy prompt</button><span class="ok" id="asko" aria-live="polite"></span>
  <p class="ex"><b>Try a neighborhood</b><a role="button" tabindex="0" data-q="Give me a profile of 311 activity in Logan Square, Chicago this month: its top moods and request types, how it compares with neighborhoods nearby, and anything unusual.">Neighborhood profile</a><a role="button" tabindex="0" data-q="Compare Dorchester and Jamaica Plain in Boston this month: which complaints are most common in each, and how do they differ?">Compare two neighborhoods</a><a role="button" tabindex="0" data-q="Track noise complaints in Williamsburg, Brooklyn day by day this month. Were there any spikes, and on which days?">Track one over time</a><a role="button" tabindex="0" data-q="Which New York neighborhoods had the most no-heat complaints this month, and where did they rise the most?">No-heat hot spots</a><a role="button" tabindex="0" data-q="Rank San Francisco neighborhoods by water and sewer reports during the storm on Nov 18, 2026.">Storm by neighborhood</a><a role="button" tabindex="0" data-q="Which Los Angeles neighborhoods reported mudslides on Nov 19, 2026, and how many each?">Mudslides by neighborhood</a></p>
  <p class="ex"><b>Or a whole city</b><a role="button" tabindex="0" data-q="Which city had the biggest spike in water and sewer complaints this week, and how far above usual was it?">Biggest water spike</a><a role="button" tabindex="0" data-q="Compare no-heat complaints in New York and Boston over the last two weeks.">NYC vs Boston no heat</a><a role="button" tabindex="0" data-q="What were the five strangest spikes across all five cities this month?">Strangest spikes</a></p>
</div>

<h2>Downloads</h2>
{all_block}
{"".join(blocks)}

<h2 id="columns">Column definitions</h2>
<p>Every column in every file. Also available as a <a href="downloads/data-dictionary.csv" download>CSV</a>. Neighborhoods are each city's own official areas: NYC Neighborhood Tabulation Areas, Chicago Community Areas, LA Neighborhood Councils, SF Analysis Neighborhoods and Boston neighborhoods.</p>
<div class="dict"><table>
<thead><tr><th>File</th><th>Column</th><th>Meaning</th></tr></thead>
<tbody>{dict_rows}</tbody>
</table></div>

<h2>How it's made, and what's left out</h2>
<ul>
  <li>Each night we pull the most recent complete day from each city's open data portal. Cities publish on their own schedules, so the newest day is usually one or two days back.</li>
  <li>Only request types, their fixed-menu details and neighborhoods are used. No addresses, coordinates, names or written notes are downloaded or published. (NYC requests are placed in a neighborhood from their rough location, which is then discarded.)</li>
  <li>Neighborhood counts under 3 are never published, so neighborhood rows don't always add up to the citywide totals.</li>
  <li>Requests about people (homelessness, panhandling, police matters and similar) are counted in "Everything else" and never named.</li>
  <li>Chicago's information-only calls and O'Hare airport noise complaints are left out of the neighborhood counts.</li>
  <li>Need individual records? Use the official portal linked under each city.</li>
</ul>

<h2>For scripts and AI agents</h2>
<p>A machine-readable list of every file, with row counts, sources and the license: <a href="downloads/manifest.json"><code>{SITE}/data/downloads/manifest.json</code></a>. Each day is also published as JSON at <code>{SITE}/data/&lt;city&gt;/days/YYYY-MM-DD.json</code>, with the list of days in <code>{SITE}/data/&lt;city&gt;/index.json</code>. City keys: {e(", ".join(c["key"] for c in cities))}. See also <a href="../llms.txt"><code>llms.txt</code></a>.</p>

<h2>Questions</h2>
<p>Using this for a story or research? I'd love to hear about it, and I can help with custom pulls: <a href="mailto:admin@citymoods311.com?subject=CityMoods%20data">admin@citymoods311.com</a>.</p>
</main>
__ASK_SCRIPT__
</body>
</html>
"""
    (DATA / "index.html").write_text(html.replace("__ASK_SCRIPT__", ASK_SCRIPT))


if __name__ == "__main__":
    export_all()
