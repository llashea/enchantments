#!/usr/bin/env python3
"""
Build snow.json: NOAA's modeled snow depth at eight places on the traverse.

The Enchantments Traverse Planner app reads
https://enchantmentstraverse.app/snow.json and shows it on Forecast and
fires. This script is the only thing that writes that file. It runs once a
day from .github/workflows/snow.yml. Standard library only.

What it does
  1. Downloads the newest SNODAS masked daily tar from NSIDC (dataset
     G02158), falling back one day at a time for up to --max-back days.
  2. Reads the snow-depth grid (product 1036). The grid's size, corner,
     cell size, units and no-data value all come from the header that
     ships beside it. Nothing about the grid is assumed.
  3. Samples the 1 km cell that holds each place in POINTS.
  4. Asks the NRCS AWDB API for the latest measured snow depth at the
     Icicle Creek SNOTEL station. If that fails the file is written without
     a "snotel" key. A missing reading is never written as zero.
  5. Writes snow.json, but only when the product date is newer than the one
     already in the file.

What it refuses to do
  It exits non-zero and writes nothing if the tar cannot be fetched, the
  grid does not match its header, the units are not millimetres, or any
  sampled cell holds the no-data value. A missing value is never published
  as 0.

The numbers are model output on a 1 km grid. They are not measurements.

Two copies
  This file lives in the website repo at tools/snow/build_snow_json.py,
  where the workflow runs it. The app repo keeps an identical copy at
  scripts/build-snow-json.py so the app's tests can pin POINTS against the
  app's own constants. Keep the two identical.

Source and citation
  National Operational Hydrologic Remote Sensing Center. 2004. Snow Data
  Assimilation System (SNODAS) Data Products at NSIDC, Version 1. Boulder,
  Colorado USA. NSIDC: National Snow and Ice Data Center.
  https://doi.org/10.7265/N5TB14TC.

Usage
  python3 tools/snow/build_snow_json.py                 write ../../snow.json if newer
  python3 tools/snow/build_snow_json.py --dry-run       print the JSON, write nothing
  python3 tools/snow/build_snow_json.py --date 2026-04-01 --dry-run
  python3 tools/snow/build_snow_json.py --force         write even if the date is not newer
"""

import argparse
import datetime as dt
import gzip
import io
import json
import math
import os
import re
import struct
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request

NSIDC_BASE = "https://noaadata.apps.nsidc.org/NOAA/G02158/masked"
AWDB_BASE = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"
USER_AGENT = "EnchantmentsTraversePlanner snow.json job (enchantments@milecheckapp.com)"

SOURCE = "NOAA NOHRSC SNODAS via NSIDC G02158"
CITATION = (
    "National Operational Hydrologic Remote Sensing Center. 2004. Snow Data "
    "Assimilation System (SNODAS) Data Products at NSIDC, Version 1. Boulder, "
    "Colorado USA. NSIDC: National Snow and Ice Data Center. "
    "https://doi.org/10.7265/N5TB14TC."
)

DEPTH_PRODUCT = "1036"

# Eight places on the mapped traverse, in walking order from the Stuart Lake
# Trailhead. Ids, names, coordinates and heights are the app's own records
# (access.seed.json, waypoints.seed.json, water.seed.json). The app pins this
# table against its constants in snowDepth.test.ts, so edit both or neither.
#
# heightFt is the app's height for the place, in feet. Six come from the
# seed record's elevation. The Stuart Lake Trailhead and Aasgard Pass have
# no elevation in their seed records, so theirs is the app's modeled track
# height at that vertex (1,047 m and 2,375 m).
#
# (id, name, lat, lon, heightFt)
POINTS = [
    ("access-stuart-lake-trailhead", "Stuart Lake Trailhead", 47.527755, -120.820866, 3435),
    ("water-colchuck-lake", "Colchuck Lake", 47.493152, -120.833794, 5571),
    ("landmark-aasgard-pass", "Aasgard Pass", 47.480785, -120.822454, 7792),
    ("water-perfection-lake", "Perfection Lake", 47.480206, -120.797163, 7100),
    ("water-lake-viviane", "Lake Viviane", 47.482487, -120.78378, 6785),
    ("water-snow-lakes", "Snow Lakes", 47.483065, -120.749933, 5433),
    ("water-nada-lake", "Nada Lake", 47.4945, -120.7406, 4934),
    ("access-snow-lakes-trailhead", "Snow Lakes Trailhead", 47.544083, -120.709661, 1299),
]

