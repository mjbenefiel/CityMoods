# City Mood · New York

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

- The job downloads only `complaint_type`, `latitude`, `longitude`. Never addresses, streets, BBL, ZIP or request IDs.
- Coordinates are used once to find the neighborhood, then dropped. Only neighborhood totals are published.
- Neighborhood counts under 3 are left out.
- Complaint types about people (homelessness, panhandling, police matters…) are listed in `SENSITIVE` in `moods.py`. They count toward "everything else" and are never named or put in the headline.
- `assert_no_pii` in `build.py` stops the build if anything address- or coordinate-like reaches the output.
- The site has no analytics, cookies or third-party requests. If that changes, update `privacy.html` too.

## Run it locally

```
python3 pipeline/build.py --no-claude        # builds the latest complete day
python3 -m http.server 8001 --directory docs  # then open http://localhost:8001
```

On this Mac, Python needs `SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")` set.

NYC publishes each day's 311 data the next morning, so the site always shows yesterday (or the day before, early in the morning).

## The daily headline

With an `ANTHROPIC_API_KEY` set, Claude writes the headline, blurb and one line per borough from the totals only (no record-level data is ever sent). Without a key, a plain rule-based headline is used. Model: `claude-opus-5-5`, override with `CITYMOOD_MODEL`. Roughly a couple of cents a day.

## Going live

1. Create a GitHub repo and push.
2. Settings → Pages: deploy from branch `main`, folder `/docs`.
3. Optional: add the repository secret `ANTHROPIC_API_KEY` for the Claude headline.
4. Actions → Daily mood → Run workflow once to check it.

Data: NYC Open Data (311 Service Requests; 2020 Neighborhood Tabulation Areas). Weather: Open-Meteo.
