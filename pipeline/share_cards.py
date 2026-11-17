"""Make the link-preview images (docs/share/*.png, 1200x630) shown when someone shares CityMoods.

One card for the whole site and one per city, each with the city's mood map from its latest day.
Run by hand when a city is added or the look changes (not part of the nightly job):

    python3 pipeline/share_cards.py

Needs Google Chrome installed (it renders the card HTML to PNG in headless mode).
"""
from __future__ import annotations

import json
import math
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA = DOCS / "data"
OUT = DOCS / "share"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SHORT = {"nyc": "New York", "chicago": "Chicago", "la": "Los Angeles", "sf": "San Francisco", "boston": "Boston"}

CSS = """
*{box-sizing:border-box;margin:0}
body{width:1200px;height:630px;background:#14161B;color:#ECEDEF;font-family:-apple-system,system-ui,sans-serif;
  display:flex;overflow:hidden}
.text{flex:1;padding:64px 0 56px 72px;display:flex;flex-direction:column}
.brand{display:flex;align-items:center;gap:12px;font:600 26px -apple-system,system-ui,sans-serif;color:#ECEDEF}
.brand img{width:40px;height:40px}
h1{font:700 64px/1.06 "Iowan Old Style",Palatino,Georgia,serif;margin-top:auto;letter-spacing:-0.5px}
h1 em{font-style:normal;color:#F06A8F}
.sub{font:500 28px -apple-system,system-ui,sans-serif;color:#9AA0AB;margin-top:18px}
.legend{display:flex;flex-wrap:wrap;gap:10px 18px;margin-top:30px;font:500 19px -apple-system,system-ui,sans-serif;color:#9AA0AB}
.legend span{display:flex;align-items:center;gap:7px}
.legend i{width:14px;height:14px;border-radius:4px;display:inline-block}
.map{width:520px;display:flex;align-items:center;justify-content:center;padding:36px 48px 36px 0}
.map svg{width:100%;height:100%}
.minis{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-top:34px;width:1056px}
.minis div{background:#1C1F26;border:1px solid #2C3039;border-radius:14px;padding:10px 10px 8px;text-align:center;
  font:600 17px -apple-system,system-ui,sans-serif;color:#ECEDEF}
.minis svg{width:100%;height:150px;display:block;margin-bottom:6px}
.site .text{padding-right:72px}
.site h1{margin-top:44px;font-size:62px}
"""


def city_svg(key: str, moods: dict) -> str:
    geo = json.loads((DATA / key / "neighborhoods.geojson").read_text())
    hoods = json.loads((DATA / key / "latest.json").read_text())["neighborhoods"]
    rings = []
    for f in geo["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        rings.append((f["id"], [r for p in polys for r in p]))
    xs = [x for _, rs in rings for r in rs for x, _ in r]
    ys = [y for _, rs in rings for r in rs for _, y in r]
    k = math.cos(math.radians((min(ys) + max(ys)) / 2))
    w, h = (max(xs) - min(xs)) * k, max(ys) - min(ys)
    s = 1000 / max(w, h)
    paths = []
    for hid, rs in rings:
        top = (hoods.get(hid) or {}).get("top")
        fill = moods[top]["color"] if top in moods else "#2A2E36"
        d = "".join("M" + "L".join(f"{(x - min(xs)) * k * s:.1f},{(max(ys) - y) * s:.1f}" for x, y in r) + "Z" for r in rs)
        paths.append(f'<path d="{d}" fill="{fill}" fill-rule="evenodd"/>')
    return (f'<svg viewBox="-8 -8 {w * s + 16:.0f} {h * s + 16:.0f}" preserveAspectRatio="xMidYMid meet">'
            f'<g stroke="#14161B" stroke-width="1.6" stroke-linejoin="round">{"".join(paths)}</g></svg>')


def top_moods(key: str, moods: dict, n: int = 4) -> list[str]:
    day = json.loads((DATA / key / "latest.json").read_text())
    return [m["id"] for m in day["moods"] if m["id"] != "other"][:n]


def page(body: str, cls: str = "") -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head>'
            f'<body class="{cls}">{body}</body></html>')


def render(html: str, out: Path):
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "card.html"
        src.write_text(html.replace('src="favicon.svg"', f'src="{(DOCS / "favicon.svg").as_uri()}"'))
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--window-size=1200,630", f"--screenshot={out}", src.as_uri()],
                       check=True, capture_output=True)
    print("wrote", out.relative_to(ROOT))


def main():
    OUT.mkdir(exist_ok=True)
    cities = [c["key"] for c in json.loads((DATA / "cities.json").read_text())["cities"]]
    moods = json.loads((DATA / cities[0] / "index.json").read_text())["moods"]
    brand = '<div class="brand"><img src="favicon.svg" alt="">CityMoods</div>'

    for key in cities:
        legend = "".join(f'<span><i style="background:{moods[m]["color"]}"></i>{moods[m]["emoji"]} {moods[m]["label"]}</span>'
                         for m in top_moods(key, moods))
        body = (f'<div class="text">{brand}<h1>What <em>{SHORT.get(key, key)}</em> complained to 311 about.</h1>'
                f'<p class="sub">Mapped, ranked and roasted.</p><div class="legend">{legend}</div></div>'
                f'<div class="map">{city_svg(key, moods)}</div>')
        render(page(body), OUT / f"{key}.png")

    minis = "".join(f'<div>{city_svg(k, moods)}{SHORT.get(k, k)}</div>' for k in cities)
    body = (f'<div class="text">{brand}<h1>What cities complained to 311 about yesterday.</h1>'
            f'<p class="sub">Mapped, ranked and roasted, every night.</p><div class="minis">{minis}</div></div>')
    render(page(body, "site"), OUT / "site.png")


if __name__ == "__main__":
    main()
