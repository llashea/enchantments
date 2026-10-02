#!/usr/bin/env python3
"""Daily check of the Forest Service pages advisory.json summarizes.

Leah, build-26 review of the app (09:46): "why was it just checked September
24th? Is there a way we can make this more live?" A person still writes the
summary. This job only notices when the pages it was written from change:
the forest alerts list (alerts that touch this trip) and the storm-damage
order's "Last updated" date. On a change it writes today's date to
advisory.json as sourcesChangedOn. The app and both web pages compare that
with checkedOn and say "the Forest Service pages changed after this summary
was written" until a person re-reads them and moves checkedOn forward.

It never edits the summary text. It never says what changed means.

    python3 tools/advisory_watch/watch.py            # fetch, compare, write
    python3 tools/advisory_watch/watch.py --dry-run  # fetch and print only
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ALERTS_URL = "https://www.fs.usda.gov/r06/okanogan-wenatchee/alerts"
ORDER_URL = "https://www.fs.usda.gov/r06/okanogan-wenatchee/alerts/storm-damaged-roads-closure-wenatchee-river-district"
UA = "enchantmentstraverse.app advisory watch (support@enchantmentstraverse.app)"
# An alert counts when its link names this district, the whole forest, or a
# place on this trip. Alerts for other districts would only cry wolf.
RELEVANT = re.compile(r"wenatchee-river|forestwide|forest-wide|alpine-lakes|enchantment|icicle|eightmile|leavenworth|public-use-restriction|campfire-ban")

HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
ROOT = HERE.parent.parent
ADVISORY = ROOT / "advisory.json"


def fetch(url: str) -> str:
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001 - retried, then raised
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"could not fetch {url}: {last}")


def relevant_alerts(html: str) -> list[str]:
    slugs = set(re.findall(r'href="/r06/okanogan-wenatchee/alerts/([a-z0-9-]+)"', html))
    return sorted(s for s in slugs if RELEVANT.search(s))


def last_updated(html: str) -> str | None:
    text = re.sub(r"<[^>]+>", " ", html)
    m = re.search(r"Last updated\s+([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    return m.group(1) if m else None


def main_text(html: str) -> str:
    """The page's own content: inside <main>, scripts and tags stripped,
    whitespace collapsed. The site header and footer change on their own."""
    m = re.search(r"<main\b.*?</main>", html, re.S)
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", m.group(0) if m else html, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def cited_pages(advisory: dict) -> list[str]:
    """Every page the summary and the items cite, except the forest-wide alerts
    index (its whole text moves with alerts on other districts; the slug list
    covers it)."""
    urls = {i.get("sourceUrl") for i in advisory.get("items", [])}
    urls.add((advisory.get("summary") or {}).get("sourceUrl"))
    return sorted(u for u in urls if isinstance(u, str) and u.startswith("https://") and u.rstrip("/") != ALERTS_URL)


def revision(state: dict) -> str:
    return fingerprint(json.dumps(state, sort_keys=True))


def compare(old: dict | None, new: dict) -> list[str]:
    """Plain-language list of what moved. Empty when nothing did."""
    if old is None:
        return []
    out = []
    added = sorted(set(new["alerts"]) - set(old.get("alerts", [])))
    removed = sorted(set(old.get("alerts", [])) - set(new["alerts"]))
    out += [f"alert added: {s}" for s in added]
    out += [f"alert removed: {s}" for s in removed]
    if new["orderLastUpdated"] != old.get("orderLastUpdated"):
        out.append(f"storm-damage order last updated: {old.get('orderLastUpdated')} -> {new['orderLastUpdated']}")
    old_pages = old.get("pages", {})
    for url, fp in sorted(new.get("pages", {}).items()):
        if url in old_pages and old_pages[url] != fp:
            out.append(f"page text changed: {url.rsplit('/', 1)[-1]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    advisory = json.loads(ADVISORY.read_text())
    alerts_html = fetch(ALERTS_URL)
    order_html = fetch(ORDER_URL)
    pages = {}
    for url in cited_pages(advisory):
        text = main_text(fetch(url))
        # A block page or an error page is a fetch problem, not a change.
        if len(text) < 300:
            print(f"{url} came back nearly empty; leaving everything alone", file=sys.stderr)
            return 1
        pages[url] = fingerprint(text)
    new = {"alerts": relevant_alerts(alerts_html), "orderLastUpdated": last_updated(order_html), "pages": pages}
    # A page that came back without what we read is a fetch problem, not a change.
    if len(new["alerts"]) == 0 or new["orderLastUpdated"] is None:
        print("pages came back without alerts or a last-updated date; leaving everything alone", file=sys.stderr)
        return 1

    old = json.loads(STATE.read_text()) if STATE.exists() else None
    changes = compare(old, new)
    today = dt.date.today().isoformat()
    print(json.dumps({"alerts": len(new["alerts"]), "orderLastUpdated": new["orderLastUpdated"], "pages": len(pages), "revision": revision(new), "changes": changes}, indent=1))
    if args.dry_run:
        return 0

    STATE.write_text(json.dumps(new, indent=2) + "\n")
    # sourcesRevision is what the pages look like now. A person who re-reads
    # them copies it into checkedRevision; the app and site warn while the two
    # differ, which a same-day change still trips (review, 10/2: a date alone
    # could not tell a morning check from an evening change).
    rev = revision(new)
    if changes or advisory.get("sourcesRevision") != rev:
        if changes:
            advisory["sourcesChangedOn"] = today
            advisory["sourcesChanged"] = changes[:10]
        advisory["sourcesRevision"] = rev
        ADVISORY.write_text(json.dumps(advisory, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
