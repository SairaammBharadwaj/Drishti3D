"""Explicit SE(3) frame chain: GNSS/IMU body -> gimbal -> optical centre.

Every frame in this pipeline is named and its axes are written down, because
the failure mode here is silent: a wrong convention produces a plausible
reconstruction in the wrong place, and Sim(3) alignment to GNSS will happily
absorb part of the error and hide the rest.

Conventions, fixed once:

===========  =========================================================
frame        axes
===========  =========================================================
``ENU``      x east, y north, z up            (local metric world)
``NED``      x north, y east, z down          (navigation)
``BODY``     x forward (nose), y right, z down  (FRD, aircraft)
``CAM``      x right, y down, z forward       (OpenCV optical)
===========  =========================================================

``CAM`` is the convention DUSt3R/MASt3R/VGGT and OpenCV all emit, so it is the
one the reconstruction code speaks. ``ENU`` is what georegistration speaks.
This module owns the transforms between them and nothing else does.

**Gimbal angles are world-referenced by default.** A 3-axis gimbal stabilises
the camera against aircraft motion, so DJI reports gimbal yaw/pitch/roll
relative to the world, not to the airframe. Composing them onto the body
rotation -- the intuitive reading -- double-counts aircraft attitude and yaws
the camera with the aircraft even though the gimbal exists precisely to stop
that. Pass ``gimbal_relative_to_body=True`` only for a rigidly-mounted or
body-referenced rig.
"""
from __future__ import annotations

import numpy as np

#: Rotation taking a vector expressed in CAM axes into BODY axes, for a camera
#: bolted to the airframe looking straight down the nose. Columns are the
#: camera axes written in body coordinates: cam +x (right) is body +y, cam +y
#: (down) is body +z, cam +z (forward) is body +x.
R_BODY_FROM_CAM = np.array([[0.0, 0.0, 1.0],
                            [1.0, 0.0, 0.0],
                            [0.0, 1.0, 0.0]])

#: NED <-> ENU: swap north/east and flip down. Its own inverse.
R_ENU_FROM_NED = np.array([[0.0, 1.0, 0.0],
                           [1.0, 0.0, 0.0],
                           [0.0, 0.0, -1.0]])


def R_ned_from_body(roll_deg, pitch_deg, yaw_deg) -> np.ndarray:
    """Aircraft attitude as a rotation BODY -> NED (ZYX / yaw-pitch-roll).

    Yaw is a compass heading: 0 deg north, increasing clockwise toward east.
    """
    r, p, y = (np.radians(float(v or 0.0)) for v in (roll_deg, pitch_deg, yaw_deg))
    cr, sr = np.cos(r), np.sin(r)
    cp, sp = np.cos(p), np.sin(p)
    cy, sy = np.cos(y), np.sin(y)
    return np.array([
        [cp * cy, sr * sp * cy - cr * sy, cr * sp * cy + sr * sy],
        [cp * sy, sr * sp * sy + cr * cy, cr * sp * sy - sr * cy],
        [-sp,     sr * cp,                cr * cp],
    ])


def R_enu_from_body(roll_deg, pitch_deg, yaw_deg) -> np.ndarray:
    """BODY -> ENU."""
    return R_ENU_FROM_NED @ R_ned_from_body(roll_deg, pitch_deg, yaw_deg)


def R_enu_from_cam(gimbal_roll_deg, gimbal_pitch_deg, gimbal_yaw_deg, *,
                   body_rpy_deg=None, gimbal_relative_to_body: bool = False,
                   boresight_rpy_deg=None) -> np.ndarray:
    """Rotation CAM -> ENU for one frame.

    ``gimbal_*``  camera attitude. World-referenced unless
                  ``gimbal_relative_to_body``, in which case ``body_rpy_deg``
                  is required and the gimbal rotation is applied on top of it.
    ``boresight_rpy_deg``  fixed misalignment between the gimbal's reported
                  attitude and the true optical axis, in BODY-style axes.
                  Applied innermost, next to the camera.

    A DJI gimbal pitch of -90 deg is straight down; 0 deg is the horizon.
    """
    if gimbal_relative_to_body:
        if body_rpy_deg is None:
            raise ValueError(
                "gimbal_relative_to_body=True needs body_rpy_deg: a "
                "body-referenced gimbal angle is meaningless without the "
                "airframe attitude it is measured against")
        br, bp, by = body_rpy_deg
        R_eb = R_enu_from_body(br, bp, by)
        R_bg = R_ned_from_body(gimbal_roll_deg, gimbal_pitch_deg, gimbal_yaw_deg)
        R_e_mount = R_eb @ R_bg
    else:
        R_e_mount = R_enu_from_body(gimbal_roll_deg, gimbal_pitch_deg,
                                    gimbal_yaw_deg)
    if boresight_rpy_deg is not None:
        R_e_mount = R_e_mount @ R_ned_from_body(*boresight_rpy_deg)
    return R_e_mount @ R_BODY_FROM_CAM


def optical_centre_enu(gnss_enu, lever_body, *, body_rpy_deg=None,
                       gimbal_rpy_deg=None, lever_on_gimbal=False):
    """Move a GNSS antenna position to the camera's optical centre.

    ``lever_body`` is the optical centre relative to the antenna phase centre,
    in BODY axes (x forward, y right, z down), metres.

    The offset is fixed in the *vehicle*, so as the aircraft rotates it traces
    a circle in the world: ignoring it on a yawing flight injects a rotating
    bias, not a constant one that alignment could absorb. Set
    ``lever_on_gimbal`` when the offset is measured from the gimbal's rotating
    frame instead of the airframe.
    """
    gnss = np.asarray(gnss_enu, float).reshape(-1, 3)
    lever = np.asarray(lever_body, float).ravel()
    if lever.shape != (3,) or not np.any(lever):
        return gnss.copy(), False
    n = len(gnss)

    def _col(v):
        if v is None:
            return None
        a = np.asarray(v, float)
        return np.broadcast_to(a, (n, 3)) if a.ndim == 1 else a[:n]

    rpy = _col(gimbal_rpy_deg if lever_on_gimbal else body_rpy_deg)
    if rpy is None:
        return gnss.copy(), False
    out = gnss.copy()
    for i in range(n):
        out[i] = gnss[i] + R_enu_from_body(*rpy[i]) @ lever
    return out, True


def cam_from_world_matrix(R_enu_cam, centre_enu) -> np.ndarray:
    """4x4 world->camera extrinsic from a CAM->ENU rotation and a centre.

    Returned in the convention the reconstruction code uses: ``X_cam = R @
    (X_enu - C)``, i.e. rotation is ENU->CAM and translation is ``-R C``.
    """
    R = np.asarray(R_enu_cam, float).T                 # ENU -> CAM
    C = np.asarray(centre_enu, float).ravel()
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = -R @ C
    return T


def optical_axis_enu(R_enu_cam) -> np.ndarray:
    """Unit vector the camera looks along, in ENU. CAM +z is forward."""
    return np.asarray(R_enu_cam, float)[:, 2]
