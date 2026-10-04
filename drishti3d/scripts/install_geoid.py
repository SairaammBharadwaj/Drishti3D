"""Install and check the EGM2008 geoid grid that heights above sea level need.

    python scripts/install_geoid.py            # download if missing, then check
    python scripts/install_geoid.py --check    # check only; exit 1 if unusable
    python scripts/install_geoid.py --from /media/usb/us_nga_egm08_25.tif

Without the grid, ``drishti_recon.position`` refuses sea-level heights (it never
hands back the ellipsoidal height under a sea-level label). This puts the grid
where PROJ looks (``pyproj.datadir.get_user_data_dir()``), verifies its SHA-256,
and checks the geoid height at known points against GeographicLib's values.
For an offline demo laptop, copy the file over and use ``--from``.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reconstruction"))

GRID = "us_nga_egm08_25.tif"
URL = f"https://cdn.proj.org/{GRID}"
SHA256 = "4191d471eefebf24091b56dbc604353cb3b8cf8cc70e448bb9ae56a272bef17a"
#: (name, lat, lon, EGM2008 geoid height N in metres, tolerance): the values
#: position.py records for the showcase missions' sites. The tolerance covers
#: the geoid's variation between a mission and the city point used here.
KNOWN = [
    ("Zurich", 47.3769, 8.5417, 47.7, 1.0),
    ("Austin", 30.2672, -97.7431, -26.9, 1.0),
    ("Hong Kong", 22.2783, 114.1747, -1.7, 1.0),
]


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def target() -> Path:
    import pyproj
    d = Path(pyproj.datadir.get_user_data_dir(True))
    d.mkdir(parents=True, exist_ok=True)
    return d / GRID


def install(source: str | None) -> Path:
    dst = target()
    if dst.exists() and _sha256(dst) == SHA256:
        print(f"grid present: {dst}")
        return dst
    tmp = dst.with_suffix(".part")
    if source:
        shutil.copyfile(source, tmp)
    else:
        print(f"downloading {URL} (80.6 MB) ...")
        try:
            with urllib.request.urlopen(URL, timeout=60) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            print(f"download failed ({exc}); copy {GRID} here with --from")
            return dst
    got = _sha256(tmp)
    if got != SHA256:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"checksum mismatch: {got} != {SHA256}; not installed")
    tmp.replace(dst)
    print(f"installed {dst}")
    return dst


def check() -> bool:
    from drishti_recon import position
    ok = True
    for name, lat, lon, N, tol in KNOWN:
        try:
            got = -float(position.orthometric_height(lat, lon, 0.0)[0])
        except position.GeoidUnavailable as exc:
            print(f"UNAVAILABLE: {exc}")
            return False
        good = abs(got - N) <= tol
        ok &= good
        print(f"{'ok ' if good else 'BAD'} {name:10s} N = {got:+8.3f} m "
              f"(expected {N:+.1f} +/- {tol})")
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="check only, do not install")
    ap.add_argument("--from", dest="source", help="copy the grid from this file")
    a = ap.parse_args(argv)
    if not a.check:
        install(a.source)
    good = check()
    print("geoid: " + ("usable" if good else "NOT usable: sea-level heights will be refused"))
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
