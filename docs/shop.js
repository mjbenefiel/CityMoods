// CityMoods Shop: our own product page; checkout happens on Redbubble.
// To add or change a product, edit PRODUCTS (order here = order on the page). `url` is the exact Redbubble
// product page; if it's left empty the button opens the whole Redbubble shop. Photos live in /shop/img/ (made by brand/merch/make_tees.py).
(function () {
  const SHOP = "https://citymoods311.redbubble.com/";
  // Shirts link to the black Classic T-Shirt ("/lrcw"); the sticker links to its sticker page.
  const RB = "https://www.redbubble.com/i/";
  const PRODUCTS = [
    { slug: "retro-logo", title: "CityMoods Retro Night Skyline", kind: "Logo tee",
      blurb: "A night skyline, a crescent moon and our name in big 70s letters. The one to wear if you just like the maps.",
      featured: true, url: RB + "t-shirt/CityMoods-Retro-Night-Skyline-70s-City-Lights-Logo-by-citymoods311/185968890/lrcw" },
    { slug: "tree-trim", title: "Tree Trim Request (No Longer Being Accepted)", kind: "Chicago 311",
      blurb: "A real Chicago request type the city retired. People still pick it hundreds of times a week.",
      url: RB + "t-shirt/Tree-Trim-Request-No-Longer-Being-Accepted-Chicago-311-by-citymoods311/185968824/lrcw" },
    { slug: "alarm", title: "Alarm That Won't Stop", kind: "NYC 311",
      blurb: "Our plain-English name for NYC's real Noise › Alarm › Chronic complaint. Every New Yorker has filed it in their head.",
      url: RB + "t-shirt/Alarm-That-Won-t-Stop-NYC-311-Noise-Complaint-by-citymoods311/185968674/lrcw" },
    { slug: "banging", title: "Banging/Pounding", kind: "NYC 311",
      blurb: "A real NYC noise complaint. It's about the neighbors. Probably.",
      url: RB + "t-shirt/Banging-Pounding-NYC-311-Noise-Complaint-by-citymoods311/185968743/lrcw" },
    { slug: "sticker-i-called-311", title: "I Called 311. Status: Closed.", kind: "Sticker",
      blurb: "For anyone who's filed a 311 request and watched it get marked closed. Laptops, water bottles, bike helmets.",
      cta: "See the sticker on Redbubble",
      url: RB + "sticker/Called-311-Request-Status-Closed-by-citymoods311/185969048/7sgk" },
  ];

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const grid = document.getElementById("shop-grid");
  grid.innerHTML = PRODUCTS.map((p) => {
    const url = p.url || SHOP;
    return `<article class="product${p.featured ? " featured" : ""}">
  <a class="ph" href="${esc(url)}" target="_blank" rel="noopener" data-goatcounter-click="shop-${esc(p.slug)}" data-goatcounter-title="${esc(p.title)}" tabindex="-1" aria-hidden="true">
    <img src="/shop/img/${esc(p.slug)}.jpg?v=1" alt="" width="800" height="800" loading="lazy"></a>
  <div class="pinfo">
    <p class="kind">${esc(p.kind)}</p>
    <h2>${esc(p.title)}</h2>
    <p class="blurb">${esc(p.blurb)}</p>
    <a class="buy" href="${esc(url)}" target="_blank" rel="noopener" data-goatcounter-click="shop-${esc(p.slug)}" data-goatcounter-title="${esc(p.title)}">${esc(p.cta || "See it on Redbubble")} <span aria-hidden="true">↗</span><span class="sr"> (opens Redbubble in a new tab)</span></a>
  </div>
</article>`;
  }).join("");
})();
