"""RTKLIB ``.pos`` solution files: RTK and PPK positions as telemetry.

RTKLIB's ``rtkpost``/``rnx2rtkp`` (and the Emlid, u-blox and DJI tools built on
it) write one epoch per line after a ``%``-commented header::

    %  GPST                  latitude(deg) longitude(deg)  height(m)   Q  ns   sdn(m)   sde(m)   sdu(m)  sdne(m)  sdeu(m)  sdun(m) age(s)  ratio
    2024/03/05 06:12:30.200   47.376900000    8.541700000   430.1234   1  14   0.0081   0.0062   0.0193  ...

The time column is ``yyyy/mm/dd hh:mm:ss.sss`` or ``week tow``, in GPS time
(``GPST``), ``UTC`` or ``JST`` as the header says. Positions are degrees,
``ddd mm ss.ss`` or ECEF metres. The header's ``height=WGS84/ellipsoidal`` (or
``/geodetic``, height above the geoid) names the vertical datum.

What this keeps, and why:

* **Every row's original quality.** ``Q`` (1 fix, 2 float, 3 SBAS, 4 DGPS,
  5 single, 6 PPP) maps to the ``rtk_status`` labels :mod:`telemetry` scores
  (``RTK_FIXED``, ``RTK_FLOAT``, ...); the code itself, ``ns``, the standard
  deviations, ``age`` and ``ratio`` stay in ``extra``. A Q of 4 is *DGPS* here
  and must not be read with the CSV convention where "4" means fixed.
* **Time, unambiguously.** GPS time runs ahead of UTC by the leap seconds
  since 1980 (18 s since 2017). Sample timestamps are seconds since the first
  epoch, like the other telemetry sources; the absolute UTC time and the GPS
  week and time of week of each row are kept in ``extra``.
* **Bad rows are reported, not dropped silently**, as :mod:`telemetry` does.
"""
from __future__ import annotations

import calendar
import math
import re
from pathlib import Path

import numpy as np

from .telemetry import TelemetrySample

#: RTKLIB quality flag -> (rtk_status label, plain name).
Q_CODES = {
    1: ("RTK_FIXED", "fix"),
    2: ("RTK_FLOAT", "float"),
    3: ("SBAS", "sbas"),
    4: ("DGPS", "dgps"),
    5: ("SINGLE", "single"),
    6: ("PPP", "ppp"),
}

#: (first UTC instant it applies from, GPS - UTC seconds). IERS Bulletin C;
#: none has been announced after 2017-01-01.
_LEAP_SECONDS = [
    ((1981, 7, 1), 1), ((1982, 7, 1), 2), ((1983, 7, 1), 3), ((1985, 7, 1), 4),
    ((1988, 1, 1), 5), ((1990, 1, 1), 6), ((1991, 1, 1), 7), ((1992, 7, 1), 8),
    ((1993, 7, 1), 9), ((1994, 7, 1), 10), ((1996, 1, 1), 11), ((1997, 7, 1), 12),
    ((1999, 1, 1), 13), ((2006, 1, 1), 14), ((2009, 1, 1), 15), ((2012, 7, 1), 16),
    ((2015, 7, 1), 17), ((2017, 1, 1), 18),
]
_LEAP_EPOCHS = [(calendar.timegm((y, m, d, 0, 0, 0)), n) for (y, m, d), n in _LEAP_SECONDS]
GPS_EPOCH_UNIX = calendar.timegm((1980, 1, 6, 0, 0, 0))
JST_OFFSET_S = 9 * 3600


def gps_minus_utc(unix_utc: float) -> int:
    """Leap seconds GPS time is ahead of UTC at a UTC instant."""
    n = 0
    for t, k in _LEAP_EPOCHS:
        if unix_utc >= t:
            n = k
    return n


def gpst_to_utc(unix_gpst: float) -> float:
    """A GPS-time instant written as if it were UTC (seconds since 1970) -> UTC."""
    # The offset is looked up at the UTC instant; a step at a leap second makes
    # the GPST-side lookup differ only inside the leap second itself.
    return unix_gpst - gps_minus_utc(unix_gpst - gps_minus_utc(unix_gpst))


