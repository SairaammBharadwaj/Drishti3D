#!/usr/bin/env python3
"""Score the land-cover building class against OpenStreetMap building footprints.

None of the project's reference LiDAR is classified, so the land-cover layer
has no labelled truth. OSM outlines are the best external reference available
for one class, buildings, and in downtown Austin they are dense and were
imported from the city's own survey. They are not survey truth: an outline can
be offset by a metre or two, or missing.

The mission is rebuilt from its saved cloud with the classifier settings under
test (nothing is written), and OSM polygons are burnt into the same grid.
Reported, over cells with data:

* precision: of cells called building, the share inside a footprint grown by
  ``--tolerance`` metres (eaves, outline offset);
* recall: of cells inside a footprint shrunk by ``--tolerance``, the share
  called building;
* roof_as_ground: of those footprint-interior cells, the share called ground
  (the ground filter keeping a roof);
* best_shift_m: the whole-grid offset (within +-``--max-shift`` m) that maximises F1, so a
  georeferencing offset is not mistaken for a classification error. Precision
  and recall are reported at zero shift and at that shift.

Usage (from the drishti3d directory):
  .venv/bin/python scripts/score_landcover_osm.py --project 051960beb15a4e1a8b851a8fa5bcc6e1 \\
      --osm ../datasets/truth/osm_buildings/dji_1003.json --set max_window_m=80
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "reconstruction"))

from drishti_recon import exports, rasters as R         # noqa: E402
from drishti_recon.geo import ENUFrame                  # noqa: E402

DEFAULTS = {"max_window_m": 40.0, "slope": 0.15, "dh0": 0.3, "dh_max": 2.5,
            "min_height": 2.0, "exg_thresh": 0.05, "rough_thresh": 0.75}


def osm_mask(osm: dict, grid: R.Grid, epsg: int) -> np.ndarray:
    """Building footprints burnt into the grid: outer rings in, inner rings out."""
    import pyproj
    from rasterio import features
    from rasterio.transform import from_origin
    tr = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)

    def ring(geom):
        x, y = tr.transform([p["lon"] for p in geom], [p["lat"] for p in geom])
        return list(zip(x, y))

    outer, inner = [], []
    for el in osm["elements"]:
        if el["type"] == "way" and len(el.get("geometry", [])) >= 3:
            outer.append({"type": "Polygon", "coordinates": [ring(el["geometry"])]})
        elif el["type"] == "relation":
            for m in el.get("members", []):
                if m.get("type") == "way" and len(m.get("geometry", [])) >= 3:
                    poly = {"type": "Polygon", "coordinates": [ring(m["geometry"])]}
                    (inner if m.get("role") == "inner" else outer).append(poly)
    transform = from_origin(grid.x0, grid.y1, grid.res, grid.res)
    shape = (grid.h, grid.w)
    mask = features.rasterize(((g, 1) for g in outer), out_shape=shape,
                              transform=transform, fill=0, dtype="uint8") > 0
    if inner:
        mask &= features.rasterize(((g, 1) for g in inner), out_shape=shape,
                                   transform=transform, fill=0, dtype="uint8") == 0
    return mask


def classify_mission(art: Path, params: dict):
    frame = ENUFrame(**json.loads((art / "trajectory.json").read_text())["frame"])
    d = np.load(art / "cloud.npz")
    utm, epsg = exports.enu_to_utm(frame, d["points"])
    res = float(json.loads((art / "rasters.json").read_text())["cell_size_m"])
    sig = d["sigma_major"] if "sigma_major" in d.files else None
    r = R.rasterize(utm, d["colors"], sig, d["provenance"], res)
    ground = R.ground_filter(r["zmin"], res, max_window_m=params["max_window_m"],
                             slope=params["slope"], dh0=params["dh0"], dh_max=params["dh_max"])
    dtm = np.where(ground, r["zmin"], np.nan)
    cls, _, _ = R.classify(r["dsm"], ground, r["rgb"], dtm=dtm,
                           min_height=params["min_height"],
                           exg_thresh=params["exg_thresh"],
                           rough_thresh=params["rough_thresh"])
    return cls, r["grid"], epsg


def score(cls, fp, res, tol_m, max_shift_m=4.0):
    k = max(1, int(round(tol_m / res)))
    st = np.ones((2 * k + 1, 2 * k + 1), bool)
    grown = ndimage.binary_dilation(fp, st)
    core = ndimage.binary_erosion(fp, st)
    have = cls > 0
    pred = cls == R.BUILDING

    def at(dr, dc):
        p = np.roll(pred, (dr, dc), axis=(0, 1))
        h = np.roll(have, (dr, dc), axis=(0, 1))
        tp_p = (p & grown).sum()
        prec = tp_p / max(p.sum(), 1)
        core_h = core & h
        rec = (p & core_h).sum() / max(core_h.sum(), 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        return prec, rec, f1

    best = (0, 0, *at(0, 0))
    span = int(np.ceil(max_shift_m / res))
    step = max(1, span // 8)
    for dr in range(-span, span + 1, step):
        for dc in range(-span, span + 1, step):
            s = at(dr, dc)
            if s[2] > best[4]:
                best = (dr, dc, *s)
    p0, r0, f0 = at(0, 0)
    core_h = core & have
    return {"precision": round(float(p0), 3), "recall": round(float(r0), 3),
            "f1": round(float(f0), 3),
            "roof_as_ground": round(float(((cls == R.GROUND) & core_h).sum()
                                          / max(core_h.sum(), 1)), 3),
            "footprint_interior_cells_with_data": int(core_h.sum()),
            "cells_called_building": int(pred.sum()),
            "best_shift_m": [round(-best[1] * res, 2), round(best[0] * res, 2)],
            "at_best_shift": {"precision": round(float(best[2]), 3),
                              "recall": round(float(best[3]), 3),
                              "f1": round(float(best[4]), 3)}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--osm", required=True)
    ap.add_argument("--data", type=Path, default=APP / "data")
    ap.add_argument("--tolerance", type=float, default=1.5)
    ap.add_argument("--max-shift", type=float, default=4.0)
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                    help=f"override a classifier setting; defaults {DEFAULTS}")
    a = ap.parse_args()
    params = dict(DEFAULTS)
    for kv in a.set:
        k, v = kv.split("=", 1)
        if k not in params:
            ap.error(f"unknown setting {k}")
        params[k] = float(v)
    art = a.data / "projects" / a.project / "artifacts"
    cls, grid, epsg = classify_mission(art, params)
    fp = osm_mask(json.loads(Path(a.osm).read_text()), grid, epsg)
    out = {"project": a.project, "params": params, "tolerance_m": a.tolerance,
           "cell_m": grid.res, **score(cls, fp, grid.res, a.tolerance, a.max_shift)}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
