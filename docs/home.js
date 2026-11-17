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

  // "yesterday" only when it really was yesterday; otherwise the weekday ("on Monday").
  function dayWords(iso) {
    const d = new Date(iso + "T12:00:00"), y = new Date(); y.setDate(y.getDate() - 1);
    const weekday = d.toLocaleDateString("en-US", { weekday: "long" });
    const isYesterday = d.toDateString() === y.toDateString();
    return { phrase: isYesterday ? "yesterday" : `on ${weekday}`, title: isYesterday ? "Yesterday's" : `${weekday}'s`, weekday };
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
        <div class="cc-mood"><p class="cc-kicker">The mood</p><p class="cc-line"></p></div>
        <p class="cc-kicker cc-stat-k">&nbsp;</p>
        <div class="cc-stat"></div>
        <p class="cc-label">&nbsp;</p>
        <p class="cc-rare"></p>
        <p class="cc-foot"><span class="cc-date"></span><span class="cc-open" aria-hidden="true">→</span></p>
      </div></a>`;
  }

  // What made this city's day different, as one big number plus a short label:
  // its biggest spike over normal, else the neighborhood that stood out most, else its top request.
  function dayHook(day, MOODS) {
    const spike = (day.detail_spikes || [])[0];
    if (spike && spike.typical) {
      const r = spike.n / spike.typical;
      return { kicker: "Biggest jump", mood: spike.mood, stat: `${r >= 10 ? Math.round(r) : r.toFixed(1)}×`, unit: "normal", label: spike.name };
    }
    const standout = Object.values(day.neighborhoods || {}).filter((h) => h.distinct)
      .sort((a, b) => b.distinct.x - a.distinct.x)[0];
    if (standout && standout.distinct.x >= 2) {
      const d = standout.distinct;
      return { kicker: "Standout area", mood: d.mood, stat: `${Math.round(d.x)}×`, unit: "city rate", label: `${d.name} in ${standout.name}` };
    }
    const top = (day.top_details || day.top_types || [])[0];
    return top ? { kicker: "Top request", mood: top.mood, stat: fmt(top.n), unit: "reports", label: top.name } : null;
  }

  // When an item's category is "everything else", pick a fitting mood from its own words.
  const WORD_MOODS = [[/rat|rodent|mice|mouse|pigeon|animal|bee|wasp|coyote|dog/i, "critters"], [/flood|sewer|water|leak|drain/i, "water"],
    [/heat|hot water/i, "heat"], [/noise|loud|music|bark/i, "noise"], [/tree|branch|weed|park/i, "trees"],
    [/park|car|vehicle|scooter|driveway|meter/i, "parking"], [/trash|litter|garbage|dump|graffiti|debris/i, "trash"],
    [/light|signal|sign|pothole|sidewalk|street|pavement/i, "streets"], [/building|repair|plumb|mold|elevator/i, "housing"]];
  function guessMood(label, MOODS) {
    const hit = WORD_MOODS.find(([rx]) => rx.test(label || ""));
    return hit && MOODS[hit[1]] ? MOODS[hit[1]] : { emoji: "🔍", color: "#B9BEC7" };
  }

  async function fillCard(c) {
    const card = $(`card-${c.key}`);
    try {
      const [index, day, geo] = await Promise.all([
        getJSON(`data/${c.key}/index.json`), getJSON(`data/${c.key}/latest.json`), getJSON(`data/${c.key}/neighborhoods.geojson`)]);
      const MOODS = index.moods;
      const hook = dayHook(day, MOODS);
      if (hook) {
        const m = MOODS[hook.mood] && hook.mood !== "other" ? MOODS[hook.mood] : guessMood(hook.label, MOODS);
        card.querySelector(".cc-stat").innerHTML =
          `<span class="badge" style="--tint:${m.color}" aria-hidden="true">${m.emoji}</span>`
          + `<b>${esc(hook.stat)}</b><span class="unit">${esc(hook.unit)}</span>`;
        card.querySelector(".cc-label").textContent = hook.label;
        card.querySelector(".cc-stat-k").textContent = hook.kicker;
      }
      // Claude's short card line. The card labels it "The mood", so drop an opener like "Monday's mood:".
      let line = (day.words && day.words.card_line) || "";
      line = line.replace(/^\s*(\w+day'?s?|today'?s?|the)?\s*mood\s*[:—-]\s*/i, "");
      line = line ? line[0].toUpperCase() + line.slice(1) : "";
      if (line) card.querySelector(".cc-line").textContent = line;
      else card.querySelector(".cc-mood").remove();
      const rare = (day.rare_finds || [])[0];
      if (rare) {
        const el = card.querySelector(".cc-rare");
        el.innerHTML = `<span aria-hidden="true">🔎</span> Rare find: <i>${esc(rare.name)}</i>`;
        el.title = `Rare find: ${rare.name}`;
      }
      card.querySelector(".cc-date").textContent =
        `${new Date(day.date + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })} · ${fmt(day.total)} requests`;
      card.setAttribute("aria-label", `${c.name}, ${niceDate(day.date)}: ${hook ? `${hook.label}, ${hook.stat} ${hook.unit}` : ""}.`
        + (rare ? ` Rare find: ${rare.name}.` : ""));
      miniMap(card.querySelector("svg"), geo, c.center_lat || 40,
        (id) => { const h = day.neighborhoods[id]; return h && h.top ? MOODS[h.top].color : "var(--empty)"; });
      return day.date;
    } catch (e) {
      card.querySelector(".cc-label").textContent = "This city's mood didn't load. Try again in a minute.";
      console.error(e);
      return null;
    }
  }

  async function render() {
    $("home").hidden = false;
    document.title = "CityMoods: what cities complain about, mapped";
    let cities = [];
    try { cities = (await getJSON("data/cities.json")).cities || []; } catch (e) { console.error(e); }
    if (window.CityMoodsTabs) window.CityMoodsTabs(cities, null);
    rotate(cities.map((c) => c.name));
    $("city-cards").innerHTML = cities.map(skeleton).join("");
    const results = await Promise.all(cities.map(fillCard));
    const dates = results.filter(Boolean).sort();
    if (dates.length) {
      const newest = dates[dates.length - 1], words = dayWords(newest);
      $("home-date").textContent = `Latest: ${niceDate(newest)} · ${cities.length} cities`;
      $("hero-day").textContent = words.phrase;
      $("cards-title").textContent = `${words.title} moods`;
      // Only call out a city when it's actually behind the others (e.g. it posted late).
      cities.forEach((c, i) => {
        const d = results[i];
        if (!d || d >= newest) return;
        const card = $(`card-${c.key}`), date = card.querySelector(".cc-date");
        date.classList.add("behind");
        date.title = `${c.name} hasn't posted ${words.weekday}'s requests yet, so this shows ${dayWords(d).weekday}.`;
        const note = document.createElement("p");
        note.className = "cc-behind";
        note.textContent = `${c.name} hasn't posted ${words.weekday} yet`;
        card.querySelector(".cc-foot").before(note);
      });
    }
    $("sources").textContent = "each city's 311 service requests";
    $("not-affiliated").textContent = "any of these cities";
  }

  window.CityMoodsHome = { render };
})();
