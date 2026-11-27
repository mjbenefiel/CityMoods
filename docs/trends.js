// Trends page: a year of 311 counts by neighborhood (Chicago for now), from data/<city>/trends.json.
// State lives in the URL (?type=rats&days=90&per=1&compare=24,8) so any view can be shared.
(function () {
  const CITY = "chicago";
  const SVGNS = "http://www.w3.org/2000/svg";
  const RANGE_LABELS = { 7: "7 days", 30: "30 days", 90: "90 days", 180: "6 months", 365: "1 year" };
  const RANGE_PHRASE = { 7: "past 7 days", 30: "past 30 days", 90: "past 90 days", 180: "past 6 months", 365: "past year" };
  const EMPTY = "#2A2E36", HIDDEN = "#1E2128";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const fmt = (n) => n.toLocaleString("en-US");
  const day = (iso, yr) => new Date(iso + "T12:00:00").toLocaleDateString("en-US", yr ? { month: "short", year: "numeric" } : { month: "short", day: "numeric" });
  const fmtRate = (r) => (r >= 10 ? r.toFixed(0) : r >= 1 ? r.toFixed(1) : r.toFixed(2));

  // Names people actually use, mapped to Chicago's 77 official community areas (what the city's data uses).
  const ALIASES = {
    "Wicker Park": ["West Town"], "Ukrainian Village": ["West Town"], "East Village": ["West Town"],
    "Noble Square": ["West Town"], "River West": ["West Town"], "Bucktown": ["Logan Square"],
    "Palmer Square": ["Logan Square"], "Wrigleyville": ["Lake View"], "Boystown": ["Lake View"],
    "Northalsted": ["Lake View"], "Lakeview": ["Lake View"], "Roscoe Village": ["North Center"],
    "Ravenswood": ["Lincoln Square"], "Andersonville": ["Edgewater"], "Old Town": ["Near North Side"],
    "Streeterville": ["Near North Side"], "River North": ["Near North Side"], "Gold Coast": ["Near North Side"],
    "Magnificent Mile": ["Near North Side"], "West Loop": ["Near West Side"], "Greektown": ["Near West Side"],
    "Little Italy": ["Near West Side"], "University Village": ["Near West Side"], "Tri-Taylor": ["Near West Side"],
    "Illinois Medical District": ["Near West Side"], "South Loop": ["The Loop", "Near South Side"],
    "Printer's Row": ["The Loop"], "Prairie District": ["Near South Side"], "Pilsen": ["Lower West Side"],
    "Little Village": ["South Lawndale"], "La Villita": ["South Lawndale"], "Chinatown": ["Armour Square"],
    "Bronzeville": ["Douglas", "Grand Boulevard"], "Back of the Yards": ["New City"], "Canaryville": ["New City"],
    "Garfield Park": ["East Garfield Park", "West Garfield Park"], "Lawndale": ["North Lawndale"],
    "Jackson Park Highlands": ["South Shore"], "Mayfair": ["Albany Park"], "Ravenswood Manor": ["Albany Park"],
    "Sauganash": ["Forest Glen"], "Edgebrook": ["Forest Glen"], "Galewood": ["Austin"], "Buena Park": ["Uptown"],
    "Sheridan Park": ["Uptown"], "West Rogers Park": ["West Ridge"], "Old Irving Park": ["Irving Park"],
    "Six Corners": ["Portage Park"], "Marquette Park": ["Chicago Lawn"], "Pill Hill": ["Calumet Heights"],
    "Gresham": ["Auburn Gresham"], "Wrightwood": ["Ashburn"], "Loop": ["The Loop"], "Downtown": ["The Loop"],
  };
  let T, MOODS, GEO, CL = null, series = null, seriesLoading = null;   // CL: time to close (close.json)
  const render_ = () => render();
  const S = { sel: null, days: 90, per: false, slow: false, compare: [], showAll: false, hood: null, adv: null };
  const paths = {};

  async function getJSON(url) {
    const r = await fetch(url, { cache: "no-cache" });
    if (!r.ok) throw new Error(url + " " + r.status);
    return r.json();
  }

  // ------------------------------------------------------------ data helpers
  // The current selection is {kind: "type", i} or {kind: "mood", id}.
  function counts(sel = S.sel, days = S.days) {
    return sel.kind === "type" ? T.counts[days][sel.i] : (T.moods[days][sel.id] || T.areas.map(() => null));
  }
  function cityTotal(sel = S.sel, days = S.days) {
    if (sel.kind === "type") return T.citywide[days][sel.i];
    return counts(sel, days).reduce((a, b) => a + (b || 0), 0);
  }
  const rate = (n, a) => (n == null || !a.pop ? null : (n / a.pop) * 1000);
  function values() {
    const c = counts();
    if (S.slow) return T.areas.map((a, k) => {   // share that took over a week to close (or is still open)
      const cell = slowOK() ? CL.areas[S.sel.i][k] : null;
      return cell ? 100 - cell[0] : null;
    });
    return T.areas.map((a, k) => (S.per ? rate(c[k], a) : c[k]));
  }
  const slowOK = () => !!(CL && S.sel.kind === "type" && CL.types[S.sel.i]);
  // Speed is per request type, so "Time to close" on a whole mood switches to that mood's most common type.
  function slowFromMood() {
    if (!CL || S.sel.kind !== "mood") return null;
    const best = T.types.map((t, i) => ({ t, i, c: CL.types[i] })).filter((x) => x.t.mood === S.sel.id && x.c).sort((a, b) => b.c.n - a.c.n)[0];
    if (!best) return null;
    const from = selLabel();
    S.sel = { kind: "type", i: best.i };
    return `Time to close is measured per request type, so the map switched from ${esc(from)} to <b>${esc(best.t.label)}</b>, the most common one. Pick another in "Request type."`;
  }
  const STEP_WORDS = { 1: "within a day", 3: "within 3 days", 7: "within a week", 14: "within 2 weeks", 30: "within a month", 90: "within 3 months" };
  const STEP_SHORT = { 1: "1 day", 3: "3 days", 7: "1 week", 14: "2 weeks", 30: "1 month", 90: "3 months" };
  const usually = (c) => (c.typ ? `usually closed ${STEP_WORDS[c.typ]}` : "usually takes over 3 months");
  const fullDay = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const closeDates = () => `${fullDay(CL.window.start)} – ${fullDay(CL.window.end)}`;
  const asOf = () => day(CL.updated);       // open/closed status is checked fresh each night
  const closeWindow = () => `a full year of requests (${closeDates()}), ending a month ago so each had time to be closed, with their status as of ${asOf()}`;
  function selLabel(sel = S.sel) {
    if (sel.kind === "type") return T.types[sel.i].label;
    const m = MOODS[sel.id];
    return m ? `${m.label} (all)` : sel.id;
  }
  function selColor(sel = S.sel) {
    const mood = sel.kind === "type" ? T.types[sel.i].mood : sel.id;
    return (MOODS[mood] && MOODS[mood].color) || "#E2557B";
  }
  function mix(a, b, t) {
    const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
    const [x, y] = [p(a), p(b)];
    return "#" + x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, "0")).join("");
  }

  // ------------------------------------------------------------ map
  function drawMap(geo) {
    const svg = $("t-map");
    const k = Math.cos((41.84 * Math.PI) / 180);
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const polys = (g) => (g.type === "Polygon" ? [g.coordinates] : g.coordinates);
    geo.features.forEach((f) => polys(f.geometry).forEach((p) => p.forEach((ring) => ring.forEach(([lon, lat]) => {
      const x = lon * k, y = -lat;
      minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    }))));
    const W = 600, pad = 10, s = (W - pad * 2) / (maxX - minX), H = Math.round((maxY - minY) * s + pad * 2);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const pt = ([lon, lat]) => `${((lon * k - minX) * s + pad).toFixed(1)},${((-lat - minY) * s + pad).toFixed(1)}`;
    // The hover box goes away as soon as the pointer leaves the map, the page scrolls, Esc is pressed,
    // or someone taps anywhere else.
    svg.addEventListener("pointerleave", hideTip);
    svg.addEventListener("pointermove", (ev) => { if (ev.target === svg) hideTip(); });   // over the lake or a gap
    for (const t of ["scroll", "wheel", "touchmove"]) window.addEventListener(t, hideTip, { passive: true });
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") hideTip(); });
    // Tapping anywhere but a neighborhood closes the box, including tapping the box itself (or its ×).
    document.addEventListener("pointerdown", (ev) => { if (!ev.target.closest || !ev.target.closest("#t-map path")) hideTip(); });
    geo.features.forEach((f) => {
      const el = document.createElementNS(SVGNS, "path");
      el.setAttribute("d", polys(f.geometry).map((p) => p.map((r) => "M" + r.map(pt).join("L") + "Z").join("")).join(""));
      el.addEventListener("pointermove", (ev) => { if (ev.pointerType === "mouse") tip(f.id, ev); });
      el.addEventListener("click", (ev) => {
        // Phones: a tap adds the neighborhood to Compare (a second tap removes it) and says so in the box.
        const touch = ev.pointerType ? ev.pointerType !== "mouse" : !matchMedia("(hover: hover)").matches;
        toggleCompare(f.id);
        tip(f.id, ev, touch ? (S.compare.includes(f.id) ? "added" : "removed") : null);
      });
      svg.append(el);
      paths[f.id] = el;
    });
  }

  function paintMap() {
    const v = values();
    const known = v.filter((x) => x != null).sort((a, b) => a - b);
    const color = selColor();
    // Five shades, split at quantiles so each shade holds about the same number of neighborhoods.
    const breaks = [0.2, 0.4, 0.6, 0.8].map((q) => known[Math.floor(q * (known.length - 1))]);
    const shade = (x) => {
      if (x == null) return HIDDEN;
      const b = breaks.filter((br) => x > br).length;
      return mix(EMPTY, color, 0.18 + b * 0.2);
    };
    T.areas.forEach((a, k) => {
      const el = paths[a.id];
      if (!el) return;
      el.setAttribute("fill", shade(v[k]));
      el.classList.toggle("picked", S.compare.includes(a.id));
    });
    const lo = known[0], hi = known[known.length - 1];
    const f = (x) => (x == null ? "" : S.slow ? `${Math.round(x)}%` : S.per ? fmtRate(x) : fmt(Math.round(x)));
    $("t-legend").innerHTML = known.length
      ? `<span>${f(lo)}</span><span class="ramp">${[0, 1, 2, 3, 4].map((b) => `<i style="background:${mix(EMPTY, color, 0.18 + b * 0.2)}"></i>`).join("")}</span>` +
        `<span>${f(hi)}${S.slow ? " took over a week" : S.per ? " per 1,000" : ""}</span>` +
        `<span class="hid"><i style="background:${HIDDEN}"></i>${S.slow ? `under ${CL ? CL.min_n : 20} requests` : "under 3"}</span>`
      : `<span>${S.slow && !slowOK() ? "Pick a single request type to see how fast it gets closed." : "No neighborhood has 3 or more reports in this range."}</span>`;
  }

  let tipTimer;
  function hideTip() { clearTimeout(tipTimer); $("t-tip").hidden = true; }

  function tip(id, ev, status) {
    const k = T.areas.findIndex((a) => a.id === id);
    if (k < 0) return;
    const a = T.areas[k], n = counts()[k], tot = cityTotal();
    const r = rate(n, a);
    const box = $("t-tip"), host = box.parentElement.getBoundingClientRect();
    const slowCell = S.slow && slowOK() ? CL.areas[S.sel.i][k] : null;
    box.innerHTML = `<b>${esc(a.name)}</b><span class="t-side">${esc(a.side)}</span>` +
      (S.slow ? (slowCell
        ? `<span>${slowCell[0]}% closed within a week · city ${CL.types[S.sel.i].wk}%</span>` + (slowCell[1] ? `<span>${slowCell[1]}% still open as of ${asOf()}</span>` : "")
        : `<span>Too few requests to say</span>`) :
      n == null ? `<span>Under 3 reports</span>` :
        `<span>${fmt(n)} report${n === 1 ? "" : "s"}${tot ? ` · ${((n / tot) * 100).toFixed(1)}% of the city` : ""}</span>` +
        (r != null ? `<span>${fmtRate(r)} per 1,000 residents</span>` : "")) +
      (status ? `<span class="t-status">${status === "added" ? "✓ Added to Compare below. Tap again to remove." : "Removed from Compare."}</span>` +
        `<button type="button" class="t-close" aria-label="Close">×</button>` : "");
    box.classList.toggle("touch", !!status);
    box.hidden = false;
    clearTimeout(tipTimer);
    if (status === "removed") tipTimer = setTimeout(hideTip, 1800);
    if (status) {                  // phones: park the box in the map's top corner instead of under the finger
      box.style.left = "8px";
      box.style.top = "8px";
      return;
    }
    const x = Math.min(ev.clientX - host.left + 14, host.width - box.offsetWidth - 8);
    const y = Math.max(ev.clientY - host.top - box.offsetHeight - 10, 8);
    box.style.left = `${Math.max(8, x)}px`;
    box.style.top = `${y}px`;
  }

  // ------------------------------------------------------------ list
  function renderList() {
    const v = values(), c = counts();
    const rows = T.areas.map((a, k) => ({ a, v: v[k], n: c[k] }));
    const known = rows.filter((r) => r.v != null).sort((x, y) => y.v - x.v);
    const hidden = rows.filter((r) => r.v == null).sort((x, y) => x.a.name.localeCompare(y.a.name));
    const max = known.length ? known[0].v : 1;
    const shown = S.showAll ? [...known, ...hidden] : known.slice(0, 10);
    $("t-list-title").textContent = S.slow
      ? `${selLabel()}: longest waits`
      : `${selLabel()}: most reports${S.per ? " per 1,000 residents" : ""}, ${RANGE_PHRASE[S.days]}`;
    $("t-hint").textContent = S.slow
      ? (slowOK() ? "% of requests that took over a week or are still open · tap one to compare"
        : "Pick a single request type to see how fast the city closes it.")
      : S.per
      ? "Tap a neighborhood to compare it (up to 3). Small neighborhoods can jump around per 1,000."
      : "Tap a neighborhood to compare it (up to 3).";
    $("t-rank").innerHTML = shown.map((r) => {
      const on = S.compare.includes(r.a.id);
      const val = r.v == null ? (S.slow ? "too few" : "under 3") : S.slow ? `${Math.round(r.v)}%` : S.per ? fmtRate(r.v) : fmt(r.v);
      const w = r.v == null ? 0 : Math.max(2, (r.v / max) * 100);
      return `<li><button type="button" data-id="${r.a.id}" aria-pressed="${on}">` +
        `<span class="nm">${esc(r.a.name)}</span><span class="val">${val}</span>` +
        `<span class="bar"><i style="width:${w.toFixed(1)}%;background:${selColor()}"></i></span></button></li>`;
    }).join("");
    $("t-more").textContent = S.showAll ? "Show top 10" : "Show all 77";
    if (S.slow) {
      const c = slowOK() ? CL.types[S.sel.i] : null;
      $("t-total").innerHTML = `<b>${esc(selLabel())}</b> · ` + (c
        ? `${usually(c)} · ${c.wk}% within a week citywide${c.open ? ` · ${c.open}% still open as of ${asOf()}` : ""}`
        : "pick a single request type");
      return;
    }
    $("t-more").hidden = known.length <= 10 && !hidden.length;
    const tot = cityTotal();
    $("t-total").innerHTML = `<b>${esc(selLabel())}</b> · ${RANGE_PHRASE[S.days]} · ` +
      (tot ? `${fmt(tot)} reports citywide` : "fewer than 3 citywide");
  }

  // ------------------------------------------------------------ compare
  function toggleCompare(id) {
    const i = S.compare.indexOf(id);
    if (i >= 0) S.compare.splice(i, 1);
    else { S.compare.push(id); if (S.compare.length > 3) S.compare.shift(); }
    render();
  }

  function spark(vals, color) {
    const W = 220, H = 44, n = vals.length, max = Math.max(1, ...vals.map((v) => v || 0));
    const pts = vals.map((v, i) => `${((i / (n - 1)) * W).toFixed(1)},${(H - 4 - ((v || 0) / max) * (H - 8)).toFixed(1)}`);
    return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">` +
      `<polyline points="${pts.join(" ")}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function renderCompare() {
    const box = $("t-compare");
    box.hidden = !S.compare.length;
    if (!S.compare.length) return;
    const color = selColor();
    if (S.sel.kind === "type" && !series && !seriesLoading) {
      seriesLoading = getJSON(`/data/${CITY}/trends-series.json`).then((d) => { series = d; renderCompare(); renderHood(); renderAdvisor(); }).catch(() => {});
    }
    $("t-cards").innerHTML = S.compare.map((id) => {
      const k = T.areas.findIndex((a) => a.id === id), a = T.areas[k];
      const n = counts()[k], r = rate(n, a);
      // This neighborhood's top request types in the chosen range
      const top = T.types.map((t, i) => ({ t, n: T.counts[S.days][i][k] })).filter((x) => x.n != null)
        .sort((x, y) => y.n - x.n).slice(0, 5);
      let trend = "";
      if (S.sel.kind === "type") {
        if (series) {
          const vals = series.types[S.sel.i][k], p = series.periods;
          trend = `<div class="t-trend"><span class="lbl">${esc(selLabel())}, every 30 days for a year</span>${spark(vals, color)}` +
            `<span class="ends"><span>${day(p[0].start, true)}</span><span>${day(p[p.length - 1].end)}</span></span></div>`;
        } else trend = `<div class="t-trend"><span class="lbl">Loading trend…</span></div>`;
      } else trend = `<div class="t-trend"><span class="lbl">Pick a single request type to see its trend line.</span></div>`;
      return `<article class="t-card"><header><h3>${esc(a.name)}</h3><button type="button" class="x" data-id="${id}" aria-label="Remove ${esc(a.name)}">×</button></header>` +
        `<p class="t-side">${esc(a.side)}${a.pop ? ` · ${fmt(a.pop)} residents` : ""}</p>` +
        `<button type="button" class="t-profile${S.hood === id ? " on" : ""}" data-hood="${id}" aria-pressed="${S.hood === id}">` +
        `${S.hood === id ? "Profile open above ↑" : "View full profile →"}</button>` +
        `<p class="big"><b>${n == null ? "Under 3" : fmt(n)}</b> report${n === 1 ? "" : "s"}` +
        (r != null ? ` · <b>${fmtRate(r)}</b> per 1,000` : "") + `</p>` + trend +
        `<p class="lbl">Top requests, ${RANGE_PHRASE[S.days]}</p><ol class="t-top">` +
        top.map((x) => `<li><span>${esc(x.t.label)}</span><span>${fmt(x.n)}${a.pop ? ` <small>(${fmtRate((x.n / a.pop) * 1000)}/1k)</small>` : ""}</span></li>`).join("") +
        `</ol></article>`;
    }).join("");
  }

  // ------------------------------------------------------------ advisors
  // One dashboard per mood, each run by a made-up city official. The joke is on the bureaucracy; the numbers are
  // the city's own 311 data for the past year, in 13 thirty-day stretches.
  const ADVISORS = {
    critters: { title: "Rat Czar", blurb: "Rats, strays, bees and other uninvited guests." },
    streets: { title: "Pothole Inspector General", blurb: "Potholes, dark streetlights and blinking signals." },
    trash: { title: "Sanitation Marshal", blurb: "Graffiti, busted carts, dumping and missed pickups." },
    water: { title: "Undersecretary of Drips", blurb: "Water on the street, leaks, sewers and wet basements." },
    trees: { title: "Keeper of the Canopy", blurb: "Fallen limbs, trims, and the trims the city stopped taking." },
    parking: { title: "Chief Justice of Parking Wars", blurb: "Abandoned cars, parking disputes and rogue e-scooters." },
    housing: { title: "Building Code Oracle", blurb: "Building, plumbing and permit violations." },
  };
  const advMoods = () => Object.keys(ADVISORS).filter((m) => MOODS[m] && T.moods[365][m]);

  function renderCouncil() {
    $("t-council-list").innerHTML = advMoods().map((m) =>
      `<button type="button" class="adv-chip${S.adv === m ? " on" : ""}" data-adv="${m}" aria-pressed="${S.adv === m}" style="--mc:${MOODS[m].color}">` +
      `<span class="adv-e">${MOODS[m].emoji}</span><span><b>${esc(ADVISORS[m].title)}</b><small>${esc(MOODS[m].label)}</small></span></button>`).join("");
  }

  function cityPeriods(idx) {        // citywide count per 30-day stretch for a set of request types
    return series.periods.map((_, j) => idx.reduce((s_, i) => s_ + series.types[i].reduce((t, area) => t + (area[j] || 0), 0), 0));
  }

  function bars(vals, color, periods) {
    const W = 520, H = 120, n = vals.length, gap = 4, bw = (W - gap * (n - 1)) / n, max = Math.max(1, ...vals);
    const rects = vals.map((v, i) => {
      const h = Math.max(2, (v / max) * (H - 18));
      return `<rect x="${(i * (bw + gap)).toFixed(1)}" y="${(H - h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="${color}"` +
        `${i === n - 1 ? "" : ' opacity=".55"'}><title>${day(periods[i].start)}–${day(periods[i].end)}: ${fmt(v)}</title></rect>`;
    }).join("");
    return `<svg class="adv-bars" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Requests every 30 days for the past year">${rects}</svg>` +
      `<span class="ends"><span>${day(periods[0].start, true)}</span><span>Latest 30 days</span></span>`;
  }

  function renderAdvisor() {
    const box = $("t-adv");
    const m = S.adv;
    if (!m || !ADVISORS[m] || !MOODS[m]) { box.hidden = true; box.innerHTML = ""; return; }
    const A_ = ADVISORS[m], color = MOODS[m].color;
    const idx = T.types.map((t, i) => (t.mood === m ? i : -1)).filter((i) => i >= 0);
    const yearN = idx.reduce((s_, i) => s_ + (T.citywide[365][i] || 0), 0);
    const monthN = idx.reduce((s_, i) => s_ + (T.citywide[30][i] || 0), 0);
    const usual = (yearN / 365) * 30, vsUsual = usual ? monthN / usual : 1;
    const types = idx.map((i) => ({ i, t: T.types[i], n: T.citywide[365][i] || 0 })).filter((x) => x.n).sort((a, b) => b.n - a.n);
    const maxT = types.length ? types[0].n : 1;
    if (!series && !seriesLoading)
      seriesLoading = getJSON(`/data/${CITY}/trends-series.json`).then((d) => { series = d; renderCompare(); renderHood(); renderAdvisor(); }).catch(() => {});
    let chart = `<p class="h-none">Loading the year…</p>`, note = "", peak = "";
    if (series) {
      const vals = cityPeriods(idx), P = series.periods;
      chart = bars(vals, color, P);
      const pk = vals.indexOf(Math.max(...vals));
      peak = `<div class="adv-stat"><span>Busiest stretch</span><b>${day(P[pk].start)}–${day(P[pk].end)}</b><small>${fmt(vals[pk])} requests</small></div>`;
      // The advisor's note: whichever request type is running furthest above its usual pace in the latest 30 days.
      const risers = idx.map((i) => {
        const v = cityPeriods([i]), last = v[v.length - 1], avg = v.reduce((a, b) => a + b, 0) / v.length;
        return { t: T.types[i], last, x: avg ? last / avg : 0 };
      }).filter((r) => r.last >= 50).sort((a, b) => b.x - a.x);
      const hot = risers[0];
      note = hot && hot.x >= 1.3
        ? `Running hot: <b>${esc(hot.t.label)}</b> is at ${hot.x.toFixed(1)}× its usual 30-day pace (${fmt(hot.last)} in the latest 30 days).`
        : vsUsual < 0.8
          ? `Quiet stretch: ${esc(MOODS[m].label.toLowerCase())} requests are running ${Math.round((1 - vsUsual) * 100)}% below their usual pace.`
          : `Steady: nothing in this department is running far above its usual pace right now.`;
    }
    box.style.setProperty("--mc", color);
    box.innerHTML =
      `<header class="h-head"><div><p class="h-kick">Advisor · ${esc(MOODS[m].label)}</p>` +
      `<h2><span class="adv-e">${MOODS[m].emoji}</span> ${esc(A_.title)}</h2><p class="t-side">${esc(A_.blurb)}</p></div>` +
      `<button type="button" class="x" data-close aria-label="Close the ${esc(A_.title)}">×</button></header>` +
      (note ? `<p class="adv-note">📋 <span>${note}</span></p>` : "") +
      `<div class="adv-stats">` +
      `<div class="adv-stat"><span>Past year</span><b>${fmt(yearN)}</b><small>requests citywide</small></div>` +
      `<div class="adv-stat"><span>Latest 30 days</span><b>${fmt(monthN)}</b><small>${vsUsual >= 1 ? "+" : "−"}${Math.abs(Math.round((vsUsual - 1) * 100))}% vs a usual 30 days</small></div>` +
      peak + `</div>` +
      `<div class="h-grid">` +
      `<div class="h-col"><h3>Every 30 days, past year</h3><div class="t-trend">${chart}</div>` +
      closeTable(idx) +
      `<h3>Where it comes up</h3><p class="adv-map">The <a href="#t-map">map above</a> is now shaded by ${esc(MOODS[m].label.toLowerCase())} requests. ` +
      `Tap any neighborhood to compare it, or search for yours to see its profile.</p></div>` +
      `<div class="h-col"><h3>What people ask for <small>(tap one to map it)</small></h3><ul class="adv-types">${types.map((x) =>
        `<li><button type="button" data-type="${x.i}"${S.sel.kind === "type" && S.sel.i === x.i ? ' class="on"' : ""}>` +
        `<span class="nm">${esc(x.t.label)}</span><span class="val">${fmt(x.n)}</span>` +
        `<span class="bar"><i style="width:${Math.max(2, (x.n / maxT) * 100).toFixed(1)}%;background:${color}"></i></span></button></li>`).join("")}</ul></div>` +
      `</div>` +
      `<p class="h-foot">From Chicago's 311 open data for the past year, in 30-day stretches. The advisors are made up; the numbers are the city's. ` +
      `"Usual pace" is the average 30 days over the past year.</p>`;
    box.hidden = false;
  }

  // "How fast the city closes these": the advisor's own report card, from close.json.
  function closeTable(idx) {
    if (!CL) return "";
    const rows = idx.map((i) => ({ t: T.types[i], i, c: CL.types[i] })).filter((x) => x.c).sort((a, b) => b.c.n - a.c.n);
    if (!rows.length) return "";
    const slowest = rows.filter((x) => x.c.n >= 500).sort((a, b) => a.c.wk - b.c.wk)[0];
    return `<h3>How fast the city closes these</h3>` +
      (slowest && slowest.c.wk < 50 ? `<p class="adv-slow">Slowest: <b>${esc(slowest.t.label)}</b>, ${usually(slowest.c)} (${slowest.c.wk}% within a week).</p>` : "") +
      `<table class="adv-close"><thead><tr><th>Request</th><th>Usually within</th><th>In a week</th><th>Open as of ${asOf()}</th></tr></thead><tbody>` +
      rows.map((x) => `<tr><td><button type="button" class="t-linkbtn" data-slow="${x.i}">${esc(x.t.label)}</button></td>` +
        `<td>${x.c.typ ? STEP_SHORT[x.c.typ] : "3+ months"}</td><td>${x.c.wk}%</td><td>${x.c.open}%</td></tr>`).join("") +
      `</tbody></table><p class="adv-fine">For ${closeWindow()}. Tap one to map how fast it gets closed in each neighborhood.</p>`;
  }

  function openAdvisor(m) {
    S.adv = m;
    S.sel = { kind: "mood", id: m };       // the map and list follow the advisor's mood
    S.slow = false;
    if (!series && !seriesLoading)
      seriesLoading = getJSON(`/data/${CITY}/trends-series.json`).then((d) => { series = d; renderCompare(); renderHood(); renderAdvisor(); }).catch(() => {});
    render();
    $("t-adv").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }

  // ------------------------------------------------------------ neighborhood view
  // A profile built only from the past year of 311 requests. The "311 signature" is the mood that makes up the
  // biggest share of this neighborhood's requests compared with the city's share (at least 1.3×, and 100+ requests).
  // Standouts are request types at least 1.5× the city's share, with 30+ requests and at least 0.5% of the neighborhood's
  // requests (so a handful of oddities don't crowd out things people recognize). No nicknames, no rankings.
  const SIG_MIN_X = 1.3, SIG_MIN_N = 100, STAND_MIN_X = 1.5, STAND_MIN_N = 30;
  function profile(k) {
    const C = T.counts[365], Mo = T.moods[365];
    const moods = Object.keys(Mo).filter((m) => m !== "other" && MOODS[m]);
    const v = (x) => x || 0;
    const cityM = Object.fromEntries(moods.map((m) => [m, Mo[m].reduce((s, x) => s + v(x), 0)]));
    const cityMT = Object.values(cityM).reduce((s, x) => s + x, 0);
    const nbM = Object.fromEntries(moods.map((m) => [m, v(Mo[m][k])]));
    const nbMT = Object.values(nbM).reduce((s, x) => s + x, 0);
    const mix = moods.map((m) => ({ m, n: nbM[m], share: nbMT ? nbM[m] / nbMT : 0, city: cityMT ? cityM[m] / cityMT : 0 }))
      .map((x) => ({ ...x, x: x.city ? x.share / x.city : 0 })).sort((a, b) => b.share - a.share);
    const sigC = mix.filter((x) => x.n >= SIG_MIN_N && x.x >= SIG_MIN_X).sort((a, b) => b.x - a.x)[0] || null;
    const cityT = T.types.map((_, i) => C[i].reduce((s, x) => s + v(x), 0)), cityTT = cityT.reduce((s, x) => s + x, 0);
    const nbTT = T.types.reduce((s, _, i) => s + v(C[i][k]), 0);
    const standouts = T.types.map((t, i) => ({ t, n: v(C[i][k]), x: nbTT && cityT[i] ? (v(C[i][k]) / nbTT) / (cityT[i] / cityTT) : 0 }))
      .filter((s_) => s_.n >= Math.max(STAND_MIN_N, nbTT * 0.005) && s_.x >= STAND_MIN_X).sort((a, b) => b.x - a.x).slice(0, 3);
    const top = T.types.map((t, i) => ({ t, i, n: C[i][k] })).filter((x) => x.n != null).sort((a, b) => b.n - a.n).slice(0, 5);
    return { total: nbTT, mix, sig: sigC, standouts, top };
  }

  function renderHood() {
    const box = $("t-hood");
    const k = S.hood ? T.areas.findIndex((a) => a.id === S.hood) : -1;
    if (k < 0) { box.hidden = true; box.innerHTML = ""; return; }
    const a = T.areas[k], P = profile(k);
    if (!series && !seriesLoading)
      seriesLoading = getJSON(`/data/${CITY}/trends-series.json`).then((d) => { series = d; renderCompare(); renderHood(); renderAdvisor(); }).catch(() => {});
    const yr = T.windows.find((w) => w.days === 365);
    const pct = (x) => `${(x * 100).toFixed(x < 0.1 ? 1 : 0)}%`;
    const sig = P.sig
      ? `<div class="h-badge" style="--mc:${MOODS[P.sig.m].color}"><span class="h-k">311 signature</span>` +
        `<b>${MOODS[P.sig.m].emoji} ${esc(MOODS[P.sig.m].label)}</b>` +
        `<span class="h-why">${pct(P.sig.share)} of its requests are about ${esc(MOODS[P.sig.m].label.toLowerCase())}, ${P.sig.x.toFixed(1)}× the city's share.</span></div>`
      : `<div class="h-badge"><span class="h-k">311 signature</span><b>🧭 A bit of everything</b>` +
        `<span class="h-why">No single mood stands out: its mix of requests is close to the city's.</span></div>`;
    const stand = P.standouts.length
      ? `<ul class="h-stand">${P.standouts.map((x) => `<li><b>${esc(x.t.label)}</b>: ${fmt(x.n)} this year, ${x.x.toFixed(1)}× the city's share</li>`).join("")}</ul>`
      : `<p class="h-none">No single request type stands out by much.</p>`;
    const maxShare = Math.max(...P.mix.map((x) => Math.max(x.share, x.city)), 0.01);
    const mix = `<ul class="h-mix">${P.mix.filter((x) => x.share >= 0.005 || x.city >= 0.02).map((x) =>
      `<li><span class="h-ml">${MOODS[x.m].emoji} ${esc(MOODS[x.m].label)}</span>` +
      `<span class="h-bars"><i class="h-me" style="width:${((x.share / maxShare) * 100).toFixed(1)}%;background:${MOODS[x.m].color}"></i>` +
      `<i class="h-city" style="width:${((x.city / maxShare) * 100).toFixed(1)}%"></i></span>` +
      `<span class="h-mv">${pct(x.share)} <small>city ${pct(x.city)}</small></span></li>`).join("")}</ul>`;
    let trend = `<p class="h-none">Loading the year's trend…</p>`;
    if (series) {
      const p = series.periods, vals = p.map((_, j) => series.types.reduce((s_, ty) => s_ + (ty[k][j] || 0), 0));
      trend = `${spark(vals, "#E2557B")}<span class="ends"><span>${day(p[0].start, true)}</span><span>${day(p[p.length - 1].end)}</span></span>`;
    }
    const top = `<ol class="t-top">${P.top.map((x) => `<li><span>${esc(x.t.label)}</span><span>${fmt(x.n)}${a.pop ? ` <small>(${fmtRate((x.n / a.pop) * 1000)}/1k)</small>` : ""}</span></li>`).join("")}</ol>`;
    let speed = "";
    if (CL) {
      const rowsC = P.top.map((x) => ({ x, here: CL.areas[x.i] && CL.areas[x.i][k], city: CL.types[x.i] })).filter((r) => r.here && r.city);
      if (rowsC.length) speed = `<h3>How fast the city closes them here</h3><ul class="h-speed">${rowsC.map((r) =>
        `<li><span>${esc(r.x.t.label)}</span><span><b>${r.here[0]}%</b> within a week <small>city ${r.city.wk}%</small></span></li>`).join("")}</ul>` +
        `<p class="adv-fine">For ${closeWindow()}.</p>`;
    }
    box.innerHTML =
      `<header class="h-head"><div><p class="h-kick">Neighborhood view · past year</p><h2>${esc(a.name)}</h2>` +
      `<p class="t-side">${esc(a.side)}${a.pop ? ` · ${fmt(a.pop)} residents` : ""} · ${fmt(P.total)} requests` +
      (a.pop ? ` · ${fmtRate((P.total / a.pop) * 1000)} per 1,000 residents` : "") + `</p></div>` +
      `<button type="button" class="x" data-close aria-label="Close the ${esc(a.name)} profile">×</button></header>` +
      `<div class="h-grid">` +
      `<div class="h-col">${sig}<h3>Stands out for</h3>${stand}<h3>Top requests</h3>${top}${speed}</div>` +
      `<div class="h-col"><h3>Mix of requests vs the city</h3>${mix}<h3>All requests, every 30 days</h3><div class="t-trend">${trend}</div></div>` +
      `</div>` +
      `<p class="h-foot">From Chicago's 311 open data, ${day(yr.start)}, ${yr.start.slice(0, 4)} to ${day(yr.end)}, ${yr.end.slice(0, 4)}. ` +
      `"311 signature" is the mood that's the biggest share of this neighborhood's requests compared with the city's share (at least ${SIG_MIN_X}×). ` +
      `It describes what people here ask the city for, not what the neighborhood is like. Counts under 3 are hidden. ` +
      `<button type="button" class="t-linkbtn" data-copy>Copy a link to this profile</button></p>`;
    box.hidden = false;
  }

  function openHood(id, scroll = true) {
    S.hood = id;
    render();
    if (scroll) $("t-hood").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }

  // ------------------------------------------------------------ find a neighborhood
  function setupFind() {
    const input = $("t-find"), box = $("t-find-results");
    const norm = (x) => x.toLowerCase().replace(/['’.]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
    const byName = Object.fromEntries(T.areas.map((a) => [a.name, a]));
    // One entry per community area, plus one per common name (pointing at its community area or areas).
    const entries = [
      ...T.areas.map((a) => ({ label: a.name, note: a.side, ids: [a.id] })),
      ...Object.entries(ALIASES).map(([alias, names]) => ({ label: alias, alias: true, note: `part of ${names.join(" and ")}`,
        names, ids: names.map((n) => byName[n] && byName[n].id).filter(Boolean) })).filter((e) => e.ids.length),
    ].map((e) => ({ ...e, key: norm(e.label) }));
    let matches = [], active = 0;

    const render = () => {
      box.hidden = !matches.length;
      input.setAttribute("aria-expanded", String(!!matches.length));
      box.innerHTML = matches.map((m, k) => `<li role="option" data-k="${k}" class="${k === active ? "on" : ""}" aria-selected="${k === active}">` +
        `<b>${esc(m.label)}</b><span>${esc(m.note)}</span></li>`).join("");
    };
    const search = () => {
      const q = norm(input.value);
      if (!q) { matches = []; render(); return; }
      const starts = entries.filter((e) => e.key.startsWith(q));
      const words = entries.filter((e) => !starts.includes(e) && e.key.split(" ").some((w) => w.startsWith(q)));
      const inside = entries.filter((e) => !starts.includes(e) && !words.includes(e) && e.key.includes(q));
      matches = [...starts, ...words, ...inside].slice(0, 7);
      // Anything that looks like a street address (or matches no name) can be looked up as an address.
      const raw = input.value.trim();
      if (raw.length >= 4 && (/^\d/.test(raw) || !matches.length))
        matches.push({ label: `Look up "${raw}"`, note: "as an address (via OpenStreetMap)", address: raw });
      active = 0;
      render();
    };
    const choose = (m) => {
      matches = []; render();
      input.value = "";        // never leave an address sitting in the box
      input.blur();
      if (m.address) return lookupAddress(m.address);
      const names = m.ids.map((id) => T.areas.find((a) => a.id === id).name);
      S.hood = m.ids[0];
      showAreas(m.ids, (m.alias ? `${esc(m.label)} is part of ${esc(names.join(" and "))}. ` : "") +
        `${esc(names[0])}'s <a href="#t-hood">profile</a> is below` +
        (names.length > 1 ? `, and both are in <a href="#t-compare">Compare</a>.` : `, and it's in <a href="#t-compare">Compare</a>.`));
    };
    input.addEventListener("input", search);
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" && matches.length) { active = (active + 1) % matches.length; render(); e.preventDefault(); }
      else if (e.key === "ArrowUp" && matches.length) { active = (active - 1 + matches.length) % matches.length; render(); e.preventDefault(); }
      else if (e.key === "Enter") { if (matches[active]) choose(matches[active]); e.preventDefault(); }
      else if (e.key === "Escape") { matches = []; render(); }
    });
    box.addEventListener("pointerdown", (e) => {
      const li = e.target.closest("li[data-k]");
      if (li) { e.preventDefault(); choose(matches[+li.dataset.k]); }
    });
    input.addEventListener("blur", () => setTimeout(() => { matches = []; render(); }, 120));
  }

  // Add neighborhoods to Compare, say so, and flash them on the map.
  function showAreas(ids, html) {
    hideTip();
    for (const id of ids) if (!S.compare.includes(id)) { S.compare.push(id); if (S.compare.length > 3) S.compare.shift(); }
    render_();
    say(html);
    for (const id of ids) {
      const el = paths[id];
      if (!el) continue;
      el.classList.remove("found"); void el.getBoundingClientRect(); el.classList.add("found");
      setTimeout(() => el.classList.remove("found"), 2400);
    }
    $("t-map").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" });
  }
  function say(html) { const n = $("t-found"); n.innerHTML = html; n.hidden = false; delete n.dataset.switch; }
  // Notes about a view switch ("the map switched to Rats…") go away on the next filter change; lookup results stay.
  function tell(html) { say(html); $("t-found").dataset.switch = "1"; }
  function hush() { const n = $("t-found"); if (n.dataset.switch) { n.hidden = true; n.innerHTML = ""; delete n.dataset.switch; } }

  // ------------------------------------------------------------ which neighborhood am I in?
  // Everything here happens in the visitor's browser. A location from "Use my location" never leaves the
  // device; a typed address goes only to OpenStreetMap's search (Nominatim) to turn it into a point. CityMoods
  // never receives, counts or stores either one, and neither ever goes in the page's link.
  const OTHER_CITIES = [   // rough bounding boxes [west, south, east, north], so we only load a city's map when needed
    { key: "nyc", name: "New York", box: [-74.27, 40.49, -73.69, 40.92] },
    { key: "la", name: "Los Angeles", box: [-118.67, 33.70, -118.15, 34.34] },
    { key: "sf", name: "San Francisco", box: [-122.52, 37.70, -122.35, 37.84] },
    { key: "boston", name: "Boston", box: [-71.20, 42.22, -70.98, 42.40] },
  ];
  const polysOf = (g) => (g.type === "Polygon" ? [g.coordinates] : g.coordinates);
  function inside(lon, lat, geom) {          // even-odd rule, so holes in a shape are handled too
    let hit = false;
    for (const poly of polysOf(geom)) for (const ring of poly)
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [xi, yi] = ring[i], [xj, yj] = ring[j];
        if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) hit = !hit;
      }
    return hit;
  }
  const miles = (lat1, lon1, lat2, lon2) => {
    const r = Math.PI / 180, a = Math.sin(((lat2 - lat1) * r) / 2) ** 2 +
      Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(((lon2 - lon1) * r) / 2) ** 2;
    return 3958.8 * 2 * Math.asin(Math.sqrt(a));
  };
  const fmtMi = (d) => (d < 10 ? d.toFixed(1) : fmt(Math.round(d)));
  const nameOf = (id) => (T.areas.find((a) => a.id === id) || {}).name;

  async function place(lon, lat, how, accuracy) {
    // how: "location" or "address". accuracy is in meters (location only).
    const rough = how === "location" && accuracy > 1000
      ? ` <span class="t-note">Your browser's location is approximate (within about ${fmtMi(accuracy / 1609)} miles), so this could be off. For an exact match, type your address.</span>` : "";
    const hit = GEO.features.find((f) => inside(lon, lat, f.geometry));
    if (hit) {
      const where = how === "location" ? "You're in" : "That address is in";
      S.hood = hit.id;
      return showAreas([hit.id], `${where} ${esc(nameOf(hit.id))}. Its <a href="#t-hood">profile</a> is below, and it's in <a href="#t-compare">Compare</a>.${rough}`);
    }
    // One of our other cities?
    for (const c of OTHER_CITIES) {
      const [w, s_, e, n] = c.box;
      if (lon < w || lon > e || lat < s_ || lat > n) continue;
      try {
        const g = await getJSON(`/data/${c.key}/neighborhoods.geojson`);
        const f = g.features.find((x) => inside(lon, lat, x.geometry));
        if (f) {
          const p = f.properties || {};
          const area = p.borough && p.borough !== p.name && p.borough !== c.name ? `${p.name}, ${p.borough}` : p.name;
          return say(`${how === "location" ? "You're in" : "That's in"} ${esc(area)}, ${esc(c.name)}. Trends are Chicago-only for now, ` +
            `but ${esc(c.name)} has its own daily map: <a href="/${c.key}/">see ${esc(c.name)} →</a>${rough}`);
        }
        // Inside the rough box but outside the city itself (a neighboring town, the water, an airport…)
        return say(`${how === "location" ? "You're" : "That's"} just outside ${esc(c.name)}. Trends are Chicago-only for now, ` +
          `but ${esc(c.name)} has its own daily map: <a href="/${c.key}/">see ${esc(c.name)} →</a>${rough}`);
      } catch (e) { /* fall through to the distance message */ }
    }
    // Near Chicago, or far away?
    let best = null;
    for (const f of GEO.features) for (const poly of polysOf(f.geometry)) for (const [x, y] of poly[0]) {
      const d = miles(lat, lon, y, x);
      if (!best || d < best.d) best = { d, id: f.id };
    }
    if (best && best.d <= 15) {
      const nm = esc(nameOf(best.id));
      say(`That's just outside Chicago. The closest neighborhood is ${nm}, about ${fmtMi(best.d)} miles away. ` +
        `<button type="button" class="t-linkbtn" data-add="${esc(best.id)}">Add ${nm} to Compare</button>${rough}`);
      return;
    }
    const far = miles(lat, lon, 41.8781, -87.6298);
    say(`${how === "location" ? "You're" : "That's"} about ${fmtMi(far)} miles from Chicago, and your city isn't on CityMoods yet. ` +
      `Want it? <a href="mailto:admin@citymoods311.com?subject=Add%20my%20city%3A%20">Ask us</a>.${rough}`);
  }

  async function lookupAddress(text) {
    // Assume Chicago unless the address already names a city or state (it has a comma, or mentions IL/Illinois/Chicago).
    const q = /,|\bchicago\b|\bil\b|\billinois\b/i.test(text) ? text : `${text}, Chicago, IL`;
    say("Looking up that address…");
    try {
      const url = "https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&countrycodes=us" +
        "&viewbox=-87.94,42.03,-87.52,41.64&q=" + encodeURIComponent(q);
      const r = await fetch(url, { headers: { "Accept-Language": "en" }, cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      const [res] = await r.json();
      if (!res) return say(`Couldn't find that address. Try adding the city, like "1600 W Division St, Chicago".`);
      place(+res.lon, +res.lat, "address");
    } catch (e) {
      say("The address search isn't answering right now. Try again in a minute, or pick a neighborhood by name.");
    }
  }

  function setupLocate() {
    const btn = $("t-locate");
    if (!btn) return;
    if (!("geolocation" in navigator)) { btn.hidden = true; return; }
    btn.hidden = false;
    btn.addEventListener("click", () => {
      say("Finding your location…");
      btn.disabled = true;
      navigator.geolocation.getCurrentPosition(
        (pos) => { btn.disabled = false; place(pos.coords.longitude, pos.coords.latitude, "location", pos.coords.accuracy); },
        (err) => {
          btn.disabled = false;
          say(err.code === 1 ? "Location is turned off for this site. You can type your address in the box instead."
            : "Couldn't get your location. You can type your address in the box instead.");
        },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
    });
    $("t-found").addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-add]");
      if (b) showAreas([b.dataset.add], `Added ${esc(nameOf(b.dataset.add))} to <a href="#t-compare">Compare</a>.`);
    });
  }

  // ------------------------------------------------------------ state + controls
  function render() {
    paintMap();
    renderList();
    renderCompare();
    renderHood();
    renderCouncil();
    renderAdvisor();
    $("t-type").value = S.sel.kind === "type" ? `t${S.sel.i}` : `m${S.sel.id}`;
    document.querySelectorAll("#t-range button").forEach((b) => b.setAttribute("aria-checked", String(+b.dataset.days === S.days)));
    const show = S.slow ? "2" : S.per ? "1" : "0";
    // In "Time to close" the time range doesn't apply: dim it and say which year the numbers cover.
    $("t-range").classList.toggle("is-fixed", S.slow);
    $("t-range-label").textContent = S.slow && CL ? `Time range · fixed: one full year, ${closeDates()}` : "Time range";
    document.querySelectorAll("#t-per button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.per === show)));
    const q = new URLSearchParams();
    q.set(S.sel.kind === "type" ? "type" : "mood", S.sel.kind === "type" ? slug(T.types[S.sel.i].label) : S.sel.id);
    q.set("days", S.days);
    if (S.per) q.set("per", "1");
    if (S.slow) q.set("show", "slow");
    if (S.compare.length) q.set("compare", S.compare.join(","));
    if (S.hood) q.set("hood", S.hood);
    if (S.adv) q.set("adv", S.adv);
    history.replaceState(null, "", `${location.pathname}?${q}`);
  }

  function readURL() {
    const q = new URLSearchParams(location.search);
    const ti = q.get("type") ? T.types.findIndex((t) => slug(t.label) === q.get("type")) : -1;
    const mood = q.get("mood");
    if (ti >= 0) S.sel = { kind: "type", i: ti };
    else if (mood && T.moods[90][mood]) S.sel = { kind: "mood", id: mood };
    else {
      const rats = T.types.findIndex((t) => t.label === "Rats");
      S.sel = { kind: "type", i: rats >= 0 ? rats : 0 };
    }
    const d = +q.get("days");
    if (RANGE_LABELS[d]) S.days = d;
    S.per = q.get("per") === "1";
    S.slow = q.get("show") === "slow" && !!CL;
    if (S.slow) { S.per = false; slowFromMood(); }
    const ids = new Set(T.areas.map((a) => a.id));
    S.compare = (q.get("compare") || "").split(",").filter((x) => ids.has(x)).slice(0, 3);
    S.hood = ids.has(q.get("hood")) ? q.get("hood") : null;
    S.adv = ADVISORS[q.get("adv")] && MOODS[q.get("adv")] && T.moods[365][q.get("adv")] ? q.get("adv") : null;
    if (S.adv && !q.get("type") && !q.get("mood")) S.sel = { kind: "mood", id: S.adv };
  }

  function setupControls() {
    const moods = Object.keys(T.moods[365]).filter((m) => MOODS[m] && m !== "other");
    const types = T.types.map((t, i) => ({ t, i })).sort((a, b) => a.t.label.localeCompare(b.t.label));
    $("t-type").innerHTML =
      `<optgroup label="Moods (all request types in each)">${moods.map((m) => `<option value="m${m}">${MOODS[m].emoji} ${esc(MOODS[m].label)} (all)</option>`).join("")}</optgroup>` +
      `<optgroup label="Request types">${types.map(({ t, i }) => `<option value="t${i}">${esc(t.label)}</option>`).join("")}</optgroup>`;
    $("t-type").addEventListener("change", (ev) => {
      const v = ev.target.value;
      S.sel = v[0] === "t" ? { kind: "type", i: +v.slice(1) } : { kind: "mood", id: v.slice(1) };
      if (S.sel.kind === "mood") S.slow = false;      // a whole mood can't be timed; show its totals instead
      hush();
      render();
    });
    $("t-range").innerHTML = T.windows.map((w) => `<button type="button" role="radio" data-days="${w.days}">${RANGE_LABELS[w.days]}</button>`).join("");
    $("t-range").addEventListener("click", (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      const wasSlow = S.slow;
      S.days = +b.dataset.days; S.slow = false;      // time to close has its own fixed year; a range means totals
      hush();
      render();
      if (wasSlow) tell(`Switched back to totals for the ${RANGE_PHRASE[S.days]}. "Time to close" always covers one fixed year.`);
    });
    $("t-per").addEventListener("click", (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      S.per = b.dataset.per === "1"; S.slow = b.dataset.per === "2";
      hush();
      const note = S.slow ? slowFromMood() : null;
      render();
      if (note) tell(note);
    });
    $("t-rank").addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-id]");
      if (b) toggleCompare(b.dataset.id);
    });
    $("t-more").addEventListener("click", () => { S.showAll = !S.showAll; renderList(); });
    $("t-cards").addEventListener("click", (ev) => {
      const b = ev.target.closest("button.x");
      if (b) toggleCompare(b.dataset.id);
      const p = ev.target.closest("button[data-hood]");
      if (p) openHood(p.dataset.hood);
    });
    $("t-council-list").addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-adv]");
      if (!b) return;
      if (S.adv === b.dataset.adv) { S.adv = null; render(); } else openAdvisor(b.dataset.adv);
    });
    $("t-adv").addEventListener("click", (ev) => {
      if (ev.target.closest("[data-close]")) { S.adv = null; render(); return; }
      const sl = ev.target.closest("button[data-slow]");
      if (sl) { S.sel = { kind: "type", i: +sl.dataset.slow }; S.slow = true; S.per = false; render(); tell(`The map now shows how often <b>${esc(T.types[+sl.dataset.slow].label)}</b> took over a week to close, by neighborhood.`); return; }
      const t = ev.target.closest("button[data-type]");
      if (t) { S.sel = { kind: "type", i: +t.dataset.type }; S.slow = false; render(); tell(`The map and list now show <b>${esc(T.types[+t.dataset.type].label)}</b>.`); return; }
      const h = ev.target.closest("button[data-hood]");
      if (h) openHood(h.dataset.hood);
    });
    $("t-hood").addEventListener("click", (ev) => {
      if (ev.target.closest("[data-close]")) { S.hood = null; render(); return; }
      const c = ev.target.closest("[data-copy]");
      if (c) {
        const done = () => { c.textContent = "Link copied"; setTimeout(() => (c.textContent = "Copy a link to this profile"), 2000); };
        if (navigator.clipboard) navigator.clipboard.writeText(location.href).then(done, () => {});
      }
    });
    // Arrow keys move between options in each button group, like radio buttons
    document.querySelectorAll(".seg").forEach((g) => g.addEventListener("keydown", (ev) => {
      if (!["ArrowLeft", "ArrowRight"].includes(ev.key)) return;
      const bs = [...g.querySelectorAll("button")], i = bs.indexOf(document.activeElement);
      if (i < 0) return;
      const nb = bs[(i + (ev.key === "ArrowRight" ? 1 : bs.length - 1)) % bs.length];
      nb.focus(); nb.click();
    }));
  }

  async function start() {
    try {
      const [t, geo, idx] = await Promise.all([getJSON(`/data/${CITY}/trends.json`), getJSON(`/data/${CITY}/neighborhoods.geojson`),
        getJSON(`/data/${CITY}/index.json`)]);
      T = t; MOODS = idx.moods || {}; GEO = geo;
      try {      // time to close is optional: the page works without it
        const cl = await getJSON(`/data/${CITY}/close.json`);
        if (cl.type_names && cl.type_names.length === T.types.length && cl.type_names.every((n, i) => n === T.types[i].type)) CL = cl;
      } catch (e) { /* no close.json yet */ }
      if (!CL) { const b = document.querySelector('#t-per button[data-per="2"]'); if (b) b.hidden = true; }
      const end = new Date(T.updated + "T12:00:00");
      $("t-kicker").textContent = `Chicago · 311 trends · through ${end.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}`;
      drawMap(geo);
      setupControls();
      setupFind();
      setupLocate();
      readURL();
      render();
    } catch (e) {
      $("t-total").textContent = "Couldn't load the trends data. Try refreshing.";
      console.error(e);
    }
  }
  start();
})();
