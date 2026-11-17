// CityMoods front page: rotating city headline, one live card per city (mini mood map, today's mood
// line and Claude's headline) and "how it works". Static JSON only, no tracking.
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => Number(n).toLocaleString("en-US");
  const SVGNS = "http://www.w3.org/2000/svg";

  async function getJSON(url) {
    const r = await fetch(url, { cache: "no-cache" });
    if (!r.ok) throw new Error(url + " " + r.status);
    return r.json();
  }

  function niceDate(iso) {
    return new Date(iso + "T12:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  }

  function possessive(name) {
    return name.endsWith("s") ? `${name}'` : `${name}'s`;
  }

  // ---------------------------------------------------------------- rotating city name
  function rotate(names) {
    const el = $("rot");
    if (!names.length) return;
    el.textContent = names[0];
    if (names.length < 2 || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let i = 0;
    setInterval(() => {
      el.classList.add("out");
      setTimeout(() => {
        i = (i + 1) % names.length;
        el.textContent = names[i];
        el.classList.remove("out");
      }, 320);
    }, 2400);
  }

  // ---------------------------------------------------------------- mini map
  function miniMap(svg, geo, centerLat, fillFor) {
    const k = Math.cos((centerLat * Math.PI) / 180);
    const polys = (g) => (g.type === "Polygon" ? [g.coordinates] : g.coordinates);
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    geo.features.forEach((f) => polys(f.geometry).forEach((p) => p.forEach((ring) => ring.forEach(([lon, lat]) => {
      const x = lon * k, y = -lat;
      minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    }))));
    const W = 400, H = 300, pad = 14;
    const s = Math.min((W - pad * 2) / (maxX - minX), (H - pad * 2) / (maxY - minY));
    const ox = (W - (maxX - minX) * s) / 2, oy = (H - (maxY - minY) * s) / 2;
    const pt = ([lon, lat]) => `${((lon * k - minX) * s + ox).toFixed(1)},${((-lat - minY) * s + oy).toFixed(1)}`;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const frag = document.createDocumentFragment();
    geo.features.forEach((f) => {
      const el = document.createElementNS(SVGNS, "path");
      el.setAttribute("d", polys(f.geometry).map((p) => p.map((ring) => "M" + ring.map(pt).join("L") + "Z").join("")).join(""));
      el.style.fill = fillFor(f.id);
      frag.append(el);
    });
    svg.append(frag);
  }

  // ---------------------------------------------------------------- city cards
  function skeleton(c) {
    return `<a class="city-card" href="?city=${c.key}" id="card-${c.key}">
      <div class="cc-map"><svg aria-hidden="true"></svg></div>
      <div class="cc-body">
        <h2>${esc(c.name)}</h2>
        <p class="cc-mood">&nbsp;</p>
        <p class="cc-head">&nbsp;</p>
        <p class="cc-foot"><span class="cc-date"></span><span class="cc-open">Open map →</span></p>
      </div></a>`;
  }

  async function fillCard(c) {
    const card = $(`card-${c.key}`);
    try {
      const [index, day, geo] = await Promise.all([
        getJSON(`data/${c.key}/index.json`), getJSON(`data/${c.key}/latest.json`), getJSON(`data/${c.key}/neighborhoods.geojson`)]);
      const MOODS = index.moods;
      const top = day.moods.find((m) => m.id !== "other" && m.n);
      const mood = top ? MOODS[top.id] : null;
      card.querySelector(".cc-mood").innerHTML = mood
        ? `<span aria-hidden="true">${mood.emoji}</span> ${esc(possessive(c.name))} mood: mostly <b style="--tint:${mood.color}">${esc(mood.label.toLowerCase())}</b>`
        : "";
      card.querySelector(".cc-head").textContent = day.words && day.words.headline ? day.words.headline : "";
      card.querySelector(".cc-date").textContent = `${niceDate(day.date)} · ${fmt(day.total)} requests`;
      card.setAttribute("aria-label", `${c.name}: ${mood ? "mostly " + mood.label.toLowerCase() : ""}. ${day.words.headline}`);
      miniMap(card.querySelector("svg"), geo, c.center_lat || 40,
        (id) => { const h = day.neighborhoods[id]; return h && h.top ? MOODS[h.top].color : "var(--empty)"; });
      return day.date;
    } catch (e) {
      card.querySelector(".cc-head").textContent = "Loading this city's mood failed. Try again in a minute.";
      console.error(e);
      return null;
    }
  }

  async function render() {
    $("home").hidden = false;
    document.title = "CityMoods: what cities complained about yesterday";
    let cities = [];
    try { cities = (await getJSON("data/cities.json")).cities || []; } catch (e) { console.error(e); }
    if (window.CityMoodsTabs) window.CityMoodsTabs(cities, null);
    rotate(cities.map((c) => c.name));
    $("city-cards").innerHTML = cities.map(skeleton).join("");
    const dates = (await Promise.all(cities.map(fillCard))).filter(Boolean).sort();
    if (dates.length) $("home-date").textContent = `Latest: ${niceDate(dates[dates.length - 1])} · ${cities.length} cities`;
    $("sources").textContent = "each city's 311 service requests";
    $("not-affiliated").textContent = "any of these cities";
  }

  window.CityMoodsHome = { render };
})();
