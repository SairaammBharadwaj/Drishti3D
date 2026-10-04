"""Flight replay: the reconstructed camera at any moment of the source video.

The cameras exist only at keyframes (``trajectory.json``'s ``cameras_enu``,
timed by ``keyframes.json``). Between two keyframes the pose is interpolated:
centre linearly, orientation by spherical interpolation. The result is labelled
so a viewer can say how far it is from a solved pose:

``synced``
    within the reconstructed span, and the bracketing keyframes are at most
    ``max_gap_s`` apart.
``gap``
    within the span, but the keyframes either side are further apart than
    that (the camera was lost, or frames were rejected): the pose is a guess
    across the gap.
``out_of_range``
    before the first or after the last solved keyframe: no pose is given.

Conventions. ``R`` in ``cameras_enu`` is OpenCV's world-to-camera rotation in
ENU: its rows are the camera's x (right), y (down) and z (forward) axes in
world coordinates. A Three.js camera looks down its local -Z with +Y up, so its
camera-to-world rotation is ``R.T @ diag(1, -1, -1)``. Getting this wrong
produces a camera that looks straight up out of the scene, which is why the
conversion lives here, tested, and the browser only interpolates.
"""
from __future__ import annotations

import bisect

import numpy as np

#: Keyframes further apart than this make the pose between them a "gap".
MAX_GAP_S = 2.0
_FLIP = np.diag([1.0, -1.0, -1.0])


def opencv_to_three_rotation(R_wc) -> np.ndarray:
    """OpenCV world->camera rotation -> Three.js camera->world rotation."""
    return np.asarray(R_wc, float).reshape(3, 3).T @ _FLIP


def matrix_to_quaternion(M) -> np.ndarray:
    """Rotation matrix -> unit quaternion (x, y, z, w), w >= 0."""
    m = np.asarray(M, float)
    tr = np.trace(m)
    if tr > 0:
        s = 2.0 * np.sqrt(tr + 1.0)
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s,
             (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2])
        q = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s,
             (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2])
        q = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s,
             (m[0, 2] - m[2, 0]) / s]
    else:
        s = 2.0 * np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1])
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s,
             (m[1, 0] - m[0, 1]) / s]
    q = np.asarray(q)
    q /= np.linalg.norm(q)
    return -q if q[3] < 0 else q


def quaternion_to_matrix(q) -> np.ndarray:
    x, y, z, w = np.asarray(q, float) / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def slerp(q0, q1, t: float) -> np.ndarray:
    q0, q1 = np.asarray(q0, float), np.asarray(q1, float)
    d = float(np.dot(q0, q1))
    if d < 0:                       # take the short way round
        q1, d = -q1, -d
    if d > 0.9995:
        q = q0 + t * (q1 - q0)
        return q / np.linalg.norm(q)
    th = np.arccos(d)
    return (np.sin((1 - t) * th) * q0 + np.sin(t * th) * q1) / np.sin(th)


def build_track(cameras_enu, keyframes) -> list[dict]:
    """Solved cameras with their video time, sorted, in Three.js convention.

    ``keyframes`` is ``keyframes.json`` (frame_index, timestamp). Cameras
    whose frame has no timestamp, or that carry no rotation, are left out.
    """
    times = {int(k["frame_index"]): float(k["timestamp"]) for k in keyframes}
    track = []
    for c in cameras_enu:
        fi = int(c["frame_index"])
        if fi not in times or c.get("R") is None:
            continue
        q = matrix_to_quaternion(opencv_to_three_rotation(c["R"]))
        track.append({"t": times[fi], "frame_index": fi,
                      "position": [float(v) for v in c["C"]],
                      "quaternion": [float(v) for v in q]})
    track.sort(key=lambda k: k["t"])
    return track


def pose_at(track: list[dict], t: float, *, max_gap_s: float = MAX_GAP_S) -> dict:
    """The interpolated Three.js pose at video time ``t`` seconds."""
    if not track:
        return {"status": "out_of_range", "reason": "no solved cameras"}
    ts = [k["t"] for k in track]
    if t < ts[0] or t > ts[-1]:
        return {"status": "out_of_range", "t": t,
                "reason": "outside the reconstructed span "
                          f"({ts[0]:.2f}-{ts[-1]:.2f} s)"}
    i = bisect.bisect_right(ts, t) - 1
    if i >= len(track) - 1:
        k = track[-1]
        return {"status": "synced", "t": t, "position": k["position"],
                "quaternion": k["quaternion"], "frame_index": k["frame_index"],
                "dt_to_keyframe_s": 0.0}
    a, b = track[i], track[i + 1]
    span = b["t"] - a["t"]
    w = 0.0 if span <= 0 else (t - a["t"]) / span
    pos = (1 - w) * np.asarray(a["position"]) + w * np.asarray(b["position"])
    q = slerp(a["quaternion"], b["quaternion"], w)
    nearest = a if w < 0.5 else b
    return {"status": "gap" if span > max_gap_s else "synced", "t": t,
            "position": pos.tolist(), "quaternion": q.tolist(),
            "frame_index": nearest["frame_index"],
            "dt_to_keyframe_s": float(min(t - a["t"], b["t"] - t)),
            "bracket_s": float(span)}


__all__ = ["build_track", "pose_at", "opencv_to_three_rotation", "matrix_to_quaternion",
           "quaternion_to_matrix", "slerp", "MAX_GAP_S"]
