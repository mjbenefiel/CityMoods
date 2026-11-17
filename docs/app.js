// CityMoods: draws yesterday's 311 moods on a map of NYC neighborhoods.
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
      el.setAttribute("role", "button");
      el.addEventListener("click", () => select(f.id));
      el.addEventListener("pointermove", (ev) => showHover(f.id, ev));
      el.addEventListener("pointerleave", hideHover);
      svg.append(el);
      paths[f.id] = el;
    });

    // Faint borough names so you know where you are before hovering.
    const BOROUGH_LABELS = [["Manhattan", -73.972, 40.785], ["Bronx", -73.866, 40.852], ["Brooklyn", -73.947, 40.648],
      ["Queens", -73.805, 40.712], ["Staten Island", -74.152, 40.582]];
    for (const [name, lon, lat] of BOROUGH_LABELS) {
      const [x, y] = pt([lon, lat]).split(",");
      const t = document.createElementNS(SVGNS, "text");
      t.setAttribute("x", x); t.setAttribute("y", y);
      t.setAttribute("class", "boro");
      t.textContent = name.toUpperCase();
      svg.append(t);
    }
  }

  // ---------------------------------------------------------------- selected neighborhood
  // Fade the rest of the map, outline the chosen neighborhood, and put its name on the map.
  let lastMarked = null;
  function markSelected() {
    const svg = $("map");
    svg.classList.toggle("has-sel", !!selected);
    const old = svg.querySelector(".sel-label");
    if (old) old.remove();
    if (!selected || !paths[selected]) { lastMarked = null; return; }
    const el = paths[selected];
    svg.insertBefore(el, svg.querySelector(".boro"));   // draw on top of its neighbors (borough names stay above)
    const b = el.getBBox();
    const vb = svg.viewBox.baseVal;
    const g = document.createElementNS(SVGNS, "g");
    g.setAttribute("class", "sel-label" + (lastMarked !== selected ? " pulse" : ""));
    const t = document.createElementNS(SVGNS, "text");
    t.textContent = el.dataset.name;
    g.append(t);
    svg.append(g);
    const tb = t.getBBox();
    const padX = 10, padY = 6, w = tb.width + padX * 2, h = tb.height + padY * 2;
    let x = b.x + b.width / 2 - w / 2, y = b.y - h - 8;          // above the shape...
    if (y < 4) y = b.y + b.height + 8;                             // ...or below if it's at the top edge
    x = Math.max(4, Math.min(vb.width - w - 4, x));
    const r = document.createElementNS(SVGNS, "rect");
    r.setAttribute("x", x); r.setAttribute("y", y); r.setAttribute("width", w); r.setAttribute("height", h);
    r.setAttribute("rx", h / 2);
    t.setAttribute("x", x + padX); t.setAttribute("y", y + padY + tb.height * 0.78);
    g.insertBefore(r, t);
    lastMarked = selected;
  }

  // ---------------------------------------------------------------- hover label
  function hoverLine(id) {
    const h = entry && entry.neighborhoods[id];
    if (!h) return "No reports with a location";
    if (mode === "distinct") {
      return h.distinct ? `✨ ${escapeHTML(h.distinct.name)}, ${h.distinct.x}× the city's rate` : "Nothing stands out";
    }
    if (MOODS[mode]) {
      const n = h.moods[mode] || 0;
      return `${MOODS[mode].emoji} ${n ? fmt(n) : "Fewer than 3"} ${MOODS[mode].label.toLowerCase()} reports`;
    }
    return h.top
      ? `${MOODS[h.top].emoji} ${MOODS[h.top].label} · ${fmt(h.moods[h.top])} of ${fmt(h.total)} reports`
      : `${fmt(h.total)} reports, no clear top gripe`;
  }

  function showHover(id, ev) {
    if (ev.pointerType && ev.pointerType !== "mouse") return;  // phones: tap opens the card instead
    const tip = $("hover"), wrap = tip.parentElement.getBoundingClientRect(), el = paths[id];
    if (tip.dataset.id !== id) {
      tip.innerHTML = `<b>${escapeHTML(el.dataset.name)}</b><span>${hoverLine(id)}</span>`;
      tip.dataset.id = id;
    }
    tip.hidden = false;
    let x = ev.clientX - wrap.left + 14, y = ev.clientY - wrap.top + 14;
    const w = tip.offsetWidth, hgt = tip.offsetHeight;
    if (x + w > wrap.width - 8) x = ev.clientX - wrap.left - w - 14;
    if (y + hgt > wrap.height - 8) y = ev.clientY - wrap.top - hgt - 14;
    tip.style.transform = `translate(${Math.max(8, x)}px, ${Math.max(8, y)}px)`;
  }

  function hideHover() {
    const tip = $("hover");
    tip.hidden = true;
    tip.dataset.id = "";
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
    if (MOODS[mode]) {
      for (const h of Object.values(hoods)) max = Math.max(max, h.moods[mode] || 0);
    }
    for (const [id, el] of Object.entries(paths)) {
      const h = hoods[id];
      let fill = "var(--empty)", tip = `${el.dataset.name}: no reports`;
      if (h) {
        if (mode === "top") {
          if (h.top) fill = MOODS[h.top].color;
          tip = `${h.name}: ${h.top ? MOODS[h.top].label : "mixed"} (${fmt(h.total)} reports)`;
        } else if (mode === "distinct") {
          const d = h.distinct;
          // Heatmap: mood color for *what* stands out, depth for *how much* (log scale, 1.5x pale -> 30x+ full).
          if (d) fill = mix(MOODS[d.mood].color, 0.2 + 0.8 * Math.min(1, Math.log(d.x / 1.5) / Math.log(20)));
          tip = d ? `${h.name}: ${d.name}, ${d.x}× the city's rate` : `${h.name}: nothing stands out`;
        } else {
          const n = h.moods[mode] || 0;
          if (n) fill = mix(MOODS[mode].color, 0.18 + 0.82 * Math.sqrt(n / max));
          tip = `${h.name}: ${n ? fmt(n) : "fewer than 3"} ${MOODS[mode].label.toLowerCase()} reports`;
        }
      }
      el.style.fill = fill;
      el.setAttribute("aria-label", tip);
      el.classList.toggle("sel", id === selected);
    }
    markSelected();
    const note = $("mode-note");
    document.querySelectorAll(".chip[data-mode]").forEach((c) => {
      c.classList.toggle("on", c.dataset.mode === mode);
      c.setAttribute("aria-pressed", c.dataset.mode === mode);
    });
    if (mode === "top") note.textContent = "";
    else if (mode === "distinct") note.innerHTML = 'What each place reports more than the city · <span class="ramp" aria-hidden="true"></span> darker = more out of character';
    else note.textContent = `${MOODS[mode].emoji} ${MOODS[mode].label}: darker = more reports`;
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

  // "Ceiling: collapsing or falling" -> ["Ceiling", "collapsing or falling"];
  // "Loud music/party (next door)" -> ["Loud music/party", "next door"].
  function splitLabel(name) {
    let main = name, note = "";
    const paren = main.match(/^(.*?)\s*\(([^)]+)\)\s*$/);
    if (paren) { main = paren[1]; note = paren[2]; }
    const colon = main.indexOf(": ");
    if (colon > 0) { note = main.slice(colon + 2) + (note ? ` · ${note}` : ""); main = main.slice(0, colon); }
    return [main, note];
  }

  function badge(mood) {
    const m = MOODS[mood] || MOODS.other;
    return `<span class="badge" style="--tint:${m.color}" aria-hidden="true">${m.emoji}</span>`;
  }

  function label(name) {
    const [main, note] = splitLabel(name);
    return `<span class="lbl"><span class="main">${escapeHTML(main)}</span>`
      + (note ? `<span class="note">${escapeHTML(note)}</span>` : "") + "</span>";
  }

  function change(n, typical) {
    if (!typical) return "";
    const r = n / typical;
    if (r >= 1.3) return `<span class="pill up">↑ ${r.toFixed(r >= 10 ? 0 : 1)}×</span>`;
    if (r <= 0.75) return `<span class="pill down">↓ ${r.toFixed(1)}×</span>`;
    return "";
  }

  function listInto(id, items) {
    const ol = $(id);
    ol.innerHTML = items.map((t) => `<li class="row">${badge(t.mood)}${label(t.name)}`
      + `<span class="num">${fmt(t.n)}${change(t.n, t.typical)}</span></li>`).join("");
    ol.closest("section > div").hidden = !items.length;
  }

  function spikesInto(id, items) {
    const ol = $(id);
    ol.innerHTML = items.map((t) => {
      const r = t.typical ? t.n / t.typical : 0;
      const mult = r >= 10 ? Math.round(r) : r.toFixed(1);
      return `<li class="spike"><span class="mult">${mult}×</span><span class="lbl">`
        + `<span class="main">${badge(t.mood)}${escapeHTML(splitLabel(t.name)[0])}</span>`
        + (splitLabel(t.name)[1] ? `<span class="note">${escapeHTML(splitLabel(t.name)[1])}</span>` : "")
        + `<span class="note">${fmt(t.n)} reports · usually ${fmt(t.typical)}</span></span></li>`;
    }).join("");
    ol.closest("section > div").hidden = !items.length;
  }

  function renderTypes() {
    // Older day files only have complaint types; newer ones have problem details too.
    listInto("types", (entry.top_details || entry.top_types).slice(0, 10));
    spikesInto("odd", (entry.detail_spikes || []).slice(0, 5));
  }

  function renderAgencies() {
    const box = $("agencies");
    const list = entry.agencies || [];
    box.closest("section > div").hidden = !list.length;
    if (!list.length) return;
    const max = list[0].n;
    box.innerHTML = list.slice(0, 8).map((a) =>
      `<li><span>${escapeHTML(a.name)}</span><b>${fmt(a.n)}</b><i style="width:${(100 * a.n / max).toFixed(1)}%"></i></li>`).join("");
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
      // One row per mood, biggest first, with the complaint types that add up to it.
      const order = Object.entries(h.moods).filter(([m]) => m !== "other").sort((a, b) => b[1] - a[1]);
      const rows = order.map(([m, n]) => {
        const shown = (h.details || h.types || []).filter((t) => t.mood === m).slice(0, 3);
        const bits = shown.map((t) => `${escapeHTML(t.name)} ${fmt(t.n)}`);
        const rest = n - shown.reduce((s, t) => s + t.n, 0);
        if (rest > 0) bits.push(`${shown.length ? "other" : "various"} ${fmt(rest)}`);
        return `<li><div class="row"><span>${MOODS[m].emoji} ${MOODS[m].label}${m === h.top ? " <em>top gripe</em>" : ""}</span><b>${fmt(n)}</b></div>`
          + `<div class="parts">${bits.join(" · ")}</div></li>`;
      }).join("");
      const elsewhere = h.total - order.reduce((s, [, n]) => s + n, 0);
      const foot = elsewhere > 0 ? `<p class="fine-card">Plus ${fmt(elsewhere)} other or uncommon reports.</p>` : "";
      const ag = h.agency ? `<p class="fine-card">Most were sent to ${escapeHTML(h.agency.name)} (${fmt(h.agency.n)} of ${fmt(h.total)}).</p>` : "";
      body = `<p class="sub">${escapeHTML(h.borough)} · ${fmt(h.total)} reports</p><ol class="card-moods">${rows}</ol>${foot}${ag}`;
    }
    const sig = h && h.distinct
      ? `<p class="signature">✨ Signature gripe: <b>${escapeHTML(h.distinct.name)}</b>, ${h.distinct.x}× the city's rate (${fmt(h.distinct.n)} reports)</p>`
      : "";
    card.innerHTML = `<button class="close" aria-label="Close">×</button><h3>${escapeHTML(el.dataset.name)}</h3>`
      + body.replace("</p>", "</p>" + sig) + `<button class="share" type="button">🔗 Copy link to ${escapeHTML(el.dataset.name.split("-")[0])}</button>`;
    card.querySelector(".close").addEventListener("click", () => { selected = null; card.hidden = true; paint(); syncURL(); });
    card.querySelector(".share").addEventListener("click", (ev) => copyLink(ev.currentTarget));
    syncURL();
    card.hidden = false;
    paint();
  }

  function setMode(m) {
    mode = m;
    paint();
    renderMoods();
    syncURL();
  }

  // The address bar always reflects what you're looking at, so any view can be shared.
  function syncURL() {
    if (!days.length) return;
    const url = new URL(location.href);
    const set = (k, v) => (v ? url.searchParams.set(k, v) : url.searchParams.delete(k));
    set("day", dayIndex === 0 ? "" : days[dayIndex]);
    set("hood", selected || "");
    set("mode", mode === "top" ? "" : mode);
    history.replaceState(null, "", url);
  }

  // ---------------------------------------------------------------- search
  function setupSearch(geo) {
    const input = $("hood-search"), box = $("hood-results");
    const all = geo.features.map((f) => ({ id: f.id, name: f.properties.name, borough: f.properties.borough }))
      .sort((a, b) => a.name.localeCompare(b.name));
    let matches = [], active = 0;

    const render = () => {
      box.hidden = !matches.length;
      box.innerHTML = matches.map((m, k) =>
        `<li role="option" data-id="${m.id}" class="${k === active ? "on" : ""}" aria-selected="${k === active}">`
        + `<b>${escapeHTML(m.name)}</b><span>${escapeHTML(m.borough)}</span></li>`).join("");
    };
    const search = () => {
      const q = input.value.trim().toLowerCase();
      if (!q) { matches = []; render(); return; }
      const starts = all.filter((m) => m.name.toLowerCase().startsWith(q));
      const words = all.filter((m) => !starts.includes(m) && m.name.toLowerCase().split(/[\s()-]+/).some((w) => w.startsWith(q)));
      const inside = all.filter((m) => !starts.includes(m) && !words.includes(m) && m.name.toLowerCase().includes(q));
      matches = [...starts, ...words, ...inside].slice(0, 6);
      active = 0;
      render();
    };
    const choose = (id) => {
      matches = []; render();
      input.value = "";
      input.blur();
      hideHover();
      select(id);
      $("map").scrollIntoView({ behavior: "smooth", block: "nearest" });
    };

    input.addEventListener("input", search);
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" && matches.length) { active = (active + 1) % matches.length; render(); e.preventDefault(); }
      else if (e.key === "ArrowUp" && matches.length) { active = (active - 1 + matches.length) % matches.length; render(); e.preventDefault(); }
      else if (e.key === "Enter") { if (matches[active]) choose(matches[active].id); e.preventDefault(); }
      else if (e.key === "Escape") { matches = []; render(); input.blur(); }
    });
    box.addEventListener("pointerdown", (e) => {
      const li = e.target.closest("li[data-id]");
      if (li) { e.preventDefault(); choose(li.dataset.id); }
    });
    input.addEventListener("blur", () => setTimeout(() => { matches = []; render(); }, 120));
  }

  async function copyLink(btn) {
    const old = btn.textContent;
    try {
      await navigator.clipboard.writeText(location.href);
      btn.textContent = "✓ Link copied";
    } catch (_) {
      window.prompt("Copy this link:", location.href);
    }
    setTimeout(() => { btn.textContent = old; }, 1800);
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
    document.title = `${entry.words.headline} · CityMoods`;
    renderMoods();
    renderTypes();
    renderAgencies();
    renderRare();
    renderBoroughs();
    renderFreshness();
    if (selected) select(selected); else paint();
    syncURL();
  }

  function renderRare() {
    const list = entry.rare_finds || [];
    $("rare-wrap").hidden = !list.length;
    $("rare").innerHTML = list.map((r) => {
      const times = r.n === 1 ? "Reported once" : `Reported ${fmt(r.n)} times`;
      const before = r.past_28_days === 0 ? "not once in the 4 weeks before"
        : `${fmt(r.past_28_days)} time${r.past_28_days === 1 ? "" : "s"} in the 4 weeks before`;
      const quip = r.quip ? `<p class="quip">${escapeHTML(r.quip)}</p>` : "";
      return `<article class="rare-card"><span class="e" aria-hidden="true">${MOODS[r.mood] && r.mood !== "other" ? MOODS[r.mood].emoji : "🔎"}</span>`
        + `<h3>${escapeHTML(r.name)}</h3>${quip}<p class="meta">${times} · ${before}</p></article>`;
    }).join("");
  }

  function renderFreshness() {
    const el = $("fresh");
    if (!entry.source_newest) { el.textContent = ""; return; }
    const t = new Date(entry.source_newest);
    const when = t.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    el.textContent = `The city's data currently runs through ${when}, so ${niceDate(days[0])} is the newest full day. NYC usually posts each day's requests the following evening.`;
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
      document.querySelectorAll(".chip[data-mode]").forEach((c) =>
        c.addEventListener("click", () => setMode(c.dataset.mode)));
      setupSearch(geo);
      $("map").addEventListener("pointerleave", hideHover);
      window.addEventListener("scroll", hideHover, { passive: true });
      const params = new URL(location.href).searchParams;
      const wantMode = params.get("mode");
      if (wantMode === "distinct" || MOODS[wantMode]) mode = wantMode;
      const wantHood = params.get("hood");
      if (wantHood && paths[wantHood]) selected = wantHood;
      await loadDay(Math.max(0, days.indexOf(params.get("day"))));
    } catch (e) {
      $("headline").textContent = "The city's mood is loading slowly. Try again in a minute.";
      console.error(e);
    }
  }

  start();
})();
