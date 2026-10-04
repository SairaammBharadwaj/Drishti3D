"""Where a point is, in the forms people read: lat/lon, UTM, MGRS, height above sea level.

Drishti3D stores heights on whatever datum the telemetry used, and records
which (``geo.VERTICAL_DATUMS``; DEC-047). Sea level (the EGM2008 geoid) sits
tens of metres off the WGS84 ellipsoid: a height above sea level is 27 m
*more* than the ellipsoidal height over Austin, 47-48 m *less* over Sardinia
and Zurich, and 1.7 m more in Hong Kong (``H = h - N``, with geoid height ``N``
-26.9, +46.9, +47.7 and -1.7 m there). A height read as one when it is the
other is wrong by that much, so both are given and each is named.

Sea-level height needs PROJ's EGM2008 grid, ``us_nga_egm08_25.tif`` (80.6 MB,
https://cdn.proj.org,
sha256 4191d471eefebf24091b56dbc604353cb3b8cf8cc70e448bb9ae56a272bef17a), in ``pyproj.datadir.get_user_data_dir()``.
Without it PROJ would fall back to a "ballpark" transform that returns the
ellipsoidal height unchanged -- a number that looks like an answer. This
refuses instead: :func:`orthometric_height` raises :class:`GeoidUnavailable`.

Checked against GeographicLib's published GeoidEval examples, through the same
code path with the EGM96 grid: 28.7017 vs 28.7068 m (Timbuktu) and -33.845 vs
-33.842 m (a UTM 18N point). The 2.5' EGM2008 grid interpolated bilinearly is
within 0.135 m of the model itself (GeographicLib's evaluation of that grid).
"""
from __future__ import annotations

import threading

import numpy as np

from .exports import enu_to_utm, utm_epsg
from .geo import ENUFrame

EGM2008_GRID = "us_nga_egm08_25.tif"
EGM2008_HEIGHT_CRS = 3855          # EPSG: EGM2008 height
_local = threading.local()         # pyproj transformers are not shared across threads


class GeoidUnavailable(RuntimeError):
    """The geoid grid is not installed; no sea-level height can be given."""


def _vertical_transformer(height_crs: int = EGM2008_HEIGHT_CRS):
    cache = getattr(_local, "transformers", None)
    if cache is None:
        cache = _local.transformers = {}
    if height_crs not in cache:
        import warnings
        from pyproj.transformer import TransformerGroup
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")      # pyproj warns about the missing grid
            group = TransformerGroup("EPSG:4979", f"EPSG:4326+{height_crs}",
                                     always_xy=True, allow_ballpark=False)
        if not group.best_available or not group.transformers:
            needed = sorted({g.short_name for op in group.unavailable_operations
                             for g in op.grids})
            raise GeoidUnavailable(
                f"geoid grid not installed ({', '.join(needed) or 'unknown'}); heights "
                f"stay WGS84 ellipsoidal. Install: download {EGM2008_GRID} from "
                f"https://cdn.proj.org into pyproj.datadir.get_user_data_dir()")
        cache[height_crs] = group.transformers[0]
    return cache[height_crs]


def orthometric_height(lat, lon, h_ellipsoidal, *, height_crs: int = EGM2008_HEIGHT_CRS):
    """Height above sea level (EGM2008 by default), metres. Raises GeoidUnavailable."""
    tr = _vertical_transformer(height_crs)
    _, _, H = tr.transform(np.asarray(lon, float), np.asarray(lat, float),
                           np.asarray(h_ellipsoidal, float))
    return np.atleast_1d(np.asarray(H, float))


def _geoid_height(lat, lon) -> float:
    """EGM2008 geoid height N at a point (``h = H + N``). Raises GeoidUnavailable."""
    return -float(orthometric_height(lat, lon, 0.0)[0])


def describe(frame: ENUFrame, enu, *, georeferenced: bool = True,
             vertical_datum: str = "unknown") -> dict:
    """Every coordinate form of one local ENU point, each labelled.

    For a cloud that is not georeferenced there is nothing to give: its
    coordinates are reconstruction units with no place on the earth.

    Heights depend on ``vertical_datum``, the telemetry's
    (``geo.VERTICAL_DATUMS``):

    * ``ellipsoidal``: the height as stored, and above sea level via EGM2008.
    * ``msl``: the height as stored *is* above sea level, on the source's own
      geoid model; ellipsoidal is derived with EGM2008 and says so.
    * ``relative``: height above the take-off point only.
    * ``unknown``: no height. A number with no datum would be read as one.
    """
    if not georeferenced:
        return {"georeferenced": False,
                "note": "relative scale: this reconstruction has no position on the earth"}
    p = np.asarray(enu, float).reshape(1, 3)
    lat, lon, h = (float(v) for v in frame.enu_to_geodetic(p)[0])
    utm, epsg = enu_to_utm(frame, p)
    out = {
        "georeferenced": True,
        "lat": lat, "lon": lon,
        "utm": {"epsg": epsg, "zone": f"{epsg % 100}{'N' if epsg < 32700 else 'S'}",
                "easting_m": float(utm[0, 0]), "northing_m": float(utm[0, 1])},
        "vertical_datum": vertical_datum,
        "h_ellipsoidal_m": None, "h_msl_m": None,
    }
    try:
        import mgrs
        out["mgrs"] = mgrs.MGRS().toMGRS(lat, lon, MGRSPrecision=5)
    except ImportError:
        out["mgrs"] = None
    try:
        if vertical_datum == "ellipsoidal":
            out["h_ellipsoidal_m"] = h
            out["h_msl_m"] = h - _geoid_height(lat, lon)
            out["h_msl_model"] = "EGM2008"
        elif vertical_datum == "msl":
            out["h_msl_m"] = h
            out["h_msl_model"] = "as recorded; geoid model not stated"
            out["h_ellipsoidal_m"] = h + _geoid_height(lat, lon)
            out["h_ellipsoidal_model"] = "derived with EGM2008"
        elif vertical_datum == "relative":
            out["h_relative_m"] = h
            out["height_note"] = ("Heights are relative to the take-off point; the "
                                  "telemetry gives no absolute datum.")
        else:
            out["height_note"] = ("The telemetry does not say what its altitude is "
                                  "measured from, so no absolute height is given. "
                                  "Heights and distances within the scene are unaffected.")
    except GeoidUnavailable as exc:
        out["height_note"] = str(exc)
    return out


__all__ = ["GeoidUnavailable", "orthometric_height", "describe", "utm_epsg"]
