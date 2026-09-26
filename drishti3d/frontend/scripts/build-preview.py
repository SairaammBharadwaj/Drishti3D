"""Build the homepage scene's metadata and first-paint sample.

The homepage shows one real reconstruction: by default the whole of DJI_1003,
native 11-minute drone video with GPS. When this installation has that mission
the page streams every point from the API (`/api/projects/<id>/model.bin`,
3.67 M points including the inferred fill); this script writes the small
uniform sample it paints first, and falls back to where the mission is absent,
plus the metadata that places both in the same frame.

Writes, under ``public/showcase/``:

* ``preview.bin`` -- one 16-byte little-endian record per point: x, y, z as
  float32 (east, up, north; centred on the crop and divided by
  ``metres_per_unit``), then r, g, b and the provenance code as uint8. The
  provenance code is ``drishti_recon.provenance.Provenance`` (0 observed high,
  1 observed low, ..., 6 inferred fill).
* ``preview.json`` -- what the scene is, where it came from, how many points
  of each class were sampled, the default view, and ``origin_enu`` and
  ``metres_per_unit``: the transform the sample was built with, which the page
  applies to the full cloud so the two frame identically.

Sampling is uniform and seeded, so a rebuild from the same artifacts is
byte-identical. The inferred fill (open water, holes) is included as its own
class, as the workspace shows it; the preview is never an input to anything.

Usage (from the repository's drishti3d directory):
  .venv/bin/python frontend/scripts/build-preview.py            # whole DJI_1003
  .venv/bin/python frontend/scripts/build-preview.py --box -300 600 -200 650
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]          # frontend/
APP = ROOT.parent                                    # drishti3d/
OUT = ROOT / "public/showcase"
FILL_CODE = 6

#: The whole of DJI_1003, viewed from the south: the river and its bridges
#: across the middle, the downtown towers beyond it.
DEFAULTS = {
    "project": "051960beb15a4e1a8b851a8fa5bcc6e1",
    "box": None,
    "points": 150_000,
    "view": {"angle": 0.35, "elevation_deg": 34},
    "title": "DJI_1003 · Austin, TX",
    "code": "ATX / 1003",
    "place": "Austin, TX",
    "capture": "11 min 18 s of native 1080p DJI video with per-frame SRT GPS",
    "scale": "metric · GPS-georeferenced",
    "credit": "Source footage: AirLock (WACV 2026), CC BY 4.0. "
              "Reconstruction by Drishti3D.",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=DEFAULTS["project"])
    ap.add_argument("--data-dir", default=str(APP / "data"))
    ap.add_argument("--box", type=float, nargs=4, default=DEFAULTS["box"],
                    metavar=("E0", "E1", "N0", "N1"),
                    help="crop in the mission's local ENU metres "
                         "(default: the whole cloud)")
    ap.add_argument("--points", type=int, default=DEFAULTS["points"])
    a = ap.parse_args()

    art = Path(a.data_dir) / "projects" / a.project / "artifacts"
    cloud = np.load(art / "cloud.npz")
    pts, cols = cloud["points"], cloud["colors"]
    prov = cloud["provenance"].astype(np.uint8)
    if (art / "fill.npz").exists():
        fill = np.load(art / "fill.npz")
        pts = np.vstack([pts, fill["points"]])
        cols = np.vstack([cols, fill["colors"]])
        prov = np.concatenate([prov, np.full(len(fill["points"]), FILL_CODE, np.uint8)])

    if a.box is None:
        e0, n0 = pts[:, :2].min(0)
        e1, n1 = pts[:, :2].max(0)
    else:
        e0, e1, n0, n1 = a.box
        keep = ((pts[:, 0] >= e0) & (pts[:, 0] <= e1)
                & (pts[:, 1] >= n0) & (pts[:, 1] <= n1))
        pts, cols, prov = pts[keep], cols[keep], prov[keep]
        if len(pts) == 0:
            raise SystemExit("the crop contains no points")
    # The ground reference comes from every point in the crop, not the
    # sample, so the full cloud streamed later lands exactly on it.
    ground = float(np.percentile(pts[:, 2], 5))
    n_total = int(len(pts))
    rng = np.random.default_rng(0)
    idx = np.sort(rng.choice(len(pts), min(a.points, len(pts)), replace=False))
    pts, cols, prov = pts[idx], cols[idx], prov[idx]

    # Centre on the crop, ground (5th height percentile) at zero, and one
    # scale for all three axes so heights keep their proportions.
    origin = np.array([(e0 + e1) / 2, (n0 + n1) / 2, ground])
    metres_per_unit = float(max(e1 - e0, n1 - n0) / 2)
    local = (pts - origin) / metres_per_unit

    rec = np.empty(len(pts), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                    ("r", "u1"), ("g", "u1"), ("b", "u1"),
                                    ("p", "u1")])
    rec["x"], rec["y"], rec["z"] = local[:, 0], local[:, 2], local[:, 1]
    rec["r"], rec["g"], rec["b"] = cols[:, 0], cols[:, 1], cols[:, 2]
    rec["p"] = prov
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "preview.bin").write_bytes(rec.tobytes())

    quality = json.loads((art / "quality_report.json").read_text())
    counts = {str(int(c)): int(n) for c, n in zip(*np.unique(prov, return_counts=True))}
    meta = {
        "format": {"version": 2, "record_bytes": 16,
                   "fields": "x,y,z float32 (east, up, north; local units) + "
                             "r,g,b uint8 + provenance uint8"},
        "project_id": a.project,
        "title": DEFAULTS["title"],
        "code": DEFAULTS["code"],
        "place": DEFAULTS["place"],
        "capture": DEFAULTS["capture"],
        "scale": DEFAULTS["scale"],
        "credit": DEFAULTS["credit"],
        "cloud_points": int(quality["cloud"]["n_points"]),
        "registered": f'{quality["reconstruction"]["n_registered"]}/'
                      f'{quality["reconstruction"]["n_keyframes"]}',
        "points_in_scene": n_total,
        "sampled_points": int(len(rec)),
        "sampled_by_provenance": counts,
        "crop_enu_m": None if a.box is None else [e0, e1, n0, n1],
        "origin_enu": [float(v) for v in origin],
        "metres_per_unit": metres_per_unit,
        "view": DEFAULTS["view"],
        "built": date.today().isoformat(),
    }
    (OUT / "preview.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"Wrote {OUT / 'preview.bin'} ({(OUT / 'preview.bin').stat().st_size:,} bytes, "
          f"{len(rec):,} points: {counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
