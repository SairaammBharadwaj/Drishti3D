#!/usr/bin/env python3
"""Record a finished mission's vertical datum, and what it rests on.

Runs before DEC-047 wrote "WGS84 ellipsoidal" into every georeference.json and
GeoTIFF whatever the telemetry's altitude was measured from. New runs carry the
telemetry's own altitude reference (``telemetry.vertical_datum``). This puts the
datum that evidence established on an existing mission, without reprocessing:

* ``georeference.json``: ``vertical_datum``, ``vertical_reference``,
  ``vertical_datum_basis``; the origin's ``alt_ellipsoidal_m`` becomes ``alt_m``.
* ``rasters.json`` and the GeoTIFFs' ``VERTICAL_REFERENCE`` tag.

Heights are not changed, only what they are said to be. The artifacts stored
answers are checked against (``storage.artifact_revision``) are never touched;
``manifest.json`` is one of them, so an old run's manifest keeps its old label
and georeference.json is the authority.

Usage (from the drishti3d directory):
  .venv/bin/python scripts/set_vertical_datum.py --datum msl \\
      --basis "DEC-047: ground matches SRTM as sea-level heights" PROJECT_ID ...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "reconstruction"))
sys.path.insert(0, str(APP / "backend"))

from drishti_recon.geo import VERTICAL_DATUMS                # noqa: E402

_TIFS = ("dsm.tif", "dtm.tif", "ortho.tif", "sigma.tif", "landcover.tif")


def _revision_files() -> tuple[str, ...]:
    from app import storage
    return storage._REVISION_FILES


def set_datum(art: Path, datum: str, basis: str) -> list[str]:
    """Label one mission's heights; return the files changed."""
    protected = set(_revision_files())
    changed = []

    geo_p = art / "georeference.json"
    geo = json.loads(geo_p.read_text())
    if not geo.get("georeferenced"):
        raise ValueError("not georeferenced: its heights have no datum to record")
    origin = geo.get("local_origin_wgs84") or {}
    if "alt_ellipsoidal_m" in origin:
        origin["alt_m"] = origin.pop("alt_ellipsoidal_m")
    geo.update(vertical_datum=datum, vertical_reference=VERTICAL_DATUMS[datum],
               vertical_datum_basis=basis)
    geo_p.write_text(json.dumps(geo, indent=2))
    changed.append(geo_p.name)

    ras_p = art / "rasters.json"
    if ras_p.exists():
        ras = json.loads(ras_p.read_text())
        ras.update(vertical_datum=datum, vertical_reference=VERTICAL_DATUMS[datum])
        ras_p.write_text(json.dumps(ras, indent=2))
        changed.append(ras_p.name)

    tifs = [art / n for n in _TIFS if (art / n).exists()]
    if tifs:
        import rasterio
        for t in tifs:
            with rasterio.open(t, "r+") as ds:
                ds.update_tags(VERTICAL_REFERENCE=VERTICAL_DATUMS[datum])
            changed.append(t.name)

    assert not protected & set(changed), "touched an artifact answers are checked against"
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("projects", nargs="+")
    ap.add_argument("--datum", required=True, choices=sorted(VERTICAL_DATUMS))
    ap.add_argument("--basis", required=True,
                    help="what establishes the datum, e.g. a DEC entry")
    ap.add_argument("--data", type=Path, default=APP / "data")
    args = ap.parse_args()
    for pid in args.projects:
        art = args.data / "projects" / pid / "artifacts"
        try:
            print(pid[:8], args.datum, set_datum(art, args.datum, args.basis))
        except Exception as exc:                 # report and carry on with the rest
            print(pid[:8], "error:", f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
