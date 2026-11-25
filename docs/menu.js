// Site menu, shared by every page: a few links in the header on wide screens, and a ☰ button that opens a
// slide-out menu with everything (on phones it's the only way in). Edit the lists below to add a page:
// set a link's `on` to false to hide it.
(function () {
  const HEADER_LINKS = [
    { href: "/trends/", label: "Trends", on: true },
    { href: "/data/", label: "Data", on: true },
    { href: "/shop/", label: "Shop", on: true },
  ];
  const CITIES = [["nyc", "New York"], ["chicago", "Chicago"], ["la", "Los Angeles"], ["sf", "San Francisco"], ["boston", "Boston"]];
  const MORE = [
    { href: "https://ko-fi.com/citymoods311", label: "Support CityMoods", ext: true },
    { href: "mailto:admin@citymoods311.com?subject=Add%20my%20city%3A%20", label: "Want your city? Ask us" },
    { href: "mailto:admin@citymoods311.com?subject=CityMoods%20feedback", label: "Spot a problem? Tell us" },
    { href: "/privacy.html", label: "Privacy" },
  ];

  const path = location.pathname.replace(/index\.html$/, "");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const link = (l, cls) => {
    const cur = !l.ext && !l.href.startsWith("mailto:") && path === l.href ? ' aria-current="page"' : "";
    const ext = l.ext ? ' target="_blank" rel="noopener"' : "";
    return `<a${cls ? ` class="${cls}"` : ""} href="${esc(l.href)}"${ext}${cur}>${esc(l.label)}${l.ext ? ' <span aria-hidden="true">↗</span>' : ""}</a>`;
  };

  // Header: links + menu button. Pages without a header (none today) get one.
  let header = document.querySelector("header.top");
  if (!header) {
    header = document.createElement("header");
    header.className = "top";
    header.innerHTML = '<a class="brand" href="/" aria-label="CityMoods home"><img src="/favicon.svg" alt="" width="22" height="22"> CityMoods</a>';
    document.body.prepend(header);
  }
  const nav = document.createElement("div");
  nav.className = "site-nav";
  nav.innerHTML = HEADER_LINKS.filter((l) => l.on).map((l) => link(l)).join("") +
    '<button class="menu-btn" type="button" aria-label="Open menu" aria-expanded="false" aria-controls="site-menu">' +
    '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button>';
  header.appendChild(nav);

  // Slide-out menu
  const section = (title, items) => `<p class="menu-h">${esc(title)}</p>${items.join("")}`;
  const scrim = document.createElement("div");
  scrim.className = "menu-scrim";
  scrim.hidden = true;
  const menu = document.createElement("aside");
  menu.className = "menu";
  menu.id = "site-menu";
  menu.hidden = true;
  menu.setAttribute("role", "dialog");
  menu.setAttribute("aria-modal", "true");
  menu.setAttribute("aria-label", "Menu");
  menu.innerHTML =
    '<div class="menu-top"><a class="brand" href="/"><img src="/favicon.svg" alt="" width="22" height="22"> CityMoods</a>' +
    '<button class="menu-close" type="button" aria-label="Close menu">' +
    '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button></div>' +
    '<nav aria-label="Site">' +
    section("Maps", [link({ href: "/", label: "All cities" }), ...CITIES.map(([k, n]) => link({ href: `/${k}/`, label: n }))]) +
    section("Explore", HEADER_LINKS.filter((l) => l.on && !l.ext).map((l) => link(l))) +
    section("CityMoods", [...HEADER_LINKS.filter((l) => l.on && l.ext), ...MORE].map((l) => link(l))) +
    "</nav>";
  document.body.append(scrim, menu);

  const btn = nav.querySelector(".menu-btn");
  const focusables = () => [...menu.querySelectorAll("a, button")];
  let closeTimer;
  function open() {
    clearTimeout(closeTimer);
    scrim.hidden = menu.hidden = false;
    requestAnimationFrame(() => document.documentElement.classList.add("menu-open"));
    btn.setAttribute("aria-expanded", "true");
    menu.querySelector("nav a").focus();
  }
  function close(returnFocus = true) {
    document.documentElement.classList.remove("menu-open");
    btn.setAttribute("aria-expanded", "false");
    closeTimer = setTimeout(() => { scrim.hidden = menu.hidden = true; }, 220);
    if (returnFocus) btn.focus();
  }
  btn.addEventListener("click", open);
  scrim.addEventListener("click", () => close());
  menu.querySelector(".menu-close").addEventListener("click", () => close());
  menu.addEventListener("click", (ev) => { if (ev.target.closest("a") && !ev.target.closest('a[href^="mailto:"]')) close(false); });
  document.addEventListener("keydown", (ev) => {
    if (menu.hidden) return;
    if (ev.key === "Escape") return close();
    if (ev.key !== "Tab") return;
    const f = focusables(), first = f[0], last = f[f.length - 1];   // keep Tab inside the open menu
    if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
  });
})();

// Tip jar: a plain link to Ko-fi in our own style, at the top of the footer on every page except the Shop
// (which has its own Ko-fi line). Nothing loads from Ko-fi until someone clicks.
(function () {
  const footer = document.querySelector("footer");
  if (!footer || location.pathname.startsWith("/shop/")) return;
  const tip = document.createElement("div");
  tip.className = "tip";
  tip.innerHTML = '<p>Like the maps? They run on tips.</p>' +
    '<a class="tip-btn" href="https://ko-fi.com/citymoods311" target="_blank" rel="noopener" ' +
    'data-goatcounter-click="kofi-tip" data-goatcounter-title="Ko-fi tip button">Chip in for the maps ' +
    '<span aria-hidden="true">↗</span><span class="sr"> (opens Ko-fi in a new tab)</span></a>';
  footer.prepend(tip);
})();

// Email links: plenty of people have no mail app set up, so a mailto click does nothing for them.
// Copy the address too and say so, while still letting the mail app open for everyone else.
(function () {
  let toast;
  function show(msg) {
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "toast";
      toast.setAttribute("role", "status");
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add("on");
    clearTimeout(show.t);
    show.t = setTimeout(() => toast.classList.remove("on"), 3500);
  }
  document.addEventListener("click", (ev) => {
    const a = ev.target.closest && ev.target.closest('a[href^="mailto:"]');
    if (!a) return;
    const addr = decodeURIComponent(a.getAttribute("href").slice(7).split("?")[0]);
    const done = () => show(`Email address copied: ${addr}`);
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(addr).then(done, () => show(`Email us at ${addr}`));
    else show(`Email us at ${addr}`);
  });
})();
