// City Mood: draws yesterday's 311 moods on a map of NYC neighborhoods.
// Everything here is static JSON made by pipeline/build.py. No tracking, no third-party calls.
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const fmt = (n) => Number(n).toLocaleString("en-US");
  const SVGNS = "http://www.w3.org/2000/svg";

  let MOODS = {};
  let days = [];
  let dayIndex = 0;
  let entry = null;
  let mode = "top";      // "top" or a mood id
  let selected = null;   // neighborhood id
  const paths = {};      // id -> <path>

  async function getJSON(url) {
    const r = await fetch(url, { cache: "no-cache" });
    if (!r.ok) throw new Error(url + " " + r.status);
    return r.json();
  }

  // ---------------------------------------------------------------- map
  function drawMap(geo) {
    const svg = $("map");
    const k = Math.cos((40.7 * Math.PI) / 180);
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const each = (coords, fn) => coords.forEach((ring) => ring.forEach(fn));
    const polys = (g) => (g.type === "Polygon" ? [g.coordinates] : g.coordinates);
    geo.features.forEach((f) => polys(f.geometry).forEach((p) => each(p, ([lon, lat]) => {
      const x = lon * k, y = -lat;
      minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    })));
    const W = 1000, pad = 20, s = (W - pad * 2) / (maxX - minX);
    const H = Math.round((maxY - minY) * s + pad * 2);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.style.aspectRatio = `${W} / ${H}`;
    const pt = ([lon, lat]) => `${((lon * k - minX) * s + pad).toFixed(1)},${((-lat - minY) * s + pad).toFixed(1)}`;

    geo.features.forEach((f) => {
      const d = polys(f.geometry).map((p) => p.map((ring) => "M" + ring.map(pt).join("L") + "Z").join("")).join("");
      const el = document.createElementNS(SVGNS, "path");
      el.setAttribute("d", d);
      el.dataset.id = f.id;
      el.dataset.name = f.properties.name;
      el.dataset.borough = f.properties.borough;
      const t = document.createElementNS(SVGNS, "title");
      el.append(t);
      el.addEventListener("click", () => select(f.id));
      svg.append(el);
      paths[f.id] = el;
    });
  }

  function mix(hex, amount) {
    // Blend a mood color toward the empty color: amount 0 = empty, 1 = full color.
    const empty = getComputedStyle(document.documentElement).getPropertyValue("--empty").trim() || "#ECE8E1";
    const a = parseInt(empty.slice(1), 16), b = parseInt(hex.slice(1), 16);
    const ch = (v, sh) => (v >> sh) & 255;
    const c = [16, 8, 0].map((sh) => Math.round(ch(a, sh) + (ch(b, sh) - ch(a, sh)) * amount));
    return "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
  }

  function paint() {
    const hoods = entry.neighborhoods;
    let max = 1;
    if (mode !== "top") {
      for (const h of Object.values(hoods)) max = Math.max(max, h.moods[mode] || 0);
    }
    for (const [id, el] of Object.entries(paths)) {
      const h = hoods[id];
      let fill = "var(--empty)", tip = `${el.dataset.name}: no reports`;
      if (h) {
        if (mode === "top") {
          if (h.top) fill = MOODS[h.top].color;
          tip = `${h.name}: ${h.top ? MOODS[h.top].label : "mixed"} (${fmt(h.total)} reports)`;
        } else {
          const n = h.moods[mode] || 0;
          if (n) fill = mix(MOODS[mode].color, 0.18 + 0.82 * Math.sqrt(n / max));
          tip = `${h.name}: ${n ? fmt(n) : "fewer than 3"} ${MOODS[mode].label.toLowerCase()} reports`;
        }
      }
      el.style.fill = fill;
      el.querySelector("title").textContent = tip;
      el.classList.toggle("sel", id === selected);
    }
    const note = $("mode-note");
    if (mode === "top") {
      note.textContent = "";
      document.querySelector('[data-mode="top"]').classList.add("on");
    } else {
      document.querySelector('[data-mode="top"]').classList.remove("on");
      note.textContent = `${MOODS[mode].emoji} ${MOODS[mode].label}: darker = more reports`;
    }
  }

  // ---------------------------------------------------------------- panels
  function vs(n, typical) {
    if (!typical) return "";
    const r = n / typical;
    if (r >= 1.3) return `<span class="vs up">${r.toFixed(1)}× usual</span>`;
    if (r <= 0.75) return `<span class="vs">below usual</span>`;
    return `<span class="vs">about usual</span>`;
  }

  function renderMoods() {
    const list = $("moods");
    list.textContent = "";
    const shown = entry.moods.filter((m) => m.id !== "other" && m.n > 0);
    const max = Math.max(...shown.map((m) => m.n));
    shown.forEach((m) => {
      const info = MOODS[m.id];
      const li = document.createElement("li");
      li.innerHTML = `<button class="mood${mode === m.id ? " on" : ""}" data-id="${m.id}" aria-pressed="${mode === m.id}">
        <span class="e" aria-hidden="true">${info.emoji}</span>
        <span>${info.label}${vs(m.n, m.typical)}</span>
        <span class="n">${fmt(m.n)}</span>
        <span class="bar"><i style="width:${(100 * m.n / max).toFixed(1)}%;background:${info.color}"></i></span>
      </button>`;
      li.firstElementChild.addEventListener("click", () => setMode(mode === m.id ? "top" : m.id));
      list.append(li);
    });
  }

  function renderTypes() {
    const ol = $("types");
    ol.textContent = "";
    entry.top_types.slice(0, 10).forEach((t) => {
      const li = document.createElement("li");
      li.innerHTML = `${MOODS[t.mood].emoji} ${escapeHTML(t.name)}: <b>${fmt(t.n)}</b> ${vs(t.n, t.typical)}`;
      ol.append(li);
    });
  }

  function renderBoroughs() {
    const box = $("boroughs");
    const lines = (entry.words && entry.words.boroughs) || {};
    const names = Object.keys(lines);
    box.innerHTML = names.length
      ? names.sort().map((b) => `<p><b>${escapeHTML(b)}</b>${escapeHTML(lines[b])}</p>`).join("")
      : Object.entries(entry.boroughs).map(([b, ms]) =>
          `<p><b>${escapeHTML(b)}</b>${ms.map((m) => `${MOODS[m.id].emoji} ${MOODS[m.id].label} ${fmt(m.n)}`).join(" · ")}</p>`).join("");
  }

  function select(id) {
    selected = id;
    const card = $("card");
    const h = entry.neighborhoods[id];
    const el = paths[id];
    if (!el) { card.hidden = true; return; }
    let body;
    if (!h) {
      body = `<p class="sub">${escapeHTML(el.dataset.borough)}</p><p>No 311 reports with a location here yesterday.</p>`;
    } else {
      const top = h.top ? `${MOODS[h.top].emoji} Top gripe: <b>${MOODS[h.top].label}</b>` : "A mixed bag of gripes";
      const items = h.types.length
        ? `<ol>${h.types.map((t) => `<li>${escapeHTML(t.name)}: ${fmt(t.n)}</li>`).join("")}</ol>`
        : "";
      body = `<p class="sub">${escapeHTML(h.borough)} · ${fmt(h.total)} reports</p><p>${top}</p>${items}`;
    }
    card.innerHTML = `<button class="close" aria-label="Close">×</button><h3>${escapeHTML(el.dataset.name)}</h3>${body}`;
    card.querySelector(".close").addEventListener("click", () => { selected = null; card.hidden = true; paint(); });
    card.hidden = false;
    paint();
  }

  function setMode(m) {
    mode = m;
    paint();
    renderMoods();
  }

  // ---------------------------------------------------------------- day
  function niceDate(iso) {
    const d = new Date(iso + "T12:00:00");
    return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  }

  async function loadDay(i) {
    dayIndex = i;
    const date = days[i];
    entry = await getJSON(`data/days/${date}.json`);
    $("day-label").textContent = niceDate(date);
    $("prev").disabled = i >= days.length - 1;
    $("next").disabled = i <= 0;
    const w = entry.weather;
    $("kicker").textContent = `${entry.weekday}, ${niceDate(date).replace(/^\w+, /, "")} · ${fmt(entry.total)} requests to 311`
      + (w ? ` · ${w.high_f}°F high, ${w.low_f}°F low` : "");
    $("headline").textContent = entry.words.headline;
    $("blurb").textContent = entry.words.blurb;
    document.title = `${entry.words.headline} · City Mood`;
    renderMoods();
    renderTypes();
    renderBoroughs();
    if (selected) select(selected); else paint();
    const url = new URL(location.href);
    if (i === 0) url.searchParams.delete("day"); else url.searchParams.set("day", date);
    history.replaceState(null, "", url);
  }

  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  async function start() {
    try {
      const [index, geo] = await Promise.all([getJSON("data/index.json"), getJSON("data/neighborhoods.geojson")]);
      MOODS = index.moods;
      days = index.days;
      drawMap(geo);
      $("prev").addEventListener("click", () => loadDay(Math.min(days.length - 1, dayIndex + 1)));
      $("next").addEventListener("click", () => loadDay(Math.max(0, dayIndex - 1)));
      document.querySelector('[data-mode="top"]').addEventListener("click", () => setMode("top"));
      const want = new URL(location.href).searchParams.get("day");
      await loadDay(Math.max(0, days.indexOf(want)));
    } catch (e) {
      $("headline").textContent = "The city's mood is loading slowly. Try again in a minute.";
      console.error(e);
    }
  }

  start();
})();
