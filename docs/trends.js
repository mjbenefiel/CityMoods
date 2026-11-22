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

  let T, MOODS, series = null, seriesLoading = null;
  const S = { sel: null, days: 90, per: false, compare: [], showAll: false };
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
    return T.areas.map((a, k) => (S.per ? rate(c[k], a) : c[k]));
  }
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
    geo.features.forEach((f) => {
      const el = document.createElementNS(SVGNS, "path");
      el.setAttribute("d", polys(f.geometry).map((p) => p.map((r) => "M" + r.map(pt).join("L") + "Z").join("")).join(""));
      el.addEventListener("pointermove", (ev) => tip(f.id, ev));
      el.addEventListener("pointerleave", () => ($("t-tip").hidden = true));
      el.addEventListener("click", (ev) => { toggleCompare(f.id); tip(f.id, ev); });
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
    const f = (x) => (x == null ? "" : S.per ? fmtRate(x) : fmt(Math.round(x)));
    $("t-legend").innerHTML = known.length
      ? `<span>${f(lo)}</span><span class="ramp">${[0, 1, 2, 3, 4].map((b) => `<i style="background:${mix(EMPTY, color, 0.18 + b * 0.2)}"></i>`).join("")}</span><span>${f(hi)}${S.per ? " per 1,000" : ""}</span>` +
        `<span class="hid"><i style="background:${HIDDEN}"></i>under 3</span>`
      : `<span>No neighborhood has 3 or more reports in this range.</span>`;
  }

  function tip(id, ev) {
    const k = T.areas.findIndex((a) => a.id === id);
    if (k < 0) return;
    const a = T.areas[k], n = counts()[k], tot = cityTotal();
    const r = rate(n, a);
    const box = $("t-tip"), host = box.parentElement.getBoundingClientRect();
    box.innerHTML = `<b>${esc(a.name)}</b><span class="t-side">${esc(a.side)}</span>` +
      (n == null ? `<span>Under 3 reports</span>` :
        `<span>${fmt(n)} report${n === 1 ? "" : "s"}${tot ? ` · ${((n / tot) * 100).toFixed(1)}% of the city` : ""}</span>` +
        (r != null ? `<span>${fmtRate(r)} per 1,000 residents</span>` : ""));
    box.hidden = false;
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
    $("t-list-title").textContent = `${selLabel()}: most reports${S.per ? " per 1,000 residents" : ""}, ${RANGE_PHRASE[S.days]}`;
    $("t-hint").textContent = S.per
      ? "Tap a neighborhood to compare it (up to 3). Small neighborhoods can jump around per 1,000."
      : "Tap a neighborhood to compare it (up to 3).";
    $("t-rank").innerHTML = shown.map((r) => {
      const on = S.compare.includes(r.a.id);
      const val = r.v == null ? "under 3" : S.per ? fmtRate(r.v) : fmt(r.v);
      const w = r.v == null ? 0 : Math.max(2, (r.v / max) * 100);
      return `<li><button type="button" data-id="${r.a.id}" aria-pressed="${on}">` +
        `<span class="nm">${esc(r.a.name)}</span><span class="val">${val}</span>` +
        `<span class="bar"><i style="width:${w.toFixed(1)}%;background:${selColor()}"></i></span></button></li>`;
    }).join("");
    $("t-more").textContent = S.showAll ? "Show top 10" : "Show all 77";
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
      seriesLoading = getJSON(`/data/${CITY}/trends-series.json`).then((d) => { series = d; renderCompare(); }).catch(() => {});
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
        `<p class="big"><b>${n == null ? "Under 3" : fmt(n)}</b> report${n === 1 ? "" : "s"}` +
        (r != null ? ` · <b>${fmtRate(r)}</b> per 1,000` : "") + `</p>` + trend +
        `<p class="lbl">Top requests, ${RANGE_PHRASE[S.days]}</p><ol class="t-top">` +
        top.map((x) => `<li><span>${esc(x.t.label)}</span><span>${fmt(x.n)}${a.pop ? ` <small>(${fmtRate((x.n / a.pop) * 1000)}/1k)</small>` : ""}</span></li>`).join("") +
        `</ol></article>`;
    }).join("");
  }

  // ------------------------------------------------------------ state + controls
  function render() {
    paintMap();
    renderList();
    renderCompare();
    $("t-type").value = S.sel.kind === "type" ? `t${S.sel.i}` : `m${S.sel.id}`;
    document.querySelectorAll("#t-range button").forEach((b) => b.setAttribute("aria-checked", String(+b.dataset.days === S.days)));
    document.querySelectorAll("#t-per button").forEach((b) => b.setAttribute("aria-checked", String((b.dataset.per === "1") === S.per)));
    const q = new URLSearchParams();
    q.set(S.sel.kind === "type" ? "type" : "mood", S.sel.kind === "type" ? slug(T.types[S.sel.i].label) : S.sel.id);
    q.set("days", S.days);
    if (S.per) q.set("per", "1");
    if (S.compare.length) q.set("compare", S.compare.join(","));
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
    const ids = new Set(T.areas.map((a) => a.id));
    S.compare = (q.get("compare") || "").split(",").filter((x) => ids.has(x)).slice(0, 3);
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
      render();
    });
    $("t-range").innerHTML = T.windows.map((w) => `<button type="button" role="radio" data-days="${w.days}">${RANGE_LABELS[w.days]}</button>`).join("");
    $("t-range").addEventListener("click", (ev) => {
      const b = ev.target.closest("button");
      if (b) { S.days = +b.dataset.days; render(); }
    });
    $("t-per").addEventListener("click", (ev) => {
      const b = ev.target.closest("button");
      if (b) { S.per = b.dataset.per === "1"; render(); }
    });
    $("t-rank").addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-id]");
      if (b) toggleCompare(b.dataset.id);
    });
    $("t-more").addEventListener("click", () => { S.showAll = !S.showAll; renderList(); });
    $("t-cards").addEventListener("click", (ev) => {
      const b = ev.target.closest("button.x");
      if (b) toggleCompare(b.dataset.id);
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
      T = t; MOODS = idx.moods || {};
      const end = new Date(T.updated + "T12:00:00");
      $("t-kicker").textContent = `Chicago · 311 trends · through ${end.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}`;
      drawMap(geo);
      setupControls();
      readURL();
      render();
    } catch (e) {
      $("t-total").textContent = "Couldn't load the trends data. Try refreshing.";
      console.error(e);
    }
  }
  start();
})();
