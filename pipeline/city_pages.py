"""Write each city's own page, docs/<city>/index.html, so its address (…/CityMoods/chicago/) is what people
see, copy and share, and link previews show that city's card and latest headline.

The page is docs/index.html with a <base href="../"> (so every file and data path still works), the city
marked on <html data-city="…">, and the title and preview tags swapped for the city's. The nightly build calls
write_city_page() after each city; after editing docs/index.html by hand, regenerate them all with:

    python3 pipeline/city_pages.py
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from common import DATA, SITE

DOCS = DATA.parent


def _set_meta(page: str, attr: str, name: str, value: str) -> str:
    pattern = re.compile(rf'(<meta {attr}="{re.escape(name)}" content=")[^"]*(")')
    if not pattern.search(page):
        raise SystemExit(f"docs/index.html is missing <meta {attr}=\"{name}\">")
    return pattern.sub(lambda m: m.group(1) + value + m.group(2), page, count=1)


def write_city_page(key: str, name: str, day: dict):
    e = lambda t: html.escape(t, quote=True)
    words = day.get("words") or {}
    title = f"What {name} complained about on {day['weekday']} · CityMoods"
    desc = (words.get("headline") or f"{name}'s 311 requests, mapped by neighborhood.").rstrip(".") + ". Mapped, ranked and roasted."
    page = (DOCS / "index.html").read_text()
    page = page.replace('<html lang="en">', f'<html lang="en" data-city="{e(key)}">', 1)
    page = page.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n<base href="../">', 1)
    page = re.sub(r"<title>[^<]*</title>", lambda m: f"<title>{e(title)}</title>", page, count=1)
    for attr, tag, value in [
        ("name", "description", desc),
        ("property", "og:title", title),
        ("property", "og:description", desc),
        ("property", "og:url", f"{SITE}{key}/"),
        ("property", "og:image", f"{SITE}share/{key}.png?v={day['date']}"),
        ("property", "og:image:alt", f"Map of {name} neighborhoods colored by their top 311 complaint"),
    ]:
        page = _set_meta(page, attr, tag, e(value))
    out = DOCS / key / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page)


def main():
    for c in json.loads((DATA / "cities.json").read_text())["cities"]:
        latest = DATA / c["key"] / "latest.json"
        if latest.exists():
            write_city_page(c["key"], c["name"], json.loads(latest.read_text()))
            print("wrote", f"docs/{c['key']}/index.html")


if __name__ == "__main__":
    main()