def week_tow_to_unix_gpst(week: int, tow: float) -> float:
    return GPS_EPOCH_UNIX + week * 604800 + tow


def unix_to_week_tow(unix_gpst: float) -> tuple[int, float]:
    s = unix_gpst - GPS_EPOCH_UNIX
    week = int(s // 604800)
    return week, s - week * 604800


_DATE = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")
_TIME = re.compile(r"^(\d{1,2}):(\d{1,2}):(\d{1,2}(?:\.\d*)?)$")


class PosHeader:
    """What the ``%`` header says: time system, coordinate form, height datum."""

    def __init__(self):
        self.time_system = "GPST"        # RTKLIB's default
        self.coords = "llh"              # llh | dms | xyz
        self.height = None               # ellipsoidal | geodetic | None (unstated)
        self.columns: list[str] = []
        self.program = None

    @classmethod
    def parse(cls, lines) -> "PosHeader":
        h = cls()
        for line in lines:
            body = line.lstrip("%").strip()
            low = body.lower()
            if low.startswith("program"):
                h.program = body.split(":", 1)[-1].strip()
            if "height=" in low or "lat/lon/height" in low:
                if "ellipsoidal" in low:
                    h.height = "ellipsoidal"
                elif "geodetic" in low:
                    h.height = "geodetic"
            if ("latitude" in low or "x-ecef" in low) and ("gpst" in low or "utc" in low
                                                         or "jst" in low):
                h.columns = body.split()
                first = h.columns[0].upper() if h.columns else ""
                if first in ("GPST", "UTC", "JST"):
                    h.time_system = first
                if "x-ecef" in low:
                    h.coords = "xyz"
                elif "(dms)" in low or "latitude(d'\")" in low:
                    h.coords = "dms"
        return h


def _num(tok: str) -> float | None:
    try:
        v = float(tok)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def _parse_time(tokens: list[str]) -> tuple[float, int] | None:
    """(unix seconds in the file's time system, tokens consumed)."""
    if len(tokens) >= 2 and _DATE.match(tokens[0]) and _TIME.match(tokens[1]):
        y, mo, d = (int(v) for v in _DATE.match(tokens[0]).groups())
        hh, mm, ss = _TIME.match(tokens[1]).groups()
        if not (1 <= mo <= 12 and 1 <= d <= 31 and int(hh) < 24 and int(mm) < 60
                and float(ss) < 61):
            return None
        whole = int(float(ss))
        return (calendar.timegm((y, mo, d, int(hh), int(mm), whole))
                + float(ss) - whole), 2
    if len(tokens) >= 2:
        week, tow = _num(tokens[0]), _num(tokens[1])
        if (week is not None and tow is not None and float(week).is_integer()
                and 0 <= week < 10000 and 0 <= tow < 604800):
            return week_tow_to_unix_gpst(int(week), tow), 2
    return None


def _dms(deg: str, mins: str, secs: str) -> float | None:
    d, m, s = _num(deg), _num(mins), _num(secs)
    if d is None or m is None or s is None:
        return None
    sign = -1.0 if deg.strip().startswith("-") else 1.0
    return sign * (abs(d) + m / 60.0 + s / 3600.0)


def _ecef_to_llh(x, y, z):
    from .geo import ecef_to_geodetic
    lat, lon, h = ecef_to_geodetic([[x, y, z]])[0]
    return float(lat), float(lon), float(h)


_STAT_NAMES = ("sdn", "sde", "sdu", "sdne", "sdeu", "sdun", "age", "ratio")
_STAT_NAMES_XYZ = ("sdx", "sdy", "sdz", "sdxy", "sdyz", "sdzx", "age", "ratio")


def parse_pos(path: Path, warnings: list[str]):
    """Parse an RTKLIB ``.pos`` file into telemetry samples.

    Returns ``(samples, None)`` like the other :mod:`telemetry` parsers. The
    samples' ``extra`` carry ``altitude_reference`` from the header (so
    :func:`telemetry.vertical_datum` reads it), ``rtklib_q``, ``ns``, the
    standard deviations, ``age_s``, ``ratio``, ``utc_unix``, ``gps_week`` and
    ``gps_tow``.
    """
    text = Path(path).read_text(errors="replace").splitlines()
    header = PosHeader.parse([l for l in text if l.startswith("%")])
    if header.height is None:
        warnings.append(".pos header does not state the height datum "
                        "(height=WGS84/ellipsoidal or /geodetic); altitude reference unknown")
    ref = {"ellipsoidal": "ELLIPSOIDAL", "geodetic": "MSL"}.get(header.height)

    rows = []
    for i, line in enumerate(text):
        if not line.strip() or line.startswith("%"):
            continue
        tok = line.split()
        t = _parse_time(tok)
        if t is None:
            warnings.append(f".pos line {i + 1}: unreadable epoch, skipped")
            continue
        t_file, k = t
        rest = tok[k:]
        if header.coords == "dms":
            if len(rest) < 9:
                warnings.append(f".pos line {i + 1}: too few columns, skipped")
                continue
            lat, lon, alt = _dms(*rest[0:3]), _dms(*rest[3:6]), _num(rest[6])
            rest = rest[7:]
        else:
            if len(rest) < 5:
                warnings.append(f".pos line {i + 1}: too few columns, skipped")
                continue
            a, b, c = (_num(v) for v in rest[0:3])
            if None in (a, b, c):
                lat = lon = alt = None
            elif header.coords == "xyz":
                lat, lon, alt = _ecef_to_llh(a, b, c)
            else:
                lat, lon, alt = a, b, c
            rest = rest[3:]
        q, ns = _num(rest[0]), _num(rest[1])
        if (lat is None or lon is None or alt is None or not -90 <= lat <= 90
                or not -180 <= lon <= 180 or q is None or ns is None):
            warnings.append(f".pos line {i + 1}: invalid position or quality, skipped")
            continue
        q = int(q)
        if q not in Q_CODES:
            warnings.append(f".pos line {i + 1}: unknown quality flag Q={q}; kept as "
                            "status UNKNOWN")
        names = _STAT_NAMES_XYZ if header.coords == "xyz" else _STAT_NAMES
        stats = {n: _num(v) for n, v in zip(names, rest[2:])}

        if header.time_system == "UTC":
            utc = t_file
            gpst = utc + gps_minus_utc(utc)
        elif header.time_system == "JST":
            utc = t_file - JST_OFFSET_S
            gpst = utc + gps_minus_utc(utc)
        else:
            gpst = t_file
            utc = gpst_to_utc(gpst)
        week, tow = unix_to_week_tow(gpst)
        rows.append((utc, lat, lon, alt, q, int(ns), stats, week, tow))

    if not rows:
        return [], None
    t0 = rows[0][0]
    samples = []
    for utc, lat, lon, alt, q, ns, stats, week, tow in rows:
        sdh = None
        if stats.get("sdn") is not None and stats.get("sde") is not None:
            sdh = math.hypot(stats["sdn"], stats["sde"])
        extra = {"rtklib_q": q, "rtklib_quality": Q_CODES.get(q, (None, "unknown"))[1],
                 "ns": ns, "utc_unix": utc, "gps_week": week, "gps_tow": round(tow, 4),
                 "time_system": header.time_system}
        extra.update({f"{k}_m" if k.startswith("sd") else
                      ("age_s" if k == "age" else k): v
                      for k, v in stats.items() if v is not None})
        if ref:
            extra["altitude_reference"] = ref
        samples.append(TelemetrySample(
            timestamp=utc - t0, latitude=lat, longitude=lon, altitude=alt,
            gps_accuracy=sdh, rtk_status=Q_CODES.get(q, ("UNKNOWN",))[0], extra=extra))
    return samples, None


__all__ = ["Q_CODES", "parse_pos", "gps_minus_utc", "gpst_to_utc",
           "week_tow_to_unix_gpst", "unix_to_week_tow", "PosHeader"]
