"""Shared reader for the Zurich Urban MAV (AGZ) log files.

The AGZ logs are keyed by ``imgid`` -- the index of the corresponding frame in
``MAV Images/`` -- which is what lets a subset of frames be rejoined to its
telemetry and to the published reference camera positions.

Two facts about these files govern every use below:

* ``OnboardGPS.csv`` carries ``eph_m`` (horizontal DOP, metres) but its
  ``epv_m`` column is corrupt in the published release: the values decode as
  denormals around 1e-43 rather than metres.  Vertical accuracy is therefore
  *unknown*, not small, and must not be written into a sigma column.
* ``GroundTruthAGL.csv`` positions were produced by the dataset authors with
  Pix4D over the full image set, with loop closures.  They are a strong
  photogrammetric reference, **not** independent RTK or LiDAR survey truth, and
  the publisher does not state their uncertainty.  Scoring against them
  measures agreement with another reconstruction.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GpsRow:
    timestamp_us: float
    imgid: int
    lat: float
    lon: float
    alt_msl_m: float
    fix_type: int
    eph_m: float
    num_sat: int


@dataclass
class TruthRow:
    """A published reference camera position, UTM zone 32N, metres."""
    imgid: int
    x_gt: float
    y_gt: float
    z_gt: float
    omega_deg: float
    phi_deg: float
    kappa_deg: float
    x_gps: float
    y_gps: float
    z_gps: float


def _rows(path: Path):
    with open(path, newline="") as fh:
        reader = csv.reader(fh)
        next(reader)                     # header
        for raw in reader:
            if not raw or not raw[0].strip():
                continue
            yield raw


def read_gps(log_dir: Path) -> dict[int, GpsRow]:
    """imgid -> GpsRow from ``OnboardGPS.csv``."""
    out: dict[int, GpsRow] = {}
    for r in _rows(Path(log_dir) / "OnboardGPS.csv"):
        imgid = int(float(r[1]))
        out[imgid] = GpsRow(float(r[0]), imgid, float(r[2]), float(r[3]),
                            float(r[4]), int(float(r[7])), float(r[8]),
                            int(float(r[13])))
    return out


def read_truth(log_dir: Path) -> dict[int, TruthRow]:
    """imgid -> TruthRow from ``GroundTruthAGL.csv`` (published every ~30th id)."""
    out: dict[int, TruthRow] = {}
    for r in _rows(Path(log_dir) / "GroundTruthAGL.csv"):
        vals = [float(x) for x in r[:10]]
        out[int(vals[0])] = TruthRow(int(vals[0]), *vals[1:10])
    return out


def read_barometer(log_dir: Path) -> list[tuple[float, float, float]]:
    """(timestamp_us, pressure_hPa, barometric_altitude_m) from the baro log."""
    out = []
    for r in _rows(Path(log_dir) / "BarometricPressure.csv"):
        out.append((float(r[0]), float(r[1]), float(r[2])))
    return out
