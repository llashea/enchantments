#!/usr/bin/env python3
"""
Offline checks for build_snow_json.py. No network.

  python3 -m unittest discover -s tools/snow -p 'test_*.py'

Each test builds a small SNODAS-shaped tar on disk, a 40 x 20 grid over the
permit area with the same header fields the real product ships, and runs the
job against it with --tar.
"""

import gzip
import importlib.util
import io
import json
import os
import struct
import tarfile
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("build_snow_json", os.path.join(HERE, "build_snow_json.py"))
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)

COLS, ROWS = 40, 20
MIN_X = -120.95
MAX_Y = 47.60
CELL = 0.008333333333333


def header(units="Meters / 1000.000000", cols=COLS, rows=ROWS, nodata=-9999, day=28):
    return "\n".join([
        "Description: Modeled snow layer thickness, total of snow layers",
        f"Number of columns: {cols}",
        f"Number of rows: {rows}",
        "Data type: integer",
        "Data bytes per pixel: 2",
        f"Minimum x-axis coordinate: {MIN_X}",
        f"Maximum y-axis coordinate: {MAX_Y}",
        f"X-axis resolution: {CELL}",
        f"Y-axis resolution: {CELL}",
        f"Data units: {units}",
        "Data slope: 1",
        "Data intercept: 0",
        f"No data value: {nodata}",
        "Start year: 2026", "Start month: 9", f"Start day: {day}",
        "Start hour: 6", "Start minute: 0", "Start second: 0",
    ]) + "\n"


def make_tar(folder, values=None, hdr=None, truncate=0, name="SNODAS_20260928.tar"):
    grid = [[7] * COLS for _ in range(ROWS)]
    for (col, row), v in (values or {}).items():
        grid[row][col] = v
    raw = b"".join(struct.pack(">h", v) for r in grid for v in r)
    if truncate:
        raw = raw[:-truncate]
    path = os.path.join(folder, name)
    with tarfile.open(path, "w") as tf:
        for member, payload in [
            ("us_ssmv11036tS__T0001TTNATS2026092805HP001.txt.gz", gzip.compress((hdr or header()).encode("ascii"))),
            ("us_ssmv11036tS__T0001TTNATS2026092805HP001.dat.gz", gzip.compress(raw)),
        ]:
            info = tarfile.TarInfo(member)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
    return path


def cell_of(lat, lon):
    return int((lon - MIN_X) // CELL), int((MAX_Y - lat) // CELL)


class BuildSnowJson(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def build(self, **kw):
        return job.build(None, 0, False, make_tar(self.dir.name, **kw))

    def test_a_good_grid_gives_every_point_a_depth_and_both_dates(self):
        pass_cell = cell_of(47.480785, -120.822454)
        out = self.build(values={pass_cell: 94})
        self.assertEqual(out["productDate"], "2026-09-28")
        self.assertEqual(out["validTime"], "2026-09-28T06:00:00Z")
        self.assertEqual(out["units"], "mm")
        self.assertEqual([p["id"] for p in out["points"]], [p[0] for p in job.POINTS])
        by_id = {p["id"]: p["depthMm"] for p in out["points"]}
        self.assertEqual(by_id["landmark-aasgard-pass"], 94)
        self.assertEqual(by_id["water-nada-lake"], 7)
        self.assertNotIn("snotel", out)
        json.dumps(out)

    def test_a_no_data_cell_is_refused_never_written_as_zero(self):
        with self.assertRaises(job.Refuse):
            self.build(values={cell_of(47.4945, -120.7406): -9999})

    def test_a_negative_or_absurd_value_is_refused(self):
        with self.assertRaises(job.Refuse):
            self.build(values={cell_of(47.4945, -120.7406): -3})
        with self.assertRaises(job.Refuse):
            self.build(values={cell_of(47.4945, -120.7406): 32000})

    def test_a_grid_that_does_not_match_its_header_is_refused(self):
        with self.assertRaises(job.Refuse):
            self.build(truncate=2)

    def test_units_other_than_millimetres_are_refused(self):
        with self.assertRaises(job.Refuse):
            self.build(hdr=header(units="Meters / 100.000000"))
        with self.assertRaises(job.Refuse):
            self.build(hdr=header(units="Kilograms per square meter / 1"))

    def test_a_header_dated_another_day_is_refused(self):
        with self.assertRaises(job.Refuse):
            self.build(hdr=header(day=27))

    def test_a_point_off_the_grid_is_refused(self):
        with self.assertRaises(job.Refuse):
            self.build(hdr=header(cols=COLS, rows=5), truncate=COLS * (ROWS - 5) * 2)

    def test_the_file_is_left_alone_unless_the_product_date_is_newer(self):
        out_path = os.path.join(self.dir.name, "snow.json")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write('{"productDate": "2026-09-28", "kept": true}\n')
        self.assertEqual(job.existing_product_date(out_path), "2026-09-28")
        out = self.build()
        self.assertFalse(out["productDate"] > job.existing_product_date(out_path))

    def test_a_refusal_on_the_command_line_exits_non_zero_and_writes_nothing(self):
        import subprocess
        import sys
        out_path = os.path.join(self.dir.name, "snow.json")
        tar = make_tar(self.dir.name, values={cell_of(47.480785, -120.822454): -9999})
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "build_snow_json.py"), "--tar", tar, "--out", out_path, "--no-snotel"],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED", r.stderr)
        self.assertFalse(os.path.exists(out_path))

    def test_a_good_run_on_the_command_line_writes_then_holds(self):
        import subprocess
        import sys
        out_path = os.path.join(self.dir.name, "snow.json")
        tar = make_tar(self.dir.name)
        cmd = [sys.executable, os.path.join(HERE, "build_snow_json.py"), "--tar", tar, "--out", out_path, "--no-snotel"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        first = open(out_path, encoding="utf-8").read()
        self.assertEqual(json.loads(first)["productDate"], "2026-09-28")
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("unchanged", r.stderr)
        self.assertEqual(open(out_path, encoding="utf-8").read(), first)


if __name__ == "__main__":
    unittest.main()
