// CityMoods: draws the latest day's 311 moods on a map of a city's neighborhoods.
// Everything here is static JSON made by pipeline/build.py. The only outside call is GoatCounter's
// cookie-free page counter (see privacy.html).
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

  // Which city. Each city has its own address (…/chicago/), a copy of this page marked <html data-city="chicago">
  // whose link previews show that city. No city means the front page (home.js). Each city's data lives in data/<city>/.
  const PAGE_CITY = document.documentElement.dataset.city || "";
  const QUERY_CITY = (new URL(location.href).searchParams.get("city") || "").toLowerCase().replace(/[^a-z]/g, "");
  // Older links used ?city=chicago on the front page; move them to the city's own address.
  const MOVING = !PAGE_CITY && !!QUERY_CITY;
  if (MOVING) {
    const old = new URL(location.href);
    old.searchParams.delete("city");
    location.replace(new URL(`${QUERY_CITY}/${old.search}${old.hash}`, document.baseURI).href);
  }
  const CITY_PARAM = PAGE_CITY || QUERY_CITY;
  const IS_HOME = !CITY_PARAM;
  const CITY_KEY = CITY_PARAM || "nyc";
  const BASE = `data/${CITY_KEY}/`;
  let CITY = { key: CITY_KEY, name: "", center_lat: 40.7, labels: [], sources: [] };

  async function getJSON(url) {
    const r = await fetch(url, { cache: "no-cache" });
    if (!r.ok) throw new Error(url + " " + r.status);
    return r.json();
  }

  // ---------------------------------------------------------------- map
  function drawMap(geo) {
    const svg = $("map");
    const k = Math.cos(((CITY.center_lat || 40.7) * Math.PI) / 180);
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const each = (coords, fn) => coords.forEach((ring) => ring.forEach(fn));
    const polys = (g) => (g.type === "Polygon" ? [g.coordinates] : g.coordinates);
    geo.features.forEach((f) => polys(f.geometry).forEach((p) => each(p, ([lon, lat]) => {
      const x = lon * k, y = -lat;
      minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    })));
    // Extra room at the top and bottom so the map's edges (and labels) don't sit under the
    // mode buttons, search box or zoom controls.
    const W = 1000, pad = 20, padTop = 70, padBottom = 60, s = (W - pad * 2) / (maxX - minX);
    const H = Math.round((maxY - minY) * s + padTop + padBottom);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    // Tall maps (Chicago) render smaller on screen, so scale map text up to match.
    svg.style.setProperty("--txt", Math.max(1, H / 1000).toFixed(2));
    svg.style.aspectRatio = `${W} / ${H}`;
    const pt = ([lon, lat]) => `${((lon * k - minX) * s + pad).toFixed(1)},${((-lat - minY) * s + padTop).toFixed(1)}`;

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
    for (const [name, lon, lat] of (CITY.labels || [])) {
      const [x, y] = pt([lon, lat]).split(",");
      const t = document.createElementNS(SVGNS, "text");
      t.setAttribute("x", x); t.setAttribute("y", y);
      t.setAttribute("class", "boro");
      t.textContent = name.toUpperCase();
      svg.append(t);
    }
    Z.base = { x: 0, y: 0, w: W, h: H };
    setView(Z.base);
    setupZoom();
  }

  // ---------------------------------------------------------------- zoom
  // The map is SVG, so zooming just changes which part of it is in view (the viewBox).
  // Buttons, double-click/tap, ⌘/Ctrl + scroll (plain scrolling still scrolls the page),
  // drag to pan when zoomed, and two-finger pinch on phones (one finger still scrolls the page).
  const Z = { base: null, v: null, max: 10, anim: 0, drag: null, moved: false, pinch: null, lastTap: 0, hintTimer: 0 };
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

  function setView(v) {
    const b = Z.base, svg = $("map");
    const w = Math.min(b.w, Math.max(b.w / Z.max, v.w)), h = w * b.h / b.w;
    const x = Math.min(b.x + b.w - w, Math.max(b.x, v.x)), y = Math.min(b.y + b.h - h, Math.max(b.y, v.y));
    Z.v = { x, y, w, h };
    svg.setAttribute("viewBox", `${x.toFixed(2)} ${y.toFixed(2)} ${w.toFixed(2)} ${h.toFixed(2)}`);
    svg.style.setProperty("--z", (b.w / w).toFixed(3));
    svg.style.setProperty("--u", unitsPerPixel().toFixed(4));
    const zoomed = w < b.w - 0.5;
    svg.classList.toggle("zoomed", zoomed);
    const ctl = (id, off) => { const el = $(id); if (el) el.disabled = off; };
    ctl("zoom-out", !zoomed); ctl("zoom-reset", !zoomed); ctl("zoom-in", w <= b.w / Z.max + 0.5);
  }

  // How many map units one screen pixel covers right now (changes with zoom and screen width).
  // Map text is sized with this so it's the same on-screen size on a phone or a big monitor.
  function unitsPerPixel() {
    const svg = $("map"), w = svg.clientWidth || svg.getBoundingClientRect().width;
    return w && Z.v ? Z.v.w / w : 1.5;
  }

  function animateTo(target, after) {
    cancelAnimationFrame(Z.anim);
    if (reduceMotion) { setView(target); markSelected(); if (after) after(); return; }
    const from = { ...Z.v }, t0 = performance.now(), ms = 340;
    const step = (now) => {
      const t = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - t, 3);
      setView({ x: from.x + (target.x - from.x) * e, y: from.y + (target.y - from.y) * e,
                w: from.w + (target.w - from.w) * e, h: from.h + (target.h - from.h) * e });
      if (t < 1) Z.anim = requestAnimationFrame(step); else { markSelected(); if (after) after(); }
    };
    Z.anim = requestAnimationFrame(step);
  }

  function zoomAt(factor, cx, cy, animate) {
    const v = Z.v, w = v.w / factor, h = v.h / factor;
    const target = { x: cx - (cx - v.x) / factor, y: cy - (cy - v.y) / factor, w, h };
    if (animate) animateTo(target); else { setView(target); markSelected(); }
  }

  function zoomCenter(factor) {
    const v = Z.v;
    zoomAt(factor, v.x + v.w / 2, v.y + v.h / 2, true);
  }

  function toSvg(clientX, clientY) {
    const r = $("map").getBoundingClientRect();
    return { x: Z.v.x + (clientX - r.left) / r.width * Z.v.w, y: Z.v.y + (clientY - r.top) / r.height * Z.v.h };
  }

  // Glide to a neighborhood (from search or a shared link). Big areas just get centered.
  function zoomToHood(id, animate = true) {
    const el = paths[id];
    if (!el || !Z.base) return;
    const bb = el.getBBox(), b = Z.base, aspect = b.w / b.h;
    // Phones get a gentler zoom so you can still see the neighbors around the pick.
    const phone = isPhoneLayout(), pad = phone ? 5 : 3, minW = b.w / (phone ? 3 : 6);
    let w = Math.max(bb.width * pad, bb.height * pad * aspect, minW);
    if (w >= b.w * 0.8) w = b.w;
    const h = w / aspect;
    // Center it in the part of the map the card doesn't cover.
    const cover = w < b.w ? cardCover() : 0, centerAt = cover + (1 - cover) / 2;
    const target = { x: bb.x + bb.width / 2 - w * centerAt, y: bb.y + bb.height / 2 - h / 2, w, h };
    if (animate) animateTo(target); else { setView(target); markSelected(); }
  }

  // On wide screens the neighborhood card floats over the left of the map; this is the share of the
  // map's width it covers (0 when the card is hidden or sits below the map on phones).
  function cardCover() {
    const card = $("card"), svg = $("map");
    if (!card || card.hidden || getComputedStyle(card).position !== "absolute") return 0;
    const r = svg.getBoundingClientRect(), c = card.getBoundingClientRect();
    return Math.max(0, Math.min(0.6, (c.right - r.left + 12) / r.width));
  }

  function showZoomHint() {
    const hint = $("zoom-hint");
    if (!hint) return;
    hint.hidden = false;
    clearTimeout(Z.hintTimer);
    Z.hintTimer = setTimeout(() => { hint.hidden = true; }, 1400);
  }

  function setupZoom() {
    const svg = $("map");
    // Keep label sizes right when the screen is resized or rotated.
    if (window.ResizeObserver) new ResizeObserver(() => { svg.style.setProperty("--u", unitsPerPixel().toFixed(4)); markSelected(); }).observe(svg);
    $("zoom-in").addEventListener("click", () => zoomCenter(1.8));
    $("zoom-out").addEventListener("click", () => zoomCenter(1 / 1.8));
    $("zoom-reset").addEventListener("click", () => animateTo({ ...Z.base }));

    svg.addEventListener("wheel", (e) => {
      if (!(e.ctrlKey || e.metaKey)) { showZoomHint(); return; }   // trackpad pinch on Mac arrives as ctrl+wheel
      e.preventDefault();
      const p = toSvg(e.clientX, e.clientY);
      zoomAt(Math.exp(-e.deltaY * 0.0028), p.x, p.y, false);
    }, { passive: false });

    svg.addEventListener("dblclick", (e) => {
      e.preventDefault();
      const p = toSvg(e.clientX, e.clientY);
      zoomAt(2, p.x, p.y, true);
    });

    // Mouse drag to pan (only when zoomed in). A drag never counts as a click on a neighborhood.
    svg.addEventListener("pointerdown", (e) => {
      if (e.pointerType !== "mouse" || e.button !== 0 || !svg.classList.contains("zoomed")) return;
      Z.drag = { x: e.clientX, y: e.clientY, v: { ...Z.v } };
      Z.moved = false;
    });
    window.addEventListener("pointermove", (e) => {
      if (!Z.drag) return;
      const dx = e.clientX - Z.drag.x, dy = e.clientY - Z.drag.y;
      if (!Z.moved && Math.hypot(dx, dy) < 4) return;
      Z.moved = true;
      svg.classList.add("dragging");
      hideHover();
      const r = svg.getBoundingClientRect();
      setView({ ...Z.drag.v, x: Z.drag.v.x - dx / r.width * Z.drag.v.w, y: Z.drag.v.y - dy / r.height * Z.drag.v.h });
    });
    window.addEventListener("pointerup", () => {
      if (Z.drag && Z.moved) markSelected();
      Z.drag = null;
      svg.classList.remove("dragging");
    });
    svg.addEventListener("click", (e) => {
      if (Z.moved) { e.stopPropagation(); e.preventDefault(); Z.moved = false; }
    }, true);

    // Phones: two fingers pinch-zoom; one finger pans only when zoomed in (otherwise the page scrolls).
    const dist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
    const mid = (t) => ({ x: (t[0].clientX + t[1].clientX) / 2, y: (t[0].clientY + t[1].clientY) / 2 });
    svg.addEventListener("touchstart", (e) => {
      if (e.touches.length === 2) {
        Z.pinch = { d: dist(e.touches), m: mid(e.touches), v: { ...Z.v } };
        Z.drag = null;
      } else if (e.touches.length === 1) {
        const t = e.touches[0], now = Date.now();
        if (now - Z.lastTap < 300) {   // double-tap to zoom in
          e.preventDefault();
          const p = toSvg(t.clientX, t.clientY);
          zoomAt(2, p.x, p.y, true);
          Z.lastTap = 0;
          return;
        }
        Z.lastTap = now;
        if (svg.classList.contains("zoomed")) Z.drag = { x: t.clientX, y: t.clientY, v: { ...Z.v }, touch: true };
        Z.moved = false;
      }
    }, { passive: false });
    svg.addEventListener("touchmove", (e) => {
      const r = svg.getBoundingClientRect();
      if (Z.pinch && e.touches.length === 2) {
        e.preventDefault();
        const s = dist(e.touches) / Z.pinch.d, m = mid(e.touches), v0 = Z.pinch.v;
        const cx = v0.x + (Z.pinch.m.x - r.left) / r.width * v0.w, cy = v0.y + (Z.pinch.m.y - r.top) / r.height * v0.h;
        const w = v0.w / s, h = v0.h / s;
        setView({ x: cx - (Z.pinch.m.x - r.left) / r.width * w - (m.x - Z.pinch.m.x) / r.width * w,
                  y: cy - (Z.pinch.m.y - r.top) / r.height * h - (m.y - Z.pinch.m.y) / r.height * h, w, h });
        Z.moved = true;
      } else if (Z.drag && Z.drag.touch && e.touches.length === 1) {
        const t = e.touches[0], dx = t.clientX - Z.drag.x, dy = t.clientY - Z.drag.y;
        if (!Z.moved && Math.hypot(dx, dy) < 6) return;
        e.preventDefault();
        Z.moved = true;
        setView({ ...Z.drag.v, x: Z.drag.v.x - dx / r.width * Z.drag.v.w, y: Z.drag.v.y - dy / r.height * Z.drag.v.h });
      }
    }, { passive: false });
    svg.addEventListener("touchend", (e) => {
      if (e.touches.length < 2) Z.pinch = null;
      if (e.touches.length === 0) { if (Z.moved) markSelected(); Z.drag = null; }
    });
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
    const u = unitsPerPixel(), view = Z.v || { x: 0, y: 0, w: vb.width, h: vb.height };
    const padX = 9 * u, padY = 5 * u, gap = 6 * u, w = tb.width + padX * 2, h = tb.height + padY * 2;
    const z = 1 / u;
    let x = b.x + b.width / 2 - w / 2, y = b.y - h - gap;          // above the shape...
    if (y < view.y + 4 / z) y = b.y + b.height + gap;               // ...or below if it's at the top edge
    const left = view.x + view.w * cardCover() + 4 / z;            // keep the name tag clear of the card
    x = Math.max(left, Math.min(view.x + view.w - w - 4 / z, x));
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
    card.querySelector(".close").addEventListener("click", closeSelection);
    showPeek(el, h);
    card.querySelector(".share").addEventListener("click", (ev) => copyLink(ev.currentTarget));
    syncURL();
    card.hidden = false;
    paint();
  }

  // Phones: the card sits below the map, so show a slim bar on the map that points to it.
  function showPeek(el, h) {
    const peek = $("peek");
    if (!peek) return;
    const top = h && h.top ? `${MOODS[h.top].emoji} ${MOODS[h.top].label} ${fmt(h.moods[h.top])}` : (h ? `${fmt(h.total)} reports` : "No reports");
    $("peek-open").innerHTML = `<span class="pk-name">${escapeHTML(el.dataset.name)}</span><span class="pk-top">${top}</span><span class="pk-go">Details ↓</span>`;
    peek.hidden = false;
    peek.closest(".map-wrap").classList.add("has-peek");
  }

  // Close the selected neighborhood and glide back out to the whole city, so you're never stuck zoomed in.
  function closeSelection() {
    selected = null;
    $("card").hidden = true;
    hidePeek();
    paint();
    syncURL();
    if (Z.base && Z.v && Z.v.w < Z.base.w - 0.5) animateTo({ ...Z.base });
  }

  function isPhoneLayout() {
    return getComputedStyle($("card")).position !== "absolute";
  }

  function hidePeek() {
    const peek = $("peek");
    if (!peek) return;
    peek.hidden = true;
    peek.closest(".map-wrap").classList.remove("has-peek");
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
    set("city", PAGE_CITY ? "" : CITY_KEY);
    set("day", dayIndex === 0 ? "" : days[dayIndex]);
    set("hood", selected || "");
    set("mode", mode === "top" ? "" : mode);
    history.replaceState(null, "", url);
    countHood();
  }

  // Page views are counted by GoatCounter on load (cookie-free, see privacy.html). Opening a
  // neighborhood doesn't reload the page, so count it once here, by name only.
  let lastCounted = null;
  function countHood() {
    if (!selected || selected === lastCounted || !window.goatcounter || !goatcounter.count) return;
    lastCounted = selected;
    const name = paths[selected] ? paths[selected].dataset.name : selected;
    goatcounter.count({ path: `${CITY_KEY} / ${name}`, title: `${name} (${CITY_KEY})`, event: true });
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
      zoomToHood(id);
      // On phones, line the search bar up with the top of the screen so the search, the whole map
      // and its details bar fit on one screen.
      // (Wait for the keyboard to slide away first, or iOS cancels the scroll.)
      if (isPhoneLayout()) setTimeout(() => $("hood-search").closest(".map-wrap").scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" }), 350);
      else $("map").scrollIntoView({ behavior: "smooth", block: "nearest" });
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
    const old = btn.textContent, link = location.href;
    try {
      await navigator.clipboard.writeText(link);
      btn.textContent = "✓ Link copied";
    } catch (_) {
      window.prompt("Copy this link:", link);
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
    entry = await getJSON(`${BASE}days/${date}.json`);
    $("day-label").textContent = niceDate(date);
    $("prev").disabled = i >= days.length - 1;
    $("next").disabled = i <= 0;
    const w = entry.weather;
    $("kicker").textContent = `${entry.weekday}, ${niceDate(date).replace(/^\w+, /, "")} · ${fmt(entry.total)} requests to 311`
      + (w ? ` · ${w.high_f}°F high, ${w.low_f}°F low` : "");
    $("headline").textContent = entry.words.headline;
    $("blurb").textContent = entry.words.blurb;
    document.title = `${entry.words.headline} · CityMoods ${CITY.name}`;
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
      const times = r.n === 1 ? "Picked once" : `Picked ${fmt(r.n)} times`;
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
    el.textContent = `The city's data currently runs through ${when}, so ${niceDate(days[0])} is the newest full day. ${CITY_KEY === "nyc" ? "New York usually posts each day's requests the following evening." : `${CITY.name} usually posts each day's requests by the next morning.`}`;
  }

  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }


  async function setupCities() {
    // Header switcher and city-specific wording. Only cities that have data are listed.
    let list = [];
    try { list = (await getJSON("data/cities.json")).cities || []; } catch (_) { /* single-city fallback */ }
    renderTabs(list, CITY_KEY);
    $("city-people").textContent = CITY.people || "people";
    $("sources").innerHTML = (CITY.sources || []).map(([label, href]) => `<a href="${href}">${escapeHTML(label)}</a>`).join(" and ");
    $("not-affiliated").textContent = `the City of ${CITY.name}`;
    $("city-data-title").textContent = `Download ${CITY.name}'s data`;
    $("city-data").href = `data/#${CITY_KEY}`;
    $("city-trends").hidden = CITY_KEY !== "chicago";   // Trends is Chicago-only for now
    // NYC has a "problem detail" level under each complaint; Chicago's menu has just the request type.
    $("gripes-hint").textContent = CITY_KEY === "nyc"
      ? `The "problem detail" ${CITY.people} picked from the 311 menu.`
      : `The request type ${CITY.people} picked from the 311 menu.`;
  }

  // City tabs in the header (shared with the front page, where none is active).
  function renderTabs(list, active) {
    $("city-tabs").innerHTML = list.map((c) =>
      `<a href="${c.key}/"${c.key === active ? ' class="on" aria-current="page"' : ""}>${escapeHTML(c.name)}</a>`).join("");
    const on = $("city-tabs").querySelector(".on");
    if (on) on.scrollIntoView({ block: "nearest", inline: "center" });
  }
  window.CityMoodsTabs = renderTabs;

  async function start() {
    if (MOVING) return;
    if (IS_HOME) {
      document.body.classList.add("is-home");
      return window.CityMoodsHome && window.CityMoodsHome.render();
    }
    try {
      const [index, geo] = await Promise.all([getJSON(`${BASE}index.json`), getJSON(`${BASE}neighborhoods.geojson`)]);
      MOODS = index.moods;
      days = index.days;
      if (index.city) CITY = index.city;
      await setupCities();
      drawMap(geo);
      $("prev").addEventListener("click", () => loadDay(Math.min(days.length - 1, dayIndex + 1)));
      $("next").addEventListener("click", () => loadDay(Math.max(0, dayIndex - 1)));
      document.querySelectorAll(".chip[data-mode]").forEach((c) =>
        c.addEventListener("click", () => setMode(c.dataset.mode)));
      setupSearch(geo);
      $("peek-open").addEventListener("click", () => $("card").scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" }));
      $("peek-close").addEventListener("click", closeSelection);
      $("map").addEventListener("pointerleave", hideHover);
      window.addEventListener("scroll", hideHover, { passive: true });
      const params = new URL(location.href).searchParams;
      const wantMode = params.get("mode");
      if (wantMode === "distinct" || MOODS[wantMode]) mode = wantMode;
      const wantHood = params.get("hood");
      if (wantHood && paths[wantHood]) selected = wantHood;
      await loadDay(Math.max(0, days.indexOf(params.get("day"))));
      if (selected) zoomToHood(selected, false);
    } catch (e) {
      $("headline").textContent = "The city's mood is loading slowly. Try again in a minute.";
      console.error(e);
    }
  }

  start();
})();