# The nearest SNOTEL station to the route. 13.4 km from Aasgard Pass and
# about 3,200 ft below it. Name and elevation as the AWDB API gave them on
# 2026-09-28.
SNOTEL_TRIPLET = "1338:WA:SNTL"
SNOTEL_NAME = "Icicle Creek"
SNOTEL_ELEVATION_FT = 4550
SNOTEL_LOOKBACK_DAYS = 7

# SNODAS stores depth as a 16-bit integer. Anything past this is not snow.
MAX_PLAUSIBLE_MM = 30000

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class Refuse(Exception):
    """The job cannot produce an honest file. Nothing gets written."""


def log(msg):
    print(msg, file=sys.stderr)


def tar_url(day):
    return f"{NSIDC_BASE}/{day.year}/{day.month:02d}_{MONTHS[day.month - 1]}/SNODAS_{day:%Y%m%d}.tar"


def fetch(url, timeout=120, accept=None):
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def find_tar(start, max_back):
    """Try `start`, then earlier days. Returns (day, url, bytes)."""
    last_err = None
    for back in range(max_back + 1):
        day = start - dt.timedelta(days=back)
        url = tar_url(day)
        try:
            return day, url, fetch(url)
        except urllib.error.HTTPError as e:
            last_err = f"{url} -> HTTP {e.code}"
            log(f"  not there: {last_err}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = f"{url} -> {e}"
            log(f"  fetch failed: {last_err}")
    raise Refuse(f"No SNODAS tar in the {max_back + 1} days ending {start}. Last error: {last_err}")


def parse_header(text):
    hdr = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            hdr[k.strip()] = v.strip()
    return hdr


def extract(tarbytes, product_code):
    """Return (header dict, raw grid bytes) for one product code."""
    try:
        tf = tarfile.open(fileobj=io.BytesIO(tarbytes))
        txt = dat = None
        names = []
        for m in tf.getmembers():
            names.append(m.name)
            if f"ssmv1{product_code}" not in m.name:
                continue
            if m.name.endswith(".txt.gz"):
                txt = gzip.decompress(tf.extractfile(m).read()).decode("ascii", "replace")
            elif m.name.endswith(".dat.gz"):
                dat = gzip.decompress(tf.extractfile(m).read())
    except (tarfile.TarError, OSError, EOFError) as e:
        raise Refuse(f"The tar could not be read: {e}") from e
    if txt is None or dat is None:
        raise Refuse(f"Product {product_code} is not in the tar. Members: {names}")
    return parse_header(txt), dat


class Grid:
    """The depth grid, with every piece of geometry read from its header."""

    def __init__(self, hdr, raw):
        try:
            self.cols = int(hdr["Number of columns"])
            self.rows = int(hdr["Number of rows"])
            self.min_x = float(hdr["Minimum x-axis coordinate"])
            self.max_y = float(hdr["Maximum y-axis coordinate"])
            self.dx = float(hdr["X-axis resolution"])
            self.dy = float(hdr["Y-axis resolution"])
            self.nodata = int(float(hdr["No data value"]))
            slope = float(hdr["Data slope"])
            intercept = float(hdr["Data intercept"])
            units = hdr["Data units"]
            bytes_per_pixel = int(hdr["Data bytes per pixel"])
            data_type = hdr["Data type"]
            self.valid_time = dt.datetime(
                int(hdr["Start year"]), int(hdr["Start month"]), int(hdr["Start day"]),
                int(hdr["Start hour"]), int(hdr["Start minute"]), int(hdr["Start second"]),
                tzinfo=dt.timezone.utc,
            )
        except (KeyError, ValueError) as e:
            raise Refuse(f"The depth header is missing a field or holds a bad value: {e}") from e

        if bytes_per_pixel != 2 or data_type != "integer":
            raise Refuse(f"Unexpected pixel type: {data_type}, {bytes_per_pixel} bytes")
        expected = self.cols * self.rows * 2
        if len(raw) != expected:
            raise Refuse(f"Grid is {len(raw)} bytes, header says {self.cols}x{self.rows}x2 = {expected}")
        # "Meters / 1000.000000" means the stored integer is millimetres.
        m = re.match(r"^Meters\s*/\s*([0-9.]+)$", units)
        if not m or float(m.group(1)) != 1000.0:
            raise Refuse(f"Depth units are '{units}', not metres over 1000. Not converting.")
        if slope != 1.0 or intercept != 0.0:
            raise Refuse(f"Data slope {slope} and intercept {intercept} are not 1 and 0. Not converting.")
        if self.dx <= 0 or self.dy <= 0:
            raise Refuse(f"Cell size {self.dx} x {self.dy} is not positive")
        self.raw = raw

    def cell(self, lat, lon):
        col = int(math.floor((lon - self.min_x) / self.dx))
        row = int(math.floor((self.max_y - lat) / self.dy))
        if not (0 <= col < self.cols and 0 <= row < self.rows):
            raise Refuse(f"{lat},{lon} is off the grid")
        i = (row * self.cols + col) * 2
        (v,) = struct.unpack(">h", self.raw[i:i + 2])
        return col, row, v

    def depth_mm(self, pid, lat, lon):
        col, row, v = self.cell(lat, lon)
        if v == self.nodata:
            raise Refuse(f"{pid}: cell {col},{row} holds the no-data value {self.nodata}")
        if v < 0 or v > MAX_PLAUSIBLE_MM:
            raise Refuse(f"{pid}: cell {col},{row} holds {v}, outside 0 to {MAX_PLAUSIBLE_MM} mm")
        return col, row, v


def snotel_reading(product_day):
    """
    The latest measured depth at Icicle Creek, or None.

    None means the key is left out of the file. A null value from the API is
    skipped, never turned into a number.
    """
    end = product_day + dt.timedelta(days=1)
    begin = product_day - dt.timedelta(days=SNOTEL_LOOKBACK_DAYS)
    q = urllib.parse.urlencode({
        "stationTriplets": SNOTEL_TRIPLET,
        "elements": "SNWD",
        "duration": "DAILY",
        "beginDate": f"{begin:%Y-%m-%d}",
        "endDate": f"{end:%Y-%m-%d}",
    })
    try:
        body = json.loads(fetch(f"{AWDB_BASE}/data?{q}", timeout=45, accept="application/json"))
        station = json.loads(
            fetch(
                f"{AWDB_BASE}/stations?{urllib.parse.urlencode({'stationTriplets': SNOTEL_TRIPLET})}",
                timeout=45,
                accept="application/json",
            )
        )
    except Exception as e:  # noqa: BLE001 - optional data, the file ships without it
        log(f"  SNOTEL left out: {e}")
        return None

    try:
        meta = next(s for s in station if s.get("stationTriplet") == SNOTEL_TRIPLET)
        if meta.get("name") != SNOTEL_NAME or round(float(meta.get("elevation"))) != SNOTEL_ELEVATION_FT:
            log(f"  SNOTEL left out: station reads {meta.get('name')} at {meta.get('elevation')} ft, "
                f"this script expects {SNOTEL_NAME} at {SNOTEL_ELEVATION_FT} ft")
            return None
        rows = next(s for s in body if s.get("stationTriplet") == SNOTEL_TRIPLET)["data"]
        series = next(d for d in rows if d["stationElement"]["elementCode"] == "SNWD")
        if series["stationElement"].get("storedUnitCode") != "in":
            log(f"  SNOTEL left out: unit is {series['stationElement'].get('storedUnitCode')}, not inches")
            return None
        best = None
        for v in series.get("values", []):
            value = v.get("value")
            date = v.get("date")
            if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if not math.isfinite(value) or value < 0:
                continue
            if not isinstance(date, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
                continue
            if best is None or date > best[0]:
                best = (date, value)
    except (StopIteration, KeyError, TypeError, ValueError) as e:
        log(f"  SNOTEL left out: unexpected response shape ({e})")
        return None

    if best is None:
        log("  SNOTEL left out: no reading in the window")
        return None
    depth = best[1]
    return {
        "triplet": SNOTEL_TRIPLET,
        "name": SNOTEL_NAME,
        "elevationFt": SNOTEL_ELEVATION_FT,
        "date": best[0],
        "depthIn": int(depth) if float(depth).is_integer() else depth,
    }


def existing_product_date(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f).get("productDate")
        return d if isinstance(d, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", d) else None
    except (OSError, ValueError, AttributeError):
        return None


def build(start, max_back, with_snotel, tar_path=None):
    if tar_path:
        with open(tar_path, "rb") as f:
            tarbytes = f.read()
        m = re.search(r"SNODAS_(\d{4})(\d{2})(\d{2})\.tar$", tar_path)
        if not m:
            raise Refuse(f"{tar_path} is not named SNODAS_YYYYMMDD.tar")
        day = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        log(f"  tar: {tar_path}")
    else:
        day, url, tarbytes = find_tar(start, max_back)
        log(f"  tar: {url} ({len(tarbytes):,} bytes)")

    hdr, raw = extract(tarbytes, DEPTH_PRODUCT)
    grid = Grid(hdr, raw)
    if grid.valid_time.date() != day:
        raise Refuse(f"The tar is dated {day} but its depth header is valid {grid.valid_time:%Y-%m-%d %H:%M} UTC")

    points = []
    for pid, name, lat, lon, height_ft in POINTS:
        col, row, mm = grid.depth_mm(pid, lat, lon)
        log(f"  {pid:30} cell {col},{row}  {mm} mm")
        points.append({"id": pid, "name": name, "lat": lat, "lon": lon, "heightFt": height_ft, "depthMm": mm})

    out = {
        "source": SOURCE,
        "citation": CITATION,
        "productDate": f"{day:%Y-%m-%d}",
        "validTime": f"{grid.valid_time:%Y-%m-%dT%H:%M:%SZ}",
        "generated": f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ}",
        "units": "mm",
        "gridKm": 1,
        "points": points,
    }
    if with_snotel:
        reading = snotel_reading(day)
        if reading is not None:
            out["snotel"] = [reading]
    return out


def write_atomic(path, text):
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".snow-", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    default_out = os.path.normpath(os.path.join(here, "..", "..", "snow.json"))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=default_out, help="file to write (default: snow.json at the site root)")
    ap.add_argument("--date", help="YYYY-MM-DD product date to start from (default: today, UTC)")
    ap.add_argument("--max-back", type=int, default=5, help="days to fall back when a tar is missing (default 5)")
    ap.add_argument("--dry-run", action="store_true", help="print the JSON and write nothing")
    ap.add_argument("--force", action="store_true", help="write even when the product date is not newer")
    ap.add_argument("--no-snotel", action="store_true", help="skip the SNOTEL request")
    ap.add_argument("--tar", help="read this SNODAS_YYYYMMDD.tar from disk instead of downloading")
    args = ap.parse_args()

    try:
        start = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(dt.timezone.utc).date()
    except ValueError:
        log(f"--date {args.date} is not YYYY-MM-DD")
        return 2

    try:
        out = build(start, args.max_back, not args.no_snotel, args.tar)
    except Refuse as e:
        log(f"REFUSED, nothing written: {e}")
        return 1

    text = json.dumps(out, indent=2) + "\n"
    if args.dry_run:
        print(text, end="")
        log("dry run, nothing written")
        return 0

    have = existing_product_date(args.out)
    if have is not None and out["productDate"] <= have and not args.force:
        log(f"unchanged: {args.out} already holds {have}, the newest tar is {out['productDate']}")
        return 0

    write_atomic(args.out, text)
    log(f"wrote {args.out} for {out['productDate']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
