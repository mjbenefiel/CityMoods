# CityMoods

A map of what cities report to 311 each day, grouped into playful "moods" (no heat, noise, parking wars, critters…) and shown by neighborhood. Cities: New York, Chicago, Los Angeles, San Francisco and Boston.

```
docs/                 The website (static, no build step). GitHub Pages serves this folder.
  index.html, style.css, privacy.html
  home.js             Front page (no ?city=): rotating headline, live city cards with mini maps
  app.js              City view (?city=nyc|chicago|la|sf|boston): map, moods, cards, rare finds
  data/cities.json    Which cities have data
  data/<city>/        latest.json, index.json, days/<date>.json, neighborhoods.geojson
pipeline/
  build.py            Shared: aggregate, distinctive gripes, rare finds, Claude headline, privacy check
  cities.py           Per-city settings: dataset, fields fetched, boundaries, extras ("Today in 311")
  common.py           Paths, logging, HTTP with retries, map simplification
  moods.py            NYC moods, detail labels, sensitive types; shared mood colors and rare-find filters
  moods_chicago.py    Chicago moods, names, sensitive types
  moods_simple.py     LA, SF and Boston moods, names, sensitive types; SF detail labels
.github/workflows/daily.yml   Runs build.py nightly for every city and commits docs/data
```

## Privacy rules (keep these)

- Chicago: the job downloads only `sr_type`, `community_area`, `owner_department`. No addresses or coordinates at all
  (Chicago already provides the community area). Information-only calls, airport-logged aircraft noise and
  duplicates are left out of the map; O'Hare's count appears only as a citywide "Today in 311" line.
- Los Angeles: only `type`, `department_name__c` and the Neighborhood Council number. Information-only calls and
  scheduled bulky-item pickups stay off the map (citywide lines only). Homeless encampments and "illegal
  activities" are never named.
- San Francisco: only the category, its two menu detail levels, agency and `analysis_neighborhood`. Never the
  free-text `status_notes`. Encampments, homelessness, needles, human waste and Muni *employee* feedback are never named.
- Boston: only `service_name`, `assigned_department`, `neighborhood` (new 311 system, July 2026 onward). Needle
  pickups are never named.
- NYC: police outcome lines come from counting NYPD's standard closing notes for noise calls; the notes
  themselves are never downloaded into the published data or quoted.

- The job downloads only `complaint_type`, `descriptor` (Problem Detail), `descriptor_2` (Additional Details), `agency`, `latitude`, `longitude`. The two detail fields are fixed menu choices, not free text. Never addresses, streets, BBL, ZIP, request IDs or `resolution_description`.
- Coordinates are used once to find the neighborhood, then dropped. Only neighborhood totals are published.
- Neighborhood counts under 3 are left out (moods, details and the lead agency alike).
- Rare finds (menu choices seen less than about once a week) are shown citywide only, never by neighborhood, and `rare_ok` in `moods.py` filters out anything grim.
- Complaint types about people (homelessness, panhandling, police matters…) are listed in `SENSITIVE` in `moods.py`. They count toward "everything else" and are never named or put in the headline.
- `assert_no_pii` in `build.py` stops the build if anything address- or coordinate-like reaches the output.
- The site sets no cookies. Its only third-party request is GoatCounter's cookie-free page counter (citymoods.goatcounter.com), which counts page views and neighborhood opens. If that changes, update `privacy.html` too.

## When it runs

`.github/workflows/daily.yml` runs every night at 05:07 UTC (11:07 PM Central; midnight during daylight time).
NYC refreshes the 311 dataset each evening around 8:30-9:15 PM Central, and that refresh completes the
*previous* day, so the site is always about a day behind.

Each run builds any complete days that aren't on the site yet, oldest first (up to 7), and Claude writes the
headline and quips for each of them. If the city hasn't posted a new full day yet, the run does nothing, so
Claude is never paid twice for the same day. `--force` rebuilds the newest day anyway.

## Changing the design

`index.html` and `privacy.html` load `style.css?v=…` and `app.js?v=…`. After editing either file, bump that
`v=` number (any new value, e.g. the date and time) so browsers fetch the new copy instead of an old cached one.

## Run it locally

```
python3 pipeline/build.py --no-claude        # builds any new complete days (no Claude)
python3 -m http.server 8001 --directory docs  # then open http://localhost:8001
```

On this Mac, Python needs `SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")` set.

NYC publishes each day's 311 data the next morning, so the site always shows yesterday (or the day before, early in the morning).

## The daily headline

With an `ANTHROPIC_API_KEY` set, Claude writes the headline, blurb, one line per borough, and picks the day's three best "rare finds" with a quip each, all from the totals only (no record-level data is ever sent). Without a key, a plain rule-based headline is used. Model: `claude-opus-5-5`, override with `CITYMOODS_MODEL`. Roughly a couple of cents a day.

## Going live

1. Create a GitHub repo and push.
2. Settings → Pages: deploy from branch `main`, folder `/docs`.
3. Optional: add the repository secret `ANTHROPIC_API_KEY` for the Claude headline.
4. Actions → Daily mood → Run workflow once to check it.

Data: NYC Open Data (311 Service Requests; 2020 Neighborhood Tabulation Areas). Weather: Open-Meteo.

## License

Code: MIT (see `LICENSE`). The published data comes from NYC Open Data (311 Service Requests; 2020 Neighborhood
Tabulation Areas) and Open-Meteo, under their own terms; CityMoods is not affiliated with the City of New York.
