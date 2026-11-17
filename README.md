# CityMoods · New York

A map of what New York reported to 311 yesterday, grouped into playful "moods" (no heat, noise, parking wars, critters…) and shown by neighborhood.

```
docs/                 The website (static, no build step). GitHub Pages serves this folder.
  index.html, style.css, app.js, privacy.html
  data/               Written by the daily job: latest.json, index.json, days/<date>.json, neighborhoods.geojson
pipeline/
  build.py            Fetch a day of 311 data, find each request's neighborhood, publish totals only
  moods.py            Which complaint types belong to which mood, and which are never shown
.github/workflows/daily.yml   Runs build.py every morning and commits docs/data
```

## Privacy rules (keep these)

- The job downloads only `complaint_type`, `descriptor` (Problem Detail), `descriptor_2` (Additional Details), `agency`, `latitude`, `longitude`. The two detail fields are fixed menu choices, not free text. Never addresses, streets, BBL, ZIP, request IDs or `resolution_description`.
- Coordinates are used once to find the neighborhood, then dropped. Only neighborhood totals are published.
- Neighborhood counts under 3 are left out (moods, details and the lead agency alike).
- Rare finds (menu choices seen less than about once a week) are shown citywide only, never by neighborhood, and `rare_ok` in `moods.py` filters out anything grim.
- Complaint types about people (homelessness, panhandling, police matters…) are listed in `SENSITIVE` in `moods.py`. They count toward "everything else" and are never named or put in the headline.
- `assert_no_pii` in `build.py` stops the build if anything address- or coordinate-like reaches the output.
- The site has no analytics, cookies or third-party requests. If that changes, update `privacy.html` too.

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
