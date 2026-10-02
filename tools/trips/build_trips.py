#!/usr/bin/env python3
"""Build the five /trips/ pages from tools/trips/src/*.md.

Leah, 2026-09-28: articles on where parties camped, by permit zone and trip
length (docs/research/guide-article-links-plan-2026-09-28.md in the app repo).
ChatGPT drafted the copy 2026-10-02 from the research brief; Claude checked it
fact by fact before it landed here. Edit the .md source, run this, commit.

Each source file: line 1 "title: ...", line 2 "description: ...", a blank
line, then the body in Markdown starting with its H1. Zone sections are H2s
starting "If you have a ... permit"; each gets the anchor the app links to.

    python3 tools/trips/build_trips.py
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent / "src"
TEMPLATE = ROOT / "packing" / "index.html"
SITE = "https://enchantmentstraverse.app"

# slug -> (output dir relative to ROOT, depth for ../ paths)
PAGES = [
    ("trips", "trips", 1),
    ("1-night", "trips/1-night", 2),
    ("2-nights", "trips/2-nights", 2),
    ("3-nights", "trips/3-nights", 2),
    ("4-to-7-nights", "trips/4-to-7-nights", 2),
]
ZONE_ANCHORS = {
    "core": "core",
    "colchuck": "colchuck",
    "snow": "snow",
    "stuart": "stuart",
    "eightmile/caroline": "eightmile-caroline",
}
CHECKED = "Agency facts checked September 28, 2026, for the 2026 season. Trip reports read September 28, 2026."


def read_src(slug: str) -> tuple[str, str, str]:
    text = (SRC / f"{slug}.md").read_text()
    lines = text.split("\n")
    assert lines[0].startswith("title: ") and lines[1].startswith("description: "), slug
    return lines[0][7:].strip(), lines[1][13:].strip(), "\n".join(lines[3:]).strip()


def zone_id(h2: str) -> str | None:
    m = re.match(r"If you have an? (.+?) permit", h2, re.I)
    if not m:
        return None
    return ZONE_ANCHORS.get(m.group(1).strip().lower())


def body_html(md: str) -> tuple[str, str, str, list[tuple[str, str]]]:
    """(h1, lede, rest_html, [(id, h2)])"""
    h1 = re.match(r"#\s+(.+)", md).group(1).strip()
    rest = md.split("\n", 1)[1].strip()
    lede, _, rest = rest.partition("\n\n")
    out = markdown.markdown(rest)
    toc = []

    def h2(m: re.Match) -> str:
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))
        zid = zone_id(title) or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        toc.append((zid, title))
        return f'<h2 id="{zid}">{m.group(1)}</h2>'

    out = re.sub(r"<h2>(.*?)</h2>", h2, out)
    return h1, markdown.markdown(lede), out, toc


def external(s: str) -> str:
    # Off-site links open in a new tab, like the rest of the site.
    return re.sub(r'<a href="(https?://[^"]+)">', r'<a href="\1" target="_blank" rel="noopener">', s)


def page(slug: str, out_dir: str, depth: int) -> str:
    title, desc, md = read_src(slug)
    h1, lede, rest, toc = body_html(md)
    up = "../" * depth
    src = TEMPLATE.read_text()
    head_end = src.find("<main")
    head = src[:head_end]
    foot = src[src.find("</main>"):]
    old_t = re.search(r"<title>(.*?)</title>", head).group(1)
    old_d = re.search(r'<meta name="description" content="(.*?)"', head).group(1)
    page_t = f"{title} — Enchantments Traverse Planner"
    head = head.replace(old_t, html.escape(page_t, quote=False)).replace(old_d, html.escape(desc))
    head = head.replace(f"{SITE}/packing/", f"{SITE}/{out_dir}/")
    head = head.replace('href="../', f'href="{up}').replace('src="../', f'src="{up}')
    # nav: the template is the packing page, so Packing list is the current
    # link there. Here it is a plain link, and Trips is current on /trips/.
    head = head.replace('<a href="./" aria-current="page">Packing list</a>', f'<a href="{up}packing/">Packing list</a>')
    if slug == "trips":
        head = head.replace(f'<a href="{up}trips/">Trips</a>', f'<a href="{up}trips/" aria-current="page">Trips</a>', 1)
    foot = foot.replace('href="../', f'href="{up}')
    aside = "".join(f'<a href="#{i}">{html.escape(t)}</a>' for i, t in toc)
    main = (
        f'<main class="legalPage" id="main-content"><header class="legalHero shell"><p class="eyebrow">Trips</p>'
        f"<h1>{html.escape(h1)}</h1>{external(lede)}<p class=\"affiliate\">{CHECKED}</p></header>"
        f'<div class="legalLayout shell"><aside aria-label="On this page">{aside}</aside>'
        f'<article class="legalCopy">{external(rest)}</article></div>'
    )
    return head + main + foot


def main() -> None:
    for slug, out_dir, depth in PAGES:
        d = ROOT / out_dir
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page(slug, out_dir, depth))
        print("wrote", out_dir + "/index.html")


if __name__ == "__main__":
    main()
